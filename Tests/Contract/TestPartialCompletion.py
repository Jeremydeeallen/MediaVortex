# directive: partial-pipeline-completion | # see transcode.D13
import os
import sys
import unittest
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

from Features.TranscodeJob.Worker.PartialCompletion import (
    AUDIO_STDERR_MARKERS,
    DispositionReasonForCopiedSlot,
    FollowupPlanForCopiedSlot,
    OppositeSlot,
    SniffFirstFallback,
)
from Features.TranscodeJob.Emit.Plan import Plan


class TestSniffFirstFallback(unittest.TestCase):

    def test_libopus_marker_picks_audio_first(self):
        Stderr = "[libopus @ 0x7f]  channel_layout '5.1(side)' not supported"
        self.assertEqual(SniffFirstFallback(Stderr), 'AudioSlot')

    def test_demucs_marker_picks_audio_first(self):
        Stderr = "Demucs subprocess failed: torch.cuda.OutOfMemoryError"
        self.assertEqual(SniffFirstFallback(Stderr), 'AudioSlot')

    def test_loudnorm_marker_picks_audio_first(self):
        Stderr = "loudnorm=I=-23.00:LRA=15.20:TP=-5.00 measured_I parse error"
        self.assertEqual(SniffFirstFallback(Stderr), 'AudioSlot')

    def test_generic_audio_marker_picks_audio_first(self):
        Stderr = "Error: no valid audio channel layout available"
        self.assertEqual(SniffFirstFallback(Stderr), 'AudioSlot')

    def test_nvenc_encoder_error_picks_video_first(self):
        Stderr = "[av1_nvenc @ 0x7f] Cannot allocate memory for encoder session"
        self.assertEqual(SniffFirstFallback(Stderr), 'VideoSlot')

    def test_qsv_encoder_error_picks_video_first(self):
        Stderr = "[av1_qsv @ 0x7f] Invalid FrameType:0"
        self.assertEqual(SniffFirstFallback(Stderr), 'VideoSlot')

    def test_empty_stderr_picks_video_first(self):
        self.assertEqual(SniffFirstFallback(''), 'VideoSlot')

    def test_none_stderr_picks_video_first(self):
        self.assertEqual(SniffFirstFallback(None), 'VideoSlot')

    def test_case_insensitive_match(self):
        Stderr = "LIBOPUS: fatal decode error"
        self.assertEqual(SniffFirstFallback(Stderr), 'AudioSlot')

    def test_all_markers_present_in_config(self):
        self.assertEqual(
            set(AUDIO_STDERR_MARKERS),
            {'libopus', 'demucs', 'loudnorm', 'audio'},
        )


class TestOppositeSlot(unittest.TestCase):

    def test_audio_returns_video(self):
        self.assertEqual(OppositeSlot('AudioSlot'), 'VideoSlot')

    def test_video_returns_audio(self):
        self.assertEqual(OppositeSlot('VideoSlot'), 'AudioSlot')

    def test_invalid_raises(self):
        with self.assertRaises(ValueError):
            OppositeSlot('SubtitleSlot')


class TestDispositionReasonForCopiedSlot(unittest.TestCase):

    def test_audio_slot_reason(self):
        self.assertEqual(
            DispositionReasonForCopiedSlot('AudioSlot'),
            'PartialSuccess_AudioSlotCopied',
        )

    def test_video_slot_reason(self):
        self.assertEqual(
            DispositionReasonForCopiedSlot('VideoSlot'),
            'PartialSuccess_VideoSlotCopied',
        )

    def test_invalid_raises(self):
        with self.assertRaises(ValueError):
            DispositionReasonForCopiedSlot('ContainerSlot')


class TestFollowupPlanForCopiedSlot(unittest.TestCase):

    def test_audio_copied_followup_is_audiofix_no_override(self):
        Result = FollowupPlanForCopiedSlot('AudioSlot')
        self.assertEqual(Result['ProcessingMode'], 'AudioFix')
        self.assertIsNone(Result['AudioSlotOverride'])

    def test_video_copied_followup_is_transcode_with_audio_copy_override(self):
        Result = FollowupPlanForCopiedSlot('VideoSlot')
        self.assertEqual(Result['ProcessingMode'], 'Transcode')
        self.assertEqual(Result['AudioSlotOverride'], 'Copy')

    def test_invalid_raises(self):
        with self.assertRaises(ValueError):
            FollowupPlanForCopiedSlot('SubtitleSlot')


class TestPlanWithSlotForcedToCopy(unittest.TestCase):

    def _MakePlan(self):
        return Plan(VideoOp='Reencode', AudioOp='Reencode', SubtitleOp='Preserve', ContainerOp='Mp4')

    def test_video_slot_forced_to_copy(self):
        Original = self._MakePlan()
        Mutated = Original.WithSlotForcedToCopy('VideoSlot')
        self.assertEqual(Mutated.VideoOp, 'Copy')
        self.assertEqual(Mutated.AudioOp, 'Reencode')
        self.assertEqual(Mutated.SubtitleOp, 'Preserve')
        self.assertEqual(Mutated.ContainerOp, 'Mp4')

    def test_audio_slot_forced_to_copy(self):
        Original = self._MakePlan()
        Mutated = Original.WithSlotForcedToCopy('AudioSlot')
        self.assertEqual(Mutated.VideoOp, 'Reencode')
        self.assertEqual(Mutated.AudioOp, 'Copy')
        self.assertEqual(Mutated.SubtitleOp, 'Preserve')
        self.assertEqual(Mutated.ContainerOp, 'Mp4')

    def test_original_unchanged_after_mutation(self):
        Original = self._MakePlan()
        _ = Original.WithSlotForcedToCopy('VideoSlot')
        self.assertEqual(Original.VideoOp, 'Reencode')
        self.assertEqual(Original.AudioOp, 'Reencode')

    def test_invalid_side_raises(self):
        Original = self._MakePlan()
        with self.assertRaises(ValueError):
            Original.WithSlotForcedToCopy('SubtitleSlot')


if __name__ == '__main__':
    unittest.main()
