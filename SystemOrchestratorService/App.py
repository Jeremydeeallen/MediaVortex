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
import threading
import select
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
    
    def __init__(self, Background=False):
        """Initialize the SystemOrchestratorService application."""
        # Check if another instance is already running
        if self.PrivateIsServiceAlreadyRunning():
            print("ERROR: SystemOrchestratorService is already running. Preventing duplicate instance.")
            sys.exit(1)
        
        self.Background = Background
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
            
            # Configure subprocess based on background mode
            if self.Background:
                # Background mode - hide windows and redirect output
                if platform.system() == "Windows":
                    service_info.Process = subprocess.Popen(
                        [python_exe, service_info.MainScript if service_info.Name == 'MediaVortex' else "Main.py"],
                        cwd=service_info.Directory,
                        stdout=subprocess.DEVNULL,
                        stderr=subprocess.DEVNULL,
                        creationflags=subprocess.CREATE_NEW_PROCESS_GROUP
                    )
                else:
                    service_info.Process = subprocess.Popen(
                        [python_exe, service_info.MainScript if service_info.Name == 'MediaVortex' else "Main.py"],
                        cwd=service_info.Directory,
                        stdout=subprocess.DEVNULL,
                        stderr=subprocess.DEVNULL,
                        start_new_session=True
                    )
            else:
                # Foreground mode - show output
                service_info.Process = subprocess.Popen(
                    [python_exe, service_info.MainScript if service_info.Name == 'MediaVortex' else "Main.py"],
                    cwd=service_info.Directory
                )
            
            service_info.StartTime = datetime.now()
            print(f"✅ {service_info.Name} started (PID: {service_info.Process.pid})")
            
        except Exception as e:
            print(f"❌ Failed to start {service_info.Name}: {e}")
    
    def PrivateMainLoop(self):
        """Main monitoring loop."""
        print("SystemOrchestratorService is now running.")
        print("Commands:")
        print("  Press 1 to reset TranscodeService")
        print("  Press 2 to reset QualityCompareService")
        print("  Press 3 to reset MediaVortex")
        print("  Press q to quit")
        print("  Press Ctrl+C to stop")
        print()
        
        try:
            while not self.ShutdownEvent:
                # Check if any service has died
                for service_name, service_info in self.ManagedServices.items():
                    if service_info.Process:
                        # poll() returns None if process is still running, returncode if it has terminated
                        returncode = service_info.Process.poll()
                        if returncode is not None:
                            print(f"⚠️  {service_name} has stopped (exit code: {returncode}), restarting...")
                            self.PrivateStartService(service_info)
                
                # Handle user input
                self.PrivateHandleUserInput()
                
                # Wait a bit before checking again
                time.sleep(1)  # Reduced sleep time for more responsive input handling
                
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
    
    def PrivateResetService(self, service_name: str):
        """Reset a specific service by stopping and restarting it."""
        if service_name not in self.ManagedServices:
            print(f"❌ Unknown service: {service_name}")
            return False
        
        service_info = self.ManagedServices[service_name]
        print(f"🔄 Resetting {service_name}...")
        
        # Stop the service if it's running
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
        
        # Wait a moment before restarting
        time.sleep(2)
        
        # Restart the service
        self.PrivateStartService(service_info)
        return True
    
    def PrivateHandleUserInput(self):
        """Handle user input for service management commands."""
        try:
            # Check if input is available (non-blocking)
            if platform.system() == "Windows":
                # Windows doesn't support select() for stdin, so we'll use a different approach
                import msvcrt
                if msvcrt.kbhit():
                    key = msvcrt.getch().decode('utf-8').lower()
                    if key == '1':
                        self.PrivateResetService('TranscodeService')
                    elif key == '2':
                        self.PrivateResetService('QualityCompareService')
                    elif key == '3':
                        self.PrivateResetService('MediaVortex')
                    elif key == 'q':
                        print("\nShutdown requested by user")
                        self.ShutdownEvent = True
            else:
                # Unix-like systems can use select()
                if select.select([sys.stdin], [], [], 0) == ([sys.stdin], [], []):
                    line = sys.stdin.readline().strip().lower()
                    if line == '1':
                        self.PrivateResetService('TranscodeService')
                    elif line == '2':
                        self.PrivateResetService('QualityCompareService')
                    elif line == '3':
                        self.PrivateResetService('MediaVortex')
                    elif line == 'q':
                        print("\nShutdown requested by user")
                        self.ShutdownEvent = True
        except Exception as e:
            # Ignore input errors to prevent crashes
            pass
    
    def Shutdown(self):
        """Gracefully shutdown the orchestrator."""
        print("SystemOrchestratorService shutdown requested")
        self.ShutdownEvent = True