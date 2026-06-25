import os
import sys
import unittest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))

from Features.AudioNormalization.AudioFilterEmitter import AudioFilterEmitter


# directive: audio-pipeline-fail-loud
def _Stream(Index, Lang, IsDefault=False):
    return {
        'index': Index,
        'tags': {'language': Lang},
        'disposition': {'default': 1 if IsDefault else 0},
    }


# directive: audio-pipeline-fail-loud
class TestAudioDefaultLanguageEnglishPreferred(unittest.TestCase):

    def setUp(self):
        self.Emitter = AudioFilterEmitter()

    def test_eng_fra_yields_eng(self):
        Streams = [_Stream(0, 'eng'), _Stream(1, 'fra')]
        Map = {0: 'eng', 1: 'fra'}
        self.assertEqual(self.Emitter._PickDefaultLanguage(Streams, Map, None), 'eng')

    def test_fra_eng_yields_eng_via_rank(self):
        Streams = [_Stream(0, 'fra'), _Stream(1, 'eng')]
        Map = {0: 'fra', 1: 'eng'}
        self.assertEqual(self.Emitter._PickDefaultLanguage(Streams, Map, None), 'eng')

    def test_fra_deu_yields_fra_no_rank_match(self):
        Streams = [_Stream(0, 'fra'), _Stream(1, 'deu')]
        Map = {0: 'fra', 1: 'deu'}
        self.assertEqual(self.Emitter._PickDefaultLanguage(Streams, Map, None), 'fra')

    def test_eng_jpn_with_jpn_default_disposition_still_yields_eng(self):
        Streams = [_Stream(0, 'eng', IsDefault=False), _Stream(1, 'jpn', IsDefault=True)]
        Map = {0: 'eng', 1: 'jpn'}
        self.assertEqual(self.Emitter._PickDefaultLanguage(Streams, Map, None), 'eng')

    def test_library_default_fra_with_eng_present_yields_fra(self):
        Streams = [_Stream(0, 'eng'), _Stream(1, 'fra')]
        Map = {0: 'eng', 1: 'fra'}
        self.assertEqual(self.Emitter._PickDefaultLanguage(Streams, Map, 'fra'), 'fra')

    def test_single_eng_yields_eng(self):
        Streams = [_Stream(0, 'eng')]
        Map = {0: 'eng'}
        self.assertEqual(self.Emitter._PickDefaultLanguage(Streams, Map, None), 'eng')

    def test_untagged_only_yields_none(self):
        Streams = [_Stream(0, 'und')]
        Map = {0: 'und'}
        self.assertIsNone(self.Emitter._PickDefaultLanguage(Streams, Map, None))

    def test_no_rank_with_source_disposition_default_returns_disposition_lang(self):
        Streams = [_Stream(0, 'fra'), _Stream(1, 'deu', IsDefault=True)]
        Map = {0: 'fra', 1: 'deu'}
        self.assertEqual(self.Emitter._PickDefaultLanguage(Streams, Map, None), 'deu')


if __name__ == '__main__':
    unittest.main()
