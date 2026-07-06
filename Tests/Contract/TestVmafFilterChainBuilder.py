# directive: transcode-flow-canonical
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from Features.QualityTesting.Vmaf.AlignmentSpec import AlignmentSpec
from Features.QualityTesting.Vmaf.VmafFilterChainBuilder import VmafFilterChainBuilder
from Features.QualityTesting.Vmaf.VmafModelSelector import VmafModel


# directive: transcode-flow-canonical
class TestVmafFilterChainBuilder(unittest.TestCase):

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
    def test_baseline_chain_shape(self):
        Spec = self._MakeSpec()
        Chain = VmafFilterChainBuilder.Build(Spec, VmafModel.Default, "vmaf_output.xml")
        self.assertIn("[0:v]", Chain)
        self.assertIn("[dist]", Chain)
        self.assertIn("[1:v]", Chain)
        self.assertIn("[ref]", Chain)
        self.assertIn("[dist][ref]libvmaf=", Chain)

    # directive: transcode-flow-canonical
    def test_setpts_first_stage(self):
        Spec = self._MakeSpec()
        Chain = VmafFilterChainBuilder.BuildPerBranchChain(Spec)
        self.assertTrue(Chain.startswith("setpts=PTS-STARTPTS"))

    # directive: transcode-flow-canonical
    def test_deinterlace_omitted_when_not_needed(self):
        Spec = self._MakeSpec(DeinterlaceNeeded=False)
        Chain = VmafFilterChainBuilder.BuildPerBranchChain(Spec)
        self.assertNotIn("yadif", Chain)

    # directive: transcode-flow-canonical
    def test_deinterlace_applied_when_needed(self):
        Spec = self._MakeSpec(DeinterlaceNeeded=True)
        Chain = VmafFilterChainBuilder.BuildPerBranchChain(Spec)
        self.assertIn("yadif=1", Chain)

    # directive: transcode-flow-canonical
    def test_detelecine_omitted_when_not_needed(self):
        Spec = self._MakeSpec(DetelecineNeeded=False)
        Chain = VmafFilterChainBuilder.BuildPerBranchChain(Spec)
        self.assertNotIn("fieldmatch", Chain)

    # directive: transcode-flow-canonical
    def test_detelecine_applied_when_needed(self):
        Spec = self._MakeSpec(DetelecineNeeded=True)
        Chain = VmafFilterChainBuilder.BuildPerBranchChain(Spec)
        self.assertIn("fieldmatch,decimate", Chain)

    # directive: transcode-flow-canonical
    def test_fps_pins_target_fps(self):
        Spec = self._MakeSpec(TargetFps=29.97)
        Chain = VmafFilterChainBuilder.BuildPerBranchChain(Spec)
        self.assertIn("fps=29.97", Chain)

    # directive: transcode-flow-canonical
    def test_colorspace_pins_range(self):
        Tv = self._MakeSpec(ColorRange='tv')
        Pc = self._MakeSpec(ColorRange='pc')
        TvChain = VmafFilterChainBuilder.BuildPerBranchChain(Tv)
        PcChain = VmafFilterChainBuilder.BuildPerBranchChain(Pc)
        self.assertIn("out_range=tv", TvChain)
        self.assertIn("out_range=pc", PcChain)

    # directive: transcode-flow-canonical
    def test_crop_applied_when_encoded_crop_set(self):
        Spec = self._MakeSpec(EncodedCrop=(0, 138, 1920, 804))
        Chain = VmafFilterChainBuilder.BuildPerBranchChain(Spec)
        self.assertIn("crop=1920:804:0:138", Chain)

    # directive: transcode-flow-canonical
    def test_crop_omitted_when_none(self):
        Spec = self._MakeSpec(EncodedCrop=None)
        Chain = VmafFilterChainBuilder.BuildPerBranchChain(Spec)
        self.assertNotIn("crop=", Chain)

    # directive: transcode-flow-canonical
    def test_scale_pins_target_resolution_lanczos(self):
        Spec = self._MakeSpec(TargetResolution=(1280, 720))
        Chain = VmafFilterChainBuilder.BuildPerBranchChain(Spec)
        self.assertIn("scale=1280:720:flags=lanczos", Chain)

    # directive: transcode-flow-canonical
    def test_chroma_420_8bit(self):
        Spec = self._MakeSpec(ChromaSubsampling='4:2:0', TargetBitDepth=8)
        Chain = VmafFilterChainBuilder.BuildPerBranchChain(Spec)
        self.assertIn("format=yuv420p", Chain)
        self.assertNotIn("yuv420p10le", Chain)

    # directive: transcode-flow-canonical
    def test_chroma_420_10bit(self):
        Spec = self._MakeSpec(ChromaSubsampling='4:2:0', TargetBitDepth=10, SourceBitDepth=10)
        Chain = VmafFilterChainBuilder.BuildPerBranchChain(Spec)
        self.assertIn("format=yuv420p10le", Chain)

    # directive: transcode-flow-canonical
    def test_chroma_422_10bit(self):
        Spec = self._MakeSpec(ChromaSubsampling='4:2:2', TargetBitDepth=10, SourceBitDepth=10)
        Chain = VmafFilterChainBuilder.BuildPerBranchChain(Spec)
        self.assertIn("format=yuv422p10le", Chain)

    # directive: transcode-flow-canonical
    def test_chroma_444_8bit(self):
        Spec = self._MakeSpec(ChromaSubsampling='4:4:4', TargetBitDepth=8)
        Chain = VmafFilterChainBuilder.BuildPerBranchChain(Spec)
        self.assertIn("format=yuv444p", Chain)

    # directive: transcode-flow-canonical
    def test_libvmaf_model_injected(self):
        Spec = self._MakeSpec()
        Chain = VmafFilterChainBuilder.Build(Spec, VmafModel.Model4K, "vmaf_output.xml")
        self.assertIn("model=version=vmaf_4k_v0.6.1", Chain)

    # directive: transcode-flow-canonical
    def test_libvmaf_xml_log_path_injected(self):
        Spec = self._MakeSpec()
        Chain = VmafFilterChainBuilder.Build(Spec, VmafModel.Default, "custom_log.xml")
        self.assertIn("log_path=custom_log.xml", Chain)
        self.assertIn("log_fmt=xml", Chain)

    # directive: transcode-flow-canonical
    def test_libvmaf_n_threads_injected(self):
        Spec = self._MakeSpec()
        Chain = VmafFilterChainBuilder.Build(Spec, VmafModel.Default, "vmaf.xml", NThreads=8)
        self.assertIn("n_threads=8", Chain)

    # directive: transcode-flow-canonical
    def test_stage_order_setpts_then_fps_then_scale(self):
        Spec = self._MakeSpec()
        Chain = VmafFilterChainBuilder.BuildPerBranchChain(Spec)
        SetptsIdx = Chain.index("setpts=")
        FpsIdx = Chain.index("fps=")
        ScaleIdx = Chain.index("scale=1920:1080")
        self.assertLess(SetptsIdx, FpsIdx)
        self.assertLess(FpsIdx, ScaleIdx)

    # directive: transcode-flow-canonical
    def test_stage_order_crop_before_scale(self):
        Spec = self._MakeSpec(EncodedCrop=(0, 138, 1920, 804))
        Chain = VmafFilterChainBuilder.BuildPerBranchChain(Spec)
        CropIdx = Chain.index("crop=")
        ScaleIdx = Chain.index("scale=1920:1080")
        self.assertLess(CropIdx, ScaleIdx)

    # directive: transcode-flow-canonical
    def test_stage_order_deinterlace_before_detelecine_before_fps(self):
        Spec = self._MakeSpec(DeinterlaceNeeded=True, DetelecineNeeded=True)
        Chain = VmafFilterChainBuilder.BuildPerBranchChain(Spec)
        DeintIdx = Chain.index("yadif")
        DetelIdx = Chain.index("fieldmatch")
        FpsIdx = Chain.index("fps=")
        self.assertLess(DeintIdx, DetelIdx)
        self.assertLess(DetelIdx, FpsIdx)

    # directive: transcode-flow-canonical
    def test_build_rejects_empty_xml_log_path(self):
        Spec = self._MakeSpec()
        with self.assertRaises(ValueError):
            VmafFilterChainBuilder.Build(Spec, VmafModel.Default, "")

    # directive: transcode-flow-canonical
    def test_build_rejects_non_positive_n_threads(self):
        Spec = self._MakeSpec()
        with self.assertRaises(ValueError):
            VmafFilterChainBuilder.Build(Spec, VmafModel.Default, "vmaf.xml", NThreads=0)

    # directive: transcode-flow-canonical
    def test_both_branches_get_identical_per_branch_chain(self):
        Spec = self._MakeSpec()
        Full = VmafFilterChainBuilder.Build(Spec, VmafModel.Default, "vmaf.xml")
        DistPart = Full[Full.index("[0:v]") + len("[0:v]"):Full.index("[dist]")]
        RefPart = Full[Full.index("[1:v]") + len("[1:v]"):Full.index("[ref]")]
        self.assertEqual(DistPart, RefPart)


if __name__ == '__main__':
    unittest.main()
