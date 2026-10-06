# directive: audio-dialog-boost-real | # see audio-normalization.C8
import sys
from Core.Logging.LoggingService import LoggingService


# directive: audio-dialog-boost-real | # see audio-normalization.C8
_PREMIX_KEYS = ('DemucsPremixPath', 'VocalsRmsDbfs', 'PremixMeasuredI', 'PremixMeasuredLra', 'PremixMeasuredTp', 'PremixMeasuredThresh')


# directive: label-decides-command | # see audio-normalization.C8
def Prepare(FfmpegPath, InputPath, JobId, ProgressReporter=None, MediaFileId=None):
    if not InputPath:
        return None
    from Features.AudioNormalization.Services.PreEncodeAudioPipeline import PreEncodeAudioPipeline
    return PreEncodeAudioPipeline(
        FfmpegPath=FfmpegPath, PythonExe=sys.executable, ProgressReporter=ProgressReporter,
    ).Run(InputPath, JobId, MediaFileId=MediaFileId)


# directive: audio-dialog-boost-real | # see audio-normalization.C8
def EnrichContext(Context, PreAudio):
    """Copy premix keys onto a dict-shaped Context (or TranscodingSettings)."""
    if not Context:
        return
    for Key in _PREMIX_KEYS:
        Context[Key] = (PreAudio or {}).get(Key)


# directive: label-decides-command | # see audio-normalization.C8
def PersistMeta(TranscodeAttemptId, PreAudio):
    if not PreAudio:
        return
    VocalsRms = PreAudio.get('VocalsRmsDbfs')
    PremixPath = PreAudio.get('DemucsPremixPath')
    if VocalsRms is None and not PremixPath:
        return
    from Features.AudioNormalization.Repositories.AudioComplianceRulesRepository import AudioComplianceRulesRepository
    from Core.Database.DatabaseService import DatabaseService
    FallbackDbfs = AudioComplianceRulesRepository().GetRules().get('Track1VocalsRmsFallbackDbfs')
    DialogBoostEmitted = bool(PremixPath) and not (
        VocalsRms is not None and FallbackDbfs is not None and float(VocalsRms) <= float(FallbackDbfs)
    )
    DatabaseService().ExecuteNonQuery(
        "UPDATE TranscodeAttempts SET DialogBoostEmitted = %s WHERE Id = %s",
        (bool(DialogBoostEmitted), int(TranscodeAttemptId)),
    )


# directive: label-decides-command | # see audio-normalization.C8
def WasDialogBoostEmitted(TranscodeAttemptId) -> bool:
    from Core.Database.DatabaseService import DatabaseService
    Rows = DatabaseService().ExecuteQuery(
        "SELECT DialogBoostEmitted FROM TranscodeAttempts WHERE Id = %s",
        (int(TranscodeAttemptId),),
    )
    return bool(Rows) and Rows[0].get('DialogBoostEmitted') is True


# directive: transcode-flow-canonical
def PersistSourceLoudness(MediaFileId, MediaFile, PreAudio):
    if not PreAudio:
        return
    SrcI = PreAudio.get('SourceMeasuredI')
    SrcLra = PreAudio.get('SourceMeasuredLra')
    SrcTp = PreAudio.get('SourceMeasuredTp')
    SrcThresh = PreAudio.get('SourceMeasuredThresh')
    if SrcI is None or SrcLra is None or SrcTp is None or SrcThresh is None:
        return
    try:
        from Core.Database.DatabaseService import DatabaseService
        DatabaseService().ExecuteNonQuery(
            "UPDATE MediaFiles SET SourceIntegratedLufs=%s, SourceLoudnessRangeLU=%s, SourceTruePeakDbtp=%s, SourceIntegratedThresholdLufs=%s, LoudnessMeasuredAt=NOW() WHERE Id=%s",
            (float(SrcI), float(SrcLra), float(SrcTp), float(SrcThresh), int(MediaFileId)),
        )
        if MediaFile is not None:
            try:
                MediaFile.SourceIntegratedLufs = float(SrcI)
                MediaFile.SourceLoudnessRangeLU = float(SrcLra)
                MediaFile.SourceTruePeakDbtp = float(SrcTp)
                MediaFile.SourceIntegratedThresholdLufs = float(SrcThresh)
            except Exception:
                pass
        # directive: ingest-pipeline-kiss -- writer-owns-cascade: loudness columns feed AudioVertical.Evaluate
        from Features.TranscodeQueue.QueueManagementBusinessService import QueueManagementBusinessService
        QueueManagementBusinessService().RecomputeForFiles([int(MediaFileId)])
    except Exception as Ex:
        LoggingService.LogException(
            f"AudioPreEncodeFacade.PersistSourceLoudness failed for MediaFileId={MediaFileId}",
            Ex, "AudioPreEncodeFacade", "PersistSourceLoudness",
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
