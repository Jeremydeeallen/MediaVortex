# directive: bug-0095-failure-classification | # see failure-accounting.C10
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from Features.FailureAccounting.Services.FailureClassifier import FailureClassifier


class TestFailureClassifier(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.C = FailureClassifier()

    def test_source_unreadable_moov_atom(self):
        self.assertEqual(
            self.C.Classify("FFmpeg exit 1. [in#0 @ 0x0] moov atom not found. Cannot open input"),
            'source_unreadable',
        )

    def test_source_unreadable_invalid_data(self):
        self.assertEqual(
            self.C.Classify("Error opening input: Invalid data found when processing input"),
            'source_unreadable',
        )

    def test_source_audio_corrupt_dts(self):
        self.assertEqual(
            self.C.Classify("Error while decoding stream 0:1: dca decoder error"),
            'source_audio_corrupt_dts',
        )

    def test_source_video_corrupt_h264(self):
        self.assertEqual(
            self.C.Classify("Error while decoding stream 0:0: h264 slice header error"),
            'source_video_corrupt_h264',
        )

    def test_subtitle_sample_too_large(self):
        self.assertEqual(
            self.C.Classify("[sost#0:4/mov_text @ 0x0] Error encoding a frame: Result too large"),
            'subtitle_sample_too_large',
        )

    def test_pix_fmt_unsupported(self):
        self.assertEqual(
            self.C.Classify("Impossible to convert between the formats supported by the encoder yuv422p16le yuv422p16be yuv444p16le"),
            'pix_fmt_unsupported',
        )

    def test_demucs_daemon_down(self):
        self.assertEqual(
            self.C.Classify("DemucsDaemonUnavailableError: daemon socket refused connection"),
            'demucs_daemon_down',
        )

    def test_loudness_invalid_unrecoverable(self):
        self.assertEqual(
            self.C.Classify("Post-encode pipeline failed: ProcessFileReplacement returned failure: ComplianceGateFailed: invalid_loudness_measurement"),
            'loudness_invalid_unrecoverable',
        )

    def test_ffmpeg_crash_midencode(self):
        self.assertEqual(
            self.C.Classify("Segmentation fault (core dumped)"),
            'ffmpeg_crash_midencode',
        )

    def test_codec_map_mismatch(self):
        self.assertEqual(
            self.C.Classify("Requested output format 'mp4' does not accept codec 'flac'"),
            'codec_map_mismatch',
        )

    def test_orphan_output(self):
        self.assertEqual(
            self.C.Classify("Refusing to overwrite existing file at /mnt/media_tv/foo.mp4"),
            'orphan_output',
        )

    def test_unclassified_catchall(self):
        self.assertEqual(
            self.C.Classify("Just some random error with no seed rule match"),
            'unclassified',
        )

    def test_empty_returns_unclassified(self):
        self.assertEqual(self.C.Classify(''), 'unclassified')

    def test_none_returns_unclassified(self):
        self.assertEqual(self.C.Classify(None), 'unclassified')

    def test_first_match_wins_by_priority(self):
        """source_unreadable (Priority 10) fires before stereo_downmix_source_unreadable (Priority 55) even when both regex would match."""
        self.assertEqual(
            self.C.Classify("stereo downmix failed (exit 183): moov atom not found"),
            'source_unreadable',
        )


if __name__ == '__main__':
    unittest.main()
