import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from Models.MediaFileModel import MediaFileModel
from Core.Resolution.ResolutionTier import ResolutionTier
from Features.Compliance.Models.EffectiveProfile import EffectiveProfile
from Features.Compliance.Models.ComplianceRuleCache import ComplianceRuleCache
from Features.Compliance.Models.ComplianceGatesModel import ComplianceGatesModel
from Features.Compliance.Models.TranscodeRulesModel import TranscodeRulesModel
from Features.Compliance.Models.RemuxRulesModel import RemuxRulesModel
from Features.Compliance.Models.AudioFixRulesModel import AudioFixRulesModel
from Features.Compliance.Models.SubtitleFixRulesModel import SubtitleFixRulesModel
from Features.Compliance.ComplianceComposition import BuildEvaluator, BuildRuleCache


# directive: resolution-types | # see resolution-types.C5
def _Tier(Name):
    """Test factory -- canonical ResolutionTier instances matching the seeded DB rows (resolution-types.C13). Decoupled from DB so unit tests don't need PostgreSQL."""
    Table = {
        'T480p':  ResolutionTier('T480p',  600,  854,  480,  1),
        'T720p':  ResolutionTier('T720p',  1100, 1280, 720,  2),
        'T1080p': ResolutionTier('T1080p', 1700, 1920, 1080, 3),
        'T2160p': ResolutionTier('T2160p', 3000, 3840, 2160, 4),
    }
    Alias = {'480p': 'T480p', '720p': 'T720p', '1080p': 'T1080p', '2160p': 'T2160p', '4k': 'T2160p'}
    return Table[Alias.get(Name, Name)]


# directive: compliance-solid-refactor | # see compliance-solid-refactor.C26
def MakeCache(Gates=None, Transcode=None, Remux=None, AudioFix=None, SubtitleFix=None):
    """Test factory -- builds a ComplianceRuleCache with the given overrides; defaults to dataclass defaults."""
    return ComplianceRuleCache(
        Gates=Gates or ComplianceGatesModel(),
        TranscodeRules=Transcode or TranscodeRulesModel(),
        RemuxRules=Remux or RemuxRulesModel(),
        AudioFixRules=AudioFix or AudioFixRulesModel(),
        SubtitleFixRules=SubtitleFix or SubtitleFixRulesModel(),
    )


# directive: compliance-solid-refactor | # see compliance-solid-refactor.C26
def CompliantMediaFile(**Over):
    """Test factory -- a baseline compliant MediaFile (480p MP4 h264, audio normalized, all measurements present)."""
    Base = dict(
        SizeMB=250, DurationMinutes=45,
        Resolution='854x480', ResolutionCategory='480p', Codec='h264', VideoBitrateKbps=600,
        AudioCodec='aac', AudioComplete=True, AudioCorruptSuspect=False,
        ContainerFormat='mp4', SubtitleFormats='',
        HasExplicitEnglishAudio=True, HasForcedSubtitles=False,
        SourceIntegratedLufs=-23.0, SourceLoudnessRangeLU=11.0,
        SourceTruePeakDbtp=-2.0, SourceIntegratedThresholdLufs=-30.0,
    )
    Base.update(Over)
    return MediaFileModel(**Base)


# directive: compliance-solid-refactor | # see compliance-solid-refactor.C26
def DefaultProfile():
    return EffectiveProfile(ProfileName='Test480p', TargetVideoKbps=600, TargetAudioKbps=96, TargetResolutionCategory=_Tier('T480p'))


