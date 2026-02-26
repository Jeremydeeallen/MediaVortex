"""
ServiceControlRepository
Data access for ServiceStatus, ServiceCommands, and ActiveJobs tables.
Extracted from DatabaseManager as part of vertical slice architecture migration.
"""

import json
from typing import Dict, Any, Optional, List
from Core.Database.BaseRepository import BaseRepository
from Core.Logging.LoggingService import LoggingService


class ServiceControlRepository(BaseRepository):
    """Data access for service control related tables."""

    # ─── ServiceStatus Methods ───────────────────────────────────────────

    def SaveServiceStatus(self, ServiceStatus: Dict[str, Any]) -> bool:
        """Save service status to database."""
        try:
            LoggingService.LogFunctionEntry("SaveServiceStatus", "ServiceControlRepository")

            # Check if service status already exists
            ExistingStatus = self.GetServiceStatus(ServiceStatus.get('ServiceName', ''))

            if ExistingStatus:
                # Update existing status
                query = """
                UPDATE ServiceStatus SET
                    Status = %s, HealthStatus = %s, StartTime = %s, LastHealthCheck = %s,
                    UptimeSeconds = %s, MemoryUsage = %s, CPUUsage = %s, DatabaseConnection = %s,
                    DiskSpace = %s, ErrorCount = %s, MaxErrors = %s, ActiveJobsCount = %s,
                    IsProcessing = %s, ProcessId = %s, Version = %s, ServiceType = %s,
                    MaxConcurrentJobs = %s, UpdatedAt = NOW()
                WHERE ServiceName = %s
                """
                parameters = (
                    ServiceStatus.get('Status'),
                    ServiceStatus.get('HealthStatus'),
                    ServiceStatus.get('StartTime'),
                    ServiceStatus.get('LastHealthCheck'),
                    ServiceStatus.get('UptimeSeconds'),
                    ServiceStatus.get('MemoryUsage'),
                    ServiceStatus.get('CPUUsage'),
                    ServiceStatus.get('DatabaseConnection'),
                    ServiceStatus.get('DiskSpace'),
                    ServiceStatus.get('ErrorCount'),
                    ServiceStatus.get('MaxErrors'),
                    ServiceStatus.get('ActiveJobsCount'),
                    ServiceStatus.get('IsProcessing'),
                    ServiceStatus.get('ProcessId'),
                    ServiceStatus.get('Version'),
                    ServiceStatus.get('ServiceType'),
                    ServiceStatus.get('MaxConcurrentJobs', 1),
                    ServiceStatus.get('ServiceName')
                )
            else:
                # Insert new status
                query = """
                INSERT INTO ServiceStatus (
                    ServiceName, Status, HealthStatus, StartTime, LastHealthCheck,
                    UptimeSeconds, MemoryUsage, CPUUsage, DatabaseConnection, DiskSpace,
                    ErrorCount, MaxErrors, ActiveJobsCount, IsProcessing, ProcessId,
                    Version, ServiceType, MaxConcurrentJobs, CreatedAt, UpdatedAt
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, NOW(), NOW())
                """
                parameters = (
                    ServiceStatus.get('ServiceName'),
                    ServiceStatus.get('Status'),
                    ServiceStatus.get('HealthStatus'),
                    ServiceStatus.get('StartTime'),
                    ServiceStatus.get('LastHealthCheck'),
                    ServiceStatus.get('UptimeSeconds'),
                    ServiceStatus.get('MemoryUsage'),
                    ServiceStatus.get('CPUUsage'),
                    ServiceStatus.get('DatabaseConnection'),
                    ServiceStatus.get('DiskSpace'),
                    ServiceStatus.get('ErrorCount'),
                    ServiceStatus.get('MaxErrors'),
                    ServiceStatus.get('ActiveJobsCount'),
                    ServiceStatus.get('IsProcessing'),
                    ServiceStatus.get('ProcessId'),
                    ServiceStatus.get('Version'),
                    ServiceStatus.get('ServiceType'),
                    ServiceStatus.get('MaxConcurrentJobs', 1)
                )

            self.ExecuteNonQuery(query, parameters)
            LoggingService.LogDebug(f"Service status saved for {ServiceStatus.get('ServiceName')}", "ServiceControlRepository", "SaveServiceStatus")
            return True

        except Exception as e:
            LoggingService.LogException("Exception saving service status", e, "ServiceControlRepository", "SaveServiceStatus")
            return False

    def UpdateServiceStatus(self, ServiceName: str, StatusData: Dict[str, Any]) -> bool:
        """Update service status in database."""
        try:
            LoggingService.LogFunctionEntry("UpdateServiceStatus", "ServiceControlRepository", ServiceName)

            # Build dynamic update query
            UpdateFields = []
            Parameters = []

            for key, value in StatusData.items():
                UpdateFields.append(f"{key} = %s")
                Parameters.append(value)

            if not UpdateFields:
                LoggingService.LogWarning("No fields to update", "ServiceControlRepository", "UpdateServiceStatus")
                return False

            Parameters.append(ServiceName)
            query = f"UPDATE ServiceStatus SET {', '.join(UpdateFields)}, UpdatedAt = NOW() WHERE ServiceName = %s"

            self.ExecuteNonQuery(query, Parameters)
            LoggingService.LogDebug(f"Service status updated for {ServiceName}", "ServiceControlRepository", "UpdateServiceStatus")
            return True

        except Exception as e:
            LoggingService.LogException("Exception updating service status", e, "ServiceControlRepository", "UpdateServiceStatus")
            return False

    def GetServiceStatus(self, ServiceName: str) -> Optional[Dict[str, Any]]:
        """Get current service status."""
        try:
            LoggingService.LogFunctionEntry("GetServiceStatus", "ServiceControlRepository", ServiceName)

            query = "SELECT * FROM ServiceStatus WHERE ServiceName = %s"
            rows = self.ExecuteQuery(query, (ServiceName,))

            if rows:
                LoggingService.LogDebug(f"Retrieved service status for {ServiceName}", "ServiceControlRepository", "GetServiceStatus")
                return rows[0]
            else:
                LoggingService.LogDebug(f"No service status found for {ServiceName}", "ServiceControlRepository", "GetServiceStatus")
                return None

        except Exception as e:
            LoggingService.LogException("Exception getting service status", e, "ServiceControlRepository", "GetServiceStatus")
            return None

    # ─── ServiceCommands Methods ─────────────────────────────────────────

    def CreateServiceCommand(self, CommandData: Dict[str, Any]) -> int:
        """Create a new service command."""
        try:
            LoggingService.LogFunctionEntry("CreateServiceCommand", "ServiceControlRepository")

            query = """
                INSERT INTO ServiceCommands (
                CommandType, SourceService, TargetService, Parameters, Status,
                Priority, CreatedBy, CreatedAt, UpdatedAt
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, NOW(), NOW())
                RETURNING Id
            """

            parameters = (
                CommandData.get('CommandType'),
                CommandData.get('SourceService', 'ServiceControlController'),
                CommandData.get('TargetService'),
                json.dumps(CommandData.get('Parameters', {})),
                CommandData.get('Status', 'Pending'),
                CommandData.get('Priority', 1),
                CommandData.get('CreatedBy', 'Unknown')
            )

            result = self.ExecuteNonQuery(query, parameters)

            if result:
                command_id = self.GetLastInsertId()
                LoggingService.LogInfo(f"Created ServiceCommand {command_id}", "ServiceControlRepository", "CreateServiceCommand")
                return command_id
            else:
                LoggingService.LogError("Failed to create ServiceCommand", "ServiceControlRepository", "CreateServiceCommand")
                return 0

        except Exception as e:
            LoggingService.LogException("Error creating ServiceCommand", e, "ServiceControlRepository", "CreateServiceCommand")
            return 0

    def UpdateServiceCommandStatus(self, CommandId: int, Status: str, Result: str = None) -> bool:
        """Update service command status."""
        try:
            LoggingService.LogFunctionEntry("UpdateServiceCommandStatus", "ServiceControlRepository")

            query = """
            UPDATE ServiceCommands
            SET Status = %s, Result = %s, UpdatedAt = NOW()
            WHERE Id = %s
            """

            result = self.ExecuteNonQuery(query, (Status, Result, CommandId))

            if result:
                LoggingService.LogInfo(f"Updated ServiceCommand {CommandId} status to {Status}", "ServiceControlRepository", "UpdateServiceCommandStatus")
                return True
            else:
                LoggingService.LogError(f"Failed to update ServiceCommand {CommandId}", "ServiceControlRepository", "UpdateServiceCommandStatus")
                return False

        except Exception as e:
            LoggingService.LogException("Error updating ServiceCommand status", e, "ServiceControlRepository", "UpdateServiceCommandStatus")
            return False

    def GetPendingCommandsForService(self, ServiceName: str) -> List[Dict[str, Any]]:
        """Get pending commands for specific service."""
        try:
            LoggingService.LogFunctionEntry("GetPendingCommandsForService", "ServiceControlRepository", ServiceName)

            query = """
            SELECT * FROM ServiceCommands
            WHERE TargetService = %s AND Status = 'Pending'
            ORDER BY Priority DESC, CreatedAt ASC
            """
            rows = self.ExecuteQuery(query, (ServiceName,))

            LoggingService.LogDebug(f"Retrieved {len(rows)} pending commands for {ServiceName}", "ServiceControlRepository", "GetPendingCommandsForService")
            return rows

        except Exception as e:
            LoggingService.LogException("Exception getting pending commands for service", e, "ServiceControlRepository", "GetPendingCommandsForService")
            return []

    # ─── ActiveJobs Methods ──────────────────────────────────────────────

    def CreateActiveJob(self, ServiceName: str, JobType: str, QueueId: int, ProcessId: int = None, ThreadId: int = None) -> int:
        """Create an active job record for tracking."""
        try:
            LoggingService.LogFunctionEntry("CreateActiveJob", "ServiceControlRepository", ServiceName, JobType, QueueId, ProcessId, ThreadId)

            query = """
                INSERT INTO ActiveJobs (ServiceName, JobType, QueueId, ProcessId, ThreadId, Status, StartedAt)
                VALUES (%s, %s, %s, %s, %s, 'Running', NOW())
                RETURNING Id
            """

            result = self.ExecuteNonQuery(query, (ServiceName, JobType, QueueId, ProcessId, ThreadId))

            if result > 0:
                job_id = self.DatabaseService.LastInsertId

                LoggingService.LogInfo(f"Created active job {job_id} for {ServiceName} - JobType: {JobType}, QueueId: {QueueId}", "ServiceControlRepository", "CreateActiveJob")
                return job_id
            else:
                LoggingService.LogError(f"Failed to create active job for {ServiceName}", "ServiceControlRepository", "CreateActiveJob")
                return 0

        except Exception as e:
            LoggingService.LogException("Exception creating active job", e, "ServiceControlRepository", "CreateActiveJob")
            return 0

    def CompleteActiveJob(self, JobId: int, Success: bool = True, ErrorMessage: str = None) -> bool:
        """Complete an active job and remove it from tracking."""
        try:
            LoggingService.LogFunctionEntry("CompleteActiveJob", "ServiceControlRepository", JobId, Success, ErrorMessage)

            status = "Completed" if Success else "Failed"

            # Update the job status first
            update_query = """
                UPDATE ActiveJobs
                SET Status = %s, UpdatedAt = NOW()
                WHERE Id = %s
            """

            self.ExecuteNonQuery(update_query, (status, JobId))

            # Log the completion
            if Success:
                LoggingService.LogInfo(f"Active job {JobId} completed successfully", "ServiceControlRepository", "CompleteActiveJob")
            else:
                LoggingService.LogError(f"Active job {JobId} failed: {ErrorMessage}", "ServiceControlRepository", "CompleteActiveJob")

            # Remove from ActiveJobs table
            delete_query = "DELETE FROM ActiveJobs WHERE Id = %s"
            result = self.ExecuteNonQuery(delete_query, (JobId,))

            return result > 0

        except Exception as e:
            LoggingService.LogException("Exception completing active job", e, "ServiceControlRepository", "CompleteActiveJob")
            return False

    def GetActiveJobByQueueId(self, ServiceName: str, QueueId: int) -> Optional[Dict[str, Any]]:
        """Get active job by service name and queue ID."""
        try:
            query = """
                SELECT Id, ServiceName, JobType, QueueId, ProcessId, ThreadId,
                       StartedAt, Status, CreatedAt, UpdatedAt
                FROM ActiveJobs
                WHERE ServiceName = %s AND QueueId = %s AND Status = 'Running'
            """

            rows = self.ExecuteQuery(query, (ServiceName, QueueId))

            if rows:
                return rows[0]
            return None

        except Exception as e:
            LoggingService.LogException("Exception getting active job by queue ID", e, "ServiceControlRepository", "GetActiveJobByQueueId")
            return None

    def GetActiveJobsByService(self, ServiceName: str) -> List[Dict[str, Any]]:
        """Get all active jobs for a specific service."""
        try:
            query = """
                SELECT Id, ServiceName, JobType, QueueId, ProcessId, ThreadId,
                       StartedAt, Status, CreatedAt, UpdatedAt
                FROM ActiveJobs
                WHERE ServiceName = %s AND Status = 'Running'
                ORDER BY StartedAt ASC
            """

            rows = self.ExecuteQuery(query, (ServiceName,))
            return list(rows)

        except Exception as e:
            LoggingService.LogException("Exception getting active jobs by service", e, "ServiceControlRepository", "GetActiveJobsByService")
            return []

    def GetAllActiveJobs(self) -> List[Dict[str, Any]]:
        """Get all active jobs across all services."""
        try:
            query = """
                SELECT Id, ServiceName, JobType, QueueId, ProcessId, ThreadId,
                       StartedAt, Status, CreatedAt, UpdatedAt
                FROM ActiveJobs
                WHERE Status = 'Running'
                ORDER BY ServiceName, StartedAt ASC
            """

            rows = self.ExecuteQuery(query)
            return list(rows)

        except Exception as e:
            LoggingService.LogException("Exception getting all active jobs", e, "ServiceControlRepository", "GetAllActiveJobs")
            return []

    def GetAllActiveJobProcessIds(self) -> List[int]:
        """Get all ProcessIds from active jobs for orphaned process detection."""
        try:
            query = """
                SELECT ProcessId
                FROM ActiveJobs
                WHERE Status = 'Running' AND ProcessId IS NOT NULL
            """

            rows = self.ExecuteQuery(query)
            return [row['processid'] for row in rows if row['processid'] is not None]

        except Exception as e:
            LoggingService.LogException("Exception getting active job process IDs", e, "ServiceControlRepository", "GetAllActiveJobProcessIds")
            return []

    def CancelActiveJob(self, JobId: int) -> bool:
        """Cancel a specific active job by ID."""
        try:
            LoggingService.LogFunctionEntry("CancelActiveJob", "ServiceControlRepository", JobId)

            update_query = """
                UPDATE ActiveJobs
                SET Status = 'Cancelled', UpdatedAt = NOW()
                WHERE Id = %s
            """

            result = self.ExecuteNonQuery(update_query, (JobId,))

            if result > 0:
                LoggingService.LogInfo(f"Active job {JobId} cancelled successfully", "ServiceControlRepository", "CancelActiveJob")
                return True
            else:
                LoggingService.LogWarning(f"Active job {JobId} not found or already cancelled", "ServiceControlRepository", "CancelActiveJob")
                return False

        except Exception as e:
            LoggingService.LogException("Exception cancelling active job", e, "ServiceControlRepository", "CancelActiveJob")
            return False

    def UpdateActiveJobThreadId(self, job_id: int, thread_id: int) -> bool:
        """Update active job with thread ID."""
        try:
            query = """
                UPDATE ActiveJobs
                SET ThreadId = %s, UpdatedAt = NOW()
                WHERE Id = %s
            """

            rows_affected = self.ExecuteNonQuery(query, (thread_id, job_id))
            return rows_affected > 0

        except Exception as e:
            LoggingService.LogException("Exception updating active job thread ID", e, "ServiceControlRepository", "UpdateActiveJobThreadId")
            return False

    def UpdateActiveJobProcessId(self, ActiveJobId: int, ProcessId: int) -> bool:
        """Update the ProcessId for an active job (for FFmpeg PID tracking)."""
        try:
            LoggingService.LogFunctionEntry("UpdateActiveJobProcessId", "ServiceControlRepository", ActiveJobId, ProcessId)

            query = "UPDATE ActiveJobs SET ProcessId = %s, UpdatedAt = NOW() WHERE Id = %s"
            affected_rows = self.ExecuteNonQuery(query, (ProcessId, ActiveJobId))

            if affected_rows > 0:
                LoggingService.LogInfo(f"Updated ActiveJob {ActiveJobId} with ProcessId {ProcessId}",
                                      "ServiceControlRepository", "UpdateActiveJobProcessId")
                return True
            else:
                LoggingService.LogWarning(f"No rows updated for ActiveJob {ActiveJobId}",
                                         "ServiceControlRepository", "UpdateActiveJobProcessId")
                return False

        except Exception as e:
            LoggingService.LogException("Exception updating active job process ID", e,
                                       "ServiceControlRepository", "UpdateActiveJobProcessId")
            return False

    def GetActiveJobDetails(self, JobId: int) -> Optional[Dict[str, Any]]:
        """Get detailed information about a specific active job."""
        try:
            LoggingService.LogFunctionEntry("GetActiveJobDetails", "ServiceControlRepository", JobId)

            query = """
                SELECT Id, ServiceName, JobType, QueueId, ProcessId, ThreadId,
                       StartedAt, Status, CreatedAt, UpdatedAt
                FROM ActiveJobs
                WHERE Id = %s
            """

            rows = self.ExecuteQuery(query, (JobId,))

            if rows:
                LoggingService.LogInfo(f"Retrieved active job details for ID {JobId}", "ServiceControlRepository", "GetActiveJobDetails")
                return rows[0]
            else:
                LoggingService.LogWarning(f"Active job not found: {JobId}", "ServiceControlRepository", "GetActiveJobDetails")
                return None

        except Exception as e:
            LoggingService.LogException("Exception getting active job details", e, "ServiceControlRepository", "GetActiveJobDetails")
            return None

    def DeleteActiveJob(self, JobId: int) -> bool:
        """Delete a specific active job record."""
        try:
            LoggingService.LogFunctionEntry("DeleteActiveJob", "ServiceControlRepository", JobId)

            query = "DELETE FROM ActiveJobs WHERE Id = %s"
            affected_rows = self.ExecuteNonQuery(query, (JobId,))

            if affected_rows > 0:
                LoggingService.LogInfo(f"Deleted active job {JobId}", "ServiceControlRepository", "DeleteActiveJob")
                return True
            else:
                LoggingService.LogWarning(f"Active job {JobId} not found for deletion", "ServiceControlRepository", "DeleteActiveJob")
                return False

        except Exception as e:
            LoggingService.LogException("Exception deleting active job", e, "ServiceControlRepository", "DeleteActiveJob")
            return False

    def DeleteActiveJobsByService(self, ServiceName: str) -> int:
        """Delete all active jobs for a specific service. Returns count of deleted jobs."""
        try:
            LoggingService.LogFunctionEntry("DeleteActiveJobsByService", "ServiceControlRepository", ServiceName)

            query = "DELETE FROM ActiveJobs WHERE ServiceName = %s"
            affected_rows = self.ExecuteNonQuery(query, (ServiceName,))

            LoggingService.LogInfo(f"Deleted {affected_rows} active jobs for service {ServiceName}", "ServiceControlRepository", "DeleteActiveJobsByService")
            return affected_rows

        except Exception as e:
            LoggingService.LogException("Exception deleting active jobs by service", e, "ServiceControlRepository", "DeleteActiveJobsByService")
            return 0

    def ResetQueueJobsToPending(self, QueueIds: List[int], QueueTable: str) -> int:
        """Reset multiple queue jobs to Pending status. Returns count of reset jobs."""
        try:
            LoggingService.LogFunctionEntry("ResetQueueJobsToPending", "ServiceControlRepository", QueueIds, QueueTable)

            if not QueueIds:
                return 0

            # Validate queue table name to prevent SQL injection
            valid_tables = ['TranscodeQueue', 'QualityTestingQueue']
            if QueueTable not in valid_tables:
                LoggingService.LogError(f"Invalid queue table name: {QueueTable}", "ServiceControlRepository", "ResetQueueJobsToPending")
                return 0

            placeholders = ','.join(['%s'] * len(QueueIds))

            if QueueTable == 'TranscodeQueue':
                query = f"""
                    UPDATE {QueueTable}
                    SET Status = 'Pending', DateStarted = NULL
                    WHERE Id IN ({placeholders})
                """
            else:
                query = f"""
                    UPDATE {QueueTable}
                    SET DateStarted = NULL, DateCompleted = NULL
                    WHERE Id IN ({placeholders})
                """

            affected_rows = self.ExecuteNonQuery(query, QueueIds)

            LoggingService.LogInfo(f"Reset {affected_rows} jobs to Pending in {QueueTable}", "ServiceControlRepository", "ResetQueueJobsToPending")
            return affected_rows

        except Exception as e:
            LoggingService.LogException("Exception resetting queue jobs to pending", e, "ServiceControlRepository", "ResetQueueJobsToPending")
            return 0
