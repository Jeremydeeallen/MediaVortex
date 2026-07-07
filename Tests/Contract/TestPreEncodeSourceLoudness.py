# directive: transcode-flow-canonical
import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from Features.AudioNormalization.Services import AudioPreEncodeFacade


# directive: transcode-flow-canonical
class TestPersistSourceLoudness(unittest.TestCase):

    # directive: transcode-flow-canonical
    def test_no_op_when_pre_audio_is_none(self):
        Mf = MagicMock()
        with patch('Core.Database.DatabaseService.DatabaseService') as MockDb:
            AudioPreEncodeFacade.PersistSourceLoudness(123, Mf, None)
        self.assertFalse(MockDb.called)

    # directive: transcode-flow-canonical
    def test_no_op_when_source_measured_i_is_missing(self):
        Mf = MagicMock()
        Pre = dict(DemucsPremixPath='x', VocalsRmsDbfs=-30)
        with patch('Core.Database.DatabaseService.DatabaseService') as MockDb:
            AudioPreEncodeFacade.PersistSourceLoudness(123, Mf, Pre)
        self.assertFalse(MockDb.called)

    # directive: transcode-flow-canonical
    def test_no_op_when_any_source_field_is_none(self):
        Mf = MagicMock()
        Pre = dict(SourceMeasuredI=-23.3, SourceMeasuredLra=None, SourceMeasuredTp=-3.8, SourceMeasuredThresh=-37.5)
        with patch('Core.Database.DatabaseService.DatabaseService') as MockDb:
            AudioPreEncodeFacade.PersistSourceLoudness(123, Mf, Pre)
        self.assertFalse(MockDb.called)

    # directive: transcode-flow-canonical
    def test_updates_db_when_all_four_fields_present(self):
        Mf = MagicMock()
        Pre = dict(SourceMeasuredI=-23.3, SourceMeasuredLra=23.3, SourceMeasuredTp=-3.8, SourceMeasuredThresh=-37.5)
        MockInstance = MagicMock()
        with patch('Core.Database.DatabaseService.DatabaseService', return_value=MockInstance):
            AudioPreEncodeFacade.PersistSourceLoudness(620351, Mf, Pre)
        self.assertTrue(MockInstance.ExecuteNonQuery.called)
        Args, _ = MockInstance.ExecuteNonQuery.call_args
        Sql = Args[0]
        Params = Args[1]
        self.assertIn('UPDATE MediaFiles', Sql)
        self.assertIn('SourceIntegratedLufs', Sql)
        self.assertIn('LoudnessMeasuredAt=NOW()', Sql)
        self.assertEqual(Params, (-23.3, 23.3, -3.8, -37.5, 620351))

    # directive: transcode-flow-canonical
    def test_updates_media_file_in_memory(self):
        class SimpleMf:
            SourceIntegratedLufs = -19.4
            SourceLoudnessRangeLU = 23.2
            SourceTruePeakDbtp = -0.3
            SourceIntegratedThresholdLufs = -33.7
        Mf = SimpleMf()
        Pre = dict(SourceMeasuredI=-23.3, SourceMeasuredLra=23.3, SourceMeasuredTp=-3.8, SourceMeasuredThresh=-37.5)
        MockInstance = MagicMock()
        with patch('Core.Database.DatabaseService.DatabaseService', return_value=MockInstance):
            AudioPreEncodeFacade.PersistSourceLoudness(620351, Mf, Pre)
        self.assertEqual(Mf.SourceIntegratedLufs, -23.3)
        self.assertEqual(Mf.SourceLoudnessRangeLU, 23.3)
        self.assertEqual(Mf.SourceTruePeakDbtp, -3.8)
        self.assertEqual(Mf.SourceIntegratedThresholdLufs, -37.5)


if __name__ == '__main__':
    unittest.main()
