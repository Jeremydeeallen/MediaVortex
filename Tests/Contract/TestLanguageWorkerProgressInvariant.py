import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from Features.AudioNormalization.Services.LanguageEnrichmentError import LanguageEnrichmentError
from WorkerService.LanguageWorker import LanguageWorker


# directive: language-worker-progress-invariant C1
class TestLanguageWorkerProgressInvariant(unittest.TestCase):

    def _MakeWorker(self, Resolver=None):
        Service = MagicMock()
        Db = MagicMock()
        Worker = LanguageWorker(
            'test-worker',
            Service=Service,
            SettingsRepo=MagicMock(),
            Db=Db,
            Resolver=Resolver or MagicMock(),
        )
        Worker._CreateActiveJob = MagicMock(return_value=42)
        Worker._DeleteActiveJob = MagicMock()
        return Worker, Service

    def test_no_audio_streams_routes_to_resolver(self):
        Resolver = MagicMock()
        Worker, Service = self._MakeWorker(Resolver=Resolver)
        Service.EnrichAndStamp.side_effect = LanguageEnrichmentError(618781, 'no_audio_streams')
        Worker._ResolveOne = MagicMock()
        Worker._ProcessOne_ForTest_LocalPath = '/mnt/tv/Show/S01E01.mkv'

        with unittest.mock.patch('WorkerService.LanguageWorker.LocalExists', return_value=True), \
             unittest.mock.patch('WorkerService.LanguageWorker.CorePath') as CorePath, \
             unittest.mock.patch('WorkerService.LanguageWorker.CoreWorker') as CoreWorker:
            CoreWorker.Current.return_value = MagicMock()
            CorePath.return_value.Resolve.return_value = '/mnt/tv/Show/S01E01.mkv'
            Worker._ProcessOne({'id': 618781, 'storagerootid': 1, 'relativepath': 'Show/S01E01.mkv', 'filename': 'S01E01.mkv'})
        Resolver.Resolve.assert_called_once_with(618781, '/mnt/tv/Show/S01E01.mkv')

    def test_non_no_audio_error_does_not_call_resolver(self):
        Resolver = MagicMock()
        Worker, Service = self._MakeWorker(Resolver=Resolver)
        Service.EnrichAndStamp.side_effect = LanguageEnrichmentError(42, 'ffmpeg_returncode_nonzero')
        with unittest.mock.patch('WorkerService.LanguageWorker.LocalExists', return_value=True), \
             unittest.mock.patch('WorkerService.LanguageWorker.CorePath') as CorePath, \
             unittest.mock.patch('WorkerService.LanguageWorker.CoreWorker') as CoreWorker:
            CoreWorker.Current.return_value = MagicMock()
            CorePath.return_value.Resolve.return_value = '/mnt/tv/Show/foo.mkv'
            Worker._ProcessOne({'id': 42, 'storagerootid': 1, 'relativepath': 'Show/foo.mkv', 'filename': 'foo.mkv'})
        Resolver.Resolve.assert_not_called()

    def test_resolver_lazy_instantiated_when_absent(self):
        Service = MagicMock()
        Db = MagicMock()
        Worker = LanguageWorker('test-worker', Service=Service, SettingsRepo=MagicMock(), Db=Db)
        Worker._CreateActiveJob = MagicMock(return_value=42)
        Worker._DeleteActiveJob = MagicMock()
        Service.EnrichAndStamp.side_effect = LanguageEnrichmentError(42, 'no_audio_streams')
        with unittest.mock.patch('WorkerService.LanguageWorker.NoAudioResolver') as NoAudio, \
             unittest.mock.patch('WorkerService.LanguageWorker.LocalExists', return_value=True), \
             unittest.mock.patch('WorkerService.LanguageWorker.CorePath') as CorePath, \
             unittest.mock.patch('WorkerService.LanguageWorker.CoreWorker') as CoreWorker:
            CoreWorker.Current.return_value = MagicMock()
            CorePath.return_value.Resolve.return_value = '/mnt/tv/foo/bar.mkv'
            Worker._ProcessOne({'id': 42, 'storagerootid': 1, 'relativepath': 'foo/bar.mkv', 'filename': 'bar.mkv'})
        NoAudio.assert_called_once()
        NoAudio.return_value.Resolve.assert_called_once_with(42, '/mnt/tv/foo/bar.mkv')


if __name__ == '__main__':
    unittest.main()
