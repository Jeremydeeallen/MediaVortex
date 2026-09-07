# directive: bug-0093-preencode-fail-loud-via-d13
import os
import sys
import unittest
from unittest.mock import MagicMock, patch
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

from Features.AudioNormalization.Services.DemucsDaemonClient import DemucsDaemonUnavailableError
from Features.TranscodeJob.Worker.JobProcessor import JobProcessor
from Features.TranscodeJob.Worker.JobResult import JobResult


def _MakeJob(Id=8001, ProcessingMode='Transcode', ParentAttemptId=None):
    Job = MagicMock()
    Job.Id = Id
    Job.ProcessingMode = ProcessingMode
    Job.StorageRootId = 1
    Job.RelativePath = 'Show/Season 1/Show - S01E01.mkv'
    Job.ParentTranscodeAttemptId = ParentAttemptId
    return Job


def _MakeMediaFile(Id=9001, AudioCompliant=False):
    Mf = MagicMock()
    Mf.Id = Id
    Mf.AudioCompliant = AudioCompliant
    return Mf


def _MakeQueueService(FfmpegPath='/opt/ffmpeg'):
    Qs = MagicMock()
    Qs.WorkerName = 'test-worker'
    Qs.FFmpegPath = FfmpegPath
    Qs.FFprobePath = FfmpegPath.replace('ffmpeg', 'ffprobe')
    Qs.ActiveJobRepository.CreateActiveJob.return_value = 7777
    Qs.CreateTranscodeAttempt.return_value = 6666
    Qs.SetupFilePreparation.return_value = '/local/scratch/input.mkv'
    Qs.SystemSettingsRepository.GetSystemSetting.return_value = 'error'
    Qs._LastSetupError = None
    Qs._VerifyInProgressFile.return_value = True
    Qs._DeleteInProgressFile.return_value = None
    Qs._ResolveTfpPathParts.return_value = (1, 'srcRel', 2, 'outRel')
    Qs.PrivateCreateTemporaryFilePathRecord.return_value = 5555
    Qs.DatabaseManager = MagicMock()
    Qs.DatabaseManager.DatabaseService = MagicMock()
    Qs._GetLocalStagingPathsIfActive.return_value = (None, None)
    return Qs


def _MakeStrategy():
    S = MagicMock()
    Cmd = MagicMock()
    Cmd.Command = 'ffmpeg -i x -c:v av1_nvenc -c:a copy -map 0 out.mp4.inprogress'
    Cmd.OutputPath = '/local/scratch/input-mv.mp4.inprogress'
    Cmd.VideoSlotStrategy = 'nvenc_av1'
    S.BuildCommand.return_value = Cmd
    S.HandleResult.return_value = None
    return S


def _MakeRegistry(Strategy):
    R = MagicMock()
    R.Get.return_value = Strategy
    return R


class _StubPlan:
    def __init__(self):
        self.VideoOp = 'Reencode'
        self.AudioOp = 'Reencode'
        self.SubtitleOp = 'Preserve'
        self.ContainerOp = 'Mp4'

    def WithSlotForcedToCopy(self, Side):
        Out = _StubPlan()
        if Side == 'AudioSlot':
            Out.AudioOp = 'Copy'
        elif Side == 'VideoSlot':
            Out.VideoOp = 'Copy'
        return Out


def _CommonPatchers():
    return [
        patch('Features.TranscodeJob.Worker.JobProcessor.Path'),
        patch('Features.TranscodeJob.Worker.JobProcessor.Worker'),
        patch('Features.TranscodeJob.Worker.JobProcessor.LocalExists', return_value=True),
        patch('Features.TranscodeJob.Worker.JobProcessor.LocalBasename', return_value='input.mkv'),
        patch('Features.TranscodeJob.Worker.JobProcessor.LocalDirname', return_value='/local/scratch'),
        patch('Features.TranscodeJob.Worker.JobProcessor.LocalSplitExt', return_value=('input', '.mkv')),
        patch('Features.TranscodeJob.Worker.JobProcessor.LocalJoin', side_effect=lambda a, b: f"{a}/{b}"),
        patch('Features.TranscodeJob.Worker.JobProcessor.OutputFilenameBuilder'),
        patch('Features.TranscodeJob.Worker.JobProcessor.WorkerContext'),
        patch('Features.TranscodeJob.Worker.JobProcessor.PlanFactory'),
    ]


