"""
TeamStatus Controller
API endpoints for transcode savings and status overview.
"""

from flask import Blueprint, request, jsonify
from Repositories.DatabaseManager import DatabaseManager
from Services.LoggingService import LoggingService
from Features.SystemSettings.SystemSettingsRepository import SystemSettingsRepository

# Directive 2026-05-27: cache last (ProcessedFiles, ProbedFiles, LastUpdated)
# per scan JobId so files-per-second can be computed as a rolling delta against
# the prior /Overview call instead of cumulative-since-start. Cleared on row
# disappearance (terminal status). One entry per active scan; bounded by the
# number of workers, not by scan history.
_ScanRateCache = {}


def _BuildActiveScans(DbManager):
    """Server-side projection of ScanJobs.Status='Running' rows for /Activity.

    Adds derived fields the client should not have to compute:
      - ElapsedSec        : seconds since StartTime
      - FilesPerSec       : rolling delta vs prior call (via _ScanRateCache);
                            cumulative-since-start on the first observation.
      - EtaSec            : Walking -> remaining files / rate; Probing -> remaining probes / probe-rate; else null.
      - IsStuck           : LastUpdated > 10 minutes ago.
    """
    from datetime import datetime, timezone
    Query = """
        SELECT JobId, WorkerName, RootFolderPath, CurrentDirectory, Phase,
               Progress, TotalFiles, ProcessedFiles, FilesNeedingProbe, ProbedFiles,
               NewFiles, UpdatedFiles, DeletedFiles, StartTime, LastUpdated,
               TopFiles,
               EXTRACT(EPOCH FROM (NOW() - StartTime))   AS ElapsedSec,
               EXTRACT(EPOCH FROM (NOW() - LastUpdated)) AS StaleSec
        FROM ScanJobs
        WHERE Status = 'Running'
        ORDER BY StartTime ASC
    """
    Rows = DbManager.DatabaseService.ExecuteQuery(Query) or []
    Now = datetime.now(timezone.utc).timestamp()
    SeenJobIds = set()
    Out = []
    for Row in Rows:
        JobId = Row.get('JobId')
        SeenJobIds.add(JobId)
        Phase = Row.get('Phase') or 'Walking'
        Processed = int(Row.get('ProcessedFiles') or 0)
        Probed = int(Row.get('ProbedFiles') or 0)
        Total = int(Row.get('TotalFiles') or 0)
        NeedProbe = int(Row.get('FilesNeedingProbe') or 0)
        ElapsedSec = float(Row.get('ElapsedSec') or 0)
        StaleSec = float(Row.get('StaleSec') or 0)

        # Rolling rate via cache; falls back to since-start average on first sighting.
        Prev = _ScanRateCache.get(JobId)
        if Prev is not None:
            PrevProc, PrevProbed, PrevTs = Prev
            DeltaT = max(Now - PrevTs, 0.001)
            DeltaProc = max(Processed - PrevProc, 0)
            DeltaProbed = max(Probed - PrevProbed, 0)
            WalkRate = DeltaProc / DeltaT
            ProbeRate = DeltaProbed / DeltaT
        else:
            WalkRate = (Processed / ElapsedSec) if ElapsedSec > 0 else 0.0
            ProbeRate = (Probed / ElapsedSec) if ElapsedSec > 0 else 0.0
        _ScanRateCache[JobId] = (Processed, Probed, Now)

        # Phase-aware rate + ETA. The UI's FPS cell reads the phase-appropriate rate.
        if Phase == 'Probing':
            FilesPerSec = ProbeRate
            Remaining = max(NeedProbe - Probed, 0)
            EtaSec = (Remaining / ProbeRate) if ProbeRate > 0.01 else None
        elif Phase in ('Reconciling', 'Completing'):
            FilesPerSec = 0.0
            EtaSec = None
        else:  # Walking (or NULL legacy)
            FilesPerSec = WalkRate
            Remaining = max(Total - Processed, 0) if Total > 0 else 0
            EtaSec = (Remaining / WalkRate) if WalkRate > 0.01 and Total > 0 else None

        # Directive 2026-05-27: surface top-5 largest files from SizeSurvey
        # under each scan row. Limit to 5 to keep payload small; full list
        # remains on ScanJobs.TopFiles for ad-hoc queries.
        TopFiles = Row.get('TopFiles')
        TopFilesOut = []
        if TopFiles:
            try:
                if isinstance(TopFiles, str):
                    import json as _json
                    TopFiles = _json.loads(TopFiles)
                if isinstance(TopFiles, list):
                    for Entry in TopFiles[:5]:
                        TopFilesOut.append({
                            "fileName": Entry.get('fileName') or '',
                            "path": Entry.get('path') or '',
                            "sizeMB": Entry.get('sizeMB') or 0,
                        })
            except Exception:
                pass

        Out.append({
            "JobId": JobId,
            "WorkerName": Row.get('WorkerName') or '<unknown>',
            "RootFolderPath": Row.get('RootFolderPath'),
            "CurrentDirectory": Row.get('CurrentDirectory'),
            "Phase": Phase,
            "Progress": float(Row.get('Progress') or 0.0),
            "TotalFiles": Total,
            "ProcessedFiles": Processed,
            "FilesNeedingProbe": NeedProbe,
            "ProbedFiles": Probed,
            "NewFiles": int(Row.get('NewFiles') or 0),
            "UpdatedFiles": int(Row.get('UpdatedFiles') or 0),
            "DeletedFiles": int(Row.get('DeletedFiles') or 0),
            "StartTime": str(Row.get('StartTime')) if Row.get('StartTime') else None,
            "LastUpdated": str(Row.get('LastUpdated')) if Row.get('LastUpdated') else None,
            "ElapsedSec": int(ElapsedSec),
            "FilesPerSec": round(FilesPerSec, 2),
            "EtaSec": int(EtaSec) if EtaSec is not None else None,
            "IsStuck": StaleSec > 600,
            "TopFiles": TopFilesOut,
        })
    # Evict cache entries for scans that completed since the last call.
    for Stale in [k for k in _ScanRateCache.keys() if k not in SeenJobIds]:
        _ScanRateCache.pop(Stale, None)
    return Out


