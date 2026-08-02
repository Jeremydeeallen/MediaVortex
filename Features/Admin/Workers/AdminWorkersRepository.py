from typing import List, Dict, Any, Optional

from Core.Database.DatabaseService import DatabaseService, CaseInsensitiveDict


# directive: worker-runtime-state | # see admin-workers.C6
class AdminWorkersRepository:

    # directive: worker-runtime-state | # see admin-workers.C6
    def __init__(self, Db: Optional[DatabaseService] = None):
        self._Db = Db or DatabaseService()

    # directive: worker-runtime-state | # see admin-workers.C6
    def GetTiles(self) -> List[Dict[str, Any]]:
        Rows = self._Db.ExecuteQuery(
            "SELECT WorkerName, Platform, Status, LastHeartbeat, MaxConcurrentJobs, "
            "MaxConcurrentQualityTestJobs, "
            "TranscodeEnabled, RemuxEnabled, QualityTestEnabled, ScanEnabled, ProbeEnabled, LanguageEnabled, NvencCapable, QsvCapable, HwAccelDecodeEnabled, "
            "Version, BuildInfo, MountValidationError, Enabled, "
            "RuntimeState, CurrentAttemptId, "
            "EXTRACT(EPOCH FROM (NOW() - LastHeartbeat))::int AS HeartbeatAgeSec "
            "FROM Workers WHERE Enabled = TRUE "
            "ORDER BY WorkerName ASC"
        )
        Threshold = self.GetStaleThresholdSec()
        HungThreshold = self.GetHungEncodeThresholdSec()
        ProgressAgeByAttempt = self._GetProgressAgeByAttempt([R.get('currentattemptid') for R in (Rows or []) if R.get('currentattemptid') is not None])
        from Features.StuckJobDetection.HungEncodeDetector import IsHung
        Tiles = []
        for R in (Rows or []):
            # directive: worker-runtime-state
            Tile = CaseInsensitiveDict(R)
            Tile['IntentDiverges'] = _DeriveDivergence(
                Tile.get('status'),
                Tile.get('runtimestate'),
                Tile.get('heartbeatagesec'),
                Threshold,
            )
            AttemptId = Tile.get('currentattemptid')
            ProgAge = ProgressAgeByAttempt.get(int(AttemptId)) if AttemptId is not None else None
            Tile['IsHung'] = IsHung(
                Tile.get('runtimestate'),
                Tile.get('heartbeatagesec'),
                ProgAge,
                HungThreshold,
            )
            Tile['ProgressAgeSec'] = ProgAge
            Tiles.append(Tile)
        return Tiles

    # directive: worker-runtime-state | # see admin-workers.C9
    def _GetProgressAgeByAttempt(self, AttemptIds):
        """Bulk-fetch per-attempt seconds since last TranscodeProgress update."""
        if not AttemptIds:
            return {}
        Rows = self._Db.ExecuteQuery(
            "SELECT TranscodeAttemptId, EXTRACT(EPOCH FROM (NOW() - LastProgressUpdate))::int AS age "
            "FROM TranscodeProgress WHERE TranscodeAttemptId = ANY(%s)",
            (AttemptIds,),
        )
        return {int(R['transcodeattemptid']): int(R['age']) for R in (Rows or []) if R.get('age') is not None}

    # directive: worker-runtime-state | # see admin-workers.C12
    def GetHungEncodeThresholdSec(self) -> int:
        Rows = self._Db.ExecuteQuery(
            "SELECT SettingValue FROM SystemSettings WHERE SettingKey = 'HungEncodeThresholdSec' LIMIT 1"
        )
        try:
            return int(Rows[0]['settingvalue']) if Rows else 600
        except (KeyError, ValueError, TypeError):
            return 600

    # directive: worker-runtime-state | # see admin-workers.C4
    def GetStaleThresholdSec(self) -> int:
        Rows = self._Db.ExecuteQuery(
            "SELECT SettingValue FROM SystemSettings WHERE SettingKey = 'HeartbeatStaleThresholdSec' LIMIT 1"
        )
        try:
            return int(Rows[0]['settingvalue']) if Rows else 300
        except (KeyError, ValueError, TypeError):
            return 300


# directive: worker-runtime-state | # see admin-workers.C6
def _DeriveDivergence(Status, RuntimeState, HeartbeatAgeSec, ThresholdSec):
    """Fresh worker with intent/state disagreement; stale is offline not diverge."""
    if not Status:
        return False
    if HeartbeatAgeSec is None:
        return False
    if int(HeartbeatAgeSec) > int(ThresholdSec):
        return False
    if not RuntimeState:
        return False
    if Status == 'Online':
        return RuntimeState not in ('Idle', 'ClaimingJob', 'Encoding', 'Scanning', 'Initializing')
    if Status == 'Paused':
        return RuntimeState not in ('Paused', 'Draining')
    return False
