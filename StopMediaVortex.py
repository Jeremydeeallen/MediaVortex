"""
StopMediaVortex - Simple script to stop MediaVortex services
Finds and stops all MediaVortex processes
"""

import os
import signal
import platform
import time
import subprocess

class MediaVortexStopper:
    """Simple stopper for MediaVortex services."""
    
    def __init__(self):
        self.LockFile = '.mediavortex_startup.lock'
    
    def StopAllServices(self):
        """Stop all MediaVortex services."""
        print("Stopping MediaVortex services...")
        
        # Find and stop MediaVortex processes
        processes = self.FindMediaVortexProcesses()
        
        if not processes:
            print("No MediaVortex services found running.")
            return True
        
        print(f"Found {len(processes)} MediaVortex processes:")
        for pid, name in processes:
            print(f"  PID {pid}: {name}")
        
        # Stop processes
        for pid, name in processes:
            self.StopProcess(pid, name)
        
        # Clean up lock file
        try:
            if os.path.exists(self.LockFile):
                os.remove(self.LockFile)
                print("Lock file removed.")
        except Exception as e:
            print(f"Could not remove lock file: {e}")
        
        print("All services stopped.")
        return True
    
    def FindMediaVortexProcesses(self):
        """Find MediaVortex processes."""
        processes = []
        try:
            import psutil
            for proc in psutil.process_iter(['pid', 'name', 'cmdline']):
                try:
                    if proc.info['name'] == 'python.exe' or proc.info['name'] == 'python':
                        cmdline = proc.info.get('cmdline', [])
                        if cmdline:
                            # Check if any of our service scripts are running
                            for service_name in ['WebService', 'TranscodeService', 'QualityTestService']:
                                if any(service_name in arg for arg in cmdline):
                                    processes.append((proc.info['pid'], service_name))
                                    break
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    continue
        except ImportError:
            print("psutil not available, using basic process detection...")
            # Fallback to basic detection
            if platform.system() == "Windows":
                try:
                    result = subprocess.run(['tasklist', '/FI', 'IMAGENAME eq python.exe'], 
                                          capture_output=True, text=True)
                    # This is a simplified fallback
                    pass
                except Exception:
                    pass
        
        return processes
    
    def StopProcess(self, pid: int, name: str):
        """Stop a specific process."""
        try:
            print(f"Stopping {name} (PID: {pid})...")
            
            # Try graceful shutdown first
            if platform.system() == "Windows":
                os.kill(pid, signal.SIGTERM)
            else:
                os.kill(pid, signal.SIGTERM)
            
            # Wait for graceful shutdown
            time.sleep(3)
            
            # Check if still running and force kill if needed
            if self.IsProcessRunning(pid):
                print(f"Force killing {name} (PID: {pid})...")
                if platform.system() == "Windows":
                    os.kill(pid, signal.SIGKILL)
                else:
                    os.kill(pid, signal.SIGKILL)
                time.sleep(1)
            
            if not self.IsProcessRunning(pid):
                print(f"{name} stopped successfully.")
            else:
                print(f"Failed to stop {name} (PID: {pid})")
                
        except (OSError, ProcessLookupError):
            print(f"{name} (PID: {pid}) is not running.")
        except Exception as e:
            print(f"Error stopping {name} (PID: {pid}): {e}")
    
    def IsProcessRunning(self, pid: int) -> bool:
        """Check if a process is running."""
        try:
            if platform.system() == "Windows":
                result = subprocess.run(['tasklist', '/FI', f'PID eq {pid}'], 
                                      capture_output=True, text=True)
                return str(pid) in result.stdout
            else:
                os.kill(pid, 0)  # Check if process exists
                return True
        except (OSError, subprocess.SubprocessError):
            return False

def main():
    """Main entry point."""
    print("MediaVortex Service Stopper")
    print("===========================")
    
    stopper = MediaVortexStopper()
    stopper.StopAllServices()

if __name__ == "__main__":
    main()