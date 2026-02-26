"""
Service Control Controller
Unified service management for all microservices using PID-based control
"""

from flask import Blueprint, request, jsonify
from typing import Dict, Any
from Repositories.DatabaseManager import DatabaseManager
from Core.Logging.LoggingService import LoggingService
from datetime import datetime
import os
import signal
import platform
import time
import psutil

# Create Blueprint for service control routes
ServiceControlBlueprint = Blueprint('ServiceControl', __name__, url_prefix='/api/ServiceControl')

# Shared database manager
SharedDatabaseManager = DatabaseManager()

def IsServiceProcessRunning(ServiceName: str) -> bool:
    """Check if a service process is already running using ServiceStatusService."""
    try:
        from Features.ServiceControl.ServiceStatusService import ServiceStatusService
        status_service = ServiceStatusService()

        # Get service status from database
        service_status = status_service.GetServiceStatus(ServiceName)
        if not service_status:
            LoggingService.LogInfo(f"No ServiceStatus record found for {ServiceName}", "ServiceControlController", "IsServiceProcessRunning")
            return False

        # Check if service is marked as running
        status = service_status.get('Status', 'Stopped')
        process_id = service_status.get('ProcessId', 0)

        if status in ['Running', 'Starting'] and process_id > 0:
            # Verify process is actually running
            is_running = status_service.IsServiceProcessActuallyRunning(ServiceName, process_id)
            LoggingService.LogInfo(f"Service {ServiceName} database status: {status}, PID: {process_id}, actually running: {is_running}",
                                 "ServiceControlController", "IsServiceProcessRunning")
            return is_running
        else:
            LoggingService.LogInfo(f"Service {ServiceName} not running (status: {status}, PID: {process_id})",
                                 "ServiceControlController", "IsServiceProcessRunning")
            return False

    except Exception as e:
        LoggingService.LogException(f"Error checking if {ServiceName} is running", e, "ServiceControlController", "IsServiceProcessRunning")
        return False

@ServiceControlBlueprint.route('/<service_name>/<action>', methods=['POST'])
def ControlService(service_name: str, action: str):
    """Unified service control endpoint for all microservices."""
    try:
        LoggingService.LogFunctionEntry(f"ControlService", "ServiceControlController", f"{service_name}/{action}")

        # Debug logging
        LoggingService.LogInfo(f"ServiceControl API called: {service_name}/{action}", "ServiceControlController", "ControlService")
        LoggingService.LogInfo(f"Processing service control request for {service_name} with action {action}", "ServiceControlController", "ControlService")

        # Validate service name
        valid_services = ['WebService', 'TranscodeService', 'QualityTestService']
        if service_name not in valid_services:
            LoggingService.LogError(f"Invalid service name: {service_name}", "ServiceControlController", "ControlService")
            return jsonify({
                "Success": False,
                "ErrorMessage": f"Invalid service name: {service_name}. Valid services: {', '.join(valid_services)}"
            }), 400

        # Validate action
        valid_actions = ['Stop', 'GracefulStop', 'TerminateNow']
        if action not in valid_actions:
            return jsonify({
                "Success": False,
                "ErrorMessage": f"Invalid action: {action}. Valid actions: {', '.join(valid_actions)}. Note: Start and Restart are only available via the orchestrator (StartMediaVortex.py)"
            }), 400

        # Get service status from database
        service_status = SharedDatabaseManager.GetServiceStatus(service_name)
        if not service_status:
            return jsonify({
                "Success": False,
                "ErrorMessage": f"Service {service_name} not found in database"
            }), 404

        # Handle different actions
        if action == "Start":
            # Service starting is now handled only by the orchestrator
            return jsonify({
                "Success": False,
                "ErrorMessage": f"Service starting is only allowed via the orchestrator (StartMediaVortex.py). Use the orchestrator to start {service_name}."
            }), 400
        elif action == "Stop":
            result = PrivateStopService(service_name)
        elif action == "GracefulStop":
            result = PrivateGracefulStopService(service_name)
        elif action == "TerminateNow":
            result = PrivateTerminateService(service_name)
        elif action == "Restart":
            # Restart is also not allowed - use orchestrator
            return jsonify({
                "Success": False,
                "ErrorMessage": f"Service restart is only allowed via the orchestrator (StartMediaVortex.py). Use the orchestrator to restart {service_name}."
            }), 400
        else:
            return jsonify({
                "Success": False,
                "ErrorMessage": f"Unsupported action: {action}"
            }), 400

        return jsonify(result)

    except Exception as e:
        errorMsg = f"Exception controlling service {service_name}: {str(e)}"
        LoggingService.LogException(errorMsg, e, "ServiceControlController", "ControlService")
        return jsonify({"Success": False, "ErrorMessage": errorMsg}), 500

