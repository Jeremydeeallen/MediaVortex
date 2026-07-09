# directive: transcode-flow-canonical | # see worker-loop.C4
import threading
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from Features.TranscodeJob.Worker.WorkerLoopService import WorkerLoopService


class _StubRegistry:
    def Get(self, Mode):
        raise KeyError(Mode)


class _StubDb:
    pass


# directive: transcode-flow-canonical
class TestWorkerLoopSlotCap(unittest.TestCase):

    def test_semaphore_capacity_matches_max_concurrent_jobs(self):
        Wls = WorkerLoopService(
            DatabaseManager=_StubDb(),
            JobProcessorRegistryInstance=_StubRegistry(),
            WorkerName='test-worker',
            TranscodeEnabled=True, RemuxEnabled=True,
            MaxConcurrentJobs=1,
        )
        self.assertEqual(Wls.MaxConcurrentJobs, 1)
        self.assertTrue(Wls.SlotSemaphore.acquire(blocking=False))
        self.assertFalse(Wls.SlotSemaphore.acquire(blocking=False))
        Wls.SlotSemaphore.release()
        self.assertTrue(Wls.SlotSemaphore.acquire(blocking=False))

    def test_semaphore_capacity_scales_with_max(self):
        Wls = WorkerLoopService(
            DatabaseManager=_StubDb(),
            JobProcessorRegistryInstance=_StubRegistry(),
            WorkerName='test-worker',
            TranscodeEnabled=True, RemuxEnabled=True,
            MaxConcurrentJobs=3,
        )
        self.assertEqual(Wls.MaxConcurrentJobs, 3)
        self.assertTrue(Wls.SlotSemaphore.acquire(blocking=False))
        self.assertTrue(Wls.SlotSemaphore.acquire(blocking=False))
        self.assertTrue(Wls.SlotSemaphore.acquire(blocking=False))
        self.assertFalse(Wls.SlotSemaphore.acquire(blocking=False))

    def test_min_floor_is_one(self):
        Wls = WorkerLoopService(
            DatabaseManager=_StubDb(),
            JobProcessorRegistryInstance=_StubRegistry(),
            WorkerName='test-worker',
            TranscodeEnabled=True, RemuxEnabled=True,
            MaxConcurrentJobs=0,
        )
        self.assertEqual(Wls.MaxConcurrentJobs, 1)

    def test_slot_release_in_finally_even_on_exception(self):
        Wls = WorkerLoopService(
            DatabaseManager=_StubDb(),
            JobProcessorRegistryInstance=_StubRegistry(),
            WorkerName='test-worker',
            TranscodeEnabled=True, RemuxEnabled=True,
            MaxConcurrentJobs=1,
        )
        Wls.SlotSemaphore.acquire(blocking=False)

        class _RaisingJob:
            Id = 999
            ProcessingMode = 'BogusMode'
            IsTestMode = False

        Wls._DispatchJobWithSlotRelease(_RaisingJob())
        self.assertTrue(Wls.SlotSemaphore.acquire(blocking=False))


if __name__ == '__main__':
    unittest.main()