class TestGates(unittest.TestCase):
    """One test per gate -- gate fires (default Enabled) + gate disabled does not fire."""

    def setUp(self):
        self.Ev = BuildEvaluator()
        self.Profile = DefaultProfile()

    def test_english_audio_gate_fires(self):
        D = self.Ev.Evaluate(CompliantMediaFile(HasExplicitEnglishAudio=False), self.Profile, MakeCache())
        self.assertEqual(D.GateBlocked, 'EnglishAudio')
        self.assertIsNone(D.IsCompliant)

    def test_english_audio_gate_disabled_lets_through(self):
        Cache = MakeCache(Gates=ComplianceGatesModel(RequireExplicitEnglishAudio=False))
        D = self.Ev.Evaluate(CompliantMediaFile(HasExplicitEnglishAudio=False), self.Profile, Cache)
        self.assertNotEqual(D.GateBlocked, 'EnglishAudio')

    def test_audio_corrupt_suspect_gate_fires(self):
        D = self.Ev.Evaluate(CompliantMediaFile(AudioCorruptSuspect=True), self.Profile, MakeCache())
        self.assertEqual(D.GateBlocked, 'AudioCorruptSuspect')

    def test_audio_stream_gate_fires(self):
        D = self.Ev.Evaluate(CompliantMediaFile(AudioCodec=''), self.Profile, MakeCache())
        self.assertEqual(D.GateBlocked, 'AudioStream')

    def test_probe_metadata_gate_fires_on_missing_codec(self):
        D = self.Ev.Evaluate(CompliantMediaFile(Codec=''), self.Profile, MakeCache())
        self.assertEqual(D.GateBlocked, 'ProbeMetadata')

    def test_effective_profile_gate_fires_on_none(self):
        D = self.Ev.Evaluate(CompliantMediaFile(), None, MakeCache())
        self.assertEqual(D.GateBlocked, 'EffectiveProfile')

    def test_resolution_category_gate_fires(self):
        D = self.Ev.Evaluate(CompliantMediaFile(ResolutionCategory=''), self.Profile, MakeCache())
        self.assertEqual(D.GateBlocked, 'ResolutionCategory')

    def test_profile_thresholds_gate_fires(self):
        BadProfile = EffectiveProfile(ProfileName='Test480p', TargetVideoKbps=None, TargetAudioKbps=None, TargetResolutionCategory=_Tier('T480p'))
        D = self.Ev.Evaluate(CompliantMediaFile(), BadProfile, MakeCache())
        self.assertEqual(D.GateBlocked, 'ProfileThresholds')

    def test_loudness_measurements_gate_fires_when_audio_not_complete_and_lufs_missing(self):
        D = self.Ev.Evaluate(CompliantMediaFile(AudioComplete=False, SourceIntegratedLufs=None), self.Profile, MakeCache())
        self.assertEqual(D.GateBlocked, 'LoudnessMeasurements')

    def test_loudness_measurements_gate_skipped_when_audio_complete(self):
        D = self.Ev.Evaluate(CompliantMediaFile(AudioComplete=True, SourceIntegratedLufs=None), self.Profile, MakeCache())
        self.assertNotEqual(D.GateBlocked, 'LoudnessMeasurements')


class TestOperations(unittest.TestCase):
    """One test per WorkBucket outcome -- exercises every operation and the BucketResolver precedence."""

    def setUp(self):
        self.Ev = BuildEvaluator()
        self.Profile = DefaultProfile()

    def test_compliant_no_operations(self):
        D = self.Ev.Evaluate(CompliantMediaFile(), self.Profile, MakeCache())
        self.assertTrue(D.IsCompliant)
        self.assertEqual(D.OperationsNeeded, frozenset())
        self.assertIsNone(D.WorkBucket)

    def test_transcode_bucket_on_codec_mismatch(self):
        D = self.Ev.Evaluate(CompliantMediaFile(Codec='vc1'), self.Profile, MakeCache())
        self.assertEqual(D.WorkBucket, 'Transcode')
        self.assertIn('Transcode', D.OperationsNeeded)

    def test_transcode_bucket_on_resolution_exceeds(self):
        Mf = CompliantMediaFile(ResolutionCategory='1080p', Resolution='1920x1080')
        D = self.Ev.Evaluate(Mf, self.Profile, MakeCache())
        self.assertEqual(D.WorkBucket, 'Transcode')

    def test_transcode_blocked_by_upscale_guard(self):
        P = EffectiveProfile(ProfileName='X', TargetVideoKbps=1500, TargetAudioKbps=128, TargetResolutionCategory=_Tier('T720p'))
        Mf = CompliantMediaFile(ResolutionCategory='480p')
        D = self.Ev.Evaluate(Mf, P, MakeCache())
        self.assertNotIn('Transcode', D.OperationsNeeded)

    def test_remux_bucket_on_container_mismatch(self):
        D = self.Ev.Evaluate(CompliantMediaFile(ContainerFormat='matroska,webm'), self.Profile, MakeCache())
        self.assertEqual(D.WorkBucket, 'Remux')

    def test_remux_bucket_when_audio_not_normalized(self):
        D = self.Ev.Evaluate(CompliantMediaFile(AudioComplete=False, SourceIntegratedLufs=-22.5), self.Profile, MakeCache())
        self.assertEqual(D.WorkBucket, 'Remux')

    def test_audiofix_only_bucket_when_only_loudness_off(self):
        D = self.Ev.Evaluate(CompliantMediaFile(AudioComplete=False, SourceIntegratedLufs=-15.0), self.Profile,
                             MakeCache(Remux=RemuxRulesModel(RequireAudioNormalized=False)))
        self.assertEqual(D.WorkBucket, 'AudioFixOnly')
        self.assertEqual(D.OperationsNeeded, frozenset({'AudioFix'}))

    def test_transcode_subsumes_remux_and_audiofix(self):
        D = self.Ev.Evaluate(CompliantMediaFile(ContainerFormat='matroska', AudioComplete=False, SourceIntegratedLufs=-15.0, Codec='vc1'), self.Profile, MakeCache())
        self.assertEqual(D.WorkBucket, 'Transcode')
        self.assertIn('Transcode', D.OperationsNeeded)
        self.assertIn('Remux', D.OperationsNeeded)
        self.assertIn('AudioFix', D.OperationsNeeded)


