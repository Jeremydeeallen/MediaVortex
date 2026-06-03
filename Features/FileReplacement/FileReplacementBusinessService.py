import os
import ntpath
from typing import Dict, Any, List, Optional
from datetime import datetime, timezone
from Models.TranscodeAttemptModel import TranscodeAttemptModel
from Repositories.DatabaseManager import DatabaseManager
from Services.FileManagerService import FileManagerService
from Core.Logging.LoggingService import LoggingService


# directive: filereplacement-decompose | see FileReplacement.feature.md
class FileReplacementBusinessService:
    """Orchestration + read-only queries for FileReplacement; see FileReplacement.feature.md."""

    # directive: filereplacement-decompose
    def __init__(self, DatabaseManagerInstance: DatabaseManager = None,
                 FileManagerInstance: FileManagerService = None,
                 PathTranslation=None, FFprobePath: str = None, WorkerName: str = None):
        self.DatabaseManager = DatabaseManagerInstance or DatabaseManager()
        self.FileManager = FileManagerInstance or FileManagerService(FFprobePath=FFprobePath)
        self.PathTranslation = PathTranslation
        if WorkerName is None:
            import socket
            from Core.WorkerContext import WorkerContext
            Ctx = WorkerContext.Current()
            WorkerName = (Ctx.WorkerName if Ctx else None) or socket.gethostname()
        self.WorkerName = WorkerName

    # directive: filereplacement-decompose
    def _ToLocalPath(self, CanonicalPath: str) -> str:
        """Translate canonical to local; see FileReplacement.S1."""
        if not CanonicalPath:
            return CanonicalPath
        try:
            from Core.PathStorage import LoadStorageRoots, Parse as PathParse, Resolve as PathResolve
            SrId, Rel = PathParse(CanonicalPath, LoadStorageRoots(self.DatabaseManager.DatabaseService))
            if SrId is None or Rel is None:
                return CanonicalPath
            return PathResolve(SrId, Rel, self.WorkerName, self.DatabaseManager.DatabaseService)
        except Exception as e:
            LoggingService.LogException(
                f"_ToLocalPath fallthrough for {CanonicalPath!r}",
                e, "FileReplacementBusinessService", "_ToLocalPath",
            )
            return CanonicalPath

    # directive: filereplacement-decompose
    def GetFailedFileReplacements(self) -> List[Dict[str, Any]]:
        """Read-only: transcoded files that passed VMAF but failed replacement; see FileReplacement.W4."""
        try:
            LoggingService.LogFunctionEntry("GetFailedFileReplacements", "FileReplacementBusinessService")

            results = self.DatabaseManager.GetFailedFileReplacements(20)
            failed_replacements = []

            for row in results:
                attempt_id = row['Id']
                original_path = row['FilePath']
                transcoded_path = row['TranscodedFilePath']
                vmaf_score = row['VMAF']
                attempt_date = row['AttemptDate']
                vmaf_status = row['VMAFStatus']

                if self.FileManager.ValidateFileExists(original_path):
                    if self.FileManager.ValidateFileExists(transcoded_path):
                        failed_replacements.append({
                            'TranscodeAttemptId': attempt_id,
                            'OriginalFilePath': original_path,
                            'TranscodedFilePath': transcoded_path,
                            'VMAFScore': vmaf_score,
                            'AttemptDate': attempt_date,
                            'VMAFStatus': vmaf_status,
                            'OriginalFileName': ntpath.basename(original_path),
                            'TranscodedFileName': ntpath.basename(transcoded_path),
                            'OriginalFileSize': self.FileManager.GetFileSizeMB(original_path),
                            'TranscodedFileSize': self.FileManager.GetFileSizeMB(transcoded_path)
                        })

            LoggingService.LogInfo(f"Found {len(failed_replacements)} failed file replacements",
                                 "FileReplacementBusinessService", "GetFailedFileReplacements")
            return failed_replacements

        except Exception as e:
            LoggingService.LogException("Exception getting failed file replacements", e,
                                     "FileReplacementBusinessService", "GetFailedFileReplacements")
            return []

    # directive: filereplacement-decompose | see FileReplacement.W1
    def ProcessFileReplacement(self, TranscodeAttemptId: int) -> Dict[str, Any]:
        """Orchestrate file replacement for an attempt; see FileReplacement.W1."""
        try:
            # allow: R12 SQL preexisting; relocate to TranscodeAttemptsRepository in follow-up
            DispositionRows = self.DatabaseManager.DatabaseService.ExecuteQuery(
                """
                SELECT Disposition, DispositionReason, FileReplaced, FileReplacedDate,
                       NewSizeBytes, OldSizeBytes, VMAF, ProfileName
                FROM TranscodeAttempts WHERE Id = %s
                """,
                (TranscodeAttemptId,),
            )
            if not DispositionRows:
                return {'Success': False, 'ErrorMessage': f'Transcode attempt {TranscodeAttemptId} not found'}
            DispositionRow = DispositionRows[0]

            Disposition = DispositionRow.get('Disposition')
            if Disposition not in ('Replace', 'BypassReplace'):
                return {
                    'Success': False,
                    'ErrorMessage': (
                        f"Refusing to replace TranscodeAttempt {TranscodeAttemptId}: "
                        f"Disposition={Disposition!r} (must be Replace or BypassReplace). "
                        f"Reason={DispositionRow.get('DispositionReason')!r}."
                    ),
                }

            if DispositionRow.get('FileReplaced'):
                return {
                    'Success': False,
                    'ErrorMessage': (
                        f"File for transcode attempt {TranscodeAttemptId} was already "
                        f"replaced on {DispositionRow.get('FileReplacedDate')}"
                    ),
                }

            transcode_attempt = self.DatabaseManager.GetTranscodeAttemptById(TranscodeAttemptId)
            if not transcode_attempt:
                return {'Success': False, 'ErrorMessage': f'Transcode attempt {TranscodeAttemptId} not found'}

            # allow: R12 SQL preexisting; relocate to TemporaryFilePathsRepository in follow-up
            file_paths_result = self.DatabaseManager.DatabaseService.ExecuteQuery(
                """
                SELECT SourceStorageRootId, SourceRelativePath,
                       OutputStorageRootId, OutputRelativePath,
                       LocalOutputPath
                FROM TemporaryFilePaths
                WHERE TranscodeAttemptId = %s
                """,
                (TranscodeAttemptId,),
            )
            if not file_paths_result:
                return {
                    'Success': False,
                    'ErrorMessage': f'No temporary file path found for transcode attempt {TranscodeAttemptId}',
                }
            FP = file_paths_result[0]
            SourceSrId = FP.get('SourceStorageRootId')
            SourceRel = FP.get('SourceRelativePath')
            OutputSrId = FP.get('OutputStorageRootId')
            OutputRel = FP.get('OutputRelativePath')
            LocalOutputPathStr = FP.get('LocalOutputPath')

            from Core.PathStorage import CanonicalFor
            if SourceSrId is None or SourceRel is None:
                return {
                    'Success': False,
                    'ErrorMessage': (
                        f'TemporaryFilePaths for attempt {TranscodeAttemptId} is '
                        f'missing SourceStorageRootId / SourceRelativePath (legacy row?). '
                        f'Cannot resolve canonical source path.'
                    ),
                }
            OriginalPath = CanonicalFor(SourceSrId, SourceRel)
            if OutputSrId is not None and OutputRel is not None:
                CanonicalNewPath = CanonicalFor(OutputSrId, OutputRel)
            else:
                CanonicalNewPath = None

            SourceMediaFileId = None
            try:
                MfRows = self.DatabaseManager.DatabaseService.ExecuteQuery(
                    "SELECT Id FROM MediaFiles WHERE StorageRootId = %s AND RelativePath = %s LIMIT 1",
                    (SourceSrId, SourceRel),
                )
                if MfRows:
                    SourceMediaFileId = MfRows[0].get('Id')
            except Exception as MfLookupEx:
                LoggingService.LogException(
                    f"MediaFile lookup by (StorageRootId={SourceSrId}, RelativePath={SourceRel}) failed",
                    MfLookupEx, "FileReplacementBusinessService", "ProcessFileReplacement",
                )

            from Core.PathStorage import Resolve as PathResolve, PathStorageError
            TranscodedPath = CanonicalNewPath
            if OutputSrId is not None and OutputRel is not None:
                try:
                    LocalTranscodedPath = PathResolve(
                        OutputSrId, OutputRel, self.WorkerName,
                        self.DatabaseManager.DatabaseService,
                    )
                except PathStorageError as ResolveEx:
                    LoggingService.LogError(
                        f"Cannot resolve output path for worker {self.WorkerName!r}: {ResolveEx}",
                        "FileReplacementBusinessService", "ProcessFileReplacement",
                    )
                    return {
                        'Success': False,
                        'ErrorMessage': f"No StorageRootResolutions row for (StorageRootId={OutputSrId}, Worker={self.WorkerName}); cannot translate output path."
                    }
            else:
                TranscodedPath = LocalOutputPathStr
                LocalTranscodedPath = self._ToLocalPath(TranscodedPath) if TranscodedPath else None

            if not LocalTranscodedPath or not self.FileManager.ValidateFileExists(LocalTranscodedPath):
                return {
                    'Success': False,
                    'ErrorMessage': f'Transcoded file not found at: {LocalTranscodedPath}',
                }

            isRemux = (transcode_attempt.ProfileName or '') in ('Remux', 'SubtitleFix')
            if (not isRemux
                and transcode_attempt.NewSizeBytes is not None
                and transcode_attempt.OldSizeBytes is not None
                and transcode_attempt.NewSizeBytes >= transcode_attempt.OldSizeBytes):
                errorMsg = (
                    f"Defense-in-depth: refusing to replace because "
                    f"NewSize ({transcode_attempt.NewSizeBytes:,}) >= "
                    f"OldSize ({transcode_attempt.OldSizeBytes:,}). "
                    f"This case should have been routed to Disposition='Discard' "
                    f"upstream -- log a bug if it reaches here."
                )
                LoggingService.LogWarning(errorMsg, "FileReplacementBusinessService", "ProcessFileReplacement")
                return {'Success': False, 'ErrorMessage': errorMsg}

            self._ArchiveOriginalFileDetails(OriginalPath, TranscodeAttemptId)

            AttemptProfileName = (transcode_attempt.ProfileName or '')
            ReplacementMode = 'Remux' if AttemptProfileName in ('Remux', 'SubtitleFix') else 'Transcode'
            from Features.FileReplacement.TranscodedOutputPlacement import TranscodedOutputPlacement
            replacement_result = TranscodedOutputPlacement(
                self.DatabaseManager, self.FileManager, WorkerName=self.WorkerName
            ).Execute(
                OriginalPath, TranscodedPath, OriginalPath,
                FFmpegCommand=getattr(transcode_attempt, 'FfpmpegCommand', None),
                SourceMediaFileId=SourceMediaFileId,
                Mode=ReplacementMode,
            )

            if replacement_result.get('Success', False):
                transcode_attempt.FileReplaced = True
                transcode_attempt.FileReplacedDate = datetime.now(timezone.utc)
                transcode_attempt.ReplacementType = (
                    'Bypass' if Disposition == 'BypassReplace' else 'Auto'
                )
                self.DatabaseManager.SaveTranscodeAttempt(transcode_attempt)

                from Features.QualityTesting.PostTranscodeDispositionService import PostTranscodeDispositionService
                PostTranscodeDispositionService().CleanupTemporaryFilePaths(TranscodeAttemptId)

                LoggingService.LogInfo(
                    f"Replaced file for TranscodeAttempt {TranscodeAttemptId} "
                    f"(Disposition={Disposition}, Reason={DispositionRow.get('DispositionReason')})",
                    "FileReplacementBusinessService", "ProcessFileReplacement",
                )

                self._NotifyJellyfinOfReplacement(
                    replacement_result.get('CanonicalOriginalPath') or OriginalPath,
                    replacement_result.get('CanonicalNewPath'),
                )

                return {
                    'Success': True,
                    'Message': 'File replacement completed successfully',
                    'OriginalFilePath': OriginalPath,
                    'TranscodedFilePath': TranscodedPath,
                    'Disposition': Disposition,
                    'DispositionReason': DispositionRow.get('DispositionReason'),
                    'VMAFScore': transcode_attempt.VMAF,
                    'StepsCompleted': replacement_result.get('StepsCompleted', []),
                }

            error_message = replacement_result.get('ErrorMessage', 'Unknown error during file replacement')

            if replacement_result.get('ComplianceGateRefused'):
                CascadeReason = replacement_result.get('CascadeReason') or 'unknown'
                try:
                    from Features.QualityTesting.PostTranscodeDispositionService import PostTranscodeDispositionService
                    PostTranscodeDispositionService().RecordComplianceGateFailure(
                        TranscodeAttemptId, CascadeReason
                    )
                except Exception as DispEx:
                    LoggingService.LogException(
                        f"Failed to record ComplianceGateFailed disposition for attempt {TranscodeAttemptId}",
                        DispEx, "FileReplacementBusinessService", "ProcessFileReplacement",
                    )
                LoggingService.LogWarning(
                    f"Compliance gate refused replace for attempt {TranscodeAttemptId}: {CascadeReason}. "
                    f"Disposition flipped to NoReplace/ComplianceGateFailed.",
                    "FileReplacementBusinessService", "ProcessFileReplacement",
                )
                return {'Success': False, 'ErrorMessage': error_message,
                        'ComplianceGateRefused': True, 'CascadeReason': CascadeReason}

            LoggingService.LogError(
                f"File replacement failed for attempt {TranscodeAttemptId}: {error_message}",
                "FileReplacementBusinessService", "ProcessFileReplacement",
            )
            return {'Success': False, 'ErrorMessage': error_message}

        except Exception as e:
            LoggingService.LogException(
                f"Exception processing file replacement for attempt {TranscodeAttemptId}", e,
                "FileReplacementBusinessService", "ProcessFileReplacement",
            )
            return {'Success': False, 'ErrorMessage': f'Exception during file replacement: {str(e)}'}

    # directive: filereplacement-decompose
    def GetFileReplacementStatus(self, TranscodeAttemptId: int) -> Dict[str, Any]:
        """Read-only: current status of file replacement for an attempt; see FileReplacement.W5."""
        try:
            transcode_attempt = self.DatabaseManager.GetTranscodeAttemptById(TranscodeAttemptId)
            if not transcode_attempt:
                return {
                    'Success': False,
                    'ErrorMessage': f'Transcode attempt {TranscodeAttemptId} not found'
                }

            vmaf_query = (
                "SELECT TranscodedFilePath FROM QualityTestingQueue "
                "WHERE TranscodeAttemptId = %s"
            )
            vmaf_result = self.DatabaseManager.DatabaseService.ExecuteQuery(vmaf_query, (TranscodeAttemptId,))

            if not vmaf_result:
                return {
                    'Success': False,
                    'ErrorMessage': f'No VMAF queue entry found for transcode attempt {TranscodeAttemptId}'
                }

            transcoded_path = vmaf_result[0]['TranscodedFilePath']
            original_exists = self.FileManager.ValidateFileExists(transcode_attempt.FilePath)
            transcoded_exists = self.FileManager.ValidateFileExists(transcoded_path)

            return {
                'Success': True,
                'TranscodeAttemptId': TranscodeAttemptId,
                'OriginalFilePath': transcode_attempt.FilePath,
                'TranscodedFilePath': transcoded_path,
                'VMAFScore': transcode_attempt.VMAF,
                'OriginalFileExists': original_exists,
                'TranscodedFileExists': transcoded_exists,
                'FileReplaced': getattr(transcode_attempt, 'FileReplaced', False),
                'FileReplacementDate': getattr(transcode_attempt, 'FileReplacementDate', None),
                'CanReplace': original_exists and transcoded_exists and transcode_attempt.VMAF and transcode_attempt.VMAF >= 90
            }

        except Exception as e:
            LoggingService.LogException(f"Exception getting file replacement status for attempt {TranscodeAttemptId}", e,
                                      "FileReplacementBusinessService", "GetFileReplacementStatus")
            return {
                'Success': False,
                'ErrorMessage': f'Exception getting status: {str(e)}'
            }

    # directive: filereplacement-decompose | see jellyfin-push-notify.C1
    def _NotifyJellyfinOfReplacement(self, CanonicalOriginalPath: str, CanonicalNewPath: str) -> None:
        """Fire-and-forget Jellyfin notify; see jellyfin-push-notify.C1."""
        try:
            from Services.JellyfinNotifyService import NotifyJellyfin
            if not CanonicalNewPath:
                return
            Updates = [{'Path': CanonicalNewPath, 'UpdateType': 'Modified'}]
            NotifyJellyfin(Updates, self.DatabaseManager.DatabaseService)
        except Exception as Ex:
            LoggingService.LogException(
                "Jellyfin notify swallowed at FileReplacement boundary",
                Ex, "FileReplacementBusinessService", "_NotifyJellyfinOfReplacement",
            )

    # directive: filereplacement-decompose
    def _ArchiveOriginalFileDetails(self, FilePath: str, TranscodeAttemptId: int) -> bool:
        """Snapshot original MediaFile row before replacement; see FileReplacement.C1."""
        try:
            LoggingService.LogFunctionEntry("_ArchiveOriginalFileDetails", "FileReplacementBusinessService",
                                          FilePath, TranscodeAttemptId)

            media_file = self.DatabaseManager.GetMediaFileByPath(FilePath)
            if not media_file:
                LoggingService.LogWarning(f"MediaFile record not found for path: {FilePath}",
                                        "FileReplacementBusinessService", "_ArchiveOriginalFileDetails")
                return False

            ArchiveId = self.DatabaseManager.SaveMediaFileArchive(media_file.Id, TranscodeAttemptId)

            if ArchiveId:
                LoggingService.LogInfo(f"Successfully archived original file details for MediaFile {media_file.Id}, Archive ID: {ArchiveId}",
                                     "FileReplacementBusinessService", "_ArchiveOriginalFileDetails")
                return True
            else:
                LoggingService.LogError(f"Failed to archive original file details for MediaFile {media_file.Id}",
                                      "FileReplacementBusinessService", "_ArchiveOriginalFileDetails")
                return False

        except Exception as e:
            LoggingService.LogException("Exception archiving original file details", e,
                                      "FileReplacementBusinessService", "_ArchiveOriginalFileDetails")
            return False
