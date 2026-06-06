from typing import List, Optional, Dict, Any
from datetime import datetime, timezone
import os
from Models.TranscodeProfileModel import TranscodeProfileModel
from Models.ProfileThresholdModel import ProfileThresholdModel
from Models.RootFolderModel import RootFolderModel
from Models.MediaFileModel import MediaFileModel
from Models.SeasonModel import SeasonModel
from Models.FileScanResultModel import FileScanResultModel
from Models.TranscodeQueueModel import TranscodeQueueModel
from Models.TranscodeAttemptModel import TranscodeAttemptModel
from Models.TranscodeFileModel import TranscodeFileModel
# Quality testing models removed - using simple QualityTest methods instead
from Services.DatabaseService import DatabaseService
from Services.LoggingService import LoggingService
from Core.Database.DatabaseService import EscapeLikePattern
from Core.Database.BaseRepository import BaseRepository
from Core.Path.Path import Path, PathError
from Features.MediaFiles.MediaFilesRepository import MediaFilesRepository
from Features.TranscodeQueue.TranscodeQueueRepository import TranscodeQueueRepository
from Features.TranscodeJob.TranscodeJobRepository import TranscodeJobRepository
from Features.QualityTesting.QualityTestRepository import QualityTestRepository
from Features.ShowSettings.ShowSettingsRepository import ShowSettingsRepository
from Features.FileScanning.FileScanningRepository import FileScanningRepository
from Features.Activity.ActivityRepository import ActivityRepository


