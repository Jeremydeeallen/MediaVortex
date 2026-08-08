# directive: plan-factory-driven-by-compliance-flags | # see transcode.D2 -- 2^3 flag combos

import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from Features.TranscodeJob.Emit.Plan import Plan, PlanFactory


def _Mf(V, A, C):
    Mf = MagicMock()
    Mf.Id = 1
    Mf.VideoCompliant = V
    Mf.AudioCompliant = A
    Mf.ContainerCompliant = C
    return Mf


class TestPlanFactoryFromComplianceState(unittest.TestCase):

    def test_fff_all_reencode(self):
        self.assertEqual(
            PlanFactory().FromComplianceState(_Mf(False, False, False)),
            Plan(VideoOp='Reencode', AudioOp='Reencode', SubtitleOp='Preserve', ContainerOp='Mp4'),
        )

    def test_ttf_container_only(self):
        self.assertEqual(
            PlanFactory().FromComplianceState(_Mf(True, True, False)),
            Plan(VideoOp='Copy', AudioOp='Copy', SubtitleOp='Preserve', ContainerOp='Mp4'),
        )

    def test_tft_audio_only(self):
        self.assertEqual(
            PlanFactory().FromComplianceState(_Mf(True, False, True)),
            Plan(VideoOp='Copy', AudioOp='Reencode', SubtitleOp='Preserve', ContainerOp='Preserve'),
        )

    def test_ftt_video_only(self):
        self.assertEqual(
            PlanFactory().FromComplianceState(_Mf(False, True, True)),
            Plan(VideoOp='Reencode', AudioOp='Copy', SubtitleOp='Preserve', ContainerOp='Preserve'),
        )

    def test_ttt_all_copy(self):
        self.assertEqual(
            PlanFactory().FromComplianceState(_Mf(True, True, True)),
            Plan(VideoOp='Copy', AudioOp='Copy', SubtitleOp='Preserve', ContainerOp='Preserve'),
        )

    def test_ffT_container_ok(self):
        self.assertEqual(
            PlanFactory().FromComplianceState(_Mf(False, False, True)),
            Plan(VideoOp='Reencode', AudioOp='Reencode', SubtitleOp='Preserve', ContainerOp='Preserve'),
        )

    def test_fTf_audio_ok(self):
        self.assertEqual(
            PlanFactory().FromComplianceState(_Mf(False, True, False)),
            Plan(VideoOp='Reencode', AudioOp='Copy', SubtitleOp='Preserve', ContainerOp='Mp4'),
        )

    def test_Tff_video_ok(self):
        self.assertEqual(
            PlanFactory().FromComplianceState(_Mf(True, False, False)),
            Plan(VideoOp='Copy', AudioOp='Reencode', SubtitleOp='Preserve', ContainerOp='Mp4'),
        )

    def test_none_video_raises(self):
        with self.assertRaises(ValueError):
            PlanFactory().FromComplianceState(_Mf(None, True, True))

    def test_none_audio_raises(self):
        with self.assertRaises(ValueError):
            PlanFactory().FromComplianceState(_Mf(True, None, True))

    def test_none_container_raises(self):
        with self.assertRaises(ValueError):
            PlanFactory().FromComplianceState(_Mf(True, True, None))


if __name__ == '__main__':
    unittest.main()
