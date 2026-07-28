import sys
import threading
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))


# directive: audio-language-detection C1
class TestBackendSelectionThreadSafe(unittest.TestCase):

    def setUp(self):
        from Core.WorkerContext import WorkerContext
        WorkerContext.Reset()
        WorkerContext.Initialize(
            WorkerName='test-worker', Platform='linux',
            FFmpegPath='/usr/bin/ffmpeg', FFprobePath='/usr/bin/ffprobe',
        )

    def tearDown(self):
        from Core.WorkerContext import WorkerContext
        WorkerContext.Reset()

    def _RunInThread(self, Bind):
        from Core.WorkerContext import WorkerContext
        from Features.AudioNormalization.Services.LanguageEnrichmentService import LanguageEnrichmentService
        Result = {}

        def _Run():
            if Bind:
                WorkerContext.Bind()
            Result['Service'] = LanguageEnrichmentService()

        T = threading.Thread(target=_Run)
        T.start()
        T.join()
        return Result['Service']

    def test_backend_selection_returns_non_stub_on_unbound_thread(self):
        Service = self._RunInThread(Bind=False)
        Name = type(Service.Backend).__name__
        self.assertNotEqual(Name, '_StubLanguageIdBackend',
                            msg=f'unbound thread got stub; expected FasterWhisperBackend when faster-whisper installed')

    def test_backend_selection_returns_non_stub_on_bound_thread(self):
        Service = self._RunInThread(Bind=True)
        Name = type(Service.Backend).__name__
        self.assertNotEqual(Name, '_StubLanguageIdBackend',
                            msg=f'bound thread got stub; expected FasterWhisperBackend when faster-whisper installed')


if __name__ == '__main__':
    unittest.main()