def _BuildRecentScans(DbManager, Limit: int = 5):
    """Last N terminal-status scans for the Recent Scans strip on /Activity."""
    Query = """
        SELECT JobId, WorkerName, RootFolderPath, Status,
               StartTime, EndTime, ErrorMessage,
               NewFiles, UpdatedFiles, DeletedFiles, ProcessedFiles, TotalFiles,
               EXTRACT(EPOCH FROM (EndTime - StartTime)) AS DurationSec
        FROM ScanJobs
        WHERE Status IN ('Completed', 'Failed', 'Stopped')
          AND EndTime IS NOT NULL
        ORDER BY EndTime DESC
        LIMIT %s
    """
    Rows = DbManager.DatabaseService.ExecuteQuery(Query, (Limit,)) or []
    Out = []
    for Row in Rows:
        Out.append({
            "JobId": Row.get('JobId'),
            "WorkerName": Row.get('WorkerName') or '<unknown>',
            "RootFolderPath": Row.get('RootFolderPath'),
            "Status": Row.get('Status'),
            "StartTime": str(Row.get('StartTime')) if Row.get('StartTime') else None,
            "EndTime": str(Row.get('EndTime')) if Row.get('EndTime') else None,
            "DurationSec": int(Row.get('DurationSec') or 0),
            "ErrorMessage": Row.get('ErrorMessage'),
            "NewFiles": int(Row.get('NewFiles') or 0),
            "UpdatedFiles": int(Row.get('UpdatedFiles') or 0),
            "DeletedFiles": int(Row.get('DeletedFiles') or 0),
            "ProcessedFiles": int(Row.get('ProcessedFiles') or 0),
            "TotalFiles": int(Row.get('TotalFiles') or 0),
        })
    return Out


def _GetContinuousScanIntervalMinutes() -> int:
    try:
        Val = SystemSettingsRepository().GetSystemSetting('ContinuousScanIntervalMinutes')
        return int(Val) if Val else 60
    except Exception:
        return 60


def _GetDisplayTimezone() -> str:
    """Read SystemSettings.DisplayTimezone for SQL day-bucketing.

    Day-bucket aggregations (e.g. SavingsByDay) must group on the user's
    configured timezone, not UTC -- otherwise transcodes finishing late
    evening Chicago time fall into the next UTC day's bucket on the chart.
    Defaults to 'UTC' if the setting is missing or unreadable so the query
    still produces a valid result instead of raising.
    """
    try:
        return SystemSettingsRepository().GetSystemSetting('DisplayTimezone') or 'UTC'
    except Exception as Ex:
        LoggingService.LogException(
            "Failed to read DisplayTimezone for SavingsByDay bucketing -- defaulting to UTC",
            Ex, "_GetDisplayTimezone", "TeamStatusController"
        )
        return 'UTC'

TeamStatusBlueprint = Blueprint('TeamStatus', __name__, url_prefix='/api/TeamStatus')


