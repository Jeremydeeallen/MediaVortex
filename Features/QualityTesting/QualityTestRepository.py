#!/usr/bin/env python3
"""QualityTestRepository.py - Repository for quality test data access"""

import os
from typing import Optional, List, Dict, Any
from datetime import datetime, timezone
from Core.Database.BaseRepository import BaseRepository
from Core.Logging.LoggingService import LoggingService
from Features.QualityTesting.Models.QualityTestResultModel import QualityTestResultModel


class QualityTestRepository(BaseRepository):
    """Repository for quality test CRUD operations."""

    # ─── QualityTestingQueue Methods ───────────────────────────────────────

    def GetQualityTestJob(self, JobId: int) -> Optional[Dict[str, Any]]:
        """Get a quality test job by ID."""
        try:
            query = """SELECT Id, TranscodeAttemptId, OriginalFilePath, LocalSourcePath, TranscodedFilePath,
                              DateAdded, DateStarted, DateCompleted
                       FROM QualityTestingQueue WHERE Id = %s"""
            rows = self.ExecuteQuery(query, (JobId,))

            if rows:
                row = rows[0]
                return {
                    "Id": row["Id"],
                    "TranscodeAttemptId": row["TranscodeAttemptId"],
                    "OriginalFilePath": row["OriginalFilePath"],
                    "LocalSourcePath": row["LocalSourcePath"],
                    "TranscodedFilePath": row["TranscodedFilePath"],
                    "DateAdded": row["DateAdded"],
                    "DateStarted": row["DateStarted"],
                    "DateCompleted": row["DateCompleted"]
                }
            return None

        except Exception as e:
            LoggingService.LogException("Exception getting quality test job", e, "QualityTestRepository", "GetQualityTestJob")
            return None

    def GetQualityTestQueue(self) -> List[Dict[str, Any]]:
        """Get all quality test jobs in queue ordered by date."""
        try:
            query = """
                SELECT Id, TranscodeAttemptId, OriginalFilePath, TranscodedFilePath, LocalSourcePath,
                       DateAdded, DateStarted, DateCompleted
                FROM QualityTestingQueue
                ORDER BY DateAdded ASC
            """
            rows = self.ExecuteQuery(query)
            return list(rows)

        except Exception as e:
            LoggingService.LogException("Exception getting quality test queue", e, "QualityTestRepository", "GetQualityTestQueue")
            return []

    # ClaimQualityTestJob lived here as a shadow with no DB-authority gate.
    # Deleted 2026-05-29: the canonical implementation is
    # DatabaseManager.ClaimQualityTestJob(WorkerName) which enforces the
    # Workers.Status + QualityTestEnabled predicate via
    # Core.Database.WorkerCapabilityPredicate. See
    # `.claude/rules/db-is-authority.md` and
    # `.claude/programs/db-authority-program.md` P1.

    def CreateQualityTestQueueEntry(self, TranscodeAttemptId: int, OriginalFilePath: str, LocalSourcePath: str, TranscodedFilePath: str) -> Optional[int]:
        """Create a new quality test queue entry."""
        try:
            LoggingService.LogFunctionEntry("CreateQualityTestQueueEntry", "QualityTestRepository",
                                          TranscodeAttemptId, OriginalFilePath, LocalSourcePath, TranscodedFilePath)

            query = """
                INSERT INTO QualityTestingQueue (
                    TranscodeAttemptId, OriginalFilePath, TranscodedFilePath, LocalSourcePath,
                    DateAdded, DateStarted, DateCompleted
                ) VALUES (%s, %s, %s, %s, NOW(), %s, %s)
                RETURNING Id
            """

            params = (
                TranscodeAttemptId,
                OriginalFilePath,
                TranscodedFilePath,
                LocalSourcePath,
                None,  # DateStarted
                None   # DateCompleted
            )

            RowsAffected = self.ExecuteNonQuery(query, params)

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

            query = "DELETE FROM QualityTestingQueue WHERE Id = %s"
            affected_rows = self.ExecuteNonQuery(query, (JobId,))

            if affected_rows > 0:
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
            query = "DELETE FROM QualityTestingQueue WHERE Id = %s"
            rows_affected = self.ExecuteNonQuery(query, (JobId,))
            if rows_affected > 0:
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

            result = QualityTestResultModel(
                TranscodeAttemptId=TranscodeAttemptId,
                Status=Status,
                DateTested=TestDate or datetime.now(timezone.utc),
                VMAFScore=0.0 if Status == "Running" else None,
                ErrorMessage=None
            )

            # Verify TranscodeAttemptId exists
            check_query = "SELECT Id FROM TranscodeAttempts WHERE Id = %s"
            check_result = self.ExecuteQuery(check_query, (TranscodeAttemptId,))

            if not check_result:
                LoggingService.LogError(
                    f"TranscodeAttemptId {TranscodeAttemptId} does not exist in TranscodeAttempts table",
                    "QualityTestRepository", "CreateQualityTestResult"
                )
                return 0

            query = """
                INSERT INTO QualityTestResults
                (TranscodeAttemptId, TestDuration, PassesThreshold, Rank, ErrorMessage, DateTested, FFmpegCommand, Status, VMAFScore)
                VALUES (%s, %s, %s, %s, %s, NOW(), %s, %s, %s)
                RETURNING Id
            """

            params = (
                result.TranscodeAttemptId,
                0.0,  # TestDuration
                False,  # PassesThreshold
                0,  # Rank
                result.ErrorMessage,
                "",  # FFmpegCommand
                result.Status,
                result.VMAFScore
            )

            LoggingService.LogInfo(f"Inserting QualityTestResult with params: {params}", "QualityTestRepository", "CreateQualityTestResult")

            try:
                affected_rows = self.ExecuteNonQuery(query, params)
                result_id = self.GetLastInsertId()

                if result_id > 0:
                    LoggingService.LogInfo(f"Created QualityTestResult {result_id} for TranscodeAttempt {TranscodeAttemptId}",
                                          "QualityTestRepository", "CreateQualityTestResult")
                    return result_id
                else:
                    LoggingService.LogError(
                        f"INSERT failed - no record ID returned. Query: {query}, Params: {params}, ParamCount: {len(params)}, RowCount: {affected_rows}",
                        "QualityTestRepository", "CreateQualityTestResult"
                    )
                    return 0
            except Exception as e:
                LoggingService.LogException(
                    f"Database error during INSERT. Query: {query}, Params: {params}, ParamCount: {len(params)}",
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

            query = "UPDATE QualityTestResults SET Status = 'Failed', ErrorMessage = %s WHERE Id = %s"
            affected_rows = self.ExecuteNonQuery(query, (ErrorMessage, ResultId))

            if affected_rows > 0:
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
        """Get recent quality test results from QualityTestResults table joined with TranscodeAttempts."""
        try:
            query = """
                SELECT
                    qtr.Id, qtr.TranscodeAttemptId, qtr.VMAFScore,
                    qtr.TestDuration, qtr.PassesThreshold, qtr.Rank, qtr.ErrorMessage, qtr.DateTested,
                    qtr.FFmpegCommand, qtr.Status,
                    ta.ProfileName, ta.FilePath, ta.OldSizeBytes, ta.NewSizeBytes, ta.SizeReductionBytes,
                    ta.SizeReductionPercent, ta.TranscodeDurationSeconds, ta.ProfileName as TranscodeProfileName,
                    ta.Quality, ta.AttemptDate, ta.NewSizeBytes as FileSize,
                    ta.FileReplaced, ta.FileReplacedDate, ta.ReplacementType,
                    tfp.LocalOutputPath as TranscodedFilePath,
                    tfp.LocalSourcePath
                FROM QualityTestResults qtr
                LEFT JOIN TranscodeAttempts ta ON qtr.TranscodeAttemptId = ta.Id
                LEFT JOIN TemporaryFilePaths tfp ON qtr.TranscodeAttemptId = tfp.TranscodeAttemptId
                ORDER BY qtr.DateTested DESC
                LIMIT %s OFFSET %s
            """
            rows = self.ExecuteQuery(query, (Limit, Offset))

            results = []
            for row in rows:
                TranscodedFilePath = row["TranscodedFilePath"]
                TranscodedFileName = None
                if TranscodedFilePath:
                    TranscodedFileName = os.path.basename(TranscodedFilePath)

                results.append({
                    "Id": row["Id"],
                    "TranscodeAttemptId": row["TranscodeAttemptId"],
                    "VMAFScore": row["VMAFScore"],
                    "ProfileName": row["ProfileName"],
                    "FileSize": row["FileSize"],
                    "TestDuration": row["TestDuration"],
                    "PassesThreshold": row["PassesThreshold"],
                    "Rank": row["Rank"],
                    "ErrorMessage": row["ErrorMessage"],
                    "DateTested": row["DateTested"],
                    "FFmpegCommand": row["FFmpegCommand"],
                    "Status": row["Status"],
                    "FilePath": row["FilePath"],
                    "TranscodedFilePath": TranscodedFilePath,
                    "TranscodedFileName": TranscodedFileName,
                    "OldSizeBytes": row["OldSizeBytes"],
                    "NewSizeBytes": row["NewSizeBytes"],
                    "SizeReductionBytes": row["SizeReductionBytes"],
                    "SizeReductionPercent": row["SizeReductionPercent"],
                    "TranscodeDurationSeconds": row["TranscodeDurationSeconds"],
                    "Quality": row["Quality"],
                    "TranscodeProfileName": row["TranscodeProfileName"],
                    "AttemptDate": row["AttemptDate"],
                    "FileReplaced": row["FileReplaced"],
                    "FileReplacedDate": row["FileReplacedDate"],
                    "ReplacementType": row["ReplacementType"],
                    "Success": row["PassesThreshold"] and not row["ErrorMessage"]
                })
            return results

        except Exception as e:
            LoggingService.LogException("Exception getting quality test results", e, "QualityTestRepository", "GetQualityTestResults")
            return []

    def GetQualityTestResultsCount(self) -> int:
        """Get total count of quality test results."""
        try:
            query = "SELECT COUNT(*) as TotalCount FROM QualityTestResults"
            result = self.ExecuteQuery(query)

            if result:
                return result[0]['totalcount']
            return 0

        except Exception as e:
            LoggingService.LogException("Exception getting quality test results count", e, "QualityTestRepository", "GetQualityTestResultsCount")
            return 0

    # ─── QualityTestProgress Methods ───────────────────────────────────────

    def SaveQualityTestProgress(self, transcode_attempt_id: int, progress_data: Dict[str, Any]) -> bool:
        """Save quality test progress - updates existing record or creates new one."""
        try:
            check_query = "SELECT Id FROM QualityTestProgress WHERE TranscodeAttemptId = %s"
            existing_records = self.ExecuteQuery(check_query, (transcode_attempt_id,))

            if existing_records:
                query = """
                    UPDATE QualityTestProgress SET
                        Status = %s, ProgressPercentage = %s, CurrentStep = %s,
                        UpdatedAt = NOW(), CurrentTime = %s, CurrentFrame = %s,
                        ProcessingSpeed = %s, ETA = %s
                    WHERE TranscodeAttemptId = %s
                """
                parameters = (
                    progress_data.get('Status', 'Running'),
                    progress_data.get('ProgressPercentage', 0),
                    progress_data.get('CurrentStep', 'Processing'),
                    progress_data.get('CurrentTime'),
                    progress_data.get('CurrentFrame', 0),
                    progress_data.get('ProcessingSpeed'),
                    progress_data.get('ETA'),
                    transcode_attempt_id
                )
            else:
                query = """
                    INSERT INTO QualityTestProgress
                    (TranscodeAttemptId, Status, ProgressPercentage, CurrentStep,
                     StartTime, UpdatedAt, CreatedAt, CurrentTime, CurrentFrame,
                     ProcessingSpeed, ETA)
                    VALUES (%s, %s, %s, %s, %s, NOW(), NOW(),
                            %s, %s, %s, %s)
                """
                parameters = (
                    transcode_attempt_id,
                    progress_data.get('Status', 'Running'),
                    progress_data.get('ProgressPercentage', 0),
                    progress_data.get('CurrentStep', 'Processing'),
                    progress_data.get('StartTime'),
                    progress_data.get('CurrentTime'),
                    progress_data.get('CurrentFrame', 0),
                    progress_data.get('ProcessingSpeed'),
                    progress_data.get('ETA')
                )

            rows_affected = self.ExecuteNonQuery(query, parameters)
            return rows_affected > 0

        except Exception as e:
            LoggingService.LogException("Exception saving quality test progress", e, "QualityTestRepository", "SaveQualityTestProgress")
            return False

    def GetRunningQualityTestProgress(self) -> Optional[Dict[str, Any]]:
        """Get running quality test progress from QualityTestProgress table with file information."""
        try:
            query = """
                SELECT
                    qtp.Id,
                    qtp.TranscodeAttemptId,
                    qtp.Status,
                    qtp.ProgressPercentage,
                    qtp.CurrentStep,
                    qtp.CurrentFrame,
                    qtp.CurrentTime,
                    qtp.ProcessingSpeed,
                    qtp.ETA,
                    qtp.StartTime,
                    qtp.UpdatedAt,
                    qtq.OriginalFilePath,
                    qtq.TranscodedFilePath,
                    qtq.LocalSourcePath
                FROM QualityTestProgress qtp
                LEFT JOIN QualityTestingQueue qtq ON qtp.TranscodeAttemptId = qtq.TranscodeAttemptId
                WHERE qtp.Status = 'Processing'
                ORDER BY qtp.StartTime DESC
                LIMIT 1
            """
            rows = self.ExecuteQuery(query)

            if rows and len(rows) > 0:
                row = rows[0]
                return {
                    "Id": row["Id"],
                    "TranscodeAttemptId": row["TranscodeAttemptId"],
                    "Status": row["Status"],
                    "ProgressPercentage": row["ProgressPercentage"],
                    "CurrentStep": row["CurrentStep"],
                    "CurrentFrame": row["CurrentFrame"],
                    "CurrentTime": row["CurrentTime"],
                    "ProcessingSpeed": row["ProcessingSpeed"],
                    "ETA": row["ETA"],
                    "StartTime": row["StartTime"],
                    "UpdatedAt": row["UpdatedAt"],
                    "FileName": os.path.basename(row["OriginalFilePath"]) if row["OriginalFilePath"] else f"TranscodeAttempt_{row['TranscodeAttemptId']}",
                    "OriginalFilePath": row["OriginalFilePath"] or f"TranscodeAttempt_{row['TranscodeAttemptId']}",
                    "TranscodedFilePath": row["TranscodedFilePath"] or f"TranscodeAttempt_{row['TranscodeAttemptId']}",
                    "LocalSourcePath": row["LocalSourcePath"],
                    "EndTime": None,
                    "ErrorMessage": None
                }
            return None

        except Exception as e:
            LoggingService.LogException("Exception getting running quality test progress", e, "QualityTestRepository", "GetRunningQualityTestProgress")
            return None

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
                return True  # Still return True as this is not an error condition

        except Exception as e:
            LoggingService.LogException("Exception deleting quality test records", e, "QualityTestRepository", "DeleteQualityTestRecordsByAttemptId")
            return False

    # ─── TranscodeAttempt Quality Test Methods ─────────────────────────────

    def MarkQualityTestCompleted(self, transcode_attempt_id: int) -> bool:
        """Mark quality test as completed in TranscodeAttempts."""
        try:
            query = """
                UPDATE TranscodeAttempts
                SET QualityTestCompleted = TRUE
                WHERE Id = %s
            """
            rows_affected = self.ExecuteNonQuery(query, (transcode_attempt_id,))
            return rows_affected > 0

        except Exception as e:
            LoggingService.LogException("Exception marking quality test completed", e, "QualityTestRepository", "MarkQualityTestCompleted")
            return False

    def SkipQualityTest(self, transcode_attempt_id: int) -> bool:
        """Skip quality test for a transcode attempt - marks QualityTestRequired = 0."""
        try:
            query = """
                UPDATE TranscodeAttempts
                SET QualityTestRequired = FALSE, QualityTestCompleted = TRUE
                WHERE Id = %s
            """
            rows_affected = self.ExecuteNonQuery(query, (transcode_attempt_id,))
            return rows_affected > 0

        except Exception as e:
            LoggingService.LogException("Exception skipping quality test", e, "QualityTestRepository", "SkipQualityTest")
            return False

    # ─── Missed / Recovery Methods ─────────────────────────────────────────

    def GetMissedQualityTests(self, Limit: int = 100) -> List[Dict[str, Any]]:
        """Get successful transcode attempts that need quality testing but don't have successful quality test results."""
        try:
            LoggingService.LogFunctionEntry("GetMissedQualityTests", "QualityTestRepository", Limit)

            query = """
                SELECT ta.Id, ta.FilePath,
                       tfp.LocalSourcePath, tfp.LocalOutputPath
                FROM TranscodeAttempts ta
                INNER JOIN TemporaryFilePaths tfp ON ta.Id = tfp.TranscodeAttemptId
                WHERE ta.Success = TRUE
                  AND ta.QualityTestRequired = TRUE
                  AND ta.QualityTestCompleted = FALSE
                  AND tfp.LocalOutputPath IS NOT NULL
                  AND ta.Id NOT IN (
                      SELECT TranscodeAttemptId
                      FROM QualityTestResults
                      WHERE TranscodeAttemptId IS NOT NULL
                        AND Status = 'Success'
                  )
                ORDER BY ta.AttemptDate DESC
                LIMIT %s
            """

            Rows = self.ExecuteQuery(query, (Limit,))

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

            Query = """
                DELETE FROM QualityTestResults
                WHERE TranscodeAttemptId IN (
                    SELECT ta.Id
                    FROM TranscodeAttempts ta
                    INNER JOIN TemporaryFilePaths tfp ON ta.Id = tfp.TranscodeAttemptId
                    WHERE ta.Success = TRUE
                      AND ta.QualityTestRequired = TRUE
                      AND ta.QualityTestCompleted = FALSE
                      AND tfp.LocalOutputPath IS NOT NULL
                      AND ta.Id NOT IN (
                          SELECT TranscodeAttemptId
                          FROM QualityTestResults
                          WHERE TranscodeAttemptId IS NOT NULL
                            AND Status = 'Success'
                      )
                )
                AND Status IN ('Failed', 'Running')
            """

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
            query = """
                SELECT aj.Id, aj.QueueId, aj.ProcessId, aj.ThreadId, aj.StartedAt,
                       qtq.TranscodeAttemptId, qtq.OriginalFilePath, qtq.TranscodedFilePath, qtq.LocalSourcePath
                FROM ActiveJobs aj
                INNER JOIN QualityTestingQueue qtq ON aj.QueueId = qtq.Id
                WHERE aj.ServiceName = 'QualityTestService'
                  AND aj.Status = 'Running'
                ORDER BY aj.StartedAt DESC
                LIMIT 1
            """

            result = self.ExecuteQuery(query)
            if result:
                return dict(result[0])
            return None

        except Exception as e:
            LoggingService.LogException("Exception getting active quality test job", e, "QualityTestRepository", "GetActiveQualityTestJob")
            return None

    def KillActiveQualityTestProcess(self, ActiveJobId: int) -> bool:
        """Terminate FFmpeg process by PID from ActiveJobs table."""
        try:
            import psutil

            query = "SELECT ProcessId FROM ActiveJobs WHERE Id = %s"
            result = self.ExecuteQuery(query, (ActiveJobId,))

            if not result:
                LoggingService.LogWarning(f"No active job found with ID {ActiveJobId}", "QualityTestRepository", "KillActiveQualityTestProcess")
                return False

            process_id = result[0]['processid']
            if not process_id:
                LoggingService.LogWarning(f"No process ID found for active job {ActiveJobId}", "QualityTestRepository", "KillActiveQualityTestProcess")
                return False

            try:
                process = psutil.Process(process_id)
                process.terminate()

                try:
                    process.wait(timeout=5)
                except psutil.TimeoutExpired:
                    process.kill()
                    process.wait()

                LoggingService.LogInfo(f"Successfully terminated FFmpeg process {process_id}", "QualityTestRepository", "KillActiveQualityTestProcess")
                return True

            except psutil.NoSuchProcess:
                LoggingService.LogInfo(f"Process {process_id} was already terminated", "QualityTestRepository", "KillActiveQualityTestProcess")
                return True
            except Exception as e:
                LoggingService.LogException(f"Error terminating process {process_id}", e, "QualityTestRepository", "KillActiveQualityTestProcess")
                return False

        except Exception as e:
            LoggingService.LogException("Exception killing active quality test process", e, "QualityTestRepository", "KillActiveQualityTestProcess")
            return False
