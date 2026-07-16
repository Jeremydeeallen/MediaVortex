import os
import queue
import subprocess
import sys
import threading
import time
import uuid

from Core.Logging.LoggingService import LoggingService
from Features.AudioNormalization.Services.DemucsDaemonProtocol import (
    EncodeRequest,
    DecodeResponse,
    IsolateRequest,
    IsolateResponse,
    READY_LINE,
)


class DemucsDaemonUnavailableError(RuntimeError):
    """Daemon subprocess failed to start or exited unexpectedly."""


# directive: transcode-flow-canonical -- process-singleton amortizes model load + XPU compile across every job the worker handles
_SINGLETON = None
_SINGLETON_LOCK = threading.Lock()


def GetOrStartDaemon(PythonExe=None, StartTimeoutSec=180):
    """Process-singleton accessor: create + start on first call, return existing daemon after."""
    global _SINGLETON
    with _SINGLETON_LOCK:
        if _SINGLETON is None or _SINGLETON._Proc is None or _SINGLETON._Proc.poll() is not None:
            _SINGLETON = DemucsDaemonClient(PythonExe=PythonExe, StartTimeoutSec=StartTimeoutSec)
            _SINGLETON.Start()
        return _SINGLETON


# directive: transcode-flow-canonical -- long-lived Demucs process amortizes model load + XPU compile
class DemucsDaemonClient:
    """Owns the long-lived Demucs subprocess for one WorkerService instance."""

    # directive: transcode-flow-canonical -- IsolateReadTimeoutSec caps blocking read so a hung daemon does not deadlock the WorkerService thread
    def __init__(self, PythonExe=None, StartTimeoutSec=180, IsolateReadTimeoutSec=1800):
        self._PythonExe = PythonExe or sys.executable
        self._StartTimeoutSec = StartTimeoutSec
        self._IsolateReadTimeoutSec = IsolateReadTimeoutSec
        self._Proc = None
        self._Lock = threading.Lock()
        self._StdoutQueue = None
        self._ReaderThread = None

    def Start(self):
        with self._Lock:
            if self._Proc is not None and self._Proc.poll() is None:
                return
            Entry = os.path.join(
                os.path.dirname(os.path.abspath(__file__)),
                'DemucsDaemonEntry.py',
            )
            self._Proc = subprocess.Popen(
                [self._PythonExe, Entry],
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                bufsize=1,
            )
            # directive: transcode-flow-canonical -- background reader thread makes deadline reads cross-platform (Windows select() rejects pipe fds)
            self._StdoutQueue = queue.Queue()
            self._ReaderThread = threading.Thread(target=self._StdoutReaderLoop, name='DemucsDaemonStdoutReader', daemon=True)
            self._ReaderThread.start()
            Ready = self._WaitForReady()
            if not Ready:
                self._Kill()
                raise DemucsDaemonUnavailableError('Demucs daemon did not emit READY line')
            LoggingService.LogInfo('Demucs daemon ready', 'DemucsDaemonClient', 'Start')

    def _StdoutReaderLoop(self):
        try:
            for Line in iter(self._Proc.stdout.readline, ''):
                self._StdoutQueue.put(Line)
        except (ValueError, OSError):
            pass
        finally:
            self._StdoutQueue.put(None)

    def _WaitForReady(self):
        Deadline = time.monotonic() + self._StartTimeoutSec
        while time.monotonic() < Deadline:
            try:
                Line = self._StdoutQueue.get(timeout=1.0)
            except queue.Empty:
                if self._Proc.poll() is not None:
                    Stderr = (self._Proc.stderr.read() or '')[:1000]
                    LoggingService.LogError(
                        f'Demucs daemon exited before READY (rc={self._Proc.returncode}): {Stderr}',
                        'DemucsDaemonClient', '_WaitForReady',
                    )
                    return False
                continue
            if Line is None:
                return False
            if Line.strip() == READY_LINE:
                return True
        return False

    def IsolateVocals(self, InputWavPath, OutputDir, ModelName='htdemucs'):
        with self._Lock:
            if self._Proc is None or self._Proc.poll() is not None:
                raise DemucsDaemonUnavailableError('Demucs daemon not running; call Start() first or restart on crash')
            Req = IsolateRequest(
                RequestId=str(uuid.uuid4()),
                InputWavPath=InputWavPath,
                OutputDir=OutputDir,
                ModelName=ModelName,
            )
            self._Proc.stdin.write(EncodeRequest(Req) + '\n')
            self._Proc.stdin.flush()
            try:
                ResponseLine = self._ReadLineWithDeadline(self._IsolateReadTimeoutSec)
            except DemucsDaemonUnavailableError:
                self._Kill()
                raise
            if not ResponseLine:
                Stderr = (self._Proc.stderr.read() or '')[:1000] if self._Proc and self._Proc.stderr else ''
                self._Kill()
                raise DemucsDaemonUnavailableError(f'Demucs daemon closed stdout unexpectedly. Stderr tail: {Stderr}')
            Resp: IsolateResponse = DecodeResponse(ResponseLine.strip())
            if Resp.RequestId != Req.RequestId:
                self._Kill()
                raise DemucsDaemonUnavailableError(f'Response request-id mismatch: expected {Req.RequestId}, got {Resp.RequestId}')
            return Resp

    # directive: transcode-flow-canonical -- deadline read via reader-thread queue; cross-platform (Windows select() rejects pipe fds); returns '' on daemon exit, raises on wall-clock timeout
    def _ReadLineWithDeadline(self, TimeoutSec):
        Deadline = time.monotonic() + TimeoutSec
        while True:
            Remaining = Deadline - time.monotonic()
            if Remaining <= 0:
                raise DemucsDaemonUnavailableError(f'Demucs daemon response timeout after {TimeoutSec}s')
            try:
                Line = self._StdoutQueue.get(timeout=min(1.0, Remaining))
            except queue.Empty:
                if self._Proc.poll() is not None:
                    return ''
                continue
            if Line is None:
                return ''
            return Line

    def Stop(self):
        with self._Lock:
            self._Kill()

    def _Kill(self):
        if self._Proc is None:
            return
        try:
            if self._Proc.stdin and not self._Proc.stdin.closed:
                self._Proc.stdin.close()
            self._Proc.terminate()
            try:
                self._Proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self._Proc.kill()
        finally:
            self._Proc = None