class TestSubtitleFix(unittest.TestCase):
    """C26 SubtitleFix-specific cases -- forced-subs default policy + Enabled flag + RequireForcedSubtitlesPresent toggle."""

    def setUp(self):
        self.Ev = BuildEvaluator()
        self.Profile = DefaultProfile()

    def test_subtitlefix_disabled_default_never_proposes(self):
        Mf = CompliantMediaFile(SubtitleFormats='ass', HasForcedSubtitles=True)
        D = self.Ev.Evaluate(Mf, self.Profile, MakeCache())
        self.assertNotIn('SubtitleFix', D.OperationsNeeded)

    def test_subtitlefix_enabled_forced_present_in_mp4_with_ass_proposes(self):
        Mf = CompliantMediaFile(SubtitleFormats='ass', HasForcedSubtitles=True, AudioComplete=True)
        Cache = MakeCache(SubtitleFix=SubtitleFixRulesModel(Enabled=True))
        D = self.Ev.Evaluate(Mf, self.Profile, Cache)
        self.assertIn('SubtitleFix', D.OperationsNeeded)
        self.assertEqual(D.WorkBucket, 'SubtitleFixOnly')

    def test_subtitlefix_enabled_non_forced_with_require_forced_does_not_propose(self):
        Mf = CompliantMediaFile(SubtitleFormats='ass', HasForcedSubtitles=False, AudioComplete=True)
        Cache = MakeCache(SubtitleFix=SubtitleFixRulesModel(Enabled=True))
        D = self.Ev.Evaluate(Mf, self.Profile, Cache)
        self.assertNotIn('SubtitleFix', D.OperationsNeeded)

    def test_subtitlefix_enabled_non_forced_with_require_forced_off_proposes(self):
        Mf = CompliantMediaFile(SubtitleFormats='ass', HasForcedSubtitles=False, AudioComplete=True)
        Cache = MakeCache(SubtitleFix=SubtitleFixRulesModel(Enabled=True, RequireForcedSubtitlesPresent=False))
        D = self.Ev.Evaluate(Mf, self.Profile, Cache)
        self.assertIn('SubtitleFix', D.OperationsNeeded)

    def test_subtitlefix_null_forced_with_require_forced_does_not_propose(self):
        Mf = CompliantMediaFile(SubtitleFormats='ass', HasForcedSubtitles=None, AudioComplete=True)
        Cache = MakeCache(SubtitleFix=SubtitleFixRulesModel(Enabled=True))
        D = self.Ev.Evaluate(Mf, self.Profile, Cache)
        self.assertNotIn('SubtitleFix', D.OperationsNeeded)


class TestMidFlightConfigChange(unittest.TestCase):
    """C12 -- non-bulk Evaluate must observe rule UPDATEs on the next call (no caching)."""

    def test_repository_get_reads_fresh(self):
        from Features.Compliance.Repositories.TranscodeRulesRepository import TranscodeRulesRepository
        Repo = TranscodeRulesRepository()
        Before = Repo.Get()
        # Flip a value, read again, restore -- mid-flight UPDATE must reflect in next Get
        Repo.Update(EstimatedSavingsMBThreshold=999)
        try:
            Mid = Repo.Get()
            self.assertEqual(Mid.EstimatedSavingsMBThreshold, 999)
        finally:
            Repo.Update(EstimatedSavingsMBThreshold=Before.EstimatedSavingsMBThreshold)
        After = Repo.Get()
        self.assertEqual(After.EstimatedSavingsMBThreshold, Before.EstimatedSavingsMBThreshold)


