#!/usr/bin/env python3
"""
TranscodeService Entry Point
Standalone transcoding microservice for MediaVortex
"""

import sys
import signal
import logging
from app import TranscodeServiceApp

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('TranscodeService.log'),
        logging.StreamHandler(sys.stdout)
    ]
)

logger = logging.getLogger(__name__)

def signal_handler(signum, frame):
    """Handle shutdown signals gracefully."""
    logger.info(f"Received signal {signum}, shutting down gracefully...")
    if hasattr(main, 'app') and main.app:
        main.app.shutdown()
    sys.exit(0)

def main():
    """Main entry point for TranscodeService."""
    try:
        logger.info("Starting TranscodeService...")
        
        # Initialize the application
        app = TranscodeServiceApp()
        main.app = app  # Store reference for signal handler
        
        # Register signal handlers
        signal.signal(signal.SIGINT, signal_handler)
        signal.signal(signal.SIGTERM, signal_handler)
        
        # Start the service (this will run indefinitely)
        logger.info("TranscodeService is now running. Press Ctrl+C to stop.")
        app.run()
        
    except KeyboardInterrupt:
        logger.info("Received keyboard interrupt, shutting down...")
        if hasattr(main, 'app') and main.app:
            main.app.shutdown()
    except Exception as e:
        logger.error(f"Fatal error in TranscodeService: {str(e)}", exc_info=True)
        sys.exit(1)
    finally:
        logger.info("TranscodeService stopped.")

if __name__ == "__main__":
    main()
