# directive: transcode-flow-canonical
import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from Features.QualityTesting.Vmaf.VmafAlignmentProbe import (
    VmafAlignmentProbe,
    VmafAlignmentProbeError,
)
from Features.QualityTesting.Vmaf.AlignmentSpec import AlignmentSpecError


# directive: transcode-flow-canonical
def _MakeProbe(FpsR='24000/1001', FpsAvg='24000/1001', Width=1920, Height=1080,
               PixFmt='yuv420p', Primaries='bt709', Transfer='bt709', Matrix='bt709',
               Range='tv', FieldOrder='progressive', Duration=100.0):
    return {
        'streams': [
            {
                'codec_type': 'video',
                'r_frame_rate': FpsR,
                'avg_frame_rate': FpsAvg,
                'width': Width,
                'height': Height,
                'pix_fmt': PixFmt,
                'color_primaries': Primaries,
                'color_transfer': Transfer,
                'color_space': Matrix,
                'color_range': Range,
                'field_order': FieldOrder,
                'duration': str(Duration),
            }
        ],
        'format': {'duration': str(Duration)},
    }


# directive: transcode-flow-canonical
class TestVmafAlignmentProbeDerive(unittest.TestCase):

    # directive: transcode-flow-canonical
    def _MakeProbeService(self, SourceProbe, EncodedProbe):
        Adapter = MagicMock()
        Adapter.ProbeStreams.side_effect = lambda P: SourceProbe if 'source' in P else EncodedProbe
        return VmafAlignmentProbe(Adapter=Adapter)

    # directive: transcode-flow-canonical
    def test_sdr_1080p_baseline(self):
        Source = _MakeProbe()
        Encoded = _MakeProbe()
        Svc = self._MakeProbeService(Source, Encoded)
        Spec = Svc.Probe('source.mkv', 'encoded.mp4')
        self.assertEqual(Spec.TargetResolution, (1920, 1080))
        self.assertEqual(Spec.MaxEdgePx, 1920)
        self.assertEqual(Spec.ColorPrimaries, 'bt709')
        self.assertEqual(Spec.SourceBitDepth, 8)
        self.assertEqual(Spec.ChromaSubsampling, '4:2:0')
        self.assertFalse(Spec.HdrDetected)
        self.assertFalse(Spec.VfrDetected)
        self.assertFalse(Spec.DeinterlaceNeeded)

    # directive: transcode-flow-canonical
    def test_hdr_pq_4k_detected(self):
        Source = _MakeProbe(Width=3840, Height=2160, PixFmt='yuv420p10le',
                            Primaries='bt2020', Transfer='smpte2084', Matrix='bt2020nc')
        Encoded = _MakeProbe(Width=3840, Height=2160, PixFmt='yuv420p10le',
                             Primaries='bt2020', Transfer='smpte2084', Matrix='bt2020nc')
        Svc = self._MakeProbeService(Source, Encoded)
        Spec = Svc.Probe('source.mkv', 'encoded.mp4')
        self.assertTrue(Spec.HdrDetected)
        self.assertEqual(Spec.MaxEdgePx, 3840)
        self.assertEqual(Spec.TargetBitDepth, 10)

    # directive: transcode-flow-canonical
    def test_vfr_detected_when_r_and_avg_differ(self):
        Source = _MakeProbe(FpsR='30000/1001', FpsAvg='23976/1000')
        Encoded = _MakeProbe()
        Svc = self._MakeProbeService(Source, Encoded)
        Spec = Svc.Probe('source.mkv', 'encoded.mp4')
        self.assertTrue(Spec.VfrDetected)

    # directive: transcode-flow-canonical
    def test_interlaced_source_flags_deinterlace(self):
        Source = _MakeProbe(FieldOrder='tt')
        Encoded = _MakeProbe()
        Svc = self._MakeProbeService(Source, Encoded)
        Spec = Svc.Probe('source.mkv', 'encoded.mp4')
        self.assertTrue(Spec.DeinterlaceNeeded)

    # directive: transcode-flow-canonical
    def test_unparseable_primaries_raises(self):
        Source = _MakeProbe(Primaries='bt2100-hdr10plus')
        Encoded = _MakeProbe()
        Svc = self._MakeProbeService(Source, Encoded)
        with self.assertRaises(Exception):
            Svc.Probe('source.mkv', 'encoded.mp4')

    # directive: transcode-flow-canonical
    def test_unparseable_fps_raises(self):
        Source = _MakeProbe(FpsR='0/1')
        Encoded = _MakeProbe()
        Svc = self._MakeProbeService(Source, Encoded)
        with self.assertRaises(VmafAlignmentProbeError):
            Svc.Probe('source.mkv', 'encoded.mp4')

    # directive: transcode-flow-canonical
    def test_duration_delta_over_one_frame_raises(self):
        FrameSec = 1001.0 / 24000.0
        Source = _MakeProbe(Duration=100.0)
        Encoded = _MakeProbe(Duration=100.0 + FrameSec * 3.0)
        Svc = self._MakeProbeService(Source, Encoded)
        with self.assertRaises(AlignmentSpecError):
            Svc.Probe('source.mkv', 'encoded.mp4')

    # directive: transcode-flow-canonical
    def test_no_video_stream_raises(self):
        Source = {'streams': [{'codec_type': 'audio'}], 'format': {'duration': '100.0'}}
        Encoded = _MakeProbe()
        Svc = self._MakeProbeService(Source, Encoded)
        with self.assertRaises(VmafAlignmentProbeError):
            Svc.Probe('source.mkv', 'encoded.mp4')

    # directive: transcode-flow-canonical
    def test_bad_pix_fmt_raises(self):
        Source = _MakeProbe(PixFmt='rgb24')
        Encoded = _MakeProbe()
        Svc = self._MakeProbeService(Source, Encoded)
        with self.assertRaises(VmafAlignmentProbeError):
            Svc.Probe('source.mkv', 'encoded.mp4')

    # directive: transcode-flow-canonical
    def test_zero_resolution_raises(self):
        Source = _MakeProbe()
        Encoded = _MakeProbe(Width=0, Height=0)
        Svc = self._MakeProbeService(Source, Encoded)
        with self.assertRaises(VmafAlignmentProbeError):
            Svc.Probe('source.mkv', 'encoded.mp4')


# directive: transcode-flow-canonical
class TestVmafAlignmentProbeToneMap(unittest.TestCase):

    # directive: transcode-flow-canonical
    def test_sdr_source_no_tonemap(self):
        Source = _MakeProbe()
        Encoded = _MakeProbe()
        Adapter = MagicMock()
        Adapter.ProbeStreams.side_effect = lambda P: Source if 'source' in P else Encoded
        Svc = VmafAlignmentProbe(Adapter=Adapter)
        Spec = Svc.Probe('source.mkv', 'encoded.mp4')
        self.assertEqual(Svc.BuildReferenceToneMap(Spec, 'bt709'), "")

    # directive: transcode-flow-canonical
    def test_hdr_source_sdr_target_returns_graph(self):
        Source = _MakeProbe(Primaries='bt2020', Transfer='smpte2084', Matrix='bt2020nc', PixFmt='yuv420p10le')
        Encoded = _MakeProbe()
        Adapter = MagicMock()
        Adapter.ProbeStreams.side_effect = lambda P: Source if 'source' in P else Encoded
        Svc = VmafAlignmentProbe(Adapter=Adapter)
        Spec = Svc.Probe('source.mkv', 'encoded.mp4')
        Graph = Svc.BuildReferenceToneMap(Spec, 'smpte2084')
        self.assertIn('tonemap', Graph)


if __name__ == '__main__':
    unittest.main()