# PrivateStartService function removed - service starting is now only handled by the orchestrator

# PrivateStartServiceProcess function removed - service starting is now only handled by the orchestrator

def PrivateStopService(service_name: str) -> Dict[str, Any]:
    """Stop a service by updating its status in the database."""
    try:
        LoggingService.LogInfo(f"Stopping {service_name} via database status update", "ServiceControlController", "PrivateStopService")

        # Update service status to Stopped
        success = SharedDatabaseManager.UpdateServiceStatus(service_name, {
            'Status': 'Stopped',
            'IsProcessing': False,
            'ActiveJobsCount': 0
        })

        if success:
            LoggingService.LogInfo(f"Successfully stopped {service_name}", "ServiceControlController", "PrivateStopService")
            return {
                "Success": True,
                "Message": f"{service_name} stop requested successfully",
                "Status": "Stopped"
            }
        else:
            LoggingService.LogError(f"Failed to stop {service_name}", "ServiceControlController", "PrivateStopService")
            return {
                "Success": False,
                "ErrorMessage": f"Failed to stop {service_name}"
            }

    except Exception as e:
        LoggingService.LogException(f"Error stopping {service_name}", e, "ServiceControlController", "PrivateStopService")
        return {
            "Success": False,
            "ErrorMessage": f"Error stopping {service_name}: {str(e)}"
        }

def PrivateGracefulStopService(service_name: str) -> Dict[str, Any]:
    """Send graceful stop signal to a service using its PID."""
    try:
        LoggingService.LogInfo(f"Graceful stop requested for {service_name}", "ServiceControlController", "PrivateGracefulStopService")

        # Get service PID from database
        service_status = SharedDatabaseManager.GetServiceStatus(service_name)
        if not service_status:
            return {
                "Success": False,
                "ErrorMessage": f"Service {service_name} not found in database"
            }

        process_id = service_status.get('ProcessId', 0)
        if process_id == 0:
            # No PID available, use database status update
            success = SharedDatabaseManager.UpdateServiceStatus(service_name, {
                'Status': 'GracefulStop',
                'IsProcessing': False,
                'ActiveJobsCount': 0
            })

            if success:
                return {
                    "Success": True,
                    "Message": f"Graceful stop requested for {service_name} (no PID available)",
                    "Status": "GracefulStop"
                }
            else:
                return {
                    "Success": False,
                    "ErrorMessage": f"Failed to request graceful stop for {service_name}"
                }

        # Send SIGTERM signal to process
        try:
            if platform.system() == "Windows":
                os.kill(process_id, signal.SIGTERM)
            else:
                os.kill(process_id, signal.SIGTERM)

            # Update database status
            SharedDatabaseManager.UpdateServiceStatus(service_name, {
                'Status': 'GracefulStop',
                'IsProcessing': False,
                'ActiveJobsCount': 0
            })

            LoggingService.LogInfo(f"Graceful stop signal sent to {service_name} (PID: {process_id})", "ServiceControlController", "PrivateGracefulStopService")
            return {
                "Success": True,
                "Message": f"Graceful stop signal sent to {service_name} (PID: {process_id})",
                "Status": "GracefulStop"
            }

        except ProcessLookupError:
            LoggingService.LogWarning(f"Process {process_id} for {service_name} not found", "ServiceControlController", "PrivateGracefulStopService")
            # Update database to reflect process is no longer running
            SharedDatabaseManager.UpdateServiceStatus(service_name, {
                'Status': 'Stopped',
                'IsProcessing': False,
                'ActiveJobsCount': 0,
                'ProcessId': 0
            })
            return {
                "Success": True,
                "Message": f"{service_name} process not found, marked as stopped",
                "Status": "Stopped"
            }
        except PermissionError:
            LoggingService.LogError(f"Permission denied to send signal to {service_name} (PID: {process_id})", "ServiceControlController", "PrivateGracefulStopService")
            return {
                "Success": False,
                "ErrorMessage": f"Permission denied to send signal to {service_name}"
            }

    except Exception as e:
        LoggingService.LogException(f"Error sending graceful stop to {service_name}", e, "ServiceControlController", "PrivateGracefulStopService")
        return {
            "Success": False,
            "ErrorMessage": f"Error sending graceful stop to {service_name}: {str(e)}"
        }

