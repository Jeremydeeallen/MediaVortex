#!/usr/bin/env python3
"""
StartAllServices.py
Cross-platform Python script to start all MediaVortex services individually
Alternative to SystemOrchestratorService for manual control
Works on both Windows and Linux
"""

import sys
import os
import subprocess
import time
import argparse
import platform
import threading
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
            return process
        else:
            print(f"Starting {ServiceName} in foreground (Ctrl+C to stop)...")
            subprocess.run([str(PythonExe), str(MainScript)], cwd=str(ServiceDir))
            return None
            
    except KeyboardInterrupt:
        print(f"\n{ServiceName} stopped by user")
        return None
    except Exception as e:
        print(f"❌ Failed to start {ServiceName}: {e}")
        return None

def StartMediaVortex(ScriptDir, Background=False):
    """Start MediaVortex main application."""
    print("\n" + "="*50)
    print("Starting MediaVortex (Main Web Application)")
    print("="*50)
    
    ServiceDir = ScriptDir
    MainScript = ScriptDir / "MediaVortex.py"
    
    if not MainScript.exists():
        print(f"❌ MediaVortex.py not found: {MainScript}")
        return None
    
    return StartService(ServiceDir, "MediaVortex", MainScript, Background)

def StartTranscodeService(ScriptDir, Background=False):
    """Start TranscodeService."""
    print("\n" + "="*50)
    print("Starting TranscodeService")
    print("="*50)
    
    ServiceDir = ScriptDir / "TranscodeService"
    MainScript = ServiceDir / "Main.py"
    
    if not ServiceDir.exists():
        print(f"❌ TranscodeService directory not found: {ServiceDir}")
        return None
    
    if not MainScript.exists():
        print(f"❌ TranscodeService Main.py not found: {MainScript}")
        return None
    
    # Check and create virtual environment
    if not CheckVirtualEnvironment(ServiceDir, "TranscodeService"):
        return None
    
    # Install dependencies
    VenvPath = ServiceDir / "venv"
    if not InstallDependencies(ServiceDir, VenvPath):
        return None
    
    return StartService(ServiceDir, "TranscodeService", MainScript, Background)

def StartQualityCompareService(ScriptDir, Background=False):
    """Start QualityCompareService."""
    print("\n" + "="*50)
    print("Starting QualityCompareService")
    print("="*50)
    
    ServiceDir = ScriptDir / "QualityCompareService"
    MainScript = ServiceDir / "Main.py"
    
    if not ServiceDir.exists():
        print(f"❌ QualityCompareService directory not found: {ServiceDir}")
        return None
    
    if not MainScript.exists():
        print(f"❌ QualityCompareService Main.py not found: {MainScript}")
        return None
    
    # Check and create virtual environment
    if not CheckVirtualEnvironment(ServiceDir, "QualityCompareService"):
        return None
    
    # Install dependencies
    VenvPath = ServiceDir / "venv"
    if not InstallDependencies(ServiceDir, VenvPath):
        return None
    
    return StartService(ServiceDir, "QualityCompareService", MainScript, Background)

def Main():
    """Main entry point."""
    parser = argparse.ArgumentParser(description='Start all MediaVortex services individually')
    parser.add_argument('--background', '-b', action='store_true', help='Start all services in background')
    parser.add_argument('--mediavortex-only', action='store_true', help='Start only MediaVortex')
    parser.add_argument('--transcode-only', action='store_true', help='Start only TranscodeService')
    parser.add_argument('--quality-only', action='store_true', help='Start only QualityCompareService')
    parser.add_argument('--verbose', '-v', action='store_true', help='Verbose output')
    
    args = parser.parse_args()
    
    # Get script directory
    ScriptDir = GetScriptDirectory()
    
    print("=" * 60)
    print("MediaVortex Services - Individual Startup")
    print("=" * 60)
    print(f"Platform: {platform.system()} {platform.release()}")
    print(f"Python: {sys.version}")
    print(f"Script Directory: {ScriptDir}")
    print()
    
    processes = []
    
    try:
        # Start services based on arguments
        if args.mediavortex_only:
            process = StartMediaVortex(ScriptDir, args.background)
            if process:
                processes.append(("MediaVortex", process))
        elif args.transcode_only:
            process = StartTranscodeService(ScriptDir, args.background)
            if process:
                processes.append(("TranscodeService", process))
        elif args.quality_only:
            process = StartQualityCompareService(ScriptDir, args.background)
            if process:
                processes.append(("QualityCompareService", process))
        else:
            # Start all services
            print("🚀 Starting all MediaVortex services...")
            print("Services will start in this order:")
            print("  1. MediaVortex (Web UI on port 5000)")
            print("  2. TranscodeService (Transcoding operations)")
            print("  3. QualityCompareService (Quality testing)")
            print()
            
            # Start MediaVortex first
            process = StartMediaVortex(ScriptDir, args.background)
            if process:
                processes.append(("MediaVortex", process))
            
            # Wait a moment for MediaVortex to start
            if args.background:
                print("⏳ Waiting for MediaVortex to start...")
                time.sleep(5)
            
            # Start TranscodeService
            process = StartTranscodeService(ScriptDir, args.background)
            if process:
                processes.append(("TranscodeService", process))
            
            # Start QualityCompareService
            process = StartQualityCompareService(ScriptDir, args.background)
            if process:
                processes.append(("QualityCompareService", process))
        
        if args.background:
            print(f"\n✅ Started {len(processes)} service(s) in background")
            print("Services are running. Use StopAllServices.py to stop them.")
        else:
            print("\n✅ All services started in foreground")
            print("Press Ctrl+C to stop all services")
            
            # Wait for keyboard interrupt
            try:
                while True:
                    time.sleep(1)
            except KeyboardInterrupt:
                print("\n🛑 Stopping all services...")
                for service_name, process in processes:
                    if process:
                        print(f"Stopping {service_name}...")
                        process.terminate()
                        process.wait()
                print("✅ All services stopped")
    
    except Exception as e:
        print(f"❌ Error starting services: {e}")
        sys.exit(1)

if __name__ == "__main__":
    Main()
