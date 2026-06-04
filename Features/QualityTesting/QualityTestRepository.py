from typing import Optional, List, Dict, Any
from datetime import datetime, timezone
from Core.Database.BaseRepository import BaseRepository
from Core.Logging.LoggingService import LoggingService
from Features.QualityTesting.Models.QualityTestResultModel import QualityTestResultModel


def _LastPathSegment(PathValue):
    """Trailing path segment from a string of unknown shape (UNC/drive/POSIX)."""
    if not PathValue:
        return ""
    Normalized = PathValue.replace('\\', '/').rstrip('/')
    Idx = Normalized.rfind('/')
    if Idx < 0:
        return Normalized
    return Normalized[Idx + 1:]


class QualityTestRepository(BaseRepository):
    """Repository for quality test CRUD operations."""

    # ─── QualityTestingQueue Methods ───────────────────────────────────────

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

    def CreateQualityTestQueueEntry(self, TranscodeAttemptId: int, OriginalFilePath: str, LocalSourcePath: str, TranscodedFilePath: str) -> Optional[int]:
        """Create a new quality test queue entry."""
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

    def GetQualityTestResults(self, Limit: int = 10, Offset: int = 0) -> List[Dict[str, Any]]:
        """Get recent quality test results joined with TranscodeAttempts."""
        try:
            Query = (
                "SELECT "
                "qtr.Id, qtr.TranscodeAttemptId, qtr.VMAFScore, "
                "qtr.TestDuration, qtr.PassesThreshold, qtr.Rank, qtr.ErrorMessage, qtr.DateTested, "
                "qtr.FFmpegCommand, qtr.Status, "
                "ta.ProfileName, ta.FilePath, ta.OldSizeBytes, ta.NewSizeBytes, ta.SizeReductionBytes, "
                "ta.SizeReductionPercent, ta.TranscodeDurationSeconds, ta.ProfileName as TranscodeProfileName, "
                "ta.Quality, ta.AttemptDate, ta.NewSizeBytes as FileSize, "
                "ta.FileReplaced, ta.FileReplacedDate, ta.ReplacementType, "
                "tfp.LocalOutputPath as TranscodedFilePath, "
                "tfp.LocalSourcePath "
                "FROM QualityTestResults qtr "
                "LEFT JOIN TranscodeAttempts ta ON qtr.TranscodeAttemptId = ta.Id "
                "LEFT JOIN TemporaryFilePaths tfp ON qtr.TranscodeAttemptId = tfp.TranscodeAttemptId "
                "ORDER BY qtr.DateTested DESC "
                "LIMIT %s OFFSET %s"
            )
            Rows = self.ExecuteQuery(Query, (Limit, Offset))

            Results = []
            for Row in Rows:
                TranscodedFilePath = Row["TranscodedFilePath"]
                TranscodedFileName = _LastPathSegment(TranscodedFilePath) if TranscodedFilePath else None

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
                    "FilePath": Row["FilePath"],
                    "TranscodedFilePath": TranscodedFilePath,
                    "TranscodedFileName": TranscodedFileName,
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

    # directive: bug-0042-activity-vmaf-list-source
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
                "ta.FilePath AS TaFilePath, ta.OldSizeBytes, ta.NewSizeBytes "
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
                OriginalPath = Row.get("OriginalFilePath") or Row.get("TaFilePath")
                FileName = _LastPathSegment(OriginalPath) if OriginalPath else f"TranscodeAttempt_{Row['TranscodeAttemptId']}"
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

    def GetMissedQualityTests(self, Limit: int = 100) -> List[Dict[str, Any]]:
        """Get successful transcode attempts that need quality testing but don't have successful quality test results."""
        try:
            LoggingService.LogFunctionEntry("GetMissedQualityTests", "QualityTestRepository", Limit)

            Query = (
                "SELECT ta.Id, ta.FilePath, "
                "tfp.LocalSourcePath, tfp.LocalOutputPath "
                "FROM TranscodeAttempts ta "
                "INNER JOIN TemporaryFilePaths tfp ON ta.Id = tfp.TranscodeAttemptId "
                "WHERE ta.Success = TRUE "
                "AND ta.QualityTestRequired = TRUE "
                "AND ta.QualityTestCompleted = FALSE "
                "AND tfp.LocalOutputPath IS NOT NULL "
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
                    "FilePath": Row["FilePath"],
                    "LocalSourcePath": Row["LocalSourcePath"],
                    "LocalOutputPath": Row["LocalOutputPath"]
                })

            LoggingService.LogInfo(f"Found {len(Results)} missed quality tests", "QualityTestRepository", "GetMissedQualityTests")
            return Results

        except Exception as e:
            LoggingService.LogException("Exception getting missed quality tests", e, "QualityTestRepository", "GetMissedQualityTests")
            return []

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
                "AND tfp.LocalOutputPath IS NOT NULL "
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
