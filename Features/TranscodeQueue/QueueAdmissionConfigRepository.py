from typing import Optional
from Core.Database.BaseRepository import BaseRepository
from Core.Logging.LoggingService import LoggingService
from Features.TranscodeQueue.Models.QueueAdmissionConfigModel import QueueAdmissionConfigModel


class QueueAdmissionConfigRepository(BaseRepository):
    """Single-row scalar config table for the queue-admission gate.

    Always reads/writes Id=1 (enforced by table CHECK constraint). No caching --
    every gate evaluation reads fresh per the standing rule against cached DB
    settings (see memory/feedback_no_cached_db_settings.md).
    """

    def Get(self) -> QueueAdmissionConfigModel:
        """Return the single config row, falling back to the dataclass defaults
        if the row is missing (which would only happen if the migration didn't
        seed it; defensive for the should-never-happen case).
        """
        try:
            Rows = self.ExecuteQuery(
                """
                SELECT Id, MinTranscodeSavingsMB, MissingEstimatePolicy, LastUpdated
                FROM QueueAdmissionConfig WHERE Id = 1
                """
            )
            if not Rows:
                LoggingService.LogWarning(
                    "QueueAdmissionConfig row Id=1 missing -- returning dataclass defaults. "
                    "Run Scripts/SQLScripts/AddQueueAdmissionTables.py to seed.",
                    "QueueAdmissionConfigRepository", "Get",
                )
                return QueueAdmissionConfigModel()
            R = Rows[0]
            return QueueAdmissionConfigModel(
                Id=R['Id'],
                MinTranscodeSavingsMB=R['MinTranscodeSavingsMB'],
                MissingEstimatePolicy=R['MissingEstimatePolicy'],
                LastUpdated=R.get('LastUpdated'),
            )
        except Exception as Ex:
            LoggingService.LogException(
                "Get failed", Ex, "QueueAdmissionConfigRepository", "Get",
            )
            return QueueAdmissionConfigModel()

    def Update(self, MinTranscodeSavingsMB: Optional[int] = None,
               MissingEstimatePolicy: Optional[str] = None) -> bool:
        """Update one or more scalars on the Id=1 row. Stamps LastUpdated=NOW()."""
        try:
            Sets = []
            Values = []
            if MinTranscodeSavingsMB is not None:
                Sets.append("MinTranscodeSavingsMB = %s")
                Values.append(MinTranscodeSavingsMB)
            if MissingEstimatePolicy is not None:
                if MissingEstimatePolicy not in ('admit', 'block'):
                    LoggingService.LogError(
                        f"Update rejected: MissingEstimatePolicy={MissingEstimatePolicy!r} "
                        f"must be 'admit' or 'block'",
                        "QueueAdmissionConfigRepository", "Update",
                    )
                    return False
                Sets.append("MissingEstimatePolicy = %s")
                Values.append(MissingEstimatePolicy)
            if not Sets:
                return True  # nothing to change
            Sets.append("LastUpdated = NOW()")
            Query = f"UPDATE QueueAdmissionConfig SET {', '.join(Sets)} WHERE Id = 1"
            self.ExecuteNonQuery(Query, tuple(Values))
            return True
        except Exception as Ex:
            LoggingService.LogException(
                "Update failed", Ex, "QueueAdmissionConfigRepository", "Update",
            )
            return False
