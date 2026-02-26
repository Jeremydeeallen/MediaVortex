"""
Failure Tracking Controller
Handles API endpoints for tracking and retrieving service failures
"""

from flask import Blueprint, request, jsonify
from typing import Dict, Any, List
from Repositories.DatabaseManager import DatabaseManager
from Core.Logging.LoggingService import LoggingService

# Create blueprint
FailureTrackingBlueprint = Blueprint('FailureTracking', __name__)

# Shared database manager
SharedDatabaseManager = DatabaseManager()

@FailureTrackingBlueprint.route('/RecentFailures', methods=['GET'])
def GetRecentFailures():
    """Get recent failures from all services."""
    try:
        LoggingService.LogFunctionEntry("GetRecentFailures", "FailureTrackingController")

        # Get query parameters
        Limit = int(request.args.get('limit', 50))
        ServiceType = request.args.get('serviceType', '')  # 'Transcode' or 'Quality' or empty for all

        if Limit < 1 or Limit > 200:
            Limit = 50

        # Get transcode failures
        TranscodeFailures = []
        if not ServiceType or ServiceType == 'Transcode':
            TranscodeQuery = """
            SELECT
                'Transcode' as ServiceType,
                Id as FailureId,
                FilePath as FileName,
                AttemptDate as FailureDate,
                ErrorMessage as FailureReason,
                ProfileName as ServiceName,
                'Transcode Job Failed' as FailureType,
                TranscodeDurationSeconds as Duration
            FROM TranscodeAttempts
            WHERE Success = FALSE AND ErrorMessage IS NOT NULL AND ErrorMessage != ''
            ORDER BY AttemptDate DESC
            LIMIT %s
            """
            TranscodeResults = SharedDatabaseManager.DatabaseService.ExecuteQuery(TranscodeQuery, (Limit,))

            for row in TranscodeResults:
                TranscodeFailures.append({
                    "ServiceType": row['ServiceType'],
                    "FailureId": row['FailureId'],
                    "FileName": row['FileName'],
                    "FailureDate": str(row['FailureDate']) if row['FailureDate'] else None,
                    "FailureReason": row['FailureReason'],
                    "ServiceName": row['ServiceName'],
                    "FailureType": row['FailureType'],
                    "Duration": row['Duration']
                })

        # Get quality testing failures from QualityTestResults table
        QualityFailures = []
        if not ServiceType or ServiceType == 'Quality':
            QualityQuery = """
            SELECT
                'Quality' as ServiceType,
                qtr.Id as FailureId,
                ta.FilePath as FileName,
                qtr.DateTested as FailureDate,
                qtr.ErrorMessage as FailureReason,
                ta.ProfileName as ServiceName,
                'Quality Test Failed' as FailureType,
                qtr.TestDuration as Duration
            FROM QualityTestResults qtr
            LEFT JOIN TranscodeAttempts ta ON qtr.TranscodeAttemptId = ta.Id
            WHERE qtr.Status = 'Failed' AND qtr.ErrorMessage IS NOT NULL AND qtr.ErrorMessage != ''
            ORDER BY qtr.DateTested DESC
            LIMIT %s
            """
            QualityResults = SharedDatabaseManager.DatabaseService.ExecuteQuery(QualityQuery, (Limit,))

            for row in QualityResults:
                QualityFailures.append({
                    "ServiceType": row['ServiceType'],
                    "FailureId": row['FailureId'],
                    "FileName": row['FileName'],
                    "FailureDate": str(row['FailureDate']) if row['FailureDate'] else None,
                    "FailureReason": row['FailureReason'],
                    "ServiceName": row['ServiceName'],
                    "FailureType": row['FailureType'],
                    "Duration": row['Duration']
                })

        # Combine and sort all failures
        AllFailures = TranscodeFailures + QualityFailures
        AllFailures.sort(key=lambda x: x['FailureDate'] or '', reverse=True)

        # Limit combined results
        AllFailures = AllFailures[:Limit]

        LoggingService.LogInfo(f"Retrieved {len(AllFailures)} recent failures", "FailureTrackingController", "GetRecentFailures")

        return jsonify({
            "Success": True,
            "Failures": AllFailures,
            "Count": len(AllFailures),
            "TranscodeCount": len(TranscodeFailures),
            "QualityCount": len(QualityFailures)
        })

    except Exception as e:
        error_msg = f"Exception getting recent failures: {str(e)}"
        LoggingService.LogException(error_msg, e, "FailureTrackingController", "GetRecentFailures")
        return jsonify({"Success": False, "ErrorMessage": error_msg}), 500

