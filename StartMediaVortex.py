"""
StartMediaVortex - Simple orchestrator for MediaVortex services
Starts all three services and exits
"""

import subprocess
import sys
import os
import platform
import time
from datetime import datetime

class MediaVortexOrchestrator:
    """Simple orchestrator for MediaVortex services."""
    
    def __init__(self):
        """Initialize the orchestrator."""
        self.RootDir = os.path.dirname(os.path.abspath(__file__))
        self.LockFile = '.mediavortex_startup.lock'
        
        # Define services
        self.ServiceConfigs = {
            'WebService': {
                'Directory': os.path.join(self.RootDir, 'WebService'),
                'MainScript': 'Main.py'
            },
            'TranscodeService': {
                'Directory': os.path.join(self.RootDir, 'TranscodeService'),
                'MainScript': 'Main.py'
            },
            'QualityTestService': {
                'Directory': os.path.join(self.RootDir, 'QualityTestService'),
                'MainScript': 'Main.py'
            }
        }
    
    def AcquireLock(self) -> bool:
        """Simple file lock to prevent multiple orchestrators."""
        try:
            if os.path.exists(self.LockFile):
                print("MediaVortex is already starting!")
                return False
            
            # Create lock file
            with open(self.LockFile, 'w') as f:
                f.write(str(os.getpid()))
            return True
        except Exception:
            return False
    
    def StartAllServices(self):
        """Start all services and exit."""
        if not self.AcquireLock():
            return False
        
        print("Starting MediaVortex services...")
        
        # Start services in order
        startup_order = ['WebService', 'TranscodeService', 'QualityTestService']
        
        for service_name in startup_order:
            self.StartService(service_name)
            time.sleep(2)  # Give each service time to start
        
        # Clean up lock file
        try:
            os.remove(self.LockFile)
        except:
            pass
        
        print("All services started. Orchestrator exiting.")
        return True
    
    def StartService(self, service_name: str):
        print(f"DEBUG: StartService called for {service_name} at {datetime.now()}")
        """Start a service and detach it."""
        config = self.ServiceConfigs[service_name]
        
        # Determine Python executable
        if platform.system() == "Windows":
            python_exe = os.path.join(config['Directory'], "venv", "Scripts", "python.exe")
        else:
            python_exe = os.path.join(config['Directory'], "venv", "bin", "python")
        
        try:
            # Start service as detached process
            process = subprocess.Popen(
                [python_exe, config['MainScript']],
                cwd=config['Directory'],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                creationflags=subprocess.CREATE_NEW_PROCESS_GROUP if platform.system() == "Windows" else 0
            )
            print(f"Started {service_name} with PID {process.pid}")
        except Exception as e:
            print(f"Failed to start {service_name}: {e}")

def main():
    """Main entry point."""
    print("MediaVortex Service Orchestrator")
    print("================================")
    
    orchestrator = MediaVortexOrchestrator()
    orchestrator.StartAllServices()

if __name__ == "__main__":
    main()