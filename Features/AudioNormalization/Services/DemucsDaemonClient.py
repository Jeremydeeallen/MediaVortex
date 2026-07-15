import os
import subprocess
import sys
import threading
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

    def __init__(self, PythonExe=None, StartTimeoutSec=180):
        self._PythonExe = PythonExe or sys.executable
        self._StartTimeoutSec = StartTimeoutSec
        self._Proc = None
        self._Lock = threading.Lock()

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
            Ready = self._WaitForReady()
            if not Ready:
                self._Kill()
                raise DemucsDaemonUnavailableError('Demucs daemon did not emit READY line')
            LoggingService.LogInfo('Demucs daemon ready', 'DemucsDaemonClient', 'Start')

    def _WaitForReady(self):
        import selectors
        Sel = selectors.DefaultSelector()
        Sel.register(self._Proc.stdout, selectors.EVENT_READ)
        Elapsed = 0
        while Elapsed < self._StartTimeoutSec:
            Events = Sel.select(timeout=1.0)
            for _Key, _Mask in Events:
                Line = self._Proc.stdout.readline()
                if Line.strip() == READY_LINE:
                    return True
            Elapsed += 1
            if self._Proc.poll() is not None:
                Stderr = (self._Proc.stderr.read() or '')[:1000]
                LoggingService.LogError(
                    f'Demucs daemon exited before READY (rc={self._Proc.returncode}): {Stderr}',
                    'DemucsDaemonClient', '_WaitForReady',
                )
                return False
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
            ResponseLine = self._Proc.stdout.readline()
            if not ResponseLine:
                Stderr = (self._Proc.stderr.read() or '')[:1000]
                raise DemucsDaemonUnavailableError(f'Demucs daemon closed stdout unexpectedly. Stderr tail: {Stderr}')
            Resp: IsolateResponse = DecodeResponse(ResponseLine.strip())
            if Resp.RequestId != Req.RequestId:
                raise DemucsDaemonUnavailableError(f'Response request-id mismatch: expected {Req.RequestId}, got {Resp.RequestId}')
            return Resp

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
