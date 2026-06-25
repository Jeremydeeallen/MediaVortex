import os
import sys
import unittest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))

from Features.AudioNormalization.AudioStrategyResult import Accept, Reject, AudioPolicyUnresolvedError
from Features.AudioNormalization.Policies.IAudioBitratePolicy import ProfileCeilingBitratePolicy
from Features.AudioNormalization.Policies.IAudioCodecPolicy import EAC3OrPassthroughCodecPolicy
from Features.AudioNormalization.Policies.IAudioDefaultLanguagePolicy import RankPreferredDefaultPolicy
from Features.AudioNormalization.AudioDispositionResolver import AudioDispositionResolver


# directive: audio-pipeline-fail-loud
class TestProfileCeilingBitratePolicy(unittest.TestCase):

    def setUp(self):
        self.Policy = ProfileCeilingBitratePolicy()

    def test_clamps_config_to_ceiling(self):
        Result = self.Policy.Decide(ProfileCeilingKbps=192, SourceBitrateKbps=1024, ConfigBitrateKbps=384)
        self.assertIsInstance(Result, Accept)
        self.assertEqual(Result.Plan, 192)

    def test_clamps_source_to_ceiling_when_no_config(self):
        Result = self.Policy.Decide(ProfileCeilingKbps=192, SourceBitrateKbps=1024, ConfigBitrateKbps=None)
        self.assertIsInstance(Result, Accept)
        self.assertEqual(Result.Plan, 192)

    def test_uses_config_when_under_ceiling(self):
        Result = self.Policy.Decide(ProfileCeilingKbps=192, SourceBitrateKbps=None, ConfigBitrateKbps=128)
        self.assertIsInstance(Result, Accept)
        self.assertEqual(Result.Plan, 128)

    def test_uses_ceiling_when_neither_config_nor_source(self):
        Result = self.Policy.Decide(ProfileCeilingKbps=192, SourceBitrateKbps=None, ConfigBitrateKbps=None)
        self.assertIsInstance(Result, Accept)
        self.assertEqual(Result.Plan, 192)

    def test_rejects_when_no_ceiling_and_no_config(self):
        Result = self.Policy.Decide(ProfileCeilingKbps=None, SourceBitrateKbps=1024, ConfigBitrateKbps=None)
        self.assertIsInstance(Result, Reject)
        self.assertEqual(Result.Reason, 'no_ceiling_and_no_config_bitrate')


# directive: audio-pipeline-fail-loud
class TestEAC3OrPassthroughCodecPolicy(unittest.TestCase):

    def setUp(self):
        self.Policy = EAC3OrPassthroughCodecPolicy()

    def test_passthrough_eac3_source(self):
        Result = self.Policy.Decide(SourceCodec='eac3', ForceReencode=False, AudioCorruptSuspect=False)
        self.assertIsInstance(Result, Accept)
        self.assertEqual(Result.Plan['Codec'], 'copy')
        self.assertEqual(Result.Plan['Mode'], 'stream_copy')

    def test_passthrough_aac_source(self):
        Result = self.Policy.Decide(SourceCodec='aac', ForceReencode=False, AudioCorruptSuspect=False)
        self.assertEqual(Result.Plan['Codec'], 'copy')

    def test_reencode_truehd_source(self):
        Result = self.Policy.Decide(SourceCodec='truehd', ForceReencode=False, AudioCorruptSuspect=False)
        self.assertIsInstance(Result, Accept)
        self.assertEqual(Result.Plan['Codec'], 'eac3')
        self.assertEqual(Result.Plan['Mode'], 'reencode')

    def test_reencode_when_force(self):
        Result = self.Policy.Decide(SourceCodec='eac3', ForceReencode=True, AudioCorruptSuspect=False)
        self.assertEqual(Result.Plan['Mode'], 'reencode')

    def test_reencode_when_audio_corrupt_suspect(self):
        Result = self.Policy.Decide(SourceCodec='eac3', ForceReencode=False, AudioCorruptSuspect=True)
        self.assertEqual(Result.Plan['Mode'], 'reencode')

    def test_reencode_when_source_bitrate_over_ceiling(self):
        # directive: worker-runtime-state
        Result = self.Policy.Decide(
            SourceCodec='aac', ForceReencode=False, AudioCorruptSuspect=False,
            ProfileCeilingKbps=128, SourceBitrateKbps=160,
        )
        self.assertEqual(Result.Plan['Mode'], 'reencode')
        self.assertEqual(Result.Plan['Reason'], 'source_bitrate_over_ceiling')

    def test_passthrough_when_source_under_ceiling(self):
        # directive: worker-runtime-state
        Result = self.Policy.Decide(
            SourceCodec='aac', ForceReencode=False, AudioCorruptSuspect=False,
            ProfileCeilingKbps=192, SourceBitrateKbps=128,
        )
        self.assertEqual(Result.Plan['Codec'], 'copy')