# directive: path-schema-migration | # see path.S8
class DatabaseManager(
    MediaFilesRepository,
    TranscodeQueueRepository,
    TranscodeJobRepository,
    QualityTestRepository,
    ShowSettingsRepository,
    FileScanningRepository,
    ActivityRepository,
):
    """Facade aggregating per-aggregate Repositories; legacy callers use this; per-aggregate code should use the specific Repository."""
    
    def __init__(self, DatabaseServiceInstance: DatabaseService = None):
        self.DatabaseService = DatabaseServiceInstance or DatabaseService()

    # allow: r19-monolith-edit-phase-8-path-schema-migration
    # directive: path-schema-migration | # see path.S8
    def RunMigrations(self):
        """Run database schema migrations. Safe to call multiple times."""
        try:
            connection = self.DatabaseService.GetConnection()
            try:
                cursor = connection.cursor()

                # Helper to check if a column exists in a table
                def column_exists(table_name, column_name):
                    cursor.execute("""
                        SELECT column_name FROM information_schema.columns
                        WHERE table_name = %s AND column_name = %s
                    """, (table_name.lower(), column_name.lower()))
                    return cursor.fetchone() is not None

                # Check if ProcessingMode column exists in TranscodeQueue
                if not column_exists('TranscodeQueue', 'ProcessingMode'):
                    cursor.execute("ALTER TABLE TranscodeQueue ADD COLUMN ProcessingMode TEXT DEFAULT 'Transcode'")
                    connection.commit()
                    LoggingService.LogInfo("Added ProcessingMode column to TranscodeQueue", "DatabaseManager", "RunMigrations")

                # Add AudioCodec and SubtitleFormats columns to MediaFiles
                if not column_exists('MediaFiles', 'AudioCodec'):
                    cursor.execute("ALTER TABLE MediaFiles ADD COLUMN AudioCodec TEXT")
                    connection.commit()
                    LoggingService.LogInfo("Added AudioCodec column to MediaFiles", "DatabaseManager", "RunMigrations")
                if not column_exists('MediaFiles', 'SubtitleFormats'):
                    cursor.execute("ALTER TABLE MediaFiles ADD COLUMN SubtitleFormats TEXT")
                    connection.commit()
                    LoggingService.LogInfo("Added SubtitleFormats column to MediaFiles", "DatabaseManager", "RunMigrations")

                # Create JellyfinOperations table for persisting FFmpeg log data
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS JellyfinOperations (
                        LogFileName TEXT PRIMARY KEY,
                        OperationType TEXT NOT NULL,
                        FilePath TEXT,
                        FileName TEXT,
                        VideoCodec TEXT,
                        AudioCodec TEXT,
                        Container TEXT,
                        Resolution TEXT,
                        SubtitleCodecs TEXT,
                        Reason TEXT,
                        TranscodeActions TEXT,
                        LogDate TEXT,
                        ImportedAt TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                """)

                # Migration: add columns and clear stale data when schema changes
                for col in ['SubtitleCodecs', 'TranscodeActions',
                            'DestResolution', 'DestProfile', 'DestLevel', 'DestPixelFormat', 'DestFormat']:
                    if not column_exists('JellyfinOperations', col):
                        try:
                            cursor.execute(f"ALTER TABLE JellyfinOperations ADD COLUMN {col} TEXT")
                            # New column added — clear stale records for re-import with correct classification
                            cursor.execute("DELETE FROM JellyfinOperations")
                        except Exception:
                            pass  # Column already exists

                # Add CompletedDate column to TranscodeAttempts
                if not column_exists('TranscodeAttempts', 'CompletedDate'):
                    cursor.execute("ALTER TABLE TranscodeAttempts ADD COLUMN CompletedDate TIMESTAMP")
                    connection.commit()
                    LoggingService.LogInfo("Added CompletedDate column to TranscodeAttempts", "DatabaseManager", "RunMigrations")

                # Add FFprobe failure tracking columns to MediaFiles
                if not column_exists('MediaFiles', 'FFprobeFailureCount'):
                    cursor.execute("ALTER TABLE MediaFiles ADD COLUMN FFprobeFailureCount INTEGER DEFAULT 0")
                    connection.commit()
                    LoggingService.LogInfo("Added FFprobeFailureCount column to MediaFiles", "DatabaseManager", "RunMigrations")
                if not column_exists('MediaFiles', 'LastFFprobeError'):
                    cursor.execute("ALTER TABLE MediaFiles ADD COLUMN LastFFprobeError TEXT")
                    connection.commit()
                    LoggingService.LogInfo("Added LastFFprobeError column to MediaFiles", "DatabaseManager", "RunMigrations")
                if not column_exists('MediaFiles', 'LastFFprobeAttemptDate'):
                    cursor.execute("ALTER TABLE MediaFiles ADD COLUMN LastFFprobeAttemptDate TIMESTAMP")
                    connection.commit()
                    LoggingService.LogInfo("Added LastFFprobeAttemptDate column to MediaFiles", "DatabaseManager", "RunMigrations")

                # Add audio language tracking columns to MediaFiles
                if not column_exists('MediaFiles', 'AudioLanguages'):
                    cursor.execute("ALTER TABLE MediaFiles ADD COLUMN AudioLanguages TEXT")
                    connection.commit()
                    LoggingService.LogInfo("Added AudioLanguages column to MediaFiles", "DatabaseManager", "RunMigrations")
                if not column_exists('MediaFiles', 'HasExplicitEnglishAudio'):
                    cursor.execute("ALTER TABLE MediaFiles ADD COLUMN HasExplicitEnglishAudio BOOLEAN")
                    connection.commit()
                    LoggingService.LogInfo("Added HasExplicitEnglishAudio column to MediaFiles", "DatabaseManager", "RunMigrations")

                # Create ShowSettings table for per-show target resolution overrides
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS ShowSettings (
                        Id SERIAL PRIMARY KEY,
                        ShowFolder TEXT NOT NULL UNIQUE,
                        TargetResolution TEXT NOT NULL DEFAULT '',
                        CreatedDate TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        LastModifiedDate TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                """)
                connection.commit()

                connection.commit()
            finally:
                self.DatabaseService.CloseConnection(connection)
        except Exception as e:
            LoggingService.LogWarning(f"Migration warning: {e}", "DatabaseManager", "RunMigrations")

    # Profile Management Methods
    
    
    
    
    # Profile Threshold Management Methods

    
    
    
    # Root Folder Management Methods
    
    
    
    
    
    # TranscodeQueue Management Methods








    
    

    
    def _ConvertPixelDimensionsToResolutionCategory(self, PixelDimensions: str) -> str:
        """Convert pixel dimensions (e.g. '3840x2160') to resolution category.

        Width-primary because mastering targets are width-fixed (1280 = 720p,
        1920 = 1080p, 3840 = 4K) but heights vary with cropping/letterboxing
        (e.g. 1280x718 is broadcast 720p; strict `height >= 720` misclassifies
        it as 480p). Falls back to height for narrow/portrait video.

        Same logic as MediaProbeBusinessService._DeriveResolutionCategory and
        QueueManagementBusinessService._ResolutionCategoryFromPixels; should be
        unified into a Core helper in a follow-up.
        """
        try:
            if not PixelDimensions or 'x' not in PixelDimensions:
                return PixelDimensions  # Return as-is if not in expected format

            Parts = PixelDimensions.split('x', 1)
            width = int(Parts[0])
            height = int(Parts[1])

            # Width-primary discrimination
            if width >= 3000:
                return "2160p"
            if width >= 1700:
                return "1080p"
            if width >= 1100:
                return "720p"
            if width >= 600:
                return "480p"
            # Fall through to height for narrow/portrait content
            if height >= 2000:
                return "2160p"
            if height >= 950:
                return "1080p"
            if height >= 650:
                return "720p"
            return "480p"

        except (ValueError, IndexError):
            return PixelDimensions
    

    def ConvertStringToDateTime(self, DateString) -> Optional[datetime]:
        """Convert date string from database to datetime object. Pass through if already datetime."""
        if not DateString:
            return None
        if isinstance(DateString, datetime):
            return DateString
        try:
            if 'T' in DateString:
                return datetime.fromisoformat(DateString.replace('Z', '+00:00'))
            else:
                return datetime.strptime(DateString, '%Y-%m-%d %H:%M:%S.%f')
        except (ValueError, AttributeError):
            try:
                return datetime.strptime(DateString, '%Y-%m-%d %H:%M:%S')
            except (ValueError, AttributeError):
                LoggingService.LogWarning(f"Failed to convert date string to datetime: {DateString}", "DatabaseManager", "ConvertStringToDateTime")
                return None
    
    # Quality Testing Database Methods
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    

    def CheckDatabaseConnection(self) -> bool:
        """Check if database connection is available."""
        try:
            # Test database connection with simple query
            testResult = self.DatabaseService.ExecuteQuery("SELECT 1")
            if testResult:
                # Only log failures, not successful connections to avoid log flooding
                return True
            else:
                LoggingService.LogError("Database connection test failed", "DatabaseManager", "CheckDatabaseConnection")
                return False
                
        except Exception as e:
            LoggingService.LogException("Exception checking database connection", e, "DatabaseManager", "CheckDatabaseConnection")
            return False
    
    # Quality Test Progress Management Methods
    
    
    # Quality Test Results Management Methods
    
    



    
    
    
    def CreateActiveJob(self, ServiceName: str, JobType: str, QueueId: int, ProcessId: int = None, ThreadId: int = None, WorkerName: str = None) -> int:
        """Create an active job record for tracking."""
        try:
            LoggingService.LogFunctionEntry("CreateActiveJob", "DatabaseManager", ServiceName, JobType, QueueId, ProcessId, ThreadId)

            query = """
                INSERT INTO ActiveJobs (ServiceName, JobType, QueueId, ProcessId, ThreadId, WorkerName, Status, StartedAt)
                VALUES (%s, %s, %s, %s, %s, %s, 'Running', NOW())
                RETURNING Id
            """

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
    
    def GetActiveJobByQueueId(self, ServiceName: str, QueueId: int) -> Optional[Dict[str, Any]]:
        """Get active job by service name and queue ID."""
        try:
            query = """
                SELECT Id, ServiceName, JobType, QueueId, ProcessId, ThreadId, 
                       StartedAt, Status, CreatedAt, UpdatedAt
                FROM ActiveJobs 
                WHERE ServiceName = %s AND QueueId = %s AND Status = 'Running'
            """
            
            rows = self.DatabaseService.ExecuteQuery(query, (ServiceName, QueueId))

            if rows:
                return rows[0]
            return None
            
        except Exception as e:
            LoggingService.LogException("Exception getting active job by queue ID", e, "DatabaseManager", "GetActiveJobByQueueId")
            return None
    
    def GetActiveJobsByService(self, ServiceName: str, WorkerName: str = None, RunningOnly: bool = True) -> List[Dict[str, Any]]:
        """Get active jobs for a service, optionally filtered by worker.
        RunningOnly=True (default) returns only Status='Running'. Set False for crash recovery."""
        try:
            conditions = ["ServiceName = %s"]
            params = [ServiceName]

            if RunningOnly:
                conditions.append("Status = 'Running'")

            if WorkerName:
                conditions.append("WorkerName = %s")
                params.append(WorkerName)

            query = """
                SELECT Id, ServiceName, JobType, QueueId, ProcessId, FFmpegPid, ThreadId,
                       StartedAt, Status, CreatedAt, UpdatedAt, WorkerName
                FROM ActiveJobs
                WHERE {}
                ORDER BY StartedAt ASC
            """.format(" AND ".join(conditions))

            rows = self.DatabaseService.ExecuteQuery(query, params)
            return list(rows)

        except Exception as e:
            LoggingService.LogException("Exception getting active jobs by service", e, "DatabaseManager", "GetActiveJobsByService")
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
            
            rows = self.DatabaseService.ExecuteQuery(query)
            return list(rows)
            
        except Exception as e:
            LoggingService.LogException("Exception getting all active jobs", e, "DatabaseManager", "GetAllActiveJobs")
            return []
    
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
    
    def CancelActiveJob(self, JobId: int) -> bool:
        """Cancel a specific active job by ID."""
        try:
            LoggingService.LogFunctionEntry("CancelActiveJob", "DatabaseManager", JobId)
            
            # Update job status to cancelled
            update_query = """
                UPDATE ActiveJobs 
                SET Status = 'Cancelled', UpdatedAt = NOW()
                WHERE Id = %s
            """
            
            result = self.DatabaseService.ExecuteNonQuery(update_query, (JobId,))
            
            if result > 0:
                LoggingService.LogInfo(f"Active job {JobId} cancelled successfully", "DatabaseManager", "CancelActiveJob")
                return True
            else:
                LoggingService.LogWarning(f"Active job {JobId} not found or already cancelled", "DatabaseManager", "CancelActiveJob")
                return False
                
        except Exception as e:
            LoggingService.LogException("Exception cancelling active job", e, "DatabaseManager", "CancelActiveJob")
            return False
    
    # Quality Testing Workflow Methods
    
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
    
    # Duplicate GetActiveJobsByService removed -- use the canonical version above (supports WorkerName + RunningOnly filters)
    
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
    
    # Simple QualityTest Methods
    
    
    

    
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
    
    def SetActiveJobFFmpegPid(self, ActiveJobId: int, FFmpegPid: int) -> bool:
        """Record the FFmpeg subprocess PID for an active job.

        ActiveJobs.ProcessId is the worker's Python PID (per IsProcessAlive
        documentation in StuckJobDetectionService). ActiveJobs.FFmpegPid is
        the FFmpeg subprocess PID -- the correct kill target for stuck-job
        cleanup. See stuck-job-detection.feature.md criterion 6.

        Returns True if a row was updated, False otherwise.
        """
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
    







