# directive: label-decides-command | # see transcode.ST6
import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from Features.TranscodeJob.Emit.Slots.AudioSlot import AudioSlot
from Features.TranscodeJob.ProcessTranscodeQueueService import ProcessTranscodeQueueService
from Features.TranscodeJob.TranscodeJobRepository import TranscodeJobRepository
from Features.TranscodeJob.Worker.JobProcessor import JobProcessor


# directive: label-decides-command | # see transcode.ST6
def _Rules():
    return MagicMock(**{'GetRules.return_value': {'AcceptableAudioCodecsCsv': 'aac,ac3,eac3,mp3,opus'}})


# directive: label-decides-command | # see transcode.ST6
class TestAudioCopyStage(unittest.TestCase):

    # directive: label-decides-command | # see transcode.ST6
    def test_container_compatible_audio_is_copied(self):
        Emission = AudioSlot(RulesRepository=_Rules()).Emit('Copy', SimpleNamespace(AudioCodec='AC3'), {})
        self.assertEqual(Emission.StreamArgs, ['-map', '0:a?', '-c:a', 'copy'])

    # directive: label-decides-command | # see transcode.ST6
    def test_audio_the_container_cannot_carry_is_converted_plainly(self):
        Emission = AudioSlot(RulesRepository=_Rules()).Emit('Copy', SimpleNamespace(AudioCodec='wmav2'), {})
        self.assertEqual(Emission.StreamArgs, ['-map', '0:a?', '-c:a', 'aac'])
        self.assertEqual(Emission.InputArgs, [])


# directive: label-decides-command | # see transcode.ST6
class TestDemucsRunsOnlyForAudioStage(unittest.TestCase):

    # directive: label-decides-command | # see transcode.ST6
    def _Run(self, Mode):
        Processor = JobProcessor(QueueService=MagicMock(), Registry=MagicMock())
        with patch('Features.TranscodeJob.Worker.JobProcessor.AudioPreEncodeFacade.Prepare', return_value={'DemucsPremixPath': 'x'}) as Prepare:
            Result = Processor._RunPreEncodeAudio(SimpleNamespace(Id=1, AudioCompliant=False), 'in.mkv', SimpleNamespace(Id=7, ProcessingMode=Mode), 99)
        return Result, Prepare

    # directive: label-decides-command | # see transcode.ST6
    def test_transcode_and_remux_never_run_demucs(self):
        for Mode in ('Transcode', 'Remux'):
            Result, Prepare = self._Run(Mode)
            self.assertIsNone(Result, Mode)
            Prepare.assert_not_called()

    # directive: label-decides-command | # see transcode.ST6
    def test_audiofix_runs_demucs_even_when_flag_says_audio_is_fine(self):
        Processor = JobProcessor(QueueService=MagicMock(), Registry=MagicMock())
        with patch('Features.TranscodeJob.Worker.JobProcessor.AudioPreEncodeFacade.Prepare', return_value={'DemucsPremixPath': 'x'}) as Prepare:
            Processor._RunPreEncodeAudio(SimpleNamespace(Id=1, AudioCompliant=True), 'in.mkv', SimpleNamespace(Id=7, ProcessingMode='AudioFix'), 99)
        Prepare.assert_called_once()


