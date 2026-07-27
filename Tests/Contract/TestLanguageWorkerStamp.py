import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from Features.AudioNormalization.Services.LanguageEnrichmentService import LanguageEnrichmentService


class _FixedBackend:

    def __init__(self, Language, Confidence):
        self._Lang = Language
        self._Conf = Confidence

    def Detect(self, LocalFilePath, StreamIndex, DurationSeconds=60):
        return {'Language': self._Lang, 'Confidence': self._Conf}


# directive: audio-language-detection C4 -- three branches
class TestLanguageWorkerStamp(unittest.TestCase):

    def _MakeService(self, Backend, MinConfidence=0.85):
        S = LanguageEnrichmentService(Backend=Backend)
        S._MinConfidenceOverride = MinConfidence  # test hook
        return S

    def test_english_confident_stamps_container(self):
        Backend = _FixedBackend('en', 0.99)
        Svc = self._MakeService(Backend)
        with patch('Features.AudioNormalization.Services.LanguageEnrichmentService.AudioStreamProbe') as MockProbe, \
             patch('Features.AudioNormalization.Services.LanguageEnrichmentService.subprocess.run') as MockRun, \
             patch('Features.AudioNormalization.Services.LanguageEnrichmentService.os.replace') as MockReplace, \
             patch.object(Svc, '_ResolveFFmpegPath', return_value='/usr/bin/ffmpeg'), \
             patch.object(Svc, '_PersistDetection'), \
             patch('Features.MediaProbe.MediaProbeBusinessService.MediaProbeBusinessService') as MockProbeSvc:
            MockProbe.return_value.Probe.return_value = [{'index': 0, 'tags': {'language': 'und'}, 'disposition': {}}]
            MockRun.return_value = MagicMock(returncode=0, stderr=b'')
            MockProbeSvc.return_value.ProbeFile.return_value = {'Success': True}
            Result = Svc.EnrichAndStamp(MediaFileId=1, LocalFilePath='/tmp/x.mp4')
            self.assertTrue(Result.get('Stamped'))
            MockReplace.assert_called_once()

    def test_english_low_confidence_does_not_stamp(self):
        Backend = _FixedBackend('en', 0.30)
        Svc = self._MakeService(Backend)
        with patch('Features.AudioNormalization.Services.LanguageEnrichmentService.AudioStreamProbe') as MockProbe, \
             patch('Features.AudioNormalization.Services.LanguageEnrichmentService.subprocess.run') as MockRun, \
             patch.object(Svc, '_ResolveFFmpegPath', return_value='/usr/bin/ffmpeg'), \
             patch.object(Svc, '_PersistDetection'):
            MockProbe.return_value.Probe.return_value = [{'index': 0, 'tags': {'language': 'und'}, 'disposition': {}}]
            Result = Svc.EnrichAndStamp(MediaFileId=1, LocalFilePath='/tmp/x.mp4')
            self.assertFalse(Result.get('Stamped'))
            MockRun.assert_not_called()

    def test_non_english_does_not_stamp(self):
        Backend = _FixedBackend('jpn', 0.99)
        Svc = self._MakeService(Backend)
        with patch('Features.AudioNormalization.Services.LanguageEnrichmentService.AudioStreamProbe') as MockProbe, \
             patch('Features.AudioNormalization.Services.LanguageEnrichmentService.subprocess.run') as MockRun, \
             patch.object(Svc, '_ResolveFFmpegPath', return_value='/usr/bin/ffmpeg'), \
             patch.object(Svc, '_PersistDetection'):
            MockProbe.return_value.Probe.return_value = [{'index': 0, 'tags': {'language': 'und'}, 'disposition': {}}]
            Result = Svc.EnrichAndStamp(MediaFileId=1, LocalFilePath='/tmp/x.mp4')
            self.assertFalse(Result.get('Stamped'))
            MockRun.assert_not_called()


if __name__ == '__main__':
    unittest.main()
