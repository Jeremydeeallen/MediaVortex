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
            "MaxConcurrentTranscodeJobs, MaxConcurrentRemuxJobs, MaxConcurrentQualityTestJobs, "
            "TranscodeEnabled, RemuxEnabled, QualityTestEnabled, ScanEnabled, NvencCapable, "
            "Version, BuildInfo, MountValidationError, Enabled, "
            "RuntimeState, CurrentAttemptId, LastRuntimeStateUpdate, "
            "EXTRACT(EPOCH FROM (NOW() - LastHeartbeat))::int AS HeartbeatAgeSec, "
            "EXTRACT(EPOCH FROM (NOW() - LastRuntimeStateUpdate))::int AS RuntimeStateAgeSec "
            "FROM Workers WHERE Enabled = TRUE "
            "ORDER BY WorkerName ASC"
        )
        Threshold = self.GetDivergenceThresholdSec()
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
                Tile.get('runtimestateagesec'),
                Threshold,
            )
            AttemptId = Tile.get('currentattemptid')
            ProgAge = ProgressAgeByAttempt.get(int(AttemptId)) if AttemptId is not None else None
            Tile['IsHung'] = IsHung(
                Tile.get('runtimestate'),
                Tile.get('runtimestateagesec'),
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
    def GetDivergenceThresholdSec(self) -> int:
        Rows = self._Db.ExecuteQuery(
            "SELECT SettingValue FROM SystemSettings WHERE SettingKey = 'WorkerIntentDivergenceSec' LIMIT 1"
        )
        try:
            return int(Rows[0]['settingvalue']) if Rows else 60
        except (KeyError, ValueError, TypeError):
            return 60


# directive: worker-runtime-state | # see admin-workers.C6
def _DeriveDivergence(Status, RuntimeState, RuntimeStateAgeSec, ThresholdSec):
    """Operator-Status vs worker-RuntimeState. Returns True when disagreement has persisted past threshold."""
    if not Status:
        return False
    Threshold = int(ThresholdSec)
    Age = None if RuntimeStateAgeSec is None else int(RuntimeStateAgeSec)
    if Status == 'Online' and (RuntimeState is None or Age is None or Age > Threshold):
        return True
    if not RuntimeState:
        return False
    WorkerActive = RuntimeState in ('Idle', 'ClaimingJob', 'Encoding', 'Scanning', 'Initializing')
    Compatible = (
        (Status == 'Online' and WorkerActive)
        or (Status == 'Paused' and (RuntimeState in ('Paused', 'Draining')))
    )
    if Compatible:
        return False
    return Age is not None and Age > Threshold
