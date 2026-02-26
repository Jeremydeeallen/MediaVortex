"""
ServiceLifecycleManager
Centralized service for managing MediaVortex service lifecycle (start, stop, status)
Implements MVVM pattern using MVVM architecture
"""

import os
import sys
import subprocess
import platform
import time
import signal
import psutil
from typing import List, Tuple, Dict, Any, Optional
from Core.Logging.LoggingService import LoggingService


class ServiceLifecycleManager:
    """Shared service for starting, stopping, and managing MediaVortex services."""

    # Service configurations
    SERVICES = {
        'WebService': {
            'Directory': 'WebService',
            'MainFile': 'Main.py',
            'ProcessName': 'WebService',  # setproctitle name
            'Description': 'Web Interface Service'
        },
        'TranscodeService': {
            'Directory': 'TranscodeService',
            'MainFile': 'Main.py',
            'ProcessName': 'TranscodeService',
            'Description': 'Video Transcoding Service'
        },
        'QualityTestService': {
            'Directory': 'QualityTestService',
            'MainFile': 'Main.py',
            'ProcessName': 'QualityTestService',
            'Description': 'Quality Testing Service'
        }
    }

    def __init__(self):
        """Initialize the service manager."""
        self.RootDirectory = os.path.dirname(os.path.abspath(__file__)).replace('Features\\ServiceControl', '').replace('Features/ServiceControl', '')
        LoggingService.LogInfo("ServiceLifecycleManager initialized", "ServiceLifecycleManager", "__init__")

    def FindRunningServices(self) -> List[Tuple[int, str]]:
        """
        Find all running MediaVortex services using command line arguments.

        Returns:
            List of (PID, ServiceName) tuples
        """
        try:
            running_services = []

            for proc in psutil.process_iter(['pid', 'name', 'cmdline']):
                try:
                    proc_name = proc.info['name']
                    cmdline = proc.info.get('cmdline', [])

                    # Check if this is a MediaVortex service by looking at command line
                    if proc_name in ['python.exe', 'pythonw.exe', 'python', 'pythonw'] and cmdline:
                        for service_name, config in self.SERVICES.items():
                            # Look for the service directory in the command line
                            service_dir = config['Directory']
                            if any(service_dir in arg for arg in cmdline):
                                running_services.append((proc.info['pid'], service_name))
                                break

                except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
                    continue

            return running_services

        except Exception as e:
            LoggingService.LogException("Error finding running services", e,
                                      "ServiceLifecycleManager", "FindRunningServices")
            return []

    def IsServiceRunning(self, ServiceName: str) -> Optional[int]:
        """
        Check if a specific service is running.

        Args:
            ServiceName: Name of the service to check

        Returns:
            PID if running, None if not running
        """
        running = self.FindRunningServices()
        for pid, name in running:
            if name == ServiceName:
                return pid
        return None

    def StartService(self, ServiceName: str, WaitSeconds: int = 5) -> Dict[str, Any]:
        """
        Start a specific service.

        Args:
            ServiceName: Name of the service to start
            WaitSeconds: Seconds to wait after starting

        Returns:
            Dict with Success, PID, Message
        """
        try:
            if ServiceName not in self.SERVICES:
                return {
                    "Success": False,
                    "ErrorMessage": f"Unknown service: {ServiceName}"
                }

            # Check if already running
            existing_pid = self.IsServiceRunning(ServiceName)
            if existing_pid:
                return {
                    "Success": False,
                    "ErrorMessage": f"{ServiceName} is already running with PID {existing_pid}"
                }

            config = self.SERVICES[ServiceName]
            service_dir = os.path.join(self.RootDirectory, config['Directory'])
            main_file = os.path.join(service_dir, config['MainFile'])

            # Determine Python executable
            if platform.system() == "Windows":
                python_exe = os.path.join(service_dir, "venv", "Scripts", "pythonw.exe")
            else:
                python_exe = os.path.join(service_dir, "venv", "bin", "python")

            if not os.path.exists(python_exe):
                return {
                    "Success": False,
                    "ErrorMessage": f"Python executable not found: {python_exe}"
                }

            if not os.path.exists(main_file):
                return {
                    "Success": False,
                    "ErrorMessage": f"Service main file not found: {main_file}"
                }

            # Start the service
            LoggingService.LogInfo(f"Starting {ServiceName}...", "ServiceLifecycleManager", "StartService")

            if platform.system() == "Windows":
                process = subprocess.Popen(
                    [python_exe, main_file],
                    cwd=service_dir,
                    creationflags=subprocess.CREATE_NEW_PROCESS_GROUP,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL
                )
            else:
                process = subprocess.Popen(
                    [python_exe, main_file],
                    cwd=service_dir,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    start_new_session=True
                )

            # Wait for service to initialize and set process title
            LoggingService.LogInfo(f"Waiting {WaitSeconds} seconds for {ServiceName} to initialize...",
                                 "ServiceLifecycleManager", "StartService")
            time.sleep(WaitSeconds)

            # Check if service is now running
            new_pid = self.IsServiceRunning(ServiceName)
            if new_pid:
                LoggingService.LogInfo(f"{ServiceName} started successfully with PID {new_pid}",
                                     "ServiceLifecycleManager", "StartService")
                return {
                    "Success": True,
                    "PID": new_pid,
                    "Message": f"{ServiceName} started successfully"
                }
            else:
                return {
                    "Success": False,
                    "ErrorMessage": f"{ServiceName} process started but not found in running services"
                }

        except Exception as e:
            error_msg = f"Error starting {ServiceName}: {str(e)}"
            LoggingService.LogException(error_msg, e, "ServiceLifecycleManager", "StartService")
            return {
                "Success": False,
                "ErrorMessage": error_msg
            }

    def StopService(self, ServiceName: str, Force: bool = False, WaitSeconds: int = 3) -> Dict[str, Any]:
        """
        Stop a specific service.

        Args:
            ServiceName: Name of the service to stop
            Force: If True, use SIGKILL immediately
            WaitSeconds: Seconds to wait for graceful shutdown

        Returns:
            Dict with Success, Message
        """
        try:
            pid = self.IsServiceRunning(ServiceName)
            if not pid:
                return {
                    "Success": True,
                    "Message": f"{ServiceName} is not running"
                }

            LoggingService.LogInfo(f"Stopping {ServiceName} (PID: {pid})...",
                                 "ServiceLifecycleManager", "StopService")

            if Force:
                # Immediate kill using psutil (works on all platforms)
                try:
                    process = psutil.Process(pid)
                    process.terminate()
                    time.sleep(1)
                    # If still running, force kill
                    if process.is_running():
                        process.kill()
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    pass  # Process already gone
            else:
                # Graceful shutdown
                os.kill(pid, signal.SIGTERM)
                time.sleep(WaitSeconds)

                # Check if still running and force kill if needed
                if self.IsServiceRunning(ServiceName):
                    LoggingService.LogInfo(f"Force killing {ServiceName} (PID: {pid})...",
                                         "ServiceLifecycleManager", "StopService")
                    try:
                        process = psutil.Process(pid)
                        process.kill()
                    except (psutil.NoSuchProcess, psutil.AccessDenied):
                        pass  # Process already gone

            # Verify stopped
            if not self.IsServiceRunning(ServiceName):
                LoggingService.LogInfo(f"{ServiceName} stopped successfully",
                                     "ServiceLifecycleManager", "StopService")
                return {
                    "Success": True,
                    "Message": f"{ServiceName} stopped successfully"
                }
            else:
                return {
                    "Success": False,
                    "ErrorMessage": f"Failed to stop {ServiceName}"
                }

        except (OSError, ProcessLookupError) as e:
            # Process already gone
            return {
                "Success": True,
                "Message": f"{ServiceName} is not running"
            }
        except Exception as e:
            error_msg = f"Error stopping {ServiceName}: {str(e)}"
            LoggingService.LogException(error_msg, e, "ServiceLifecycleManager", "StopService")
            return {
                "Success": False,
                "ErrorMessage": error_msg
            }

    def StartAllServices(self) -> Dict[str, Any]:
        """
        Start all MediaVortex services in order.

        Returns:
            Dict with Success, StartedServices, FailedServices
        """
        try:
            LoggingService.LogInfo("Starting all MediaVortex services...",
                                 "ServiceLifecycleManager", "StartAllServices")

            started_services = []
            failed_services = []

            # Start services in order
            for service_name in self.SERVICES.keys():
                result = self.StartService(service_name)
                if result["Success"]:
                    started_services.append({
                        "ServiceName": service_name,
                        "PID": result.get("PID")
                    })
                else:
                    failed_services.append({
                        "ServiceName": service_name,
                        "Error": result.get("ErrorMessage")
                    })

            success = len(failed_services) == 0
            message = f"Started {len(started_services)} services" if success else f"Failed to start {len(failed_services)} services"

            return {
                "Success": success,
                "Message": message,
                "StartedServices": started_services,
                "FailedServices": failed_services
            }

        except Exception as e:
            error_msg = f"Error starting services: {str(e)}"
            LoggingService.LogException(error_msg, e, "ServiceLifecycleManager", "StartAllServices")
            return {
                "Success": False,
                "ErrorMessage": error_msg
            }

    def StopAllServices(self, Force: bool = False) -> Dict[str, Any]:
        """
        Stop all running MediaVortex services.

        Args:
            Force: If True, use immediate kill

        Returns:
            Dict with Success, StoppedServices, FailedServices
        """
        try:
            LoggingService.LogInfo(f"Stopping all MediaVortex services (Force: {Force})...",
                                 "ServiceLifecycleManager", "StopAllServices")

            running = self.FindRunningServices()
            if not running:
                return {
                    "Success": True,
                    "Message": "No services running"
                }

            stopped_services = []
            failed_services = []

            for pid, service_name in running:
                result = self.StopService(service_name, Force=Force)
                if result["Success"]:
                    stopped_services.append(service_name)
                else:
                    failed_services.append({
                        "ServiceName": service_name,
                        "Error": result.get("ErrorMessage")
                    })

            success = len(failed_services) == 0
            message = f"Stopped {len(stopped_services)} services" if success else f"Failed to stop {len(failed_services)} services"

            return {
                "Success": success,
                "Message": message,
                "StoppedServices": stopped_services,
                "FailedServices": failed_services
            }

        except Exception as e:
            error_msg = f"Error stopping services: {str(e)}"
            LoggingService.LogException(error_msg, e, "ServiceLifecycleManager", "StopAllServices")
            return {
                "Success": False,
                "ErrorMessage": error_msg
            }