@TeamStatusBlueprint.route('/Overview', methods=['GET'])
def GetOverview():
    """Get summary stats: total space saved, total jobs, avg savings %, current status."""
    try:
        LoggingService.LogFunctionEntry("GetOverview", "TeamStatusController")

        DbManager = DatabaseManager()

        # Summary stats from successful transcode attempts that ACTUALLY
        # landed on disk (FileReplaced=TRUE). Without that filter, Requeued
        # intermediate attempts get their delta double-counted -- the
        # staged file was deleted by Requeue cleanup so no real disk
        # savings, but ta.SizeReductionBytes still records "would have
        # saved this much." Only the winning attempt actually saves bytes.
        StatsQuery = """
            SELECT COUNT(*) AS JobCount,
                   COALESCE(SUM(ta.OldSizeBytes), 0) AS TotalOriginalBytes,
                   COALESCE(SUM(ta.NewSizeBytes), 0) AS TotalNewBytes,
                   COALESCE(SUM(ta.SizeReductionBytes), 0) AS TotalSavedBytes
            FROM TranscodeAttempts ta
            WHERE ta.Success = TRUE AND ta.SizeReductionBytes > 0
              AND ta.FileReplaced = TRUE
        """
        StatsRows = DbManager.DatabaseService.ExecuteQuery(StatsQuery)
        Stats = StatsRows[0] if StatsRows else {}

        TotalOriginal = Stats.get('TotalOriginalBytes', 0) or 0
        AvgSavingsPercent = round((Stats.get('TotalSavedBytes', 0) or 0) / TotalOriginal * 100, 1) if TotalOriginal > 0 else 0

        # Current transcode service status — same approach as Activity page
        StatusQuery = """
            SELECT Status, HealthStatus, IsProcessing, ActiveJobsCount, LastHealthCheck
            FROM ServiceStatus
            WHERE ServiceName = 'TranscodeService'
        """
        StatusRows = DbManager.DatabaseService.ExecuteQuery(StatusQuery)
        StatusRow = StatusRows[0] if StatusRows else None

        CurrentStatus = StatusRow.get('Status', 'Unknown') if StatusRow else 'Unknown'
        IsProcessing = bool(StatusRow.get('IsProcessing', False)) if StatusRow else False
        ActiveJobsCount = StatusRow.get('ActiveJobsCount', 0) if StatusRow else 0

        # Current job info — query ALL active jobs from progress + queue
        # Includes ClaimedBy (worker name) and worker heartbeat for stuck detection
        ActiveJobs = []
        JobQuery = """
            SELECT tq.Id AS QueueId, ta.FilePath, tq.FileName, tq.SizeMB,
                   tq.ProcessingMode,
                   tp.ProgressPercent, tp.CurrentPhase,
                   tp.CurrentFPS, tp.CurrentSpeed, tp.ETA,
                   tq.DateStarted, tq.ClaimedBy,
                   w.LastHeartbeat,
                   EXTRACT(EPOCH FROM (NOW() - w.LastHeartbeat)) AS HeartbeatAgeSec
            FROM TranscodeProgress tp
            JOIN TranscodeAttempts ta ON tp.TranscodeAttemptId = ta.Id
            JOIN TranscodeQueue tq ON tq.MediaFileId = ta.MediaFileId AND tq.Status = 'Running'
            LEFT JOIN Workers w ON w.WorkerName = tq.ClaimedBy
            WHERE ta.Success IS NULL
            ORDER BY tq.DateStarted ASC
        """
        JobRows = DbManager.DatabaseService.ExecuteQuery(JobQuery)

        # Also find Running queue items with NO progress row (stuck before FFmpeg started)
        StuckFallbackQuery = """
            SELECT tq.Id AS QueueId, tq.FilePath, tq.FileName, tq.SizeMB,
                   tq.ProcessingMode,
                   tq.DateStarted, tq.ClaimedBy,
                   w.LastHeartbeat,
                   EXTRACT(EPOCH FROM (NOW() - w.LastHeartbeat)) AS HeartbeatAgeSec
            FROM TranscodeQueue tq
            LEFT JOIN Workers w ON w.WorkerName = tq.ClaimedBy
            WHERE tq.Status = 'Running'
              AND NOT EXISTS (
                  SELECT 1 FROM TranscodeProgress tp
                  JOIN TranscodeAttempts ta ON tp.TranscodeAttemptId = ta.Id
                  WHERE ta.MediaFileId = tq.MediaFileId AND ta.Success IS NULL
              )
        """
        StuckRows = DbManager.DatabaseService.ExecuteQuery(StuckFallbackQuery)

        ProgressQueueIds = set()
        for Row in (JobRows or []):
            HeartbeatAge = Row.get('HeartbeatAgeSec')
            IsStuck = HeartbeatAge is not None and HeartbeatAge > 300
            ProgressQueueIds.add(Row.get('QueueId', 0))
            ActiveJobs.append({
                "QueueId": Row.get('QueueId', 0),
                "FilePath": Row.get('FilePath', ''),
                "FileName": Row.get('FileName', ''),
                "SizeMB": Row.get('SizeMB', 0),
                "ProcessingMode": Row.get('ProcessingMode', 'Transcode') or 'Transcode',
                "ProgressPercent": Row.get('ProgressPercent', 0),
                "CurrentPhase": Row.get('CurrentPhase', ''),
                "CurrentFPS": Row.get('CurrentFPS', 0),
                "CurrentSpeed": Row.get('CurrentSpeed', ''),
                "ETA": Row.get('ETA', ''),
                "DateStarted": str(Row.get('DateStarted', '')) if Row.get('DateStarted') else '',
                "ClaimedBy": Row.get('ClaimedBy', ''),
                "IsStuck": IsStuck
            })

        for Row in (StuckRows or []):
            QueueId = Row.get('QueueId', 0)
            if QueueId in ProgressQueueIds:
                continue
            ActiveJobs.append({
                "QueueId": QueueId,
                "FilePath": Row.get('FilePath', ''),
                "FileName": Row.get('FileName', ''),
                "SizeMB": Row.get('SizeMB', 0),
                "ProcessingMode": Row.get('ProcessingMode', 'Transcode') or 'Transcode',
                "ProgressPercent": 0,
                "CurrentPhase": '',
                "CurrentFPS": 0,
                "CurrentSpeed": '',
                "ETA": '',
                "DateStarted": str(Row.get('DateStarted', '')) if Row.get('DateStarted') else '',
                "ClaimedBy": Row.get('ClaimedBy', ''),
                "IsStuck": True
            })

        # Also check for running queue items as a fallback
        if not IsProcessing:
            RunningQueueQuery = """
                SELECT COUNT(*) AS RunningCount
                FROM TranscodeQueue
                WHERE Status = 'Running'
            """
            RunningRows = DbManager.DatabaseService.ExecuteQuery(RunningQueueQuery)
            if RunningRows and (RunningRows[0].get('RunningCount', 0) or 0) > 0:
                IsProcessing = True
                ActiveJobsCount = RunningRows[0].get('RunningCount', 0)

        # Backward compat: CurrentJob is first active job (or null)
        CurrentJob = ActiveJobs[0] if ActiveJobs else None

        # Directive 2026-05-27: ActiveScans + RecentScans for /Activity scan
        # rows. Server-computes FilesPerSec / EtaSec / ElapsedSec / IsStuck so
        # the client renders without computation.
        ActiveScans = _BuildActiveScans(DbManager)
        RecentScans = _BuildRecentScans(DbManager, Limit=5)

        return jsonify({
            "Success": True,
            "Data": {
                "TotalSavedBytes": Stats.get('TotalSavedBytes', 0) or 0,
                "TotalOriginalBytes": TotalOriginal,
                "TotalNewBytes": Stats.get('TotalNewBytes', 0) or 0,
                "JobCount": Stats.get('JobCount', 0) or 0,
                "AvgSavingsPercent": AvgSavingsPercent,
                "ServiceStatus": CurrentStatus,
                "IsProcessing": IsProcessing,
                "ActiveJobsCount": ActiveJobsCount,
                "CurrentJob": CurrentJob,
                "ActiveJobs": ActiveJobs,
                "ActiveScans": ActiveScans,
                "RecentScans": RecentScans
            }
        })

    except Exception as e:
        ErrorMsg = f"Exception in GetOverview: {str(e)}"
        LoggingService.LogException(ErrorMsg, e, "TeamStatusController", "GetOverview")
        return jsonify({"Success": False, "ErrorMessage": ErrorMsg}), 500


