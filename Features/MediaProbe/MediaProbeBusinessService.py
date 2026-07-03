import os
from typing import Dict, Any, Optional, List
from datetime import datetime, timezone
from Core.Models.MediaFileModel import MediaFileModel
from Features.MediaProbe.MediaProbeRepository import MediaProbeRepository
from Services.FileManagerService import FileManagerService
from Core.Logging.LoggingService import LoggingService
from Core.Path import Path, Worker, PathError


# directive: mediaprobe-uses-path | # see path.S3
class MediaProbeBusinessService:
    """Orchestrates FFprobe metadata extraction with failure tracking."""

    MaxFFprobeFailures = 3  # Files exceeding this are skipped until manually reset

    # directive: path-class-perfection | # see path.C26
    def __init__(self, RepositoryInstance=None, FileManagerInstance=None, worker: Optional[Worker] = None):
        self.Repository = RepositoryInstance or MediaProbeRepository()
        self.FileManager = FileManagerInstance or FileManagerService()
        self._Worker: Worker = worker if worker is not None else Worker.Current()

    # directive: path-class-perfection | # see path.C26
    def _GetWorker(self) -> Worker:
        return self._Worker

    # directive: path-class-perfection | # see path.C18
    def _GetStorageRoots(self) -> List[dict]:
        from Core.Path.PathStorageRoots import GetStorageRoots
        return GetStorageRoots()

    # directive: mediaprobe-uses-path | # see path.S5
    def _ResolveWorkerLocal(self, MediaFile: MediaFileModel, FallbackFilePath: str):
        """Return (local_path_str, Path_obj_or_None). Prefers the typed pair; falls back to FromLegacyString parsing of FallbackFilePath; final-fallback returns the raw string with None for logging when both attempts fail."""
        Wk = self._GetWorker()
        if MediaFile.StorageRootId is not None and MediaFile.RelativePath:
            try:
                P = Path(MediaFile.StorageRootId, MediaFile.RelativePath)
                return (P.Resolve(Wk), P)
            except PathError as PErr:
                # directive: path-class-perfection | # see path.C22
                LoggingService.LogWarning(f"MediaProbeBusinessService._ResolveWorkerLocal: typed-pair ({MediaFile.StorageRootId},{MediaFile.RelativePath!r}) failed to Resolve: {PErr}", 'MediaProbeBusinessService', '_ResolveWorkerLocal')
        if FallbackFilePath:
            try:
                P = Path.FromLegacyString(FallbackFilePath, self._GetStorageRoots())
                return (P.Resolve(Wk), P)
            except PathError as PErr2:
                LoggingService.LogWarning(f"MediaProbeBusinessService._ResolveWorkerLocal: legacy FallbackFilePath {FallbackFilePath!r} did not match any StorageRoot prefix: {PErr2}", 'MediaProbeBusinessService', '_ResolveWorkerLocal')
        return (FallbackFilePath, None)

    # ─── Single File Probe ─────────────────────────────────────────────

    def ProbeFile(self, MediaFileId: int, Force: bool = False) -> Dict[str, Any]:
        """Run FFprobe against a single file by ID. Set Force=True to ignore failure limits."""
        try:
            MediaFile = self.Repository.GetMediaFileById(MediaFileId)
            if not MediaFile:
                return {'Success': False, 'Message': f'Media file not found: {MediaFileId}'}

            if not Force and (MediaFile.FFprobeFailureCount or 0) >= self.MaxFFprobeFailures:
                return {
                    'Success': False,
                    'Message': f'File has exceeded max probe failures ({MediaFile.FFprobeFailureCount}/{self.MaxFFprobeFailures}). Use Force=True or reset failures first.',
                    'FFprobeFailureCount': MediaFile.FFprobeFailureCount,
                    'LastFFprobeError': MediaFile.LastFFprobeError
                }

            return self._ExecuteProbe(MediaFile)

        except Exception as Ex:
            LoggingService.LogException(f"Error probing file ID {MediaFileId}", Ex, "MediaProbeBusinessService", "ProbeFile")
            return {'Success': False, 'Message': f'Error: {str(Ex)}'}

    # directive: mediaprobe-uses-path | # see path.S5
    def _ExecuteProbe(self, MediaFile: MediaFileModel) -> Dict[str, Any]:
        """Execute FFprobe against a media file and update the database. Worker-local path via Path/Worker; FromLegacyString fallback for unmigrated typed pair or orphan-StorageRoot edge cases."""
        FilePath = MediaFile.FilePath
        LocalPath, PathObj = self._ResolveWorkerLocal(MediaFile, FilePath)
        from Core.Path.PathFs import Exists as _PathFsExists
        Exists = _PathFsExists(PathObj, self._GetWorker())
        try:
            if not Exists:
                ErrorMsg = f"File does not exist on disk: {FilePath} (local: {LocalPath})"
                LoggingService.LogWarning(ErrorMsg, "MediaProbeBusinessService", "_ExecuteProbe")
                self.Repository.RecordProbeFailure(MediaFile.Id, ErrorMsg)
                return {'Success': False, 'Message': ErrorMsg}

            if not self.FileManager.IsMediaAnalysisAvailable():
                return {'Success': False, 'Message': 'FFprobe is not available'}

            # Run FFprobe via FileManagerService against the local path.
            MetadataResult = self.FileManager.ExtractMediaMetadata(LocalPath)

            if MetadataResult.get('Success', False):
                # Apply metadata to model
                MediaFile.VideoBitrateKbps = MetadataResult.get('VideoBitrateKbps')
                MediaFile.AudioBitrateKbps = MetadataResult.get('AudioBitrateKbps')
                MediaFile.Resolution = MetadataResult.get('Resolution')
                MediaFile.ResolutionCategory = self._DeriveResolutionCategory(MediaFile.Resolution)
                MediaFile.Codec = MetadataResult.get('VideoCodec')
                MediaFile.DurationMinutes = MetadataResult.get('DurationMinutes')
                MediaFile.FrameRate = MetadataResult.get('FrameRate')
                MediaFile.TotalFrames = MetadataResult.get('TotalFrames')
                MediaFile.CodecProfile = MetadataResult.get('CodecProfile')
                MediaFile.ColorRange = MetadataResult.get('ColorRange')
                MediaFile.FieldOrder = MetadataResult.get('FieldOrder')
                MediaFile.HasBFrames = MetadataResult.get('HasBFrames')
                MediaFile.RefFrames = MetadataResult.get('RefFrames')
                MediaFile.PixelFormat = MetadataResult.get('PixelFormat')
                MediaFile.Level = MetadataResult.get('Level')
                MediaFile.AudioChannels = MetadataResult.get('AudioChannels')
                MediaFile.AudioSampleRate = MetadataResult.get('AudioSampleRate')
                MediaFile.AudioSampleFormat = MetadataResult.get('AudioSampleFormat')
                MediaFile.AudioChannelLayout = MetadataResult.get('AudioChannelLayout')
                MediaFile.AudioCodec = MetadataResult.get('AudioCodec')
                MediaFile.SubtitleFormats = MetadataResult.get('SubtitleFormats')
                # directive: compliance-solid-refactor | # see compliance-solid-refactor.C5b
                MediaFile.HasForcedSubtitles = MetadataResult.get('HasForcedSubtitles')
                MediaFile.ContainerFormat = MetadataResult.get('ContainerFormat')
                MediaFile.OverallBitrate = MetadataResult.get('OverallBitrate')
                MediaFile.AudioLanguages = MetadataResult.get('AudioLanguages')
                MediaFile.HasExplicitEnglishAudio = MetadataResult.get('HasExplicitEnglishAudio')

                # Clear failure tracking on success
                MediaFile.FFprobeFailureCount = 0
                MediaFile.LastFFprobeError = None
                MediaFile.LastFFprobeAttemptDate = datetime.now(timezone.utc)
                # Clear operator-triggered reprobe flag on success
                MediaFile.NeedsReprobe = False

                self.Repository.UpdateMetadata(MediaFile)

                # Loudness measurement (best-effort -- failure does NOT roll
                # back the probe). See Features/LoudnessAnalysis/.
                try:
                    from Features.AudioNormalization.Measurement.EbuR128MeasurementService import EbuR128MeasurementService
                    LoudnessSvc = EbuR128MeasurementService()
                    Ok, FailureReason = LoudnessSvc.MeasureAndPersist(MediaFile.Id, LocalPath)
                    if not Ok and FailureReason:
                        LoggingService.LogWarning(
                            f"Loudness measurement skipped for MediaFileId={MediaFile.Id}: {FailureReason}",
                            "MediaProbeBusinessService", "_ExecuteProbe"
                        )
                    elif Ok and FailureReason is None:
                        # see audio-normalization.C36
                        self._MaybeAutoMarkAudioCompleteAtTarget(MediaFile.Id)
                except Exception as LoudnessEx:
                    LoggingService.LogException(
                        f"Loudness measurement failed for MediaFileId={MediaFile.Id} -- probe data is saved",
                        LoudnessEx, "MediaProbeBusinessService", "_ExecuteProbe"
                    )

                # Flag files with no audio stream as possibly corrupt
                if not MetadataResult.get('AudioCodec'):
                    try:
                        from Repositories.DatabaseManager import DatabaseManager
                        DatabaseManager().AddProblemFile(
                            FilePath,
                            'No_Audio_Stream',
                            f'File has no audio stream -- possibly corrupt: {FilePath}'
                        )
                        LoggingService.LogWarning(
                            f"No audio stream detected (possibly corrupt): {FilePath}",
                            "MediaProbeBusinessService", "_ExecuteProbe"
                        )
                    except Exception as ProblemEx:
                        LoggingService.LogException(
                            f"Failed to flag no-audio file as problem: {FilePath}",
                            ProblemEx, "MediaProbeBusinessService", "_ExecuteProbe"
                        )

                # ContentSignals: compute MotionFraction / SceneChangeRatePerMin /
                # LumaVariance once per file. Failure logged, never blocks probe.
                # See Features/ContentSignals/content-signals.feature.md.
                try:
                    from Features.ContentSignals.ContentSignalsRepository import ContentSignalsRepository
                    from Features.ContentSignals.ContentSignalsService import ContentSignalsService
                    SignalsRepo = ContentSignalsRepository()
                    if not SignalsRepo.HasSignals(MediaFile.Id):
                        Signals = ContentSignalsService.ComputeSignals(LocalPath)
                        if Signals is not None:
                            SignalsRepo.WriteSignals(MediaFile.Id, Signals)
                except Exception as SignalsEx:
                    LoggingService.LogException(
                        f"ContentSignals after probe failed for MediaFileId={MediaFile.Id} -- probe data is saved",
                        SignalsEx, "MediaProbeBusinessService", "_ExecuteProbe"
                    )

                # see compliance.flow.md (post-probe recompute; failure must not roll back the probe)
                try:
                    from Features.TranscodeQueue.QueueManagementBusinessService import QueueManagementBusinessService
                    QueueManagementBusinessService().RecomputeForFiles([MediaFile.Id])
                except Exception as PriorityEx:
                    LoggingService.LogException(
                        f"Priority recompute after probe failed for MediaFileId={MediaFile.Id} -- probe data is saved",
                        PriorityEx, "MediaProbeBusinessService", "_ExecuteProbe"
                    )

                # ContentClassifier: auto-assign profile if AssignedProfile is still NULL
                # after the cascade above. Operator overrides are respected (the service
                # short-circuits on non-NULL AssignedProfile). Failure never blocks probe.
                # See Features/ContentClassifier/content-classifier.feature.md.
                try:
                    from Features.ContentClassifier.ContentClassifierService import ContentClassifierService
                    ContentClassifierService().ClassifyAndAssign(MediaFile.Id)
                except Exception as ClassifierEx:
                    LoggingService.LogException(
                        f"ContentClassifier after probe failed for MediaFileId={MediaFile.Id} -- probe data is saved",
                        ClassifierEx, "MediaProbeBusinessService", "_ExecuteProbe"
                    )

                LoggingService.LogInfo(f"Probe succeeded: {FilePath} ({MediaFile.Resolution}, {MediaFile.Codec})", "MediaProbeBusinessService", "_ExecuteProbe")
                return {
                    'Success': True,
                    'Message': f'Metadata extracted successfully',
                    'Resolution': MediaFile.Resolution,
                    'Codec': MediaFile.Codec,
                    'DurationMinutes': MediaFile.DurationMinutes
                }
            else:
                # Probe failed - record the failure
                ErrorMessage = MetadataResult.get('ErrorMessage', 'Unknown FFprobe error')
                self.Repository.RecordProbeFailure(MediaFile.Id, ErrorMessage)

                LoggingService.LogWarning(f"Probe failed for {FilePath}: {ErrorMessage}", "MediaProbeBusinessService", "_ExecuteProbe")
                return {
                    'Success': False,
                    'Message': f'FFprobe failed: {ErrorMessage}',
                    'FFprobeFailureCount': (MediaFile.FFprobeFailureCount or 0) + 1
                }

        except Exception as Ex:
            ErrorMessage = f"Exception during probe: {str(Ex)}"
            self.Repository.RecordProbeFailure(MediaFile.Id, ErrorMessage)
            LoggingService.LogException(f"Error in _ExecuteProbe for {FilePath}", Ex, "MediaProbeBusinessService", "_ExecuteProbe")
            return {'Success': False, 'Message': ErrorMessage}

    def _DeriveResolutionCategory(self, Resolution: str) -> str:
        """Convert pixel dimensions (e.g. '1920x1080') to resolution category.

        Width-primary because mastering targets are width-fixed (1280 = 720p,
        1920 = 1080p, 3840 = 4K) but heights vary with cropping/letterboxing
        (e.g. 1280x718 is broadcast 720p with cropping; the strict
        `height >= 720` cutoff misclassifies thousands of real files).

        Same logic as DatabaseManager._ConvertPixelDimensionsToResolutionCategory
        and QueueManagementBusinessService._ResolutionCategoryFromPixels; should
        be unified into a Core helper in a follow-up.
        """
        try:
            if not Resolution or 'x' not in Resolution:
                return None
            Parts = Resolution.split('x', 1)
            Width = int(Parts[0])
            Height = int(Parts[1])
            # Width-primary discrimination
            if Width >= 3000:
                return "2160p"
            if Width >= 1700:
                return "1080p"
            if Width >= 1100:
                return "720p"
            if Width >= 600:
                return "480p"
            # Fall through to height for narrow/portrait content
            if Height >= 2000:
                return "2160p"
            if Height >= 950:
                return "1080p"
            if Height >= 650:
                return "720p"
            return "480p"
        except Exception:
            return None

    def _MaybeAutoMarkAudioCompleteAtTarget(self, MediaFileId: int) -> None:
        """If newly-measured file is at -23 LUFS (+/- 1) with MP4-compat audio codec, mark AudioComplete=true with AudioStateService clause-d reason; best-effort."""
        try:
            from Core.Database.DatabaseService import DatabaseService
            from Features.AudioNormalization.Services.AudioStateService import AudioStateService
            Db = DatabaseService()
            Rows = Db.ExecuteQuery(
                """
                SELECT SourceIntegratedLufs, AudioCodec, AudioComplete,
                       AudioCorruptSuspect, HasExplicitEnglishAudio, Resolution,
                       AudioBitrateKbps, AudioChannels
                FROM MediaFiles WHERE Id = %s
                """,
                (MediaFileId,),
            )
            if not Rows:
                return
            Row = Rows[0]
            if Row.get('AudioComplete') is True or Row.get('AudioCorruptSuspect') is True:
                return  # already settled
            # Reuse the canonical state derivation -- HasLoudnormHistory=False
            # is correct here since we are evaluating fresh measurements, not
            # historical attempts. The backfill is the path that consults
            # history; the probe co-trigger is the steady-state path.
            from Features.TranscodeQueue.QueueAdmissionConfigRepository import QueueAdmissionConfigRepository
            FloorCfg = QueueAdmissionConfigRepository().Get()
            Complete, Suspect, Reason = AudioStateService.EvaluateInitialAudioState(
                Row, FloorCfg, HasLoudnormHistory=False,
            )
            if Complete is True and Reason == AudioStateService.REASON_ALREADY_AT_TARGET_LOUDNESS:
                if AudioStateService.MarkAudioComplete(MediaFileId):
                    # Also stamp the reason -- MarkAudioComplete only sets the
                    # flag + timestamp; the reason needs a separate write.
                    Db.ExecuteNonQuery(
                        "UPDATE MediaFiles SET AudioCorruptReason = %s WHERE Id = %s",
                        (AudioStateService.REASON_ALREADY_AT_TARGET_LOUDNESS, MediaFileId),
                    )
                    LoggingService.LogInfo(
                        f"Auto-marked AudioComplete=true (already_at_target_loudness) "
                        f"for MediaFileId={MediaFileId}",
                        "MediaProbeBusinessService", "_MaybeAutoMarkAudioCompleteAtTarget"
                    )
        except Exception as Ex:
            LoggingService.LogException(
                f"_MaybeAutoMarkAudioCompleteAtTarget failed for MediaFileId={MediaFileId}",
                Ex, "MediaProbeBusinessService", "_MaybeAutoMarkAudioCompleteAtTarget"
            )

    # ─── Batch Operations ──────────────────────────────────────────────

    def ProbeFilesNeedingMetadata(self, RootFolderId: Optional[int] = None, ProgressCallback=None) -> Dict[str, Any]:
        """Probe all files that need metadata, respecting failure limits.

        ProgressCallback(Index: int) is called after each probe completion with the
        1-based count of probes finished so far. If the callback returns truthy,
        the loop exits early (directive 2026-05-27 soft-stop). Callback errors are
        non-fatal -- the probe loop continues even if the caller raises.
        """
        try:
            FilesToProbe = self.Repository.GetFilesNeedingProbe(RootFolderId, self.MaxFFprobeFailures)

            if not FilesToProbe:
                return {
                    'Success': True,
                    'Message': 'No files need probing',
                    'Processed': 0,
                    'Succeeded': 0,
                    'Failed': 0,
                    'Skipped': 0
                }

            LoggingService.LogInfo(f"Starting batch probe for {len(FilesToProbe)} files", "MediaProbeBusinessService", "ProbeFilesNeedingMetadata")

            Succeeded = 0
            Failed = 0

            for Index, File in enumerate(FilesToProbe, start=1):
                Result = self._ExecuteProbe(File)
                if Result.get('Success', False):
                    Succeeded += 1
                else:
                    Failed += 1
                if ProgressCallback is not None:
                    try:
                        ShouldStop = ProgressCallback(Index)
                        if ShouldStop:
                            LoggingService.LogInfo(f"Probe loop stopped via callback at {Index}/{len(FilesToProbe)}", "MediaProbeBusinessService", "ProbeFilesNeedingMetadata")
                            break
                    except Exception as CbEx:
                        LoggingService.LogException("ProgressCallback raised", CbEx, "MediaProbeBusinessService", "ProbeFilesNeedingMetadata")

            LoggingService.LogInfo(f"Batch probe complete: {Succeeded} succeeded, {Failed} failed out of {len(FilesToProbe)}", "MediaProbeBusinessService", "ProbeFilesNeedingMetadata")

            return {
                'Success': True,
                'Message': f'Probed {len(FilesToProbe)} files: {Succeeded} succeeded, {Failed} failed',
                'Processed': len(FilesToProbe),
                'Succeeded': Succeeded,
                'Failed': Failed
            }

        except Exception as Ex:
            LoggingService.LogException("Error in batch probe", Ex, "MediaProbeBusinessService", "ProbeFilesNeedingMetadata")
            return {'Success': False, 'Message': f'Error: {str(Ex)}', 'Processed': 0, 'Succeeded': 0, 'Failed': 0}

    # ─── Failure Management ────────────────────────────────────────────

    def ResetFailures(self, MediaFileId: int) -> Dict[str, Any]:
        """Reset failure tracking for a single file so it can be retried."""
        try:
            MediaFile = self.Repository.GetMediaFileById(MediaFileId)
            if not MediaFile:
                return {'Success': False, 'Message': f'Media file not found: {MediaFileId}'}

            self.Repository.ResetProbeFailures(MediaFileId)
            LoggingService.LogInfo(f"Reset probe failures for file ID {MediaFileId}: {MediaFile.FilePath}", "MediaProbeBusinessService", "ResetFailures")
            return {'Success': True, 'Message': f'Failures reset for: {MediaFile.FileName}'}

        except Exception as Ex:
            LoggingService.LogException(f"Error resetting failures for file ID {MediaFileId}", Ex, "MediaProbeBusinessService", "ResetFailures")
            return {'Success': False, 'Message': f'Error: {str(Ex)}'}

    def ResetAllFailures(self) -> Dict[str, Any]:
        """Reset failure tracking for all files."""
        try:
            AffectedRows = self.Repository.ResetAllProbeFailures()
            LoggingService.LogInfo(f"Reset probe failures for {AffectedRows} files", "MediaProbeBusinessService", "ResetAllFailures")
            return {'Success': True, 'Message': f'Reset failures for {AffectedRows} files', 'ResetCount': AffectedRows}
        except Exception as Ex:
            LoggingService.LogException("Error resetting all failures", Ex, "MediaProbeBusinessService", "ResetAllFailures")
            return {'Success': False, 'Message': f'Error: {str(Ex)}'}

    def GetFailedFiles(self) -> Dict[str, Any]:
        """Get list of permanently failed files."""
        try:
            FailedFiles = self.Repository.GetPermanentlyFailedFiles(self.MaxFFprobeFailures)
            FileList = []
            for File in FailedFiles:
                FileList.append({
                    'Id': File.Id,
                    'FilePath': File.FilePath,
                    'FileName': File.FileName,
                    'SizeMB': File.SizeMB,
                    'FFprobeFailureCount': File.FFprobeFailureCount,
                    'LastFFprobeError': File.LastFFprobeError,
                    'LastFFprobeAttemptDate': str(File.LastFFprobeAttemptDate) if File.LastFFprobeAttemptDate else None
                })
            return {'Success': True, 'Files': FileList, 'Count': len(FileList)}
        except Exception as Ex:
            LoggingService.LogException("Error getting failed files", Ex, "MediaProbeBusinessService", "GetFailedFiles")
            return {'Success': False, 'Message': f'Error: {str(Ex)}', 'Files': [], 'Count': 0}

    # ─── Statistics ────────────────────────────────────────────────────

    def GetProbeStatistics(self) -> Dict[str, Any]:
        """Get probe status statistics."""
        try:
            Stats = self.Repository.GetProbeStatistics()
            Stats['MaxFFprobeFailures'] = self.MaxFFprobeFailures
            Stats['Success'] = True
            return Stats
        except Exception as Ex:
            LoggingService.LogException("Error getting probe statistics", Ex, "MediaProbeBusinessService", "GetProbeStatistics")
            return {'Success': False, 'Message': f'Error: {str(Ex)}'}
