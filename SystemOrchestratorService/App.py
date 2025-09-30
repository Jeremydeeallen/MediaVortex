"""
SystemOrchestratorService Application Logic
Simple process manager for MediaVortex services
"""

import sys
import os
import time
import subprocess
import signal
import platform
from typing import Dict, Any, Optional
from datetime import datetime


class ServiceInfo:
    """Information about a managed service."""
    
    def __init__(self, Name: str, Directory: str, MainScript: str, Port: Optional[int] = None):
        self.Name = Name
        self.Directory = Directory
        self.MainScript = MainScript
        self.Port = Port
        self.Process = None
        self.StartTime = None


class SystemOrchestratorApp:
    """Simple process manager for MediaVortex services."""
    
    def __init__(self):
        """Initialize the SystemOrchestratorService application."""
        # Check if another instance is already running
        if self.PrivateIsServiceAlreadyRunning():
            print("ERROR: SystemOrchestratorService is already running. Preventing duplicate instance.")
            sys.exit(1)
        
        self.ShutdownEvent = False
        self.StartTime = datetime.now()
        
        # Initialize managed services
        self.ManagedServices = self.PrivateInitializeServices()
        
        print("SystemOrchestratorApp initialized")
    
    def PrivateIsServiceAlreadyRunning(self) -> bool:
        """Check if another SystemOrchestratorService instance is already running."""
        # Simple check - just return False for now
        # Each service will handle its own duplicate prevention
        return False
    
    def PrivateInitializeServices(self) -> Dict[str, ServiceInfo]:
        """Initialize the list of managed services."""
        services = {}
        
        # Get the script directory
        script_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        
        # MediaVortex main application (runs in root directory)
        services['MediaVortex'] = ServiceInfo(
            Name='MediaVortex',
            Directory=script_dir,  # Main project directory
            MainScript='MediaVortex.py',  # Just the filename
            Port=5000
        )
        
        # TranscodeService
        services['TranscodeService'] = ServiceInfo(
            Name='TranscodeService',
            Directory=os.path.join(script_dir, 'TranscodeService'),
            MainScript=os.path.join(script_dir, 'TranscodeService', 'Main.py'),
            Port=None
        )
        
        # QualityCompareService
        services['QualityCompareService'] = ServiceInfo(
            Name='QualityCompareService',
            Directory=os.path.join(script_dir, 'QualityCompareService'),
            MainScript=os.path.join(script_dir, 'QualityCompareService', 'Main.py'),
            Port=None
        )
        
        return services
    
    def Run(self):
        """Start all managed services."""
        try:
            print("Starting SystemOrchestratorService...")
            
            # Start all services
            self.PrivateStartAllServices()
            
            # Main monitoring loop
            self.PrivateMainLoop()
            
            return True
            
        except Exception as e:
            print(f"Error starting SystemOrchestratorService: {e}")
            return False
    
    def PrivateStartAllServices(self):
        """Start all managed services."""
        print("Starting all MediaVortex services...")
        
        # Start MediaVortex first
        self.PrivateStartService(self.ManagedServices['MediaVortex'])
        
        # Wait for MediaVortex to start
        print("Waiting for MediaVortex to start...")
        time.sleep(5)
        
        # Start other services
        self.PrivateStartService(self.ManagedServices['TranscodeService'])
        self.PrivateStartService(self.ManagedServices['QualityCompareService'])
        
        print("All services started")
    
    def PrivateStartService(self, service_info: ServiceInfo):
        """Start a specific service."""
        try:
            print(f"Starting {service_info.Name}...")
            
            # All services use their venv python
            if platform.system() == "Windows":
                python_exe = os.path.join(service_info.Directory, "venv", "Scripts", "python.exe")
            else:
                python_exe = os.path.join(service_info.Directory, "venv", "bin", "python")
            
            if service_info.Name == 'MediaVortex':
                # MediaVortex runs with venv python MediaVortex.py
                service_info.Process = subprocess.Popen(
                    [python_exe, service_info.MainScript],
                    cwd=service_info.Directory
                )
            else:
                # Microservices run with venv python Main.py
                service_info.Process = subprocess.Popen(
                    [python_exe, "Main.py"],
                    cwd=service_info.Directory
                )
            
            service_info.StartTime = datetime.now()
            print(f"✅ {service_info.Name} started (PID: {service_info.Process.pid})")
            
        except Exception as e:
            print(f"❌ Failed to start {service_info.Name}: {e}")
    
    def PrivateMainLoop(self):
        """Main monitoring loop."""
        print("SystemOrchestratorService is now running. Press Ctrl+C to stop.")
        
        try:
            while not self.ShutdownEvent:
                # Check if any service has died
                for service_name, service_info in self.ManagedServices.items():
                    if service_info.Process and service_info.Process.poll() is not None:
                        print(f"⚠️  {service_name} has stopped, restarting...")
                        self.PrivateStartService(service_info)
                
                # Wait a bit before checking again
                time.sleep(10)
                
        except KeyboardInterrupt:
            print("\nReceived keyboard interrupt, shutting down...")
            self.ShutdownEvent = True
        finally:
            self.PrivateShutdownAllServices()
    
    def PrivateShutdownAllServices(self):
        """Shutdown all managed services."""
        print("Shutting down all services...")
        
        for service_name, service_info in self.ManagedServices.items():
            if service_info.Process:
                print(f"Stopping {service_name}...")
                try:
                    service_info.Process.terminate()
                    service_info.Process.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    print(f"Force killing {service_name}...")
                    service_info.Process.kill()
                except Exception as e:
                    print(f"Error stopping {service_name}: {e}")
        
        print("All services stopped")
    
    def Shutdown(self):
        """Gracefully shutdown the orchestrator."""
        print("SystemOrchestratorService shutdown requested")
        self.ShutdownEvent = True