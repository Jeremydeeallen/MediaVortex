# directive: local-staging-cleanup-restore | # see local-staging.S5
import inspect
import unittest


class TestJobProcessorScratchCleanup(unittest.TestCase):

    def _JobProcessorProcessSource(self):
        from Features.TranscodeJob.Worker.JobProcessor import JobProcessor
        return inspect.getsource(JobProcessor.Process)

    def test_process_calls_cleanup_job_scratch_dir(self):
        Src = self._JobProcessorProcessSource()
        self.assertIn('CleanupJobScratchDir', Src, "JobProcessor.Process must call CleanupJobScratchDir on terminal state")

    def test_cleanup_lives_in_finally_block(self):
        Src = self._JobProcessorProcessSource()
        FinallyIdx = Src.rfind('finally:')
        CleanupIdx = Src.rfind('CleanupJobScratchDir')
        self.assertGreater(FinallyIdx, 0, "JobProcessor.Process must have a finally block")
        self.assertGreater(CleanupIdx, FinallyIdx, "CleanupJobScratchDir must run inside the finally block (both success + exception paths)")

    def test_cleanup_gated_on_mediafile_present(self):
        Src = self._JobProcessorProcessSource()
        self.assertIn('MediaFile is not None', Src, "Cleanup must gate on MediaFile presence to avoid AttributeError before load")

    def test_dead_shim_process_transcode_queue_service_gone(self):
        from Features.TranscodeJob import ProcessTranscodeQueueService as PtqsMod
        self.assertFalse(hasattr(PtqsMod.ProcessTranscodeQueueService, '_CleanupLocalScratchForAttempt'),
                         "_CleanupLocalScratchForAttempt shim must be deleted; JobProcessor calls LocalStagingService directly")

    def test_dead_shim_temporary_file_paths_service_gone(self):
        from Features.TranscodeJob.Worker import TemporaryFilePathsService as TfpsMod
        self.assertFalse(hasattr(TfpsMod.TemporaryFilePathsService, 'CleanupLocalScratch'),
                         "TemporaryFilePathsService.CleanupLocalScratch shim must be deleted")


if __name__ == '__main__':
    unittest.main()
