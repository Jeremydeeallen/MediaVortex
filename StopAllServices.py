#!/usr/bin/env python3
"""
StopAllServices.py
Cross-platform Python script to stop all MediaVortex services
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

def FindMediaVortexProcesses():
    """Find all MediaVortex-related processes."""
    try:
        import psutil
        processes = []
        
        for proc in psutil.process_iter(['pid', 'name', 'cmdline']):
            try:
                if proc.info['name'] == 'python':
                    cmdline = ' '.join(proc.info['cmdline']) if proc.info['cmdline'] else ''
                    # Look for MediaVortex-related processes
                    if any(keyword in cmdline for keyword in ['MediaVortex.py', 'TranscodeService', 'QualityCompareService', 'SystemOrchestratorService']):
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
    
    # Find all MediaVortex processes
    Processes = FindMediaVortexProcesses()
    
    if not Processes:
        print("✅ No MediaVortex processes found")
        return True
    
    print(f"Found {len(Processes)} MediaVortex process(es)")
    
    # Stop all processes gracefully first
    for proc_info in Processes:
        Pid = proc_info['pid']
        Cmdline = ' '.join(proc_info['cmdline']) if proc_info['cmdline'] else ''
        print(f"Stopping process PID: {Pid} ({Cmdline[:50]}...)")
        StopProcess(Pid, Force=False)
    
    # Wait for graceful shutdown
    print("⏳ Waiting for graceful shutdown...")
    time.sleep(5)
    
    # Check if processes are still running
    RemainingProcesses = FindMediaVortexProcesses()
    if RemainingProcesses:
        print(f"⚠️  {len(RemainingProcesses)} process(es) still running, force stopping...")
        for proc_info in RemainingProcesses:
            Pid = proc_info['pid']
            StopProcess(Pid, Force=True)
    
    # Final check
    FinalCheck = FindMediaVortexProcesses()
    if FinalCheck:
        print(f"❌ {len(FinalCheck)} process(es) still running after force stop:")
        for proc_info in FinalCheck:
            Cmdline = ' '.join(proc_info['cmdline']) if proc_info['cmdline'] else ''
            print(f"  PID: {proc_info['pid']} ({Cmdline[:50]}...)")
        return False
    else:
        print("✅ All MediaVortex processes stopped")
        return True

def Main():
    """Main entry point."""
    parser = argparse.ArgumentParser(description='Stop all MediaVortex services')
    parser.add_argument('--force', '-f', action='store_true', help='Force stop all processes')
    parser.add_argument('--verbose', '-v', action='store_true', help='Verbose output')
    
    args = parser.parse_args()
    
    print("=" * 60)
    print("MediaVortex Services - Shutdown")
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
