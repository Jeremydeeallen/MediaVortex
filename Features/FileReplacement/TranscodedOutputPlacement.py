import os
import ntpath
from typing import Dict, Any, List, Optional
from datetime import datetime, timezone
from Repositories.DatabaseManager import DatabaseManager
from Services.FileManagerService import FileManagerService
from Core.Logging.LoggingService import LoggingService
from Core.Path import Path, Worker, PathError
from Core.Path.LocalPath import LocalBasename, LocalExists, LocalGetSize, LocalGetMTime, LocalSamePath
from Features.FileReplacement.FilesystemRenameWithBackup import FilesystemRenameWithBackup
from Features.FileReplacement.PostFlightProcessors.PostFlightRegistry import BuildDefaultRegistry


# directive: filereplacement-uses-path | # see path.S5
class TranscodedOutputPlacement:
    """Owns .inprogress rename, MediaFiles refresh, original delete; see transcoded-output-placement.feature.md."""

    # directive: path-class-perfection | # see path.C26
    def __init__(self, DatabaseManagerInstance: DatabaseManager = None,
                 FileManagerInstance: FileManagerService = None,
                 FFprobePath: str = None, WorkerName: str = None,
                 worker: Optional[Worker] = None,
                 PostFlightRegistryInstance=None):
        self.DatabaseManager = DatabaseManagerInstance or DatabaseManager()
        self.FileManager = FileManagerInstance or FileManagerService(FFprobePath=FFprobePath)
        if WorkerName is None:
            import socket
            from Core.WorkerContext import WorkerContext
            Ctx = WorkerContext.Current()
            WorkerName = (Ctx.WorkerName if Ctx else None) or socket.gethostname()
        self.WorkerName = WorkerName
        self._Worker: Worker = worker if worker is not None else Worker.Current(Db=self.DatabaseManager.DatabaseService)
        self._PostFlightRegistry = PostFlightRegistryInstance if PostFlightRegistryInstance is not None else BuildDefaultRegistry()

    # directive: path-class-perfection | # see path.C26
    def _GetWorker(self) -> Worker:
        return self._Worker

    # directive: path-class-perfection | # see path.C18
    def _GetStorageRoots(self) -> List[dict]:
        from Core.Path.PathStorageRoots import GetStorageRoots
        return GetStorageRoots()

    # directive: filereplacement-decompose | see transcoded-output-placement.C4 | see transcoded-output-placement.S1 | # see transcode.ST9
    def Execute(self, OriginalFilePath: str, TranscodedFilePath: str, NetworkOriginalPath: str = None,
                FFmpegCommand: Optional[str] = None, SourceMediaFileId: Optional[int] = None,
                Mode: str = 'Transcode') -> Dict[str, Any]:
        """Rename .inprogress -> final, refresh MediaFiles, delete original; see transcoded-output-placement.C4."""
        try:
            LocalOriginalPath = Path.FromLegacyString(OriginalFilePath, self._GetStorageRoots()).Resolve(self._GetWorker())
            LocalStagedPath = Path.FromLegacyString(TranscodedFilePath, self._GetStorageRoots()).Resolve(self._GetWorker())

            LoggingService.LogFunctionEntry("Execute", "TranscodedOutputPlacement",
                                          LocalOriginalPath, LocalStagedPath)

            StepsCompleted = []

            if not LocalExists(LocalStagedPath):  # allow: local-path; host-resolved
                ErrorMsg = f"Staged file not found: {LocalStagedPath}"
                LoggingService.LogError(ErrorMsg, "TranscodedOutputPlacement", "Execute")
                return {'Success': False, 'ErrorMessage': ErrorMsg}

            if not LocalStagedPath.endswith('.inprogress'):
                ErrorMsg = (
                    f"Staged file does not end in .inprogress: {LocalStagedPath}. "
                    f"The .inprogress pattern is the only supported producer for FileReplacement."
                )
                LoggingService.LogError(ErrorMsg, "TranscodedOutputPlacement", "Execute")
                return {'Success': False, 'ErrorMessage': ErrorMsg}

            TargetPath = LocalStagedPath[:-len('.inprogress')]

            SameSlotReplacement = LocalSamePath(TargetPath, LocalOriginalPath)

            if LocalExists(TargetPath) and not SameSlotReplacement:
                ErrorMsg = (
                    f"Refusing to overwrite existing file at target: {TargetPath}. "
                    f"A prior replacement may have partially succeeded and left this artifact behind."
                )
                LoggingService.LogError(ErrorMsg, "TranscodedOutputPlacement", "Execute")
                return {'Success': False, 'ErrorMessage': ErrorMsg}

            if SourceMediaFileId is not None and Mode == 'Transcode':
                from Features.FileReplacement.ComplianceGate import ComplianceGate
                GateResult = ComplianceGate(self.DatabaseManager, self.FileManager).Evaluate(LocalStagedPath, SourceMediaFileId, FFmpegCommand)
                if not GateResult.get('Compliant', False):
                    CascadeReason = GateResult.get('RefusalReason') or 'unknown'
                    ErrorMsg = f'ComplianceGateFailed: {CascadeReason}'
                    LoggingService.LogWarning(
                        f"Compliance gate refused rename for {LocalStagedPath}: {CascadeReason}. "
                        f"Deleting `.inprogress`; source `{LocalOriginalPath}` untouched.",
                        "TranscodedOutputPlacement", "Execute",
                    )
                    try:
                        if LocalExists(LocalStagedPath):  # allow: local-path; host-resolved
                            os.remove(LocalStagedPath)
                    except Exception as DelEx:
                        LoggingService.LogException(
                            f"Compliance gate refused but failed to delete `.inprogress` {LocalStagedPath}",
                            DelEx, "TranscodedOutputPlacement", "Execute"
                        )
                    return {
                        'Success': False,
                        'ErrorMessage': ErrorMsg,
                        'ComplianceGateRefused': True,
                        'CascadeReason': CascadeReason,
                    }

            BackupPath = LocalOriginalPath + '.replacing.bak' if SameSlotReplacement else None
            if SameSlotReplacement and LocalExists(BackupPath):
                try:
                    os.remove(BackupPath)
                    LoggingService.LogInfo(
                        f"Removed pre-existing backup before same-slot replacement: {BackupPath}",
                        "TranscodedOutputPlacement", "Execute"
                    )
                except Exception as PreBakEx:
                    ErrorMsg = (
                        f"Same-slot replacement: pre-existing backup {BackupPath} could not be cleared: {str(PreBakEx)}. "
                        f"Refusing to proceed."
                    )
                    LoggingService.LogError(ErrorMsg, "TranscodedOutputPlacement", "Execute")
                    return {'Success': False, 'ErrorMessage': ErrorMsg}

            Renamer = FilesystemRenameWithBackup(LocalStagedPath, TargetPath, BackupPath)  # see transcoded-output-placement.C13
            try:
                Renamer.Apply()
                StepsCompleted.append(f"Renamed {LocalBasename(LocalStagedPath)} -> {LocalBasename(TargetPath)}")
                LoggingService.LogInfo(
                    f"Dropped .inprogress suffix: {LocalStagedPath} -> {TargetPath}",
                    "TranscodedOutputPlacement", "Execute"
                )
            except Exception as RenameEx:
                Renamer.Rollback()
                ErrorMsg = f"Failed to rename .inprogress to final target: {str(RenameEx)}"
                LoggingService.LogError(ErrorMsg, "TranscodedOutputPlacement", "Execute")
                return {'Success': False, 'ErrorMessage': ErrorMsg}

            try:
                TargetSize = LocalGetSize(TargetPath)
                if TargetSize <= 0:
                    LoggingService.LogWarning(
                        f"Target file is empty after rename (size={TargetSize}): {TargetPath}",
                        "TranscodedOutputPlacement", "Execute"
                    )
                else:
                    StepsCompleted.append(f"Verified target file has {TargetSize} bytes")
            except Exception as e:
                LoggingService.LogWarning(
                    f"Could not stat target after rename ({TargetPath}): {str(e)}",
                    "TranscodedOutputPlacement", "Execute"
                )

            CanonicalOriginal = NetworkOriginalPath or OriginalFilePath
            # canonical dirname (ntpath) + worker-local TargetPath basename (LocalBasename)
            CanonicalNewPath = ntpath.join(ntpath.dirname(CanonicalOriginal), LocalBasename(TargetPath))
            UpdateResult = self._UpdateMediaFilesAfterReplacement(CanonicalOriginal, CanonicalNewPath,
                                                                   FFmpegCommand=FFmpegCommand,
                                                                   Mode=Mode)
            if UpdateResult.get('Success', False):
                StepsCompleted.append("Updated MediaFiles table")
                Renamer.Commit()  # see transcoded-output-placement.C13
                if SameSlotReplacement and BackupPath:
                    StepsCompleted.append(f"Removed backup {LocalBasename(BackupPath)}")
                RecomputeMediaFileId = UpdateResult.get('MediaFileId')
                if RecomputeMediaFileId:
                    try:
                        from Features.AudioNormalization.Services.AudioStateService import AudioStateService
                        if AudioStateService.DetectNormalizationInCommand(FFmpegCommand):
                            if AudioStateService.MarkAudioComplete(RecomputeMediaFileId):
                                StepsCompleted.append("Marked AudioComplete=true (post-normalize)")
                    except Exception as AudioEx:
                        LoggingService.LogException(
                            f"MarkAudioComplete failed for MediaFileId={RecomputeMediaFileId} -- "
                            f"replacement still succeeded; next admin recompute will reconcile",
                            AudioEx, "TranscodedOutputPlacement", "Execute"
                        )
                    try:
                        from Features.TranscodeQueue.QueueManagementBusinessService import QueueManagementBusinessService
                        Updated = QueueManagementBusinessService().RecomputeForFiles([RecomputeMediaFileId])
                        StepsCompleted.append(f"Recomputed compliance (updated {Updated} row)")
                    except Exception as RecomputeEx:
                        LoggingService.LogException(
                            f"RecomputeForFiles failed for MediaFileId={RecomputeMediaFileId} after replacement",
                            RecomputeEx, "TranscodedOutputPlacement", "Execute"
                        )
            else:
                # BUG-0067 rollback (see transcoded-output-placement.C13 / S4): no orphan on disk, no silent Success=True.
                UpdateError = UpdateResult.get('ErrorMessage', 'Unknown update error')
                LoggingService.LogError(
                    f"MediaFiles update failed after rename to {TargetPath}; rolling back filesystem. Update error: {UpdateError}",
                    "TranscodedOutputPlacement", "Execute"
                )
                Renamer.Rollback()  # see transcoded-output-placement.C13
                if SameSlotReplacement and LocalExists(LocalStagedPath):  # allow: local-path; host-resolved
                    try:
                        os.remove(LocalStagedPath)
                    except Exception as CleanEx:
                        LoggingService.LogException(
                            f"Rollback: could not remove staging artifact {LocalStagedPath}",
                            CleanEx, "TranscodedOutputPlacement", "Execute"
                        )
                LoggingService.LogInfo(
                    f"Rollback after MediaFiles update failure completed via FilesystemRenameWithBackup",
                    "TranscodedOutputPlacement", "Execute"
                )
                return {
                    'Success': False,
                    'ErrorMessage': f'MediaFiles update failed: {UpdateError}',
                    'StepsCompleted': StepsCompleted,
                    'RollbackErrors': None,
                }

            if LocalSamePath(LocalOriginalPath, TargetPath):
                StepsCompleted.append("Original and target are the same path; no original to delete")
            elif LocalExists(LocalOriginalPath):
                try:
                    os.remove(LocalOriginalPath)
                    StepsCompleted.append(f"Deleted original {LocalBasename(LocalOriginalPath)}")
                    LoggingService.LogInfo(f"Deleted original source file: {LocalOriginalPath}",
                                         "TranscodedOutputPlacement", "Execute")
                except Exception as e:
                    LoggingService.LogWarning(
                        f"Could not delete original source (left at {LocalOriginalPath}): {str(e)}",
                        "TranscodedOutputPlacement", "Execute"
                    )
            else:
                StepsCompleted.append("Original source was already absent")

            return {
                'Success': True,
                'StepsCompleted': StepsCompleted,
                'Message': f'File replacement completed successfully. Steps: {", ".join(StepsCompleted)}',
                'CanonicalOriginalPath': CanonicalOriginal,
                'CanonicalNewPath': CanonicalNewPath,
            }

        except Exception as e:
            LoggingService.LogException(f"Exception in complete file replacement process", e,
                                      "TranscodedOutputPlacement", "Execute")
            return {
                'Success': False,
                'ErrorMessage': f'Exception during file replacement: {str(e)}'
            }

    # directive: filereplacement-decompose | see worker-lifecycle.C12
    def FinalizePartialReplacement(self, OriginalLocalPath: str, FinalLocalPath: str,
                                    CanonicalOriginalPath: str) -> Dict[str, Any]:
        """Crash-recovery: complete a replacement past the rename but before original delete; see worker-lifecycle.C12."""
        try:
            StepsCompleted = []
            if not LocalExists(FinalLocalPath):
                return {'Success': False, 'ErrorMessage': f'Final file does not exist: {FinalLocalPath}'}

            # canonical dirname (ntpath) + worker-local FinalLocalPath basename (LocalBasename)
            CanonicalNewPath = ntpath.join(ntpath.dirname(CanonicalOriginalPath), LocalBasename(FinalLocalPath))
            UpdateResult = self._UpdateMediaFilesAfterReplacement(CanonicalOriginalPath, CanonicalNewPath)
            if UpdateResult.get('Success', False):
                StepsCompleted.append("Updated MediaFiles table")
            else:
                # BUG-0067 (see transcoded-output-placement.C13): crash-recovery must not mask a failed update as success.
                UpdateError = UpdateResult.get('ErrorMessage', 'Unknown update error')
                LoggingService.LogError(
                    f"FinalizePartialReplacement: MediaFiles update failed for {FinalLocalPath}. Error: {UpdateError}",
                    "TranscodedOutputPlacement", "FinalizePartialReplacement"
                )
                return {
                    'Success': False,
                    'ErrorMessage': f'MediaFiles update failed during crash recovery: {UpdateError}',
                    'StepsCompleted': StepsCompleted,
                }

            if LocalSamePath(OriginalLocalPath, FinalLocalPath):
                StepsCompleted.append("Original and final are the same path; no delete needed")
            elif LocalExists(OriginalLocalPath):
                try:
                    os.remove(OriginalLocalPath)
                    StepsCompleted.append(f"Deleted original {LocalBasename(OriginalLocalPath)}")
                    LoggingService.LogInfo(f"FinalizePartialReplacement: deleted original {OriginalLocalPath}",
                                         "TranscodedOutputPlacement", "FinalizePartialReplacement")
                except Exception as e:
                    LoggingService.LogWarning(
                        f"FinalizePartialReplacement: could not delete original (left at {OriginalLocalPath}): {str(e)}",
                        "TranscodedOutputPlacement", "FinalizePartialReplacement"
                    )
            else:
                StepsCompleted.append("Original already absent")

            try:  # see jellyfin-push-notify.C1
                from Services.JellyfinNotifyService import NotifyJellyfin
                if CanonicalNewPath:
                    NotifyJellyfin([{'Path': CanonicalNewPath, 'UpdateType': 'Modified'}], self.DatabaseManager.DatabaseService)
            except Exception as NfEx:
                LoggingService.LogException(
                    "Jellyfin notify swallowed at FinalizePartialReplacement boundary",
                    NfEx, "TranscodedOutputPlacement", "FinalizePartialReplacement",
                )

            return {'Success': True, 'StepsCompleted': StepsCompleted}
        except Exception as e:
            LoggingService.LogException(
                f"FinalizePartialReplacement failed for {OriginalLocalPath} -> {FinalLocalPath}",
                e, "TranscodedOutputPlacement", "FinalizePartialReplacement"
            )
            return {'Success': False, 'ErrorMessage': str(e)}

    # directive: filereplacement-decompose | see remuxed-flag.C4, transcoded-output-placement
    def _UpdateMediaFilesAfterReplacement(self, OriginalFilePath: str, NewFilePath: str,
                                          FFmpegCommand: Optional[str] = None,
                                          Mode: str = 'Transcode') -> Dict[str, Any]:
        """Re-probe + update MediaFiles row; see remuxed-flag.C4."""
        try:
            LoggingService.LogFunctionEntry("_UpdateMediaFilesAfterReplacement", "TranscodedOutputPlacement",
                                          OriginalFilePath, NewFilePath)

            media_file = self.DatabaseManager.GetMediaFileByPath(OriginalFilePath)
            if not media_file:
                return {
                    'Success': False,
                    'ErrorMessage': f'MediaFile record not found for path: {OriginalFilePath}'
                }

            LocalNewFilePath = Path.FromLegacyString(NewFilePath, self._GetStorageRoots()).Resolve(self._GetWorker())
            metadata = self.FileManager.ExtractMediaMetadata(LocalNewFilePath)
            if not metadata.get('Success', False):
                OriginalError = metadata.get('ErrorMessage', 'Unknown error')
                LoggingService.LogError(
                    f"Re-probe failed for transcoded file at '{LocalNewFilePath}' (canonical: '{NewFilePath}'): {OriginalError}",
                    "TranscodedOutputPlacement", "_UpdateMediaFilesAfterReplacement"
                )
                return {
                    'Success': False,
                    'ErrorMessage': OriginalError,
                    'LocalNewFilePath': LocalNewFilePath,
                    'CanonicalNewFilePath': NewFilePath,
                }

            # directive: path-schema-migration | # see path.S8
            _P = Path.FromLegacyString(NewFilePath, self._GetStorageRoots())
            media_file.StorageRootId = _P.StorageRootId
            media_file.RelativePath = _P.RelativePath
            media_file.FileName = ntpath.basename(NewFilePath)  # canonical display (Windows shape)

            media_file.SizeMB = metadata.get('FileSizeMB', media_file.SizeMB)
            media_file.VideoBitrateKbps = metadata.get('VideoBitrateKbps')
            media_file.AudioBitrateKbps = metadata.get('AudioBitrateKbps')
            media_file.Resolution = metadata.get('Resolution')
            media_file.Codec = metadata.get('VideoCodec')
            media_file.DurationMinutes = metadata.get('DurationMinutes')
            media_file.FrameRate = metadata.get('FrameRate')

            media_file.TotalFrames = metadata.get('TotalFrames')
            media_file.CodecProfile = metadata.get('CodecProfile')
            media_file.ColorRange = metadata.get('ColorRange')
            media_file.FieldOrder = metadata.get('FieldOrder')
            media_file.HasBFrames = metadata.get('HasBFrames')
            media_file.RefFrames = metadata.get('RefFrames')
            media_file.PixelFormat = metadata.get('PixelFormat')
            media_file.Level = metadata.get('Level')
            media_file.AudioChannels = metadata.get('AudioChannels')
            media_file.AudioSampleRate = metadata.get('AudioSampleRate')
            media_file.AudioSampleFormat = metadata.get('AudioSampleFormat')
            media_file.AudioChannelLayout = metadata.get('AudioChannelLayout')
            media_file.AudioCodec = metadata.get('AudioCodec')
            media_file.SubtitleFormats = metadata.get('SubtitleFormats')
            media_file.ContainerFormat = metadata.get('ContainerFormat')
            media_file.OverallBitrate = metadata.get('OverallBitrate')
            media_file.AudioLanguages = metadata.get('AudioLanguages')
            media_file.HasExplicitEnglishAudio = metadata.get('HasExplicitEnglishAudio')

            NewResolution = media_file.Resolution or ''
            if NewResolution and 'x' in NewResolution:
                try:
                    Parts = NewResolution.split('x', 1)
                    Width = int(Parts[0])
                    Height = int(Parts[1])
                    if Width >= 3000:
                        media_file.ResolutionCategory = "2160p"
                    elif Width >= 1700:
                        media_file.ResolutionCategory = "1080p"
                    elif Width >= 1100:
                        media_file.ResolutionCategory = "720p"
                    elif Width >= 600:
                        media_file.ResolutionCategory = "480p"
                    elif Height >= 2000:
                        media_file.ResolutionCategory = "2160p"
                    elif Height >= 950:
                        media_file.ResolutionCategory = "1080p"
                    elif Height >= 650:
                        media_file.ResolutionCategory = "720p"
                    else:
                        media_file.ResolutionCategory = "480p"
                except (ValueError, IndexError):
                    pass

            self._PostFlightRegistry.Get(Mode).Execute(media_file, 0, NewFilePath)  # see remuxed-flag.C4

            NewFieldOrder = (metadata.get('FieldOrder') or '').strip().lower()
            if NewFieldOrder:
                media_file.IsInterlaced = '0' if NewFieldOrder == 'progressive' else '1'

            if FFmpegCommand:
                try:
                    from Features.AudioNormalization.Services.AudioStateService import AudioStateService
                    DerivedMode = AudioStateService.DetectNormalizationMode(FFmpegCommand)
                    if DerivedMode is not None:
                        media_file.AudioNormalizationMode = DerivedMode
                except Exception as ModeEx:
                    LoggingService.LogException(
                        f"Failed to derive AudioNormalizationMode from command",
                        ModeEx, "TranscodedOutputPlacement", "_UpdateMediaFilesAfterReplacement",
                    )

            try:
                NewMtime = datetime.fromtimestamp(
                    LocalGetMTime(LocalNewFilePath), tz=timezone.utc
                ).replace(tzinfo=None)
                media_file.FileModificationTime = NewMtime
                media_file.LastModifiedDate = NewMtime
                media_file.FileSize = LocalGetSize(LocalNewFilePath)
            except Exception as e:
                LoggingService.LogException(
                    f"Failed to re-stamp filesystem timestamps from {LocalNewFilePath}",
                    e, "TranscodedOutputPlacement", "_UpdateMediaFilesAfterReplacement"
                )

            media_file.LastScannedDate = datetime.now(timezone.utc)

            self.DatabaseManager.SaveMediaFile(media_file)

            try:
                self.DatabaseManager.DatabaseService.ExecuteNonQuery(
                    "UPDATE MediaFiles SET NeedsReprobe = FALSE WHERE Id = %s AND NeedsReprobe = TRUE",
                    (media_file.Id,),
                )
            except Exception as ReprobeEx:
                LoggingService.LogException(
                    f"Failed to clear NeedsReprobe after replacement for MediaFileId={media_file.Id}",
                    ReprobeEx, "TranscodedOutputPlacement", "_UpdateMediaFilesAfterReplacement",
                )

            LoggingService.LogInfo(f"Successfully updated MediaFiles record for: {OriginalFilePath}",
                                 "TranscodedOutputPlacement", "_UpdateMediaFilesAfterReplacement")

            return {
                'Success': True,
                'Message': 'MediaFiles table updated successfully',
                'MediaFileId': media_file.Id,
            }

        except Exception as e:
            LoggingService.LogException(f"Exception updating MediaFiles after replacement", e,
                                      "TranscodedOutputPlacement", "_UpdateMediaFilesAfterReplacement")
            return {
                'Success': False,
                'ErrorMessage': f'Exception updating MediaFiles: {str(e)}'
            }

