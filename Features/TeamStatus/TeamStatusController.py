"""
TeamStatus Controller
API endpoints for transcode savings and status overview.
"""

from flask import Blueprint, request, jsonify
from Repositories.DatabaseManager import DatabaseManager
from Services.LoggingService import LoggingService
from Features.SystemSettings.SystemSettingsRepository import SystemSettingsRepository


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

        # Summary stats from successful transcode attempts
        StatsQuery = """
            SELECT COUNT(*) AS JobCount,
                   COALESCE(SUM(ta.OldSizeBytes), 0) AS TotalOriginalBytes,
                   COALESCE(SUM(ta.NewSizeBytes), 0) AS TotalNewBytes,
                   COALESCE(SUM(ta.SizeReductionBytes), 0) AS TotalSavedBytes
            FROM TranscodeAttempts ta
            WHERE ta.Success = TRUE AND ta.SizeReductionBytes > 0
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
                "ActiveJobs": ActiveJobs
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

        Query = """
            SELECT UPPER(LEFT(ta.FilePath, 3)) AS Volume,
                   COUNT(*) AS JobCount,
                   SUM(ta.OldSizeBytes) AS TotalOriginalBytes,
                   SUM(ta.NewSizeBytes) AS TotalNewBytes,
                   SUM(ta.SizeReductionBytes) AS TotalSavedBytes
            FROM TranscodeAttempts ta
            WHERE ta.Success = TRUE AND ta.SizeReductionBytes > 0
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
        Query = f"""
            SELECT DATE(ta.CompletedDate AT TIME ZONE 'UTC' AT TIME ZONE %s) AS Day,
                   COUNT(*) AS JobCount,
                   SUM(ta.SizeReductionBytes) AS TotalSavedBytes,
                   SUM(ta.OldSizeBytes) AS TotalOriginalBytes,
                   SUM(ta.NewSizeBytes) AS TotalNewBytes
            FROM TranscodeAttempts ta
            WHERE ta.Success = TRUE AND ta.SizeReductionBytes > 0
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

        Query = """
            SELECT WorkerName, Platform, Status, LastHeartbeat,
                   MaxConcurrentJobs, MaxCpuThreads, AcceptsInterlaced,
                   TranscodeEnabled, QualityTestEnabled, ScanEnabled,
                   EXTRACT(EPOCH FROM (NOW() - LastHeartbeat)) AS HeartbeatAgeSec
            FROM Workers
            ORDER BY WorkerName
        """
        Rows = DbManager.DatabaseService.ExecuteQuery(Query)

        Workers = []
        for Row in (Rows or []):
            HeartbeatAge = Row.get('HeartbeatAgeSec')
            IsOnline = HeartbeatAge is not None and HeartbeatAge < 300
            Workers.append({
                "WorkerName": Row.get('WorkerName', ''),
                "Platform": Row.get('Platform', ''),
                "Status": 'Online' if IsOnline else 'Offline',
                "LastHeartbeat": str(Row.get('LastHeartbeat', '')) if Row.get('LastHeartbeat') else '',
                "HeartbeatAgeSec": HeartbeatAge,
                "MaxConcurrentJobs": Row.get('MaxConcurrentJobs', 0),
                "MaxCpuThreads": Row.get('MaxCpuThreads'),
                "AcceptsInterlaced": bool(Row.get('AcceptsInterlaced', True)),
                "TranscodeEnabled": bool(Row.get('TranscodeEnabled', True)),
                "QualityTestEnabled": bool(Row.get('QualityTestEnabled', False)),
                "ScanEnabled": bool(Row.get('ScanEnabled', False))
            })

        return jsonify({"Success": True, "Data": Workers})

    except Exception as e:
        ErrorMsg = f"Exception in GetWorkers: {str(e)}"
        LoggingService.LogException(ErrorMsg, e, "TeamStatusController", "GetWorkers")
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
        AllowedColumns = {'TranscodeEnabled', 'QualityTestEnabled', 'ScanEnabled'}
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
            "SELECT WorkerName, TranscodeEnabled, QualityTestEnabled, ScanEnabled FROM Workers WHERE WorkerName = %s",
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
            }
        })

    except Exception as e:
        ErrorMsg = f"Exception in SetWorkerCapability: {str(e)}"
        LoggingService.LogException(ErrorMsg, e, "TeamStatusController", "SetWorkerCapability")
        return jsonify({"Success": False, "ErrorMessage": ErrorMsg}), 500


@TeamStatusBlueprint.route('/Workers/<WorkerName>/Status', methods=['POST'])
def SetWorkerStatus(WorkerName):
    """Set per-worker status (Online, Draining, Offline)."""
    try:
        LoggingService.LogFunctionEntry("SetWorkerStatus", "TeamStatusController")

        Data = request.get_json()
        if not Data or 'Status' not in Data:
            return jsonify({"Success": False, "Message": "Status is required"}), 400

        NewStatus = Data['Status']
        ValidStatuses = ('Online', 'Draining', 'Offline')
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
