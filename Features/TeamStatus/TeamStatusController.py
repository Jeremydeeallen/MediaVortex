"""
TeamStatus Controller
API endpoints for transcode savings and status overview.
"""

from flask import Blueprint, request, jsonify
from Repositories.DatabaseManager import DatabaseManager
from Services.LoggingService import LoggingService

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

        # Current job info — fetch from Progress endpoint data
        CurrentJob = None
        if IsProcessing:
            JobQuery = """
                SELECT ta.FilePath, tp.ProgressPercent, tp.CurrentPhase,
                       tp.CurrentFPS, tp.CurrentSpeed
                FROM TranscodeProgress tp
                JOIN TranscodeAttempts ta ON tp.TranscodeAttemptId = ta.Id
                WHERE tp.Status = 'Running'
                ORDER BY tp.LastProgressUpdate DESC
                LIMIT 1
            """
            JobRows = DbManager.DatabaseService.ExecuteQuery(JobQuery)
            if JobRows:
                CurrentJob = {
                    "FilePath": JobRows[0].get('FilePath', ''),
                    "ProgressPercent": JobRows[0].get('ProgressPercent', 0),
                    "CurrentPhase": JobRows[0].get('CurrentPhase', ''),
                    "CurrentFPS": JobRows[0].get('CurrentFPS', 0),
                    "CurrentSpeed": JobRows[0].get('CurrentSpeed', '')
                }

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
                "CurrentJob": CurrentJob
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

        Query = f"""
            SELECT DATE(ta.CompletedDate) AS Day, COUNT(*) AS JobCount,
                   SUM(ta.SizeReductionBytes) AS TotalSavedBytes,
                   SUM(ta.OldSizeBytes) AS TotalOriginalBytes,
                   SUM(ta.NewSizeBytes) AS TotalNewBytes
            FROM TranscodeAttempts ta
            WHERE ta.Success = TRUE AND ta.SizeReductionBytes > 0
              AND ta.CompletedDate >= CURRENT_DATE - {Days} * INTERVAL '1 day'
            GROUP BY DATE(ta.CompletedDate)
            ORDER BY Day ASC
        """
        Rows = DbManager.DatabaseService.ExecuteQuery(Query)

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
