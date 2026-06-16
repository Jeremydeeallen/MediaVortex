import json
import sys
import unittest
from pathlib import Path
from unittest.mock import patch, MagicMock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from Features.AudioNormalization.Services.LanguageEnrichmentService import (
    LanguageEnrichmentService,
)


# directive: perfect-audio-vertical | # see perfect-audio-vertical.C19
class _CountingBackend:
    """Backend that records every Detect call so cache-hit paths can be asserted."""

    # directive: perfect-audio-vertical | # see perfect-audio-vertical.C19
    def __init__(self, Result=None):
        self.Calls = []
        self.Result = Result or {'Language': 'eng', 'Confidence': 0.92}

    # directive: perfect-audio-vertical | # see perfect-audio-vertical.C19
    def Detect(self, LocalFilePath, StreamIndex, DurationSeconds=60):
        self.Calls.append((LocalFilePath, StreamIndex))
        return self.Result


# directive: perfect-audio-vertical | # see perfect-audio-vertical.C19
class TestLanguageEnrichmentService(unittest.TestCase):
    """C19: backend runs once per stream, cache hit skips re-run, results persist to AudioStreamLanguageDetectionsJson."""

    # directive: perfect-audio-vertical | # see perfect-audio-vertical.C19
    def test_first_admission_runs_backend(self):
        Backend = _CountingBackend()
        Svc = LanguageEnrichmentService(Backend=Backend)
        with patch(
            'Features.AudioNormalization.Services.LanguageEnrichmentService.DatabaseService'
        ) as MockDb:
            Instance = MagicMock()
            MockDb.return_value = Instance
            Instance.ExecuteQuery.return_value = [{'audiostreamlanguagedetectionsjson': None}]
            Cached = Svc.Enrich(MediaFileId=42, LocalFilePath='/tmp/foo.mp4', StreamIndices=(0,))
            self.assertEqual(len(Backend.Calls), 1)
            self.assertEqual(Cached['0']['Language'], 'eng')
            Instance.ExecuteNonQuery.assert_called_once()

    # directive: perfect-audio-vertical | # see perfect-audio-vertical.C19
    def test_second_admission_does_not_re_run_backend(self):
        Backend = _CountingBackend()
        Svc = LanguageEnrichmentService(Backend=Backend)
        with patch(
            'Features.AudioNormalization.Services.LanguageEnrichmentService.DatabaseService'
        ) as MockDb:
            Instance = MagicMock()
            MockDb.return_value = Instance
            Instance.ExecuteQuery.return_value = [
                {'audiostreamlanguagedetectionsjson': {'0': {'Language': 'fra'}}}
            ]
            Svc.Enrich(MediaFileId=42, LocalFilePath='/tmp/foo.mp4', StreamIndices=(0,))
            self.assertEqual(Backend.Calls, [])

    # directive: perfect-audio-vertical | # see perfect-audio-vertical.C19
    def test_has_cache_for_all_streams_true(self):
        Svc = LanguageEnrichmentService()
        with patch.object(Svc, 'GetCached', return_value={'0': {}, '1': {}}):
            self.assertTrue(Svc.HasCacheForAllStreams(42, (0, 1)))

    # directive: perfect-audio-vertical | # see perfect-audio-vertical.C19
    def test_has_cache_for_all_streams_false(self):
        Svc = LanguageEnrichmentService()
        with patch.object(Svc, 'GetCached', return_value={'0': {}}):
            self.assertFalse(Svc.HasCacheForAllStreams(42, (0, 1)))

    # directive: perfect-audio-vertical | # see perfect-audio-vertical.C19
    def test_default_backend_returns_und(self):
        Svc = LanguageEnrichmentService()
        Result = Svc.Backend.Detect('/tmp/x.mp4', 0)
        self.assertEqual(Result['Language'], 'und')


if __name__ == '__main__':
    unittest.main()
