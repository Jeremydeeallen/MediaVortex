from datetime import datetime, timezone, timedelta
from typing import List, Optional, Tuple
from Core.Database.DatabaseService import DatabaseService


WINDOW_SAMPLES = 10
WINDOW_SECONDS = 30


# directive: activity-dashboard-solid | # see activity-dashboard-solid.C2
class ProgressSmoothingService:
    """Rolling-window arithmetic mean of CurrentFPS + CurrentSpeed per TranscodeAttemptId. DB-fresh per call; no cache. Past StaleProgressThresholdSec returns (None, None, None) -- rendered '--'."""

    # directive: activity-dashboard-solid | # see activity-dashboard-solid.C2
    def __init__(self, Db: Optional[DatabaseService] = None, StaleSec: int = 15):
        self.Db = Db or DatabaseService()
        self.StaleSec = int(StaleSec)

    # directive: activity-dashboard-solid | # see activity-dashboard-solid.C2
    def SmoothForAttempt(self, AttemptId: int) -> Tuple[Optional[float], Optional[float], Optional[int]]:
        """Return (smoothed_fps, smoothed_speed_x, eta_seconds). All None when no fresh samples within StaleSec."""
        Cutoff = datetime.now(timezone.utc) - timedelta(seconds=WINDOW_SECONDS)
        Rows = self.Db.ExecuteQuery(
            "SELECT CurrentFPS, CurrentSpeed, ProgressPercent, CurrentFrame, TotalFrames, LastProgressUpdate "
            "FROM TranscodeProgress WHERE TranscodeAttemptId = %s "
            "AND LastProgressUpdate >= %s "
            "ORDER BY LastProgressUpdate DESC LIMIT %s",
            (int(AttemptId), Cutoff, WINDOW_SAMPLES),
        )
        if not Rows:
            return (None, None, None)

        Newest = Rows[0]
        if Newest['LastProgressUpdate'] is None:
            return (None, None, None)
        Newest_ts = Newest['LastProgressUpdate']
        if Newest_ts.tzinfo is None:
            Newest_ts = Newest_ts.replace(tzinfo=timezone.utc)
        AgeSec = (datetime.now(timezone.utc) - Newest_ts).total_seconds()
        if AgeSec > self.StaleSec:
            return (None, None, None)

        FPSVals = [float(R['CurrentFPS']) for R in Rows if R.get('CurrentFPS') is not None]
        SpeedVals = []
        for R in Rows:
            S = R.get('CurrentSpeed')
            if S is None:
                continue
            try:
                StrS = str(S).strip().rstrip('xX')
                if StrS:
                    SpeedVals.append(float(StrS))
            except (TypeError, ValueError):
                pass

        Fps = round(sum(FPSVals) / len(FPSVals), 1) if FPSVals else None
        Speed = round(sum(SpeedVals) / len(SpeedVals), 2) if SpeedVals else None

        Eta = self._ComputeEta(Newest, Fps)
        return (Fps, Speed, Eta)

    @staticmethod
    # directive: activity-dashboard-solid | # see activity-dashboard-solid.C2
    def _ComputeEta(Newest: dict, SmoothedFps: Optional[float]) -> Optional[int]:
        """ETA = (total_frames - current_frame) / smoothed_fps. None when smoothed FPS unavailable or totals unknown."""
        if not SmoothedFps or SmoothedFps <= 0:
            return None
        Total = Newest.get('TotalFrames')
        Cur = Newest.get('CurrentFrame')
        if not Total or Cur is None:
            return None
        try:
            Remaining = max(0, int(Total) - int(Cur))
            return int(Remaining / SmoothedFps)
        except (TypeError, ValueError, ZeroDivisionError):
            return None
