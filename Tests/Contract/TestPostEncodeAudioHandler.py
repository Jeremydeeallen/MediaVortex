import sys
import unittest
from pathlib import Path
from unittest.mock import patch, MagicMock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from Features.AudioNormalization.Workers.PostEncodeAudioHandler import PostEncodeAudioHandler


# directive: audio-vertical-perfection-and-self-healing | # see audio-normalization.S4
class _StubMeasurementService:
    """Captures Probe calls so the handler's invocation can be asserted in isolation."""

    # directive: audio-vertical-perfection-and-self-healing | # see audio-normalization.S4
    def __init__(self, Result=True):
        self.Result = Result
        self.Calls = []

    # directive: audio-vertical-perfection-and-self-healing | # see audio-normalization.S4
    def Probe(self, AttemptId, Path):
        self.Calls.append((AttemptId, Path))
        return self.Result


# directive: audio-vertical-perfection-and-self-healing | # see audio-normalization.S4
class TestPostEncodeAudioHandler(unittest.TestCase):
    """S4: handler resolves canonical path + invokes Probe; never propagates exceptions to the encode flow."""

    # directive: audio-vertical-perfection-and-self-healing | # see audio-normalization.S4
    def test_resolve_path_builds_windows_canonical(self):
        Handler = PostEncodeAudioHandler()
        with patch(
            'Features.AudioNormalization.Workers.PostEncodeAudioHandler.DatabaseService'
        ) as MockDb:
            Instance = MagicMock()
            MockDb.return_value = Instance
            Instance.ExecuteQuery.return_value = [{
                'canonicalprefix': 'T:',
                'relativepath': 'Show/Season 1/episode.mp4',
            }]
            Path = Handler.ResolvePostReplacementCanonicalPath(42)
            self.assertEqual(Path, 'T:\\Show/Season 1/episode.mp4')

    # directive: audio-vertical-perfection-and-self-healing | # see audio-normalization.S4
    def test_resolve_path_returns_none_for_missing_row(self):
        Handler = PostEncodeAudioHandler()
        with patch(
            'Features.AudioNormalization.Workers.PostEncodeAudioHandler.DatabaseService'
        ) as MockDb:
            Instance = MagicMock()
            MockDb.return_value = Instance
            Instance.ExecuteQuery.return_value = []
            self.assertIsNone(Handler.ResolvePostReplacementCanonicalPath(99999999))

    # directive: audio-vertical-perfection-and-self-healing | # see audio-normalization.S4
    def test_handle_post_encode_calls_probe_with_resolved_path(self):
        Svc = _StubMeasurementService(Result=True)
        Handler = PostEncodeAudioHandler(
            FFmpegPath='/usr/bin/ffmpeg',
            FFprobePath='/usr/bin/ffprobe',
            MeasurementService=Svc,
        )
        with patch.object(Handler, 'ResolvePostReplacementCanonicalPath',
                          return_value='T:\\Show\\episode.mp4'):
            Ok = Handler.HandlePostEncode(42, 690000)
        self.assertTrue(Ok)
        self.assertEqual(Svc.Calls, [(42, 'T:\\Show\\episode.mp4')])

    # directive: audio-vertical-perfection-and-self-healing | # see audio-normalization.S4
    def test_handle_post_encode_returns_false_when_path_unresolved(self):
        Svc = _StubMeasurementService()
        Handler = PostEncodeAudioHandler(MeasurementService=Svc)
        with patch.object(Handler, 'ResolvePostReplacementCanonicalPath', return_value=None):
            Ok = Handler.HandlePostEncode(42, 690000)
        self.assertFalse(Ok)
        self.assertEqual(Svc.Calls, [])

    # directive: audio-vertical-perfection-and-self-healing | # see audio-normalization.S4
    def test_handle_post_encode_swallows_inner_exception(self):
        Handler = PostEncodeAudioHandler()
        BoomSvc = MagicMock()
        BoomSvc.Probe.side_effect = RuntimeError('boom')
        with patch.object(Handler, 'ResolvePostReplacementCanonicalPath',
                          return_value='T:\\x.mp4'), \
             patch.object(Handler, '_ResolveMeasurementService', return_value=BoomSvc):
            Ok = Handler.HandlePostEncode(42, 690000)
        self.assertFalse(Ok)


if __name__ == '__main__':
    unittest.main()
