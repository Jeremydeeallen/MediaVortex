import os
from typing import Dict, Any, Optional, List
from datetime import datetime, timezone
from Core.Models.MediaFileModel import MediaFileModel
from Features.MediaProbe.MediaProbeRepository import MediaProbeRepository
from Services.FileManagerService import FileManagerService
from Core.Logging.LoggingService import LoggingService


class MediaProbeBusinessService:
    """Orchestrates FFprobe metadata extraction with failure tracking."""

    MaxFFprobeFailures = 3  # Files exceeding this are skipped until manually reset

    def __init__(self, RepositoryInstance=None, FileManagerInstance=None):
        self.Repository = RepositoryInstance or MediaProbeRepository()
        self.FileManager = FileManagerInstance or FileManagerService()

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

    def _ExecuteProbe(self, MediaFile: MediaFileModel) -> Dict[str, Any]:
        """Execute FFprobe against a media file and update the database."""
        FilePath = MediaFile.FilePath
        try:
            if not os.path.exists(FilePath):
                ErrorMsg = f"File does not exist on disk: {FilePath}"
                LoggingService.LogWarning(ErrorMsg, "MediaProbeBusinessService", "_ExecuteProbe")
                self.Repository.RecordProbeFailure(MediaFile.Id, ErrorMsg)
                return {'Success': False, 'Message': ErrorMsg}

            if not self.FileManager.IsMediaAnalysisAvailable():
                return {'Success': False, 'Message': 'FFprobe is not available'}

            # Run FFprobe via FileManagerService
            MetadataResult = self.FileManager.ExtractMediaMetadata(FilePath)

            if MetadataResult.get('Success', False):
                # Apply metadata to model
                MediaFile.VideoBitrateKbps = MetadataResult.get('VideoBitrateKbps')
                MediaFile.AudioBitrateKbps = MetadataResult.get('AudioBitrateKbps')
                MediaFile.Resolution = MetadataResult.get('Resolution')
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
                MediaFile.ContainerFormat = MetadataResult.get('ContainerFormat')
                MediaFile.OverallBitrate = MetadataResult.get('OverallBitrate')
                MediaFile.AudioLanguages = MetadataResult.get('AudioLanguages')
                MediaFile.HasExplicitEnglishAudio = MetadataResult.get('HasExplicitEnglishAudio')

                # Clear failure tracking on success
                MediaFile.FFprobeFailureCount = 0
                MediaFile.LastFFprobeError = None
                MediaFile.LastFFprobeAttemptDate = datetime.now(timezone.utc)

                self.Repository.UpdateMetadata(MediaFile)

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
        """Convert pixel dimensions (e.g. '1920x1080') to resolution category (e.g. '1080p')."""
        try:
            if not Resolution or 'x' not in Resolution:
                return None
            Height = int(Resolution.split('x')[1])
            if Height >= 2160:
                return "2160p"
            elif Height >= 1080:
                return "1080p"
            elif Height >= 720:
                return "720p"
            elif Height >= 480:
                return "480p"
            else:
                return "480p"
        except Exception:
            return None

    # ─── Batch Operations ──────────────────────────────────────────────

    def ProbeFilesNeedingMetadata(self, RootFolderId: Optional[int] = None) -> Dict[str, Any]:
        """Probe all files that need metadata, respecting failure limits."""
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

            for File in FilesToProbe:
                Result = self._ExecuteProbe(File)
                if Result.get('Success', False):
                    Succeeded += 1
                else:
                    Failed += 1

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
