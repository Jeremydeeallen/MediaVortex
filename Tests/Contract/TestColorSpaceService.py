# directive: transcode-flow-canonical
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from Core.Media.ColorSpaceService import (
    ColorSpaceService,
    ColorSpaceParseError,
    ColorPrimaries,
    TransferFunction,
    ColorMatrix,
    ColorRange,
)


# directive: transcode-flow-canonical
class TestColorSpaceServiceParse(unittest.TestCase):

    # directive: transcode-flow-canonical
    def test_parse_primaries_known_values(self):
        self.assertEqual(ColorSpaceService.ParsePrimaries('bt709'), ColorPrimaries.Bt709)
        self.assertEqual(ColorSpaceService.ParsePrimaries('BT709'), ColorPrimaries.Bt709)
        self.assertEqual(ColorSpaceService.ParsePrimaries('bt2020'), ColorPrimaries.Bt2020)
        self.assertEqual(ColorSpaceService.ParsePrimaries('smpte170m'), ColorPrimaries.Smpte170m)

    # directive: transcode-flow-canonical
    def test_parse_primaries_empty_raises(self):
        with self.assertRaises(ColorSpaceParseError):
            ColorSpaceService.ParsePrimaries('')

    # directive: transcode-flow-canonical
    def test_parse_primaries_unknown_raises(self):
        with self.assertRaises(ColorSpaceParseError):
            ColorSpaceService.ParsePrimaries('bt2100-something')

    # directive: transcode-flow-canonical
    def test_parse_transfer_known_values(self):
        self.assertEqual(ColorSpaceService.ParseTransfer('bt709'), TransferFunction.Bt709)
        self.assertEqual(ColorSpaceService.ParseTransfer('smpte2084'), TransferFunction.Smpte2084)
        self.assertEqual(ColorSpaceService.ParseTransfer('arib-std-b67'), TransferFunction.AribStdB67)

    # directive: transcode-flow-canonical
    def test_parse_transfer_unknown_raises(self):
        with self.assertRaises(ColorSpaceParseError):
            ColorSpaceService.ParseTransfer('foo')

    # directive: transcode-flow-canonical
    def test_parse_matrix_known_values(self):
        self.assertEqual(ColorSpaceService.ParseMatrix('bt709'), ColorMatrix.Bt709)
        self.assertEqual(ColorSpaceService.ParseMatrix('bt2020nc'), ColorMatrix.Bt2020Nc)

    # directive: transcode-flow-canonical
    def test_parse_matrix_unknown_raises(self):
        with self.assertRaises(ColorSpaceParseError):
            ColorSpaceService.ParseMatrix('bt-foo')

    # directive: transcode-flow-canonical
    def test_parse_range_aliases(self):
        self.assertEqual(ColorSpaceService.ParseRange('tv'), ColorRange.Tv)
        self.assertEqual(ColorSpaceService.ParseRange('limited'), ColorRange.Tv)
        self.assertEqual(ColorSpaceService.ParseRange('mpeg'), ColorRange.Tv)
        self.assertEqual(ColorSpaceService.ParseRange('pc'), ColorRange.Pc)
        self.assertEqual(ColorSpaceService.ParseRange('full'), ColorRange.Pc)

    # directive: transcode-flow-canonical
    def test_parse_range_unknown_raises(self):
        with self.assertRaises(ColorSpaceParseError):
            ColorSpaceService.ParseRange('super-full')


# directive: transcode-flow-canonical
class TestColorSpaceServiceHdrDetect(unittest.TestCase):

    # directive: transcode-flow-canonical
    def test_sdr_bt709_not_hdr(self):
        self.assertFalse(ColorSpaceService.IsHdr(ColorPrimaries.Bt709, TransferFunction.Bt709))

    # directive: transcode-flow-canonical
    def test_pq_transfer_is_hdr(self):
        self.assertTrue(ColorSpaceService.IsHdr(ColorPrimaries.Bt2020, TransferFunction.Smpte2084))

    # directive: transcode-flow-canonical
    def test_hlg_transfer_is_hdr(self):
        self.assertTrue(ColorSpaceService.IsHdr(ColorPrimaries.Bt2020, TransferFunction.AribStdB67))

    # directive: transcode-flow-canonical
    def test_bt2020_primaries_alone_is_hdr(self):
        self.assertTrue(ColorSpaceService.IsHdr(ColorPrimaries.Bt2020, TransferFunction.Bt709))


# directive: transcode-flow-canonical
class TestColorSpaceServiceToneMap(unittest.TestCase):

    # directive: transcode-flow-canonical
    def test_identity_returns_empty(self):
        self.assertEqual(
            ColorSpaceService.BuildToneMapGraph(TransferFunction.Bt709, TransferFunction.Bt709),
            "",
        )

    # directive: transcode-flow-canonical
    def test_pq_to_bt709_returns_graph(self):
        Graph = ColorSpaceService.BuildToneMapGraph(TransferFunction.Smpte2084, TransferFunction.Bt709)
        self.assertIn('tonemap', Graph)
        self.assertIn('zscale', Graph)
        self.assertIn('p=bt709', Graph)

    # directive: transcode-flow-canonical
    def test_hlg_to_bt709_returns_graph(self):
        Graph = ColorSpaceService.BuildToneMapGraph(TransferFunction.AribStdB67, TransferFunction.Bt709)
        self.assertIn('tonemap', Graph)

    # directive: transcode-flow-canonical
    def test_unsupported_pair_raises(self):
        with self.assertRaises(ColorSpaceParseError):
            ColorSpaceService.BuildToneMapGraph(TransferFunction.Bt709, TransferFunction.Smpte2084)


if __name__ == '__main__':
    unittest.main()
