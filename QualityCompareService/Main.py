"""
QualityCompareService Main Entry Point
Handles service initialization, signal handling, and graceful shutdown.
"""

import sys
import os
import signal
import threading
from datetime import datetime

# Add parent directory to path to import shared services
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from App import QualityCompareServiceApp
from Services.LoggingService import LoggingService


class QualityCompareServiceMain:
    """Main entry point for QualityCompareService microservice."""
    
    def __init__(self):
        self.App = None
        self.ShutdownEvent = threading.Event()
        self.StartTime = datetime.now()
        self.ProcessId = os.getpid()
        
        # Setup signal handlers
        signal.signal(signal.SIGINT, self.SignalHandler)
        signal.signal(signal.SIGTERM, self.SignalHandler)
        
        LoggingService.LogInfo("QualityCompareServiceMain initialized", "QualityCompareService", "__init__")
    
    def SignalHandler(self, signum, frame):
        """Handle shutdown signals gracefully."""
        try:
            LoggingService.LogInfo(f"Received signal {signum}, initiating graceful shutdown", 
                                 "QualityCompareService", "SignalHandler")
            
            if self.App:
                self.App.Shutdown()
            
            self.ShutdownEvent.set()
            
        except Exception as e:
            LoggingService.LogException("Exception in signal handler", e, 
                                      "QualityCompareService", "SignalHandler")
    
    def Run(self):
        """Run the QualityCompareService."""
        try:
            LoggingService.LogInfo("Starting QualityCompareService...", "QualityCompareService", "Run")
            
            # Initialize application
            self.App = QualityCompareServiceApp()
            
            # Start the application
            self.App.Run()
            
            # Wait for shutdown signal
            self.ShutdownEvent.wait()
            
            LoggingService.LogInfo("QualityCompareService shutdown complete", "QualityCompareService", "Run")
            
        except Exception as e:
            LoggingService.LogException("Exception in QualityCompareService main", e, 
                                      "QualityCompareService", "Run")
        finally:
            if self.App:
                self.App.Cleanup()


def main():
    """Main entry point for QualityCompareService."""
    try:
        service = QualityCompareServiceMain()
        service.Run()
    except Exception as e:
        LoggingService.LogException("Fatal exception in QualityCompareService", e, 
                                  "QualityCompareService", "main")
        sys.exit(1)


if __name__ == "__main__":
    main()
