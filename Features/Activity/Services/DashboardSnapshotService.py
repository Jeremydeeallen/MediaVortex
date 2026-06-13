from datetime import datetime, timezone
from typing import List, Dict, Optional

from Core.Database.DatabaseService import DatabaseService
from Features.Activity.Models.ActiveJobRow import ActiveJobRow
from Features.Activity.Models.WorkerTile import WorkerTile
from Features.Activity.Models.DashboardSnapshot import DashboardSnapshot
from Features.Activity.Services.ProgressSmoothingService import ProgressSmoothingService


# directive: activity-dashboard-solid | # see activity-dashboard-solid.C1
class DashboardSnapshotService:
    """Orchestrates a single DashboardSnapshot per poll. SRP: assembly only -- data lives in Repositories + Services it composes."""

    # directive: activity-dashboard-solid | # see activity-dashboard-solid.C1
    def __init__(self, Db: Optional[DatabaseService] = None):
        self.Db = Db or DatabaseService()
        StaleSec = self._GetIntSetting('StaleProgressThresholdSec', 15)
        HeartSec = self._GetIntSetting('HeartbeatStaleThresholdSec', 300)
        self.StaleSec = StaleSec
        self.HeartSec = HeartSec
        self.Smoother = ProgressSmoothingService(Db=self.Db, StaleSec=StaleSec)

    # directive: activity-dashboard-solid | # see activity-dashboard-solid.C1
    def _GetIntSetting(self, Key: str, Default: int) -> int:
        """Fresh DB read; never cached on the instance after construction's setting fetch (db-is-authority)."""
        Rows = self.Db.ExecuteQuery("SELECT SettingValue FROM SystemSettings WHERE SettingKey = %s LIMIT 1", (Key,))
        if not Rows:
            return Default
        try:
            return int(Rows[0]['SettingValue'])
        except (TypeError, ValueError):
            return Default

    # directive: activity-dashboard-solid | # see activity-dashboard-solid.C1
    def BuildSnapshot(self) -> DashboardSnapshot:
        """Single-pass build. Workers and ActiveJobs are independently sourced; Worker.Status never filters ActiveJobs (AC3)."""
        Workers = self._BuildWorkers()
        ActiveJobs = self._BuildActiveJobs()
        QueueCounts = self._BuildQueueCounts()
        BadgeState = self._BuildBadgeState(ActiveJobs)
        return DashboardSnapshot(
            Workers=Workers,
            ActiveJobs=ActiveJobs,
            QueueCounts=QueueCounts,
            BadgeState=BadgeState,
            StaleProgressThresholdSec=self.StaleSec,
            HeartbeatStaleThresholdSec=self.HeartSec,
        )

    # directive: activity-dashboard-solid | # see activity-dashboard-solid.C4
    def _BuildWorkers(self) -> List[WorkerTile]:
        """All Workers, with HeartbeatAgeSec derived from LastHeartbeat. Status field is verbatim. see activity-dashboard-solid.C4"""
        Now = datetime.now(timezone.utc)
        Rows = self.Db.ExecuteQuery(
            "SELECT WorkerName, Status, LastHeartbeat, TranscodeEnabled, RemuxEnabled, QualityTestEnabled, "
            "ScanEnabled, AcceptsInterlaced, nvenccapable, MaxConcurrentJobs "
            "FROM Workers WHERE COALESCE(Enabled, TRUE) = TRUE "
            "ORDER BY WorkerName"
        )
        Tiles: List[WorkerTile] = []
        for R in Rows:
            Lh = R.get('LastHeartbeat')
            Age = None
            if Lh is not None:
                Lh_ts = Lh if Lh.tzinfo else Lh.replace(tzinfo=timezone.utc)
                Age = int((Now - Lh_ts).total_seconds())
            Tiles.append(WorkerTile(
                WorkerName=R['WorkerName'],
                Status=str(R.get('Status') or 'Paused'),
                LastHeartbeat=Lh,
                HeartbeatAgeSec=Age,
                TranscodeEnabled=bool(R.get('TranscodeEnabled')),
                RemuxEnabled=bool(R.get('RemuxEnabled')),
                QualityTestEnabled=bool(R.get('QualityTestEnabled')),
                ScanEnabled=bool(R.get('ScanEnabled')),
                AcceptsInterlaced=bool(R.get('AcceptsInterlaced')),
                nvenccapable=bool(R.get('nvenccapable')),
                MaxConcurrentJobs=int(R.get('MaxConcurrentJobs') or 1),
            ))
        return Tiles

    # directive: activity-dashboard-solid | # see activity-dashboard-solid.C3
    def _BuildActiveJobs(self) -> List[ActiveJobRow]:
        """ActiveJobs WHERE TranscodeAttempts.Success IS NULL. JOIN Workers for display name only. Worker.Status NEVER filters."""
        Rows = self.Db.ExecuteQuery(
            "SELECT aj.Id AS AttemptId, aj.WorkerName, aj.ServiceName, aj.StartedAt, "
            "tq.MediaFileId, tq.FileName, tq.SizeMB, "
            "ta.ProfileName, "
            "tp.ProgressPercent, tp.CurrentFrame, tp.TotalFrames, tp.LastProgressUpdate "
            "FROM ActiveJobs aj "
            "LEFT JOIN TranscodeQueue tq ON tq.Id = aj.QueueId "
            "LEFT JOIN TranscodeAttempts ta ON ta.Id = aj.QueueId "
            "LEFT JOIN TranscodeProgress tp ON tp.TranscodeAttemptId = aj.QueueId "
            "WHERE (ta.Success IS NULL OR ta.Id IS NULL) "
            "ORDER BY aj.StartedAt ASC"
        )
        Out: List[ActiveJobRow] = []
        for R in Rows:
            AttemptId = int(R['AttemptId'])
            Fps, Speed, Eta = self.Smoother.SmoothForAttempt(AttemptId)
            IsStale = (Fps is None)
            Out.append(ActiveJobRow(
                AttemptId=AttemptId,
                MediaFileId=int(R['MediaFileId']) if R.get('MediaFileId') is not None else None,
                FileName=R.get('FileName') or '',
                WorkerName=R.get('WorkerName'),
                ProfileName=R.get('ProfileName'),
                SizeMB=float(R['SizeMB']) if R.get('SizeMB') is not None else None,
                ProgressPercent=int(R['ProgressPercent']) if R.get('ProgressPercent') is not None else None,
                SmoothedFPS=Fps,
                SmoothedSpeed=Speed,
                EtaSeconds=Eta,
                ServiceName=R.get('ServiceName'),
                ClaimedAt=R.get('StartedAt'),
                IsStale=IsStale,
            ))
        return Out

    # directive: activity-dashboard-solid | # see activity-dashboard-solid.C1
    def _BuildQueueCounts(self) -> Dict[str, int]:
        """Counts for the badge state. Cheap aggregates only -- no per-row work."""
        Counts = {}
        Rows = self.Db.ExecuteQuery(
            "SELECT ProcessingMode, COUNT(*) AS n FROM TranscodeQueue "
            "WHERE Status = 'Pending' GROUP BY ProcessingMode"
        )
        for R in Rows:
            Mode = R.get('ProcessingMode') or 'Transcode'
            Counts[Mode] = int(R['n'])
        return Counts

    # directive: activity-dashboard-solid | # see activity-dashboard-solid.C1
    def _BuildBadgeState(self, ActiveJobs: List[ActiveJobRow]) -> Dict[str, int]:
        """Top-of-page badges: active job count, failed-jobs count (from Cluster A repository), QT in-flight."""
        FailedCount = 0
        try:
            from Features.FailureAccounting.Repositories.FailedJobsRepository import FailedJobsRepository
            FailedCount = FailedJobsRepository().CountCapped()
        except Exception:
            FailedCount = 0
        QtInFlight = int(self.Db.ExecuteQuery(
            "SELECT COUNT(*) AS n FROM QualityTestingQueue WHERE Status = 'Running'"
        )[0]['n'])
        return {
            'ActiveJobs': len(ActiveJobs),
            'FailedJobs': FailedCount,
            'QualityTestsInFlight': QtInFlight,
        }
