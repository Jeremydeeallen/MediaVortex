import os
import sys
import unittest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))

from Features.AudioNormalization.AudioFilterEmitter import AudioFilterEmitter
from Features.AudioNormalization.AudioStrategyClassifier import STRATEGY_REVIEW
from Features.AudioNormalization.AudioStrategyResult import AudioPolicyUnresolvedError


# directive: audio-pipeline-fail-loud
class _AlwaysReviewClassifier:

    # directive: audio-pipeline-fail-loud
    def ClassifyTrack(self, MediaFile, TrackConfig, Policy):
        class _Verdict:
            Strategy = STRATEGY_REVIEW
        return _Verdict()


# directive: audio-pipeline-fail-loud
class _FakeProfileResolver:

    # directive: audio-pipeline-fail-loud
    def __init__(self, CeilingKbps):
        self._CeilingKbps = CeilingKbps

    # directive: audio-pipeline-fail-loud
    def Resolve(self, MediaFile):
        class _Profile:
            pass
        Profile = _Profile()
        Profile.TargetAudioKbps = self._CeilingKbps
        return Profile


# directive: audio-pipeline-fail-loud
class _FakeLanguageDetector:

    # directive: audio-pipeline-fail-loud
    def Detect(self, AudioStreams, LibraryDefault=None, SpeechCache=None, EnableSpeechLayer=False):
        class _StreamLang:
            def __init__(self, idx, lang):
                self.StreamIndex = idx
                self.Language = lang
        class _Detection:
            pass
        D = _Detection()
        D.StreamLanguages = [_StreamLang(S.get('index', 0), 'eng') for S in AudioStreams]
        return D


# directive: audio-pipeline-fail-loud
class _MediaFile:

    # directive: audio-pipeline-fail-loud
    def __init__(self, **Kwargs):
        for K, V in Kwargs.items():
            setattr(self, K, V)


# directive: audio-pipeline-fail-loud
class TestAudioBitratePolicyHonorsCeiling(unittest.TestCase):

    def setUp(self):
        self.Emitter = AudioFilterEmitter(
            Classifier=_AlwaysReviewClassifier(),
            LanguageDetectorInstance=_FakeLanguageDetector(),
            ProfileResolver=_FakeProfileResolver(CeilingKbps=192),
        )
        self.Policy = {
            'EmitTracks': [
                {'Label': 'Dialog Boost', 'Codec': 'eac3', 'LanguageFilter': 'keep-all', 'IsDefaultTrack': True},
            ],
            'KeepCommentaryTracks': False,
            'EnableSpeechLanguageDetection': False,
            'LanguageDefault': None,
        }
        self.AudioStreams = [{'index': 0, 'tags': {'language': 'eng'}, 'disposition': {}}]

    def test_review_with_truehd_source_emits_eac3_at_ceiling(self):
        MediaFile = _MediaFile(AudioCodec='truehd', AudioBitrateKbps=1024, AudioCorruptSuspect=False)
        Blocks = self.Emitter.EmitTracks(MediaFile, self.Policy, AudioStreams=self.AudioStreams)
        self.assertGreater(len(Blocks), 0, "REVIEW must NOT silently skip the track; resolver-driven block expected")
        Block = Blocks[0]
        Argv = ' '.join(Block.CodecArgs)
        self.assertIn('eac3', Argv, f"REVIEW + truehd source must emit eac3, got: {Argv}")
        self.assertIn('192k', Argv, f"REVIEW must clamp to 192k ceiling, got: {Argv}")

    def test_review_with_aac_source_emits_stream_copy(self):
        MediaFile = _MediaFile(AudioCodec='aac', AudioBitrateKbps=128, AudioCorruptSuspect=False)
        Blocks = self.Emitter.EmitTracks(MediaFile, self.Policy, AudioStreams=self.AudioStreams)
        self.assertGreater(len(Blocks), 0)
        Block = Blocks[0]
        Argv = ' '.join(Block.CodecArgs)
        self.assertIn('copy', Argv, f"REVIEW + MP4-compat source goes through codec policy stream_copy, got: {Argv}")

    def test_review_with_no_ceiling_and_no_config_bitrate_raises(self):
        Emitter = AudioFilterEmitter(
            Classifier=_AlwaysReviewClassifier(),
            LanguageDetectorInstance=_FakeLanguageDetector(),
            ProfileResolver=_FakeProfileResolver(CeilingKbps=None),
        )
        Policy = dict(self.Policy)
        Policy['EmitTracks'] = [
            {'Label': 'Dialog Boost', 'Codec': 'eac3', 'LanguageFilter': 'keep-all', 'IsDefaultTrack': True},
        ]
        MediaFile = _MediaFile(AudioCodec='truehd', AudioBitrateKbps=None, AudioCorruptSuspect=False)
        with self.assertRaises(AudioPolicyUnresolvedError):
            Emitter.EmitTracks(MediaFile, Policy, AudioStreams=self.AudioStreams)


if __name__ == '__main__':
    unittest.main()
