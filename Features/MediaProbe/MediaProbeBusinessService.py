import os
from typing import Dict, Any, Optional, List
from datetime import datetime, timezone
from Core.Models.MediaFileModel import MediaFileModel
from Core.Resolution.ResolutionTierRegistry import ResolutionTierRegistry
from Features.MediaProbe.MediaProbeRepository import MediaProbeRepository
from Services.FileManagerService import FileManagerService
from Core.Logging.LoggingService import LoggingService
from Core.Path import Path, Worker, PathError


# directive: probe-fail-loud-no-retry-cap | # see probe.C7 (retry cap removed)
class MediaProbeBusinessService:
    """Orchestrates FFprobe metadata extraction. Fail-loud: on failure writes LastFFprobeError + FFprobeFailureCount++; never silently skips."""

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
        """Run FFprobe against a single file by ID. Force arg preserved for callers; no cap to override (see probe-fail-loud-no-retry-cap)."""
        try:
            MediaFile = self.Repository.GetMediaFileById(MediaFileId)
            if not MediaFile:
                return {'Success': False, 'Message': f'Media file not found: {MediaFileId}'}
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
                MediaFile.ResolutionCategory = ResolutionTierRegistry().CategoryStringFromResolution(MediaFile.Resolution)
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
            FailedFiles = self.Repository.GetPermanentlyFailedFiles()
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
            Stats['Success'] = True
            return Stats
        except Exception as Ex:
            LoggingService.LogException("Error getting probe statistics", Ex, "MediaProbeBusinessService", "GetProbeStatistics")
            return {'Success': False, 'Message': f'Error: {str(Ex)}'}
