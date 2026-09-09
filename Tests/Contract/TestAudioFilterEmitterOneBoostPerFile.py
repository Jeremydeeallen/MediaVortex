# directive: dialog-boost-emission-integrity | # see .claude/directive.md C1
import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from Features.AudioNormalization.AudioFilterEmitter import AudioFilterEmitter


def _Rules():
    return {
        'Track0BitratePerChannelKbps': 48, 'Track0MinPerChannelKbps': 48,
        'Track1StereoBitrateKbps': 64, 'Track1VocalsRmsFallbackDbfs': -50,
        'TargetIntegratedLufs': -23.0, 'TargetTruePeakDbtp': -2.0,
        'SampleLimitHeadroomDb': 3.0,
        'DialogBoostTargetLufs': -20.0, 'DialogBoostTargetLra': 5.0,
        'Track0Codec': 'opus', 'Track1Codec': 'opus',
    }


def _RulesRepo():
    R = MagicMock()
    R.GetRules = lambda: _Rules()
    return R


def _MediaFile():
    M = MagicMock()
    M.Id = 999001
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


_ThreeEngStreams = [
    {'index': 0, 'channels': 6, 'channel_layout': '5.1', 'tags': {'language': 'eng'}, 'disposition': {'default': 1}},
    {'index': 1, 'channels': 2, 'channel_layout': 'stereo', 'tags': {'language': 'eng'}, 'disposition': {'default': 0}},
    {'index': 2, 'channels': 2, 'channel_layout': 'stereo', 'tags': {'language': 'eng'}, 'disposition': {'default': 0}},
]


class TestAudioFilterEmitterOneBoostPerFile(unittest.TestCase):
    """C1: Dialog Boost emit is per-file, not per-stream. N eng streams -> 1 boost + N originals."""

    def _Emitter(self):
        return AudioFilterEmitter(RulesRepo=_RulesRepo())

    def test_three_eng_streams_emit_one_boost_and_three_originals(self):
        Blocks = self._Emitter().EmitTracks(
            _MediaFile(), _Policy(),
            AudioStreams=_ThreeEngStreams,
            DemucsPremixPath='/tmp/premix.wav',
            VocalsRmsDbfs=-20.0,
            PremixMeasuredI=-15.0, PremixMeasuredLra=6.0,
            PremixMeasuredTp=-2.0, PremixMeasuredThresh=-25.0,
            Rules=_Rules(),
        )
        BoostBlocks = [B for B in Blocks if B.Label == 'Dialog Boost']
        OriginalBlocks = [B for B in Blocks if B.Label == 'Original']
        self.assertEqual(len(BoostBlocks), 1, f"expected 1 Dialog Boost block, got {len(BoostBlocks)}: {[B.Label for B in Blocks]}")
        self.assertEqual(len(OriginalBlocks), 3, f"expected 3 Original blocks, got {len(OriginalBlocks)}: {[B.Label for B in Blocks]}")

    def test_boost_appears_first_before_originals(self):
        Blocks = self._Emitter().EmitTracks(
            _MediaFile(), _Policy(),
            AudioStreams=_ThreeEngStreams,
            DemucsPremixPath='/tmp/premix.wav',
            VocalsRmsDbfs=-20.0,
            Rules=_Rules(),
        )
        self.assertEqual(Blocks[0].Label, 'Dialog Boost')
        self.assertTrue(all(B.Label == 'Original' for B in Blocks[1:]))

    def test_boost_input_appears_once(self):
        Blocks = self._Emitter().EmitTracks(
            _MediaFile(), _Policy(),
            AudioStreams=_ThreeEngStreams,
            DemucsPremixPath='/tmp/premix.wav',
            VocalsRmsDbfs=-20.0,
            Rules=_Rules(),
        )
        InputArgs = []
        for B in Blocks:
            InputArgs.extend(B.InputArgs)
        PremixCount = sum(1 for A in InputArgs if A == '/tmp/premix.wav')
        self.assertEqual(PremixCount, 1, f"premix WAV should be added once, found {PremixCount}: {InputArgs}")

    def test_no_boost_when_premix_missing_still_emits_originals(self):
        Blocks = self._Emitter().EmitTracks(
            _MediaFile(), _Policy(),
            AudioStreams=_ThreeEngStreams,
            DemucsPremixPath=None,
            VocalsRmsDbfs=None,
            Rules=_Rules(),
        )
        BoostBlocks = [B for B in Blocks if B.Label == 'Dialog Boost']
        OriginalBlocks = [B for B in Blocks if B.Label == 'Original']
        self.assertEqual(len(BoostBlocks), 0)
        self.assertEqual(len(OriginalBlocks), 3)

    def test_originals_never_default_when_boost_emitted(self):
        Blocks = self._Emitter().EmitTracks(
            _MediaFile(), _Policy(),
            AudioStreams=_ThreeEngStreams,
            DemucsPremixPath='/tmp/premix.wav',
            VocalsRmsDbfs=-20.0,
            Rules=_Rules(),
        )
        OriginalBlocks = [B for B in Blocks if B.Label == 'Original']
        for B in OriginalBlocks:
            Disp = ' '.join(B.DispositionArgs)
            self.assertIn(' 0', Disp, f"Original disposition should be 0 when boost is emitted: {Disp}")


if __name__ == '__main__':
    unittest.main()
