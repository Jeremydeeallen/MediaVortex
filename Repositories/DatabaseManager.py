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
from Features.FileScanning.FileScanningRepository import FileScanningRepository
from Features.Activity.ActivityRepository import ActivityRepository
from Features.SystemSettings.SystemSettingsRepository import SystemSettingsRepository
from Features.ServiceControl.ServiceControlRepository import ServiceControlRepository
from Features.ServiceControl.ActiveJobRepository import ActiveJobRepository
from Features.Profiles.ProfileRepository import ProfileRepository
from Features.Workers.WorkersRepository import WorkersRepository
from Features.JellyfinIntegration.JellyfinRepository import JellyfinRepository
from Core.Database.MaintenanceRepository import MaintenanceRepository
from Core.Database.CodecFlagsRepository import CodecFlagsRepository
from Core.Database.PathNormalizer import PathNormalizer


# directive: db-monolith-decompose | # directive: path-schema-migration | # see path.S8
class DatabaseManager(
    MediaFilesRepository,
    TranscodeQueueRepository,
    TranscodeJobRepository,
    QualityTestRepository,
    FileScanningRepository,
    ActivityRepository,
    SystemSettingsRepository,
    ServiceControlRepository,
    ActiveJobRepository,
    ProfileRepository,
    WorkersRepository,
    JellyfinRepository,
    MaintenanceRepository,
    CodecFlagsRepository,
    PathNormalizer,
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
    
    



    
    
    
    
    
    
    
    
    
    
    # Quality Testing Workflow Methods
    
    
    
    
    # Duplicate GetActiveJobsByService removed -- use the canonical version above (supports WorkerName + RunningOnly filters)
    
    
    
    
    
    # Simple QualityTest Methods
    
    
    

    
    
    
    

    