# directive: audio-pipeline-fail-loud
class TestRankPreferredDefaultPolicy(unittest.TestCase):

    def setUp(self):
        self.Policy = RankPreferredDefaultPolicy()

    def test_english_preferred_over_french(self):
        Result = self.Policy.Decide(PresentLanguages=['fra', 'eng'], LibraryDefault=None)
        self.assertIsInstance(Result, Accept)
        self.assertEqual(Result.Plan['Language'], 'eng')

    def test_library_default_overrides_rank(self):
        Result = self.Policy.Decide(PresentLanguages=['eng', 'fra'], LibraryDefault='fra')
        self.assertEqual(Result.Plan['Language'], 'fra')
        self.assertEqual(Result.Plan['Reason'], 'library_default_present')

    def test_first_source_order_when_no_rank_match(self):
        Result = self.Policy.Decide(PresentLanguages=['fra', 'deu'], LibraryDefault=None)
        self.assertIsInstance(Result, Accept)
        self.assertEqual(Result.Plan['Language'], 'fra')
        self.assertEqual(Result.Plan['Reason'], 'first_source_order_present')

    def test_rejects_when_no_present_languages(self):
        Result = self.Policy.Decide(PresentLanguages=['und', ''], LibraryDefault=None)
        self.assertIsInstance(Result, Reject)
        self.assertEqual(Result.Reason, 'no_tagged_present_languages')

    def test_english_single_track(self):
        Result = self.Policy.Decide(PresentLanguages=['eng'], LibraryDefault=None)
        self.assertEqual(Result.Plan['Language'], 'eng')


# directive: audio-pipeline-fail-loud
class TestAudioDispositionResolver(unittest.TestCase):

    def setUp(self):
        self.Resolver = AudioDispositionResolver()

    def test_resolves_passthrough_track(self):
        Disp = self.Resolver.ResolveForTrack(
            TrackIndex=0, ProfileCeilingKbps=192, SourceBitrateKbps=192, ConfigBitrateKbps=None,
            SourceCodec='eac3', ForceReencode=False, AudioCorruptSuspect=False, IsDefault=True,
        )
        self.assertEqual(Disp.Mode, 'stream_copy')
        self.assertEqual(Disp.Codec, 'copy')
        self.assertIsNone(Disp.BitrateKbps)
        self.assertEqual(len(Disp.Verdicts), 1)

    def test_resolves_reencode_track_clamps_bitrate(self):
        Disp = self.Resolver.ResolveForTrack(
            TrackIndex=0, ProfileCeilingKbps=192, SourceBitrateKbps=1024, ConfigBitrateKbps=384,
            SourceCodec='truehd', ForceReencode=False, AudioCorruptSuspect=False, IsDefault=True,
        )
        self.assertEqual(Disp.Mode, 'reencode')
        self.assertEqual(Disp.Codec, 'eac3')
        self.assertEqual(Disp.BitrateKbps, 192)
        self.assertEqual(len(Disp.Verdicts), 2)

    def test_raises_when_reencode_has_no_bitrate_source(self):
        with self.assertRaises(AudioPolicyUnresolvedError) as Ctx:
            self.Resolver.ResolveForTrack(
                TrackIndex=2, ProfileCeilingKbps=None, SourceBitrateKbps=None, ConfigBitrateKbps=None,
                SourceCodec='truehd', ForceReencode=False, AudioCorruptSuspect=False, IsDefault=False,
            )
        self.assertEqual(Ctx.exception.PolicyName, 'ProfileCeilingBitratePolicy')
        self.assertEqual(Ctx.exception.TrackIndex, 2)


if __name__ == '__main__':
    unittest.main()
