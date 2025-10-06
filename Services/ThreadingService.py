#!/usr/bin/env python3
"""
Threading Service
Service for managing threading operations in quality testing
"""

import sys
import os
import threading
from datetime import datetime

# Add the project root to the Python path
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, project_root)

from Services.LoggingService import LoggingService


class ThreadingService:
    """Threading Service for managing threading operations."""
    
    def __init__(self):
        """Initialize the threading service."""
        self.ActiveThreads = []
        
        LoggingService.LogInfo("ThreadingService initialized", "ThreadingService", "__init__")
    
    def StartThread(self, target, args=(), daemon=True, name=None):
        """Start a new thread."""
        try:
            thread = threading.Thread(target=target, args=args, daemon=daemon, name=name)
            thread.start()
            self.ActiveThreads.append(thread)
            
            LoggingService.LogInfo(f"Started thread: {thread.name}", "ThreadingService", "StartThread")
            return thread
            
        except Exception as e:
            LoggingService.LogException("Error starting thread", e, "ThreadingService", "StartThread")
            return None
    
    def MonitorProgress(self, Process, JobId: int, DatabaseManager, callback=None):
        """Monitor FFmpeg progress in a separate thread."""
        try:
            def progress_monitor():
                try:
                    import re
                    
                    # Initial progress record
                    progress_data = {
                        'TranscodeAttemptId': 0,
                        'Status': 'Running',
                        'CurrentStep': 'VMAF analysis starting',
                        'StartTime': datetime.now().isoformat(),
                        'ProgressPercentage': 0,
                        'CurrentFrame': 0,
                        'TotalFrames': 0,
                        'FramesPerSecond': 0.0,
                        'EstimatedTimeRemaining': 0,
                        'ErrorMessage': None,
                        'SubprocessPID': Process.pid,
                        'SubprocessStartTime': datetime.now().isoformat()
                    }
                    DatabaseManager.SaveQualityTestProgress(JobId, progress_data)
                    
                    # Monitor stderr for progress updates
                    while Process.poll() is None:
                        line = Process.stderr.readline()
                        if line:
                            # Parse frame information
                            frame_match = re.search(r'frame=\s*(\d+)', line)
                            fps_match = re.search(r'fps=\s*([\d.]+)', line)
                            
                            if frame_match:
                                current_frame = int(frame_match.group(1))
                                fps = float(fps_match.group(1)) if fps_match else 0.0
                                
                                # Update progress
                                progress_data.update({
                                    'Status': 'Running',
                                    'CurrentStep': f'VMAF analysis in progress - Frame {current_frame}',
                                    'CurrentFrame': current_frame,
                                    'FramesPerSecond': fps,
                                    'ProgressPercentage': min(95, int((current_frame / 1000) * 100))
                                })
                                DatabaseManager.SaveQualityTestProgress(JobId, progress_data)
                                
                                # Call callback if provided
                                if callback:
                                    callback(JobId, progress_data)
                                    
                except Exception as e:
                    LoggingService.LogException("Error in progress monitor thread", e, "ThreadingService", "MonitorProgress")
            
            # Start the progress monitoring thread
            return self.StartThread(progress_monitor, daemon=True, name=f"ProgressMonitor-{JobId}")
            
        except Exception as e:
            LoggingService.LogException("Error starting progress monitor", e, "ThreadingService", "MonitorProgress")
            return None
    
    def WaitForThreads(self, timeout=30):
        """Wait for all active threads to complete."""
        try:
            LoggingService.LogInfo(f"Waiting for {len(self.ActiveThreads)} threads to complete", "ThreadingService", "WaitForThreads")
            
            for thread in self.ActiveThreads[:]:  # Copy list to avoid modification during iteration
                if thread.is_alive():
                    thread.join(timeout=timeout)
                    if thread.is_alive():
                        LoggingService.LogWarning(f"Thread {thread.name} did not complete within timeout", "ThreadingService", "WaitForThreads")
                    else:
                        self.ActiveThreads.remove(thread)
                        LoggingService.LogInfo(f"Thread {thread.name} completed", "ThreadingService", "WaitForThreads")
            
            LoggingService.LogInfo("All threads completed", "ThreadingService", "WaitForThreads")
            return True
            
        except Exception as e:
            LoggingService.LogException("Error waiting for threads", e, "ThreadingService", "WaitForThreads")
            return False
    
    def GetActiveThreadCount(self) -> int:
        """Get the number of active threads."""
        try:
            # Clean up completed threads
            self.ActiveThreads = [t for t in self.ActiveThreads if t.is_alive()]
            return len(self.ActiveThreads)
        except Exception as e:
            LoggingService.LogException("Error getting active thread count", e, "ThreadingService", "GetActiveThreadCount")
            return 0
    
    def Shutdown(self) -> bool:
        """Graceful shutdown of the threading service."""
        try:
            LoggingService.LogInfo("Shutting down ThreadingService", "ThreadingService", "Shutdown")
            
            # Wait for all threads to complete
            self.WaitForThreads()
            
            # Shutdown completed silently
            return True
            
        except Exception as e:
            LoggingService.LogException("Error during threading service shutdown", e, "ThreadingService", "Shutdown")
            return False