@TeamStatusBlueprint.route('/SavingsByVolume', methods=['GET'])
def GetSavingsByVolume():
    """Get savings grouped by drive volume (e.g. T:\\, Z:\\, M:\\)."""
    try:
        LoggingService.LogFunctionEntry("GetSavingsByVolume", "TeamStatusController")

        DbManager = DatabaseManager()

        # FileReplaced=TRUE filter: only count attempts whose output actually
        # landed on disk -- otherwise multi-attempt files (Requeue -> Replace)
        # double-count their savings. See StatsQuery comment above.
        Query = """
            SELECT UPPER(LEFT(ta.FilePath, 3)) AS Volume,
                   COUNT(*) AS JobCount,
                   SUM(ta.OldSizeBytes) AS TotalOriginalBytes,
                   SUM(ta.NewSizeBytes) AS TotalNewBytes,
                   SUM(ta.SizeReductionBytes) AS TotalSavedBytes
            FROM TranscodeAttempts ta
            WHERE ta.Success = TRUE AND ta.SizeReductionBytes > 0
              AND ta.FileReplaced = TRUE
            GROUP BY UPPER(LEFT(ta.FilePath, 3))
            ORDER BY TotalSavedBytes DESC
        """
        Rows = DbManager.DatabaseService.ExecuteQuery(Query)

        return jsonify({
            "Success": True,
            "Data": [dict(Row) for Row in Rows]
        })

    except Exception as e:
        ErrorMsg = f"Exception in GetSavingsByVolume: {str(e)}"
        LoggingService.LogException(ErrorMsg, e, "TeamStatusController", "GetSavingsByVolume")
        return jsonify({"Success": False, "ErrorMessage": ErrorMsg}), 500


@TeamStatusBlueprint.route('/SavingsByDay', methods=['GET'])
def GetSavingsByDay():
    """Get savings grouped by day. Query param: Days (default 30)."""
    try:
        LoggingService.LogFunctionEntry("GetSavingsByDay", "TeamStatusController")

        Days = request.args.get('Days', 30, type=int)
        if Days < 1 or Days > 365:
            Days = 30

        DbManager = DatabaseManager()
        DisplayTz = _GetDisplayTimezone()

        # Bucket the day in the configured display timezone, not UTC. CompletedDate
        # is stored as a naive UTC TIMESTAMP, so we tell PostgreSQL to interpret it
        # as UTC and convert to the target zone before truncating to a date.
        # The date-window filter stays on raw CompletedDate (UTC) -- this slightly
        # over-fetches at the boundary but the GROUP BY produces correct buckets.
        # FileReplaced=TRUE filter: only count attempts whose output actually
        # landed on disk -- otherwise multi-attempt files double-count their
        # daily savings deltas. See StatsQuery comment above.
        Query = f"""
            SELECT DATE(ta.CompletedDate AT TIME ZONE 'UTC' AT TIME ZONE %s) AS Day,
                   COUNT(*) AS JobCount,
                   SUM(ta.SizeReductionBytes) AS TotalSavedBytes,
                   SUM(ta.OldSizeBytes) AS TotalOriginalBytes,
                   SUM(ta.NewSizeBytes) AS TotalNewBytes
            FROM TranscodeAttempts ta
            WHERE ta.Success = TRUE AND ta.SizeReductionBytes > 0
              AND ta.FileReplaced = TRUE
              AND ta.CompletedDate >= CURRENT_DATE - {Days} * INTERVAL '1 day'
            GROUP BY DATE(ta.CompletedDate AT TIME ZONE 'UTC' AT TIME ZONE %s)
            ORDER BY Day ASC
        """
        Rows = DbManager.DatabaseService.ExecuteQuery(Query, (DisplayTz, DisplayTz))

        # Convert date objects to strings for JSON serialization
        Data = []
        for Row in Rows:
            RowDict = dict(Row)
            if RowDict.get('Day'):
                RowDict['Day'] = str(RowDict['Day'])
            Data.append(RowDict)

        return jsonify({
            "Success": True,
            "Data": Data
        })

    except Exception as e:
        ErrorMsg = f"Exception in GetSavingsByDay: {str(e)}"
        LoggingService.LogException(ErrorMsg, e, "TeamStatusController", "GetSavingsByDay")
        return jsonify({"Success": False, "ErrorMessage": ErrorMsg}), 500


