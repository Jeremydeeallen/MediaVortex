import ntpath
from typing import Dict, Any, List, Optional
from datetime import datetime, timezone
from Models.TranscodeAttemptModel import TranscodeAttemptModel
from Repositories.DatabaseManager import DatabaseManager
from Services.FileManagerService import FileManagerService
from Core.Logging.LoggingService import LoggingService
from Core.Path import Path, Worker, PathError


# directive: filereplacement-uses-path | # see filereplacement.C7
class FileReplacementBusinessService:
    """Orchestration + read-only queries for FileReplacement; see FileReplacement.feature.md."""

    # directive: path-class-perfection | # see path.C26
    def __init__(self, DatabaseManagerInstance: DatabaseManager = None,
                 FileManagerInstance: FileManagerService = None,
                 FFprobePath: str = None, WorkerName: str = None,
                 worker: Optional[Worker] = None):
        self.DatabaseManager = DatabaseManagerInstance or DatabaseManager()
        self.FileManager = FileManagerInstance or FileManagerService(FFprobePath=FFprobePath)
        if WorkerName is None:
            import socket
            from Core.WorkerContext import WorkerContext
            Ctx = WorkerContext.Current()
            WorkerName = (Ctx.WorkerName if Ctx else None) or socket.gethostname()
        self.WorkerName = WorkerName
        self._Worker: Worker = worker if worker is not None else Worker.Current(Db=self.DatabaseManager.DatabaseService)

    # directive: path-class-perfection | # see path.C26
    def _GetWorker(self) -> Worker:
        return self._Worker

    # directive: path-class-perfection | # see path.C18
    def _GetStorageRoots(self) -> List[dict]:
        from Core.Path.PathStorageRoots import GetStorageRoots
        return GetStorageRoots()

       # directive: path-class-perfection | # see path.C18
    def _GetPrefixMap(self) -> Dict[int, str]:
        from Core.Path.PathStorageRoots import GetPrefixMap
        return GetPrefixMap()  

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

    # directive: filereplacement-decompose | see FileReplacement.W1 | # see transcode.ST9
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
            if Disposition != 'Replace':
                return {
                    'Success': False,
                    'ErrorMessage': (
                        f"Refusing to replace TranscodeAttempt {TranscodeAttemptId}: "
                        f"Disposition={Disposition!r} (must be Replace). "
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
                       OutputStorageRootId, OutputRelativePath
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

            if SourceSrId is None or SourceRel is None:
                return {
                    'Success': False,
                    'ErrorMessage': (
                        f'TemporaryFilePaths for attempt {TranscodeAttemptId} is '
                        f'missing SourceStorageRootId / SourceRelativePath. '
                        f'Cannot resolve canonical source path.'
                    ),
                }
            if OutputSrId is None or OutputRel is None:
                return {
                    'Success': False,
                    'ErrorMessage': (
                        f'TemporaryFilePaths for attempt {TranscodeAttemptId} is '
                        f'missing OutputStorageRootId / OutputRelativePath. '
                        f'Cannot resolve canonical output path.'
                    ),
                }
            OriginalPath = Path(SourceSrId, SourceRel).CanonicalDisplay(self._GetPrefixMap())
            CanonicalNewPath = Path(OutputSrId, OutputRel).CanonicalDisplay(self._GetPrefixMap())

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

            TranscodedPath = CanonicalNewPath
            try:
                OutPathObj = Path(OutputSrId, OutputRel)
                LocalTranscodedPath = OutPathObj.Resolve(self._GetWorker())
            except PathError as ResolveEx:
                LoggingService.LogError(
                    f"Cannot resolve output path for worker {self.WorkerName!r}: {ResolveEx}",
                    "FileReplacementBusinessService", "ProcessFileReplacement",
                )
                return {
                    'Success': False,
                    'ErrorMessage': f"No StorageRootResolutions row for (StorageRootId={OutputSrId}, Worker={self.WorkerName}); cannot translate output path."
                }

            if not LocalTranscodedPath or not self.FileManager.ValidateFileExists(LocalTranscodedPath):
                return {
                    'Success': False,
                    'ErrorMessage': f'Transcoded file not found at: {LocalTranscodedPath}',
                }

            # directive: transcode-flow-canonical | # see transcode.ST9
            from Features.TranscodeJob import ProcessingModeMetadata
            AttemptMode = (transcode_attempt.ProfileName or 'Transcode')
            ModeMeta = ProcessingModeMetadata.GetOrDefault(AttemptMode)
            isRemux = not ModeMeta['RequiresProfileGates']
            EffectiveOldBytes = transcode_attempt.OldSizeBytes
            if (not isRemux) and (EffectiveOldBytes is None or EffectiveOldBytes <= 0):
                try:
                    from Core.Path.Path import Path as _Path
                    SourceLocalPath = _Path(SourceSrId, SourceRel).Resolve(self._GetWorker())
                    if SourceLocalPath and self.FileManager.ValidateFileExists(SourceLocalPath):
                        from Core.Path.LocalPath import LocalGetSize
                        EffectiveOldBytes = LocalGetSize(SourceLocalPath)
                        LoggingService.LogInfo(
                            f"Defense-in-depth fallback: TranscodeAttempt {TranscodeAttemptId} OldSizeBytes={transcode_attempt.OldSizeBytes!r}; resolved actual source size to {EffectiveOldBytes:,} bytes",
                            "FileReplacementBusinessService", "ProcessFileReplacement",
                        )
                except Exception as SizeEx:
                    LoggingService.LogException(
                        f"Defense-in-depth fallback: could not resolve source size for TranscodeAttempt {TranscodeAttemptId}",
                        SizeEx, "FileReplacementBusinessService", "ProcessFileReplacement",
                    )

            if (not isRemux
                and transcode_attempt.NewSizeBytes is not None
                and EffectiveOldBytes is not None and EffectiveOldBytes > 0
                and transcode_attempt.NewSizeBytes >= EffectiveOldBytes):
                errorMsg = (
                    f"Defense-in-depth: refusing to replace because "
                    f"NewSize ({transcode_attempt.NewSizeBytes:,}) >= "
                    f"OldSize ({EffectiveOldBytes:,}). "
                    f"This case should have been routed to Disposition='Reject' "
                    f"upstream -- log a bug if it reaches here."
                )
                LoggingService.LogWarning(errorMsg, "FileReplacementBusinessService", "ProcessFileReplacement")
                return {'Success': False, 'ErrorMessage': errorMsg}

            self._ArchiveOriginalFileDetails(OriginalPath, TranscodeAttemptId)

            from Features.FileReplacement.TranscodedOutputPlacement import TranscodedOutputPlacement
            replacement_result = TranscodedOutputPlacement(
                self.DatabaseManager, self.FileManager, WorkerName=self.WorkerName
            ).Execute(
                OriginalPath, TranscodedPath, OriginalPath,
                FFmpegCommand=getattr(transcode_attempt, 'FfpmpegCommand', None),
                SourceMediaFileId=SourceMediaFileId,
                Mode=AttemptMode,
                RunComplianceGate=ModeMeta['RequiresProfileGates'],
            )

            if replacement_result.get('Success', False):
                transcode_attempt.FileReplaced = True
                transcode_attempt.FileReplacedDate = datetime.now(timezone.utc)
                transcode_attempt.ReplacementType = 'Auto'
                self.DatabaseManager.SaveTranscodeAttempt(transcode_attempt)

                # directive: perfect-solid-transcode-pipeline | # see perfect-solid-transcode-pipeline.C11
                from Features.QualityTesting.Disposition.AttemptCleanupService import AttemptCleanupService
                from Core.Database.DatabaseService import DatabaseService
                AttemptCleanupService(DatabaseService()).Cleanup(TranscodeAttemptId)

                LoggingService.LogInfo(
                    f"Replaced file for TranscodeAttempt {TranscodeAttemptId} "
                    f"(Disposition={Disposition}, Reason={DispositionRow.get('DispositionReason')})",
                    "FileReplacementBusinessService", "ProcessFileReplacement",
                )

                try:  # see jellyfin-push-notify.C1
                    from Services.JellyfinNotifyService import NotifyJellyfin
                    _NewPath = replacement_result.get('CanonicalNewPath')
                    if _NewPath:
                        NotifyJellyfin([{'Path': _NewPath, 'UpdateType': 'Modified'}], self.DatabaseManager.DatabaseService)
                except Exception as NfEx:
                    LoggingService.LogException(
                        "Jellyfin notify swallowed at ProcessFileReplacement boundary",
                        NfEx, "FileReplacementBusinessService", "ProcessFileReplacement",
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
                    # directive: perfect-solid-transcode-pipeline | # see perfect-solid-transcode-pipeline.C9
                    from Features.QualityTesting.Disposition.ComplianceFailureRecorder import ComplianceFailureRecorder
                    from Features.QualityTesting.Disposition.AttemptCleanupService import AttemptCleanupService
                    from Core.Database.DatabaseService import DatabaseService
                    DbSvc = DatabaseService()
                    Recorder = ComplianceFailureRecorder(DatabaseService=DbSvc, AttemptCleanupService=AttemptCleanupService(DbSvc))
                    Recorder.Record(TranscodeAttemptId, CascadeReason)
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

            # read threshold fresh from DB per db-is-authority.md; see transcode.ST9
            ThresholdRows = self.DatabaseManager.DatabaseService.ExecuteQuery(
                "SELECT FileReplacementCanReplaceThreshold FROM PostTranscodeGateConfig WHERE Id = 1"
            )
            CanReplaceThreshold = float(ThresholdRows[0]['FileReplacementCanReplaceThreshold']) if ThresholdRows else 90.0

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
                'CanReplace': original_exists and transcoded_exists and transcode_attempt.VMAF and transcode_attempt.VMAF >= CanReplaceThreshold
            }

        except Exception as e:
            LoggingService.LogException(f"Exception getting file replacement status for attempt {TranscodeAttemptId}", e,
                                      "FileReplacementBusinessService", "GetFileReplacementStatus")
            return {
                'Success': False,
                'ErrorMessage': f'Exception getting status: {str(e)}'
            }

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
