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
        
        # QualityCompareService handles quality testing
        # (QualityTestingService was renamed to QualityCompareService)
        
        return services
    
    def PrivateRegisterSystemOrchestratorService(self):
        """Register SystemOrchestratorService in the database."""
        try:
            print("Registering SystemOrchestratorService in database...")
            
            # Create service status entry in database
            service_status = {
                'ServiceName': 'SystemOrchestratorService',
                'Status': 'Running',
                'HealthStatus': 'Healthy',
                'StartTime': datetime.now().isoformat(),
                'LastHealthCheck': datetime.now().isoformat(),
                'UptimeSeconds': 0,
                'MemoryUsage': 0.0,
                'CPUUsage': 0.0,
                'DatabaseConnection': True,
                'DiskSpace': 0.0,
                'ErrorCount': 0,
                'MaxErrors': 10,
                'ActiveJobsCount': 0,
                'IsProcessing': False,
                'LastErrorMessage': None,
                'ProcessId': os.getpid(),
                'Version': '1.0.0',
                'ServiceType': 'Orchestrator'
            }
            
            # Save to database
            import sys
            import os
            # Add parent directory to path to access Repositories module
            parent_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            if parent_dir not in sys.path:
                sys.path.insert(0, parent_dir)
            
            from Repositories.DatabaseManager import DatabaseManager
            db_manager = DatabaseManager()
            success = db_manager.SaveServiceStatus(service_status)
            
            if success:
                print("✅ SystemOrchestratorService registered in database")
            else:
                print("❌ Failed to register SystemOrchestratorService in database")
                
        except Exception as e:
            print(f"❌ Error registering SystemOrchestratorService in database: {e}")
    
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
        """Start MediaVortex and initialize other services in database."""
        print("Starting MediaVortex and initializing service database entries...")
        
        # Start MediaVortex first (web service)
        self.PrivateStartService(self.ManagedServices['MediaVortex'])
        
        # Wait for MediaVortex to start
        print("Waiting for MediaVortex to start...")
        time.sleep(5)
        
        # Initialize other services in database as "Stopped" - they will be started via web GUI
        print("Initializing TranscodeService and QualityCompareService in database as 'Stopped'...")
        self.PrivateInitializeServiceInDatabase('TranscodeService')
        self.PrivateInitializeServiceInDatabase('QualityCompareService')
        
        print("MediaVortex started. Other services can be started via web GUI.")
    
    def PrivateInitializeServiceInDatabase(self, service_name: str):
        """Initialize a service in the database as 'Stopped' without starting the process."""
        try:
            print(f"Initializing {service_name} in database as 'Stopped'...")
            
            # Create service status entry in database
            service_status = {
                'ServiceName': service_name,
                'Status': 'Stopped',
                'HealthStatus': 'Stopped',
                'StartTime': datetime.now().isoformat(),
                'LastHealthCheck': datetime.now().isoformat(),
                'UptimeSeconds': 0,
                'MemoryUsage': 0.0,
                'CPUUsage': 0.0,
                'DatabaseConnection': True,
                'DiskSpace': 0.0,
                'ErrorCount': 0,
                'MaxErrors': 10,
                'ActiveJobsCount': 0,
                'IsProcessing': False,
                'LastErrorMessage': None,
                'ProcessId': 0,  # No process running
                'Version': '1.0.0',
                'ServiceType': 'Microservice'
            }
            
            # Save to database
            import sys
            import os
            # Add parent directory to path to access Repositories module
            parent_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            if parent_dir not in sys.path:
                sys.path.insert(0, parent_dir)
            
            from Repositories.DatabaseManager import DatabaseManager
            db_manager = DatabaseManager()
            success = db_manager.SaveServiceStatus(service_status)
            
            if success:
                print(f"✅ {service_name} initialized in database as 'Stopped'")
            else:
                print(f"❌ Failed to initialize {service_name} in database")
                
        except Exception as e:
            print(f"❌ Error initializing {service_name} in database: {e}")
    
    def StartServiceOnDemand(self, service_name: str) -> bool:
        """Start a service on demand via web GUI."""
        try:
            if service_name not in self.ManagedServices:
                print(f"❌ Unknown service: {service_name}")
                return False
            
            service_info = self.ManagedServices[service_name]
            print(f"Starting {service_name} on demand...")
            
            # Start the service
            self.PrivateStartService(service_info)
            
            print(f"✅ {service_name} started successfully")
            return True
            
        except Exception as e:
            print(f"❌ Error starting {service_name} on demand: {e}")
            return False
    
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
            print(f"[SUCCESS] {service_info.Name} started (PID: {service_info.Process.pid})")
            
            # Update service status in database with actual PID
            self.PrivateUpdateServiceStatusWithPID(service_info.Name, "Running", "Healthy", service_info.Process.pid)
            
        except Exception as e:
            print(f"[ERROR] Failed to start {service_info.Name}: {e}")
            # Update status to error if startup failed
            self.PrivateUpdateServiceStatusWithPID(service_info.Name, "Error", "Unhealthy", 0)
    
    def PrivateMainLoop(self):
        """Main monitoring loop."""
        print("SystemOrchestratorService is now running.")
        print("Commands:")
        print("  Press 1 to reset TranscodeService")
        print("  Press 2 to reset QualityCompareService")
        print("  Press 3 to reset SystemOrchestratorService")
        print("  Press 4 to reset MediaVortex")
        print("  Press 5 to graceful stop TranscodeService")
        print("  Press 6 to graceful stop QualityCompareService")
        print("  Press 7 to graceful stop SystemOrchestratorService")
        print("  Press 8 to graceful stop MediaVortex")
        print("  Press 9 to graceful stop all services")
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
                            # Check if this was a graceful stop
                            if self.PrivateIsServiceGracefullyStopped(service_name):
                                print(f"[SUCCESS] {service_name} has gracefully stopped (exit code: {returncode})")
                                service_info.Process = None  # Clear the process reference
                            else:
                                print(f"[WARNING] {service_name} has stopped unexpectedly (exit code: {returncode}), restarting...")
                            self.PrivateStartService(service_info)
                
                # Process pending service commands
                self.PrivateProcessServiceCommands()
                
                # Handle user input
                self.PrivateHandleUserInput()
                
                # Wait a bit before checking again (reduced for more responsive input)
                time.sleep(0.1)  # Much more responsive input handling
                
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
                # Check for multiple key presses in a short burst to catch rapid input
                keys_pressed = []
                while msvcrt.kbhit():
                    try:
                        key = msvcrt.getch().decode('utf-8').lower()
                        keys_pressed.append(key)
                    except:
                        # Skip invalid characters
                        msvcrt.getch()
                
                # Process the last key pressed (most recent command)
                if keys_pressed:
                    key = keys_pressed[-1]  # Use the most recent key press
                    # Echo the input immediately
                    print(f"\n[INPUT] Command received: '{key}'")
                    
                    if key == '1':
                        print("[ACTION] Resetting TranscodeService...")
                        self.PrivateResetService('TranscodeService')
                    elif key == '2':
                        print("[ACTION] Resetting QualityCompareService...")
                        self.PrivateResetService('QualityCompareService')
                    elif key == '3':
                        print("[ACTION] Resetting SystemOrchestratorService...")
                        self.PrivateResetService('SystemOrchestratorService')
                    elif key == '4':
                        print("[ACTION] Resetting MediaVortex...")
                        self.PrivateResetService('MediaVortex')
                    elif key == '5':
                        print("[ACTION] Graceful stop TranscodeService...")
                        self.PrivateGracefulStopService('TranscodeService')
                    elif key == '6':
                        print("[ACTION] Graceful stop QualityCompareService...")
                        self.PrivateGracefulStopService('QualityCompareService')
                    elif key == '7':
                        print("[ACTION] Graceful stop SystemOrchestratorService...")
                        self.PrivateGracefulStopService('SystemOrchestratorService')
                    elif key == '8':
                        print("[ACTION] Graceful stop MediaVortex...")
                        self.PrivateGracefulStopService('MediaVortex')
                    elif key == '9':
                        print("[ACTION] Graceful stop all services...")
                        self.PrivateGracefulStopAllServices()
                    elif key == 'q':
                        print("\n[SHUTDOWN] Shutdown requested by user")
                        self.ShutdownEvent = True
                    else:
                        print(f"[ERROR] Unknown command: '{key}'. Press 1-7 or q")
                    
                    # Show the menu again after command
                    print("\nCommands:")
                    print("  Press 1 to reset TranscodeService")
                    print("  Press 2 to reset QualityCompareService")
                    print("  Press 3 to reset SystemOrchestratorService")
                    print("  Press 4 to reset MediaVortex")
                    print("  Press 5 to graceful stop TranscodeService")
                    print("  Press 6 to graceful stop QualityCompareService")
                    print("  Press 7 to graceful stop SystemOrchestratorService")
                    print("  Press 8 to graceful stop MediaVortex")
                    print("  Press 9 to graceful stop all services")
                    print("  Press q to quit")
                    print()
            else:
                # Unix-like systems can use select()
                if select.select([sys.stdin], [], [], 0) == ([sys.stdin], [], []):
                    line = sys.stdin.readline().strip().lower()
                    # Echo the input immediately
                    print(f"\n[INPUT] Command received: '{line}'")
                    
                    if line == '1':
                        print("[ACTION] Resetting TranscodeService...")
                        self.PrivateResetService('TranscodeService')
                    elif line == '2':
                        print("[ACTION] Resetting QualityCompareService...")
                        self.PrivateResetService('QualityCompareService')
                    elif line == '3':
                        print("[ACTION] Resetting SystemOrchestratorService...")
                        self.PrivateResetService('SystemOrchestratorService')
                    elif line == '4':
                        print("[ACTION] Resetting MediaVortex...")
                        self.PrivateResetService('MediaVortex')
                    elif line == '5':
                        print("[ACTION] Graceful stop TranscodeService...")
                        self.PrivateGracefulStopService('TranscodeService')
                    elif line == '6':
                        print("[ACTION] Graceful stop QualityCompareService...")
                        self.PrivateGracefulStopService('QualityCompareService')
                    elif line == '7':
                        print("[ACTION] Graceful stop SystemOrchestratorService...")
                        self.PrivateGracefulStopService('SystemOrchestratorService')
                    elif line == '8':
                        print("[ACTION] Graceful stop MediaVortex...")
                        self.PrivateGracefulStopService('MediaVortex')
                    elif line == '9':
                        print("[ACTION] Graceful stop all services...")
                        self.PrivateGracefulStopAllServices()
                    elif line == 'q':
                        print("\n[SHUTDOWN] Shutdown requested by user")
                        self.ShutdownEvent = True
                    else:
                        print(f"[ERROR] Unknown command: '{line}'. Press 1-7 or q")
                    
                    # Show the menu again after command
                    print("\nCommands:")
                    print("  Press 1 to reset TranscodeService")
                    print("  Press 2 to reset QualityCompareService")
                    print("  Press 3 to reset SystemOrchestratorService")
                    print("  Press 4 to reset MediaVortex")
                    print("  Press 5 to graceful stop TranscodeService")
                    print("  Press 6 to graceful stop QualityCompareService")
                    print("  Press 7 to graceful stop SystemOrchestratorService")
                    print("  Press 8 to graceful stop MediaVortex")
                    print("  Press 9 to graceful stop all services")
                    print("  Press q to quit")
                    print()
        except Exception as e:
            # Log input errors but don't crash
            print(f"[WARNING] Input handling error: {e}")
            pass
    
    def PrivateGracefulStopService(self, service_name: str):
        """Send graceful stop command to a specific service."""
        if service_name not in self.ManagedServices:
            print(f"[ERROR] Unknown service: {service_name}")
            return False
        
        service_info = self.ManagedServices[service_name]
        print(f"[ACTION] Stopping {service_name}...")
        
        try:
            # Update service status to "GracefulStop" in database
            self.PrivateUpdateServiceStatus(service_name, "GracefulStop", "Stopping")
            
            # Actually terminate the process
            if service_info.Process and service_info.Process.poll() is None:
                print(f"[ACTION] Terminating {service_name} process...")
                service_info.Process.terminate()
                
                # Wait for graceful shutdown
                try:
                    service_info.Process.wait(timeout=10)
                    print(f"[SUCCESS] {service_name} stopped gracefully")
                except subprocess.TimeoutExpired:
                    print(f"[WARNING] {service_name} did not stop gracefully, force killing...")
                    service_info.Process.kill()
                    service_info.Process.wait()
                    print(f"[SUCCESS] {service_name} force killed")
                
                service_info.Process = None
            
            print(f"[SUCCESS] {service_name} stopped")
            return True
            
        except Exception as e:
            print(f"[ERROR] Error stopping {service_name}: {e}")
            return False
    
    def PrivateGracefulStopAllServices(self):
        """Send graceful stop command to all services."""
        print("[ACTION] Sending graceful stop command to all services...")
        
        success_count = 0
        for service_name in self.ManagedServices.keys():
            if self.PrivateGracefulStopService(service_name):
                success_count += 1
        
        print(f"[SUCCESS] Graceful stop commands sent to {success_count}/{len(self.ManagedServices)} services")
        print("   Services will stop after completing current operations")
        return success_count > 0
    
    def PrivateUpdateServiceStatus(self, service_name: str, status: str, health_status: str = "Unknown"):
        """Update service status in database."""
        try:
            import sys
            import os
            # Add parent directory to path to access Repositories module
            parent_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            if parent_dir not in sys.path:
                sys.path.insert(0, parent_dir)
            
            from Repositories.DatabaseManager import DatabaseManager
            
            # Prepare service status data
            service_status = {
                'ServiceName': service_name,
                'Status': status,
                'HealthStatus': health_status,
                'StartTime': datetime.now().isoformat(),
                'LastHealthCheck': datetime.now().isoformat(),
                'UptimeSeconds': 0,
                'MemoryUsage': 0.0,
                'CPUUsage': 0.0,
                'DatabaseConnection': True,
                'DiskSpace': 0.0,
                'ErrorCount': 0,
                'MaxErrors': 10,
                'ActiveJobsCount': 0,
                'IsProcessing': False,
                'LastErrorMessage': None,
                'ProcessId': 0,
                'Version': '1.0.0',
                'ServiceType': 'Microservice'
            }
            
            # Save to database
            db_manager = DatabaseManager()
            success = db_manager.SaveServiceStatus(service_status)
            
            if success:
                print(f"[INFO] Updated {service_name} status to: {status}")
            else:
                print(f"[WARNING] Failed to update {service_name} status in database")
                
            return success
            
        except Exception as e:
            print(f"[ERROR] Error updating service status: {e}")
            return False
    
    def PrivateUpdateServiceStatusWithPID(self, service_name: str, status: str, health_status: str = "Unknown", process_id: int = 0):
        """Update service status in database with actual process ID."""
        try:
            import sys
            import os
            # Add parent directory to path to access Repositories module
            parent_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            if parent_dir not in sys.path:
                sys.path.insert(0, parent_dir)
            
            from Repositories.DatabaseManager import DatabaseManager
            
            # Prepare service status data with actual PID
            service_status = {
                'ServiceName': service_name,
                'Status': status,
                'HealthStatus': health_status,
                'StartTime': datetime.now().isoformat(),
                'LastHealthCheck': datetime.now().isoformat(),
                'UptimeSeconds': 0,
                'MemoryUsage': 0.0,
                'CPUUsage': 0.0,
                'DatabaseConnection': True,
                'DiskSpace': 0.0,
                'ErrorCount': 0,
                'MaxErrors': 10,
                'ActiveJobsCount': 0,
                'IsProcessing': False,
                'LastErrorMessage': None,
                'ProcessId': process_id,  # Use actual PID
                'Version': '1.0.0',
                'ServiceType': 'Microservice'
            }
            
            # Save to database
            db_manager = DatabaseManager()
            success = db_manager.SaveServiceStatus(service_status)
            
            if success:
                print(f"[INFO] Updated {service_name} status to: {status} (PID: {process_id})")
            else:
                print(f"[WARNING] Failed to update {service_name} status in database")
                
            return success
            
        except Exception as e:
            print(f"[ERROR] Error updating service status: {e}")
            return False
    
    def PrivateIsServiceGracefullyStopped(self, service_name: str) -> bool:
        """Check if a service was gracefully stopped by checking database status."""
        try:
            import sys
            import os
            # Add parent directory to path to access Repositories module
            parent_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            if parent_dir not in sys.path:
                sys.path.insert(0, parent_dir)
            
            from Repositories.DatabaseManager import DatabaseManager
            
            db_manager = DatabaseManager()
            service_status = db_manager.GetServiceStatus(service_name)
            
            if service_status and service_status.get('Status') == 'GracefulStop':
                # Update status to "Stopped" since the process has actually stopped
                self.PrivateUpdateServiceStatus(service_name, "Stopped", "Stopped")
                return True
            
            return False
            
        except Exception as e:
            print(f"[WARNING] Error checking graceful stop status for {service_name}: {e}")
            return False
    
    def PrivateSendSignalToService(self, service_name: str, signal_type: str) -> bool:
        """Send a signal to a service using its PID from the database."""
        try:
            import sys
            import os
            # Add parent directory to path to access Repositories module
            parent_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            if parent_dir not in sys.path:
                sys.path.insert(0, parent_dir)
            
            from Repositories.DatabaseManager import DatabaseManager
            
            # Get service status from database to get PID
            db_manager = DatabaseManager()
            service_status = db_manager.GetServiceStatus(service_name)
            
            if not service_status:
                print(f"[ERROR] Service {service_name} not found in database")
                return False
            
            process_id = service_status.get('ProcessId', 0)
            if process_id == 0:
                print(f"[ERROR] No valid PID found for service {service_name}")
                return False
            
            # Send signal to process
            try:
                if platform.system() == "Windows":
                    # Windows signal handling
                    if signal_type == "SIGTERM":
                        os.kill(process_id, signal.SIGTERM)
                    elif signal_type == "SIGINT":
                        os.kill(process_id, signal.SIGINT)
                    elif signal_type == "SIGKILL":
                        os.kill(process_id, signal.SIGKILL)
                    else:
                        print(f"[ERROR] Unsupported signal type: {signal_type}")
                        return False
                else:
                    # Unix signal handling
                    if signal_type == "SIGTERM":
                        os.kill(process_id, signal.SIGTERM)
                    elif signal_type == "SIGINT":
                        os.kill(process_id, signal.SIGINT)
                    elif signal_type == "SIGKILL":
                        os.kill(process_id, signal.SIGKILL)
                    else:
                        print(f"[ERROR] Unsupported signal type: {signal_type}")
                        return False
                
                print(f"[SUCCESS] Sent {signal_type} to {service_name} (PID: {process_id})")
                return True
                
            except ProcessLookupError:
                print(f"[ERROR] Process {process_id} for {service_name} not found")
                # Update database to reflect process is no longer running
                self.PrivateUpdateServiceStatusWithPID(service_name, "Stopped", "Stopped", 0)
                return False
            except PermissionError:
                print(f"[ERROR] Permission denied to send signal to {service_name} (PID: {process_id})")
                return False
                
        except Exception as e:
            print(f"[ERROR] Error sending signal to {service_name}: {e}")
            return False
    
    def PrivateTerminateServiceByPID(self, service_name: str) -> bool:
        """Terminate a service immediately using its PID."""
        try:
            print(f"[ACTION] Terminating {service_name} immediately...")
            
            # Send SIGKILL to force immediate termination
            success = self.PrivateSendSignalToService(service_name, "SIGKILL")
            
            if success:
                # Update database status
                self.PrivateUpdateServiceStatusWithPID(service_name, "Stopped", "Stopped", 0)
                print(f"[SUCCESS] {service_name} terminated immediately")
            else:
                print(f"[ERROR] Failed to terminate {service_name}")
            
            return success
            
        except Exception as e:
            print(f"[ERROR] Error terminating {service_name}: {e}")
            return False
    
    def PrivateGracefulStopServiceByPID(self, service_name: str) -> bool:
        """Send graceful stop signal to a service using its PID."""
        try:
            print(f"[ACTION] Sending graceful stop to {service_name}...")
            
            # Send SIGTERM for graceful shutdown
            success = self.PrivateSendSignalToService(service_name, "SIGTERM")
            
            if success:
                # Update database status to GracefulStop
                self.PrivateUpdateServiceStatus(service_name, "GracefulStop", "Stopping")
                print(f"[SUCCESS] Graceful stop signal sent to {service_name}")
            else:
                print(f"[ERROR] Failed to send graceful stop to {service_name}")
            
            return success
            
        except Exception as e:
            print(f"[ERROR] Error sending graceful stop to {service_name}: {e}")
            return False
    
    def PrivateProcessServiceCommands(self):
        """Process pending service commands from the database."""
        try:
            from Repositories.DatabaseManager import DatabaseManager
            
            db_manager = DatabaseManager()
            pending_commands = db_manager.GetPendingCommandsForService("SystemOrchestratorService")
            
            for command in pending_commands:
                command_id = command[0]  # Assuming first column is ID
                command_type = command[1]  # Assuming second column is CommandType
                parameters = command[3]  # Assuming fourth column is Parameters
                
                if command_type == "StartService":
                    # Parse parameters (they're stored as string)
                    import json
                    try:
                        params = json.loads(parameters) if isinstance(parameters, str) else parameters
                        service_name = params.get('ServiceName')
                        action = params.get('Action')
                        
                        if service_name and action == 'Start':
                            print(f"[COMMAND] Processing StartService command for {service_name}")
                            
                            # Start the service
                            if service_name in self.ManagedServices:
                                self.PrivateStartService(self.ManagedServices[service_name])
                                
                                # Mark command as completed
                                db_manager.UpdateServiceCommandStatus(command_id, 'Completed', 'Service started successfully')
                                print(f"[SUCCESS] Started {service_name} via command {command_id}")
                            else:
                                # Mark command as failed
                                db_manager.UpdateServiceCommandStatus(command_id, 'Failed', f'Unknown service: {service_name}')
                                print(f"[ERROR] Unknown service: {service_name}")
                        
                    except json.JSONDecodeError:
                        db_manager.UpdateServiceCommandStatus(command_id, 'Failed', 'Invalid parameters format')
                        print(f"[ERROR] Invalid parameters in command {command_id}")
                        
        except Exception as e:
            print(f"[ERROR] Error processing service commands: {e}")
    
    def Shutdown(self):
        """Gracefully shutdown the orchestrator."""
        print("SystemOrchestratorService shutdown requested")
        self.ShutdownEvent = True