#!/usr/bin/env python3
"""
StartSystemOrchestrator.py
Cross-platform Python script to start the SystemOrchestratorService (master controller)
Works on both Windows and Linux
"""

import sys
import os
import subprocess
import time
import argparse
import platform
from pathlib import Path

def GetScriptDirectory():
    """Get the directory containing this script."""
    return Path(__file__).parent.absolute()

def CheckVirtualEnvironment(ServiceDir, ServiceName):
    """Check if virtual environment exists and create if needed."""
    VenvPath = ServiceDir / "venv"
    
    if not VenvPath.exists():
        print(f"Virtual environment not found for {ServiceName}: {VenvPath}")
        print(f"Creating virtual environment...")
        
        try:
            subprocess.run([sys.executable, "-m", "venv", str(VenvPath)], check=True)
            print(f"✅ Virtual environment created: {VenvPath}")
        except subprocess.CalledProcessError as e:
            print(f"❌ Failed to create virtual environment: {e}")
            return False
    
    return True

def GetActivationScript(VenvPath):
    """Get the appropriate activation script for the platform."""
    if platform.system() == "Windows":
        return VenvPath / "Scripts" / "activate.bat"
    else:
        return VenvPath / "bin" / "activate"

def InstallDependencies(ServiceDir, VenvPath):
    """Install dependencies in the virtual environment."""
    RequirementsFile = ServiceDir / "requirements.txt"
    
    if RequirementsFile.exists():
        print(f"Installing dependencies for {ServiceDir.name}...")
        
        # Get the python executable in the virtual environment
        if platform.system() == "Windows":
            PythonExe = VenvPath / "Scripts" / "python.exe"
        else:
            PythonExe = VenvPath / "bin" / "python"
        
        try:
            subprocess.run([str(PythonExe), "-m", "pip", "install", "-r", str(RequirementsFile)], check=True)
            print(f"✅ Dependencies installed for {ServiceDir.name}")
        except subprocess.CalledProcessError as e:
            print(f"❌ Failed to install dependencies: {e}")
            return False
    
    return True

def CheckServiceRunning(ServiceName, MainScript):
    """Check if a service is already running."""
    try:
        # Check for running processes
        for proc in psutil.process_iter(['pid', 'name', 'cmdline']):
            try:
                if proc.info['name'] == 'python':
                    cmdline = ' '.join(proc.info['cmdline']) if proc.info['cmdline'] else ''
                    if str(MainScript) in cmdline:
                        return proc.info['pid']
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue
        return None
    except Exception as e:
        print(f"Warning: Could not check for running processes: {e}")
        return None

def StartService(ServiceDir, ServiceName, MainScript, Background=False):
    """Start a service."""
    VenvPath = ServiceDir / "venv"
    
    # Get the python executable in the virtual environment
    if platform.system() == "Windows":
        PythonExe = VenvPath / "Scripts" / "python.exe"
    else:
        PythonExe = VenvPath / "bin" / "python"
    
    print(f"Starting {ServiceName}...")
    print(f"Working Directory: {ServiceDir}")
    print(f"Python Script: {MainScript}")
    print(f"Python Executable: {PythonExe}")
    
    try:
        if Background:
            print(f"Starting {ServiceName} in background...")
            if platform.system() == "Windows":
                # On Windows, use subprocess with CREATE_NEW_PROCESS_GROUP
                process = subprocess.Popen(
                    [str(PythonExe), str(MainScript)],
                    cwd=str(ServiceDir),
                    creationflags=subprocess.CREATE_NEW_PROCESS_GROUP
                )
            else:
                # On Linux, use nohup or similar
                process = subprocess.Popen(
                    [str(PythonExe), str(MainScript)],
                    cwd=str(ServiceDir),
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    start_new_session=True
                )
            print(f"✅ {ServiceName} started in background (PID: {process.pid})")
        else:
            print(f"Starting {ServiceName} in foreground (Ctrl+C to stop)...")
            subprocess.run([str(PythonExe), str(MainScript)], cwd=str(ServiceDir))
            
    except KeyboardInterrupt:
        print(f"\n{ServiceName} stopped by user")
    except Exception as e:
        print(f"❌ Failed to start {ServiceName}: {e}")
        return False
    
    return True

def Main():
    """Main entry point."""
    parser = argparse.ArgumentParser(description='Start SystemOrchestratorService (MediaVortex Master Controller)')
    parser.add_argument('--background', '-b', action='store_true', help='Start in background')
    parser.add_argument('--force', '-f', action='store_true', help='Force restart if already running')
    parser.add_argument('--verbose', '-v', action='store_true', help='Verbose output')
    
    args = parser.parse_args()
    
    # Import psutil for process checking
    try:
        import psutil
    except ImportError:
        print("❌ psutil is required. Install it with: pip install psutil")
        sys.exit(1)
    
    # Get script directory
    ScriptDir = GetScriptDirectory()
    SystemOrchestratorDir = ScriptDir / "SystemOrchestratorService"
    MainScript = SystemOrchestratorDir / "Main.py"
    
    print("=" * 60)
    print("MediaVortex System Orchestrator")
    print("=" * 60)
    print(f"Platform: {platform.system()} {platform.release()}")
    print(f"Python: {sys.version}")
    print(f"Script Directory: {ScriptDir}")
    print()
    
    # Check if SystemOrchestratorService directory exists
    if not SystemOrchestratorDir.exists():
        print(f"❌ SystemOrchestratorService directory not found: {SystemOrchestratorDir}")
        sys.exit(1)
    
    # Check if main script exists
    if not MainScript.exists():
        print(f"❌ Main script not found: {MainScript}")
        sys.exit(1)
    
    # Check if service is already running
    RunningPid = CheckServiceRunning("SystemOrchestrator", MainScript)
    if RunningPid:
        if not args.force:
            print(f"⚠️  SystemOrchestratorService appears to be already running (PID: {RunningPid})")
            print("Use --force to restart or stop the existing process first")
            sys.exit(1)
        else:
            print(f"🔄 Force restarting SystemOrchestratorService (stopping PID: {RunningPid})")
            try:
                os.kill(RunningPid, 9)  # Force kill
                time.sleep(2)
            except Exception as e:
                print(f"Warning: Could not stop existing process: {e}")
    
    # Check and create virtual environment
    if not CheckVirtualEnvironment(SystemOrchestratorDir, "SystemOrchestratorService"):
        sys.exit(1)
    
    # Install dependencies
    VenvPath = SystemOrchestratorDir / "venv"
    if not InstallDependencies(SystemOrchestratorDir, VenvPath):
        sys.exit(1)
    
    print()
    print("🚀 Starting MediaVortex System Orchestrator...")
    print("This will start all MediaVortex services:")
    print("  - MediaVortex (Web UI on port 5000)")
    print("  - TranscodeService (Transcoding operations)")
    print("  - QualityCompareService (Quality testing)")
    print()
    
    # Start the service
    Success = StartService(SystemOrchestratorDir, "SystemOrchestratorService", MainScript, args.background)
    
    if Success:
        print("✅ SystemOrchestratorService startup complete")
        if args.background:
            print("All MediaVortex services should be starting in the background...")
    else:
        print("❌ SystemOrchestratorService startup failed")
        sys.exit(1)

if __name__ == "__main__":
    Main()
