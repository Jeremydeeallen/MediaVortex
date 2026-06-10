import os
from typing import Optional
from Core.Logging.LoggingService import LoggingService
from Core.Path import Path, Worker, PathError
from Core.Path.LocalPath import LocalExists


# directive: perfect-solid-transcode-pipeline-phase3 | # see perfect-solid-transcode-pipeline-phase3.C10
class TemporaryFilePathsService:
    """Single-responsibility service for TemporaryFilePaths CRUD + scratch cleanup."""

    # directive: perfect-solid-transcode-pipeline-phase3 | # see perfect-solid-transcode-pipeline-phase3.C10
    def __init__(self, DatabaseManager, WorkerName: str = None):
        """Inject DatabaseManager and optional WorkerName (needed for local-scratch cleanup)."""
        self.DatabaseManager = DatabaseManager
        self.WorkerName = WorkerName

    # directive: perfect-solid-transcode-pipeline-phase3 | # see perfect-solid-transcode-pipeline-phase3.C10
    def CreateRecord(self, TranscodeAttemptId: int, SourceStorageRootId: int, SourceRelativePath: str, OutputStorageRootId: Optional[int] = None, OutputRelativePath: Optional[str] = None, LocalSourcePath: Optional[str] = None, LocalOutputPath: Optional[str] = None) -> Optional[int]:
        """Route TemporaryFilePaths insert through QualityTestRepository; populate worker-local staging paths when staging is active."""
        try:
            LoggingService.LogFunctionEntry("CreateRecord", "TemporaryFilePathsService",
                                          TranscodeAttemptId, SourceStorageRootId, SourceRelativePath,
                                          OutputStorageRootId, OutputRelativePath, LocalSourcePath, LocalOutputPath)

            from Features.QualityTesting.QualityTestRepository import QualityTestRepository
            _Repo = QualityTestRepository(self.DatabaseManager.DatabaseService)
            TemporaryFilePathId = _Repo.CreateTemporaryFilePath(
                TranscodeAttemptId, SourceStorageRootId, SourceRelativePath,
                OutputStorageRootId, OutputRelativePath,
                LocalSourcePath, LocalOutputPath,
            )

            if TemporaryFilePathId:
                LoggingService.LogInfo(f"Successfully created TemporaryFilePath record {TemporaryFilePathId} for TranscodeAttempt {TranscodeAttemptId}",
                                     "TemporaryFilePathsService", "CreateRecord")
                return TemporaryFilePathId
            else:
                LoggingService.LogError(f"Failed to create TemporaryFilePath record for TranscodeAttempt {TranscodeAttemptId}",
                                      "TemporaryFilePathsService", "CreateRecord")
                return None

        except Exception as e:
            LoggingService.LogException("Exception creating TemporaryFilePath record", e,
                                      "TemporaryFilePathsService", "CreateRecord")
            return None

    # directive: perfect-solid-transcode-pipeline-phase3 | # see perfect-solid-transcode-pipeline-phase3.C10
    def HandlePreparationFailure(self, TranscodeAttemptId: int, ErrorMessage: str) -> None:
        """Mark file-prep failure on the attempt + clean up partial paths."""
        try:
            LoggingService.LogFunctionEntry("HandlePreparationFailure", "TemporaryFilePathsService",
                                          TranscodeAttemptId, ErrorMessage)

            self.DatabaseManager.DeleteTemporaryFilePath(TranscodeAttemptId)

            LoggingService.LogError(f"File preparation failed for TranscodeAttempt {TranscodeAttemptId}: {ErrorMessage}",
                                  "TemporaryFilePathsService", "HandlePreparationFailure")

        except Exception as e:
            LoggingService.LogException("Exception handling file preparation failure", e,
                                      "TemporaryFilePathsService", "HandlePreparationFailure")

    # directive: perfect-solid-transcode-pipeline-phase3 | # see perfect-solid-transcode-pipeline-phase3.C10
    def CleanupFailedAttempt(self, TranscodeAttemptId: int) -> None:
        """Cleanup orphaned .inprogress + TFP rows for a failed attempt."""
        try:
            LoggingService.LogInfo(f"Cleaning up files for failed TranscodeAttempt {TranscodeAttemptId}",
                                 "TemporaryFilePathsService", "CleanupFailedAttempt")

            # directive: path-schema-migration | # see path.S8
            from Features.QualityTesting.QualityTestRepository import QualityTestRepository
            TemporaryFilePathRecord = QualityTestRepository(self.DatabaseManager.DatabaseService).GetTemporaryFilePath(TranscodeAttemptId)

            if TemporaryFilePathRecord:
                # directive: path-perfect-implementation | # see path.S11
                OutSid = TemporaryFilePathRecord.get('OutputStorageRootId')
                OutRel = TemporaryFilePathRecord.get('OutputRelativePath')
                ActualPath = None
                if OutSid is not None and OutRel is not None:
                    try:
                        ActualPath = Path(OutSid, OutRel).Resolve(Worker.Current(Db=self.DatabaseManager.DatabaseService))
                    except PathError:
                        ActualPath = None
                if ActualPath:
                    if LocalExists(ActualPath):
                        try:
                            os.remove(ActualPath)
                            LoggingService.LogInfo(f"Deleted partial output file: {ActualPath}",
                                                 "TemporaryFilePathsService", "CleanupFailedAttempt")
                        except Exception as e:
                            LoggingService.LogWarning(f"Failed to delete partial output file {ActualPath}: {str(e)}",
                                                    "TemporaryFilePathsService", "CleanupFailedAttempt")
                    else:
                        LoggingService.LogInfo(f"Partial output file does not exist (already cleaned up): {ActualPath}",
                                             "TemporaryFilePathsService", "CleanupFailedAttempt")

                # directive: local-staging | # see local-staging.C11
                if TemporaryFilePathRecord.get('IsStaged'):
                    from Features.TranscodeJob.LocalStagingService import LocalStagingService
                    Staging = LocalStagingService(self.DatabaseManager.DatabaseService)
                    Staging.Cleanup(TemporaryFilePathRecord.get('LocalSourcePath'))
                    Staging.Cleanup(TemporaryFilePathRecord.get('LocalOutputPath'))

                self.DatabaseManager.DeleteTemporaryFilePath(TranscodeAttemptId)
            else:
                LoggingService.LogInfo(f"No TemporaryFilePaths record found for TranscodeAttempt {TranscodeAttemptId} (nothing to clean up)",
                                     "TemporaryFilePathsService", "CleanupFailedAttempt")

        except Exception as e:
            LoggingService.LogException(f"Exception cleaning up failed attempt files for TranscodeAttempt {TranscodeAttemptId}",
                                       e, "TemporaryFilePathsService", "CleanupFailedAttempt")

    # directive: perfect-solid-transcode-pipeline-phase3 | # see perfect-solid-transcode-pipeline-phase3.C10
    def CleanupLocalScratch(self, MediaFileId: int) -> bool:
        """Cleanup the worker-local scratch dir for the MediaFileId; returns True iff any file was removed."""
        try:
            from Features.TranscodeJob.LocalStagingService import LocalStagingService
            return LocalStagingService(self.DatabaseManager.DatabaseService).CleanupJobScratchDir(self.WorkerName, MediaFileId)
        except Exception as Ex:
            LoggingService.LogException(f"CleanupLocalScratch failed for MediaFileId={MediaFileId}", Ex, "TemporaryFilePathsService", "CleanupLocalScratch")
            return False
