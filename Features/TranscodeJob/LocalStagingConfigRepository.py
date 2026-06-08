from typing import Any, Dict, Optional

from Core.Database.DatabaseService import DatabaseService
from Services.LoggingService import LoggingService


# directive: local-staging | # see local-staging.C17
class LocalStagingConfigRepository:
    """Single-row scalar config for the worker-local staging gate; fresh read per call (no cache)."""

    def __init__(self, DatabaseServiceInstance: Optional[DatabaseService] = None):
        self.DatabaseService = DatabaseServiceInstance or DatabaseService()

    # directive: local-staging | # see local-staging.C5
    def Get(self) -> Dict[str, Any]:
        """Return the single config row as a dict; defaults if the row is missing (defensive)."""
        try:
            Rows = self.DatabaseService.ExecuteQuery("SELECT Id, MinSizeMB, LastUpdated FROM LocalStagingConfig WHERE Id = 1")
            if not Rows:
                LoggingService.LogWarning("LocalStagingConfig row Id=1 missing -- returning defaults (MinSizeMB=500). Run Scripts/SQLScripts/AddLocalStagingColumns.py to seed.", "LocalStagingConfigRepository", "Get")
                return {"Id": 1, "MinSizeMB": 500, "LastUpdated": None}
            R = Rows[0]
            return {"Id": R.get('id') or R.get('Id') or 1, "MinSizeMB": int(R.get('minsizemb') or R.get('MinSizeMB') or 500), "LastUpdated": R.get('lastupdated') or R.get('LastUpdated')}
        except Exception as Ex:
            LoggingService.LogException("Get failed", Ex, "LocalStagingConfigRepository", "Get")
            return {"Id": 1, "MinSizeMB": 500, "LastUpdated": None}

    # directive: local-staging | # see local-staging.C16
    def Update(self, MinSizeMB: Optional[int] = None) -> bool:
        """Update non-None fields on Id=1 row; validates MinSizeMB > 0; stamps LastUpdated=NOW()."""
        try:
            Sets = []
            Values = []
            if MinSizeMB is not None:
                if not isinstance(MinSizeMB, int) or MinSizeMB <= 0:
                    LoggingService.LogError(f"Update rejected: MinSizeMB={MinSizeMB!r} must be a positive integer", "LocalStagingConfigRepository", "Update")
                    return False
                Sets.append("MinSizeMB = %s")
                Values.append(MinSizeMB)
            if not Sets:
                return True
            Sets.append("LastUpdated = NOW()")
            Query = f"UPDATE LocalStagingConfig SET {', '.join(Sets)} WHERE Id = 1"
            self.DatabaseService.ExecuteNonQuery(Query, tuple(Values))
            return True
        except Exception as Ex:
            LoggingService.LogException("Update failed", Ex, "LocalStagingConfigRepository", "Update")
            return False
