# directive: transcode-flow-canonical
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from Features.QualityTesting.Vmaf.AlignmentSpec import AlignmentSpec
from Features.QualityTesting.Vmaf.VmafModelSelector import VmafModelSelector, VmafModel


# directive: transcode-flow-canonical
class TestVmafModelSelector(unittest.TestCase):

    # directive: transcode-flow-canonical
    def _MakeSpec(self, **Overrides) -> AlignmentSpec:
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
    def test_max_edge_ge_1440_selects_4k_model(self):
        Spec = self._MakeSpec(TargetResolution=(3840, 2160), MaxEdgePx=3840)
        self.assertEqual(VmafModelSelector.Select(Spec), VmafModel.Model4K)

    # directive: transcode-flow-canonical
    def test_max_edge_1440_boundary_selects_4k(self):
        Spec = self._MakeSpec(TargetResolution=(2560, 1440), MaxEdgePx=2560)
        self.assertEqual(VmafModelSelector.Select(Spec), VmafModel.Model4K)

    # directive: transcode-flow-canonical
    def test_max_edge_le_540_selects_phone_model(self):
        Spec = self._MakeSpec(TargetResolution=(540, 960), MaxEdgePx=960)
        Spec2 = self._MakeSpec(TargetResolution=(540, 480), MaxEdgePx=540)
        self.assertEqual(VmafModelSelector.Select(Spec2), VmafModel.Phone)

    # directive: transcode-flow-canonical
    def test_hdr_flag_selects_neg_model(self):
        Spec = self._MakeSpec(
            ColorPrimaries='bt2020',
            TransferFunction='smpte2084',
            HdrDetected=True,
            TargetResolution=(1280, 720),
            MaxEdgePx=1280,
            TargetBitDepth=10,
            SourceBitDepth=10,
        )
        self.assertEqual(VmafModelSelector.Select(Spec), VmafModel.Neg)

    # directive: transcode-flow-canonical
    def test_1080p_max_edge_1920_selects_4k(self):
        Spec = self._MakeSpec()
        self.assertEqual(VmafModelSelector.Select(Spec), VmafModel.Model4K)

    # directive: transcode-flow-canonical
    def test_4k_hdr_prefers_4k_model_over_neg(self):
        Spec = self._MakeSpec(
            ColorPrimaries='bt2020',
            TransferFunction='smpte2084',
            HdrDetected=True,
            TargetResolution=(3840, 2160),
            MaxEdgePx=3840,
            TargetBitDepth=10,
            SourceBitDepth=10,
        )
        self.assertEqual(VmafModelSelector.Select(Spec), VmafModel.Model4K)

    # directive: transcode-flow-canonical
    def test_phone_beats_hdr_at_540(self):
        Spec = self._MakeSpec(
            TargetResolution=(540, 480),
            MaxEdgePx=540,
            HdrDetected=True,
            ColorPrimaries='bt2020',
            TransferFunction='smpte2084',
            TargetBitDepth=10,
            SourceBitDepth=10,
        )
        self.assertEqual(VmafModelSelector.Select(Spec), VmafModel.Phone)

    # directive: transcode-flow-canonical
    def test_720p_sdr_default_model(self):
        Spec = self._MakeSpec(TargetResolution=(1280, 720), MaxEdgePx=1280)
        self.assertEqual(VmafModelSelector.Select(Spec), VmafModel.Default)


if __name__ == '__main__':
    unittest.main()
