import queue
import subprocess
import sys
import threading
import time
import unittest

from Features.AudioNormalization.Services.DemucsDaemonClient import (
    DemucsDaemonClient,
    DemucsDaemonUnavailableError,
)


STALL_SEC = 3

BUSY_THEN_ANSWER = (
    "import sys, time\n"
    "End = time.monotonic() + 8\n"
    "while time.monotonic() < End:\n"
    "    sum(range(10000))\n"
    "sys.stdout.write('ANSWER\\n'); sys.stdout.flush()\n"
    "time.sleep(30)\n"
)

TICKS_THEN_ANSWER = (
    "import sys, time\n"
    "for I in range(16):\n"
    "    sys.stderr.write('tick %d\\n' % I); sys.stderr.flush()\n"
    "    time.sleep(0.5)\n"
    "sys.stdout.write('ANSWER\\n'); sys.stdout.flush()\n"
    "time.sleep(30)\n"
)

SILENT = "import time\ntime.sleep(60)\n"

EXITS = "import time\ntime.sleep(1)\n"


# directive: demucs-liveness | # see demucs-daemon.C8
def _ClientAround(Script):
    Client = DemucsDaemonClient('cpu', StallTimeoutSec=STALL_SEC)
    Client._Proc = subprocess.Popen(
        [sys.executable, '-c', Script],
        stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
    )
    Client._StdoutQueue = queue.Queue()
    threading.Thread(target=Client._StdoutReaderLoop, daemon=True).start()
    threading.Thread(target=Client._StderrDrainLoop, daemon=True).start()
    return Client


# directive: demucs-liveness | # see demucs-daemon.C8
class TestDemucsDaemonLiveness(unittest.TestCase):

    # directive: demucs-liveness | # see demucs-daemon.C8
    def _Run(self, Script):
        Client = _ClientAround(Script)
        self.addCleanup(Client._Proc.kill)
        Started = time.monotonic()
        try:
            return Client._ReadLineUntilStalled(STALL_SEC), time.monotonic() - Started
        except DemucsDaemonUnavailableError as Ex:
            return Ex, time.monotonic() - Started

    # directive: demucs-liveness | # see demucs-daemon.C8
    def test_cpu_work_past_the_stall_window_is_not_failed(self):
        Result, Elapsed = self._Run(BUSY_THEN_ANSWER)
        self.assertEqual(Result, 'ANSWER\n')
        self.assertGreater(Elapsed, STALL_SEC * 2)

    # directive: demucs-liveness | # see demucs-daemon.C8
    def test_progress_output_past_the_stall_window_is_not_failed(self):
        Result, Elapsed = self._Run(TICKS_THEN_ANSWER)
        self.assertEqual(Result, 'ANSWER\n')
        self.assertGreater(Elapsed, STALL_SEC * 2)

    # directive: demucs-liveness | # see demucs-daemon.C8
    def test_silent_idle_process_is_failed_as_stalled(self):
        Result, Elapsed = self._Run(SILENT)
        self.assertIsInstance(Result, DemucsDaemonUnavailableError)
        self.assertIn('stalled', str(Result))
        self.assertLess(Elapsed, STALL_SEC + 4)

    # directive: demucs-liveness | # see demucs-daemon.C8
    def test_process_exit_returns_immediately(self):
        Result, Elapsed = self._Run(EXITS)
        self.assertEqual(Result, '')
        self.assertLess(Elapsed, STALL_SEC)

    # directive: demucs-liveness | # see demucs-daemon.C8
    def test_client_has_no_total_duration_cap(self):
        Client = DemucsDaemonClient('cpu')
        self.assertFalse(hasattr(Client, '_IsolateReadTimeoutSec'))


if __name__ == '__main__':
    unittest.main()
