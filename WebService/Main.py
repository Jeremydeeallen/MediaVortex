#!/usr/bin/env python3
"""
WebService Entry Point
Main Flask web application for MediaVortex
"""

import sys
import signal
import os
import setproctitle
from App import WebServiceApp

# Set process title for better visibility in Task Manager
setproctitle.setproctitle("WebService")

# Add parent directory to path to import shared services
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from Services.LoggingService import LoggingService

def SignalHandler(signum, frame):
    """Handle shutdown signals gracefully."""
    LoggingService.LogInfo(f"Received signal {signum}, shutting down gracefully...", "WebService", "SignalHandler")
    if hasattr(Main, 'app') and Main.app:
        Main.app.Shutdown()
    sys.exit(0)

def Main():
    """Main entry point for WebService."""
    try:
        LoggingService.LogInfo("Starting WebService...", "WebService", "main")
        
        # Initialize the application
        app = WebServiceApp()
        Main.app = app  # Store reference for signal handler
        
        # Register signal handlers
        signal.signal(signal.SIGINT, SignalHandler)
        signal.signal(signal.SIGTERM, SignalHandler)
        
        # Start the service (this will run indefinitely)
        LoggingService.LogInfo("WebService is now running. Press Ctrl+C to stop.", "WebService", "main")
        app.Run()
        
    except KeyboardInterrupt:
        LoggingService.LogInfo("Received keyboard interrupt, shutting down...", "WebService", "main")
        if hasattr(Main, 'app') and Main.app:
            Main.app.Shutdown()
    except Exception as e:
        LoggingService.LogException("Fatal error in WebService", e, "WebService", "main")
        sys.exit(1)
    finally:
        LoggingService.LogInfo("WebService stopped.", "WebService", "main")

if __name__ == "__main__":
    Main()
