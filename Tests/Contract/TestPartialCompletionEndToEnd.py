# directive: partial-pipeline-completion | # see transcode.D13
import os
import sys
import unittest
from unittest.mock import MagicMock, patch
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

from Features.TranscodeJob.Worker import PartialCompletion
from Features.TranscodeJob.Emit.Plan import Plan


class TestFallbackOrdering(unittest.TestCase):
    """Verifies the two-fallback ordering table without spinning up ffmpeg. Sniff -> first/second slot pairings."""

    def test_audio_marker_picks_audio_first_then_video_second(self):
        FirstSide = PartialCompletion.SniffFirstFallback("[libopus] channel_layout fail")
        SecondSide = PartialCompletion.OppositeSlot(FirstSide)
        self.assertEqual((FirstSide, SecondSide), ('AudioSlot', 'VideoSlot'))

    def test_no_audio_marker_picks_video_first_then_audio_second(self):
        FirstSide = PartialCompletion.SniffFirstFallback("[av1_nvenc] rc=-2 encoder init failed")
        SecondSide = PartialCompletion.OppositeSlot(FirstSide)
        self.assertEqual((FirstSide, SecondSide), ('VideoSlot', 'AudioSlot'))


class TestFollowupPlanRouting(unittest.TestCase):
    """Verifies that CopiedSlot -> follow-up (ProcessingMode, AudioSlotOverride) mapping matches D5."""

    def test_audio_copied_routes_to_audiofix_no_override(self):
        Followup = PartialCompletion.FollowupPlanForCopiedSlot('AudioSlot')
        self.assertEqual(Followup, {'ProcessingMode': 'AudioFix', 'AudioSlotOverride': None})

    def test_video_copied_routes_to_transcode_with_audio_copy_override(self):
        Followup = PartialCompletion.FollowupPlanForCopiedSlot('VideoSlot')
        self.assertEqual(Followup, {'ProcessingMode': 'Transcode', 'AudioSlotOverride': 'Copy'})


class TestDispositionReasonMapping(unittest.TestCase):
    """Verifies CopiedSlot -> DispositionReason mapping is symmetric with SniffFirstFallback outcomes."""

    def test_audio_copied_reason(self):
        self.assertEqual(
            PartialCompletion.DispositionReasonForCopiedSlot('AudioSlot'),
            'PartialSuccess_AudioSlotCopied',
        )

    def test_video_copied_reason(self):
        self.assertEqual(
            PartialCompletion.DispositionReasonForCopiedSlot('VideoSlot'),
            'PartialSuccess_VideoSlotCopied',
        )


class TestPlanMutationForFallback(unittest.TestCase):
    """Verifies Plan.WithSlotForcedToCopy produces the exact Plan shape the fallback ffmpeg needs."""

    def test_video_reencode_plan_mutated_to_video_copy_preserves_audio_reencode(self):
        Original = Plan(VideoOp='Reencode', AudioOp='Reencode', SubtitleOp='Preserve', ContainerOp='Mp4')
        Mutated = Original.WithSlotForcedToCopy('VideoSlot')
        self.assertEqual(Mutated.VideoOp, 'Copy')
        self.assertEqual(Mutated.AudioOp, 'Reencode')

    def test_video_reencode_plan_mutated_to_audio_copy_preserves_video_reencode(self):
        Original = Plan(VideoOp='Reencode', AudioOp='Reencode', SubtitleOp='Preserve', ContainerOp='Mp4')
        Mutated = Original.WithSlotForcedToCopy('AudioSlot')
        self.assertEqual(Mutated.VideoOp, 'Reencode')
        self.assertEqual(Mutated.AudioOp, 'Copy')


