# directive: transcode-flow-canonical
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from Features.QualityTesting.Vmaf.AlignmentSpec import AlignmentSpec, AlignmentSpecError


# directive: transcode-flow-canonical
class TestAlignmentSpec(unittest.TestCase):

    # directive: transcode-flow-canonical
    def _MakeValid(self, **Overrides):
        Base = dict(
            ColorPrimaries='bt709',
            TransferFunction='bt709',
            ColorMatrix='bt709',
            ColorRange='tv',
            SourceFps=23.976,
            TargetFps=23.976,
            VfrDetected=False,
            TargetResolution=(1920, 1080),
            SourceCrop=None,
            EncodedCrop=None,
            DeinterlaceNeeded=False,
            DetelecineNeeded=False,
            SourceBitDepth=8,
            TargetBitDepth=8,
            ChromaSubsampling='4:2:0',
            HdrDetected=False,
            MaxEdgePx=1920,
            SourceDurationSec=100.0,
            EncodedDurationSec=100.0,
        )
        Base.update(Overrides)
        return AlignmentSpec(**Base)

    # directive: transcode-flow-canonical
    def test_valid_spec_constructs(self):
        Spec = self._MakeValid()
        self.assertEqual(Spec.ColorPrimaries, 'bt709')
        self.assertEqual(Spec.TargetResolution, (1920, 1080))

    # directive: transcode-flow-canonical
    def test_spec_is_frozen(self):
        Spec = self._MakeValid()
        with self.assertRaises(Exception):
            Spec.ColorPrimaries = 'bt2020'

    # directive: transcode-flow-canonical
    def test_empty_primaries_raises(self):
        with self.assertRaises(AlignmentSpecError):
            self._MakeValid(ColorPrimaries='')

    # directive: transcode-flow-canonical
    def test_empty_transfer_raises(self):
        with self.assertRaises(AlignmentSpecError):
            self._MakeValid(TransferFunction='')

    # directive: transcode-flow-canonical
    def test_empty_matrix_raises(self):
        with self.assertRaises(AlignmentSpecError):
            self._MakeValid(ColorMatrix='')

    # directive: transcode-flow-canonical
    def test_empty_range_raises(self):
        with self.assertRaises(AlignmentSpecError):
            self._MakeValid(ColorRange='')

    # directive: transcode-flow-canonical
    def test_zero_source_fps_raises(self):
        with self.assertRaises(AlignmentSpecError):
            self._MakeValid(SourceFps=0.0)

    # directive: transcode-flow-canonical
    def test_negative_target_fps_raises(self):
        with self.assertRaises(AlignmentSpecError):
            self._MakeValid(TargetFps=-1.0)

    # directive: transcode-flow-canonical
    def test_bad_bit_depth_raises(self):
        with self.assertRaises(AlignmentSpecError):
            self._MakeValid(SourceBitDepth=9)
        with self.assertRaises(AlignmentSpecError):
            self._MakeValid(TargetBitDepth=16)

    # directive: transcode-flow-canonical
    def test_zero_max_edge_raises(self):
        with self.assertRaises(AlignmentSpecError):
            self._MakeValid(MaxEdgePx=0)

    # directive: transcode-flow-canonical
    def test_duration_parity_within_two_frames_passes(self):
        FrameSec = 1.0 / 23.976
        Spec = self._MakeValid(SourceDurationSec=100.0, EncodedDurationSec=100.0 + FrameSec * 1.5)
        self.assertIsNotNone(Spec)

    # directive: transcode-flow-canonical
    def test_duration_parity_over_two_frames_raises(self):
        FrameSec = 1.0 / 23.976
        with self.assertRaises(AlignmentSpecError):
            self._MakeValid(SourceDurationSec=100.0, EncodedDurationSec=100.0 + FrameSec * 3.0)

    # directive: transcode-flow-canonical
    def test_zero_source_duration_raises(self):
        with self.assertRaises(AlignmentSpecError):
            self._MakeValid(SourceDurationSec=0.0)

    # directive: transcode-flow-canonical
    def test_invalid_resolution_raises(self):
        with self.assertRaises(AlignmentSpecError):
            self._MakeValid(TargetResolution=(0, 1080))


if __name__ == '__main__':
    unittest.main()
