import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from Models.MediaFileModel import MediaFileModel
from Features.Compliance.Models.EffectiveProfile import EffectiveProfile
from Features.Compliance.Models.TranscodeRulesModel import TranscodeRulesModel
from Features.Compliance.Operations.TranscodeOperation import TranscodeOperation
from Features.Compliance.Services.EffectiveProfileResolver import EffectiveProfileResolver


def _mf(*, TranscodedByMediaVortex, Codec='av1', Res='480p', SizeMB=215.0, DurationMinutes=42.7, VideoBitrateKbps=607):
    return MediaFileModel(
        Id=1, FileName='x.mkv', SizeMB=SizeMB, DurationMinutes=DurationMinutes,
        Resolution=None, ResolutionCategory=Res, Codec=Codec, VideoBitrateKbps=VideoBitrateKbps,
        AudioCodec='aac', AudioChannels=2, AudioBitrateKbps=128,
        AudioComplete=True, AudioCorruptSuspect=False,
        ContainerFormat='mp4', SubtitleFormats=None,
        AssignedProfile='NVENC AV1 P7 CANARY VBR -720p',
        HasExplicitEnglishAudio=True, HasForcedSubtitles=False,
        SourceIntegratedLufs=-23.0,
        TranscodedByMediaVortex=TranscodedByMediaVortex,
    )


def _profile(TargetVideoKbps=182, TargetRes='480p'):
    return EffectiveProfile(ProfileName='NVENC AV1 P7 CANARY VBR -720p', TargetVideoKbps=TargetVideoKbps, TargetAudioKbps=0, TargetResolutionCategory=TargetRes)


def _rules():
    # Match production: PreventUpscale=True, ResolutionExceedsProfileTarget=True, codecs csv, savings=150
    return TranscodeRulesModel(
        PreventUpscale=True,
        ResolutionExceedsProfileTarget=True,
        AcceptableVideoCodecsCsv='h264,hevc,av1',
        EstimatedSavingsMBThreshold=150,
    )


# directive: mv-trust-savings-and-clamp | # see mv-trust-savings-and-clamp.C1
class TestSavingsRuleHonorsMvTrust(unittest.TestCase):
    """AC1: EstimatedSavingsMBThreshold does not fire when Mf.TranscodedByMediaVortex=True."""

    # directive: mv-trust-savings-and-clamp | # see mv-trust-savings-and-clamp.C1
    def test_savings_fires_when_not_mv_transcoded(self):
        Op = TranscodeOperation()
        # Fresh source (TxByMV=False or None), savings = 215 - 57 = 158 >= 150 -> fires
        Result = Op.Apply(_mf(TranscodedByMediaVortex=False), _profile(), _rules())
        self.assertTrue(Result.Applies)
        Reasons = [R for R in Result.Reasons if R.get('Rule') == 'EstimatedSavingsMBThreshold']
        self.assertEqual(len(Reasons), 1)
        self.assertEqual(Reasons[0]['Outcome'], 'applies')

    # directive: mv-trust-savings-and-clamp | # see mv-trust-savings-and-clamp.C1
    def test_savings_skipped_when_mv_transcoded(self):
        Op = TranscodeOperation()
        # Same shape, TxByMV=True -> savings should not fire; op should not apply
        Result = Op.Apply(_mf(TranscodedByMediaVortex=True), _profile(), _rules())
        self.assertFalse(Result.Applies)
        Reasons = [R for R in Result.Reasons if R.get('Rule') == 'EstimatedSavingsMBThreshold']
        self.assertEqual(len(Reasons), 1)
        self.assertEqual(Reasons[0]['Outcome'], 'skip')

    # directive: mv-trust-savings-and-clamp | # see mv-trust-savings-and-clamp.C1
    def test_codec_rule_still_fires_on_mv_transcoded(self):
        Op = TranscodeOperation()
        # MV-transcoded but wrong codec (e.g. vp9 not in acceptable list) -> codec rule still fires
        Result = Op.Apply(_mf(TranscodedByMediaVortex=True, Codec='vp9'), _profile(), _rules())
        self.assertTrue(Result.Applies)
        Reasons = [R for R in Result.Reasons if R.get('Rule') == 'AcceptableVideoCodecsCsv']
        self.assertEqual(len(Reasons), 1)
        self.assertEqual(Reasons[0]['Outcome'], 'applies')


# directive: mv-trust-savings-and-clamp | # see mv-trust-savings-and-clamp.C2
class TestVbrClamp(unittest.TestCase):
    """AC2: _ResolveTargetVideoKbps clamps VBR result by MinBitrateKbps / MaxBitrateKbps."""

    # directive: mv-trust-savings-and-clamp | # see mv-trust-savings-and-clamp.C2
    def setUp(self):
        self.DbStub = MagicMock()
        self.Resolver = EffectiveProfileResolver(self.DbStub)

    # directive: mv-trust-savings-and-clamp | # see mv-trust-savings-and-clamp.C2
    def test_vbr_clamps_to_floor(self):
        Row = {'VideoBitrateKbps': 0, 'SourceBitratePercent': 30, 'MinBitrateKbps': 350, 'MaxBitrateKbps': 600, 'Quality': None, 'Codec': 'libsvtav1', 'TargetResolution': '480p'}
        Mf = _mf(TranscodedByMediaVortex=False, VideoBitrateKbps=607)
        self.assertEqual(self.Resolver._ResolveTargetVideoKbps(Row, Mf, '480p'), 350)

    # directive: mv-trust-savings-and-clamp | # see mv-trust-savings-and-clamp.C2
    def test_vbr_clamps_to_ceiling(self):
        Row = {'VideoBitrateKbps': 0, 'SourceBitratePercent': 30, 'MinBitrateKbps': 350, 'MaxBitrateKbps': 600, 'Quality': None, 'Codec': 'libsvtav1', 'TargetResolution': '720p'}
        Mf = _mf(TranscodedByMediaVortex=False, VideoBitrateKbps=2400)
        self.assertEqual(self.Resolver._ResolveTargetVideoKbps(Row, Mf, '720p'), 600)

    # directive: mv-trust-savings-and-clamp | # see mv-trust-savings-and-clamp.C2
    def test_vbr_unclamped_when_no_floor_ceiling(self):
        Row = {'VideoBitrateKbps': 0, 'SourceBitratePercent': 30, 'MinBitrateKbps': None, 'MaxBitrateKbps': None, 'Quality': None, 'Codec': 'libsvtav1', 'TargetResolution': '480p'}
        Mf = _mf(TranscodedByMediaVortex=False, VideoBitrateKbps=607)
        self.assertEqual(self.Resolver._ResolveTargetVideoKbps(Row, Mf, '480p'), 182)

    # directive: mv-trust-savings-and-clamp | # see mv-trust-savings-and-clamp.C2
    def test_vbr_within_band_unchanged(self):
        Row = {'VideoBitrateKbps': 0, 'SourceBitratePercent': 30, 'MinBitrateKbps': 100, 'MaxBitrateKbps': 600, 'Quality': None, 'Codec': 'libsvtav1', 'TargetResolution': '480p'}
        Mf = _mf(TranscodedByMediaVortex=False, VideoBitrateKbps=1200)
        self.assertEqual(self.Resolver._ResolveTargetVideoKbps(Row, Mf, '480p'), 360)


if __name__ == '__main__':
    unittest.main()