class TestJobProcessorPreEncodeFailureRoutesToD13(unittest.TestCase):

    def setUp(self):
        self.Patchers = _CommonPatchers()
        self.Mocks = [P.start() for P in self.Patchers]
        self.addCleanup(lambda: [P.stop() for P in self.Patchers])
        self.Mocks[-1].return_value.FromComplianceState.return_value = _StubPlan()

    def test_pre_encode_raise_routes_via_D13_success_path(self):
        Qs = _MakeQueueService()
        Qs.ExecuteTranscoding.return_value = {'Success': True, 'ErrorMessage': None}
        Strategy = _MakeStrategy()
        Jp = JobProcessor(QueueService=Qs, Registry=_MakeRegistry(Strategy))
        with patch.object(Jp, '_RunPreEncodeAudio', side_effect=DemucsDaemonUnavailableError('Demucs daemon closed stdout unexpectedly')):
            with patch.object(Jp, '_PreCommitPartialDisposition') as MockPreCommit:
                with patch.object(Jp, '_EnqueuePartialFollowup') as MockEnqueue:
                    with patch('Features.AudioNormalization.Services.AudioPreEncodeFacade.PersistSourceLoudness'):
                        with patch('Features.AudioNormalization.Services.AudioPreEncodeFacade.PersistMeta'):
                            with patch('Features.AudioNormalization.Services.AudioPreEncodeFacade.Cleanup'):
                                Result = Jp.Process(_MakeJob(), _MakeMediaFile())
        self.assertIsInstance(Result, JobResult)
        self.assertTrue(Result.Success, f"Expected Success=True on pre-encode fail + fallback pass, got {Result}")
        MockPreCommit.assert_called_once()
        self.assertEqual(MockPreCommit.call_args[0][1], 'AudioSlot')
        MockEnqueue.assert_called_once()
        Strategy.HandleResult.assert_called_once()
        self.assertEqual(Qs.ExecuteTranscoding.call_count, 1, "Pre-encode failure path must invoke ffmpeg exactly once (fallback only)")

    def test_pre_encode_raise_then_fallback_ffmpeg_also_fails_lands_failure(self):
        Qs = _MakeQueueService()
        Qs.ExecuteTranscoding.return_value = {'Success': False, 'ErrorMessage': 'fallback ffmpeg exit 234'}
        Strategy = _MakeStrategy()
        Jp = JobProcessor(QueueService=Qs, Registry=_MakeRegistry(Strategy))
        with patch.object(Jp, '_RunPreEncodeAudio', side_effect=DemucsDaemonUnavailableError('Demucs daemon response timeout after 1800s')):
            with patch.object(Jp, '_PreCommitPartialDisposition') as MockPreCommit:
                with patch.object(Jp, '_EnqueuePartialFollowup') as MockEnqueue:
                    with patch('Features.AudioNormalization.Services.AudioPreEncodeFacade.PersistSourceLoudness'):
                        with patch('Features.AudioNormalization.Services.AudioPreEncodeFacade.Cleanup'):
                            Result = Jp.Process(_MakeJob(), _MakeMediaFile())
        self.assertFalse(Result.Success)
        self.assertIn('Pre-encode', Result.ErrorMessage or '')
        MockPreCommit.assert_not_called()
        MockEnqueue.assert_not_called()
        self.assertEqual(Qs.ExecuteTranscoding.call_count, 1, "Pre-encode failure must not attempt a second (VideoSlot=Copy) fallback")
        Qs.HandleJobFailure.assert_called_once()

    def test_normal_success_path_unaffected_by_pre_encode_wrapping(self):
        Qs = _MakeQueueService()
        Qs.ExecuteTranscoding.return_value = {'Success': True, 'ErrorMessage': None}
        Strategy = _MakeStrategy()
        Jp = JobProcessor(QueueService=Qs, Registry=_MakeRegistry(Strategy))
        PreAudio = {
            'DemucsPremixPath': '/scratch/premix.wav', 'VocalsRmsDbfs': -18.0,
            'PremixMeasuredI': -20.0, 'PremixMeasuredLra': 5.0, 'PremixMeasuredTp': -5.0, 'PremixMeasuredThresh': -30.0,
            'SourceMeasuredI': -23.0, 'SourceMeasuredLra': 7.0, 'SourceMeasuredTp': -1.0, 'SourceMeasuredThresh': -34.0,
            'ScratchDir': '/scratch/mv_audio_8001',
        }
        with patch.object(Jp, '_RunPreEncodeAudio', return_value=PreAudio):
            with patch.object(Jp, '_PreCommitPartialDisposition') as MockPreCommit:
                with patch.object(Jp, '_EnqueuePartialFollowup') as MockEnqueue:
                    with patch('Features.AudioNormalization.Services.AudioPreEncodeFacade.PersistSourceLoudness'):
                        with patch('Features.AudioNormalization.Services.AudioPreEncodeFacade.PersistMeta'):
                            with patch('Features.AudioNormalization.Services.AudioPreEncodeFacade.Cleanup'):
                                Result = Jp.Process(_MakeJob(), _MakeMediaFile())
        self.assertTrue(Result.Success)
        MockPreCommit.assert_not_called()
        MockEnqueue.assert_not_called()
        Ctx = Strategy.BuildCommand.call_args.kwargs['Context']
        self.assertEqual(Ctx['DemucsPremixPath'], '/scratch/premix.wav')
        self.assertEqual(Ctx['VocalsRmsDbfs'], -18.0)


