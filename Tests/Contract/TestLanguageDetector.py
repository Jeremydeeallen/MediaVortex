import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from Features.AudioNormalization.LanguageDetector import (
    LanguageDetector,
    LAYER_ISO_TAG,
    LAYER_TITLE_REGEX,
    LAYER_SINGLE_STREAM,
    LAYER_DEFAULT_FLAG,
    LAYER_LIBRARY_DEFAULT,
    LAYER_SPEECH_CACHE,
    KEEP_ALL,
)


# directive: perfect-audio-vertical | # see perfect-audio-vertical.C11
class TestLanguageDetector(unittest.TestCase):
    """C11: layered detection iso_tag -> title_regex -> single_stream -> default_flag -> library_default + C19 speech cache."""

    # directive: perfect-audio-vertical | # see perfect-audio-vertical.C11
    def test_layer_iso_tag(self):
        Streams = [
            {'index': 0, 'tags': {'language': 'eng'}},
            {'index': 1, 'tags': {'language': 'jpn'}},
        ]
        Det = LanguageDetector().Detect(Streams)
        self.assertEqual(Det.StreamLanguages[0].Language, 'eng')
        self.assertEqual(Det.StreamLanguages[0].Layer, LAYER_ISO_TAG)
        self.assertEqual(Det.StreamLanguages[1].Language, 'jpn')

    # directive: perfect-audio-vertical | # see perfect-audio-vertical.C11
    def test_layer_title_regex(self):
        Streams = [
            {'index': 0, 'tags': {'title': 'English 5.1'}},
            {'index': 1, 'tags': {'title': 'Director Commentary'}},
        ]
        Det = LanguageDetector().Detect(Streams)
        self.assertEqual(Det.StreamLanguages[0].Language, 'eng')
        self.assertEqual(Det.StreamLanguages[0].Layer, LAYER_TITLE_REGEX)

    # directive: perfect-audio-vertical | # see perfect-audio-vertical.C11
    def test_layer_single_stream(self):
        Streams = [{'index': 0, 'tags': {}}]
        Det = LanguageDetector().Detect(Streams, LibraryDefault='eng')
        self.assertEqual(Det.StreamLanguages[0].Layer, LAYER_SINGLE_STREAM)
        self.assertEqual(Det.StreamLanguages[0].Language, 'eng')

    # directive: perfect-audio-vertical | # see perfect-audio-vertical.C11
    def test_layer_default_flag(self):
        Streams = [
            {'index': 0, 'tags': {}, 'disposition': {'default': 0}},
            {'index': 1, 'tags': {}, 'disposition': {'default': 1}},
        ]
        Det = LanguageDetector().Detect(Streams, LibraryDefault='eng')
        self.assertEqual(Det.StreamLanguages[1].Layer, LAYER_DEFAULT_FLAG)
        self.assertEqual(Det.StreamLanguages[1].Language, 'eng')

    # directive: perfect-audio-vertical | # see perfect-audio-vertical.C11
    def test_layer_library_default(self):
        Streams = [
            {'index': 0, 'tags': {}, 'disposition': {'default': 0}},
            {'index': 1, 'tags': {}, 'disposition': {'default': 0}},
        ]
        Det = LanguageDetector().Detect(Streams, LibraryDefault='eng')
        self.assertEqual(Det.StreamLanguages[0].Layer, LAYER_LIBRARY_DEFAULT)

    # directive: perfect-audio-vertical | # see perfect-audio-vertical.C11
    def test_none_resolved_returns_keep_all(self):
        Streams = [
            {'index': 0, 'tags': {}, 'disposition': {'default': 0}},
            {'index': 1, 'tags': {}, 'disposition': {'default': 0}},
        ]
        Det = LanguageDetector().Detect(Streams, LibraryDefault=None)
        self.assertEqual(Det.KeepPolicy, KEEP_ALL)

    # directive: perfect-audio-vertical | # see perfect-audio-vertical.C19
    def test_layer_speech_cache_when_enabled(self):
        Streams = [
            {'index': 0, 'tags': {}, 'disposition': {'default': 0}},
        ]
        Cache = {0: {'Language': 'fra'}}
        Det = LanguageDetector().Detect(
            Streams,
            LibraryDefault=None,
            SpeechCache=Cache,
            EnableSpeechLayer=True,
        )
        self.assertEqual(Det.StreamLanguages[0].Language, 'fra')
        self.assertEqual(Det.StreamLanguages[0].Layer, LAYER_SPEECH_CACHE)

    # directive: perfect-audio-vertical | # see perfect-audio-vertical.C19
    def test_speech_cache_ignored_when_disabled(self):
        Streams = [{'index': 0, 'tags': {}, 'disposition': {'default': 0}}]
        Cache = {0: {'Language': 'fra'}}
        Det = LanguageDetector().Detect(
            Streams,
            LibraryDefault=None,
            SpeechCache=Cache,
            EnableSpeechLayer=False,
        )
        self.assertNotEqual(Det.StreamLanguages[0].Language, 'fra')

    # directive: perfect-audio-vertical | # see perfect-audio-vertical.C11
    def test_empty_stream_list(self):
        Det = LanguageDetector().Detect([])
        self.assertEqual(Det.StreamLanguages, [])
        self.assertEqual(Det.KeepPolicy, KEEP_ALL)


if __name__ == '__main__':
    unittest.main()
