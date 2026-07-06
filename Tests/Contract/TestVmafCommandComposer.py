# directive: transcode-flow-canonical
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from Features.QualityTesting.Vmaf.AlignmentSpec import AlignmentSpec
from Features.QualityTesting.Vmaf.VmafCommandComposer import VmafCommandComposer
from Features.QualityTesting.Vmaf.VmafModelSelector import VmafModel


# directive: transcode-flow-canonical
class TestVmafCommandComposer(unittest.TestCase):

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
    def test_argv_starts_with_ffmpeg_path(self):
        Spec = self._MakeSpec()
        Argv = VmafCommandComposer.Build(
            FFmpegPath="/usr/bin/ffmpeg",
            DistortedPath="/tmp/enc.mp4",
            ReferencePath="/tmp/src.mkv",
            Spec=Spec,
            XmlLogPath="vmaf.xml",
        )
        self.assertEqual(Argv[0], "/usr/bin/ffmpeg")

    # directive: transcode-flow-canonical
    def test_argv_input_order_distorted_first(self):
        Spec = self._MakeSpec()
        Argv = VmafCommandComposer.Build(
            FFmpegPath="ffmpeg",
            DistortedPath="/tmp/enc.mp4",
            ReferencePath="/tmp/src.mkv",
            Spec=Spec,
            XmlLogPath="vmaf.xml",
        )
        InputFlags = [I for I, A in enumerate(Argv) if A == "-i"]
        self.assertEqual(len(InputFlags), 2)
        self.assertEqual(Argv[InputFlags[0] + 1], "/tmp/enc.mp4")
        self.assertEqual(Argv[InputFlags[1] + 1], "/tmp/src.mkv")

    # directive: transcode-flow-canonical
    def test_argv_ends_with_null_output(self):
        Spec = self._MakeSpec()
        Argv = VmafCommandComposer.Build(
            FFmpegPath="ffmpeg",
            DistortedPath="e.mp4",
            ReferencePath="s.mkv",
            Spec=Spec,
            XmlLogPath="vmaf.xml",
        )
        self.assertEqual(Argv[-3:], ["-f", "null", "-"])

    # directive: transcode-flow-canonical
    def test_argv_carries_lavfi_with_filter_chain(self):
        Spec = self._MakeSpec()
        Argv = VmafCommandComposer.Build(
            FFmpegPath="ffmpeg",
            DistortedPath="e.mp4",
            ReferencePath="s.mkv",
            Spec=Spec,
            XmlLogPath="vmaf.xml",
        )
        LavfiIdx = Argv.index("-lavfi")
        Chain = Argv[LavfiIdx + 1]
        self.assertIn("[0:v]", Chain)
        self.assertIn("[dist][ref]libvmaf=", Chain)

    # directive: transcode-flow-canonical
    def test_start_time_injects_ss_before_first_input(self):
        Spec = self._MakeSpec()
        Argv = VmafCommandComposer.Build(
            FFmpegPath="ffmpeg",
            DistortedPath="e.mp4",
            ReferencePath="s.mkv",
            Spec=Spec,
            XmlLogPath="vmaf.xml",
            StartTime="00:00:30",
        )
        SsIdx = Argv.index("-ss")
        FirstIIdx = Argv.index("-i")
        self.assertLess(SsIdx, FirstIIdx)
        self.assertEqual(Argv[SsIdx + 1], "00:00:30")

    # directive: transcode-flow-canonical
    def test_no_start_time_omits_ss(self):
        Spec = self._MakeSpec()
        Argv = VmafCommandComposer.Build(
            FFmpegPath="ffmpeg",
            DistortedPath="e.mp4",
            ReferencePath="s.mkv",
            Spec=Spec,
            XmlLogPath="vmaf.xml",
        )
        self.assertNotIn("-ss", Argv)

    # directive: transcode-flow-canonical
    def test_auto_model_selection_from_spec(self):
        Spec = self._MakeSpec(TargetResolution=(3840, 2160), MaxEdgePx=3840)
        Argv = VmafCommandComposer.Build(
            FFmpegPath="ffmpeg",
            DistortedPath="e.mp4",
            ReferencePath="s.mkv",
            Spec=Spec,
            XmlLogPath="vmaf.xml",
        )
        Chain = Argv[Argv.index("-lavfi") + 1]
        self.assertIn("vmaf_4k_v0.6.1", Chain)

    # directive: transcode-flow-canonical
    def test_explicit_model_override(self):
        Spec = self._MakeSpec()
        Argv = VmafCommandComposer.Build(
            FFmpegPath="ffmpeg",
            DistortedPath="e.mp4",
            ReferencePath="s.mkv",
            Spec=Spec,
            XmlLogPath="vmaf.xml",
            Model=VmafModel.Phone,
        )
        Chain = Argv[Argv.index("-lavfi") + 1]
        self.assertIn("vmaf_v0.6.1_phone", Chain)

    # directive: transcode-flow-canonical
    def test_n_threads_carries_through(self):
        Spec = self._MakeSpec()
        Argv = VmafCommandComposer.Build(
            FFmpegPath="ffmpeg",
            DistortedPath="e.mp4",
            ReferencePath="s.mkv",
            Spec=Spec,
            XmlLogPath="vmaf.xml",
            NThreads=12,
        )
        Chain = Argv[Argv.index("-lavfi") + 1]
        self.assertIn("n_threads=12", Chain)

    # directive: transcode-flow-canonical
    def test_xml_log_path_carries_through(self):
        Spec = self._MakeSpec()
        Argv = VmafCommandComposer.Build(
            FFmpegPath="ffmpeg",
            DistortedPath="e.mp4",
            ReferencePath="s.mkv",
            Spec=Spec,
            XmlLogPath="/var/log/vmaf_run.xml",
        )
        Chain = Argv[Argv.index("-lavfi") + 1]
        self.assertIn("log_path=/var/log/vmaf_run.xml", Chain)

    # directive: transcode-flow-canonical
    def test_rejects_empty_ffmpeg_path(self):
        Spec = self._MakeSpec()
        with self.assertRaises(ValueError):
            VmafCommandComposer.Build(
                FFmpegPath="",
                DistortedPath="e.mp4",
                ReferencePath="s.mkv",
                Spec=Spec,
                XmlLogPath="vmaf.xml",
            )

    # directive: transcode-flow-canonical
    def test_rejects_empty_distorted_path(self):
        Spec = self._MakeSpec()
        with self.assertRaises(ValueError):
            VmafCommandComposer.Build(
                FFmpegPath="ffmpeg",
                DistortedPath="",
                ReferencePath="s.mkv",
                Spec=Spec,
                XmlLogPath="vmaf.xml",
            )

    # directive: transcode-flow-canonical
    def test_rejects_empty_reference_path(self):
        Spec = self._MakeSpec()
        with self.assertRaises(ValueError):
            VmafCommandComposer.Build(
                FFmpegPath="ffmpeg",
                DistortedPath="e.mp4",
                ReferencePath="",
                Spec=Spec,
                XmlLogPath="vmaf.xml",
            )

    # directive: transcode-flow-canonical
    def test_rejects_empty_xml_log_path(self):
        Spec = self._MakeSpec()
        with self.assertRaises(ValueError):
            VmafCommandComposer.Build(
                FFmpegPath="ffmpeg",
                DistortedPath="e.mp4",
                ReferencePath="s.mkv",
                Spec=Spec,
                XmlLogPath="",
            )


if __name__ == '__main__':
    unittest.main()
