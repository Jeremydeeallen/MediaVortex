"""
Service Status Controller
Handles monitoring and management of microservices
"""

from flask import Blueprint, jsonify
from typing import Dict, Any, List
from Repositories.DatabaseManager import DatabaseManager
from Services.LoggingService import LoggingService
from Services.SystemMonitoringService import SystemMonitoringServiceInstance

# Create blueprint
ServiceStatusBlueprint = Blueprint('ServiceStatus', __name__)

# Shared database manager
SharedDatabaseManager = DatabaseManager()

@ServiceStatusBlueprint.route('/Status', methods=['GET'])
def GetServiceStatus():
    """Get status of all services."""
    try:
        LoggingService.LogFunctionEntry("GetServiceStatus", "ServiceStatusController")
        
        # Get all service statuses
        query = """
        SELECT ServiceName, Status, HealthStatus, StartTime, LastHealthCheck,
               UptimeSeconds, MemoryUsage, CPUUsage, DatabaseConnection, DiskSpace,
               ErrorCount, MaxErrors, ActiveJobsCount, IsProcessing, LastErrorMessage,
               ProcessId, Version, ServiceType, CreatedAt, UpdatedAt
        FROM ServiceStatus
        ORDER BY ServiceName
        """
        
        results = SharedDatabaseManager.DatabaseService.ExecuteQuery(query)
        
        services = []
        for row in results:
            service = {
                "ServiceName": row[0],
                "Status": row[1],
                "HealthStatus": row[2],
                "StartTime": row[3],
                "LastHealthCheck": row[4],
                "UptimeSeconds": row[5],
                "MemoryUsage": row[6],
                "CPUUsage": row[7],
                "DatabaseConnection": row[8],
                "DiskSpace": row[9],
                "ErrorCount": row[10],
                "MaxErrors": row[11],
                "ActiveJobsCount": row[12],
                "IsProcessing": row[13],
                "LastErrorMessage": row[14],
                "ProcessId": row[15],
                "Version": row[16],
                "ServiceType": row[17],
                "CreatedAt": row[18],
                "UpdatedAt": row[19]
            }
            services.append(service)
        
        LoggingService.LogInfo(f"Retrieved status for {len(services)} services", "ServiceStatusController", "GetServiceStatus")
        
        return jsonify({
            "Success": True,
            "Services": services,
            "Count": len(services)
        })
        
    except Exception as e:
        error_msg = f"Exception getting service status: {str(e)}"
        LoggingService.LogException(error_msg, e, "ServiceStatusController", "GetServiceStatus")
        return jsonify({"Success": False, "ErrorMessage": error_msg}), 500

@ServiceStatusBlueprint.route('/Status/<service_name>', methods=['GET'])
def GetServiceStatusByName(service_name: str):
    """Get status of a specific service."""
    try:
        LoggingService.LogFunctionEntry("GetServiceStatusByName", "ServiceStatusController", service_name)
        
        # Get specific service status
        query = """
        SELECT ServiceName, Status, HealthStatus, StartTime, LastHealthCheck,
               UptimeSeconds, MemoryUsage, CPUUsage, DatabaseConnection, DiskSpace,
               ErrorCount, MaxErrors, ActiveJobsCount, IsProcessing, LastErrorMessage,
               ProcessId, Version, ServiceType, CreatedAt, UpdatedAt
        FROM ServiceStatus
        WHERE ServiceName = ?
        """
        
        results = SharedDatabaseManager.DatabaseService.ExecuteQuery(query, (service_name,))
        
        if not results:
            return jsonify({
                "Success": False,
                "ErrorMessage": f"Service '{service_name}' not found"
            }), 404
        
        row = results[0]
        service = {
            "ServiceName": row[0],
            "Status": row[1],
            "HealthStatus": row[2],
            "StartTime": row[3],
            "LastHealthCheck": row[4],
            "UptimeSeconds": row[5],
            "MemoryUsage": row[6],
            "CPUUsage": row[7],
            "DatabaseConnection": row[8],
            "DiskSpace": row[9],
            "ErrorCount": row[10],
            "MaxErrors": row[11],
            "ActiveJobsCount": row[12],
            "IsProcessing": row[13],
            "LastErrorMessage": row[14],
            "ProcessId": row[15],
            "Version": row[16],
            "ServiceType": row[17],
            "CreatedAt": row[18],
            "UpdatedAt": row[19]
        }
        
        LoggingService.LogInfo(f"Retrieved status for service: {service_name}", "ServiceStatusController", "GetServiceStatusByName")
        
        return jsonify({
            "Success": True,
            "Service": service
        })
        
    except Exception as e:
        error_msg = f"Exception getting service status for {service_name}: {str(e)}"
        LoggingService.LogException(error_msg, e, "ServiceStatusController", "GetServiceStatusByName")
        return jsonify({"Success": False, "ErrorMessage": error_msg}), 500

