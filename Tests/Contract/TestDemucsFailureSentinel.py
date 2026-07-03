# directive: audio-dialog-boost-real | # see audio-normalization.C39
import json
import sys
import unittest
from pathlib import Path
from unittest.mock import patch, MagicMock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from Features.AudioNormalization.Services.PreEncodeAudioPipeline import PreEncodeAudioPipeline
from Features.AudioNormalization.Services.PostEncodeMeasurementService import PostEncodeMeasurementService
from Features.AudioNormalization.Services import AudioPreEncodeFacade


# directive: audio-dialog-boost-real | # see audio-normalization.C39
class TestDemucsFailureSentinel(unittest.TestCase):
    """C39: Demucs crash MUST persist a distinguishing signal so operator can SQL-distinguish silent Demucs crash from deliberate G5 skip."""

    # directive: audio-dialog-boost-real | # see audio-normalization.C39
    def test_pipeline_returns_failure_sentinel_when_downmix_raises(self):
        MockDemucs = MagicMock()
        MockDemucs.ModelName = 'htdemucs'
        MockDemucs.Device = 'cpu'
        Pipeline = PreEncodeAudioPipeline(FfmpegPath='/does/not/exist/ffmpeg', PythonExe='python', DemucsService=MockDemucs)
        with patch.object(Pipeline, '_ExtractStereoDownmix', side_effect=RuntimeError('stereo downmix failed (exit 1): boom')):
            Result = Pipeline.Run(SourceFilePath='/tmp/fake.mkv', JobId=99999)
        self.assertIsInstance(Result, dict)
        self.assertIs(Result['DemucsFailed'], True)
        self.assertIn('RuntimeError', Result['DemucsFailureReason'])
        self.assertIn('boom', Result['DemucsFailureReason'])
        self.assertIsNone(Result['DemucsPremixPath'])
        self.assertIsNone(Result['VocalsRmsDbfs'])

    # directive: audio-dialog-boost-real | # see audio-normalization.C39
    def test_pipeline_returns_failure_sentinel_when_demucs_isolate_raises(self):
        MockDemucs = MagicMock()
        MockDemucs.ModelName = 'htdemucs'
        MockDemucs.Device = 'cuda'
        MockDemucs.IsolateVocals.side_effect = FileNotFoundError('demucs binary not on PATH')
        Pipeline = PreEncodeAudioPipeline(FfmpegPath='/does/not/exist/ffmpeg', PythonExe='python', DemucsService=MockDemucs)
        with patch.object(Pipeline, '_ExtractStereoDownmix', return_value='/tmp/downmix.wav'):
            Result = Pipeline.Run(SourceFilePath='/tmp/fake.mkv', JobId=99998)
        self.assertIs(Result['DemucsFailed'], True)
        self.assertIn('FileNotFoundError', Result['DemucsFailureReason'])

    # directive: audio-dialog-boost-real | # see audio-normalization.C39
    def test_failure_reason_capped_at_200_chars(self):
        MockDemucs = MagicMock()
        MockDemucs.ModelName = 'htdemucs'
        MockDemucs.Device = 'cpu'
        LongMsg = 'X' * 5000
        Pipeline = PreEncodeAudioPipeline(FfmpegPath='/does/not/exist/ffmpeg', PythonExe='python', DemucsService=MockDemucs)
        with patch.object(Pipeline, '_ExtractStereoDownmix', side_effect=RuntimeError(LongMsg)):
            Result = Pipeline.Run(SourceFilePath='/tmp/fake.mkv', JobId=99997)
        Prefix = 'RuntimeError: '
        self.assertTrue(Result['DemucsFailureReason'].startswith(Prefix))
        Body = Result['DemucsFailureReason'][len(Prefix):]
        self.assertLessEqual(len(Body), 200)

    # directive: audio-dialog-boost-real | # see audio-normalization.C39
    def test_facade_persist_forwards_demucs_failure_to_measurement_service(self):
        FailureDict = {
            'DemucsPremixPath': None,
            'VocalsRmsDbfs': None,
            'ScratchDir': None,
            'DemucsFailed': True,
            'DemucsFailureReason': 'RuntimeError: stereo downmix failed',
        }
        with patch('Features.AudioNormalization.Repositories.AudioComplianceRulesRepository.AudioComplianceRulesRepository') as MockRules, \
             patch('Features.AudioNormalization.Services.PostEncodeMeasurementService.PostEncodeMeasurementService') as MockSvc:
            MockRules.return_value.GetRules.return_value = {'Track1VocalsRmsFallbackDbfs': -50.0}
            Instance = MagicMock()
            MockSvc.return_value = Instance
            AudioPreEncodeFacade.PersistMeta(TranscodeAttemptId=42, PreAudio=FailureDict)
            Instance.PersistPreEncodeMeta.assert_called_once()
            Kwargs = Instance.PersistPreEncodeMeta.call_args.kwargs
            self.assertIs(Kwargs['DemucsFailed'], True)
            self.assertIn('stereo downmix failed', Kwargs['DemucsFailureReason'])

    # directive: audio-dialog-boost-real | # see audio-normalization.C39
    def test_measurement_service_stamps_demucs_failed_on_meta_only_entry_when_no_tracks(self):
        Svc = PostEncodeMeasurementService(FFmpegPath='/usr/bin/ffmpeg', FFprobePath='/usr/bin/ffprobe')
        with patch('Features.AudioNormalization.Services.PostEncodeMeasurementService.DatabaseService') as MockDb:
            Instance = MagicMock()
            Instance.ExecuteQuery.return_value = [{'audiotracksemittedjson': None}]
            MockDb.return_value = Instance
            Ok = Svc.PersistPreEncodeMeta(
                TranscodeAttemptId=42, VocalsRmsDbfs=None, DialogBoostEmitted=False, VocalsFallbackDbfs=-50.0,
                DemucsFailed=True, DemucsFailureReason='RuntimeError: cuda oom',
            )
            self.assertTrue(Ok)
            Args = Instance.ExecuteNonQuery.call_args.args
            Parsed = json.loads(Args[1][0])
            self.assertEqual(len(Parsed), 1)
            self.assertIs(Parsed[0]['demucs_failed'], True)
            self.assertEqual(Parsed[0]['demucs_failure_reason'], 'RuntimeError: cuda oom')
            self.assertEqual(Parsed[0]['Label'], 'pre_encode_meta')

    # directive: audio-dialog-boost-real | # see audio-normalization.C39
    def test_measurement_service_stamps_demucs_failed_on_every_existing_track(self):
        Svc = PostEncodeMeasurementService(FFmpegPath='/usr/bin/ffmpeg', FFprobePath='/usr/bin/ffprobe')
        Existing = [
            {'TrackIndex': 1, 'Label': 'Original', 'AchievedIntegratedLufs': -23.0},
            {'TrackIndex': 2, 'Label': 'Dialog Boost', 'AchievedIntegratedLufs': -20.1},
        ]
        with patch('Features.AudioNormalization.Services.PostEncodeMeasurementService.DatabaseService') as MockDb:
            Instance = MagicMock()
            Instance.ExecuteQuery.return_value = [{'audiotracksemittedjson': Existing}]
            MockDb.return_value = Instance
            Ok = Svc.PersistPreEncodeMeta(
                TranscodeAttemptId=99, VocalsRmsDbfs=None, DialogBoostEmitted=False, VocalsFallbackDbfs=-50.0,
                DemucsFailed=True, DemucsFailureReason='FileNotFoundError: demucs not on PATH',
            )
            self.assertTrue(Ok)
            Args = Instance.ExecuteNonQuery.call_args.args
            Parsed = json.loads(Args[1][0])
            self.assertEqual(len(Parsed), 2)
            for Entry in Parsed:
                self.assertIs(Entry['demucs_failed'], True)
                self.assertEqual(Entry['demucs_failure_reason'], 'FileNotFoundError: demucs not on PATH')
            self.assertEqual(Parsed[0]['AchievedIntegratedLufs'], -23.0)
            self.assertEqual(Parsed[1]['AchievedIntegratedLufs'], -20.1)

    # directive: audio-dialog-boost-real | # see audio-normalization.C39
    def test_measurement_service_demucs_failed_false_on_happy_path(self):
        Svc = PostEncodeMeasurementService(FFmpegPath='/usr/bin/ffmpeg', FFprobePath='/usr/bin/ffprobe')
        Existing = [{'TrackIndex': 1, 'Label': 'Original'}]
        with patch('Features.AudioNormalization.Services.PostEncodeMeasurementService.DatabaseService') as MockDb:
            Instance = MagicMock()
            Instance.ExecuteQuery.return_value = [{'audiotracksemittedjson': Existing}]
            MockDb.return_value = Instance
            Svc.PersistPreEncodeMeta(
                TranscodeAttemptId=77, VocalsRmsDbfs=-30.5, DialogBoostEmitted=True, VocalsFallbackDbfs=-50.0,
            )
            Parsed = json.loads(Instance.ExecuteNonQuery.call_args.args[1][0])
            self.assertIs(Parsed[0]['demucs_failed'], False)
            self.assertIsNone(Parsed[0]['demucs_failure_reason'])


if __name__ == '__main__':
    unittest.main()
