#!/usr/bin/env python3
"""
StopAllPythonServices.py
Script to stop all MediaVortex Python services and log the results
"""

import sys
import os
import psutil
import time
from typing import List, Dict, Any

# Add the project root to the Python path
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, project_root)

from Services.LoggingService import LoggingService
from Repositories.DatabaseManager import DatabaseManager


class PythonServiceStopper:
    """Class to handle stopping all MediaVortex Python services."""
    
    def __init__(self):
        """Initialize the service stopper."""
        self.DatabaseManager = DatabaseManager()
        self.ServicesToStop = [
            "MediaVortex",
            "TranscodeService", 
            "QualityTestingService",
            "SystemOrchestratorService"
        ]
        self.StoppedServices = []
        self.FailedServices = []
        
        LoggingService.LogInfo("PythonServiceStopper initialized", "PythonServiceStopper", "__init__")
    
    def FindPythonProcesses(self) -> List[Dict[str, Any]]:
        """Find all Python processes that are MediaVortex services."""
        try:
            LoggingService.LogInfo("Scanning for MediaVortex Python processes", "PythonServiceStopper", "FindPythonProcesses")
            
            MediaVortexProcesses = []
            
            for Process in psutil.process_iter(['pid', 'name', 'cmdline', 'create_time']):
                try:
                    # Check if it's a Python process
                    if Process.info['name'] and 'python' in Process.info['name'].lower():
                        CmdLine = Process.info['cmdline']
                        if CmdLine:
                            CmdLineStr = ' '.join(CmdLine)
                            
                            # Check if it's a MediaVortex service
                            for ServiceName in self.ServicesToStop:
                                if self.IsMediaVortexService(CmdLineStr, ServiceName):
                                    MediaVortexProcesses.append({
                                        'Pid': Process.info['pid'],
                                        'Name': ServiceName,
                                        'CmdLine': CmdLineStr,
                                        'CreateTime': Process.info['create_time']
                                    })
                                    break
                                    
                except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
                    # Process may have terminated or we don't have access
                    continue
            
            LoggingService.LogInfo(f"Found {len(MediaVortexProcesses)} MediaVortex Python processes", 
                                 "PythonServiceStopper", "FindPythonProcesses")
            return MediaVortexProcesses
            
        except Exception as e:
            LoggingService.LogException("Error finding Python processes", e, 
                                      "PythonServiceStopper", "FindPythonProcesses")
            return []
    
    def IsMediaVortexService(self, CmdLineStr: str, ServiceName: str) -> bool:
        """Check if a command line represents a specific MediaVortex service."""
        try:
            # Convert to lowercase for case-insensitive matching
            CmdLineLower = CmdLineStr.lower()
            
            if ServiceName == "MediaVortex":
                # Main MediaVortex app
                return ('mediavortex.py' in CmdLineLower or 
                       'mediavortex' in CmdLineLower and 'main.py' in CmdLineLower)
            
            elif ServiceName == "TranscodeService":
                # TranscodeService
                return ('transcodeservice' in CmdLineLower and 'main.py' in CmdLineLower)
            
            elif ServiceName == "QualityTestingService":
                # QualityTestingService
                return ('qualitytestingservice' in CmdLineLower and 'main.py' in CmdLineLower)
            
            elif ServiceName == "SystemOrchestratorService":
                # SystemOrchestratorService
                return ('systemorchestratorservice' in CmdLineLower and 'main.py' in CmdLineLower)
            
            return False
            
        except Exception as e:
            LoggingService.LogException(f"Error checking if process is {ServiceName}", e, 
                                      "PythonServiceStopper", "IsMediaVortexService")
            return False
    
    def StopProcess(self, ProcessInfo: Dict[str, Any]) -> bool:
        """Stop a single Python process."""
        try:
            Pid = ProcessInfo['Pid']
            ServiceName = ProcessInfo['Name']
            
            LoggingService.LogInfo(f"Attempting to stop {ServiceName} (PID: {Pid})", 
                                 "PythonServiceStopper", "StopProcess")
            
            # Get the process
            Process = psutil.Process(Pid)
            
            # Try graceful termination first
            Process.terminate()
            
            # Wait up to 10 seconds for graceful shutdown
            try:
                Process.wait(timeout=10)
                LoggingService.LogInfo(f"Successfully stopped {ServiceName} (PID: {Pid}) gracefully", 
                                     "PythonServiceStopper", "StopProcess")
                return True
            except psutil.TimeoutExpired:
                # Force kill if graceful termination failed
                LoggingService.LogWarning(f"Graceful shutdown failed for {ServiceName} (PID: {Pid}), forcing kill", 
                                        "PythonServiceStopper", "StopProcess")
                Process.kill()
                Process.wait(timeout=5)
                LoggingService.LogInfo(f"Force killed {ServiceName} (PID: {Pid})", 
                                     "PythonServiceStopper", "StopProcess")
                return True
                
        except psutil.NoSuchProcess:
            LoggingService.LogInfo(f"Process {ServiceName} (PID: {Pid}) already terminated", 
                                 "PythonServiceStopper", "StopProcess")
            return True
        except psutil.AccessDenied:
            LoggingService.LogError(f"Access denied when trying to stop {ServiceName} (PID: {Pid})", 
                                  "PythonServiceStopper", "StopProcess")
            return False
        except Exception as e:
            LoggingService.LogException(f"Error stopping {ServiceName} (PID: {Pid})", e, 
                                      "PythonServiceStopper", "StopProcess")
            return False
    
    def UpdateServiceStatusInDatabase(self, ServiceName: str, Status: str):
        """Update service status in database to reflect shutdown."""
        try:
            # Update the service status to Stopped
            StatusData = {
                'Status': Status,
                'HealthStatus': 'Stopped',
                'IsProcessing': False,
                'ActiveJobsCount': 0,
                'ProcessId': 0
            }
            
            Success = self.DatabaseManager.UpdateServiceStatus(ServiceName, StatusData)
            if Success:
                LoggingService.LogInfo(f"Updated {ServiceName} status to {Status} in database", 
                                     "PythonServiceStopper", "UpdateServiceStatusInDatabase")
            else:
                LoggingService.LogWarning(f"Failed to update {ServiceName} status in database", 
                                        "PythonServiceStopper", "UpdateServiceStatusInDatabase")
                
        except Exception as e:
            LoggingService.LogException(f"Error updating {ServiceName} status in database", e, 
                                      "PythonServiceStopper", "UpdateServiceStatusInDatabase")
    
    def StopAllServices(self) -> Dict[str, Any]:
        """Stop all MediaVortex Python services."""
        try:
            LoggingService.LogInfo("Starting shutdown of all MediaVortex Python services", 
                                 "PythonServiceStopper", "StopAllServices")
            
            # Find all MediaVortex processes
            Processes = self.FindPythonProcesses()
            
            if not Processes:
                LoggingService.LogInfo("No MediaVortex Python services found running", 
                                     "PythonServiceStopper", "StopAllServices")
                return {
                    "Success": True,
                    "Message": "No services were running",
                    "ServicesStopped": 0,
                    "ServicesFailed": 0,
                    "StoppedServices": [],
                    "FailedServices": []
                }
            
            # Stop each process
            for ProcessInfo in Processes:
                ServiceName = ProcessInfo['Name']
                Success = self.StopProcess(ProcessInfo)
                
                if Success:
                    self.StoppedServices.append(ServiceName)
                    # Update database status
                    self.UpdateServiceStatusInDatabase(ServiceName, "Stopped")
                else:
                    self.FailedServices.append(ServiceName)
            
            # Log summary
            TotalStopped = len(self.StoppedServices)
            TotalFailed = len(self.FailedServices)
            
            LoggingService.LogInfo(f"Service shutdown completed. Stopped: {TotalStopped}, Failed: {TotalFailed}", 
                                 "PythonServiceStopper", "StopAllServices")
            
            if self.StoppedServices:
                LoggingService.LogInfo(f"Successfully stopped services: {', '.join(self.StoppedServices)}", 
                                     "PythonServiceStopper", "StopAllServices")
            
            if self.FailedServices:
                LoggingService.LogWarning(f"Failed to stop services: {', '.join(self.FailedServices)}", 
                                        "PythonServiceStopper", "StopAllServices")
            
            return {
                "Success": TotalFailed == 0,
                "Message": f"Stopped {TotalStopped} services, {TotalFailed} failed",
                "ServicesStopped": TotalStopped,
                "ServicesFailed": TotalFailed,
                "StoppedServices": self.StoppedServices,
                "FailedServices": self.FailedServices
            }
            
        except Exception as e:
            LoggingService.LogException("Error during service shutdown", e, 
                                      "PythonServiceStopper", "StopAllServices")
            return {
                "Success": False,
                "Message": f"Error during shutdown: {str(e)}",
                "ServicesStopped": len(self.StoppedServices),
                "ServicesFailed": len(self.FailedServices),
                "StoppedServices": self.StoppedServices,
                "FailedServices": self.FailedServices
            }


def main():
    """Main entry point for the script."""
    try:
        print("MediaVortex Python Service Stopper")
        print("=" * 40)
        
        # Create service stopper
        Stopper = PythonServiceStopper()
        
        # Stop all services
        Result = Stopper.StopAllServices()
        
        # Print results
        print(f"\nShutdown Results:")
        print(f"Success: {Result['Success']}")
        print(f"Message: {Result['Message']}")
        print(f"Services Stopped: {Result['ServicesStopped']}")
        print(f"Services Failed: {Result['ServicesFailed']}")
        
        if Result['StoppedServices']:
            print(f"Stopped Services: {', '.join(Result['StoppedServices'])}")
        
        if Result['FailedServices']:
            print(f"Failed Services: {', '.join(Result['FailedServices'])}")
        
        print(f"\nResults logged to database.")
        
        # Exit with appropriate code
        sys.exit(0 if Result['Success'] else 1)
        
    except Exception as e:
        print(f"Fatal error: {e}")
        LoggingService.LogException("Fatal error in main", e, "StopAllPythonServices", "main")
        sys.exit(1)


if __name__ == "__main__":
    main()
