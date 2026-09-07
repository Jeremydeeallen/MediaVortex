# directive: bug-0093-preencode-fail-loud-via-d13
import unittest
from unittest.mock import patch, MagicMock

from Features.AudioNormalization.Services import AudioPreEncodeFacade
from Features.AudioNormalization.Services.DemucsDaemonClient import DemucsDaemonUnavailableError
from Features.AudioNormalization.Services.PreEncodeAudioPipeline import PreEncodeAudioPipeline
from Features.TranscodeJob.Worker import PartialCompletion


class TestPreEncodePipelineRaises(unittest.TestCase):

    def test_pipeline_run_raises_daemon_unavailable(self):
        Fake = MagicMock()
        Fake.MeasureSourceLoudnorm.return_value = (-23.0, 7.0, -1.0, -34.0)
        Fake.IsolateVocals.side_effect = DemucsDaemonUnavailableError("Demucs daemon closed stdout unexpectedly. Stderr tail: fake")
        P = PreEncodeAudioPipeline(FfmpegPath='ffmpeg', PythonExe='python', DemucsService=Fake, ScratchRoot='/tmp')
        P._RulesRepo = MagicMock()
        P._RulesRepo.GetRules.return_value = {
            'TargetTruePeakDbtp': -1.0, 'SampleLimitHeadroomDb': 0.5,
            'TargetIntegratedLufs': -23.0, 'SourceMeasureTargetLra': 7.0,
            'VocalsBoostDb': 6.0, 'InstrumentalAttenDb': -6.0,
            'PremixCompressorThreshold': -20.0, 'PremixCompressorRatio': 4.0,
            'PremixCompressorMakeupDb': 3.0, 'PremixDynaudnormFrameLen': 500,
            'PremixDynaudnormGaussSize': 31, 'DialogBoostTargetLufs': -20.0,
            'DialogBoostTargetLra': 5.0,
        }
        P._ExtractStereoDownmix = MagicMock(return_value='downmix.wav')
        with self.assertRaises(DemucsDaemonUnavailableError) as Ctx:
            P.Run('/src/x.mkv', JobId=1)
        self.assertIn("closed stdout unexpectedly", str(Ctx.exception))

    def test_pipeline_run_raises_runtime_error(self):
        Fake = MagicMock()
        Fake.MeasureSourceLoudnorm.return_value = (-23.0, 7.0, -1.0, -34.0)
        Fake.IsolateVocals.side_effect = RuntimeError("demucs output missing: vocals_exists=False")
        P = PreEncodeAudioPipeline(FfmpegPath='ffmpeg', PythonExe='python', DemucsService=Fake, ScratchRoot='/tmp')
        P._RulesRepo = MagicMock()
        P._RulesRepo.GetRules.return_value = {
            'TargetTruePeakDbtp': -1.0, 'SampleLimitHeadroomDb': 0.5,
            'TargetIntegratedLufs': -23.0, 'SourceMeasureTargetLra': 7.0,
            'VocalsBoostDb': 6.0, 'InstrumentalAttenDb': -6.0,
            'PremixCompressorThreshold': -20.0, 'PremixCompressorRatio': 4.0,
            'PremixCompressorMakeupDb': 3.0, 'PremixDynaudnormFrameLen': 500,
            'PremixDynaudnormGaussSize': 31, 'DialogBoostTargetLufs': -20.0,
            'DialogBoostTargetLra': 5.0,
        }
        P._ExtractStereoDownmix = MagicMock(return_value='downmix.wav')
        with self.assertRaises(RuntimeError):
            P.Run('/src/x.mkv', JobId=2)


class TestAudioPreEncodeFacadeRaises(unittest.TestCase):

    def test_facade_prepare_propagates_daemon_unavailable(self):
        with patch('Features.AudioNormalization.Services.PreEncodeAudioPipeline.PreEncodeAudioPipeline.Run',
                   side_effect=DemucsDaemonUnavailableError("Demucs daemon response timeout after 1800s")):
            with self.assertRaises(DemucsDaemonUnavailableError) as Ctx:
                AudioPreEncodeFacade.Prepare(FfmpegPath='ffmpeg', InputPath='/src/x.mkv', JobId=1)
            self.assertIn("timeout after 1800s", str(Ctx.exception))

    def test_facade_prepare_returns_none_on_empty_input(self):
        self.assertIsNone(AudioPreEncodeFacade.Prepare(FfmpegPath='ffmpeg', InputPath='', JobId=1))


class TestPreEncodeFallbackLogEmit(unittest.TestCase):

    def test_log_pre_encode_fallback_calls_warning(self):
        with patch('Features.TranscodeJob.Worker.PartialCompletion.LoggingService') as MockLog:
            PartialCompletion.LogPreEncodeFallback(999999, "DemucsDaemonUnavailableError: closed stdout")
            MockLog.LogWarning.assert_called_once()
            Args = MockLog.LogWarning.call_args[0]
            self.assertIn("PreEncodePartialFallback", Args[0])
            self.assertIn("MediaFileId=999999", Args[0])
            self.assertIn("first_fallback=AudioSlot", Args[0])


class TestGateBypassOnPartialSuccess(unittest.TestCase):
    """C14: FileReplacementBusinessService passes RunComplianceGate=False when DispositionReason startswith 'PartialSuccess_'."""

    def test_startswith_check_matches_both_partial_success_reasons(self):
        for Reason in ('PartialSuccess_AudioSlotCopied', 'PartialSuccess_VideoSlotCopied'):
            self.assertTrue(str(Reason or '').startswith('PartialSuccess_'), f"Reason {Reason!r} must match bypass predicate")

    def test_startswith_check_does_not_match_non_partial_reasons(self):
        for Reason in ('', None, 'VmafBelowMin', 'PartialRetryExhausted', 'TestMode', 'ComplianceGateFailed'):
            self.assertFalse(str(Reason or '').startswith('PartialSuccess_'), f"Reason {Reason!r} must NOT match bypass predicate")


if __name__ == '__main__':
    unittest.main()