@TeamStatusBlueprint.route('/Workers', methods=['GET'])
def GetWorkers():
    """Get all registered workers with status and heartbeat info."""
    try:
        LoggingService.LogFunctionEntry("GetWorkers", "TeamStatusController")

        DbManager = DatabaseManager()

        IncludeDisabled = request.args.get('IncludeDisabled', 'false').lower() == 'true'
        Query = """
            SELECT WorkerName, Platform, Status, LastHeartbeat,
                   MaxConcurrentJobs, MaxCpuThreads, AcceptsInterlaced,
                   TranscodeEnabled, QualityTestEnabled, ScanEnabled, RemuxEnabled,
                   MaxConcurrentTranscodeJobs, MaxConcurrentQualityTestJobs, MaxConcurrentRemuxJobs,
                   Enabled,
                   Version, BuildInfo,
                   MountValidationError,
                   EXTRACT(EPOCH FROM (NOW() - LastHeartbeat)) AS HeartbeatAgeSec
            FROM Workers
            {where}
            ORDER BY WorkerName
        """.format(where='' if IncludeDisabled else 'WHERE Enabled = TRUE')
        Rows = DbManager.DatabaseService.ExecuteQuery(Query)

        # Directive 2026-05-27 criterion 20: per-worker scan posture for the
        # /Activity worker-tile "Scan:" line. One round-trip across all workers
        # (no per-worker DB query in the loop).
        ScanPostureRows = DbManager.DatabaseService.ExecuteQuery(
            """
            SELECT WorkerName,
                   MAX(EndTime) FILTER (WHERE Status='Completed') AS LastScanCompleted,
                   MAX(RootFolderPath) FILTER (WHERE Status='Running') AS CurrentScanRootFolder
            FROM ScanJobs
            WHERE WorkerName IS NOT NULL
            GROUP BY WorkerName
            """
        ) or []
        ScanPostureByWorker = {
            (R.get('WorkerName') or ''): {
                'LastScanCompleted': R.get('LastScanCompleted'),
                'CurrentScanRootFolder': R.get('CurrentScanRootFolder'),
            } for R in ScanPostureRows
        }
        IntervalMin = _GetContinuousScanIntervalMinutes()

        Workers = []
        for Row in (Rows or []):
            HeartbeatAge = Row.get('HeartbeatAgeSec')
            IsAlive = HeartbeatAge is not None and HeartbeatAge < 300
            WorkerName = Row.get('WorkerName', '') or ''
            ScanPosture = ScanPostureByWorker.get(WorkerName, {})
            LastScanCompleted = ScanPosture.get('LastScanCompleted')
            ScanEnabled = bool(Row.get('ScanEnabled', False))
            # NextScanEstimate is null when the worker can't scan; otherwise
            # LastScanCompleted + ContinuousScanIntervalMinutes. If a worker
            # has no prior scan, the UI renders "imminent" -- not our concern.
            NextScanEstimate = None
            if ScanEnabled and LastScanCompleted is not None:
                from datetime import timedelta
                NextScanEstimate = LastScanCompleted + timedelta(minutes=IntervalMin)
            Workers.append({
                "WorkerName": WorkerName,
                "Platform": Row.get('Platform', ''),
                "Status": Row.get('Status', 'Paused'),
                "IsAlive": IsAlive,
                "LastHeartbeat": str(Row.get('LastHeartbeat', '')) if Row.get('LastHeartbeat') else '',
                "HeartbeatAgeSec": HeartbeatAge,
                "MaxConcurrentJobs": Row.get('MaxConcurrentJobs', 0),
                "MaxCpuThreads": Row.get('MaxCpuThreads'),
                "AcceptsInterlaced": bool(Row.get('AcceptsInterlaced', True)),
                "TranscodeEnabled": bool(Row.get('TranscodeEnabled', True)),
                "QualityTestEnabled": bool(Row.get('QualityTestEnabled', False)),
                "ScanEnabled": ScanEnabled,
                "RemuxEnabled": bool(Row.get('RemuxEnabled', True)),
                "MaxConcurrentTranscodeJobs": Row.get('MaxConcurrentTranscodeJobs') or 1,
                "MaxConcurrentQualityTestJobs": Row.get('MaxConcurrentQualityTestJobs') or 2,
                "MaxConcurrentRemuxJobs": Row.get('MaxConcurrentRemuxJobs') or 2,
                "Enabled": bool(Row.get('Enabled', True)),
                "Version": Row.get('Version'),
                "BuildInfo": Row.get('BuildInfo'),
                "MountValidationError": Row.get('MountValidationError'),
                "LastScanCompleted": str(LastScanCompleted) if LastScanCompleted else None,
                "NextScanEstimate": str(NextScanEstimate) if NextScanEstimate else None,
                "CurrentScanRootFolder": ScanPosture.get('CurrentScanRootFolder'),
            })

        return jsonify({"Success": True, "Data": Workers})

    except Exception as e:
        ErrorMsg = f"Exception in GetWorkers: {str(e)}"
        LoggingService.LogException(ErrorMsg, e, "TeamStatusController", "GetWorkers")
        return jsonify({"Success": False, "ErrorMessage": ErrorMsg}), 500

