from typing import Dict, Any, Optional

from Core.Database.DatabaseService import DatabaseService


# directive: activity-admin-and-worker-telemetry
class AdminComplianceRepository:

    # directive: activity-admin-and-worker-telemetry
    def __init__(self, Db: Optional[DatabaseService] = None):
        self._Db = Db or DatabaseService()

    # directive: activity-admin-and-worker-telemetry
    def GetCard(self) -> Dict[str, Any]:
        Compliance = self._GetCompliance()
        Mode = self._GetMode()
        Audio = self._GetAudio()
        return {'Compliance': Compliance, 'Mode': Mode, 'Audio': Audio}

    # directive: activity-admin-and-worker-telemetry
    def _GetCompliance(self) -> Dict[str, int]:
        Rows = self._Db.ExecuteQuery(
            "SELECT "
            "COUNT(*) AS total, "
            "COUNT(*) FILTER (WHERE IsCompliant = TRUE) AS true_count, "
            "COUNT(*) FILTER (WHERE IsCompliant = FALSE) AS false_count, "
            "COUNT(*) FILTER (WHERE IsCompliant IS NULL) AS null_count "
            "FROM MediaFiles"
        )
        if not Rows:
            return {'Total': 0, 'True': 0, 'False': 0, 'Null': 0}
        R = Rows[0]
        return {'Total': int(R['total']), 'True': int(R['true_count']), 'False': int(R['false_count']), 'Null': int(R['null_count'])}

    # directive: activity-admin-and-worker-telemetry
    def _GetMode(self) -> Dict[str, int]:
        Rows = self._Db.ExecuteQuery(
            "SELECT WorkBucket, COUNT(*) AS cnt FROM MediaFiles GROUP BY WorkBucket"
        )
        Result = {'Transcode': 0, 'Remux': 0, 'AudioFix': 0, 'None': 0}
        for R in (Rows or []):
            Bucket = R.get('workbucket')
            Cnt = int(R['cnt'])
            if Bucket is None:
                Result['None'] = Cnt
            elif Bucket in Result:
                Result[Bucket] = Cnt
        return Result

    # directive: activity-admin-and-worker-telemetry
    def _GetAudio(self) -> Dict[str, int]:
        Rows = self._Db.ExecuteQuery(
            "SELECT "
            "COUNT(*) FILTER (WHERE AudioComplete = TRUE) AS complete_true, "
            "COUNT(*) FILTER (WHERE AudioComplete = FALSE) AS complete_false, "
            "COUNT(*) FILTER (WHERE AudioComplete IS NULL) AS complete_null, "
            "COUNT(*) FILTER (WHERE AudioCorruptSuspect = TRUE) AS suspect "
            "FROM MediaFiles"
        )
        if not Rows:
            return {'CompleteTrue': 0, 'CompleteFalse': 0, 'CompleteNull': 0, 'Suspect': 0}
        R = Rows[0]
        return {
            'CompleteTrue': int(R['complete_true']),
            'CompleteFalse': int(R['complete_false']),
            'CompleteNull': int(R['complete_null']),
            'Suspect': int(R['suspect']),
        }
