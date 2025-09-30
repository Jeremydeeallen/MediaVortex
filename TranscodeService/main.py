#!/usr/bin/env python3
"""
TranscodeService Entry Point
Standalone transcoding microservice for MediaVortex
"""

import sys
import signal
import os
import setproctitle
from App import TranscodeServiceApp

# Set process title for better visibility in Task Manager
setproctitle.setproctitle("TranscodeService")

# Add parent directory to path to import shared services
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from Services.LoggingService import LoggingService

def SignalHandler(signum, frame):
    """Handle shutdown signals gracefully."""
    LoggingService.LogInfo(f"Received signal {signum}, shutting down gracefully...", "TranscodeService", "SignalHandler")
    if hasattr(Main, 'app') and Main.app:
        Main.app.Shutdown()
    sys.exit(0)

def Main():
    """Main entry point for TranscodeService."""
    try:
        LoggingService.LogInfo("Starting TranscodeService...", "TranscodeService", "main")
        
        # Initialize the application
        app = TranscodeServiceApp()
        Main.app = app  # Store reference for signal handler
        
        # Register signal handlers
        signal.signal(signal.SIGINT, SignalHandler)
        signal.signal(signal.SIGTERM, SignalHandler)
        
        # Start the service (this will run indefinitely)
        LoggingService.LogInfo("TranscodeService is now running. Press Ctrl+C to stop.", "TranscodeService", "main")
        app.Run()
        
    except KeyboardInterrupt:
        LoggingService.LogInfo("Received keyboard interrupt, shutting down...", "TranscodeService", "main")
        if hasattr(Main, 'app') and Main.app:
            Main.app.Shutdown()
    except Exception as e:
        LoggingService.LogException("Fatal error in TranscodeService", e, "TranscodeService", "main")
        sys.exit(1)
    finally:
        LoggingService.LogInfo("TranscodeService stopped.", "TranscodeService", "main")

if __name__ == "__main__":
    Main()