@TeamStatusBlueprint.route('/Workers/VersionStatus', methods=['GET'])
def GetWorkersVersionStatus():
    """Aggregate worker versions for fleet-wide mismatch detection.
    Single round-trip so the Activity page banner doesn't need client-side grouping.

    Response shape:
        {"AllAgree": bool,
         "Versions": {"<sha-or-unknown>": ["<workerName>", ...]},
         "MismatchCount": int}
    AllAgree is True iff all enabled workers report the SAME non-"unknown"
    version. Workers reporting "unknown" do not trigger the mismatch flag
    (an unknown worker is its own problem, not evidence of a split fleet).
    """
    try:
        DbManager = DatabaseManager()
        Rows = DbManager.DatabaseService.ExecuteQuery(
            "SELECT WorkerName, Version FROM Workers WHERE Enabled = TRUE ORDER BY WorkerName"
        )
        Versions = {}
        for Row in (Rows or []):
            Sha = Row.get('Version') or 'unknown'
            Versions.setdefault(Sha, []).append(Row.get('WorkerName', ''))

        KnownVersions = [V for V in Versions.keys() if V != 'unknown']
        AllAgree = len(KnownVersions) <= 1
        MismatchCount = max(0, len(KnownVersions) - 1)

        return jsonify({
            "Success": True,
            "Data": {
                "AllAgree": AllAgree,
                "Versions": Versions,
                "MismatchCount": MismatchCount,
            },
        })
    except Exception as e:
        ErrorMsg = f"Exception in GetWorkersVersionStatus: {str(e)}"
        LoggingService.LogException(ErrorMsg, e, "TeamStatusController", "GetWorkersVersionStatus")
        return jsonify({"Success": False, "ErrorMessage": ErrorMsg}), 500


@TeamStatusBlueprint.route('/Workers/<WorkerName>/Enable', methods=['POST'])
def EnableWorker(WorkerName):
    """Re-enable a disabled worker so it appears in the UI again."""
    try:
        LoggingService.LogFunctionEntry("EnableWorker", "TeamStatusController")
        DbManager = DatabaseManager()
        Rows = DbManager.DatabaseService.ExecuteQuery("SELECT 1 FROM Workers WHERE WorkerName = %s", (WorkerName,))
        if not Rows:
            return jsonify({"Success": False, "Message": f"Worker '{WorkerName}' not found"}), 404
        DbManager.DatabaseService.ExecuteNonQuery("UPDATE Workers SET Enabled = TRUE WHERE WorkerName = %s", (WorkerName,))
        LoggingService.LogInfo(f"Worker '{WorkerName}' enabled", "TeamStatusController", "EnableWorker")
        return jsonify({"Success": True, "Message": f"Worker '{WorkerName}' enabled"})
    except Exception as e:
        ErrorMsg = f"Exception in EnableWorker: {str(e)}"
        LoggingService.LogException(ErrorMsg, e, "TeamStatusController", "EnableWorker")
        return jsonify({"Success": False, "ErrorMessage": ErrorMsg}), 500


@TeamStatusBlueprint.route('/Workers/<WorkerName>/Disable', methods=['POST'])
def DisableWorker(WorkerName):
    """Disable a worker -- hides it from the UI and sets status to Paused."""
    try:
        LoggingService.LogFunctionEntry("DisableWorker", "TeamStatusController")
        DbManager = DatabaseManager()
        Rows = DbManager.DatabaseService.ExecuteQuery("SELECT 1 FROM Workers WHERE WorkerName = %s", (WorkerName,))
        if not Rows:
            return jsonify({"Success": False, "Message": f"Worker '{WorkerName}' not found"}), 404
        DbManager.DatabaseService.ExecuteNonQuery(
            "UPDATE Workers SET Enabled = FALSE, Status = 'Paused' WHERE WorkerName = %s", (WorkerName,)
        )
        LoggingService.LogInfo(f"Worker '{WorkerName}' disabled", "TeamStatusController", "DisableWorker")
        return jsonify({"Success": True, "Message": f"Worker '{WorkerName}' disabled"})
    except Exception as e:
        ErrorMsg = f"Exception in DisableWorker: {str(e)}"
        LoggingService.LogException(ErrorMsg, e, "TeamStatusController", "DisableWorker")
        return jsonify({"Success": False, "ErrorMessage": ErrorMsg}), 500

