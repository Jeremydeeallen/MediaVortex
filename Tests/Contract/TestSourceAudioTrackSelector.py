# directive: dialog-boost-emission-integrity | # see .claude/directive.md C2
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from Features.AudioNormalization.SourceAudioTrackSelector import (
    IsMediaVortexBoostTrack,
    SelectTrueSourceStreams,
    PriorBoostSourceError,
)


class TestSourceAudioTrackSelector(unittest.TestCase):

    def test_identifies_boost_track_via_handler_name(self):
        Stream = {'index': 0, 'tags': {'handler_name': 'Dialog Boost (eng)', 'language': 'eng'}}
        self.assertTrue(IsMediaVortexBoostTrack(Stream))

    def test_identifies_boost_track_via_title(self):
        Stream = {'index': 0, 'tags': {'title': 'Dialog Boost', 'language': 'eng'}}
        self.assertTrue(IsMediaVortexBoostTrack(Stream))

    def test_rejects_non_boost_stream(self):
        Stream = {'index': 0, 'tags': {'title': 'Original', 'handler_name': 'Original (eng)', 'language': 'eng'}}
        self.assertFalse(IsMediaVortexBoostTrack(Stream))

    def test_rejects_untagged_stream(self):
        Stream = {'index': 0, 'tags': {}}
        self.assertFalse(IsMediaVortexBoostTrack(Stream))

    def test_filters_prior_boost_and_keeps_originals(self):
        Streams = [
            {'index': 0, 'tags': {'handler_name': 'Dialog Boost (eng)', 'language': 'eng'}},
            {'index': 1, 'tags': {'handler_name': 'Original (eng)', 'language': 'eng'}},
            {'index': 2, 'tags': {'language': 'jpn'}},
        ]
        Filtered = SelectTrueSourceStreams(Streams)
        self.assertEqual([S['index'] for S in Filtered], [1, 2])

    def test_returns_untouched_when_no_boost_tracks(self):
        Streams = [
            {'index': 0, 'tags': {'language': 'eng'}},
            {'index': 1, 'tags': {'language': 'jpn'}},
        ]
        Filtered = SelectTrueSourceStreams(Streams)
        self.assertEqual([S['index'] for S in Filtered], [0, 1])

    def test_raises_when_all_streams_are_prior_boost(self):
        Streams = [
            {'index': 0, 'tags': {'handler_name': 'Dialog Boost (eng)'}},
            {'index': 1, 'tags': {'title': 'Dialog Boost'}},
        ]
        with self.assertRaises(PriorBoostSourceError):
            SelectTrueSourceStreams(Streams)

    def test_empty_input_returns_empty(self):
        self.assertEqual(SelectTrueSourceStreams([]), [])
        self.assertEqual(SelectTrueSourceStreams(None), [])


if __name__ == '__main__':
    unittest.main()