# directive: label-decides-command | # see transcode.ST8
class TestVideoCopyStageVerification(unittest.TestCase):

    # directive: label-decides-command | # see transcode.ST8
    def _Handle(self, Mode, ChecksumOk, BoostEmitted):
        Service = ProcessTranscodeQueueService.__new__(ProcessTranscodeQueueService)
        Service.DatabaseManager = MagicMock()
        Service.ActiveJobRepository = MagicMock()
        Service._VerifyStreamCopyChecksum = MagicMock(return_value={
            'Success': ChecksumOk, 'Vmaf': None, 'ErrorMessage': None if ChecksumOk else 'StreamCopy checksum mismatch: source=a output=b',
        })
        Service._DeleteInProgressFile = MagicMock()
        Service.HandleJobFailure = MagicMock()
        Service.UpdateTranscodeFileRecord = MagicMock()
        Service.DispatchDisposition = MagicMock()
        Job = SimpleNamespace(Id=5, ProcessingMode=Mode, SizeBytes=1000, FilePath='T:\\x.mkv', MediaFileId=3)
        with patch('Features.AudioNormalization.Services.AudioPreEncodeFacade.WasDialogBoostEmitted', return_value=BoostEmitted):
            Service.HandleRemuxResult(Job, {'NewSizeBytes': 900, 'OutputFilePath': 'x-mv.mp4.inprogress'}, 11, 22, 'x-mv.mp4.inprogress')
        return Service

    # directive: label-decides-command | # see transcode.ST8
    def test_checksum_mismatch_fails_the_job_and_replaces_nothing(self):
        Service = self._Handle('Remux', ChecksumOk=False, BoostEmitted=False)
        Service.DispatchDisposition.assert_not_called()
        Service._DeleteInProgressFile.assert_called_once_with('x-mv.mp4.inprogress')
        Service.HandleJobFailure.assert_called_once()
        self.assertIn('checksum mismatch', Service.HandleJobFailure.call_args[0][1])

    # directive: label-decides-command | # see transcode.ST8
    def test_audiofix_without_dialog_boost_fails_the_job(self):
        Service = self._Handle('AudioFix', ChecksumOk=True, BoostEmitted=False)
        Service.DispatchDisposition.assert_not_called()
        Service._DeleteInProgressFile.assert_called_once()
        self.assertIn('no Dialog Boost', Service.HandleJobFailure.call_args[0][1])

    # directive: label-decides-command | # see transcode.ST8
    def test_audiofix_with_dialog_boost_is_recorded_successful_then_dispatched(self):
        Service = self._Handle('AudioFix', ChecksumOk=True, BoostEmitted=True)
        Service.HandleJobFailure.assert_not_called()
        self.assertIs(Service.DatabaseManager.UpdateTranscodeAttempt.call_args[0][1]['Success'], True)
        Service.DispatchDisposition.assert_called_once()

    # directive: label-decides-command | # see transcode.ST8
    def test_remux_needs_no_dialog_boost(self):
        Service = self._Handle('Remux', ChecksumOk=True, BoostEmitted=False)
        Service.HandleJobFailure.assert_not_called()
        Service.DispatchDisposition.assert_called_once()

    # directive: label-decides-command | # see transcode.ST8
    def test_failure_after_verification_still_fails_the_job(self):
        Service = ProcessTranscodeQueueService.__new__(ProcessTranscodeQueueService)
        Service.DatabaseManager = MagicMock()
        Service.ActiveJobRepository = MagicMock()
        Service._VerifyStreamCopyChecksum = MagicMock(return_value={'Success': True, 'Vmaf': None, 'ErrorMessage': None})
        Service._DeleteInProgressFile = MagicMock()
        Service.HandleJobFailure = MagicMock()
        Service.UpdateTranscodeFileRecord = MagicMock()
        Service.DispatchDisposition = MagicMock(side_effect=RuntimeError('replacement refused'))
        Job = SimpleNamespace(Id=5, ProcessingMode='Remux', SizeBytes=1000, FilePath='T:\\x.mkv', MediaFileId=3)
        Service.HandleRemuxResult(Job, {'NewSizeBytes': 900, 'OutputFilePath': 'x-mv.mp4.inprogress'}, 11, 22, 'x-mv.mp4.inprogress')
        Service.HandleJobFailure.assert_called_once()
        self.assertIn('replacement refused', Service.HandleJobFailure.call_args[0][1])


# directive: label-decides-command | # see transcode.ST8
class TestAttemptUpdateRefusesUnknownFields(unittest.TestCase):

    # directive: label-decides-command | # see transcode.ST8
    def test_unknown_field_raises_instead_of_being_dropped(self):
        Repository = TranscodeJobRepository.__new__(TranscodeJobRepository)
        Repository.DatabaseService = MagicMock()
        with self.assertRaises(ValueError):
            Repository.UpdateTranscodeAttempt(1, {'Disposition': 'Replace'})
        Repository.DatabaseService.GetConnection.assert_not_called()


if __name__ == '__main__':
    unittest.main()