@TeamStatusBlueprint.route('/ResetStuckJob', methods=['POST'])
def ResetStuckJob():
    """Reset a stuck queue item back to Pending."""
    try:
        LoggingService.LogFunctionEntry("ResetStuckJob", "TeamStatusController")

        Data = request.get_json()
        QueueId = Data.get('QueueId') if Data else None
        if not QueueId:
            return jsonify({"Success": False, "ErrorMessage": "QueueId is required"}), 400

        DbManager = DatabaseManager()

        # Reset the queue item to Pending
        ResetQuery = """
            UPDATE TranscodeQueue
            SET Status = 'Pending', ClaimedBy = NULL, ClaimedAt = NULL, DateStarted = NULL
            WHERE Id = %s AND Status = 'Running'
        """
        RowsAffected = DbManager.DatabaseService.ExecuteNonQuery(ResetQuery, (QueueId,))

        if RowsAffected == 0:
            return jsonify({"Success": False, "ErrorMessage": f"Queue item {QueueId} not found or not in Running state"}), 404

        # Clean up ActiveJobs for this queue item
        CleanupQuery = """
            DELETE FROM ActiveJobs WHERE QueueId = %s
        """
        DbManager.DatabaseService.ExecuteNonQuery(CleanupQuery, (QueueId,))

        # Clean up TranscodeProgress for incomplete attempts on this file
        ProgressCleanupQuery = """
            DELETE FROM TranscodeProgress
            WHERE TranscodeAttemptId IN (
                SELECT ta.Id FROM TranscodeAttempts ta
                JOIN TranscodeQueue tq ON ta.MediaFileId = tq.MediaFileId
                WHERE tq.Id = %s AND ta.Success IS NULL
            )
        """
        DbManager.DatabaseService.ExecuteNonQuery(ProgressCleanupQuery, (QueueId,))

        LoggingService.LogInfo(f"Reset stuck job QueueId={QueueId} to Pending", "TeamStatusController", "ResetStuckJob")

        return jsonify({"Success": True, "Message": f"Queue item {QueueId} reset to Pending"})

    except Exception as e:
        ErrorMsg = f"Exception in ResetStuckJob: {str(e)}"
        LoggingService.LogException(ErrorMsg, e, "TeamStatusController", "ResetStuckJob")
        return jsonify({"Success": False, "ErrorMessage": ErrorMsg}), 500


@TeamStatusBlueprint.route('/Workers/<WorkerName>/Capability', methods=['POST'])
def SetWorkerCapability(WorkerName):
    """Set per-worker capability flags (TranscodeEnabled, QualityTestEnabled, ScanEnabled).

    Body: {"TranscodeEnabled": true, "QualityTestEnabled": false, ...}
    Any subset of the three keys is accepted; unspecified columns are left untouched.
    Values must be true / false / null. null on QualityTestEnabled means "use the
    SystemSettings.QualityTestEnabled global default" -- see WorkerService.feature.md.

    The worker's _CapabilityPollingLoop reads the new value within 60s and starts
    or stops the corresponding capability without restarting the worker process.
    """
    try:
        LoggingService.LogFunctionEntry("SetWorkerCapability", "TeamStatusController")

        Data = request.get_json() or {}
        AllowedColumns = {'TranscodeEnabled', 'QualityTestEnabled', 'ScanEnabled', 'RemuxEnabled'}
        UpdateColumns = {k: v for k, v in Data.items() if k in AllowedColumns}
        if not UpdateColumns:
            return jsonify({"Success": False, "Message": f"Provide at least one of: {', '.join(sorted(AllowedColumns))}"}), 400

        # Validate value types: bool or None
        for Key, Val in UpdateColumns.items():
            if Val is not None and not isinstance(Val, bool):
                return jsonify({"Success": False, "Message": f"{Key} must be true, false, or null"}), 400

        DbManager = DatabaseManager()
        CheckRows = DbManager.DatabaseService.ExecuteQuery("SELECT 1 FROM Workers WHERE WorkerName = %s", (WorkerName,))
        if not CheckRows:
            return jsonify({"Success": False, "Message": f"Worker '{WorkerName}' not found"}), 404

        SetClauses = ", ".join(f"{Col} = %s" for Col in UpdateColumns.keys())
        Params = tuple(UpdateColumns.values()) + (WorkerName,)
        UpdateQuery = f"UPDATE Workers SET {SetClauses} WHERE WorkerName = %s"
        DbManager.DatabaseService.ExecuteNonQuery(UpdateQuery, Params)

        LoggingService.LogInfo(
            f"Worker '{WorkerName}' capabilities updated: {UpdateColumns}",
            "TeamStatusController", "SetWorkerCapability"
        )

        # Return the updated row so the UI can reflect the new state immediately
        # without re-fetching the whole worker list.
        FreshRows = DbManager.DatabaseService.ExecuteQuery(
            "SELECT WorkerName, TranscodeEnabled, QualityTestEnabled, ScanEnabled, RemuxEnabled FROM Workers WHERE WorkerName = %s",
            (WorkerName,)
        )
        Fresh = FreshRows[0] if FreshRows else {}
        return jsonify({
            "Success": True,
            "Message": f"Worker '{WorkerName}' capabilities updated",
            "Updated": UpdateColumns,
            "Worker": {
                "WorkerName": Fresh.get('WorkerName'),
                "TranscodeEnabled": bool(Fresh.get('TranscodeEnabled')) if Fresh.get('TranscodeEnabled') is not None else None,
                "QualityTestEnabled": bool(Fresh.get('QualityTestEnabled')) if Fresh.get('QualityTestEnabled') is not None else None,
                "ScanEnabled": bool(Fresh.get('ScanEnabled')) if Fresh.get('ScanEnabled') is not None else None,
                "RemuxEnabled": bool(Fresh.get('RemuxEnabled')) if Fresh.get('RemuxEnabled') is not None else None,
            }
        })

    except Exception as e:
        ErrorMsg = f"Exception in SetWorkerCapability: {str(e)}"
        LoggingService.LogException(ErrorMsg, e, "TeamStatusController", "SetWorkerCapability")
        return jsonify({"Success": False, "ErrorMessage": ErrorMsg}), 500


