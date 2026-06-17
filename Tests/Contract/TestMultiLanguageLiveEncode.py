import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from Features.AudioNormalization.AudioFilterEmitter import AudioFilterEmitter


# directive: audio-vertical-perfection-and-self-healing | # see audio-normalization.L1
def _Mf():
    """Gainable MediaFile dict with default loudness measurements."""
    return {
        'Id': 1,
        'SourceIntegratedLufs': -30.0,
        'SourceLoudnessRangeLU': 9.0,
        'SourceTruePeakDbtp': -10.0,
        'SourceIntegratedThresholdLufs': -40.0,
        'AudioCodec': 'aac',
        'AudioCorruptSuspect': False,
    }


# directive: audio-vertical-perfection-and-self-healing | # see audio-normalization.L1
def _DualTrackPolicy():
    """Global default policy: Original + Dialog Boost, keep-all languages."""
    return {
        'Enabled': True,
        'TargetIntegratedLufs': -23.0,
        'TargetTruePeakDbtp': -2.0,
        'LoudnessTolerance': 4.0,
        'UngainablePolicy': 'adaptive',
        'KeepCommentaryTracks': True,
        'EnableSpeechLanguageDetection': False,
        'EmitTracks': [
            {'Label': 'Original', 'TargetLufs': -23.0, 'TargetLra': None,
             'Channels': 'source', 'Codec': 'eac3', 'Bitrate': 384,
             'SampleRateHz': 48000, 'BitDepth': 16,
             'LanguageFilter': 'keep-all', 'IsDefaultTrack': False},
            {'Label': 'Dialog Boost', 'TargetLufs': -23.0, 'TargetLra': 11.0,
             'Channels': 'source', 'Codec': 'eac3', 'Bitrate': 384,
             'SampleRateHz': 48000, 'BitDepth': 16,
             'LanguageFilter': 'keep-all', 'IsDefaultTrack': True},
        ],
    }


# directive: audio-vertical-perfection-and-self-healing | # see audio-normalization.L1
def _Stream(Index, Language, Default=False):
    """ffprobe-shaped audio stream with given index, language tag, and default disposition."""
    return {
        'index': Index,
        'tags': {'language': Language},
        'disposition': {'default': 1 if Default else 0},
    }


# directive: audio-vertical-perfection-and-self-healing | # see audio-normalization.L1
class TestMultiLanguageLiveEncode(unittest.TestCase):
    """L1: emitter produces the 4-stream shape required by the operator's multi-language criterion."""

    # directive: audio-vertical-perfection-and-self-healing | # see audio-normalization.L1
    def test_two_source_languages_produce_four_output_streams(self):
        Streams = [_Stream(0, 'eng', Default=True), _Stream(1, 'jpn')]
        Blocks = AudioFilterEmitter().EmitTracks(_Mf(), _DualTrackPolicy(), AudioStreams=Streams)
        self.assertEqual(len(Blocks), 4)

    # directive: audio-vertical-perfection-and-self-healing | # see audio-normalization.L1
    def test_each_language_gets_original_and_dialog_boost(self):
        Streams = [_Stream(0, 'eng'), _Stream(1, 'jpn')]
        Blocks = AudioFilterEmitter().EmitTracks(_Mf(), _DualTrackPolicy(), AudioStreams=Streams)
        LabelLang = sorted((B.Label, B.Language) for B in Blocks)
        self.assertEqual(
            LabelLang,
            [('Dialog Boost', 'eng'), ('Dialog Boost', 'jpn'),
             ('Original', 'eng'), ('Original', 'jpn')],
        )

    # directive: audio-vertical-perfection-and-self-healing | # see audio-normalization.L1
    def test_dialog_boost_default_flag_per_language(self):
        Streams = [_Stream(0, 'eng'), _Stream(1, 'jpn')]
        Blocks = AudioFilterEmitter().EmitTracks(_Mf(), _DualTrackPolicy(), AudioStreams=Streams)
        DefaultBoosts = [B for B in Blocks if B.Label == 'Dialog Boost'
                         and 'default' in ' '.join(B.DispositionArgs)]
        self.assertEqual(len(DefaultBoosts), 2)

    # directive: audio-vertical-perfection-and-self-healing | # see audio-normalization.L1
    def test_language_metadata_per_output_stream(self):
        Streams = [_Stream(0, 'eng'), _Stream(1, 'jpn')]
        Blocks = AudioFilterEmitter().EmitTracks(_Mf(), _DualTrackPolicy(), AudioStreams=Streams)
        for Block in Blocks:
            Md = ' '.join(Block.MetadataArgs)
            self.assertIn(f'language={Block.Language}', Md)

    # directive: audio-vertical-perfection-and-self-healing | # see audio-normalization.L1
    def test_three_source_languages_produce_six_output_streams(self):
        Streams = [_Stream(0, 'eng'), _Stream(1, 'jpn'), _Stream(2, 'spa')]
        Blocks = AudioFilterEmitter().EmitTracks(_Mf(), _DualTrackPolicy(), AudioStreams=Streams)
        self.assertEqual(len(Blocks), 6)
        Langs = sorted({B.Language for B in Blocks})
        self.assertEqual(Langs, ['eng', 'jpn', 'spa'])

    # directive: audio-vertical-perfection-and-self-healing | # see audio-normalization.L1
    def test_per_stream_output_indices_are_sequential(self):
        Streams = [_Stream(0, 'eng'), _Stream(1, 'jpn')]
        Blocks = AudioFilterEmitter().EmitTracks(_Mf(), _DualTrackPolicy(), AudioStreams=Streams)
        Codecs = ' '.join(' '.join(B.CodecArgs) for B in Blocks)
        for I in range(len(Blocks)):
            self.assertIn(f'-c:a:{I}', Codecs)


if __name__ == '__main__':
    unittest.main()