def PrivateTerminateService(service_name: str) -> Dict[str, Any]:
    """Terminate a service immediately using its PID."""
    try:
        LoggingService.LogInfo(f"Terminate requested for {service_name}", "ServiceControlController", "PrivateTerminateService")

        # Get service PID from database
        service_status = SharedDatabaseManager.GetServiceStatus(service_name)
        if not service_status:
            return {
                "Success": False,
                "ErrorMessage": f"Service {service_name} not found in database"
            }

        process_id = service_status.get('ProcessId', 0)
        if process_id == 0:
            # No PID available, use database status update
            success = SharedDatabaseManager.UpdateServiceStatus(service_name, {
                'Status': 'Stopped',
                'IsProcessing': False,
                'ActiveJobsCount': 0
            })

            if success:
                return {
                    "Success": True,
                    "Message": f"Terminate requested for {service_name} (no PID available)",
                    "Status": "Stopped"
                }
            else:
                return {
                    "Success": False,
                    "ErrorMessage": f"Failed to terminate {service_name}"
                }

        # Send SIGKILL signal to process
        try:
            if platform.system() == "Windows":
                os.kill(process_id, signal.SIGKILL)
            else:
                os.kill(process_id, signal.SIGKILL)

            # Update database status
            SharedDatabaseManager.UpdateServiceStatus(service_name, {
                'Status': 'Stopped',
                'IsProcessing': False,
                'ActiveJobsCount': 0,
                'ProcessId': 0
            })

            LoggingService.LogInfo(f"Terminate signal sent to {service_name} (PID: {process_id})", "ServiceControlController", "PrivateTerminateService")
            return {
                "Success": True,
                "Message": f"Terminate signal sent to {service_name} (PID: {process_id})",
                "Status": "Stopped"
            }

        except ProcessLookupError:
            LoggingService.LogWarning(f"Process {process_id} for {service_name} not found", "ServiceControlController", "PrivateTerminateService")
            # Update database to reflect process is no longer running
            SharedDatabaseManager.UpdateServiceStatus(service_name, {
                'Status': 'Stopped',
                'IsProcessing': False,
                'ActiveJobsCount': 0,
                'ProcessId': 0
            })
            return {
                "Success": True,
                "Message": f"{service_name} process not found, marked as stopped",
                "Status": "Stopped"
            }
        except PermissionError:
            LoggingService.LogError(f"Permission denied to send signal to {service_name} (PID: {process_id})", "ServiceControlController", "PrivateTerminateService")
            return {
                "Success": False,
                "ErrorMessage": f"Permission denied to send signal to {service_name}"
            }

    except Exception as e:
        LoggingService.LogException(f"Error terminating {service_name}", e, "ServiceControlController", "PrivateTerminateService")
        return {
            "Success": False,
            "ErrorMessage": f"Error terminating {service_name}: {str(e)}"
        }

# PrivateRestartService function removed - service restart is now only handled by the orchestrator

@ServiceControlBlueprint.route('/Status', methods=['GET'])
def GetAllServiceStatus():
    """Get status of all services."""
    try:
        LoggingService.LogFunctionEntry("GetAllServiceStatus", "ServiceControlController")

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
            services.append({
                "ServiceName": row['ServiceName'],
                "Status": row['Status'],
                "HealthStatus": row['HealthStatus'],
                "StartTime": str(row['StartTime']) if row['StartTime'] else None,
                "LastHealthCheck": str(row['LastHealthCheck']) if row['LastHealthCheck'] else None,
                "UptimeSeconds": row['UptimeSeconds'],
                "MemoryUsage": row['MemoryUsage'],
                "CPUUsage": row['CPUUsage'],
                "DatabaseConnection": bool(row['DatabaseConnection']),
                "DiskSpace": row['DiskSpace'],
                "ErrorCount": row['ErrorCount'],
                "MaxErrors": row['MaxErrors'],
                "ActiveJobsCount": row['ActiveJobsCount'],
                "IsProcessing": bool(row['IsProcessing']),
                "LastErrorMessage": row['LastErrorMessage'],
                "ProcessId": row['ProcessId'],
                "Version": row['Version'],
                "ServiceType": row['ServiceType'],
                "CreatedAt": str(row['CreatedAt']) if row['CreatedAt'] else None,
                "UpdatedAt": str(row['UpdatedAt']) if row['UpdatedAt'] else None
            })

        LoggingService.LogInfo(f"Retrieved status for {len(services)} services", "ServiceControlController", "GetAllServiceStatus")
        return jsonify({
            "Success": True,
            "Services": services,
            "Count": len(services)
        })

    except Exception as e:
        errorMsg = f"Exception getting service status: {str(e)}"
        LoggingService.LogException(errorMsg, e, "ServiceControlController", "GetAllServiceStatus")
        return jsonify({"Success": False, "ErrorMessage": errorMsg}), 500


