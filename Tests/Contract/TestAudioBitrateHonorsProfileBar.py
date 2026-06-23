import unittest

from Features.AudioNormalization.AudioFilterEmitter import AudioFilterEmitter


# directive: worker-runtime-state | # see audio-normalization.C8
class _FakeProfile:

    # directive: worker-runtime-state | # see audio-normalization.C8
    def __init__(self, TargetAudioKbps):
        self.TargetAudioKbps = TargetAudioKbps


# directive: worker-runtime-state | # see audio-normalization.C8
class _FakeResolver:

    # directive: worker-runtime-state | # see audio-normalization.C8
    def __init__(self, Profile):
        self._Profile = Profile

    # directive: worker-runtime-state | # see audio-normalization.C8
    def Resolve(self, _MediaFile):
        return self._Profile


# directive: worker-runtime-state | # see audio-normalization.C8
class TestAudioBitrateHonorsProfileBar(unittest.TestCase):

    # directive: worker-runtime-state | # see audio-normalization.C8
    def test_clamps_track_bitrate_to_profile_ceiling(self):
        Emitter = AudioFilterEmitter(ProfileResolver=_FakeResolver(_FakeProfile(TargetAudioKbps=128)))
        Emitter._ProfileBitrateCeiling = 128
        Args = Emitter._BuildCodecArgs({'Bitrate': 256}, 'reencode', 'eac3', 0)
        self.assertIn('-b:a:0', Args)
        self.assertEqual(Args[Args.index('-b:a:0') + 1], '128k')

    # directive: worker-runtime-state | # see audio-normalization.C8
    def test_preserves_track_bitrate_when_below_ceiling(self):
        Emitter = AudioFilterEmitter(ProfileResolver=_FakeResolver(_FakeProfile(TargetAudioKbps=192)))
        Emitter._ProfileBitrateCeiling = 192
        Args = Emitter._BuildCodecArgs({'Bitrate': 96}, 'reencode', 'aac', 0)
        self.assertEqual(Args[Args.index('-b:a:0') + 1], '96k')

    # directive: worker-runtime-state | # see audio-normalization.C8
    def test_no_resolver_no_clamp(self):
        Emitter = AudioFilterEmitter()
        Args = Emitter._BuildCodecArgs({'Bitrate': 256}, 'reencode', 'eac3', 0)
        self.assertEqual(Args[Args.index('-b:a:0') + 1], '256k')

    # directive: worker-runtime-state | # see audio-normalization.C8
    def test_profile_without_ceiling_no_clamp(self):
        Emitter = AudioFilterEmitter(ProfileResolver=_FakeResolver(_FakeProfile(TargetAudioKbps=None)))
        Emitter._ProfileBitrateCeiling = Emitter._ResolveProfileBitrateCeiling(object())
        Args = Emitter._BuildCodecArgs({'Bitrate': 256}, 'reencode', 'eac3', 0)
        self.assertEqual(Args[Args.index('-b:a:0') + 1], '256k')

    # directive: worker-runtime-state | # see audio-normalization.C8
    def test_stream_copy_refused_when_source_exceeds_ceiling(self):
        """Even when policy says stream_copy, force reencode if source AudioBitrateKbps > Profile ceiling."""
        from Features.AudioNormalization.AudioStrategyClassifier import STRATEGY_SKIP
        class _S: Strategy = STRATEGY_SKIP
        class _Mf:
            AudioCodec = 'aac'
            AudioBitrateKbps = 160
            AudioCorruptSuspect = False
        Emitter = AudioFilterEmitter(ProfileResolver=_FakeResolver(_FakeProfile(TargetAudioKbps=128)))
        Emitter._ProfileBitrateCeiling = 128
        Mode = Emitter._DecideStreamCopyOrReencode(_Mf, {'Codec': 'aac'}, _S())
        self.assertEqual(Mode, 'reencode')

    # directive: worker-runtime-state | # see audio-normalization.C8
    def test_stream_copy_allowed_when_source_at_or_below_ceiling(self):
        """When source bitrate <= ceiling and policy says skip, stream_copy stays allowed."""
        from Features.AudioNormalization.AudioStrategyClassifier import STRATEGY_SKIP
        class _S: Strategy = STRATEGY_SKIP
        class _Mf:
            AudioCodec = 'aac'
            AudioBitrateKbps = 96
            AudioCorruptSuspect = False
        Emitter = AudioFilterEmitter(ProfileResolver=_FakeResolver(_FakeProfile(TargetAudioKbps=128)))
        Emitter._ProfileBitrateCeiling = 128
        Mode = Emitter._DecideStreamCopyOrReencode(_Mf, {'Codec': 'aac'}, _S())
        self.assertEqual(Mode, 'stream_copy')


if __name__ == '__main__':
    unittest.main()
