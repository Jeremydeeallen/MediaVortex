"""
SystemOrchestratorService Main Entry Point
Simple process manager for MediaVortex services
"""

import sys
import os
import signal
from App import SystemOrchestratorApp

# Global reference for signal handler
app = None

def SignalHandler(signum, frame):
    """Handle shutdown signals."""
    print("Received shutdown signal, initiating graceful shutdown...")
    if app:
        app.Shutdown()
    sys.exit(0)

def Main():
    """Main entry point for SystemOrchestratorService."""
    global app
    
    try:
        print("Starting SystemOrchestratorService...")
        
        # Initialize the application
        app = SystemOrchestratorApp()
        
        # Register signal handlers
        signal.signal(signal.SIGINT, SignalHandler)
        signal.signal(signal.SIGTERM, SignalHandler)
        
        # Start the orchestrator (this will run indefinitely)
        print("SystemOrchestratorService is now running. Press Ctrl+C to stop.")
        app.Run()
        
    except KeyboardInterrupt:
        print("Received keyboard interrupt, shutting down...")
        if app:
            app.Shutdown()
    except Exception as e:
        print(f"Fatal error in SystemOrchestratorService: {e}")
        sys.exit(1)
    finally:
        print("SystemOrchestratorService stopped.")

if __name__ == "__main__":
    Main()
