import sys
import threading
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))


# directive: audio-language-detection
class TestBackendSelectionThreadSafe(unittest.TestCase):

    def test_backend_selection_returns_non_stub_on_unbound_thread(self):
        from Features.AudioNormalization.Services.LanguageEnrichmentService import LanguageEnrichmentService

        Result = {}

        def _Run():
            Result['Service'] = LanguageEnrichmentService()

        T = threading.Thread(target=_Run)
        T.start()
        T.join()
        Service = Result['Service']
        Name = type(Service.Backend).__name__
        self.assertNotIn(Name, ('_StubLanguageIdBackend', 'StubLanguageIdBackend'))

    def test_backend_selection_returns_non_stub_on_bound_thread(self):
        from Core.WorkerContext import WorkerContext
        from Features.AudioNormalization.Services.LanguageEnrichmentService import LanguageEnrichmentService

        Result = {}

        def _Run():
            WorkerContext.Bind()
            Result['Service'] = LanguageEnrichmentService()

        T = threading.Thread(target=_Run)
        T.start()
        T.join()
        Service = Result['Service']
        Name = type(Service.Backend).__name__
        self.assertNotIn(Name, ('_StubLanguageIdBackend', 'StubLanguageIdBackend'))


if __name__ == '__main__':
    unittest.main()
