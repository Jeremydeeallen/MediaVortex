"""
Service Control Controller
Unified service management for all microservices using PID-based control
"""

from flask import Blueprint, request, jsonify
from typing import Dict, Any
from Repositories.DatabaseManager import DatabaseManager
from Services.LoggingService import LoggingService
from datetime import datetime
import os
import signal
import platform
import time

# Create Blueprint for service control routes
ServiceControlBlueprint = Blueprint('ServiceControl', __name__, url_prefix='/api/ServiceControl')

# Shared database manager
SharedDatabaseManager = DatabaseManager()

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
        valid_actions = ['Start', 'Stop', 'GracefulStop', 'TerminateNow', 'Restart']
        if action not in valid_actions:
            return jsonify({
                "Success": False,
                "ErrorMessage": f"Invalid action: {action}. Valid actions: {', '.join(valid_actions)}"
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
            result = PrivateStartService(service_name)
        elif action == "Stop":
            result = PrivateStopService(service_name)
        elif action == "GracefulStop":
            result = PrivateGracefulStopService(service_name)
        elif action == "TerminateNow":
            result = PrivateTerminateService(service_name)
        elif action == "Restart":
            result = PrivateRestartService(service_name)
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

def PrivateStartService(service_name: str) -> Dict[str, Any]:
    """Start a service by creating a ServiceCommand."""
    try:
        LoggingService.LogInfo(f"Starting {service_name} via ServiceCommand queue", "ServiceControlController", "PrivateStartService")
        
        # For WebService, just update database status (it's already running)
        if service_name == "WebService":
            success = SharedDatabaseManager.UpdateServiceStatus(service_name, {
                'Status': 'Running',
                'IsProcessing': False,
                'ActiveJobsCount': 0
            })
            
            if success:
                LoggingService.LogInfo(f"Successfully started {service_name}", "ServiceControlController", "PrivateStartService")
                return {
                    "Success": True,
                    "Message": f"{service_name} started successfully",
                    "Status": "Running"
                }
            else:
                return {
                    "Success": False,
                    "ErrorMessage": f"Failed to start {service_name}"
                }
        
        # Directly start the service process
        LoggingService.LogInfo(f"Directly starting {service_name} process", "ServiceControlController", "PrivateStartService")
        
        # Update service status to indicate start is requested
        LoggingService.LogInfo(f"Updating {service_name} status to 'Starting'", "ServiceControlController", "PrivateStartService")
        update_success = SharedDatabaseManager.UpdateServiceStatus(service_name, {
            'Status': 'Starting',
            'IsProcessing': False,
            'ActiveJobsCount': 0
        })
        LoggingService.LogInfo(f"UpdateServiceStatus result for {service_name}: {update_success}", "ServiceControlController", "PrivateStartService")
        
        # Start the service process directly
        success = PrivateStartServiceProcess(service_name)
        
        if success:
            return {
                "Success": True,
                "Message": f"{service_name} started successfully",
                "Status": "Running"
            }
        else:
            return {
                "Success": False,
                "ErrorMessage": f"Failed to start {service_name} process"
            }
            
    except Exception as e:
        LoggingService.LogException(f"Error starting {service_name}", e, "ServiceControlController", "PrivateStartService")
        return {
            "Success": False,
            "ErrorMessage": f"Error starting {service_name}: {str(e)}"
        }

def PrivateStartServiceProcess(service_name: str) -> bool:
    """Directly start a service process."""
    try:
        import subprocess
        import os
        import platform
        
        LoggingService.LogInfo(f"Starting {service_name} process directly", "ServiceControlController", "PrivateStartServiceProcess")
        
        # Get the script directory
        script_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        
        # Determine service directory and main script
        if service_name == "QualityTestService":
            service_dir = os.path.join(script_dir, "QualityTestService")
            main_script = "Main.py"
        elif service_name == "TranscodeService":
            service_dir = os.path.join(script_dir, "TranscodeService")
            main_script = "Main.py"
        else:
            LoggingService.LogError(f"Unknown service: {service_name}", "ServiceControlController", "PrivateStartServiceProcess")
            return False
        
        # Determine Python executable
        if platform.system() == "Windows":
            python_exe = os.path.join(service_dir, "venv", "Scripts", "python.exe")
        else:
            python_exe = os.path.join(service_dir, "venv", "bin", "python")
        
        # Start the service process
        process = subprocess.Popen(
            [python_exe, main_script],
            cwd=service_dir,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            creationflags=subprocess.CREATE_NEW_PROCESS_GROUP if platform.system() == "Windows" else 0
        )
        
        LoggingService.LogInfo(f"Started {service_name} process with PID {process.pid}", "ServiceControlController", "PrivateStartServiceProcess")
        
        # Update service status with process ID
        SharedDatabaseManager.UpdateServiceStatus(service_name, {
            'Status': 'Running',
            'ProcessId': process.pid,
            'IsProcessing': False,
            'ActiveJobsCount': 0
        })
        
        return True
        
    except Exception as e:
        LoggingService.LogException(f"Error starting {service_name} process", e, "ServiceControlController", "PrivateStartServiceProcess")
        return False

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

def PrivateRestartService(service_name: str) -> Dict[str, Any]:
    """Restart a service by stopping it first, then starting it."""
    try:
        LoggingService.LogInfo(f"Restart requested for {service_name}", "ServiceControlController", "PrivateRestartService")
        
        # First stop the service
        stop_result = PrivateStopService(service_name)
        if not stop_result.get("Success", False):
            return {
                "Success": False,
                "ErrorMessage": f"Failed to stop {service_name} for restart: {stop_result.get('ErrorMessage', 'Unknown error')}"
            }
        
        # Wait a moment for the service to stop
        time.sleep(2)
        
        # Then start the service
        start_result = PrivateStartService(service_name)
        if not start_result.get("Success", False):
            return {
                "Success": False,
                "ErrorMessage": f"Failed to start {service_name} after restart: {start_result.get('ErrorMessage', 'Unknown error')}"
            }
        
        LoggingService.LogInfo(f"Successfully restarted {service_name}", "ServiceControlController", "PrivateRestartService")
        return {
            "Success": True,
            "Message": f"{service_name} restarted successfully",
            "Status": "Running"
        }
        
    except Exception as e:
        LoggingService.LogException(f"Error restarting {service_name}", e, "ServiceControlController", "PrivateRestartService")
        return {
            "Success": False,
            "ErrorMessage": f"Error restarting {service_name}: {str(e)}"
        }

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
                "ServiceName": row[0],
                "Status": row[1],
                "HealthStatus": row[2],
                "StartTime": row[3],
                "LastHealthCheck": row[4],
                "UptimeSeconds": row[5],
                "MemoryUsage": row[6],
                "CPUUsage": row[7],
                "DatabaseConnection": bool(row[8]),
                "DiskSpace": row[9],
                "ErrorCount": row[10],
                "MaxErrors": row[11],
                "ActiveJobsCount": row[12],
                "IsProcessing": bool(row[13]),
                "LastErrorMessage": row[14],
                "ProcessId": row[15],
                "Version": row[16],
                "ServiceType": row[17],
                "CreatedAt": row[18],
                "UpdatedAt": row[19]
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



