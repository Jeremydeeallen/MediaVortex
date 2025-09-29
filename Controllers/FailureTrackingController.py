"""
Failure Tracking Controller
Handles API endpoints for tracking and retrieving service failures
"""

from flask import Blueprint, request, jsonify
from typing import Dict, Any, List
from Repositories.DatabaseManager import DatabaseManager
from Services.LoggingService import LoggingService

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
            WHERE Success = 0 AND ErrorMessage IS NOT NULL AND ErrorMessage != ''
            ORDER BY AttemptDate DESC
            LIMIT ?
            """
            TranscodeResults = SharedDatabaseManager.DatabaseService.ExecuteQuery(TranscodeQuery, (Limit,))
            
            for row in TranscodeResults:
                TranscodeFailures.append({
                    "ServiceType": row[0],
                    "FailureId": row[1],
                    "FileName": row[2],
                    "FailureDate": row[3],
                    "FailureReason": row[4],
                    "ServiceName": row[5],
                    "FailureType": row[6],
                    "Duration": row[7]
                })
        
        # Get quality testing failures
        QualityFailures = []
        if not ServiceType or ServiceType == 'Quality':
            QualityQuery = """
            SELECT 
                'Quality' as ServiceType,
                Id as FailureId,
                FileName,
                DateCompleted as FailureDate,
                ErrorMessage as FailureReason,
                StrategyType as ServiceName,
                'Quality Test Failed' as FailureType,
                NULL as Duration
            FROM QualityTestingQueue 
            WHERE Status = 'Failed' AND ErrorMessage IS NOT NULL AND ErrorMessage != ''
            ORDER BY DateCompleted DESC
            LIMIT ?
            """
            QualityResults = SharedDatabaseManager.DatabaseService.ExecuteQuery(QualityQuery, (Limit,))
            
            for row in QualityResults:
                QualityFailures.append({
                    "ServiceType": row[0],
                    "FailureId": row[1],
                    "FileName": row[2],
                    "FailureDate": row[3],
                    "FailureReason": row[4],
                    "ServiceName": row[5],
                    "FailureType": row[6],
                    "Duration": row[7]
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
            COUNT(CASE WHEN AttemptDate >= datetime('now', '-24 hours') THEN 1 END) as Last24Hours,
            COUNT(CASE WHEN AttemptDate >= datetime('now', '-7 days') THEN 1 END) as Last7Days,
            COUNT(CASE WHEN AttemptDate >= datetime('now', '-30 days') THEN 1 END) as Last30Days
        FROM TranscodeAttempts 
        WHERE Success = 0 AND ErrorMessage IS NOT NULL AND ErrorMessage != ''
        """
        TranscodeStats = SharedDatabaseManager.DatabaseService.ExecuteQuery(TranscodeStatsQuery)[0]
        
        # Get quality testing failure stats
        QualityStatsQuery = """
        SELECT 
            COUNT(*) as TotalFailures,
            COUNT(CASE WHEN DateCompleted >= datetime('now', '-24 hours') THEN 1 END) as Last24Hours,
            COUNT(CASE WHEN DateCompleted >= datetime('now', '-7 days') THEN 1 END) as Last7Days,
            COUNT(CASE WHEN DateCompleted >= datetime('now', '-30 days') THEN 1 END) as Last30Days
        FROM QualityTestingQueue 
        WHERE Status = 'Failed' AND ErrorMessage IS NOT NULL AND ErrorMessage != ''
        """
        QualityStats = SharedDatabaseManager.DatabaseService.ExecuteQuery(QualityStatsQuery)[0]
        
        # Get most common failure reasons
        CommonReasonsQuery = """
        SELECT ErrorMessage, COUNT(*) as Count
        FROM (
            SELECT ErrorMessage FROM TranscodeAttempts WHERE Success = 0 AND ErrorMessage IS NOT NULL AND ErrorMessage != ''
            UNION ALL
            SELECT ErrorMessage FROM QualityTestingQueue WHERE Status = 'Failed' AND ErrorMessage IS NOT NULL AND ErrorMessage != ''
        )
        GROUP BY ErrorMessage
        ORDER BY Count DESC
        LIMIT 10
        """
        CommonReasons = SharedDatabaseManager.DatabaseService.ExecuteQuery(CommonReasonsQuery)
        
        Stats = {
            "TranscodeService": {
                "TotalFailures": TranscodeStats[0],
                "Last24Hours": TranscodeStats[1],
                "Last7Days": TranscodeStats[2],
                "Last30Days": TranscodeStats[3]
            },
            "QualityCompareService": {
                "TotalFailures": QualityStats[0],
                "Last24Hours": QualityStats[1],
                "Last7Days": QualityStats[2],
                "Last30Days": QualityStats[3]
            },
            "CommonFailureReasons": [
                {"Reason": row[0], "Count": row[1]} for row in CommonReasons
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
            WHERE Success = 0 AND ErrorMessage IS NOT NULL AND ErrorMessage != ''
            ORDER BY AttemptDate DESC
            LIMIT ?
            """
            Results = SharedDatabaseManager.DatabaseService.ExecuteQuery(Query, (Limit,))
            
            for row in Results:
                Failures.append({
                    "FailureId": row[0],
                    "FileName": row[1],
                    "FailureDate": row[2],
                    "FailureReason": row[3],
                    "ServiceName": row[4],
                    "Duration": row[5]
                })
                
        elif service_name.lower() == 'quality':
            Query = """
            SELECT 
                Id as FailureId,
                FileName,
                DateCompleted as FailureDate,
                ErrorMessage as FailureReason,
                StrategyType as ServiceName,
                NULL as Duration
            FROM QualityTestingQueue 
            WHERE Status = 'Failed' AND ErrorMessage IS NOT NULL AND ErrorMessage != ''
            ORDER BY DateCompleted DESC
            LIMIT ?
            """
            Results = SharedDatabaseManager.DatabaseService.ExecuteQuery(Query, (Limit,))
            
            for row in Results:
                Failures.append({
                    "FailureId": row[0],
                    "FileName": row[1],
                    "FailureDate": row[2],
                    "FailureReason": row[3],
                    "ServiceName": row[4],
                    "Duration": row[5]
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
