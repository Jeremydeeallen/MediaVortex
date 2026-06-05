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

        TranscodeFailures = []
        if not ServiceType or ServiceType == 'Transcode':
            # directive: path-schema-migration | # see path.S8
            from Core.Path.Path import Path as _PathT1, PathError as _PET1
            from Core.Path.PathStorageRoots import GetPrefixMap as _GPMT1
            _PmT1 = _GPMT1()
            def _SynthT1(Sid, Rel):
                if Sid is None:
                    return ''
                try:
                    return _PathT1(Sid, Rel or '').CanonicalDisplay(_PmT1)
                except _PET1:
                    return ''
            TranscodeQuery = (
                "SELECT 'Transcode' as ServiceType, Id as FailureId, "
                "StorageRootId AS TaStorageRootId, RelativePath AS TaRelativePath, "
                "AttemptDate as FailureDate, ErrorMessage as FailureReason, "
                "ProfileName as ServiceName, 'Transcode Job Failed' as FailureType, "
                "TranscodeDurationSeconds as Duration "
                "FROM TranscodeAttempts "
                "WHERE Success = FALSE AND ErrorMessage IS NOT NULL AND ErrorMessage != '' "
                "ORDER BY AttemptDate DESC "
                "LIMIT %s"
            )
            TranscodeResults = SharedDatabaseManager.DatabaseService.ExecuteQuery(TranscodeQuery, (Limit,))

            for row in TranscodeResults:
                TranscodeFailures.append({
                    "ServiceType": row['ServiceType'],
                    "FailureId": row['FailureId'],
                    "FileName": _SynthT1(row.get('TaStorageRootId'), row.get('TaRelativePath')),
                    "FailureDate": row['FailureDate'],
                    "FailureReason": row['FailureReason'],
                    "ServiceName": row['ServiceName'],
                    "FailureType": row['FailureType'],
                    "Duration": row['Duration']
                })

        # Get quality testing failures from QualityTestResults table
        QualityFailures = []
        if not ServiceType or ServiceType == 'Quality':
            # directive: path-schema-migration | # see path.S8 -- SELECT typed pair; synthesize display string in Python
            from Core.Path.Path import Path as _PathQ1, PathError as _PEQ1
            from Core.Path.PathStorageRoots import GetPrefixMap as _GPMQ1
            _PmQ1 = _GPMQ1()
            def _SynthQ1(Sid, Rel):
                if Sid is None:
                    return ''
                try:
                    return _PathQ1(Sid, Rel or '').CanonicalDisplay(_PmQ1)
                except _PEQ1:
                    return ''
            QualityQuery = (
                "SELECT 'Quality' as ServiceType, qtr.Id as FailureId, "
                "ta.StorageRootId as TaStorageRootId, ta.RelativePath as TaRelativePath, "
                "qtr.DateTested as FailureDate, qtr.ErrorMessage as FailureReason, "
                "ta.ProfileName as ServiceName, 'Quality Test Failed' as FailureType, "
                "qtr.TestDuration as Duration "
                "FROM QualityTestResults qtr "
                "LEFT JOIN TranscodeAttempts ta ON qtr.TranscodeAttemptId = ta.Id "
                "WHERE qtr.Status = 'Failed' AND qtr.ErrorMessage IS NOT NULL AND qtr.ErrorMessage != '' "
                "ORDER BY qtr.DateTested DESC "
                "LIMIT %s"
            )
            QualityResults = SharedDatabaseManager.DatabaseService.ExecuteQuery(QualityQuery, (Limit,))

            for row in QualityResults:
                QualityFailures.append({
                    "ServiceType": row['ServiceType'],
                    "FailureId": row['FailureId'],
                    "FileName": _SynthQ1(row.get('TaStorageRootId'), row.get('TaRelativePath')),
                    "FailureDate": row['FailureDate'],
                    "FailureReason": row['FailureReason'],
                    "ServiceName": row['ServiceName'],
                    "FailureType": row['FailureType'],
                    "Duration": row['Duration']
                })

        # Combine and sort all failures (FailureDate is a datetime; sort by epoch with NULLs last)
        AllFailures = TranscodeFailures + QualityFailures
        AllFailures.sort(key=lambda x: x['FailureDate'].timestamp() if x['FailureDate'] else 0, reverse=True)

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
            # directive: path-schema-migration | # see path.S8
            from Core.Path.Path import Path as _PathT2, PathError as _PET2
            from Core.Path.PathStorageRoots import GetPrefixMap as _GPMT2
            _PmT2 = _GPMT2()
            def _SynthT2(Sid, Rel):
                if Sid is None:
                    return ''
                try:
                    return _PathT2(Sid, Rel or '').CanonicalDisplay(_PmT2)
                except _PET2:
                    return ''
            Query = (
                "SELECT Id as FailureId, "
                "StorageRootId AS TaStorageRootId, RelativePath AS TaRelativePath, "
                "AttemptDate as FailureDate, ErrorMessage as FailureReason, "
                "ProfileName as ServiceName, TranscodeDurationSeconds as Duration "
                "FROM TranscodeAttempts "
                "WHERE Success = FALSE AND ErrorMessage IS NOT NULL AND ErrorMessage != '' "
                "ORDER BY AttemptDate DESC "
                "LIMIT %s"
            )
            Results = SharedDatabaseManager.DatabaseService.ExecuteQuery(Query, (Limit,))

            for row in Results:
                Failures.append({
                    "FailureId": row['FailureId'],
                    "FileName": _SynthT2(row.get('TaStorageRootId'), row.get('TaRelativePath')),
                    "FailureDate": row['FailureDate'],
                    "FailureReason": row['FailureReason'],
                    "ServiceName": row['ServiceName'],
                    "Duration": row['Duration']
                })

        elif service_name.lower() == 'quality':
            # directive: path-schema-migration | # see path.S8 -- typed-pair SELECT + Python-side display synthesis
            from Core.Path.Path import Path as _PathQ2, PathError as _PEQ2
            from Core.Path.PathStorageRoots import GetPrefixMap as _GPMQ2
            _PmQ2 = _GPMQ2()
            def _SynthQ2(Sid, Rel):
                if Sid is None:
                    return ''
                try:
                    return _PathQ2(Sid, Rel or '').CanonicalDisplay(_PmQ2)
                except _PEQ2:
                    return ''
            Query = (
                "SELECT qtr.Id as FailureId, "
                "ta.StorageRootId as TaStorageRootId, ta.RelativePath as TaRelativePath, "
                "qtr.DateTested as FailureDate, qtr.ErrorMessage as FailureReason, "
                "ta.ProfileName as ServiceName, qtr.TestDuration as Duration "
                "FROM QualityTestResults qtr "
                "LEFT JOIN TranscodeAttempts ta ON qtr.TranscodeAttemptId = ta.Id "
                "WHERE qtr.Status = 'Failed' AND qtr.ErrorMessage IS NOT NULL AND qtr.ErrorMessage != '' "
                "ORDER BY qtr.DateTested DESC "
                "LIMIT %s"
            )
            Results = SharedDatabaseManager.DatabaseService.ExecuteQuery(Query, (Limit,))

            for row in Results:
                Failures.append({
                    "FailureId": row['FailureId'],
                    "FileName": _SynthQ2(row.get('TaStorageRootId'), row.get('TaRelativePath')),
                    "FailureDate": row['FailureDate'],
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
