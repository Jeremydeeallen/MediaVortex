from datetime import datetime, timezone
from typing import List, Dict, Optional

from Core.Database.DatabaseService import DatabaseService
from Features.Activity.Models.ActiveJobRow import ActiveJobRow
from Features.Activity.Models.WorkerTile import WorkerTile
from Features.Activity.Models.DashboardSnapshot import DashboardSnapshot
from Features.Activity.Services.ProgressSmoothingService import ProgressSmoothingService


# directive: worker-runtime-state | # see activity.S4
def _EstimateSavings(ProcessingMode, SourceSizeBytes, SourceVideoKbps, TargetVideoKbps):
    """Negative => size shrink. Only meaningful for Transcode jobs with known source + target bitrates."""
    if ProcessingMode != 'Transcode' or not SourceSizeBytes or not SourceVideoKbps or not TargetVideoKbps:
        return None
    try:
        SrcBytes = int(SourceSizeBytes)
        SrcKbps = float(SourceVideoKbps)
        TgtKbps = float(TargetVideoKbps)
    except (TypeError, ValueError):
        return None
    if SrcKbps <= 0:
        return None
    TargetBytes = int(SrcBytes * (TgtKbps / SrcKbps))
    return TargetBytes - SrcBytes


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

    # directive: worker-runtime-state | # see activity.C5
    def BuildSnapshot(self) -> DashboardSnapshot:
        """Single-pass build. Active Jobs + Active Scans + Queue Counts + Badge State + Hung Attempts."""
        Workers = self._BuildWorkers()
        ActiveJobs = self._BuildActiveJobs()
        ActiveScans = self._BuildActiveScans()
        QueueCounts = self._BuildQueueCounts()
        BadgeState = self._BuildBadgeState(ActiveJobs)
        HungAttempts = self._BuildHungAttempts()
        return DashboardSnapshot(
            Workers=Workers,
            ActiveJobs=ActiveJobs,
            ActiveScans=ActiveScans,
            QueueCounts=QueueCounts,
            BadgeState=BadgeState,
            HungAttempts=HungAttempts,
            StaleProgressThresholdSec=self.StaleSec,
            HeartbeatStaleThresholdSec=self.HeartSec,
        )

    # directive: worker-runtime-state | # see admin-workers.C9
    def _BuildHungAttempts(self):
        """Return list of currently-hung attempts (worker-RuntimeState='Encoding' too long without progress)."""
        from Features.StuckJobDetection.HungEncodeDetector import IsHung
        ThresholdRows = self.Db.ExecuteQuery(
            "SELECT SettingValue FROM SystemSettings WHERE SettingKey = 'HungEncodeThresholdSec' LIMIT 1"
        )
        try:
            Threshold = int(ThresholdRows[0]['SettingValue']) if ThresholdRows else 600
        except (KeyError, ValueError, TypeError):
            Threshold = 600
        Rows = self.Db.ExecuteQuery(
            "SELECT w.WorkerName, w.RuntimeState, w.CurrentAttemptId, "
            "EXTRACT(EPOCH FROM (NOW() - w.LastRuntimeStateUpdate))::int AS rs_age, "
            "EXTRACT(EPOCH FROM (NOW() - tp.LastProgressUpdate))::int AS prog_age, "
            "tq.FileName "
            "FROM Workers w "
            "LEFT JOIN TranscodeProgress tp ON tp.TranscodeAttemptId = w.CurrentAttemptId "
            "LEFT JOIN ActiveJobs aj ON aj.QueueId = w.CurrentAttemptId AND aj.WorkerName = w.WorkerName "
            "LEFT JOIN TranscodeQueue tq ON tq.Id = aj.QueueId "
            "WHERE w.Enabled = TRUE AND w.RuntimeState = 'Encoding' AND w.CurrentAttemptId IS NOT NULL"
        )
        Out = []
        for R in (Rows or []):
            if not IsHung(R.get('RuntimeState') or R.get('runtimestate'), R.get('rs_age'), R.get('prog_age'), Threshold):
                continue
            Out.append({
                'AttemptId': int(R['CurrentAttemptId']) if R.get('CurrentAttemptId') is not None else int(R['currentattemptid']),
                'WorkerName': R.get('WorkerName') or R.get('workername'),
                'FileName': R.get('FileName') or R.get('filename'),
                'MinutesStuck': int((int(R.get('rs_age') or 0)) / 60),
            })
        return Out

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

    # directive: worker-runtime-state | # see activity.S4
    def _BuildActiveJobs(self) -> List[ActiveJobRow]:
        """ActiveJobs JOIN MediaFiles + Profiles for the interesting columns. Worker.Status NEVER filters."""
        Rows = self.Db.ExecuteQuery(
            "SELECT aj.Id AS AttemptId, aj.WorkerName, aj.ServiceName, aj.StartedAt, "
            "tq.MediaFileId, tq.FileName, tq.SizeMB, tq.ProcessingMode, tq.SizeBytes, "
            "ta.ProfileName, "
            "tp.ProgressPercent, tp.CurrentFrame, tp.TotalFrames, tp.LastProgressUpdate, "
            "mf.ResolutionCategory AS SourceResolutionCategory, mf.Codec AS SourceCodec, "
            "mf.VideoBitrateKbps AS SourceVideoKbps, "
            "p.TargetResolutionCategory AS TargetResolutionCategory, p.Codec AS TargetCodec, "
            "p.TargetVideoKbps "
            "FROM ActiveJobs aj "
            "LEFT JOIN TranscodeQueue tq ON tq.Id = aj.QueueId "
            "LEFT JOIN TranscodeAttempts ta ON ta.Id = aj.QueueId "
            "LEFT JOIN TranscodeProgress tp ON tp.TranscodeAttemptId = aj.QueueId "
            "LEFT JOIN MediaFiles mf ON mf.Id = tq.MediaFileId "
            "LEFT JOIN Profiles p ON p.ProfileName = ta.ProfileName "
            "WHERE (ta.Success IS NULL OR ta.Id IS NULL) "
            "ORDER BY aj.StartedAt ASC"
        )
        Out: List[ActiveJobRow] = []
        for R in Rows:
            AttemptId = int(R['AttemptId'])
            Fps, Speed, Eta = self.Smoother.SmoothForAttempt(AttemptId)
            IsStale = (Fps is None)
            SizeBytes = R.get('SizeBytes')
            TargetKbps = R.get('TargetVideoKbps')
            EstSavings = _EstimateSavings(R.get('ProcessingMode'), SizeBytes, R.get('SourceVideoKbps'), TargetKbps)
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
                ProcessingMode=R.get('ProcessingMode'),
                SourceResolutionCategory=R.get('SourceResolutionCategory'),
                TargetResolutionCategory=str(R.get('TargetResolutionCategory')) if R.get('TargetResolutionCategory') is not None else None,
                SourceCodec=R.get('SourceCodec'),
                TargetCodec=R.get('TargetCodec'),
                EstimatedSavingsBytes=EstSavings,
            ))
        return Out

    # directive: worker-runtime-state | # see activity.C3
    def _BuildActiveScans(self) -> List[Dict]:
        """Drive / Worker / Phase / Progress / Files / ETA for the Active Scans table."""
        Rows = self.Db.ExecuteQuery(
            "SELECT WorkerName, CurrentDirectory AS Drive, Phase, "
            "ProcessedFiles, TotalFiles, Progress AS PercentComplete, "
            "StartTime "
            "FROM ScanJobs WHERE Status = 'Running' "
            "ORDER BY WorkerName ASC"
        )
        from datetime import datetime, timezone
        Now = datetime.now(timezone.utc)
        Out = []
        for R in (Rows or []):
            Processed = R.get('ProcessedFiles')
            Total = R.get('TotalFiles')
            StartTime = R.get('StartTime')
            EtaSec = None
            if StartTime is not None and Processed and Total and int(Total) > int(Processed):
                StartTs = StartTime if StartTime.tzinfo else StartTime.replace(tzinfo=timezone.utc)
                Elapsed = (Now - StartTs).total_seconds()
                if Elapsed > 0 and int(Processed) > 0:
                    EtaSec = int((Elapsed / int(Processed)) * (int(Total) - int(Processed)))
            Out.append({
                'Drive': R.get('Drive'),
                'WorkerName': R.get('WorkerName'),
                'Phase': R.get('Phase'),
                'PercentComplete': float(R['PercentComplete']) if R.get('PercentComplete') is not None else None,
                'FilesProcessed': int(Processed) if Processed is not None else None,
                'FilesTotal': int(Total) if Total is not None else None,
                'EtaSeconds': EtaSec,
            })
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
