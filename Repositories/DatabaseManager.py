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
    def GetAllProfiles(self) -> List[TranscodeProfileModel]:
        """Get all transcoding profiles."""
        query = """SELECT Id, ProfileName, Description, CreatedDate, LastModified, 
                          Codec, Preset, FilmGrain, YadifMode, YadifParity, YadifDeint, UseNvidiaHardware 
                   FROM Profiles ORDER BY ProfileName"""
        rows = self.DatabaseService.ExecuteQuery(query)
        
        profiles = []
        for row in rows:
            profile = TranscodeProfileModel(
                Id=row['Id'],
                ProfileName=row['ProfileName'],
                Description=row['Description'],
                CreatedDate=row['CreatedDate'],
                LastModified=row['LastModified'],
                Codec=row['Codec'] if row['Codec'] is not None else 'libsvtav1',
                Preset=row['Preset'] if row['Preset'] is not None else 6,
                FilmGrain=row['FilmGrain'] if row['FilmGrain'] is not None else 10,
                YadifMode=row['YadifMode'] if row['YadifMode'] is not None else 1,
                YadifParity=row['YadifParity'] if row['YadifParity'] is not None else 1,
                YadifDeint=row['YadifDeint'] if row['YadifDeint'] is not None else 1,
                UseNvidiaHardware=row['UseNvidiaHardware'] if row['UseNvidiaHardware'] is not None else 0
            )
            profiles.append(profile)
        
        return profiles
    
    def GetProfileById(self, ProfileId: int) -> Optional[TranscodeProfileModel]:
        """Get a specific profile by ID."""
        query = """SELECT Id, ProfileName, Description, CreatedDate, LastModified, 
                          Codec, Preset, FilmGrain, YadifMode, YadifParity, YadifDeint, UseNvidiaHardware 
                   FROM Profiles WHERE Id = %s"""
        rows = self.DatabaseService.ExecuteQuery(query, (ProfileId,))
        
        if not rows:
            return None
        
        row = rows[0]
        return TranscodeProfileModel(
            Id=row['Id'],
            ProfileName=row['ProfileName'],
            Description=row['Description'],
            CreatedDate=row['CreatedDate'],
            LastModified=row['LastModified'],
            Codec=row['Codec'] if row['Codec'] is not None else 'libsvtav1',
            Preset=row['Preset'] if row['Preset'] is not None else 6,
            FilmGrain=row['FilmGrain'] if row['FilmGrain'] is not None else 10,
            YadifMode=row['YadifMode'] if row['YadifMode'] is not None else 1,
            YadifParity=row['YadifParity'] if row['YadifParity'] is not None else 1,
            YadifDeint=row['YadifDeint'] if row['YadifDeint'] is not None else 1,
            UseNvidiaHardware=row['UseNvidiaHardware'] if row['UseNvidiaHardware'] is not None else 0
        )
    
    def SaveProfile(self, Profile: TranscodeProfileModel) -> int:
        """Save a profile (insert or update) and return the profile ID."""
        try:
            LoggingService.LogFunctionEntry("SaveProfile", "DatabaseManager", Profile.Id, Profile.ProfileName, Profile.Description)
            
            connection = self.DatabaseService.GetConnection()
            try:
                cursor = connection.cursor()
                
                if Profile.Id is None:
                    # Insert new profile
                    LoggingService.LogInfo("Inserting new profile...", "DatabaseManager", "SaveProfile")
                    query = """
                        INSERT INTO Profiles (ProfileName, Description, CreatedDate, LastModified, 
                                             Codec, Preset, FilmGrain, YadifMode, YadifParity, YadifDeint, UseNvidiaHardware)
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                        RETURNING Id
                    """
                    parameters = (Profile.ProfileName, Profile.Description, Profile.CreatedDate, Profile.LastModified,
                                 Profile.Codec, Profile.Preset, Profile.FilmGrain, Profile.YadifMode,
                                 Profile.YadifParity, Profile.YadifDeint, Profile.UseNvidiaHardware)
                    LoggingService.LogInfo("Insert parameters: {}", "DatabaseManager", "SaveProfile", parameters)
                    cursor.execute(query, parameters)
                    profile_id = cursor.fetchone()[0]
                    connection.commit()
                    LoggingService.LogInfo("Profile inserted with ID: {}", "DatabaseManager", "SaveProfile", profile_id)
                    return profile_id
                else:
                    # Update existing profile
                    LoggingService.LogInfo("Updating existing profile with ID: {}", "DatabaseManager", "SaveProfile", Profile.Id)
                    query = """
                        UPDATE Profiles 
                        SET ProfileName = %s, Description = %s, LastModified = %s, 
                            Codec = %s, Preset = %s, FilmGrain = %s, YadifMode = %s, YadifParity = %s, YadifDeint = %s, UseNvidiaHardware = %s
                        WHERE Id = %s
                    """
                    parameters = (Profile.ProfileName, Profile.Description, Profile.LastModified,
                                 Profile.Codec, Profile.Preset, Profile.FilmGrain, Profile.YadifMode, 
                                 Profile.YadifParity, Profile.YadifDeint, Profile.UseNvidiaHardware, Profile.Id)
                    LoggingService.LogInfo("Update parameters: {}", "DatabaseManager", "SaveProfile", parameters)
                    cursor.execute(query, parameters)
                    connection.commit()
                    affected_rows = cursor.rowcount
                    LoggingService.LogInfo("Profile update affected {} rows", "DatabaseManager", "SaveProfile", affected_rows)
                    return Profile.Id
            finally:
                self.DatabaseService.CloseConnection(connection)
        except Exception as e:
            LoggingService.LogException("Exception in SaveProfile", e, "DatabaseManager", "SaveProfile")
            raise
    
    def DeleteProfile(self, ProfileId: int) -> bool:
        """Delete a profile and its associated thresholds."""
        try:
            # Delete associated thresholds first
            self.DatabaseService.ExecuteNonQuery("DELETE FROM ProfileThresholds WHERE ProfileId = %s", (ProfileId,))

            # Delete the profile
            affected_rows = self.DatabaseService.ExecuteNonQuery("DELETE FROM Profiles WHERE Id = %s", (ProfileId,))
            return affected_rows > 0
        except Exception as e:
            LoggingService.LogException(
                f"Failed to delete Profile {ProfileId}", e, "DatabaseManager", "DeleteProfile"
            )
            return False
    
    # Profile Threshold Management Methods
    def GetThresholdsByProfileId(self, ProfileId: int) -> List[ProfileThresholdModel]:
        """Get all thresholds for a specific profile."""
        query = """
            SELECT Id, ProfileId, Resolution, Under30MinMB, Under65MinMB, Over65MinMB,
                   VideoBitrateKbps, AudioBitrateKbps, FallbackVideoBitrateKbps,
                   FallbackAudioBitrateKbps, TranscodeDownTo, Quality, KeepSource, ContainerType
            FROM ProfileThresholds 
            WHERE ProfileId = %s
            ORDER BY Resolution
        """
        rows = self.DatabaseService.ExecuteQuery(query, (ProfileId,))
        
        thresholds = []
        for row in rows:
            threshold = ProfileThresholdModel(
                Id=row['Id'],
                ProfileId=row['ProfileId'],
                Resolution=row['Resolution'],
                Under30MinMB=row['Under30MinMB'],
                Under65MinMB=row['Under65MinMB'],
                Over65MinMB=row['Over65MinMB'],
                VideoBitrateKbps=row['VideoBitrateKbps'],
                AudioBitrateKbps=row['AudioBitrateKbps'],
                FallbackVideoBitrateKbps=row['FallbackVideoBitrateKbps'],
                FallbackAudioBitrateKbps=row['FallbackAudioBitrateKbps'],
                TranscodeDownTo=row['TranscodeDownTo'],
                Quality=row['Quality'],
                KeepSource=bool(row['keepsource'] if 'keepsource' in row else 0),
                ContainerType=row['containertype'] if 'containertype' in row else 'mp4'
            )
            thresholds.append(threshold)

        return thresholds

    def GetAllProfileThresholds(self) -> List[ProfileThresholdModel]:
        """Get all thresholds from all profiles."""
        query = """
            SELECT Id, ProfileId, Resolution, Under30MinMB, Under65MinMB, Over65MinMB,
                   VideoBitrateKbps, AudioBitrateKbps, FallbackVideoBitrateKbps,
                   FallbackAudioBitrateKbps, TranscodeDownTo, Quality, KeepSource, ContainerType
            FROM ProfileThresholds 
            ORDER BY ProfileId, Resolution
        """
        rows = self.DatabaseService.ExecuteQuery(query)
        
        thresholds = []
        for row in rows:
            threshold = ProfileThresholdModel(
                Id=row['Id'],
                ProfileId=row['ProfileId'],
                Resolution=row['Resolution'],
                Under30MinMB=row['Under30MinMB'],
                Under65MinMB=row['Under65MinMB'],
                Over65MinMB=row['Over65MinMB'],
                VideoBitrateKbps=row['VideoBitrateKbps'],
                AudioBitrateKbps=row['AudioBitrateKbps'],
                FallbackVideoBitrateKbps=row['FallbackVideoBitrateKbps'],
                FallbackAudioBitrateKbps=row['FallbackAudioBitrateKbps'],
                TranscodeDownTo=row['TranscodeDownTo'],
                Quality=row['Quality'],
                KeepSource=bool(row['keepsource'] if 'keepsource' in row else 0),
                ContainerType=row['containertype'] if 'containertype' in row else 'mp4'
            )
            thresholds.append(threshold)

        return thresholds
    
    def SaveThreshold(self, Threshold: ProfileThresholdModel) -> int:
        """Save a threshold (insert or update) and return the threshold ID."""
        try:
            LoggingService.LogFunctionEntry("SaveThreshold", "DatabaseManager", Threshold.Id, Threshold.ProfileId, Threshold.Resolution)
            
            connection = self.DatabaseService.GetConnection()
            try:
                cursor = connection.cursor()
                
                if Threshold.Id is None:
                    # Insert new threshold
                    LoggingService.LogInfo("Inserting new threshold...")
                    query = """
                        INSERT INTO ProfileThresholds 
                        (ProfileId, Resolution, Under30MinMB, Under65MinMB, Over65MinMB,
                         VideoBitrateKbps, AudioBitrateKbps, FallbackVideoBitrateKbps,
                         FallbackAudioBitrateKbps, TranscodeDownTo, Quality, KeepSource, ContainerType)
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                        RETURNING Id
                    """
                    parameters = (
                        Threshold.ProfileId, Threshold.Resolution, Threshold.Under30MinMB,
                        Threshold.Under65MinMB, Threshold.Over65MinMB, Threshold.VideoBitrateKbps,
                        Threshold.AudioBitrateKbps, Threshold.FallbackVideoBitrateKbps,
                        Threshold.FallbackAudioBitrateKbps,
                        Threshold.TranscodeDownTo if Threshold.TranscodeDownTo is not None else '',
                        Threshold.Quality, Threshold.KeepSource, 'mp4'
                    )
                    LoggingService.LogInfo(f"Insert threshold parameters: {parameters}", "SaveThreshold", "DatabaseManager")
                    cursor.execute(query, parameters)
                    threshold_id = cursor.fetchone()[0]
                    connection.commit()
                    LoggingService.LogInfo(f"Threshold inserted with ID: {threshold_id}", "SaveThreshold", "DatabaseManager")
                    return threshold_id
                else:
                    # Update existing threshold
                    LoggingService.LogInfo(f"Updating existing threshold with ID: {Threshold.Id}", "SaveThreshold", "DatabaseManager")
                    query = """
                        UPDATE ProfileThresholds 
                        SET ProfileId = %s, Resolution = %s, Under30MinMB = %s, Under65MinMB = %s,
                            Over65MinMB = %s, VideoBitrateKbps = %s, AudioBitrateKbps = %s,
                            FallbackVideoBitrateKbps = %s, FallbackAudioBitrateKbps = %s,
                            TranscodeDownTo = %s, Quality = %s, KeepSource = %s
                        WHERE Id = %s
                    """
                    parameters = (
                        Threshold.ProfileId, Threshold.Resolution, Threshold.Under30MinMB,
                        Threshold.Under65MinMB, Threshold.Over65MinMB, Threshold.VideoBitrateKbps,
                        Threshold.AudioBitrateKbps, Threshold.FallbackVideoBitrateKbps,
                        Threshold.FallbackAudioBitrateKbps, 
                        Threshold.TranscodeDownTo if Threshold.TranscodeDownTo is not None else '', 
                        Threshold.Quality, Threshold.KeepSource, Threshold.Id
                    )
                    LoggingService.LogInfo(f"Update threshold parameters: {parameters}", "SaveThreshold", "DatabaseManager")
                    cursor.execute(query, parameters)
                    connection.commit()
                    affected_rows = cursor.rowcount
                    LoggingService.LogInfo(f"Threshold update affected {affected_rows} rows", "SaveThreshold", "DatabaseManager")
                    return Threshold.Id
            finally:
                self.DatabaseService.CloseConnection(connection)
        except Exception as e:
            LoggingService.LogException("Exception in SaveThreshold", e, "DatabaseManager", "SaveThreshold")
            raise
    
    def DeleteThreshold(self, ThresholdId: int) -> bool:
        """Delete a threshold."""
        affected_rows = self.DatabaseService.ExecuteNonQuery("DELETE FROM ProfileThresholds WHERE Id = %s", (ThresholdId,))
        return affected_rows > 0
    
    # Root Folder Management Methods
    def GetSystemSetting(self, SettingKey: str) -> Optional[str]:
        """Get a system setting value by key."""
        query = "SELECT SettingValue FROM SystemSettings WHERE SettingKey = %s"
        rows = self.DatabaseService.ExecuteQuery(query, (SettingKey,))
        
        if not rows:
            return None
        
        return rows[0]['SettingValue']
    
    def GetAllSystemSettings(self) -> List[Dict[str, Any]]:
        """Get all system settings."""
        query = "SELECT Id, SettingKey, SettingValue, Description, DataType, LastModified FROM SystemSettings ORDER BY SettingKey"
        rows = self.DatabaseService.ExecuteQuery(query)
        
        settings = []
        for row in rows:
            settings.append({
                'Id': row['Id'],
                'SettingKey': row['SettingKey'],
                'SettingValue': row['SettingValue'],
                'Description': row['Description'],
                'DataType': row['DataType'],
                'LastModified': row['LastModified']
            })
        
        return settings
    
    def GetScanDirectories(self) -> List[Dict[str, str]]:
        """Get all scan directory settings (ScanDir1, ScanDir2, etc.)."""
        query = "SELECT SettingKey, SettingValue, Description FROM SystemSettings WHERE SettingKey LIKE 'ScanDir%%' ORDER BY SettingKey"
        rows = self.DatabaseService.ExecuteQuery(query)
        
        scanDirs = []
        for row in rows:
            if row['SettingValue'] and row['SettingValue'].strip():  # Only include non-empty directories
                scanDirs.append({
                    'Key': row['SettingKey'],
                    'Path': row['SettingValue'],
                    'Description': row['Description']
                })
        
        return scanDirs
    
    def AddOrUpdateSystemSetting(self, SettingKey: str, SettingValue: str, Description: str, DataType: str = 'string') -> bool:
        """Add or update a system setting."""
        try:
            # Check if setting already exists
            existingValue = self.GetSystemSetting(SettingKey)
            
            if existingValue is not None:
                # Update existing setting
                query = """
                    UPDATE SystemSettings 
                    SET SettingValue = %s, Description = %s, DataType = %s, LastModified = NOW()
                    WHERE SettingKey = %s
                """
                self.DatabaseService.ExecuteNonQuery(query, (SettingValue, Description, DataType, SettingKey))
            else:
                # Insert new setting
                query = """
                    INSERT INTO SystemSettings (SettingKey, SettingValue, Description, DataType, LastModified)
                    VALUES (%s, %s, %s, %s, NOW())
                """
                self.DatabaseService.ExecuteNonQuery(query, (SettingKey, SettingValue, Description, DataType))
            
            return True
            
        except Exception as e:
            LoggingService.LogException(f"Error adding/updating system setting {SettingKey}", e, "AddOrUpdateSystemSetting", "DatabaseManager")
            return False
    
    def DeleteSystemSetting(self, SettingKey: str) -> bool:
        """Delete a system setting."""
        try:
            query = "DELETE FROM SystemSettings WHERE SettingKey = %s"
            affectedRows = self.DatabaseService.ExecuteNonQuery(query, (SettingKey,))
            return affectedRows > 0
            
        except Exception as e:
            LoggingService.LogException(f"Error deleting system setting {SettingKey}", e, "DeleteSystemSetting", "DatabaseManager")
            return False
    
    # TranscodeQueue Management Methods

    def RegisterWorker(self, WorkerName: str, Platform: str = 'windows', FFmpegPath: str = None,
                       FFprobePath: str = None,
                       ShareMountPrefix: str = None, MaxConcurrentJobs: int = 1,
                       MaxCpuThreads: int = None, Version: str = None,
                       BuildInfo: str = None) -> bool:
        """Register or update a worker in the Workers table (UPSERT).
        Version + BuildInfo are nullable; workers without resolved versions
        register cleanly with NULL values that the UI renders as "unknown"."""
        try:
            query = """
                INSERT INTO Workers (WorkerName, Platform, FFmpegPath, FFprobePath,
                                     ShareMountPrefix, MaxConcurrentJobs, MaxCpuThreads,
                                     Version, BuildInfo,
                                     Status, LastHeartbeat, RegisteredAt)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, 'Paused', NOW(), NOW())
                ON CONFLICT (WorkerName) DO UPDATE SET
                    Platform = EXCLUDED.Platform,
                    FFmpegPath = COALESCE(EXCLUDED.FFmpegPath, Workers.FFmpegPath),
                    FFprobePath = COALESCE(EXCLUDED.FFprobePath, Workers.FFprobePath),
                    ShareMountPrefix = COALESCE(EXCLUDED.ShareMountPrefix, Workers.ShareMountPrefix),
                    MaxConcurrentJobs = EXCLUDED.MaxConcurrentJobs,
                    MaxCpuThreads = COALESCE(EXCLUDED.MaxCpuThreads, Workers.MaxCpuThreads),
                    Version = EXCLUDED.Version,
                    BuildInfo = EXCLUDED.BuildInfo,
                    LastHeartbeat = NOW()
            """
            self.DatabaseService.ExecuteNonQuery(query, (
                WorkerName, Platform, FFmpegPath, FFprobePath,
                ShareMountPrefix, MaxConcurrentJobs, MaxCpuThreads,
                Version, BuildInfo,
            ))
            return True
        except Exception as e:
            LoggingService.LogException("Exception in RegisterWorker", e, "DatabaseManager", "RegisterWorker")
            return False

    def UpdateWorkerHeartbeat(self, WorkerName: str) -> bool:
        """Update the LastHeartbeat timestamp for a worker."""
        try:
            query = "UPDATE Workers SET LastHeartbeat = NOW() WHERE WorkerName = %s"
            self.DatabaseService.ExecuteNonQuery(query, (WorkerName,))
            return True
        except Exception as e:
            LoggingService.LogException("Exception in UpdateWorkerHeartbeat", e, "DatabaseManager", "UpdateWorkerHeartbeat")
            return False

    def GetWorkerConfig(self, WorkerName: str) -> Optional[Dict[str, Any]]:
        """Get worker configuration from the Workers table, including share mappings."""
        try:
            query = """
                SELECT WorkerName, Platform, FFmpegPath, FFprobePath,
                       ShareMountPrefix, ShareCanonicalPrefix, MaxConcurrentJobs, Status,
                       MaxCpuThreads, AcceptsInterlaced, QualityTestEnabled,
                       MaxConcurrentTranscodeJobs, MaxConcurrentQualityTestJobs,
                       MaxConcurrentRemuxJobs, RemuxEnabled
                FROM Workers WHERE WorkerName = %s
            """
            rows = self.DatabaseService.ExecuteQuery(query, (WorkerName,))
            if rows:
                Config = rows[0]
                Config['ShareMappings'] = self.GetWorkerShareMappings(WorkerName)
                return Config
            return None
        except Exception as e:
            LoggingService.LogException("Exception in GetWorkerConfig", e, "DatabaseManager", "GetWorkerConfig")
            return None

    def GetWorkerShareMappings(self, WorkerName: str) -> dict:
        """Get drive letter to mount path mappings for a worker.

        Returns dict of {DriveLetter: LocalMountPrefix}.
        e.g. {'T': '/mnt/media_tv/', 'M': '/mnt/movies/', 'Z': '/mnt/xxx/'}
        Falls back to empty dict if table doesn't exist yet (pre-migration).
        """
        try:
            query = """
                SELECT DriveLetter, LocalMountPrefix
                FROM WorkerShareMappings WHERE WorkerName = %s
                ORDER BY DriveLetter
            """
            rows = self.DatabaseService.ExecuteQuery(query, (WorkerName,))
            return {
                (row.get('driveletter') or row.get('DriveLetter')).strip():
                (row.get('localmountprefix') or row.get('LocalMountPrefix'))
                for row in rows
            }
        except Exception as e:
            LoggingService.LogException("Exception in GetWorkerShareMappings", e, "DatabaseManager", "GetWorkerShareMappings")
            return {}

    def RegisterWorkerShareMappings(self, WorkerName: str, Mappings: dict) -> bool:
        """Register drive letter to mount path mappings for a worker (UPSERT).

        Mappings: dict of {DriveLetter: LocalMountPrefix}
        e.g. {'T': '/mnt/media_tv/', 'M': '/mnt/movies/', 'Z': '/mnt/xxx/'}
        """
        try:
            query = """
                INSERT INTO WorkerShareMappings (WorkerName, DriveLetter, LocalMountPrefix)
                VALUES (%s, %s, %s)
                ON CONFLICT (WorkerName, DriveLetter) DO UPDATE SET
                    LocalMountPrefix = EXCLUDED.LocalMountPrefix
            """
            for DriveLetter, LocalMountPrefix in Mappings.items():
                self.DatabaseService.ExecuteNonQuery(query, (WorkerName, DriveLetter, LocalMountPrefix))
            return True
        except Exception as e:
            LoggingService.LogException("Exception in RegisterWorkerShareMappings", e, "DatabaseManager", "RegisterWorkerShareMappings")
            return False

    def RegisterStorageRootResolutions(self, WorkerName: str, Platform: str, Mappings: dict) -> bool:
        """UPSERT StorageRootResolutions rows derived from share mappings.

        For each drive letter in Mappings, looks up StorageRoots.CanonicalPrefix
        matching that letter (e.g. 'T:\\') and UPSERTs the resolution row.
        Mappings: dict of {DriveLetter: AbsolutePath}
        e.g. {'T': '/mnt/media_tv/', 'M': '/mnt/movies/', 'Z': '/mnt/xxx/'}
        """
        try:
            for DriveLetter, AbsolutePath in Mappings.items():
                CanonicalPrefix = f"{DriveLetter.upper()}:\\"
                Rows = self.DatabaseService.ExecuteQuery(
                    "SELECT Id FROM StorageRoots WHERE CanonicalPrefix = %s LIMIT 1",
                    (CanonicalPrefix,)
                )
                if not Rows:
                    LoggingService.LogInfo(
                        f"No StorageRoots row with CanonicalPrefix='{CanonicalPrefix}' -- skipping",
                        "DatabaseManager", "RegisterStorageRootResolutions"
                    )
                    continue
                StorageRootId = Rows[0]['id']
                self.DatabaseService.ExecuteNonQuery(
                    """INSERT INTO StorageRootResolutions (StorageRootId, WorkerName, Platform, AbsolutePath, IsActive)
                    VALUES (%s, %s, %s, %s, TRUE)
                    ON CONFLICT (StorageRootId, WorkerName) DO UPDATE SET
                        Platform = EXCLUDED.Platform,
                        AbsolutePath = EXCLUDED.AbsolutePath,
                        IsActive = TRUE""",
                    (StorageRootId, WorkerName, Platform, AbsolutePath)
                )
            return True
        except Exception as e:
            LoggingService.LogException("Exception in RegisterStorageRootResolutions", e, "DatabaseManager", "RegisterStorageRootResolutions")
            return False

    def UpdateWorkerStatus(self, WorkerName: str, Status: str) -> bool:
        """Update worker status (Online or Paused)."""
        try:
            query = "UPDATE Workers SET Status = %s, LastHeartbeat = NOW() WHERE WorkerName = %s"
            self.DatabaseService.ExecuteNonQuery(query, (Status, WorkerName))
            return True
        except Exception as e:
            LoggingService.LogException("Exception in UpdateWorkerStatus", e, "DatabaseManager", "UpdateWorkerStatus")
            return False

    def SetWorkerMountValidationError(self, WorkerName: str, Reason) -> bool:
        """Persist the last mount-validation failure reason (or clear it with None)."""
        try:
            self.DatabaseService.ExecuteNonQuery(
                "UPDATE Workers SET MountValidationError = %s WHERE WorkerName = %s",
                (Reason, WorkerName)
            )
            return True
        except Exception as e:
            LoggingService.LogException("Exception in SetWorkerMountValidationError", e, "DatabaseManager", "SetWorkerMountValidationError")
            return False
    
    def GetProfileQuality(self, ProfileName: str) -> Optional[int]:
        """Get the Quality value from ProfileThresholds for a given profile name."""
        try:
            LoggingService.LogFunctionEntry("GetProfileQuality", "DatabaseManager", ProfileName)
            
            query = """
                SELECT pt.Quality 
                FROM ProfileThresholds pt
                JOIN Profiles p ON pt.ProfileId = p.Id
                WHERE p.ProfileName = %s
                LIMIT 1
            """
            rows = self.DatabaseService.ExecuteQuery(query, (ProfileName,))
            
            if rows:
                quality = rows[0]['Quality']
                LoggingService.LogInfo(f"Found Quality {quality} for Profile {ProfileName}", "DatabaseManager", "GetProfileQuality")
                return quality
            else:
                LoggingService.LogWarning(f"No Quality found for Profile {ProfileName}", "DatabaseManager", "GetProfileQuality")
                return None
                
        except Exception as e:
            LoggingService.LogException("Exception getting profile quality", e, "DatabaseManager", "GetProfileQuality")
            return None
    
    def GetProfileQualityForTargetResolution(self, ProfileName: str, SourceResolution: str) -> Optional[int]:
        """Get the Quality value from ProfileThresholds for the target resolution based on TranscodeDownTo setting."""
        try:
            LoggingService.LogFunctionEntry("GetProfileQualityForTargetResolution", "DatabaseManager", ProfileName, SourceResolution)
            
            # Convert pixel dimensions to resolution category
            resolutionCategory = self._ConvertPixelDimensionsToResolutionCategory(SourceResolution)
            LoggingService.LogInfo(f"Converted {SourceResolution} to {resolutionCategory}", "DatabaseManager", "GetProfileQualityForTargetResolution")
            
            # First, get the TranscodeDownTo setting for the source resolution
            query = """
                SELECT pt.TranscodeDownTo 
                FROM ProfileThresholds pt
                JOIN Profiles p ON pt.ProfileId = p.Id
                WHERE p.ProfileName = %s AND pt.Resolution = %s
                LIMIT 1
            """
            rows = self.DatabaseService.ExecuteQuery(query, (ProfileName, resolutionCategory))
            
            if not rows:
                LoggingService.LogWarning(f"No TranscodeDownTo found for Profile {ProfileName} and Resolution {SourceResolution}", "DatabaseManager", "GetProfileQualityForTargetResolution")
                return None
            
            targetResolution = rows[0]['TranscodeDownTo']
            if not targetResolution:
                LoggingService.LogInfo(f"No TranscodeDownTo set for Profile {ProfileName} and Resolution {SourceResolution}", "DatabaseManager", "GetProfileQualityForTargetResolution")
                return None
            
            # Handle "No downscaling" case - use current resolution's settings
            if targetResolution == 'No downscaling':
                # Get the Quality from the current resolution entry
                query = """
                    SELECT pt.Quality 
                    FROM ProfileThresholds pt
                    JOIN Profiles p ON pt.ProfileId = p.Id
                    WHERE p.ProfileName = %s AND pt.Resolution = %s
                    LIMIT 1
                """
                rows = self.DatabaseService.ExecuteQuery(query, (ProfileName, resolutionCategory))
                
                if rows:
                    quality = rows[0]['Quality']
                    LoggingService.LogInfo(f"Found Quality {quality} for Profile {ProfileName} with no downscaling (from source {SourceResolution})", "DatabaseManager", "GetProfileQualityForTargetResolution")
                    return quality
                else:
                    LoggingService.LogWarning(f"No Quality found for Profile {ProfileName} and Resolution {resolutionCategory} (no downscaling)", "DatabaseManager", "GetProfileQualityForTargetResolution")
                    return None
            else:
                # Now get the Quality for the target resolution
                query = """
                    SELECT pt.Quality 
                    FROM ProfileThresholds pt
                    JOIN Profiles p ON pt.ProfileId = p.Id
                    WHERE p.ProfileName = %s AND pt.Resolution = %s
                    LIMIT 1
                """
                rows = self.DatabaseService.ExecuteQuery(query, (ProfileName, targetResolution))
                
                if rows:
                    quality = rows[0]['Quality']
                    LoggingService.LogInfo(f"Found Quality {quality} for Profile {ProfileName} targeting {targetResolution} (from source {SourceResolution})", "DatabaseManager", "GetProfileQualityForTargetResolution")
                    return quality
                else:
                    LoggingService.LogWarning(f"No Quality found for Profile {ProfileName} and target Resolution {targetResolution}", "DatabaseManager", "GetProfileQualityForTargetResolution")
                    return None
                
        except Exception as e:
            LoggingService.LogException("Exception getting profile quality for target resolution", e, "DatabaseManager", "GetProfileQualityForTargetResolution")
            return None

    def GetProfileSettingsForTargetResolution(self, ProfileName: str, SourceResolution: str) -> Optional[Dict[str, Any]]:
        """Get all quality settings from ProfileThresholds for the target resolution based on TranscodeDownTo setting."""
        try:
            LoggingService.LogFunctionEntry("GetProfileSettingsForTargetResolution", "DatabaseManager", ProfileName, SourceResolution)
            
            # First try to find exact resolution match (for VR resolutions like 7680x3840)
            query = """
                SELECT pt.TranscodeDownTo 
                FROM ProfileThresholds pt
                JOIN Profiles p ON pt.ProfileId = p.Id
                WHERE p.ProfileName = %s AND pt.Resolution = %s
                LIMIT 1
            """
            rows = self.DatabaseService.ExecuteQuery(query, (ProfileName, SourceResolution))
            foundResolution = SourceResolution
            
            # If no exact match found, try standardized resolution
            if not rows:
                resolutionCategory = self._ConvertPixelDimensionsToResolutionCategory(SourceResolution)
                LoggingService.LogInfo(f"Resolution {SourceResolution} not found in database, using standardized resolution {resolutionCategory}", "DatabaseManager", "GetProfileSettingsForTargetResolution")
                rows = self.DatabaseService.ExecuteQuery(query, (ProfileName, resolutionCategory))
                foundResolution = resolutionCategory
            else:
                LoggingService.LogInfo(f"Found exact resolution match for {SourceResolution}", "DatabaseManager", "GetProfileSettingsForTargetResolution")
            
            if not rows:
                LoggingService.LogWarning(f"No profile settings found for Profile '{ProfileName}' and Resolution '{foundResolution}' (original: {SourceResolution})", "DatabaseManager", "GetProfileSettingsForTargetResolution")
                return None
            
            targetResolution = rows[0]['TranscodeDownTo']
            if not targetResolution:
                LoggingService.LogInfo(f"No TranscodeDownTo set for Profile {ProfileName} and Resolution {SourceResolution}, treating as 'No downscaling'", "DatabaseManager", "GetProfileSettingsForTargetResolution")
                targetResolution = 'No downscaling'
            
            # Handle "No downscaling" case (including empty TranscodeDownTo) - use current resolution's settings
            if targetResolution == 'No downscaling':
                # Get all settings from the current resolution entry (use the resolution that was found)
                query = """
                    SELECT pt.VideoBitrateKbps, pt.AudioBitrateKbps, pt.Quality, pt.Resolution,
                           p.Codec, p.Preset, p.FilmGrain, p.YadifMode, p.YadifParity, p.YadifDeint, p.UseNvidiaHardware, pt.ContainerType, p.Id as ProfileId,
                           p.RateControlMode, pt.SourceBitratePercent, pt.MinBitrateKbps, pt.MaxBitrateKbps, pt.Gop
                    FROM ProfileThresholds pt
                    JOIN Profiles p ON pt.ProfileId = p.Id
                    WHERE p.ProfileName = %s AND pt.Resolution = %s
                    LIMIT 1
                """
                rows = self.DatabaseService.ExecuteQuery(query, (ProfileName, foundResolution))
            else:
                # Now get all settings for the target resolution
                query = """
                    SELECT pt.VideoBitrateKbps, pt.AudioBitrateKbps, pt.Quality, pt.Resolution,
                           p.Codec, p.Preset, p.FilmGrain, p.YadifMode, p.YadifParity, p.YadifDeint, p.UseNvidiaHardware, pt.ContainerType, p.Id as ProfileId,
                           p.RateControlMode, pt.SourceBitratePercent, pt.MinBitrateKbps, pt.MaxBitrateKbps, pt.Gop
                    FROM ProfileThresholds pt
                    JOIN Profiles p ON pt.ProfileId = p.Id
                    WHERE p.ProfileName = %s AND pt.Resolution = %s
                    LIMIT 1
                """
                rows = self.DatabaseService.ExecuteQuery(query, (ProfileName, targetResolution))
            
            if rows:
                row = rows[0]
                # Calculate the actual target resolution for transcoding
                actualTargetResolution = SourceResolution if targetResolution == 'No downscaling' else targetResolution
                settings = {
                    'VideoBitrateKbps': row['VideoBitrateKbps'],
                    'AudioBitrateKbps': row['AudioBitrateKbps'],
                    'Quality': row['Quality'],
                    'TargetResolution': actualTargetResolution,  # Use the actual target resolution from TranscodeDownTo
                    'Codec': row['Codec'],
                    'Preset': row['Preset'],
                    'FilmGrain': row['FilmGrain'],
                    'YadifMode': row['YadifMode'],
                    'YadifParity': row['YadifParity'],
                    'YadifDeint': row['YadifDeint'],
                    'UseNvidiaHardware': row['UseNvidiaHardware'],
                    'ContainerType': row['ContainerType'],
                    'ProfileId': row['ProfileId'],
                    'RateControlMode': row.get('RateControlMode'),
                    'SourceBitratePercent': row.get('SourceBitratePercent'),
                    'MinBitrateKbps': row.get('MinBitrateKbps'),
                    'MaxBitrateKbps': row.get('MaxBitrateKbps'),
                    'Gop': row.get('Gop'),
                }
                LoggingService.LogInfo(f"Found ProfileSettings for {ProfileName} targeting {actualTargetResolution}: {settings}", "DatabaseManager", "GetProfileSettingsForTargetResolution")
                return settings
            else:
                LoggingService.LogWarning(f"No ProfileSettings found for Profile {ProfileName} and target Resolution {targetResolution}", "DatabaseManager", "GetProfileSettingsForTargetResolution")
                return None
                
        except Exception as e:
            LoggingService.LogException("Exception getting profile settings for target resolution", e, "DatabaseManager", "GetProfileSettingsForTargetResolution")
            return None
    
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
    
    def SaveServiceStatus(self, ServiceStatus: Dict[str, Any]) -> bool:
        """Save service status to database."""
        try:
            LoggingService.LogFunctionEntry("SaveServiceStatus", "DatabaseManager")
            
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
            
            self.DatabaseService.ExecuteNonQuery(query, parameters)
            LoggingService.LogDebug(f"Service status saved for {ServiceStatus.get('ServiceName')}", "DatabaseManager", "SaveServiceStatus")
            return True
            
        except Exception as e:
            LoggingService.LogException("Exception saving service status", e, "DatabaseManager", "SaveServiceStatus")
            return False
    
    def UpdateServiceStatus(self, ServiceName: str, StatusData: Dict[str, Any]) -> bool:
        """Update service status in database."""
        try:
            LoggingService.LogFunctionEntry("UpdateServiceStatus", "DatabaseManager", ServiceName)
            
            # Build dynamic update query
            UpdateFields = []
            Parameters = []
            
            for key, value in StatusData.items():
                UpdateFields.append(f"{key} = %s")
                Parameters.append(value)
            
            if not UpdateFields:
                LoggingService.LogWarning("No fields to update", "DatabaseManager", "UpdateServiceStatus")
                return False
            
            Parameters.append(ServiceName)
            query = f"UPDATE ServiceStatus SET {', '.join(UpdateFields)}, UpdatedAt = NOW() WHERE ServiceName = %s"
            
            self.DatabaseService.ExecuteNonQuery(query, Parameters)
            LoggingService.LogDebug(f"Service status updated for {ServiceName}", "DatabaseManager", "UpdateServiceStatus")
            return True
            
        except Exception as e:
            LoggingService.LogException("Exception updating service status", e, "DatabaseManager", "UpdateServiceStatus")
            return False
    
    def GetServiceStatus(self, ServiceName: str) -> Optional[Dict[str, Any]]:
        """Get current service status."""
        try:
            LoggingService.LogFunctionEntry("GetServiceStatus", "DatabaseManager", ServiceName)
            
            query = "SELECT * FROM ServiceStatus WHERE ServiceName = %s"
            rows = self.DatabaseService.ExecuteQuery(query, (ServiceName,))
            
            if rows:
                LoggingService.LogDebug(f"Retrieved service status for {ServiceName}", "DatabaseManager", "GetServiceStatus")
                # Return the CaseInsensitiveDict directly to preserve case-insensitive key access
                return rows[0]
            else:
                LoggingService.LogDebug(f"No service status found for {ServiceName}", "DatabaseManager", "GetServiceStatus")
                return None
                
        except Exception as e:
            LoggingService.LogException("Exception getting service status", e, "DatabaseManager", "GetServiceStatus")
            return None
    
    
    
    
    
    
    
    
    
    def CreateServiceCommand(self, CommandData: Dict[str, Any]) -> int:
        """Create a new service command."""
        try:
            LoggingService.LogFunctionEntry("CreateServiceCommand", "DatabaseManager")
            
            query = """
                INSERT INTO ServiceCommands (
                CommandType, SourceService, TargetService, Parameters, Status,
                Priority, CreatedBy, CreatedAt, UpdatedAt
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, NOW(), NOW())
                RETURNING Id
            """
            
            import json
            parameters = (
                CommandData.get('CommandType'),
                CommandData.get('SourceService', 'ServiceControlController'),
                CommandData.get('TargetService'),
                json.dumps(CommandData.get('Parameters', {})),
                CommandData.get('Status', 'Pending'),
                CommandData.get('Priority', 1),
                CommandData.get('CreatedBy', 'Unknown')
            )
            
            result = self.DatabaseService.ExecuteNonQuery(query, parameters)
            
            if result:
                # Get the ID of the created command
                command_id = self.DatabaseService.GetLastInsertId()
                LoggingService.LogInfo(f"Created ServiceCommand {command_id}", "DatabaseManager", "CreateServiceCommand")
                return command_id
            else:
                LoggingService.LogError("Failed to create ServiceCommand", "DatabaseManager", "CreateServiceCommand")
                return 0
                
        except Exception as e:
            LoggingService.LogException("Error creating ServiceCommand", e, "DatabaseManager", "CreateServiceCommand")
            return 0
    
    def UpdateServiceCommandStatus(self, CommandId: int, Status: str, Result: str = None) -> bool:
        """Update service command status."""
        try:
            LoggingService.LogFunctionEntry("UpdateServiceCommandStatus", "DatabaseManager")
            
            query = """
            UPDATE ServiceCommands 
            SET Status = %s, Result = %s, UpdatedAt = NOW()
            WHERE Id = %s
            """
            
            result = self.DatabaseService.ExecuteNonQuery(query, (Status, Result, CommandId))
            
            if result:
                LoggingService.LogInfo(f"Updated ServiceCommand {CommandId} status to {Status}", "DatabaseManager", "UpdateServiceCommandStatus")
                return True
            else:
                LoggingService.LogError(f"Failed to update ServiceCommand {CommandId}", "DatabaseManager", "UpdateServiceCommandStatus")
                return False
                
        except Exception as e:
            LoggingService.LogException("Error updating ServiceCommand status", e, "DatabaseManager", "UpdateServiceCommandStatus")
            return False
    
    def GetPendingCommandsForService(self, ServiceName: str) -> List[Dict[str, Any]]:
        """Get pending commands for specific service."""
        try:
            LoggingService.LogFunctionEntry("GetPendingCommandsForService", "DatabaseManager", ServiceName)
            
            query = """
            SELECT * FROM ServiceCommands 
            WHERE TargetService = %s AND Status = 'Pending'
            ORDER BY Priority DESC, CreatedAt ASC
            """
            rows = self.DatabaseService.ExecuteQuery(query, (ServiceName,))
            
            LoggingService.LogDebug(f"Retrieved {len(rows)} pending commands for {ServiceName}", "DatabaseManager", "GetPendingCommandsForService")
            return rows
            
        except Exception as e:
            LoggingService.LogException("Exception getting pending commands for service", e, "DatabaseManager", "GetPendingCommandsForService")
            return []
    
    

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
    
    def GetMaxConcurrentJobs(self) -> int:
        """Get the maximum concurrent jobs limit from ServiceStatus."""
        try:
            query = "SELECT MaxConcurrentJobs FROM ServiceStatus WHERE ServiceName = 'QualityTestingService'"
            result = self.DatabaseService.ExecuteQuery(query)
            
            if result and len(result) > 0:
                return result[0]['maxconcurrentjobs'] or 1  # Default to 1 if not set
            
            return 1  # Default value
            
        except Exception as e:
            LoggingService.LogException("Exception getting max concurrent jobs", e, "DatabaseManager", "GetMaxConcurrentJobs")
            return 1
    
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
    
    def PrivateValidateTranscodeAttemptId(self, TranscodeAttemptId: int) -> bool:
        """Private method to validate TranscodeAttemptId exists."""
        try:
            query = "SELECT COUNT(*) as Count FROM TranscodeAttempts WHERE Id = %s"
            results = self.DatabaseService.ExecuteQuery(query, (TranscodeAttemptId,))
            return results[0]['Count'] > 0 if results else False
        except Exception as e:
            LoggingService.LogException("Exception validating TranscodeAttemptId", e, "DatabaseManager", "PrivateValidateTranscodeAttemptId")
            return False
    
    def PrivateLogTemporaryFilePathOperation(self, Operation: str, TranscodeAttemptId: int, RecordId: Optional[int], Status: str, ErrorMessage: str = None):
        """Private method to log temporary file path operations."""
        try:
            Message = f"TemporaryFilePath {Operation} - TranscodeAttemptId: {TranscodeAttemptId}"
            if RecordId:
                Message += f", RecordId: {RecordId}"
            Message += f", Status: {Status}"
            if ErrorMessage:
                Message += f", Error: {ErrorMessage}"
            
            LogLevel = "ERROR" if Status in ["FAILED", "EXCEPTION"] else "INFO"
            LoggingService.Log(LogLevel, Message, "DatabaseManager", "PrivateLogTemporaryFilePathOperation")
        except Exception as e:
            LoggingService.LogException("Exception logging temporary file path operation", e, "DatabaseManager", "PrivateLogTemporaryFilePathOperation")
    
    def GetSystemSetting(self, SettingKey: str) -> Optional[str]:
        """Get a system setting value by key."""
        try:
            LoggingService.LogFunctionEntry("GetSystemSetting", "DatabaseManager", SettingKey)
            
            query = "SELECT SettingValue FROM SystemSettings WHERE SettingKey = %s"
            results = self.DatabaseService.ExecuteQuery(query, (SettingKey,))
            
            if results:
                SettingValue = results[0]['SettingValue']
                LoggingService.LogInfo(f"Retrieved system setting '{SettingKey}': '{SettingValue}'", 
                                     "DatabaseManager", "GetSystemSetting")
                return SettingValue
            else:
                LoggingService.LogDebug(f"System setting not found: {SettingKey}",
                                      "DatabaseManager", "GetSystemSetting")
                return None
                
        except Exception as e:
            LoggingService.LogException("Exception getting system setting", e, "DatabaseManager", "GetSystemSetting")
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
    
    def InsertJellyfinOperation(self, LogFileName: str, OperationType: str, FilePath: str,
                                 FileName: str, VideoCodec: str, AudioCodec: str,
                                 Container: str, Resolution: str, SubtitleCodecs: str,
                                 Reason: str, TranscodeActions: str, LogDate: str) -> bool:
        """Insert a Jellyfin FFmpeg operation log entry. Skips if LogFileName already exists."""
        try:
            query = """
                INSERT INTO JellyfinOperations
                (LogFileName, OperationType, FilePath, FileName, VideoCodec, AudioCodec, Container, Resolution,
                 SubtitleCodecs, Reason, TranscodeActions, LogDate,
                 DestResolution, DestProfile, DestLevel, DestPixelFormat, DestFormat)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (LogFileName) DO NOTHING
            """
            self.DatabaseService.ExecuteNonQuery(query, (
                LogFileName, OperationType, FilePath, FileName,
                VideoCodec, AudioCodec, Container, Resolution, SubtitleCodecs, Reason, TranscodeActions, LogDate,
                "", "", "", "", ""
            ))
            return True
        except Exception as e:
            LoggingService.LogException("Error inserting Jellyfin operation", e, "DatabaseManager", "InsertJellyfinOperation")
            return False

    def InsertJellyfinOperationsBatch(self, Entries: list) -> int:
        """Batch insert Jellyfin operations. Returns count of new rows inserted."""
        try:
            query = """
                INSERT INTO JellyfinOperations
                (LogFileName, OperationType, FilePath, FileName, VideoCodec, AudioCodec, Container, Resolution,
                 SubtitleCodecs, Reason, TranscodeActions, LogDate,
                 DestResolution, DestProfile, DestLevel, DestPixelFormat, DestFormat)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (LogFileName) DO NOTHING
            """
            connection = self.DatabaseService.GetConnection()
            try:
                cursor = connection.cursor()
                cursor.execute("SELECT COUNT(*) FROM JellyfinOperations")
                beforeCount = cursor.fetchone()[0]
                cursor.executemany(query, [
                    (e["LogFileName"], e["OperationType"], e["FilePath"], e["FileName"],
                     e["VideoCodec"], e["AudioCodec"], e["Container"], e["Resolution"],
                     e.get("SubtitleCodecs", ""), e["Reason"], e.get("TranscodeActions", ""), e["LogDate"],
                     e.get("DestResolution", ""), e.get("DestProfile", ""), e.get("DestLevel", ""),
                     e.get("DestPixelFormat", ""), e.get("DestFormat", ""))
                    for e in Entries
                ])
                connection.commit()
                cursor.execute("SELECT COUNT(*) FROM JellyfinOperations")
                afterCount = cursor.fetchone()[0]
                return afterCount - beforeCount
            finally:
                self.DatabaseService.CloseConnection(connection)
        except Exception as e:
            LoggingService.LogException("Error batch inserting Jellyfin operations", e, "DatabaseManager", "InsertJellyfinOperationsBatch")
            return 0

    def GetExistingLogFileNames(self) -> set:
        """Get set of all LogFileName values already in the database."""
        try:
            rows = self.DatabaseService.ExecuteQuery("SELECT LogFileName FROM JellyfinOperations")
            return {row['logfilename'] for row in rows}
        except Exception as e:
            LoggingService.LogException("Error getting existing log filenames", e, "DatabaseManager", "GetExistingLogFileNames")
            return set()

    def GetStaleJellyfinRecordCount(self) -> int:
        """Count transcode records missing destination format data (need re-import)."""
        try:
            rows = self.DatabaseService.ExecuteQuery("""
                SELECT COUNT(*) FROM JellyfinOperations
                WHERE OperationType = 'Transcode'
                  AND (DestResolution IS NULL OR DestResolution = '')
                  AND (DestProfile IS NULL OR DestProfile = '')
                  AND (DestLevel IS NULL OR DestLevel = '')
            """)
            return rows[0]['count'] if rows else 0
        except Exception as e:
            LoggingService.LogException("Error checking stale records", e, "DatabaseManager", "GetStaleJellyfinRecordCount")
            return 0

    def ClearJellyfinOperations(self):
        """Delete all JellyfinOperations records to force full re-import."""
        try:
            self.DatabaseService.ExecuteNonQuery("DELETE FROM JellyfinOperations")
        except Exception as e:
            LoggingService.LogException("Error clearing Jellyfin operations", e, "DatabaseManager", "ClearJellyfinOperations")

    def GetJellyfinOperationCounts(self) -> Dict[str, Any]:
        """Get distinct file count and total log count per operation type, with date range."""
        try:
            query = """
                SELECT OperationType,
                       COUNT(*) as TotalLogs,
                       COUNT(DISTINCT FileName) as DistinctFiles,
                       MIN(LogDate) as OldestDate,
                       MAX(LogDate) as NewestDate
                FROM JellyfinOperations
                GROUP BY OperationType
            """
            rows = self.DatabaseService.ExecuteQuery(query)
            result = {}
            allOldest = []
            allNewest = []
            for row in rows:
                result[row['operationtype']] = {"Distinct": row['distinctfiles'], "Total": row['totallogs']}
                if row['oldestdate']:
                    allOldest.append(row['oldestdate'])
                if row['newestdate']:
                    allNewest.append(row['newestdate'])
            return {
                "Success": True,
                "Counts": result,
                "OldestDate": min(allOldest) if allOldest else None,
                "NewestDate": max(allNewest) if allNewest else None,
                "TotalRecords": sum(r["Total"] for r in result.values())
            }
        except Exception as e:
            LoggingService.LogException("Error getting Jellyfin operation counts", e, "DatabaseManager", "GetJellyfinOperationCounts")
            return {"Success": False, "ErrorMessage": str(e)}

    def GetJellyfinOperationsByType(self, OperationType: str, Limit: int = 100) -> Dict[str, Any]:
        """Get operation details from local DB, grouped by file with play counts."""
        try:
            query = """
                SELECT FileName, FilePath, VideoCodec, AudioCodec, Container, Resolution, Reason,
                       COUNT(*) as PlayCount,
                       MIN(LogDate) as FirstSeen,
                       MAX(LogDate) as LastSeen,
                       SubtitleCodecs,
                       TranscodeActions
                FROM JellyfinOperations
                WHERE OperationType = %s
                GROUP BY FileName, FilePath, VideoCodec, AudioCodec, Container, Resolution, Reason,
                         SubtitleCodecs, TranscodeActions
                ORDER BY LastSeen DESC
                LIMIT %s
            """
            rows = self.DatabaseService.ExecuteQuery(query, (OperationType, Limit))
            files = []
            reasons = {}
            for row in rows:
                reason = row['reason'] or "other"
                files.append({
                    "FileName": row['filename'],
                    "FilePath": row['filepath'],
                    "VideoCodec": row['videocodec'],
                    "AudioCodec": row['audiocodec'],
                    "Container": row['container'],
                    "Resolution": row['resolution'],
                    "Reason": reason,
                    "Count": row['playcount'],
                    "FirstSeen": row['firstseen'],
                    "LastSeen": row['lastseen'],
                    "SubtitleCodecs": row['subtitlecodecs'] or "",
                    "TranscodeActions": row['transcodeactions'] or ""
                })
                if OperationType == "Transcode":
                    reasons[reason] = reasons.get(reason, 0) + row['playcount']

            totalQuery = "SELECT COUNT(*) FROM JellyfinOperations WHERE OperationType = %s"
            totalRow = self.DatabaseService.ExecuteQuery(totalQuery, (OperationType,))
            totalLogs = totalRow[0]['count'] if totalRow else 0

            dateQuery = "SELECT MIN(LogDate), MAX(LogDate) FROM JellyfinOperations WHERE OperationType = %s"
            dateRow = self.DatabaseService.ExecuteQuery(dateQuery, (OperationType,))

            return {
                "Success": True,
                "Files": files,
                "Count": len(files),
                "TotalLogs": totalLogs,
                "OperationType": OperationType,
                "Reasons": reasons,
                "OldestDate": dateRow[0]['min'] if dateRow else None,
                "NewestDate": dateRow[0]['max'] if dateRow else None
            }
        except Exception as e:
            LoggingService.LogException("Error getting Jellyfin operations by type", e, "DatabaseManager", "GetJellyfinOperationsByType")
            return {"Success": False, "ErrorMessage": str(e)}

