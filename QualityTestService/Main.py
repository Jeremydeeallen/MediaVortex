#!/usr/bin/env python3
"""
QualityTestService Entry Point
Standalone quality testing microservice for MediaVortex
"""

import sys
import signal
import os
import setproctitle
from App import QualityTestServiceApp

# Set process title for better visibility in Task Manager
setproctitle.setproctitle("QualityTestService")

# Add parent directory to path to import shared services
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from Services.LoggingService import LoggingService

def SignalHandler(signum, frame):
    """Handle shutdown signals gracefully."""
    LoggingService.LogInfo(f"Received signal {signum}, shutting down gracefully...", "QualityTestService", "SignalHandler")
    if hasattr(Main, 'app') and Main.app:
        Main.app.Shutdown()
    sys.exit(0)

def Main():
    """Main entry point for QualityTestService."""
    try:
        LoggingService.LogInfo("Starting QualityTestService...", "QualityTestService", "main")
        
        # Initialize the application
        app = QualityTestServiceApp()
        Main.app = app  # Store reference for signal handler
        
        # Register signal handlers
        signal.signal(signal.SIGINT, SignalHandler)
        signal.signal(signal.SIGTERM, SignalHandler)
        
        # Start the service (this will run indefinitely)
        LoggingService.LogInfo("QualityTestService is now running. Press Ctrl+C to stop.", "QualityTestService", "main")
        app.Run()
        
    except KeyboardInterrupt:
        LoggingService.LogInfo("Received keyboard interrupt, shutting down...", "QualityTestService", "main")
        if hasattr(Main, 'app') and Main.app:
            Main.app.Shutdown()
    except Exception as e:
        LoggingService.LogException("Fatal error in QualityTestService", e, "QualityTestService", "main")
        sys.exit(1)
    finally:
        LoggingService.LogInfo("QualityTestService stopped.", "QualityTestService", "main")

if __name__ == "__main__":
    Main()
