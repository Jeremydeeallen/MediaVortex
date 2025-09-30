#!/usr/bin/env python3
"""
StopSystemOrchestrator.py
Cross-platform Python script to stop the SystemOrchestratorService and all managed services
Works on both Windows and Linux
"""

import sys
import os
import subprocess
import time
import argparse
import platform
import signal
from pathlib import Path

def GetScriptDirectory():
    """Get the directory containing this script."""
    return Path(__file__).parent.absolute()

def FindSystemOrchestratorProcesses():
    """Find all SystemOrchestratorService processes."""
    try:
        import psutil
        processes = []
        
        for proc in psutil.process_iter(['pid', 'name', 'cmdline']):
            try:
                if proc.info['name'] == 'python':
                    cmdline = ' '.join(proc.info['cmdline']) if proc.info['cmdline'] else ''
                    if 'SystemOrchestratorService' in cmdline and 'Main.py' in cmdline:
                        processes.append(proc.info)
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue
        
        return processes
    except ImportError:
        print("❌ psutil is required. Install it with: pip install psutil")
        sys.exit(1)
    except Exception as e:
        print(f"Warning: Could not find processes: {e}")
        return []

def StopProcess(Pid, Force=False):
    """Stop a process by PID."""
    try:
        if Force:
            print(f"🔨 Force stopping process PID: {Pid}")
            os.kill(Pid, 9)  # SIGKILL
        else:
            print(f"🛑 Gracefully stopping process PID: {Pid}")
            os.kill(Pid, signal.SIGTERM)  # SIGTERM
        
        return True
    except ProcessLookupError:
        print(f"Process PID {Pid} not found (may have already stopped)")
        return True
    except PermissionError:
        print(f"Permission denied stopping process PID {Pid}")
        return False
    except Exception as e:
        print(f"Error stopping process PID {Pid}: {e}")
        return False

def StopAllMediaVortexServices():
    """Stop all MediaVortex-related services."""
    print("🔄 Stopping all MediaVortex services...")
    
    # Find and stop SystemOrchestratorService processes
    OrchestratorProcesses = FindSystemOrchestratorProcesses()
    
    if not OrchestratorProcesses:
        print("✅ No SystemOrchestratorService processes found")
        return True
    
    print(f"Found {len(OrchestratorProcesses)} SystemOrchestratorService process(es)")
    
    # Stop orchestrator processes first
    for proc_info in OrchestratorProcesses:
        Pid = proc_info['pid']
        print(f"Stopping SystemOrchestratorService PID: {Pid}")
        StopProcess(Pid, Force=False)
    
    # Wait for graceful shutdown
    print("⏳ Waiting for graceful shutdown...")
    time.sleep(5)
    
    # Check if processes are still running
    RemainingProcesses = FindSystemOrchestratorProcesses()
    if RemainingProcesses:
        print(f"⚠️  {len(RemainingProcesses)} process(es) still running, force stopping...")
        for proc_info in RemainingProcesses:
            Pid = proc_info['pid']
            StopProcess(Pid, Force=True)
    
    # Final check
    FinalCheck = FindSystemOrchestratorProcesses()
    if FinalCheck:
        print(f"❌ {len(FinalCheck)} process(es) still running after force stop:")
        for proc_info in FinalCheck:
            print(f"  PID: {proc_info['pid']}")
        return False
    else:
        print("✅ All SystemOrchestratorService processes stopped")
        return True

def Main():
    """Main entry point."""
    parser = argparse.ArgumentParser(description='Stop SystemOrchestratorService and all managed services')
    parser.add_argument('--force', '-f', action='store_true', help='Force stop all processes')
    parser.add_argument('--verbose', '-v', action='store_true', help='Verbose output')
    
    args = parser.parse_args()
    
    print("=" * 60)
    print("MediaVortex System Orchestrator - Shutdown")
    print("=" * 60)
    print(f"Platform: {platform.system()} {platform.release()}")
    print(f"Python: {sys.version}")
    print()
    
    if args.force:
        print("🔨 Force mode enabled - all processes will be force killed")
    
    # Stop all services
    Success = StopAllMediaVortexServices()
    
    if Success:
        print("✅ All MediaVortex services stopped successfully")
    else:
        print("❌ Some services may still be running")
        sys.exit(1)

if __name__ == "__main__":
    Main()
