"""
ServiceStatusService
Generic service for managing ServiceStatus records and process detection for all services
Implements MVVM pattern using MVVM architecture
"""

import os
import psutil
from typing import Dict, Any, Optional
from datetime import datetime
from Repositories.DatabaseManager import DatabaseManager
from Core.Logging.LoggingService import LoggingService
from Features.ServiceControl.ServiceControlRepository import ServiceControlRepository


class ServiceStatusService:
    """Generic service for managing ServiceStatus records and process detection."""

    def __init__(self, DatabaseManagerInstance: DatabaseManager = None, ServiceControlRepositoryInstance: Optional[ServiceControlRepository] = None):
        """Initialize the ServiceStatusService."""
        self.DatabaseManager = DatabaseManagerInstance or DatabaseManager()
        LoggingService.LogInfo("ServiceStatusService initialized", "ServiceStatusService", "__init__")
        self.ServiceControlRepository = ServiceControlRepositoryInstance or ServiceControlRepository()

    def EnsureServiceStatusExists(self, ServiceName: str, MaxConcurrentJobs: int = 1) -> bool:
        """Ensure ServiceStatus record exists, create with defaults if missing."""
        try:
            LoggingService.LogFunctionEntry("EnsureServiceStatusExists", "ServiceStatusService", ServiceName)

            # Check if record exists
            existing_status = self.ServiceControlRepository.GetServiceStatus(ServiceName)

            if existing_status is None:
                # Create new ServiceStatus record with defaults
                LoggingService.LogInfo(f"Creating ServiceStatus record for {ServiceName}", "ServiceStatusService", "EnsureServiceStatusExists")

                service_status = {
                    'ServiceName': ServiceName,
                    'Status': 'Stopped',
                    'HealthStatus': 'Unknown',
                    'StartTime': None,
                    'LastHealthCheck': None,
                    'UptimeSeconds': 0,
                    'MemoryUsage': 0.0,
                    'CPUUsage': 0.0,
                    'DatabaseConnection': True,
                    'DiskSpace': 0.0,
                    'ErrorCount': 0,
                    'MaxErrors': 5,
                    'ActiveJobsCount': 0,
                    'IsProcessing': False,
                    'ProcessId': 0,
                    'Version': '1.0.0',
                    'ServiceType': 'Microservice',
                    'MaxConcurrentJobs': MaxConcurrentJobs
                }

                result = self.ServiceControlRepository.SaveServiceStatus(service_status)
                if result:
                    LoggingService.LogInfo(f"ServiceStatus record created for {ServiceName} with MaxConcurrentJobs={MaxConcurrentJobs}",
                                         "ServiceStatusService", "EnsureServiceStatusExists")
                    return True
                else:
                    LoggingService.LogError(f"Failed to create ServiceStatus record for {ServiceName}",
                                          "ServiceStatusService", "EnsureServiceStatusExists")
                    return False
            else:
                LoggingService.LogInfo(f"ServiceStatus record already exists for {ServiceName}",
                                     "ServiceStatusService", "EnsureServiceStatusExists")
                return True

        except Exception as e:
            LoggingService.LogException(f"Error ensuring ServiceStatus exists for {ServiceName}", e,
                                      "ServiceStatusService", "EnsureServiceStatusExists")
            return False

    def IsServiceRunningInDatabase(self, ServiceName: str) -> bool:
        """Check if service is marked as Running or Starting in database."""
        try:
            LoggingService.LogFunctionEntry("IsServiceRunningInDatabase", "ServiceStatusService", ServiceName)

            service_status = self.ServiceControlRepository.GetServiceStatus(ServiceName)
            if service_status:
                status = service_status.get('Status', 'Stopped')
                is_running = status in ['Running', 'Starting']
                LoggingService.LogInfo(f"Service {ServiceName} database status: {status} (running: {is_running})",
                                     "ServiceStatusService", "IsServiceRunningInDatabase")
                return is_running
            else:
                LoggingService.LogInfo(f"No ServiceStatus record found for {ServiceName}",
                                     "ServiceStatusService", "IsServiceRunningInDatabase")
                return False

        except Exception as e:
            LoggingService.LogException(f"Error checking if {ServiceName} is running in database", e,
                                      "ServiceStatusService", "IsServiceRunningInDatabase")
            return False

    def IsServiceProcessActuallyRunning(self, ServiceName: str, ProcessId: int) -> bool:
        """Check if service process is actually running using setproctitle name matching."""
        try:
            LoggingService.LogFunctionEntry("IsServiceProcessActuallyRunning", "ServiceStatusService", ServiceName, ProcessId)

            if ProcessId <= 0:
                LoggingService.LogInfo(f"Invalid ProcessId {ProcessId} for {ServiceName}",
                                     "ServiceStatusService", "IsServiceProcessActuallyRunning")
                return False

            # Use setproctitle for reliable process name matching
            for proc in psutil.process_iter(['pid', 'name']):
                try:
                    if proc.info['pid'] == ProcessId:
                        process_name = proc.info['name']
                        # Check if process name matches the service name (setproctitle sets this)
                        if process_name == ServiceName:
                            LoggingService.LogInfo(f"Found running {ServiceName} process: PID {ProcessId}, Name: {process_name}",
                                                 "ServiceStatusService", "IsServiceProcessActuallyRunning")
                            return True
                        else:
                            LoggingService.LogInfo(f"Process {ProcessId} name '{process_name}' doesn't match {ServiceName}",
                                                 "ServiceStatusService", "IsServiceProcessActuallyRunning")
                            return False
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    continue

            LoggingService.LogInfo(f"No running process found for {ServiceName} with PID {ProcessId}",
                                 "ServiceStatusService", "IsServiceProcessActuallyRunning")
            return False

        except Exception as e:
            LoggingService.LogException(f"Error checking if {ServiceName} process is running", e,
                                      "ServiceStatusService", "IsServiceProcessActuallyRunning")
            return False

    def RegisterServiceStartup(self, ServiceName: str, MaxConcurrentJobs: int = 1) -> bool:
        """
        Combined service startup registration logic.
        Returns True if service is already running (prevent duplicate), False if safe to start.
        """
        try:
            current_pid = os.getpid()
            LoggingService.LogFunctionEntry("RegisterServiceStartup", "ServiceStatusService", f"{ServiceName} (PID: {current_pid})")

            # Step 1: Ensure ServiceStatus record exists
            if not self.EnsureServiceStatusExists(ServiceName, MaxConcurrentJobs):
                LoggingService.LogError(f"Failed to ensure ServiceStatus record exists for {ServiceName} (PID: {current_pid})",
                                      "ServiceStatusService", "RegisterServiceStartup")
                return True  # Prevent startup if we can't create record

            # Step 2: Check if service is marked as running in database
            if self.IsServiceRunningInDatabase(ServiceName):
                # Get the ProcessId from database
                service_status = self.ServiceControlRepository.GetServiceStatus(ServiceName)
                process_id = service_status.get('ProcessId', 0) if service_status else 0
                LoggingService.LogInfo(f"Service {ServiceName} marked as running in database with PID {process_id}. Current PID: {current_pid}",
                                     "ServiceStatusService", "RegisterServiceStartup")

                # Step 3: Verify if process is actually running
                if self.IsServiceProcessActuallyRunning(ServiceName, process_id):
                    LoggingService.LogInfo(f"Service {ServiceName} is already running with PID {process_id}. Current PID: {current_pid} - PREVENTING DUPLICATE",
                                         "ServiceStatusService", "RegisterServiceStartup")
                    return True  # Service already running, prevent duplicate
                else:
                    # Process not running, clean up stale record
                    LoggingService.LogInfo(f"Cleaning up stale ServiceStatus record for {ServiceName} (PID {process_id} not running). Current PID: {current_pid}",
                                         "ServiceStatusService", "RegisterServiceStartup")
                    self.ServiceControlRepository.UpdateServiceStatus(ServiceName, {
                        'Status': 'Stopped',
                        'ProcessId': 0,
                        'IsProcessing': False,
                        'ActiveJobsCount': 0
                    })
            else:
                LoggingService.LogInfo(f"Service {ServiceName} not marked as running in database. Current PID: {current_pid}",
                                     "ServiceStatusService", "RegisterServiceStartup")

            # Step 4: Register this service startup
            self.ServiceControlRepository.UpdateServiceStatus(ServiceName, {
                'Status': 'Starting',
                'ProcessId': current_pid,
                'IsProcessing': False,
                'ActiveJobsCount': 0
            })

            LoggingService.LogInfo(f"Service {ServiceName} startup registered with PID {current_pid} - ALLOWING STARTUP",
                                 "ServiceStatusService", "RegisterServiceStartup")
            return False  # Safe to start

        except Exception as e:
            LoggingService.LogException(f"Error registering service startup for {ServiceName}", e,
                                      "ServiceStatusService", "RegisterServiceStartup")
            return True  # Prevent startup on error

    def UpdateServiceStatus(self, ServiceName: str, StatusData: Dict[str, Any]) -> bool:
        """Update service status in database."""
        try:
            LoggingService.LogFunctionEntry("UpdateServiceStatus", "ServiceStatusService", ServiceName)

            result = self.ServiceControlRepository.UpdateServiceStatus(ServiceName, StatusData)
            if result:
                LoggingService.LogInfo(f"Service status updated for {ServiceName}",
                                     "ServiceStatusService", "UpdateServiceStatus")
            else:
                LoggingService.LogError(f"Failed to update service status for {ServiceName}",
                                      "ServiceStatusService", "UpdateServiceStatus")
            return result

        except Exception as e:
            LoggingService.LogException(f"Error updating service status for {ServiceName}", e,
                                      "ServiceStatusService", "UpdateServiceStatus")
            return False

    def GetServiceStatus(self, ServiceName: str) -> Optional[Dict[str, Any]]:
        """Get service status from database."""
        try:
            LoggingService.LogFunctionEntry("GetServiceStatus", "ServiceStatusService", ServiceName)

            return self.ServiceControlRepository.GetServiceStatus(ServiceName)

        except Exception as e:
            LoggingService.LogException(f"Error getting service status for {ServiceName}", e,
                                      "ServiceStatusService", "GetServiceStatus")
            return None
