#!/usr/bin/env python3
"""
Process Management Service
Cross-platform process management utilities for crash recovery
Implements MVVM pattern using MVVM architecture
"""

import os
import signal
import platform
import psutil
from typing import Dict, List, Optional
from Services.LoggingService import LoggingService


class ProcessManagementService:
    """Cross-platform process management utilities."""
    
    def __init__(self):
        """Initialize the process management service."""
        self.Platform = platform.system()
        LoggingService.LogInfo("ProcessManagementService initialized", "ProcessManagementService", "__init__")
    
    def IsProcessRunning(self, ProcessId: int) -> bool:
        """Check if a process with the given PID is currently running."""
        try:
            if ProcessId <= 0:
                return False
            
            # Use psutil to check if process exists and is running
            process = psutil.Process(ProcessId)
            return process.is_running()
            
        except psutil.NoSuchProcess:
            # Process doesn't exist
            return False
        except psutil.AccessDenied:
            # Process exists but we can't access it (permission denied)
            LoggingService.LogWarning(f"Access denied when checking process {ProcessId}", "ProcessManagementService", "IsProcessRunning")
            return True  # Assume it's running if we can't check
        except Exception as e:
            LoggingService.LogException(f"Error checking if process {ProcessId} is running", e, "ProcessManagementService", "IsProcessRunning")
            return False
    
    def KillProcess(self, ProcessId: int, Graceful: bool = True) -> bool:
        """Kill a process by PID. Returns True if successful."""
        try:
            if ProcessId <= 0:
                LoggingService.LogWarning(f"Invalid ProcessId {ProcessId} for kill operation", "ProcessManagementService", "KillProcess")
                return False
            
            process = psutil.Process(ProcessId)
            
            if not process.is_running():
                LoggingService.LogInfo(f"Process {ProcessId} is not running, no need to kill", "ProcessManagementService", "KillProcess")
                return True
            
            if Graceful:
                # Try graceful termination first
                LoggingService.LogInfo(f"Attempting graceful termination of process {ProcessId}", "ProcessManagementService", "KillProcess")
                process.terminate()
                
                # Wait for graceful shutdown
                try:
                    process.wait(timeout=10)  # Wait up to 10 seconds
                    LoggingService.LogInfo(f"Process {ProcessId} terminated gracefully", "ProcessManagementService", "KillProcess")
                    return True
                except psutil.TimeoutExpired:
                    # Force kill if graceful termination times out
                    LoggingService.LogWarning(f"Graceful termination timed out for process {ProcessId}, force killing", "ProcessManagementService", "KillProcess")
                    process.kill()
                    process.wait()
                    LoggingService.LogInfo(f"Process {ProcessId} force killed", "ProcessManagementService", "KillProcess")
                    return True
            else:
                # Force kill immediately
                LoggingService.LogInfo(f"Force killing process {ProcessId}", "ProcessManagementService", "KillProcess")
                process.kill()
                process.wait()
                LoggingService.LogInfo(f"Process {ProcessId} force killed", "ProcessManagementService", "KillProcess")
                return True
                
        except psutil.NoSuchProcess:
            LoggingService.LogInfo(f"Process {ProcessId} no longer exists", "ProcessManagementService", "KillProcess")
            return True  # Process is already dead
        except psutil.AccessDenied:
            LoggingService.LogError(f"Access denied when trying to kill process {ProcessId}", "ProcessManagementService", "KillProcess")
            return False
        except Exception as e:
            LoggingService.LogException(f"Error killing process {ProcessId}", e, "ProcessManagementService", "KillProcess")
            return False
    
    def GetProcessInfo(self, ProcessId: int) -> Optional[Dict]:
        """Get information about a process by PID."""
        try:
            if ProcessId <= 0:
                return None
            
            process = psutil.Process(ProcessId)
            
            return {
                "Pid": process.pid,
                "Name": process.name(),
                "Status": process.status(),
                "CreateTime": process.create_time(),
                "CpuPercent": process.cpu_percent(),
                "MemoryInfo": process.memory_info()._asdict() if hasattr(process.memory_info(), '_asdict') else str(process.memory_info()),
                "Cmdline": " ".join(process.cmdline()) if process.cmdline() else None
            }
            
        except psutil.NoSuchProcess:
            return None
        except psutil.AccessDenied:
            LoggingService.LogWarning(f"Access denied when getting info for process {ProcessId}", "ProcessManagementService", "GetProcessInfo")
            return {"Pid": ProcessId, "Name": "Unknown", "Status": "Access Denied"}
        except Exception as e:
            LoggingService.LogException(f"Error getting process info for {ProcessId}", e, "ProcessManagementService", "GetProcessInfo")
            return None
    
    def FindFFmpegProcesses(self) -> List[Dict]:
        """Find all running FFmpeg processes on the system."""
        try:
            ffmpeg_processes = []
            
            for process in psutil.process_iter(['pid', 'name', 'cmdline']):
                try:
                    process_info = process.info
                    
                    # Check if this is an FFmpeg process
                    if (process_info['name'] and 'ffmpeg' in process_info['name'].lower()) or \
                       (process_info['cmdline'] and any('ffmpeg' in str(cmd).lower() for cmd in process_info['cmdline'])):
                        
                        ffmpeg_processes.append({
                            "Pid": process_info['pid'],
                            "Name": process_info['name'],
                            "Cmdline": " ".join(process_info['cmdline']) if process_info['cmdline'] else None
                        })
                        
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    # Process disappeared or we can't access it
                    continue
            
            LoggingService.LogInfo(f"Found {len(ffmpeg_processes)} FFmpeg processes", "ProcessManagementService", "FindFFmpegProcesses")
            return ffmpeg_processes
            
        except Exception as e:
            LoggingService.LogException("Error finding FFmpeg processes", e, "ProcessManagementService", "FindFFmpegProcesses")
            return []
    
    def KillAllFFmpegProcesses(self) -> int:
        """Kill all FFmpeg processes on the system. Returns count of processes killed."""
        try:
            ffmpeg_processes = self.FindFFmpegProcesses()
            killed_count = 0
            
            for process_info in ffmpeg_processes:
                if self.KillProcess(process_info['Pid'], Graceful=True):
                    killed_count += 1
                    LoggingService.LogInfo(f"Killed FFmpeg process {process_info['Pid']}: {process_info['Name']}", "ProcessManagementService", "KillAllFFmpegProcesses")
            
            LoggingService.LogInfo(f"Killed {killed_count} FFmpeg processes", "ProcessManagementService", "KillAllFFmpegProcesses")
            return killed_count
            
        except Exception as e:
            LoggingService.LogException("Error killing all FFmpeg processes", e, "ProcessManagementService", "KillAllFFmpegProcesses")
            return 0
    
    def GetSystemProcessCount(self) -> int:
        """Get total number of processes running on the system."""
        try:
            return len(psutil.pids())
        except Exception as e:
            LoggingService.LogException("Error getting system process count", e, "ProcessManagementService", "GetSystemProcessCount")
            return 0