class TestLoggingCalls(unittest.TestCase):
    """Verifies fail-loud log invariants (D8 amendment): sniff INFO, attempt INFO, success WARNING, both-fail ERROR, child-exhausted ERROR."""

    @patch('Features.TranscodeJob.Worker.PartialCompletion.LoggingService')
    def test_log_sniff_uses_info_level(self, MockLogging):
        PartialCompletion.LogSniff(42, "[libopus] fail", 'AudioSlot')
        MockLogging.LogInfo.assert_called_once()
        Msg = MockLogging.LogInfo.call_args[0][0]
        self.assertIn('PartialCompletionSniff', Msg)
        self.assertIn('MediaFileId=42', Msg)
        self.assertIn("first_fallback=AudioSlot", Msg)
        self.assertIn("['libopus']", Msg)

    @patch('Features.TranscodeJob.Worker.PartialCompletion.LoggingService')
    def test_log_fallback_attempt_uses_info_level(self, MockLogging):
        PartialCompletion.LogFallbackAttempt(42, 1, 'VideoSlot')
        MockLogging.LogInfo.assert_called_once()
        Msg = MockLogging.LogInfo.call_args[0][0]
        self.assertIn('PartialCompletionFallback', Msg)
        self.assertIn('attempt=1', Msg)

    @patch('Features.TranscodeJob.Worker.PartialCompletion.LoggingService')
    def test_log_fallback_success_uses_warning_level(self, MockLogging):
        PartialCompletion.LogFallbackSuccess(42, 2, 'AudioSlot')
        MockLogging.LogWarning.assert_called_once()
        Msg = MockLogging.LogWarning.call_args[0][0]
        self.assertIn('PartialCompletionSuccess', Msg)
        self.assertIn('disposition_reason=PartialSuccess_AudioSlotCopied', Msg)

    @patch('Features.TranscodeJob.Worker.PartialCompletion.LoggingService')
    def test_log_both_fallbacks_failed_uses_error_level(self, MockLogging):
        PartialCompletion.LogBothFallbacksFailed(42, "orig-err", "fb1-err", "fb2-err")
        MockLogging.LogError.assert_called_once()
        Msg = MockLogging.LogError.call_args[0][0]
        self.assertIn('PartialCompletionExhausted', Msg)
        self.assertIn('orig-err', Msg)
        self.assertIn('fb1-err', Msg)
        self.assertIn('fb2-err', Msg)

    @patch('Features.TranscodeJob.Worker.PartialCompletion.LoggingService')
    def test_log_partial_retry_exhausted_uses_error_level(self, MockLogging):
        PartialCompletion.LogPartialRetryExhausted(42, 100, "child-err")
        MockLogging.LogError.assert_called_once()
        Msg = MockLogging.LogError.call_args[0][0]
        self.assertIn('PartialRetryExhausted', Msg)
        self.assertIn('ParentAttemptId=100', Msg)


class TestQueueRowCarriesFallbackFields(unittest.TestCase):
    """Verifies TranscodeQueueModel exposes ParentTranscodeAttemptId + AudioSlotOverride so the JobProcessor's D9 cap and fallback-Plan hint reach it."""

    def test_model_defaults_to_none_for_normal_jobs(self):
        from Features.TranscodeQueue.Models.TranscodeQueueModel import TranscodeQueueModel
        Row = TranscodeQueueModel(Id=1, StorageRootId=1, RelativePath='x/y.mkv', FileName='y.mkv', SizeMB=100.0)
        self.assertIsNone(Row.ParentTranscodeAttemptId)
        self.assertIsNone(Row.AudioSlotOverride)

    def test_model_carries_populated_fields_for_partial_followup(self):
        from Features.TranscodeQueue.Models.TranscodeQueueModel import TranscodeQueueModel
        Row = TranscodeQueueModel(Id=1, MediaFileId=99,
                                  ParentTranscodeAttemptId=12345,
                                  AudioSlotOverride='Copy')
        self.assertEqual(Row.ParentTranscodeAttemptId, 12345)
        self.assertEqual(Row.AudioSlotOverride, 'Copy')


if __name__ == '__main__':
    unittest.main()