@FailureTrackingBlueprint.route('/FailureStats', methods=['GET'])
def GetFailureStats():
    """Get failure statistics by service."""
    try:
        LoggingService.LogFunctionEntry("GetFailureStats", "FailureTrackingController")

        # Get transcode failure stats
        TranscodeStatsQuery = """
        SELECT
            COUNT(*) as TotalFailures,
            COUNT(CASE WHEN AttemptDate >= NOW() - INTERVAL '24 hours' THEN 1 END) as Last24Hours,
            COUNT(CASE WHEN AttemptDate >= NOW() - INTERVAL '7 days' THEN 1 END) as Last7Days,
            COUNT(CASE WHEN AttemptDate >= NOW() - INTERVAL '30 days' THEN 1 END) as Last30Days
        FROM TranscodeAttempts
        WHERE Success = FALSE AND ErrorMessage IS NOT NULL AND ErrorMessage != ''
        """
        TranscodeStats = SharedDatabaseManager.DatabaseService.ExecuteQuery(TranscodeStatsQuery)[0]

        # Get quality testing failure stats from QualityTestResults
        QualityStatsQuery = """
        SELECT
            COUNT(*) as TotalFailures,
            COUNT(CASE WHEN DateTested >= NOW() - INTERVAL '24 hours' THEN 1 END) as Last24Hours,
            COUNT(CASE WHEN DateTested >= NOW() - INTERVAL '7 days' THEN 1 END) as Last7Days,
            COUNT(CASE WHEN DateTested >= NOW() - INTERVAL '30 days' THEN 1 END) as Last30Days
        FROM QualityTestResults
        WHERE Status = 'Failed' AND ErrorMessage IS NOT NULL AND ErrorMessage != ''
        """
        QualityStats = SharedDatabaseManager.DatabaseService.ExecuteQuery(QualityStatsQuery)[0]

        # Get most common failure reasons
        CommonReasonsQuery = """
        SELECT ErrorMessage, COUNT(*) as Count
        FROM (
            SELECT ErrorMessage FROM TranscodeAttempts WHERE Success = FALSE AND ErrorMessage IS NOT NULL AND ErrorMessage != ''
            UNION ALL
            SELECT ErrorMessage FROM QualityTestResults WHERE Status = 'Failed' AND ErrorMessage IS NOT NULL AND ErrorMessage != ''
        ) AS error_source
        GROUP BY ErrorMessage
        ORDER BY Count DESC
        LIMIT 10
        """
        CommonReasons = SharedDatabaseManager.DatabaseService.ExecuteQuery(CommonReasonsQuery)

        Stats = {
            "TranscodeService": {
                "TotalFailures": TranscodeStats['TotalFailures'],
                "Last24Hours": TranscodeStats['Last24Hours'],
                "Last7Days": TranscodeStats['Last7Days'],
                "Last30Days": TranscodeStats['Last30Days']
            },
            "QualityCompareService": {
                "TotalFailures": QualityStats['TotalFailures'],
                "Last24Hours": QualityStats['Last24Hours'],
                "Last7Days": QualityStats['Last7Days'],
                "Last30Days": QualityStats['Last30Days']
            },
            "CommonFailureReasons": [
                {"Reason": row['ErrorMessage'], "Count": row['Count']} for row in CommonReasons
            ]
        }

        LoggingService.LogInfo("Retrieved failure statistics", "FailureTrackingController", "GetFailureStats")

        return jsonify({
            "Success": True,
            "Stats": Stats
        })

    except Exception as e:
        error_msg = f"Exception getting failure stats: {str(e)}"
        LoggingService.LogException(error_msg, e, "FailureTrackingController", "GetFailureStats")
        return jsonify({"Success": False, "ErrorMessage": error_msg}), 500

@FailureTrackingBlueprint.route('/ServiceFailures/<service_name>', methods=['GET'])
def GetServiceFailures(service_name: str):
    """Get failures for a specific service."""
    try:
        LoggingService.LogFunctionEntry(f"GetServiceFailures({service_name})", "FailureTrackingController")

        # Get query parameters
        Limit = int(request.args.get('limit', 25))
        if Limit < 1 or Limit > 100:
            Limit = 25

        Failures = []

        if service_name.lower() == 'transcode':
            Query = """
            SELECT
                Id as FailureId,
                FilePath as FileName,
                AttemptDate as FailureDate,
                ErrorMessage as FailureReason,
                ProfileName as ServiceName,
                TranscodeDurationSeconds as Duration
            FROM TranscodeAttempts
            WHERE Success = FALSE AND ErrorMessage IS NOT NULL AND ErrorMessage != ''
            ORDER BY AttemptDate DESC
            LIMIT %s
            """
            Results = SharedDatabaseManager.DatabaseService.ExecuteQuery(Query, (Limit,))

            for row in Results:
                Failures.append({
                    "FailureId": row['FailureId'],
                    "FileName": row['FileName'],
                    "FailureDate": str(row['FailureDate']) if row['FailureDate'] else None,
                    "FailureReason": row['FailureReason'],
                    "ServiceName": row['ServiceName'],
                    "Duration": row['Duration']
                })

        elif service_name.lower() == 'quality':
            Query = """
            SELECT
                qtr.Id as FailureId,
                ta.FilePath as FileName,
                qtr.DateTested as FailureDate,
                qtr.ErrorMessage as FailureReason,
                ta.ProfileName as ServiceName,
                qtr.TestDuration as Duration
            FROM QualityTestResults qtr
            LEFT JOIN TranscodeAttempts ta ON qtr.TranscodeAttemptId = ta.Id
            WHERE qtr.Status = 'Failed' AND qtr.ErrorMessage IS NOT NULL AND qtr.ErrorMessage != ''
            ORDER BY qtr.DateTested DESC
            LIMIT %s
            """
            Results = SharedDatabaseManager.DatabaseService.ExecuteQuery(Query, (Limit,))

            for row in Results:
                Failures.append({
                    "FailureId": row['FailureId'],
                    "FileName": row['FileName'],
                    "FailureDate": str(row['FailureDate']) if row['FailureDate'] else None,
                    "FailureReason": row['FailureReason'],
                    "ServiceName": row['ServiceName'],
                    "Duration": row['Duration']
                })
        else:
            return jsonify({
                "Success": False,
                "ErrorMessage": f"Unknown service: {service_name}. Use 'transcode' or 'quality'."
            }), 400

        LoggingService.LogInfo(f"Retrieved {len(Failures)} failures for {service_name}", "FailureTrackingController", "GetServiceFailures")

        return jsonify({
            "Success": True,
            "ServiceName": service_name,
            "Failures": Failures,
            "Count": len(Failures)
        })

    except Exception as e:
        error_msg = f"Exception getting failures for {service_name}: {str(e)}"
        LoggingService.LogException(error_msg, e, "FailureTrackingController", "GetServiceFailures")
        return jsonify({"Success": False, "ErrorMessage": error_msg}), 500
