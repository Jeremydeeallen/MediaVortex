import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from Features.AudioNormalization.AudioFilterEmitter import AudioFilterEmitter
from Features.AudioNormalization.AudioStrategyClassifier import (
    TrackStrategy,
    STRATEGY_LINEAR,
    STRATEGY_SKIP,
)


# directive: audio-vertical-perfection-and-self-healing | # see audio-normalization.S1
def _ReencodeStrategy(TargetLufs=-23.0, TargetTp=-2.0, Lra=None):
    """Build a TrackStrategy in the LINEAR reencode shape."""
    return TrackStrategy(
        Strategy=STRATEGY_LINEAR,
        EffectiveTargetLufs=TargetLufs,
        EffectiveTruePeakDbtp=TargetTp,
        EffectiveLra=Lra,
    )


# directive: audio-vertical-perfection-and-self-healing | # see audio-normalization.S1
def _SkipStrategy():
    """Build a SKIP-strategy TrackStrategy."""
    return TrackStrategy(
        Strategy=STRATEGY_SKIP,
        EffectiveTargetLufs=None,
        EffectiveTruePeakDbtp=None,
        EffectiveLra=None,
        Reason='ungainable_skip',
    )


# directive: audio-vertical-perfection-and-self-healing | # see audio-normalization.S1
class TestDecideStreamCopyOrReencode(unittest.TestCase):
    """S1: per-track stream-copy vs reencode decision is the first helper of the orchestrator."""

    # directive: audio-vertical-perfection-and-self-healing | # see audio-normalization.S1
    def test_returns_reencode_for_linear_strategy_with_no_suspect_or_complete(self):
        Mf = {'AudioCorruptSuspect': False, 'AudioCodec': 'aac'}
        Track = {}
        Strategy = _ReencodeStrategy()
        self.assertEqual(
            AudioFilterEmitter()._DecideStreamCopyOrReencode(Mf, Track, Strategy),
            'reencode',
        )

    # directive: audio-vertical-perfection-and-self-healing | # see audio-normalization.S1
    def test_returns_stream_copy_fallback_for_skip_strategy_non_mp4_codec(self):
        Mf = {'AudioCorruptSuspect': False, 'AudioCodec': 'dts'}
        Track = {}
        self.assertEqual(
            AudioFilterEmitter()._DecideStreamCopyOrReencode(Mf, Track, _SkipStrategy()),
            'stream_copy_fallback',
        )

    # directive: audio-vertical-perfection-and-self-healing | # see audio-normalization.S1
    def test_returns_stream_copy_for_skip_strategy_mp4_compat_codec(self):
        Mf = {'AudioCorruptSuspect': False, 'AudioCodec': 'eac3'}
        Track = {}
        self.assertEqual(
            AudioFilterEmitter()._DecideStreamCopyOrReencode(Mf, Track, _SkipStrategy()),
            'stream_copy',
        )


# directive: audio-vertical-perfection-and-self-healing | # see audio-normalization.S1
class TestBuildCodecArgs(unittest.TestCase):
    """S1: codec/bitrate/sample-rate/channel argv builder."""

    # directive: audio-vertical-perfection-and-self-healing | # see audio-normalization.S1
    def test_stream_copy_emits_copy_only(self):
        Args = AudioFilterEmitter()._BuildCodecArgs({}, 'stream_copy', 'eac3', 3)
        self.assertEqual(Args, ['-c:a:3', 'copy'])

    # directive: audio-vertical-perfection-and-self-healing | # see audio-normalization.S1
    def test_reencode_with_all_fields(self):
        Track = {'Bitrate': 384, 'SampleRateHz': 48000, 'Channels': 2}
        Args = AudioFilterEmitter()._BuildCodecArgs(Track, 'reencode', 'eac3', 0)
        self.assertEqual(Args, ['-c:a:0', 'eac3', '-b:a:0', '384k', '-ar:0', '48000', '-ac:0', '2'])

    # directive: audio-vertical-perfection-and-self-healing | # see audio-normalization.S1
    def test_reencode_skips_channels_when_source(self):
        Track = {'Bitrate': 192, 'SampleRateHz': 48000, 'Channels': 'source'}
        Args = AudioFilterEmitter()._BuildCodecArgs(Track, 'reencode', 'aac', 1)
        self.assertNotIn('-ac:1', Args)


# directive: audio-vertical-perfection-and-self-healing | # see audio-normalization.S1
class TestBuildMetadataArgs(unittest.TestCase):
    """S1: language + title metadata always quoted to survive shape join."""

    # directive: audio-vertical-perfection-and-self-healing | # see audio-normalization.S1
    def test_quotes_language_and_title(self):
        Args = AudioFilterEmitter()._BuildMetadataArgs('eng', 'Dialog Boost', 2)
        Joined = ' '.join(Args)
        self.assertIn('"language=eng"', Joined)
        self.assertIn('"title=Dialog Boost"', Joined)


# directive: audio-vertical-perfection-and-self-healing | # see audio-normalization.S1
class TestBuildDialNormArgs(unittest.TestCase):
    """S1: dialnorm is a codec option only for ac3/eac3 reencode; emits signed dB."""

    # directive: audio-vertical-perfection-and-self-healing | # see audio-normalization.S1
    def test_empty_on_stream_copy(self):
        Stream = {'tags': {'DialNorm': '24'}}
        Args = AudioFilterEmitter()._BuildDialNormArgs(
            _ReencodeStrategy(), Stream, 'stream_copy', True, 'Original', 0,
        )
        self.assertEqual(Args, [])

    # directive: audio-vertical-perfection-and-self-healing | # see audio-normalization.S1
    def test_empty_on_non_ac3_codec(self):
        Stream = {'tags': {'DialNorm': '24'}}
        Args = AudioFilterEmitter()._BuildDialNormArgs(
            _ReencodeStrategy(), Stream, 'reencode', False, 'Original', 0,
        )
        self.assertEqual(Args, [])

    # directive: audio-vertical-perfection-and-self-healing | # see audio-normalization.S1
    def test_signed_negative_on_eac3_reencode(self):
        Stream = {}
        Args = AudioFilterEmitter()._BuildDialNormArgs(
            _ReencodeStrategy(TargetLufs=-23.0), Stream, 'reencode', True, 'Original', 0,
        )
        self.assertEqual(Args[0], '-dialnorm:0')
        self.assertTrue(int(Args[1]) < 0)


# directive: audio-vertical-perfection-and-self-healing | # see audio-normalization.S1
class TestBuildDispositionArgs(unittest.TestCase):
    """S1: 'default' on the default track; '0' on every other."""

    # directive: audio-vertical-perfection-and-self-healing | # see audio-normalization.S1
    def test_default_track(self):
        Args = AudioFilterEmitter()._BuildDispositionArgs({'IsDefaultTrack': True}, 1)
        self.assertEqual(Args, ['-disposition:a:1', 'default'])

    # directive: audio-vertical-perfection-and-self-healing | # see audio-normalization.S1
    def test_non_default_track(self):
        Args = AudioFilterEmitter()._BuildDispositionArgs({'IsDefaultTrack': False}, 0)
        self.assertEqual(Args, ['-disposition:a:0', '0'])

    # directive: audio-vertical-perfection-and-self-healing | # see audio-normalization.S1
    def test_missing_default_flag_treated_as_non_default(self):
        Args = AudioFilterEmitter()._BuildDispositionArgs({}, 2)
        self.assertEqual(Args, ['-disposition:a:2', '0'])


if __name__ == '__main__':
    unittest.main()
