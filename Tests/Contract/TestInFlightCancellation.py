"""Conformance: long-running worker loops honor StopRequested at safe boundaries.

Asserts the invariant from Features/ServiceControl/graceful-drain.feature.md
across the four worker-side long-running operations (transcode, remux,
quality-test, scan). Each loop must exit within N seconds of the stop flag
being set, without killing whatever it was doing mid-job.

Run:
    py -m pytest Tests/Contract/TestInFlightCancellation.py -v
"""

import threading
import time
import unittest


_STOP_RESPONSE_BUDGET_SEC = 10
_LOOP_STARTUP_WAIT_SEC = 0.5


def _RunLoopAndStop(LoopFn, SetStopFn) -> bool:
    """Spawn LoopFn in a thread, wait briefly, set stop, return True if thread exited within budget."""
    T = threading.Thread(target=LoopFn, daemon=True)
    T.start()
    time.sleep(_LOOP_STARTUP_WAIT_SEC)
    SetStopFn()
    T.join(timeout=_STOP_RESPONSE_BUDGET_SEC)
    return not T.is_alive()


class TestTranscodeLoopStopsOnStopRequested(unittest.TestCase):
    def test_stop_request_exits_loop(self):
        from Features.TranscodeJob.ProcessTranscodeQueueService import ProcessTranscodeQueueService
        Svc = ProcessTranscodeQueueService.__new__(ProcessTranscodeQueueService)
        Svc.IsProcessing = True
        Svc.MaxConcurrentJobs = 1
        Svc.ActiveJobs = []
        Svc.StopRequested = False
        Svc.GetNextJob = lambda: None
        Svc.ProcessJob = lambda Job: None
        Exited = _RunLoopAndStop(Svc.ProcessQueueLoop, lambda: setattr(Svc, "StopRequested", True))
        self.assertTrue(Exited, f"Transcode loop did not exit within {_STOP_RESPONSE_BUDGET_SEC}s of StopRequested=True")


class TestQualityTestLoopStopsOnStopRequested(unittest.TestCase):
    def test_stop_request_exits_loop(self):
        from Features.QualityTesting.ProcessQualityTestQueueService import ProcessQualityTestQueueService
        Svc = ProcessQualityTestQueueService.__new__(ProcessQualityTestQueueService)
        Svc.IsProcessing = True
        Svc.MaxConcurrentJobs = 1
        Svc.ActiveJobs = []
        Svc.StopRequested = False
        Svc.ClaimNextJob = lambda: None
        Svc.ProcessJob = lambda Job: None
        Exited = _RunLoopAndStop(Svc.ProcessQueueLoop, lambda: setattr(Svc, "StopRequested", True))
        self.assertTrue(Exited, f"QualityTest loop did not exit within {_STOP_RESPONSE_BUDGET_SEC}s of StopRequested=True")


class TestRemuxLoopStopsOnStopRequested(unittest.TestCase):
    def test_stop_request_exits_loop(self):
        from Features.TranscodeJob.ProcessRemuxQueueService import ProcessRemuxQueueService
        Svc = ProcessRemuxQueueService.__new__(ProcessRemuxQueueService)
        Svc.IsProcessing = True
        Svc.MaxConcurrentJobs = 1
        Svc.ActiveJobs = []
        Svc.StopRequested = False
        Svc.GetNextJob = lambda: None
        Svc.ProcessJob = lambda Job: None
        Exited = _RunLoopAndStop(Svc.ProcessQueueLoop, lambda: setattr(Svc, "StopRequested", True))
        self.assertTrue(Exited, f"Remux loop did not exit within {_STOP_RESPONSE_BUDGET_SEC}s of StopRequested=True")


class TestScanStopScanningFlipsStopRequested(unittest.TestCase):
    """The scan walker has multiple `if self._StopRequested: return` checkpoints
    rather than a single top-level loop guard. Verify that StopScanning() flips
    the flag synchronously so those checkpoints see it on their next pass."""

    def test_stop_scanning_sets_stop_requested(self):
        from Features.FileScanning.FileScanningBusinessService import FileScanningBusinessService
        Svc = FileScanningBusinessService.__new__(FileScanningBusinessService)
        Svc.CurrentJobId = "_test-sentinel-job"
        Svc.IsScanning = True
        Svc.ScanProgress = 50.0
        Svc.CurrentScanDirectory = "_test"
        Svc._StopRequested = False
        Svc.UpdateJobStatus = lambda *args, **kwargs: None
        Result = Svc.StopScanning()
        self.assertTrue(Result.get("Success"))
        self.assertTrue(Svc._StopRequested, "StopScanning must set _StopRequested=True so per-file checkpoints exit")


class TestSignalHandlerDrainsCapabilities(unittest.TestCase):
    """SignalHandler must call _StopAllCapabilities (graceful) instead of Proc.kill (immediate)."""

    def test_signal_handler_invokes_stop_all_capabilities(self):
        import os as _os
        import WorkerService.Main as WM
        FakeApp = type("FakeApp", (), {})()
        FakeApp.TranscodeService = None
        FakeApp.RemuxService = None
        FakeApp.QualityTestService = None
        FakeApp.ContinuousScanService = None
        Called = {"stop_all": False, "exit": False}
        FakeApp._StopAllCapabilities = lambda: Called.__setitem__("stop_all", True)
        FakeApp.DatabaseManager = type("FakeDb", (), {"UpdateServiceStatus": staticmethod(lambda *a, **kw: None)})()
        OriginalApp = getattr(WM.Main, "app", None)
        OriginalExit = _os._exit
        WM.Main.app = FakeApp
        WM.SignalHandler._in_progress = False

        def _MockExit(code):
            Called["exit"] = True
            raise SystemExit(code)

        _os._exit = _MockExit
        try:
            with self.assertRaises(SystemExit):
                WM.SignalHandler(15, None)
        finally:
            _os._exit = OriginalExit
            WM.SignalHandler._in_progress = False
            if OriginalApp is None and hasattr(WM.Main, "app"):
                del WM.Main.app
            elif OriginalApp is not None:
                WM.Main.app = OriginalApp
        self.assertTrue(Called["stop_all"], "SignalHandler must invoke _StopAllCapabilities (graceful drain)")
        self.assertTrue(Called["exit"], "SignalHandler must terminate via os._exit after drain")


if __name__ == "__main__":
    unittest.main()
