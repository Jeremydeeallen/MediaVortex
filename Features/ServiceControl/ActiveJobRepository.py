from typing import Any, Dict, List, Optional
from datetime import datetime, timezone
from Services.DatabaseService import DatabaseService
from Services.LoggingService import LoggingService
from Core.Database.DatabaseService import EscapeLikePattern
from Features.ServiceControl.JobPhase import JobPhase


class ActiveJobRepository:
    def __init__(self, DatabaseServiceInstance: Optional[DatabaseService] = None):
        self.DatabaseService = DatabaseServiceInstance or DatabaseService()

    # directive: transcode-flow-canonical
    def SetJobPhase(self, ActiveJobId: int, Phase: JobPhase) -> bool:
        """Transition ActiveJob to Phase; stamps PhaseTransitionedAt=NOW(). Clears FFmpegPid when leaving Encoding."""
        try:
            if Phase == JobPhase.PostEncode:
                Query = (
                    "UPDATE ActiveJobs "
                    "SET Phase = %s, PhaseTransitionedAt = NOW(), FFmpegPid = NULL, UpdatedAt = NOW() "
                    "WHERE Id = %s"
                )
            else:
                Query = (
                    "UPDATE ActiveJobs "
                    "SET Phase = %s, PhaseTransitionedAt = NOW(), UpdatedAt = NOW() "
                    "WHERE Id = %s"
                )
            Affected = self.DatabaseService.ExecuteNonQuery(Query, (Phase.value, ActiveJobId))
            return Affected > 0
        # fail-loud-ok: phase-write failure logged; callers proceed (encode still runs); missing phase surfaces via GetJobPhase=None
        except Exception as Ex:
            LoggingService.LogException(
                f"SetJobPhase({ActiveJobId}, {Phase}) failed",
                Ex, "ActiveJobRepository", "SetJobPhase",
            )
            return False

    # directive: transcode-flow-canonical
    def GetJobPhase(self, ActiveJobId: int):
        """Return (JobPhase, PhaseTransitionedAt) or None."""
        try:
            Query = "SELECT Phase, PhaseTransitionedAt FROM ActiveJobs WHERE Id = %s"
            Rows = self.DatabaseService.ExecuteQuery(Query, (ActiveJobId,))
            if not Rows:
                return None
            Row = Rows[0]
            PhaseVal = Row.get('Phase') or Row.get('phase')
            TransitionedAt = Row.get('PhaseTransitionedAt') or Row.get('phasetransitionedat')
            if PhaseVal is None:
                return None
            return (JobPhase.FromString(PhaseVal), TransitionedAt)
        # fail-loud-ok: phase-read failure returns None; caller treats as pre-Setup (no false-positive kill)
        except Exception as Ex:
            LoggingService.LogException(
                f"GetJobPhase({ActiveJobId}) failed",
                Ex, "ActiveJobRepository", "GetJobPhase",
            )
            return None


    def CancelActiveJob(self, job_id: int) -> bool:
        """Cancel a specific active job"""
        try:
            # Get job details
            get_job_query = "SELECT ServiceName, JobType, QueueId FROM ActiveJobs WHERE Id = %s"
            job_rows = self.DatabaseService.ExecuteNonQuery(get_job_query, (job_id,))
            
            if not job_rows:
                return False
            
            # Log cancellation
            self.LogError(f"Job cancelled: {job_rows[0]['ServiceName']} {job_rows[0]['JobType']} QueueId={job_rows[0]['QueueId']}", 
                         "DatabaseManager", "CancelActiveJob")
            
            # Delete from ActiveJobs
            delete_query = "DELETE FROM ActiveJobs WHERE Id = %s"
            rows_affected = self.DatabaseService.ExecuteNonQuery(delete_query, (job_id,))
            
            return rows_affected > 0
            
        except Exception as e:
            LoggingService.LogException("Exception cancelling active job", e, "DatabaseManager", "CancelActiveJob")
            return False

    def CancelActiveJobs(self, service_name: str) -> bool:
        """Cancel all active jobs for a specific service."""
        try:
            # Get all active jobs for the service
            get_jobs_query = "SELECT Id, JobType, QueueId FROM ActiveJobs WHERE ServiceName = %s AND Status = 'Running'"
            jobs = self.DatabaseService.ExecuteQuery(get_jobs_query, (service_name,))
            
            if not jobs:
                return True  # No active jobs to cancel
            
            # Log cancellation for each job
            for job in jobs:
                self.LogError(f"Cancelling job: {service_name} {job[1]} QueueId={job[2]}", 
                             "DatabaseManager", "CancelActiveJobs")
            
            # Delete all active jobs for the service
            delete_query = "DELETE FROM ActiveJobs WHERE ServiceName = %s AND Status = 'Running'"
            rows_affected = self.DatabaseService.ExecuteNonQuery(delete_query, (service_name,))
            
            return rows_affected >= 0  # Return True even if no rows affected
            
        except Exception as e:
            LoggingService.LogException("Exception cancelling active jobs", e, "DatabaseManager", "CancelActiveJobs")
            return False

    def CompleteActiveJob(self, JobId: int, Success: bool = True, ErrorMessage: str = None) -> bool:
        """Complete an active job and remove it from tracking."""
        try:
            LoggingService.LogFunctionEntry("CompleteActiveJob", "DatabaseManager", JobId, Success, ErrorMessage)
            
            status = "Completed" if Success else "Failed"
            
            # Update the job status first
            update_query = """
                UPDATE ActiveJobs 
                SET Status = %s, UpdatedAt = NOW()
                WHERE Id = %s
            """
            
            self.DatabaseService.ExecuteNonQuery(update_query, (status, JobId))
            
            # Log the completion
            if Success:
                LoggingService.LogInfo(f"Active job {JobId} completed successfully", "DatabaseManager", "CompleteActiveJob")
            else:
                LoggingService.LogError(f"Active job {JobId} failed: {ErrorMessage}", "DatabaseManager", "CompleteActiveJob")
            
            # Remove from ActiveJobs table
            delete_query = "DELETE FROM ActiveJobs WHERE Id = %s"
            result = self.DatabaseService.ExecuteNonQuery(delete_query, (JobId,))
            
            return result > 0
            
        except Exception as e:
            LoggingService.LogException("Exception completing active job", e, "DatabaseManager", "CompleteActiveJob")
            return False

    # directive: transcode-flow-canonical
    def CreateActiveJob(self, ServiceName: str, JobType: str, QueueId: int, ProcessId: int = None, ThreadId: int = None, WorkerName: str = None) -> int:
        """Create an active job record; initial Phase='Setup' + PhaseTransitionedAt=NOW()."""
        try:
            LoggingService.LogFunctionEntry("CreateActiveJob", "DatabaseManager", ServiceName, JobType, QueueId, ProcessId, ThreadId)

            query = (
                "INSERT INTO ActiveJobs (ServiceName, JobType, QueueId, ProcessId, ThreadId, WorkerName, Status, StartedAt, Phase, PhaseTransitionedAt) "
                "VALUES (%s, %s, %s, %s, %s, %s, 'Running', NOW(), 'Setup', NOW()) "
                "RETURNING Id"
            )

            result = self.DatabaseService.ExecuteNonQuery(query, (ServiceName, JobType, QueueId, ProcessId, ThreadId, WorkerName))

            if result > 0:
                job_id = self.DatabaseService.LastInsertId
                
                LoggingService.LogInfo(f"Created active job {job_id} for {ServiceName} - JobType: {JobType}, QueueId: {QueueId}", "DatabaseManager", "CreateActiveJob")
                return job_id
            else:
                LoggingService.LogError(f"Failed to create active job for {ServiceName}", "DatabaseManager", "CreateActiveJob")
                return 0
                
        except Exception as e:
            LoggingService.LogException("Exception creating active job", e, "DatabaseManager", "CreateActiveJob")
            return 0

    def DeleteActiveJob(self, JobId: int) -> bool:
        """Delete a specific active job record."""
        try:
            LoggingService.LogFunctionEntry("DeleteActiveJob", "DatabaseManager", JobId)
            
            query = "DELETE FROM ActiveJobs WHERE Id = %s"
            affected_rows = self.DatabaseService.ExecuteNonQuery(query, (JobId,))
            
            if affected_rows > 0:
                LoggingService.LogInfo(f"Deleted active job {JobId}", "DatabaseManager", "DeleteActiveJob")
                return True
            else:
                LoggingService.LogWarning(f"Active job {JobId} not found for deletion", "DatabaseManager", "DeleteActiveJob")
                return False
                
        except Exception as e:
            LoggingService.LogException("Exception deleting active job", e, "DatabaseManager", "DeleteActiveJob")
            return False

    def DeleteActiveJobsByService(self, ServiceName: str) -> int:
        """Delete all active jobs for a specific service. Returns count of deleted jobs."""
        try:
            LoggingService.LogFunctionEntry("DeleteActiveJobsByService", "DatabaseManager", ServiceName)
            
            query = "DELETE FROM ActiveJobs WHERE ServiceName = %s"
            affected_rows = self.DatabaseService.ExecuteNonQuery(query, (ServiceName,))
            
            LoggingService.LogInfo(f"Deleted {affected_rows} active jobs for service {ServiceName}", "DatabaseManager", "DeleteActiveJobsByService")
            return affected_rows
            
        except Exception as e:
            LoggingService.LogException("Exception deleting active jobs by service", e, "DatabaseManager", "DeleteActiveJobsByService")
            return 0

    def GetActiveJobByQueueId(self, service_name: str, queue_id: int) -> Optional[Dict[str, Any]]:
        """Get active job by service and queue ID"""
        try:
            query = """
                SELECT Id, ServiceName, JobType, QueueId, ProcessId, ThreadId, 
                       StartedAt, Status, CreatedAt, UpdatedAt
                FROM ActiveJobs 
                WHERE ServiceName = %s AND QueueId = %s
            """
            
            rows = self.DatabaseService.ExecuteQuery(query, (service_name, queue_id))

            if rows:
                return rows[0]
            
            return None
            
        except Exception as e:
            LoggingService.LogException("Exception getting active job by queue ID", e, "DatabaseManager", "GetActiveJobByQueueId")
            return None

    def GetActiveJobDetails(self, JobId: int) -> Optional[Dict[str, Any]]:
        """Get detailed information about a specific active job."""
        try:
            LoggingService.LogFunctionEntry("GetActiveJobDetails", "DatabaseManager", JobId)
            
            query = """
                SELECT Id, ServiceName, JobType, QueueId, ProcessId, ThreadId, 
                       StartedAt, Status, CreatedAt, UpdatedAt
                FROM ActiveJobs 
                WHERE Id = %s
            """
            
            rows = self.DatabaseService.ExecuteQuery(query, (JobId,))
            
            if rows:
                LoggingService.LogInfo(f"Retrieved active job details for ID {JobId}", "DatabaseManager", "GetActiveJobDetails")
                return rows[0]
            else:
                LoggingService.LogWarning(f"Active job not found: {JobId}", "DatabaseManager", "GetActiveJobDetails")
                return None
                
        except Exception as e:
            LoggingService.LogException("Exception getting active job details", e, "DatabaseManager", "GetActiveJobDetails")
            return None

    ActiveJobsSortWhitelist = {
        "StartedAt": "StartedAt",
        "ServiceName": "ServiceName",
        "WorkerName": "WorkerName",
    }

    @staticmethod
    # directive: paged-query-core | # see paged-query.C11
    def BuildActiveJobsQuery(ServiceName: str, WorkerName: str = None, RunningOnly: bool = True, Page: int = 1, PageSize: int = 10000):
        """Compose a PagedQuery from the legacy (ServiceName + WorkerName + RunningOnly) args; default sort StartedAt ASC."""
        from Core.Querying import PagedQuery, QuerySort, EqualsFilter
        Filters = [EqualsFilter("ServiceName", ServiceName)]
        if RunningOnly:
            Filters.append(EqualsFilter("Status", "Running"))
        if WorkerName:
            Filters.append(EqualsFilter("WorkerName", WorkerName))
        Sort = QuerySort("StartedAt", "ASC", ActiveJobRepository.ActiveJobsSortWhitelist, NullsLast=False)
        return PagedQuery(Page=Page, PageSize=PageSize, Sort=Sort, Filters=Filters)

    # directive: paged-query-core | # see paged-query.C11
    def GetActiveJobsByService(self, Query: "PagedQuery") -> "PagedQueryResult":
        """Paged active jobs via PagedQuery; window-count strategy; ActiveJobs columns preserved verbatim (Id, ServiceName, JobType, QueueId, ProcessId, FFmpegPid, ThreadId, StartedAt, Status, CreatedAt, UpdatedAt, WorkerName)."""
        from Core.Querying import PagedQueryBuilder, PagedQueryResult, PagedQueryConfig, CountStrategy
        try:
            UnboundedConfig = PagedQueryConfig(DefaultPageSize=10000, MaxPageSize=10000)
            Builder = PagedQueryBuilder(self.DatabaseService, UnboundedConfig)
            return Builder.Execute(
                RowsSelect=(
                    "SELECT Id, ServiceName, JobType, QueueId, ProcessId, FFmpegPid, ThreadId, "
                    "StartedAt, Status, CreatedAt, UpdatedAt, WorkerName, "
                    "COUNT(*) OVER () AS __TotalCount "
                    "FROM ActiveJobs"
                ),
                Query=Query,
                CountStrategyChoice=CountStrategy.WINDOW,
            )
        except Exception as e:
            LoggingService.LogException("Exception getting active jobs by service", e, "ActiveJobRepository", "GetActiveJobsByService")
            return PagedQueryResult(Rows=[], TotalCount=0, Page=Query.Page, PageSize=Query.PageSize)

    def GetAllActiveJobProcessIds(self) -> List[int]:
        """Get all ProcessIds from active jobs for orphaned process detection."""
        try:
            query = """
                SELECT ProcessId 
                FROM ActiveJobs 
                WHERE Status = 'Running' AND ProcessId IS NOT NULL
            """
            
            rows = self.DatabaseService.ExecuteQuery(query)
            return [row['processid'] for row in rows if row['processid'] is not None]
            
        except Exception as e:
            LoggingService.LogException("Exception getting active job process IDs", e, "DatabaseManager", "GetAllActiveJobProcessIds")
            return []

    def GetAllActiveJobs(self) -> List[Dict[str, Any]]:
        """Get all active jobs"""
        try:
            query = """
                SELECT Id, ServiceName, JobType, QueueId, ProcessId, ThreadId, 
                       StartedAt, Status, CreatedAt, UpdatedAt
                FROM ActiveJobs
            """
            
            rows = self.DatabaseService.ExecuteQuery(query)
            return list(rows)
            
        except Exception as e:
            LoggingService.LogException("Exception getting all active jobs", e, "DatabaseManager", "GetAllActiveJobs")
            return []

    # directive: transcode-flow-canonical
    def SetActiveJobFFmpegPid(self, ActiveJobId: int, FFmpegPid: Optional[int]) -> bool:
        """Record the FFmpeg subprocess PID (None clears; used at Encoding->PostEncode transition)."""
        try:
            query = "UPDATE ActiveJobs SET FFmpegPid = %s, UpdatedAt = NOW() WHERE Id = %s"
            affected = self.DatabaseService.ExecuteNonQuery(query, (FFmpegPid, ActiveJobId))
            return affected > 0
        except Exception as e:
            LoggingService.LogException(
                f"SetActiveJobFFmpegPid({ActiveJobId}, {FFmpegPid}) failed",
                e, "DatabaseManager", "SetActiveJobFFmpegPid"
            )
            return False

    def UpdateActiveJobProcessId(self, ActiveJobId: int, ProcessId: int) -> bool:
        """Update the ProcessId for an active job (for FFmpeg PID tracking)."""
        try:
            LoggingService.LogFunctionEntry("UpdateActiveJobProcessId", "DatabaseManager", ActiveJobId, ProcessId)
            
            query = "UPDATE ActiveJobs SET ProcessId = %s, UpdatedAt = NOW() WHERE Id = %s"
            affected_rows = self.DatabaseService.ExecuteNonQuery(query, (ProcessId, ActiveJobId))
            
            if affected_rows > 0:
                LoggingService.LogInfo(f"Updated ActiveJob {ActiveJobId} with ProcessId {ProcessId}", 
                                      "DatabaseManager", "UpdateActiveJobProcessId")
                return True
            else:
                LoggingService.LogWarning(f"No rows updated for ActiveJob {ActiveJobId}", 
                                         "DatabaseManager", "UpdateActiveJobProcessId")
                return False
                
        except Exception as e:
            LoggingService.LogException("Exception updating active job process ID", e, 
                                       "DatabaseManager", "UpdateActiveJobProcessId")
            return False

    def UpdateActiveJobThreadId(self, job_id: int, thread_id: int) -> bool:
        """Update active job with thread ID"""
        try:
            query = """
                UPDATE ActiveJobs 
                SET ThreadId = %s, UpdatedAt = NOW()
                WHERE Id = %s
            """
            
            rows_affected = self.DatabaseService.ExecuteNonQuery(query, (thread_id, job_id))
            return rows_affected > 0
            
        except Exception as e:
            LoggingService.LogException("Exception updating active job thread ID", e, "DatabaseManager", "UpdateActiveJobThreadId")
            return False