class TestFileReplacementGateBypassOnPartialSuccess(unittest.TestCase):

    def _RunProcessFileReplacement(self, DispositionReason):
        from Features.FileReplacement.FileReplacementBusinessService import FileReplacementBusinessService
        Svc = FileReplacementBusinessService()
        Svc._WorkerName = 'test-worker'
        Svc.DatabaseManager = MagicMock()
        Svc.FileManager = MagicMock()
        Svc.FileManager.ValidateFileExists.return_value = True

        DispositionRow = {
            'Disposition': 'Replace',
            'DispositionReason': DispositionReason,
            'FileReplaced': False, 'FileReplacedDate': None,
            'NewSizeBytes': 100_000, 'OldSizeBytes': 200_000, 'VMAF': 85.0,
            'ProfileName': 'nvenc-fast-720p',
        }
        TfpRow = {
            'SourceStorageRootId': 1, 'SourceRelativePath': 'in.mkv',
            'OutputStorageRootId': 1, 'OutputRelativePath': 'in-mv.mp4',
        }
        MfRow = {'Id': 9999}
        Svc.DatabaseManager.DatabaseService.ExecuteQuery.side_effect = [
            [DispositionRow], [TfpRow], [MfRow],
        ]

        TranscodeAttempt = MagicMock()
        TranscodeAttempt.ProcessingMode = 'Transcode'
        TranscodeAttempt.OldSizeBytes = 200_000
        TranscodeAttempt.NewSizeBytes = 100_000
        TranscodeAttempt.FfpmpegCommand = 'ffmpeg -i x -c:v av1_nvenc -c:a copy out.mp4'
        Svc.DatabaseManager.GetTranscodeAttemptById.return_value = TranscodeAttempt

        with patch('Features.FileReplacement.FileReplacementBusinessService.Path') as MockPath:
            MockPath.return_value.CanonicalDisplay.return_value = 'T:\\test\\in.mkv'
            MockPath.return_value.Resolve.return_value = '/local/in-mv.mp4'
            with patch.object(Svc, '_GetWorker', return_value=None):
                with patch.object(Svc, '_GetPrefixMap', return_value={}):
                    with patch.object(Svc, '_ArchiveOriginalFileDetails'):
                        with patch('Features.FileReplacement.TranscodedOutputPlacement.TranscodedOutputPlacement') as MockPlacement:
                            Instance = MockPlacement.return_value
                            Instance.Execute.return_value = {'Success': False, 'ErrorMessage': 'test-stop'}
                            Svc.ProcessFileReplacement(TranscodeAttemptId=6666)
                            return Instance

    def test_partial_success_audio_slot_copied_bypasses_gate(self):
        Instance = self._RunProcessFileReplacement('PartialSuccess_AudioSlotCopied')
        Instance.Execute.assert_called_once()
        self.assertEqual(Instance.Execute.call_args.kwargs.get('RunComplianceGate'), False,
                         "PartialSuccess_AudioSlotCopied must bypass ComplianceGate")

    def test_partial_success_video_slot_copied_bypasses_gate(self):
        Instance = self._RunProcessFileReplacement('PartialSuccess_VideoSlotCopied')
        Instance.Execute.assert_called_once()
        self.assertEqual(Instance.Execute.call_args.kwargs.get('RunComplianceGate'), False)

    def test_normal_replace_disposition_runs_gate(self):
        Instance = self._RunProcessFileReplacement('VmafAutoReplace')
        Instance.Execute.assert_called_once()
        self.assertEqual(Instance.Execute.call_args.kwargs.get('RunComplianceGate'), True,
                         "Non-partial Replace disposition (Transcode mode) must run ComplianceGate")

    def test_partial_retry_exhausted_does_not_bypass(self):
        Instance = self._RunProcessFileReplacement('PartialRetryExhausted')
        Instance.Execute.assert_called_once()
        self.assertEqual(Instance.Execute.call_args.kwargs.get('RunComplianceGate'), True,
                         "'PartialRetryExhausted' must NOT match the PartialSuccess_ bypass predicate")


if __name__ == '__main__':
    unittest.main()