@ServiceStatusBlueprint.route('/Health', methods=['GET'])
def GetServiceHealth():
    """Get overall health status of all services."""
    try:
        LoggingService.LogFunctionEntry("GetServiceHealth", "ServiceStatusController")
        
        # Get service health summary
        query = """
        SELECT 
            COUNT(*) as TotalServices,
            SUM(CASE WHEN Status = 'Running' THEN 1 ELSE 0 END) as RunningServices,
            SUM(CASE WHEN HealthStatus = 'Healthy' THEN 1 ELSE 0 END) as HealthyServices,
            SUM(CASE WHEN HealthStatus = 'Warning' THEN 1 ELSE 0 END) as WarningServices,
            SUM(CASE WHEN HealthStatus = 'Unhealthy' THEN 1 ELSE 0 END) as UnhealthyServices,
            SUM(CASE WHEN Status = 'Stopped' THEN 1 ELSE 0 END) as StoppedServices,
            SUM(CASE WHEN Status = 'Error' THEN 1 ELSE 0 END) as ErrorServices
        FROM ServiceStatus
        """
        
        results = SharedDatabaseManager.DatabaseService.ExecuteQuery(query)
        row = results[0]
        
        health_summary = {
            "TotalServices": row[0],
            "RunningServices": row[1],
            "HealthyServices": row[2],
            "WarningServices": row[3],
            "UnhealthyServices": row[4],
            "StoppedServices": row[5],
            "ErrorServices": row[6],
            "OverallHealth": "Healthy" if row[4] == 0 and row[6] == 0 else "Warning" if row[3] > 0 else "Unhealthy"
        }
        
        LoggingService.LogInfo(f"Retrieved health summary: {health_summary['OverallHealth']}", "ServiceStatusController", "GetServiceHealth")
        
        return jsonify({
            "Success": True,
            "HealthSummary": health_summary
        })
        
    except Exception as e:
        error_msg = f"Exception getting service health: {str(e)}"
        LoggingService.LogException(error_msg, e, "ServiceStatusController", "GetServiceHealth")
        return jsonify({"Success": False, "ErrorMessage": error_msg}), 500

@ServiceStatusBlueprint.route('/TranscodeService/Status', methods=['GET'])
def GetTranscodeServiceStatus():
    """Get specific status of TranscodeService."""
    try:
        LoggingService.LogFunctionEntry("GetTranscodeServiceStatus", "ServiceStatusController")
        
        # Get TranscodeService status
        query = """
        SELECT ServiceName, Status, HealthStatus, StartTime, LastHealthCheck,
               UptimeSeconds, MemoryUsage, CPUUsage, DatabaseConnection, DiskSpace,
               ErrorCount, MaxErrors, ActiveJobsCount, IsProcessing, LastErrorMessage,
               ProcessId, Version, ServiceType, CreatedAt, UpdatedAt
        FROM ServiceStatus
        WHERE ServiceName = 'TranscodeService'
        """
        
        results = SharedDatabaseManager.DatabaseService.ExecuteQuery(query)
        
        if not results:
            return jsonify({
                "Success": False,
                "ErrorMessage": "TranscodeService not found in ServiceStatus table"
            }), 404
        
        row = results[0]
        service = {
            "ServiceName": row[0],
            "Status": row[1],
            "HealthStatus": row[2],
            "StartTime": row[3],
            "LastHealthCheck": row[4],
            "UptimeSeconds": row[5],
            "MemoryUsage": row[6],
            "CPUUsage": row[7],
            "DatabaseConnection": row[8],
            "DiskSpace": row[9],
            "ErrorCount": row[10],
            "MaxErrors": row[11],
            "ActiveJobsCount": row[12],
            "IsProcessing": row[13],
            "LastErrorMessage": row[14],
            "ProcessId": row[15],
            "Version": row[16],
            "ServiceType": row[17],
            "CreatedAt": row[18],
            "UpdatedAt": row[19]
        }
        
        # Check if service is running
        is_running = service["Status"] == "Running"
        is_healthy = service["HealthStatus"] == "Healthy"
        
        LoggingService.LogInfo(f"TranscodeService status: {service['Status']}, Health: {service['HealthStatus']}", "ServiceStatusController", "GetTranscodeServiceStatus")
        
        return jsonify({
            "Success": True,
            "Service": service,
            "IsRunning": is_running,
            "IsHealthy": is_healthy
        })
        
    except Exception as e:
        error_msg = f"Exception getting TranscodeService status: {str(e)}"
        LoggingService.LogException(error_msg, e, "ServiceStatusController", "GetTranscodeServiceStatus")
        return jsonify({"Success": False, "ErrorMessage": error_msg}), 500

@ServiceStatusBlueprint.route('/SystemResources', methods=['GET'])
def GetSystemResources():
    """Get system resource information including CPU temperature, usage, and memory."""
    try:
        LoggingService.LogFunctionEntry("GetSystemResources", "ServiceStatusController")
        
        # Get system resources from SystemMonitoringService
        resources = SystemMonitoringServiceInstance.GetSystemResources()
        
        LoggingService.LogInfo("Successfully retrieved system resources", "ServiceStatusController", "GetSystemResources")
        
        return jsonify({
            "Success": True,
            "Resources": resources
        })
        
    except Exception as e:
        error_msg = f"Exception getting system resources: {str(e)}"
        LoggingService.LogException(error_msg, e, "ServiceStatusController", "GetSystemResources")
        return jsonify({"Success": False, "ErrorMessage": error_msg}), 500
