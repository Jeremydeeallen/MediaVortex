from typing import Any, Dict, List, Optional
from datetime import datetime, timezone
from Services.DatabaseService import DatabaseService
from Services.LoggingService import LoggingService
from Core.Database.DatabaseService import EscapeLikePattern


class WorkersRepository:
    def __init__(self, DatabaseServiceInstance: Optional[DatabaseService] = None):
        self.DatabaseService = DatabaseServiceInstance or DatabaseService()


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

    def UpdateWorkerHeartbeat(self, WorkerName: str) -> bool:
        """Update the LastHeartbeat timestamp for a worker."""
        try:
            query = "UPDATE Workers SET LastHeartbeat = NOW() WHERE WorkerName = %s"
            self.DatabaseService.ExecuteNonQuery(query, (WorkerName,))
            return True
        except Exception as e:
            LoggingService.LogException("Exception in UpdateWorkerHeartbeat", e, "DatabaseManager", "UpdateWorkerHeartbeat")
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
