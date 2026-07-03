# directive: audio-dialog-boost-real | # see audio-normalization.C8
import sys
from Core.Logging.LoggingService import LoggingService


# directive: audio-dialog-boost-real | # see audio-normalization.C8
_PREMIX_KEYS = ('DemucsPremixPath', 'VocalsRmsDbfs', 'PremixMeasuredI', 'PremixMeasuredLra', 'PremixMeasuredTp', 'PremixMeasuredThresh')


# directive: audio-dialog-boost-real | # see audio-normalization.C8
def Prepare(FfmpegPath, InputPath, JobId, ProgressReporter=None):
    """Run Demucs pre-encode pipeline; return dict with premix path + measurements. None on empty input."""
    if not InputPath:
        return None
    try:
        from Features.AudioNormalization.Services.PreEncodeAudioPipeline import PreEncodeAudioPipeline
        return PreEncodeAudioPipeline(
            FfmpegPath=FfmpegPath, PythonExe=sys.executable, ProgressReporter=ProgressReporter,
        ).Run(InputPath, JobId)
    except Exception as Ex:
        LoggingService.LogException(
            f"AudioPreEncodeFacade.Prepare failed for JobId={JobId}; Dialog Boost will be skipped",
            Ex, "AudioPreEncodeFacade", "Prepare",
        )
        return {'DemucsPremixPath': None, 'VocalsRmsDbfs': None, 'ScratchDir': None}


# directive: audio-dialog-boost-real | # see audio-normalization.C8
def EnrichContext(Context, PreAudio):
    """Copy premix keys onto a dict-shaped Context (or TranscodingSettings)."""
    if not Context:
        return
    for Key in _PREMIX_KEYS:
        Context[Key] = (PreAudio or {}).get(Key)


# directive: audio-dialog-boost-real | # see audio-normalization.C8
def PersistMeta(TranscodeAttemptId, PreAudio):
    """G5: stamp vocals_rms_dbfs + dialog_boost_emitted onto TranscodeAttempts.AudioTracksEmittedJson."""
    if not PreAudio:
        return
    VocalsRms = PreAudio.get('VocalsRmsDbfs')
    PremixPath = PreAudio.get('DemucsPremixPath')
    DemucsFailed = bool(PreAudio.get('DemucsFailed'))
    DemucsFailureReason = PreAudio.get('DemucsFailureReason')
    if VocalsRms is None and not PremixPath and not DemucsFailed:
        return
    try:
        from Features.AudioNormalization.Repositories.AudioComplianceRulesRepository import AudioComplianceRulesRepository
        from Features.AudioNormalization.Services.PostEncodeMeasurementService import PostEncodeMeasurementService
        FallbackDbfs = AudioComplianceRulesRepository().GetRules().get('Track1VocalsRmsFallbackDbfs')
        DialogBoostEmitted = bool(PremixPath) and not (
            VocalsRms is not None and FallbackDbfs is not None and float(VocalsRms) <= float(FallbackDbfs)
        )
        # see audio-normalization.C39
        PostEncodeMeasurementService().PersistPreEncodeMeta(
            TranscodeAttemptId, VocalsRms, DialogBoostEmitted, FallbackDbfs,
            DemucsFailed=DemucsFailed, DemucsFailureReason=DemucsFailureReason,
        )
    except Exception as Ex:
        LoggingService.LogException(
            f"AudioPreEncodeFacade.PersistMeta failed for AttemptId={TranscodeAttemptId}",
            Ex, "AudioPreEncodeFacade", "PersistMeta",
        )


# directive: audio-dialog-boost-real | # see audio-normalization.C8
def Cleanup(FfmpegPath, PreAudio):
    """Delete Demucs scratch dir; safe when PreAudio is None or ScratchDir missing."""
    if not PreAudio:
        return
    ScratchDir = PreAudio.get('ScratchDir')
    if not ScratchDir:
        return
    try:
        from Features.AudioNormalization.Services.PreEncodeAudioPipeline import PreEncodeAudioPipeline
        PreEncodeAudioPipeline(FfmpegPath=FfmpegPath, PythonExe=sys.executable).Cleanup(ScratchDir)
    except Exception:
        pass