@TeamStatusBlueprint.route('/Workers/<WorkerName>/Concurrency', methods=['POST'])
def SetWorkerConcurrency(WorkerName):
    """Set per-capability concurrency limits for a worker.

    Body: {"MaxConcurrentTranscodeJobs": 1, "MaxConcurrentQualityTestJobs": 3, ...}
    Any subset of the three keys is accepted; unspecified columns are left untouched.
    Values must be positive integers (floor of 1, no upper ceiling -- see
    worker-lifecycle.feature.md criterion 18).
    Takes effect within one CapabilityPollingIntervalSec on the running worker
    (criterion 19) -- no restart required.
    """
    try:
        LoggingService.LogFunctionEntry("SetWorkerConcurrency", "TeamStatusController")

        Data = request.get_json() or {}
        AllowedColumns = {'MaxConcurrentTranscodeJobs', 'MaxConcurrentQualityTestJobs', 'MaxConcurrentRemuxJobs'}
        UpdateColumns = {k: v for k, v in Data.items() if k in AllowedColumns}
        if not UpdateColumns:
            return jsonify({"Success": False, "Message": f"Provide at least one of: {', '.join(sorted(AllowedColumns))}"}), 400

        # Validate value types and range
        for Key, Val in UpdateColumns.items():
            if not isinstance(Val, int) or Val < 1:
                return jsonify({"Success": False, "Message": f"{Key} must be a positive integer"}), 400

        DbManager = DatabaseManager()
        CheckRows = DbManager.DatabaseService.ExecuteQuery("SELECT 1 FROM Workers WHERE WorkerName = %s", (WorkerName,))
        if not CheckRows:
            return jsonify({"Success": False, "Message": f"Worker '{WorkerName}' not found"}), 404

        SetClauses = ", ".join(f"{Col} = %s" for Col in UpdateColumns.keys())
        Params = tuple(UpdateColumns.values()) + (WorkerName,)
        UpdateQuery = f"UPDATE Workers SET {SetClauses} WHERE WorkerName = %s"
        DbManager.DatabaseService.ExecuteNonQuery(UpdateQuery, Params)

        LoggingService.LogInfo(
            f"Worker '{WorkerName}' concurrency updated: {UpdateColumns}",
            "TeamStatusController", "SetWorkerConcurrency"
        )

        return jsonify({
            "Success": True,
            "Message": f"Worker '{WorkerName}' concurrency updated. Applies within one polling interval.",
            "Updated": UpdateColumns
        })

    except Exception as e:
        ErrorMsg = f"Exception in SetWorkerConcurrency: {str(e)}"
        LoggingService.LogException(ErrorMsg, e, "TeamStatusController", "SetWorkerConcurrency")
        return jsonify({"Success": False, "ErrorMessage": ErrorMsg}), 500


@TeamStatusBlueprint.route('/Workers/<WorkerName>/Status', methods=['POST'])
def SetWorkerStatus(WorkerName):
    """Set per-worker status (Online or Paused)."""
    try:
        LoggingService.LogFunctionEntry("SetWorkerStatus", "TeamStatusController")

        Data = request.get_json()
        if not Data or 'Status' not in Data:
            return jsonify({"Success": False, "Message": "Status is required"}), 400

        NewStatus = Data['Status']
        ValidStatuses = ('Online', 'Paused')
        if NewStatus not in ValidStatuses:
            return jsonify({"Success": False, "Message": f"Status must be one of: {', '.join(ValidStatuses)}"}), 400

        DbManager = DatabaseManager()

        # Verify worker exists
        CheckQuery = "SELECT 1 FROM Workers WHERE WorkerName = %s"
        Rows = DbManager.DatabaseService.ExecuteQuery(CheckQuery, (WorkerName,))
        if not Rows:
            return jsonify({"Success": False, "Message": f"Worker '{WorkerName}' not found"}), 404

        # Update worker status
        UpdateQuery = "UPDATE Workers SET Status = %s WHERE WorkerName = %s"
        DbManager.DatabaseService.ExecuteNonQuery(UpdateQuery, (NewStatus, WorkerName))

        LoggingService.LogInfo(f"Worker '{WorkerName}' status set to {NewStatus}", "TeamStatusController", "SetWorkerStatus")

        return jsonify({"Success": True, "Message": f"Worker '{WorkerName}' status set to {NewStatus}"})

    except Exception as e:
        ErrorMsg = f"Exception in SetWorkerStatus: {str(e)}"
        LoggingService.LogException(ErrorMsg, e, "TeamStatusController", "SetWorkerStatus")
        return jsonify({"Success": False, "ErrorMessage": ErrorMsg}), 500
