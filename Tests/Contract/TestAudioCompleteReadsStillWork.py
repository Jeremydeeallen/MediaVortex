# directive: audio-vertical-dialog-boost-enforcement | # see audio-vertical-dialog-boost-enforcement.S3
import unittest

from Core.Database.DatabaseService import DatabaseService
from Models.MediaFileModel import MediaFileModel
from Features.MediaFiles.MediaFilesRepository import MediaFilesRepository, _FULL_SELECT_COLS
from Features.AudioNormalization.Services.AudioStateService import AudioStateService


class TestAudioCompleteReadsStillWork(unittest.TestCase):

    def test_media_file_model_carries_audio_complete_field(self):
        Mf = MediaFileModel()
        self.assertTrue(hasattr(Mf, 'AudioComplete'))

    def test_media_file_model_carries_has_dialog_boost_track_field(self):
        Mf = MediaFileModel()
        self.assertTrue(hasattr(Mf, 'HasDialogBoostTrack'))

    def test_full_select_includes_audio_complete_and_has_dialog_boost_track(self):
        self.assertIn('AudioComplete', _FULL_SELECT_COLS)
        self.assertIn('HasDialogBoostTrack', _FULL_SELECT_COLS)

    def test_mark_audio_complete_method_still_present(self):
        self.assertTrue(callable(getattr(AudioStateService, 'MarkAudioComplete', None)))

    def test_audio_complete_column_readable(self):
        Rows = DatabaseService().ExecuteQuery(
            "SELECT AudioComplete, HasDialogBoostTrack FROM MediaFiles LIMIT 1"
        )
        if Rows:
            R = Rows[0]
            self.assertIn('audiocomplete', {K.lower() for K in R.keys()})
            self.assertIn('hasdialogboosttrack', {K.lower() for K in R.keys()})


if __name__ == '__main__':
    unittest.main()
