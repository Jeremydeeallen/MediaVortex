# directive: bug-0087-audio-per-stream-channels | # see audio-normalization.C31
import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from Features.AudioNormalization.AudioFilterEmitter import AudioFilterEmitter


def _Rules():
    return {
        'Track0BitratePerChannelKbps': 48, 'Track0MinPerChannelKbps': 32,
        'Track1StereoBitrateKbps': 64, 'Track1VocalsRmsFallbackDbfs': -50,
        'TargetIntegratedLufs': -23.0, 'TargetTruePeakDbtp': -2.0,
        'SampleLimitHeadroomDb': 3.0,
        'DialogBoostTargetLufs': -20.0, 'DialogBoostTargetLra': 5.0,
        'VocalsBoostDb': 4.0, 'InstrumentalAttenDb': 3.0,
        'PremixCompressorThreshold': -20.0, 'PremixCompressorRatio': 2.5,
        'PremixCompressorMakeupDb': 3.0,
        'PremixDynaudnormFrameLen': 500, 'PremixDynaudnormGaussSize': 3,
        'Track0Codec': 'opus', 'Track1Codec': 'opus',
    }


def _RulesRepo():
    R = MagicMock()
    R.GetRules = lambda: _Rules()
    return R


def _MediaFile():
    M = MagicMock()
    M.AudioChannels = 2
    M.Id = 692101
    M.AudioStreamLanguageDetectionsJson = None
    M.SourceIntegratedLufs = -20.0
    M.SourceLoudnessRangeLU = 10.0
    M.SourceTruePeakDbtp = -1.5
    M.SourceIntegratedThresholdLufs = -30.0
    return M


def _Policy():
    P = MagicMock()
    P.LanguageDefault = 'eng'
    P.EnableSpeechLanguageDetection = False
    return P


# Mixed-layout source: eng 5.1(side) + fre 2.0 (the failing pattern from 2026-08-07 12:00 UTC).
_MixedStreams = [
    {'index': 0, 'channels': 6, 'channel_layout': '5.1(side)', 'tags': {'language': 'eng'}, 'disposition': {'default': 1}},
    {'index': 1, 'channels': 2, 'channel_layout': 'stereo', 'tags': {'language': 'fre'}, 'disposition': {'default': 0}},
]


class TestOpusMultichannelPerStream(unittest.TestCase):
    """C3: libopus multichannel guard fires per-stream, not per-file."""

    def _Emitter(self):
        return AudioFilterEmitter(RulesRepo=_RulesRepo())

    def _EmittedArgv(self, Blocks):
        Argv = []
        for B in Blocks:
            Argv.extend(getattr(B, 'CodecArgs', []))
            Argv.extend(getattr(B, 'FilterArgs', []))
        return Argv

    def test_5_1_stream_gets_mapping_family_1_and_aformat(self):
        Blocks = self._Emitter().EmitTracks(_MediaFile(), _Policy(), AudioStreams=_MixedStreams, Rules=_Rules())
        Original5_1 = next(B for B in Blocks if 'fre' not in ' '.join(B.MetadataArgs) and B.Label == 'Original')
        Codec5_1 = ' '.join(Original5_1.CodecArgs)
        Filter5_1 = ' '.join(Original5_1.FilterArgs)
        self.assertIn('-mapping_family:a', Codec5_1)
        self.assertIn('aformat=channel_layouts=5.1|7.1', Filter5_1)

    def test_stereo_stream_omits_mapping_family_and_aformat(self):
        Blocks = self._Emitter().EmitTracks(_MediaFile(), _Policy(), AudioStreams=_MixedStreams, Rules=_Rules())
        OriginalStereo = next(B for B in Blocks if 'fre' in ' '.join(B.MetadataArgs) and B.Label == 'Original')
        CodecStereo = ' '.join(OriginalStereo.CodecArgs)
        FilterStereo = ' '.join(OriginalStereo.FilterArgs)
        self.assertNotIn('-mapping_family:a', CodecStereo)
        self.assertNotIn('aformat=channel_layouts', FilterStereo)

    def test_bitrate_reflects_per_stream_channels(self):
        Blocks = self._Emitter().EmitTracks(_MediaFile(), _Policy(), AudioStreams=_MixedStreams, Rules=_Rules())
        Original5_1 = next(B for B in Blocks if 'fre' not in ' '.join(B.MetadataArgs) and B.Label == 'Original')
        OriginalStereo = next(B for B in Blocks if 'fre' in ' '.join(B.MetadataArgs) and B.Label == 'Original')
        # 48 kbps/ch * 6ch = 288k on the 5.1 stream; 48 * 2 = 96k on the stereo.
        self.assertIn('288k', ' '.join(Original5_1.CodecArgs))
        self.assertIn('96k', ' '.join(OriginalStereo.CodecArgs))


if __name__ == '__main__':
    unittest.main()