class TestCrfProfileRegression(unittest.TestCase):
    """Regression: VideoBitrateKbps=0 (CRF profile, no fixed bitrate) must NOT trigger ProfileThresholds gate or savings estimate -- 2026-06-09 dot-worker-1 NoReplace incident."""

    def setUp(self):
        self.Ev = BuildEvaluator()

    def test_crf_profile_zero_bitrate_passes_thresholds_gate(self):
        """A CRF profile (TargetVideoKbps=0, TargetAudioKbps=0) is valid; the ProfileThresholds gate fires only on None, not 0."""
        Mf = CompliantMediaFile(ResolutionCategory='720p', Codec='hevc', AudioCodec='aac', ContainerFormat='mp4', AudioComplete=True)
        CrfProfile = EffectiveProfile(ProfileName='NVENC AV1 P7 CANARY VBR -720p', TargetVideoKbps=0, TargetAudioKbps=0, TargetResolutionCategory=_Tier('T720p'))
        D = self.Ev.Evaluate(Mf, CrfProfile, MakeCache())
        self.assertNotEqual(D.GateBlocked, 'ProfileThresholds')

    def test_crf_profile_zero_bitrate_does_not_trigger_savings(self):
        """When CRF profile (kbps=0) is in play, EstimatedSavingsMBThreshold rule MUST NOT propose Transcode just because savings calc looks unbounded."""
        Mf = CompliantMediaFile(SizeMB=5000, DurationMinutes=60, ResolutionCategory='720p', Codec='av1', AudioCodec='aac', ContainerFormat='mp4', AudioComplete=True)
        CrfProfile = EffectiveProfile(ProfileName='X', TargetVideoKbps=0, TargetAudioKbps=0, TargetResolutionCategory=_Tier('T720p'))
        D = self.Ev.Evaluate(Mf, CrfProfile, MakeCache())
        self.assertNotIn('Transcode', D.OperationsNeeded)

    def test_missing_thresholds_still_blocks(self):
        """ProfileThresholds gate must still fire when TargetVideoKbps IS None (distinct from 0)."""
        Mf = CompliantMediaFile()
        NoThresholdsProfile = EffectiveProfile(ProfileName='X', TargetVideoKbps=None, TargetAudioKbps=None, TargetResolutionCategory=_Tier('T720p'))
        D = self.Ev.Evaluate(Mf, NoThresholdsProfile, MakeCache())
        self.assertEqual(D.GateBlocked, 'ProfileThresholds')


class TestBucketResolverPrecedence(unittest.TestCase):
    """C14 bucket precedence rules -- Transcode > Remux > AudioFixOnly > SubtitleFixOnly."""

    def setUp(self):
        from Features.Compliance.Services.ComplianceBucketResolver import ComplianceBucketResolver
        self.R = ComplianceBucketResolver()

    def test_empty_set_returns_compliant_no_bucket(self):
        self.assertEqual(self.R.Resolve(frozenset()), (True, None))

    def test_transcode_wins(self):
        self.assertEqual(self.R.Resolve(frozenset({'Transcode', 'Remux', 'AudioFix'})), (False, 'Transcode'))

    def test_remux_wins_over_audiofix(self):
        self.assertEqual(self.R.Resolve(frozenset({'Remux', 'AudioFix'})), (False, 'Remux'))

    def test_audiofix_alone(self):
        self.assertEqual(self.R.Resolve(frozenset({'AudioFix'})), (False, 'AudioFixOnly'))

    def test_subtitlefix_alone(self):
        self.assertEqual(self.R.Resolve(frozenset({'SubtitleFix'})), (False, 'SubtitleFixOnly'))

    def test_audiofix_subtitlefix_collapses_to_audiofixonly(self):
        self.assertEqual(self.R.Resolve(frozenset({'AudioFix', 'SubtitleFix'})), (False, 'AudioFixOnly'))


if __name__ == '__main__':
    unittest.main()
