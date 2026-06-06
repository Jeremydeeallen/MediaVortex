from typing import Any, Dict, List, Optional
from datetime import datetime, timezone
from Services.DatabaseService import DatabaseService
from Services.LoggingService import LoggingService
from Core.Database.DatabaseService import EscapeLikePattern


class MaintenanceRepository:
    def __init__(self, DatabaseServiceInstance: Optional[DatabaseService] = None):
        self.DatabaseService = DatabaseServiceInstance or DatabaseService()


    def CleanupOldLogs(self, DaysToKeep: int = 30) -> int:
        """Clean up old log entries to prevent database bloat."""
        try:
            query = """
                DELETE FROM Logs
                WHERE Timestamp < NOW() - INTERVAL '{} days'
            """.format(DaysToKeep)

            rowsAffected = self.DatabaseService.ExecuteNonQuery(query)

            LoggingService.LogInfo(f"Cleaned up {rowsAffected} old log records (older than {DaysToKeep} days)", "DatabaseManager", "CleanupOldLogs")
            return rowsAffected

        except Exception as e:
            LoggingService.LogException("Exception cleaning up old logs", e, "DatabaseManager", "CleanupOldLogs")
            return 0
