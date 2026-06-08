import ntpath
from typing import Optional, List, Dict, Any
from datetime import datetime, timezone
from Core.Database.BaseRepository import BaseRepository
from Core.Logging.LoggingService import LoggingService
from Features.QualityTesting.Models.QualityTestResultModel import QualityTestResultModel
# directive: path-schema-migration | # see path.S8
from Core.Path.Path import Path, PathError
from Core.Path.PathStorageRoots import GetStorageRoots, GetPrefixMap


# directive: path-schema-migration | # see path.S8
def _SafeCanonical(StorageRootId, RelativePath) -> str:
    if StorageRootId is None:
        return ""
    try:
        return Path(StorageRootId, RelativePath or "").CanonicalDisplay(GetPrefixMap())
    except PathError:
        return ""


# directive: path-schema-migration | # see path.S8
class QualityTestRepository(BaseRepository):
    """Repository for quality test CRUD operations."""

    # ─── QualityTestingQueue Methods ───────────────────────────────────────

    # directive: path-schema-migration | # see path.S8
    def GetQualityTestJob(self, JobId: int) -> Optional[Dict[str, Any]]:
        """Get a quality test job by ID."""
        try:
            Query = (
                "SELECT Id, TranscodeAttemptId, OriginalFilePath, LocalSourcePath, TranscodedFilePath, "
                "DateAdded, DateStarted, DateCompleted "
                "FROM QualityTestingQueue WHERE Id = %s"
            )
            Rows = self.ExecuteQuery(Query, (JobId,))

            if Rows:
                Row = Rows[0]
                return {
                    "Id": Row["Id"],
                    "TranscodeAttemptId": Row["TranscodeAttemptId"],
                    "OriginalFilePath": Row["OriginalFilePath"],
                    "LocalSourcePath": Row["LocalSourcePath"],
                    "TranscodedFilePath": Row["TranscodedFilePath"],
                    "DateAdded": Row["DateAdded"],
                    "DateStarted": Row["DateStarted"],
                    "DateCompleted": Row["DateCompleted"]
                }
            return None

        except Exception as e:
            LoggingService.LogException("Exception getting quality test job", e, "QualityTestRepository", "GetQualityTestJob")
            return None

    # directive: path-schema-migration | # see path.S8
    def GetQualityTestQueue(self) -> List[Dict[str, Any]]:
        """Get all quality test jobs in queue ordered by date."""
        try:
            Query = (
                "SELECT Id, TranscodeAttemptId, OriginalFilePath, TranscodedFilePath, LocalSourcePath, "
                "DateAdded, DateStarted, DateCompleted "
                "FROM QualityTestingQueue "
                "ORDER BY DateAdded ASC"
            )
            Rows = self.ExecuteQuery(Query)
            return list(Rows)

        except Exception as e:
            LoggingService.LogException("Exception getting quality test queue", e, "QualityTestRepository", "GetQualityTestQueue")
            return []

    # directive: path-schema-migration | # see path.S8
    def CreateQualityTestQueueEntry(self, TranscodeAttemptId: int, OriginalFilePath: str, LocalSourcePath: str, TranscodedFilePath: str) -> Optional[int]:
        """Create a new quality test queue entry. QualityTestingQueue path columns are NOT in the drop list."""
        try:
            LoggingService.LogFunctionEntry("CreateQualityTestQueueEntry", "QualityTestRepository",
                                          TranscodeAttemptId, OriginalFilePath, LocalSourcePath, TranscodedFilePath)

            Query = (
                "INSERT INTO QualityTestingQueue ("
                "TranscodeAttemptId, OriginalFilePath, TranscodedFilePath, LocalSourcePath, "
                "DateAdded, DateStarted, DateCompleted"
                ") VALUES (%s, %s, %s, %s, NOW(), %s, %s) "
                "RETURNING Id"
            )

            Params = (
                TranscodeAttemptId,
                OriginalFilePath,
                TranscodedFilePath,
                LocalSourcePath,
                None,
                None
            )

            RowsAffected = self.ExecuteNonQuery(Query, Params)

            if RowsAffected > 0:
                JobId = self.GetLastInsertId()
                LoggingService.LogInfo(f"Created quality test queue entry with ID {JobId} for TranscodeAttempt {TranscodeAttemptId}",
                                     "QualityTestRepository", "CreateQualityTestQueueEntry")
                return JobId
            else:
                LoggingService.LogError(f"Failed to create quality test queue entry for TranscodeAttempt {TranscodeAttemptId}",
                                      "QualityTestRepository", "CreateQualityTestQueueEntry")
                return None

        except Exception as e:
            LoggingService.LogException("Exception creating quality test queue entry", e, "QualityTestRepository", "CreateQualityTestQueueEntry")
            return None

    # directive: path-schema-migration | # see path.S8
    def DeleteQualityTestQueueItem(self, JobId: int) -> bool:
        """Delete a job from the quality testing queue."""
        try:
            LoggingService.LogFunctionEntry("DeleteQualityTestQueueItem", "QualityTestRepository", JobId)

            Query = "DELETE FROM QualityTestingQueue WHERE Id = %s"
            AffectedRows = self.ExecuteNonQuery(Query, (JobId,))

            if AffectedRows > 0:
                LoggingService.LogInfo(f"Deleted QualityTestingQueue item {JobId}", "QualityTestRepository", "DeleteQualityTestQueueItem")
                return True
            else:
                LoggingService.LogWarning(f"No rows deleted for QualityTestingQueue item {JobId}",
                                         "QualityTestRepository", "DeleteQualityTestQueueItem")
                return False

        except Exception as e:
            LoggingService.LogException("Error deleting quality test queue item", e,
                                       "QualityTestRepository", "DeleteQualityTestQueueItem")
            return False

    # directive: path-schema-migration | # see path.S8
    def RemoveFromQualityTestQueue(self, JobId: int) -> bool:
        """Remove completed job from QualityTestingQueue (revolving door)."""
        try:
            Query = "DELETE FROM QualityTestingQueue WHERE Id = %s"
            RowsAffected = self.ExecuteNonQuery(Query, (JobId,))
            if RowsAffected > 0:
                LoggingService.LogInfo(f"Successfully removed job {JobId} from quality test queue", "QualityTestRepository", "RemoveFromQualityTestQueue")
                return True
            else:
                LoggingService.LogError(f"Failed to remove job {JobId} from quality test queue - no rows affected", "QualityTestRepository", "RemoveFromQualityTestQueue")
                return False

        except Exception as e:
            LoggingService.LogException("Exception removing from quality test queue", e, "QualityTestRepository", "RemoveFromQualityTestQueue")
            return False

    # ─── QualityTestResults Methods ────────────────────────────────────────

    # directive: path-schema-migration | # see path.S8
    def CreateQualityTestResult(self, TranscodeAttemptId: int, Status: str = "Running", TestDate: datetime = None) -> int:
        """Create a quality test result record at the start of testing."""
        try:
            LoggingService.LogFunctionEntry("CreateQualityTestResult", "QualityTestRepository", TranscodeAttemptId, Status)

            Result = QualityTestResultModel(
                TranscodeAttemptId=TranscodeAttemptId,
                Status=Status,
                DateTested=TestDate or datetime.now(timezone.utc),
                VMAFScore=0.0 if Status == "Running" else None,
                ErrorMessage=None
            )

            CheckQuery = "SELECT Id FROM TranscodeAttempts WHERE Id = %s"
            CheckResult = self.ExecuteQuery(CheckQuery, (TranscodeAttemptId,))

            if not CheckResult:
                LoggingService.LogError(
                    f"TranscodeAttemptId {TranscodeAttemptId} does not exist in TranscodeAttempts table",
                    "QualityTestRepository", "CreateQualityTestResult"
                )
                return 0

            Query = (
                "INSERT INTO QualityTestResults "
                "(TranscodeAttemptId, TestDuration, PassesThreshold, Rank, ErrorMessage, DateTested, FFmpegCommand, Status, VMAFScore) "
                "VALUES (%s, %s, %s, %s, %s, NOW(), %s, %s, %s) "
                "RETURNING Id"
            )

            Params = (
                Result.TranscodeAttemptId,
                0.0,
                False,
                0,
                Result.ErrorMessage,
                "",
                Result.Status,
                Result.VMAFScore
            )

            LoggingService.LogInfo(f"Inserting QualityTestResult with params: {Params}", "QualityTestRepository", "CreateQualityTestResult")

            try:
                AffectedRows = self.ExecuteNonQuery(Query, Params)
                ResultId = self.GetLastInsertId()

                if ResultId > 0:
                    LoggingService.LogInfo(f"Created QualityTestResult {ResultId} for TranscodeAttempt {TranscodeAttemptId}",
                                          "QualityTestRepository", "CreateQualityTestResult")
                    return ResultId
                else:
                    LoggingService.LogError(
                        f"INSERT failed - no record ID returned. Query: {Query}, Params: {Params}, ParamCount: {len(Params)}, RowCount: {AffectedRows}",
                        "QualityTestRepository", "CreateQualityTestResult"
                    )
                    return 0
            except Exception as e:
                LoggingService.LogException(
                    f"Database error during INSERT. Query: {Query}, Params: {Params}, ParamCount: {len(Params)}",
                    e, "QualityTestRepository", "CreateQualityTestResult"
                )
                return 0

        except Exception as e:
            LoggingService.LogException("Error creating quality test result", e,
                                       "QualityTestRepository", "CreateQualityTestResult")
            return 0

    # directive: path-schema-migration | # see path.S8
    def UpdateQualityTestResultFailure(self, ResultId: int, ErrorMessage: str) -> bool:
        """Update a quality test result with failure details."""
        try:
            LoggingService.LogFunctionEntry("UpdateQualityTestResultFailure", "QualityTestRepository", ResultId, ErrorMessage)

            Query = "UPDATE QualityTestResults SET Status = 'Failed', ErrorMessage = %s WHERE Id = %s"
            AffectedRows = self.ExecuteNonQuery(Query, (ErrorMessage, ResultId))

            if AffectedRows > 0:
                LoggingService.LogInfo(f"Updated QualityTestResult {ResultId} with failure status", "QualityTestRepository", "UpdateQualityTestResultFailure")
                return True
            else:
                LoggingService.LogWarning(f"No rows updated for QualityTestResult {ResultId}",
                                         "QualityTestRepository", "UpdateQualityTestResultFailure")
                return False

        except Exception as e:
            LoggingService.LogException("Error updating quality test failure", e,
                                       "QualityTestRepository", "UpdateQualityTestResultFailure")
            return False

    # directive: path-schema-migration | # see path.S8
    def GetQualityTestResults(self, Limit: int = 10, Offset: int = 0) -> List[Dict[str, Any]]:
        """Get recent quality test results joined with TranscodeAttempts."""
        try:
            Query = (
                "SELECT "
                "qtr.Id, qtr.TranscodeAttemptId, qtr.VMAFScore, "
                "qtr.TestDuration, qtr.PassesThreshold, qtr.Rank, qtr.ErrorMessage, qtr.DateTested, "
                "qtr.FFmpegCommand, qtr.Status, "
                "ta.ProfileName, ta.StorageRootId AS TaStorageRootId, ta.RelativePath AS TaRelativePath, "
                "ta.OldSizeBytes, ta.NewSizeBytes, ta.SizeReductionBytes, "
                "ta.SizeReductionPercent, ta.TranscodeDurationSeconds, ta.ProfileName as TranscodeProfileName, "
                "ta.Quality, ta.AttemptDate, ta.NewSizeBytes as FileSize, "
                "ta.FileReplaced, ta.FileReplacedDate, ta.ReplacementType, "
                "tfp.SourceStorageRootId, tfp.SourceRelativePath, "
                "tfp.OutputStorageRootId, tfp.OutputRelativePath "
                "FROM QualityTestResults qtr "
                "LEFT JOIN TranscodeAttempts ta ON qtr.TranscodeAttemptId = ta.Id "
                "LEFT JOIN TemporaryFilePaths tfp ON qtr.TranscodeAttemptId = tfp.TranscodeAttemptId "
                "ORDER BY qtr.DateTested DESC "
                "LIMIT %s OFFSET %s"
            )
            Rows = self.ExecuteQuery(Query, (Limit, Offset))

            Results = []
            for Row in Rows:
                FilePath = _SafeCanonical(Row.get("TaStorageRootId"), Row.get("TaRelativePath"))
                TranscodedFilePath = _SafeCanonical(Row.get("OutputStorageRootId"), Row.get("OutputRelativePath"))
                LocalSourcePath = _SafeCanonical(Row.get("SourceStorageRootId"), Row.get("SourceRelativePath"))
                TranscodedFileName = ntpath.basename(TranscodedFilePath) if TranscodedFilePath else None

                Results.append({
                    "Id": Row["Id"],
                    "TranscodeAttemptId": Row["TranscodeAttemptId"],
                    "VMAFScore": Row["VMAFScore"],
                    "ProfileName": Row["ProfileName"],
                    "FileSize": Row["FileSize"],
                    "TestDuration": Row["TestDuration"],
                    "PassesThreshold": Row["PassesThreshold"],
                    "Rank": Row["Rank"],
                    "ErrorMessage": Row["ErrorMessage"],
                    "DateTested": Row["DateTested"],
                    "FFmpegCommand": Row["FFmpegCommand"],
                    "Status": Row["Status"],
                    "FilePath": FilePath,
                    "TranscodedFilePath": TranscodedFilePath,
                    "TranscodedFileName": TranscodedFileName,
                    "LocalSourcePath": LocalSourcePath,
                    "OldSizeBytes": Row["OldSizeBytes"],
                    "NewSizeBytes": Row["NewSizeBytes"],
                    "SizeReductionBytes": Row["SizeReductionBytes"],
                    "SizeReductionPercent": Row["SizeReductionPercent"],
                    "TranscodeDurationSeconds": Row["TranscodeDurationSeconds"],
                    "Quality": Row["Quality"],
                    "TranscodeProfileName": Row["TranscodeProfileName"],
                    "AttemptDate": Row["AttemptDate"],
                    "FileReplaced": Row["FileReplaced"],
                    "FileReplacedDate": Row["FileReplacedDate"],
                    "ReplacementType": Row["ReplacementType"],
                    "Success": Row["PassesThreshold"] and not Row["ErrorMessage"]
                })
            return Results

        except Exception as e:
            LoggingService.LogException("Exception getting quality test results", e, "QualityTestRepository", "GetQualityTestResults")
            return []

    # directive: path-schema-migration | # see path.S8
    def GetQualityTestResultsCount(self) -> int:
        """Get total count of quality test results."""
        try:
            Query = "SELECT COUNT(*) as TotalCount FROM QualityTestResults"
            Result = self.ExecuteQuery(Query)

            if Result:
                return Result[0]['totalcount']
            return 0

        except Exception as e:
            LoggingService.LogException("Exception getting quality test results count", e, "QualityTestRepository", "GetQualityTestResultsCount")
            return 0

    # ─── QualityTestProgress Methods ───────────────────────────────────────

    # directive: path-schema-migration | # see path.S8
    def SaveQualityTestProgress(self, TranscodeAttemptId: int, ProgressData: Dict[str, Any]) -> bool:
        """Save quality test progress - updates existing record or creates new one."""
        try:
            CheckQuery = "SELECT Id FROM QualityTestProgress WHERE TranscodeAttemptId = %s"
            ExistingRecords = self.ExecuteQuery(CheckQuery, (TranscodeAttemptId,))

            if ExistingRecords:
                Query = (
                    "UPDATE QualityTestProgress SET "
                    "Status = %s, ProgressPercentage = %s, CurrentStep = %s, "
                    "UpdatedAt = NOW(), CurrentTime = %s, CurrentFrame = %s, "
                    "ProcessingSpeed = %s, ETA = %s "
                    "WHERE TranscodeAttemptId = %s"
                )
                Parameters = (
                    ProgressData.get('Status', 'Running'),
                    ProgressData.get('ProgressPercentage', 0),
                    ProgressData.get('CurrentStep', 'Processing'),
                    ProgressData.get('CurrentTime'),
                    ProgressData.get('CurrentFrame', 0),
                    ProgressData.get('ProcessingSpeed'),
                    ProgressData.get('ETA'),
                    TranscodeAttemptId
                )
            else:
                Query = (
                    "INSERT INTO QualityTestProgress "
                    "(TranscodeAttemptId, Status, ProgressPercentage, CurrentStep, "
                    "StartTime, UpdatedAt, CreatedAt, CurrentTime, CurrentFrame, "
                    "ProcessingSpeed, ETA) "
                    "VALUES (%s, %s, %s, %s, %s, NOW(), NOW(), "
                    "%s, %s, %s, %s)"
                )
                Parameters = (
                    TranscodeAttemptId,
                    ProgressData.get('Status', 'Running'),
                    ProgressData.get('ProgressPercentage', 0),
                    ProgressData.get('CurrentStep', 'Processing'),
                    ProgressData.get('StartTime'),
                    ProgressData.get('CurrentTime'),
                    ProgressData.get('CurrentFrame', 0),
                    ProgressData.get('ProcessingSpeed'),
                    ProgressData.get('ETA')
                )

            RowsAffected = self.ExecuteNonQuery(Query, Parameters)
            return RowsAffected > 0

        except Exception as e:
            LoggingService.LogException("Exception saving quality test progress", e, "QualityTestRepository", "SaveQualityTestProgress")
            return False

    # directive: path-schema-migration | # see path.S8
    def GetRunningQualityTestProgress(self) -> list:
        """One row per QualityTestService claim in ActiveJobs; orphan claims carry NULL progress fields."""
        # see activity-dashboard-improvements.C19
        try:
            Query = (
                "SELECT "
                "qtq.TranscodeAttemptId AS TranscodeAttemptId, "
                "aj.WorkerName, "
                "aj.StartedAt AS ClaimedAt, "
                "EXTRACT(EPOCH FROM (NOW() - aj.StartedAt))::int AS ClaimAgeSec, "
                "qtp.Id, qtp.Status, qtp.ProgressPercentage, qtp.CurrentStep, qtp.CurrentFrame, "
                "qtp.CurrentTime, qtp.ProcessingSpeed, qtp.ETA, qtp.StartTime, qtp.UpdatedAt, "
                "qtp.CurrentFps, qtp.AverageFps, qtp.EtaSeconds, "
                "qtq.OriginalFilePath, qtq.TranscodedFilePath, qtq.LocalSourcePath, "
                "ta.StorageRootId AS TaStorageRootId, ta.RelativePath AS TaRelativePath, "
                "ta.OldSizeBytes, ta.NewSizeBytes "
                "FROM ActiveJobs aj "
                "LEFT JOIN QualityTestingQueue qtq ON qtq.Id = aj.QueueId "
                "LEFT JOIN QualityTestProgress qtp "
                "ON qtp.TranscodeAttemptId = qtq.TranscodeAttemptId AND qtp.Status = 'Processing' "
                "LEFT JOIN TranscodeAttempts ta ON ta.Id = qtq.TranscodeAttemptId "
                "WHERE aj.ServiceName = 'QualityTestService' "
                "ORDER BY aj.StartedAt DESC"
            )
            Rows = self.ExecuteQuery(Query)
            Results = []
            for Row in Rows or []:
                TaFilePath = _SafeCanonical(Row.get("TaStorageRootId"), Row.get("TaRelativePath"))
                OriginalPath = Row.get("OriginalFilePath") or TaFilePath
                FileName = ntpath.basename(OriginalPath) if OriginalPath else f"TranscodeAttempt_{Row['TranscodeAttemptId']}"
                Results.append({
                    "Id": Row.get("Id"),
                    "TranscodeAttemptId": Row["TranscodeAttemptId"],
                    "WorkerName": Row.get("WorkerName"),
                    "ClaimedBy": Row.get("WorkerName"),
                    "ClaimedAt": Row.get("ClaimedAt"),
                    "ClaimAgeSec": Row.get("ClaimAgeSec"),
                    "Status": Row.get("Status"),
                    "ProgressPercentage": Row.get("ProgressPercentage"),
                    "CurrentStep": Row.get("CurrentStep"),
                    "CurrentFrame": Row.get("CurrentFrame"),
                    "CurrentTime": Row.get("CurrentTime"),
                    "ProcessingSpeed": Row.get("ProcessingSpeed"),
                    "ETA": Row.get("ETA"),
                    "StartTime": Row.get("StartTime"),
                    "UpdatedAt": Row.get("UpdatedAt"),
                    "CurrentFps": Row.get("CurrentFps"),
                    "AverageFps": Row.get("AverageFps"),
                    "EtaSeconds": Row.get("EtaSeconds"),
                    "FileName": FileName,
                    "OriginalFilePath": OriginalPath,
                    "TranscodedFilePath": Row.get("TranscodedFilePath"),
                    "LocalSourcePath": Row.get("LocalSourcePath"),
                    "OldSizeBytes": Row.get("OldSizeBytes"),
                    "NewSizeBytes": Row.get("NewSizeBytes"),
                    "EndTime": None,
                    "ErrorMessage": None,
                })
            return Results

        except Exception as e:
            LoggingService.LogException("Exception getting running quality test progress", e, "QualityTestRepository", "GetRunningQualityTestProgress")
            return []

    # ─── Cleanup / Deletion Methods ────────────────────────────────────────

    # directive: path-schema-migration | # see path.S8
    def DeleteQualityTestRecordsByAttemptId(self, TranscodeAttemptId: int) -> bool:
        """Delete existing quality test records for a specific transcode attempt."""
        try:
            LoggingService.LogFunctionEntry("DeleteQualityTestRecordsByAttemptId", "QualityTestRepository", TranscodeAttemptId)

            QueueQuery = "DELETE FROM QualityTestingQueue WHERE TranscodeAttemptId = %s"
            QueueRowsAffected = self.ExecuteNonQuery(QueueQuery, (TranscodeAttemptId,))

            ProgressQuery = "DELETE FROM QualityTestProgress WHERE TranscodeAttemptId = %s"
            ProgressRowsAffected = self.ExecuteNonQuery(ProgressQuery, (TranscodeAttemptId,))

            TotalRowsAffected = QueueRowsAffected + ProgressRowsAffected

            if TotalRowsAffected > 0:
                LoggingService.LogInfo(f"Deleted {TotalRowsAffected} quality test records for TranscodeAttempt {TranscodeAttemptId} "
                                     f"(Queue: {QueueRowsAffected}, Progress: {ProgressRowsAffected})",
                                     "QualityTestRepository", "DeleteQualityTestRecordsByAttemptId")
                return True
            else:
                LoggingService.LogInfo(f"No quality test records found for TranscodeAttempt {TranscodeAttemptId}",
                                     "QualityTestRepository", "DeleteQualityTestRecordsByAttemptId")
                return True

        except Exception as e:
            LoggingService.LogException("Exception deleting quality test records", e, "QualityTestRepository", "DeleteQualityTestRecordsByAttemptId")
            return False

    # ─── TranscodeAttempt Quality Test Methods ─────────────────────────────

    # directive: path-schema-migration | # see path.S8
    def MarkQualityTestCompleted(self, TranscodeAttemptId: int) -> bool:
        """Mark quality test as completed in TranscodeAttempts."""
        try:
            Query = (
                "UPDATE TranscodeAttempts "
                "SET QualityTestCompleted = TRUE "
                "WHERE Id = %s"
            )
            RowsAffected = self.ExecuteNonQuery(Query, (TranscodeAttemptId,))
            return RowsAffected > 0

        except Exception as e:
            LoggingService.LogException("Exception marking quality test completed", e, "QualityTestRepository", "MarkQualityTestCompleted")
            return False

    # directive: path-schema-migration | # see path.S8
    def SkipQualityTest(self, TranscodeAttemptId: int) -> bool:
        """Skip quality test for a transcode attempt - marks QualityTestRequired = 0."""
        try:
            Query = (
                "UPDATE TranscodeAttempts "
                "SET QualityTestRequired = FALSE, QualityTestCompleted = TRUE "
                "WHERE Id = %s"
            )
            RowsAffected = self.ExecuteNonQuery(Query, (TranscodeAttemptId,))
            return RowsAffected > 0

        except Exception as e:
            LoggingService.LogException("Exception skipping quality test", e, "QualityTestRepository", "SkipQualityTest")
            return False

    # ─── Missed / Recovery Methods ─────────────────────────────────────────

    # directive: path-schema-migration | # see path.S8
    def GetMissedQualityTests(self, Limit: int = 100) -> List[Dict[str, Any]]:
        """Get successful transcode attempts that need quality testing but don't have successful quality test results."""
        try:
            LoggingService.LogFunctionEntry("GetMissedQualityTests", "QualityTestRepository", Limit)

            Query = (
                "SELECT ta.Id, ta.StorageRootId AS TaStorageRootId, ta.RelativePath AS TaRelativePath, "
                "tfp.SourceStorageRootId, tfp.SourceRelativePath, "
                "tfp.OutputStorageRootId, tfp.OutputRelativePath "
                "FROM TranscodeAttempts ta "
                "INNER JOIN TemporaryFilePaths tfp ON ta.Id = tfp.TranscodeAttemptId "
                "WHERE ta.Success = TRUE "
                "AND ta.QualityTestRequired = TRUE "
                "AND ta.QualityTestCompleted = FALSE "
                "AND tfp.OutputRelativePath IS NOT NULL "
                "AND ta.Id NOT IN ("
                "SELECT TranscodeAttemptId "
                "FROM QualityTestResults "
                "WHERE TranscodeAttemptId IS NOT NULL "
                "AND Status = 'Success'"
                ") "
                "ORDER BY ta.AttemptDate DESC "
                "LIMIT %s"
            )

            Rows = self.ExecuteQuery(Query, (Limit,))

            Results = []
            for Row in Rows:
                Results.append({
                    "Id": Row["Id"],
                    "FilePath": _SafeCanonical(Row.get("TaStorageRootId"), Row.get("TaRelativePath")),
                    "SourceStorageRootId": Row.get("SourceStorageRootId"),
                    "SourceRelativePath": Row.get("SourceRelativePath"),
                    "OutputStorageRootId": Row.get("OutputStorageRootId"),
                    "OutputRelativePath": Row.get("OutputRelativePath"),
                    "LocalSourcePath": _SafeCanonical(Row.get("SourceStorageRootId"), Row.get("SourceRelativePath")),
                    "LocalOutputPath": _SafeCanonical(Row.get("OutputStorageRootId"), Row.get("OutputRelativePath"))
                })

            LoggingService.LogInfo(f"Found {len(Results)} missed quality tests", "QualityTestRepository", "GetMissedQualityTests")
            return Results

        except Exception as e:
            LoggingService.LogException("Exception getting missed quality tests", e, "QualityTestRepository", "GetMissedQualityTests")
            return []

    # directive: path-schema-migration | # see path.S8
    def ResetFailedQualityTestResultsForRetry(self) -> int:
        """Reset failed quality test results for interrupted tests so they can be retried."""
        try:
            LoggingService.LogFunctionEntry("ResetFailedQualityTestResultsForRetry", "QualityTestRepository")

            Query = (
                "DELETE FROM QualityTestResults "
                "WHERE TranscodeAttemptId IN ("
                "SELECT ta.Id "
                "FROM TranscodeAttempts ta "
                "INNER JOIN TemporaryFilePaths tfp ON ta.Id = tfp.TranscodeAttemptId "
                "WHERE ta.Success = TRUE "
                "AND ta.QualityTestRequired = TRUE "
                "AND ta.QualityTestCompleted = FALSE "
                "AND tfp.OutputRelativePath IS NOT NULL "
                "AND ta.Id NOT IN ("
                "SELECT TranscodeAttemptId "
                "FROM QualityTestResults "
                "WHERE TranscodeAttemptId IS NOT NULL "
                "AND Status = 'Success'"
                ")"
                ") "
                "AND Status IN ('Failed', 'Running')"
            )

            AffectedRows = self.ExecuteNonQuery(Query)

            if AffectedRows > 0:
                LoggingService.LogInfo(f"Reset {AffectedRows} failed quality test results for retry", "QualityTestRepository", "ResetFailedQualityTestResultsForRetry")
            else:
                LoggingService.LogInfo("No failed quality test results found to reset", "QualityTestRepository", "ResetFailedQualityTestResultsForRetry")

            return AffectedRows

        except Exception as e:
            LoggingService.LogException("Exception resetting failed quality test results for retry", e, "QualityTestRepository", "ResetFailedQualityTestResultsForRetry")
            return 0

    # ─── Active Job Methods ────────────────────────────────────────────────

    # directive: path-schema-migration | # see path.S8
    def GetActiveQualityTestJob(self) -> Optional[Dict[str, Any]]:
        """Get the currently running quality test job details."""
        try:
            Query = (
                "SELECT aj.Id, aj.QueueId, aj.ProcessId, aj.ThreadId, aj.StartedAt, "
                "qtq.TranscodeAttemptId, qtq.OriginalFilePath, qtq.TranscodedFilePath, qtq.LocalSourcePath "
                "FROM ActiveJobs aj "
                "INNER JOIN QualityTestingQueue qtq ON aj.QueueId = qtq.Id "
                "WHERE aj.ServiceName = 'QualityTestService' "
                "AND aj.Status = 'Running' "
                "ORDER BY aj.StartedAt DESC "
                "LIMIT 1"
            )

            Result = self.ExecuteQuery(Query)
            if Result:
                return dict(Result[0])
            return None

        except Exception as e:
            LoggingService.LogException("Exception getting active quality test job", e, "QualityTestRepository", "GetActiveQualityTestJob")
            return None

    # directive: path-schema-migration | # see path.S8
    def KillActiveQualityTestProcess(self, ActiveJobId: int) -> bool:
        """Terminate FFmpeg process by PID from ActiveJobs table."""
        try:
            import psutil

            Query = "SELECT ProcessId FROM ActiveJobs WHERE Id = %s"
            Result = self.ExecuteQuery(Query, (ActiveJobId,))

            if not Result:
                LoggingService.LogWarning(f"No active job found with ID {ActiveJobId}", "QualityTestRepository", "KillActiveQualityTestProcess")
                return False

            ProcessId = Result[0]['processid']
            if not ProcessId:
                LoggingService.LogWarning(f"No process ID found for active job {ActiveJobId}", "QualityTestRepository", "KillActiveQualityTestProcess")
                return False

            try:
                Process = psutil.Process(ProcessId)
                Process.terminate()

                try:
                    Process.wait(timeout=5)
                except psutil.TimeoutExpired:
                    Process.kill()
                    Process.wait()

                LoggingService.LogInfo(f"Successfully terminated FFmpeg process {ProcessId}", "QualityTestRepository", "KillActiveQualityTestProcess")
                return True

            except psutil.NoSuchProcess:
                LoggingService.LogInfo(f"Process {ProcessId} was already terminated", "QualityTestRepository", "KillActiveQualityTestProcess")
                return True
            except Exception as e:
                LoggingService.LogException(f"Error terminating process {ProcessId}", e, "QualityTestRepository", "KillActiveQualityTestProcess")
                return False

        except Exception as e:
            LoggingService.LogException("Exception killing active quality test process", e, "QualityTestRepository", "KillActiveQualityTestProcess")
            return False

    # ─── TranscodeAttempts VMAF Method (DatabaseManager port) ──────────────

    # directive: path-schema-migration | # see path.S8
    def UpdateTranscodeAttemptVMAF(self, TranscodeAttemptId: int, VMAFScore: float) -> bool:
        """Update TranscodeAttempts with VMAF score."""
        try:
            Query = (
                "UPDATE TranscodeAttempts "
                "SET VMAF = %s "
                "WHERE Id = %s"
            )
            RowsAffected = self.ExecuteNonQuery(Query, (VMAFScore, TranscodeAttemptId))
            return RowsAffected > 0

        except Exception as e:
            LoggingService.LogException("Exception updating TranscodeAttempt VMAF", e, "QualityTestRepository", "UpdateTranscodeAttemptVMAF")
            return False

    # ─── TemporaryFilePaths Methods (DatabaseManager port + Phase 8 typed-pair) ────

    # directive: path-schema-migration, local-staging | # see path.S8, local-staging.C7
    def CreateTemporaryFilePath(self,
                                TranscodeAttemptId: int,
                                SourceStorageRootId: int,
                                SourceRelativePath: str,
                                OutputStorageRootId: Optional[int] = None,
                                OutputRelativePath: Optional[str] = None,
                                LocalSourcePath: Optional[str] = None,
                                LocalOutputPath: Optional[str] = None) -> Optional[int]:
        """Create a TemporaryFilePaths row using typed-pair source + optional typed-pair output + optional worker-local staging paths."""
        try:
            LoggingService.LogFunctionEntry("CreateTemporaryFilePath", "QualityTestRepository",
                                          TranscodeAttemptId, SourceStorageRootId, SourceRelativePath,
                                          OutputStorageRootId, OutputRelativePath, LocalSourcePath, LocalOutputPath)

            if not self.PrivateValidateTranscodeAttemptId(TranscodeAttemptId):
                LoggingService.LogError(f"Invalid TranscodeAttemptId: {TranscodeAttemptId}", "QualityTestRepository", "CreateTemporaryFilePath")
                return None

            if OutputStorageRootId is not None and OutputRelativePath:
                Query = "INSERT INTO TemporaryFilePaths (TranscodeAttemptId, SourceStorageRootId, SourceRelativePath, OutputStorageRootId, OutputRelativePath, LocalSourcePath, LocalOutputPath, CreatedDate) VALUES (%s, %s, %s, %s, %s, %s, %s, NOW()) RETURNING Id"
                Params = (TranscodeAttemptId, SourceStorageRootId, SourceRelativePath, OutputStorageRootId, OutputRelativePath, LocalSourcePath, LocalOutputPath)
            else:
                Query = "INSERT INTO TemporaryFilePaths (TranscodeAttemptId, SourceStorageRootId, SourceRelativePath, LocalSourcePath, LocalOutputPath, CreatedDate) VALUES (%s, %s, %s, %s, %s, NOW()) RETURNING Id"
                Params = (TranscodeAttemptId, SourceStorageRootId, SourceRelativePath, LocalSourcePath, LocalOutputPath)

            RowsAffected = self.ExecuteNonQuery(Query, Params)

            if RowsAffected > 0:
                RecordId = self.GetLastInsertId()
                LoggingService.LogInfo(f"Created TemporaryFilePaths row {RecordId} for TranscodeAttempt {TranscodeAttemptId}",
                                     "QualityTestRepository", "CreateTemporaryFilePath")
                self.PrivateLogTemporaryFilePathOperation("CREATE", TranscodeAttemptId, RecordId, "SUCCESS")
                return RecordId
            else:
                LoggingService.LogError(f"Failed to create TemporaryFilePaths row for TranscodeAttempt {TranscodeAttemptId}",
                                      "QualityTestRepository", "CreateTemporaryFilePath")
                self.PrivateLogTemporaryFilePathOperation("CREATE", TranscodeAttemptId, None, "FAILED")
                return None

        except Exception as e:
            LoggingService.LogException("Exception creating temporary file path record", e, "QualityTestRepository", "CreateTemporaryFilePath")
            self.PrivateLogTemporaryFilePathOperation("CREATE", TranscodeAttemptId, None, "EXCEPTION", str(e))
            return None

    # directive: path-schema-migration | # see path.S8
    def UpdateTemporaryFilePath(self,
                                TranscodeAttemptId: int,
                                OutputStorageRootId: int,
                                OutputRelativePath: str) -> bool:
        """Update TemporaryFilePaths row with typed-pair output columns (Phase 8 schema)."""
        try:
            LoggingService.LogFunctionEntry("UpdateTemporaryFilePath", "QualityTestRepository",
                                          TranscodeAttemptId, OutputStorageRootId, OutputRelativePath)

            if not self.PrivateValidateTranscodeAttemptId(TranscodeAttemptId):
                LoggingService.LogError(f"Invalid TranscodeAttemptId: {TranscodeAttemptId}", "QualityTestRepository", "UpdateTemporaryFilePath")
                return False

            Query = (
                "UPDATE TemporaryFilePaths "
                "SET OutputStorageRootId = %s, OutputRelativePath = %s "
                "WHERE TranscodeAttemptId = %s"
            )
            Params = (OutputStorageRootId, OutputRelativePath, TranscodeAttemptId)
            RowsAffected = self.ExecuteNonQuery(Query, Params)

            if RowsAffected > 0:
                LoggingService.LogInfo(f"Updated TemporaryFilePaths row for TranscodeAttempt {TranscodeAttemptId} with output typed pair ({OutputStorageRootId}, {OutputRelativePath})",
                                     "QualityTestRepository", "UpdateTemporaryFilePath")
                self.PrivateLogTemporaryFilePathOperation("UPDATE", TranscodeAttemptId, None, "SUCCESS")
                return True
            else:
                LoggingService.LogWarning(f"No TemporaryFilePaths row found for TranscodeAttempt {TranscodeAttemptId}",
                                        "QualityTestRepository", "UpdateTemporaryFilePath")
                self.PrivateLogTemporaryFilePathOperation("UPDATE", TranscodeAttemptId, None, "NOT_FOUND")
                return False

        except Exception as e:
            LoggingService.LogException("Exception updating temporary file path record", e, "QualityTestRepository", "UpdateTemporaryFilePath")
            self.PrivateLogTemporaryFilePathOperation("UPDATE", TranscodeAttemptId, None, "EXCEPTION", str(e))
            return False

    # directive: path-schema-migration, local-staging | # see path.S8, local-staging.C7
    def GetTemporaryFilePath(self, TranscodeAttemptId: int) -> Optional[Dict[str, Any]]:
        """Get TemporaryFilePaths row by TranscodeAttemptId. Returns typed-pair columns + LocalSourcePath/LocalOutputPath (real local staging paths when set, synthesized canonical otherwise)."""
        try:
            LoggingService.LogFunctionEntry("GetTemporaryFilePath", "QualityTestRepository", TranscodeAttemptId)

            Query = "SELECT Id, TranscodeAttemptId, SourceStorageRootId, SourceRelativePath, OutputStorageRootId, OutputRelativePath, LocalSourcePath, LocalOutputPath, CreatedDate FROM TemporaryFilePaths WHERE TranscodeAttemptId = %s"
            Results = self.ExecuteQuery(Query, (TranscodeAttemptId,))

            if Results:
                Row = Results[0]
                SrcId = Row.get("SourceStorageRootId") if "SourceStorageRootId" in Row else Row.get("sourcestoragerootid")
                SrcRel = Row.get("SourceRelativePath") if "SourceRelativePath" in Row else Row.get("sourcerelativepath")
                OutId = Row.get("OutputStorageRootId") if "OutputStorageRootId" in Row else Row.get("outputstoragerootid")
                OutRel = Row.get("OutputRelativePath") if "OutputRelativePath" in Row else Row.get("outputrelativepath")
                StoredLocalSrc = Row.get("LocalSourcePath") if "LocalSourcePath" in Row else Row.get("localsourcepath")
                StoredLocalOut = Row.get("LocalOutputPath") if "LocalOutputPath" in Row else Row.get("localoutputpath")

                SynthesizedSource = _SafeCanonical(SrcId, SrcRel)
                SynthesizedOutput = _SafeCanonical(OutId, OutRel)

                Record = {
                    "Id": Row.get("Id") if "Id" in Row else Row.get("id"),
                    "TranscodeAttemptId": Row.get("TranscodeAttemptId") if "TranscodeAttemptId" in Row else Row.get("transcodeattemptid"),
                    "SourceStorageRootId": SrcId,
                    "SourceRelativePath": SrcRel,
                    "OutputStorageRootId": OutId,
                    "OutputRelativePath": OutRel,
                    "CreatedDate": Row.get("CreatedDate") if "CreatedDate" in Row else Row.get("createddate"),
                    "OriginalPath": SynthesizedSource,
                    "LocalSourcePath": StoredLocalSrc if StoredLocalSrc else SynthesizedSource,
                    "LocalOutputPath": StoredLocalOut if StoredLocalOut else SynthesizedOutput,
                    "IsStaged": bool(StoredLocalSrc) or bool(StoredLocalOut),
                }
                LoggingService.LogInfo(f"Retrieved temporary file path record for TranscodeAttempt {TranscodeAttemptId}",
                                     "QualityTestRepository", "GetTemporaryFilePath")
                self.PrivateLogTemporaryFilePathOperation("SELECT", TranscodeAttemptId, Record.get("Id"), "SUCCESS")
                return Record
            else:
                LoggingService.LogWarning(f"No temporary file path record found for TranscodeAttempt {TranscodeAttemptId}",
                                        "QualityTestRepository", "GetTemporaryFilePath")
                self.PrivateLogTemporaryFilePathOperation("SELECT", TranscodeAttemptId, None, "NOT_FOUND")
                return None

        except Exception as e:
            LoggingService.LogException("Exception getting temporary file path record", e, "QualityTestRepository", "GetTemporaryFilePath")
            self.PrivateLogTemporaryFilePathOperation("SELECT", TranscodeAttemptId, None, "EXCEPTION", str(e))
            return None

    # directive: path-schema-migration | # see path.S8
    def DeleteTemporaryFilePath(self, TranscodeAttemptId: int) -> bool:
        """Delete TemporaryFilePaths row by TranscodeAttemptId."""
        try:
            LoggingService.LogFunctionEntry("DeleteTemporaryFilePath", "QualityTestRepository", TranscodeAttemptId)

            Query = (
                "DELETE FROM TemporaryFilePaths "
                "WHERE TranscodeAttemptId = %s"
            )
            RowsAffected = self.ExecuteNonQuery(Query, (TranscodeAttemptId,))

            if RowsAffected > 0:
                LoggingService.LogInfo(f"Deleted temporary file path record for TranscodeAttempt {TranscodeAttemptId}",
                                     "QualityTestRepository", "DeleteTemporaryFilePath")
                self.PrivateLogTemporaryFilePathOperation("DELETE", TranscodeAttemptId, None, "SUCCESS")
                return True
            else:
                LoggingService.LogWarning(f"No temporary file path record found to delete for TranscodeAttempt {TranscodeAttemptId}",
                                        "QualityTestRepository", "DeleteTemporaryFilePath")
                self.PrivateLogTemporaryFilePathOperation("DELETE", TranscodeAttemptId, None, "NOT_FOUND")
                return False

        except Exception as e:
            LoggingService.LogException("Exception deleting temporary file path record", e, "QualityTestRepository", "DeleteTemporaryFilePath")
            self.PrivateLogTemporaryFilePathOperation("DELETE", TranscodeAttemptId, None, "EXCEPTION", str(e))
            return False

    # directive: path-schema-migration | # see path.S8
    def PrivateValidateTranscodeAttemptId(self, TranscodeAttemptId: int) -> bool:
        """Verify TranscodeAttemptId exists in TranscodeAttempts."""
        try:
            Query = "SELECT COUNT(*) as Count FROM TranscodeAttempts WHERE Id = %s"
            Results = self.ExecuteQuery(Query, (TranscodeAttemptId,))
            if not Results:
                return False
            Row = Results[0]
            Count = Row.get("Count") if "Count" in Row else Row.get("count")
            return (Count or 0) > 0
        except Exception as e:
            LoggingService.LogException("Exception validating TranscodeAttemptId", e, "QualityTestRepository", "PrivateValidateTranscodeAttemptId")
            return False

    # directive: path-schema-migration | # see path.S8
    def PrivateLogTemporaryFilePathOperation(self, Operation: str, TranscodeAttemptId: int, RecordId: Optional[int], Status: str, ErrorMessage: str = None):
        """Log a TemporaryFilePaths CRUD operation for audit."""
        try:
            Message = f"TemporaryFilePath {Operation} - TranscodeAttemptId: {TranscodeAttemptId}"
            if RecordId:
                Message += f", RecordId: {RecordId}"
            Message += f", Status: {Status}"
            if ErrorMessage:
                Message += f", Error: {ErrorMessage}"

            if Status in ("FAILED", "EXCEPTION"):
                LoggingService.LogError(Message, "QualityTestRepository", "PrivateLogTemporaryFilePathOperation")
            else:
                LoggingService.LogInfo(Message, "QualityTestRepository", "PrivateLogTemporaryFilePathOperation")
        except Exception as e:
            LoggingService.LogException("Exception logging temporary file path operation", e, "QualityTestRepository", "PrivateLogTemporaryFilePathOperation")

    def ClaimQualityTestJob(self, WorkerName: str) -> dict:
        """Atomically claim a pending quality test job, gated on DB authority.

        DB-authoritative gate (see `.claude/rules/db-is-authority.md`):
        Workers.Status='Online' AND Workers.QualityTestEnabled=TRUE enforced
        via the shared WorkerCapabilityPredicate helper. A Paused worker or
        a worker with QualityTestEnabled=FALSE cannot claim, regardless of
        any cached state in the calling service. Mid-flight GUI flag changes
        are honored on the next claim attempt -- no restart needed.

        Override-aware: rows with ForceDisposition set are reserved for the
        WebService override path -- workers must not race them. See
        qt-queue-visibility-and-override.feature.md C4.
        """
        try:
            from Core.Database.WorkerCapabilityPredicate import BuildClaimPredicate
            CapabilityFragment, CapabilityParams = BuildClaimPredicate(WorkerName, "QualityTestEnabled")
            select_query = f"""
                SELECT Id, TranscodeAttemptId, OriginalFilePath, LocalSourcePath, TranscodedFilePath, DateAdded
                FROM QualityTestingQueue
                WHERE Status = 'Pending'
                  AND ForceDisposition IS NULL
                  AND DateStarted IS NULL
                  AND {CapabilityFragment}
                ORDER BY DateAdded ASC
                LIMIT 1
            """

            jobs = self.DatabaseService.ExecuteQuery(select_query, CapabilityParams)
            if not jobs or len(jobs) == 0:
                LoggingService.LogDebug(f"No claimable QT jobs for {WorkerName} (Paused / QualityTestEnabled=FALSE / no Pending rows)", "DatabaseManager", "ClaimQualityTestJob")
                return None

            job_to_claim = jobs[0]
            job_id = job_to_claim["Id"]

            # Atomic claim: re-gate on the same predicate inside the UPDATE so
            # a flag flip between SELECT and UPDATE refuses the claim. Records
            # the claiming worker on the row so operator UIs can show which
            # host is doing the work.
            update_query = f"""
                UPDATE QualityTestingQueue
                SET DateStarted = NOW(), Status = 'Running', ClaimedBy = %s
                WHERE Id = %s
                  AND DateStarted IS NULL
                  AND ForceDisposition IS NULL
                  AND {CapabilityFragment}
            """

            rows_affected = self.DatabaseService.ExecuteNonQuery(update_query, (WorkerName, job_id) + CapabilityParams)
            
            if rows_affected > 0:
                LoggingService.LogInfo(f"Successfully claimed quality test job {job_id}", "DatabaseManager", "ClaimQualityTestJob")
                return {
                    "Id": job_to_claim["Id"],
                    "TranscodeAttemptId": job_to_claim["TranscodeAttemptId"],
                    "OriginalFilePath": job_to_claim["OriginalFilePath"],
                    "LocalSourcePath": job_to_claim["LocalSourcePath"],
                    "TranscodedFilePath": job_to_claim["TranscodedFilePath"],
                    "DateAdded": job_to_claim["DateAdded"]
                }
            else:
                LoggingService.LogDebug(f"Job {job_id} was already claimed by another worker", "DatabaseManager", "ClaimQualityTestJob")
                return None
                
        except Exception as e:
            LoggingService.LogException("Exception claiming quality test job", e, "DatabaseManager", "ClaimQualityTestJob")
            return None
