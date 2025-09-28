"""
TranscodeService Application Logic
Handles transcoding queue processing and service orchestration
"""

import sys
import os
import time
import threading
import logging
from typing import Dict, Any, Optional

# Add parent directory to path to import shared services
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from Services.ProcessTranscodeQueueService import ProcessTranscodeQueueService
from Services.LoggingService import LoggingService
from Repositories.DatabaseManager import DatabaseManager

logger = logging.getLogger(__name__)

class TranscodeServiceApp:
    """Main application class for TranscodeService."""
    
    def __init__(self):
        """Initialize the TranscodeService application."""
        self.DatabaseManager = DatabaseManager()
        self.ProcessTranscodeQueue = ProcessTranscodeQueueService(
            DatabaseManagerInstance=self.DatabaseManager
        )
        self.IsRunning = False
        self.ProcessingThread = None
        self.HealthCheckThread = None
        self.ShutdownEvent = threading.Event()
        
        logger.info("TranscodeServiceApp initialized")
    
    def run(self):
        """Start the transcoding service."""
        try:
            logger.info("Starting TranscodeService...")
            
            # Check database connection
            if not self._check_database_connection():
                logger.error("Database connection failed, exiting...")
                return False
            
            # Update service status in database
            self._update_service_status("Starting")
            
            # Start health monitoring
            self._start_health_monitoring()
            
            # Start transcoding processing
            self._start_transcoding_processing()
            
            # Main processing loop
            self._main_loop()
            
            return True
            
        except Exception as e:
            logger.error(f"Error starting TranscodeService: {str(e)}", exc_info=True)
            return False
    
    def shutdown(self):
        """Gracefully shutdown the service."""
        try:
            logger.info("Shutting down TranscodeService...")
            
            # Update service status
            self._update_service_status("Stopping")
            
            # Signal shutdown
            self.ShutdownEvent.set()
            
            # Stop transcoding processing
            if self.ProcessTranscodeQueue:
                self.ProcessTranscodeQueue.Stop()
            
            # Wait for threads to finish
            if self.ProcessingThread and self.ProcessingThread.is_alive():
                self.ProcessingThread.join(timeout=10)
            
            if self.HealthCheckThread and self.HealthCheckThread.is_alive():
                self.HealthCheckThread.join(timeout=5)
            
            # Update service status
            self._update_service_status("Stopped")
            
            logger.info("TranscodeService shutdown complete")
            
        except Exception as e:
            logger.error(f"Error during shutdown: {str(e)}", exc_info=True)
    
    def _check_database_connection(self) -> bool:
        """Check if database connection is available."""
        try:
            # Try to get a simple query to test connection
            result = self.DatabaseManager.DatabaseService.ExecuteQuery("SELECT 1")
            logger.info("Database connection successful")
            return True
        except Exception as e:
            logger.error(f"Database connection failed: {str(e)}")
            return False
    
    def _update_service_status(self, status: str):
        """Update service status in database."""
        try:
            # This would update a service status table
            # For now, just log the status
            logger.info(f"Service status: {status}")
        except Exception as e:
            logger.error(f"Error updating service status: {str(e)}")
    
    def _start_health_monitoring(self):
        """Start health monitoring thread."""
        try:
            self.HealthCheckThread = threading.Thread(
                target=self._health_monitoring_loop,
                daemon=True,
                name="HealthMonitor"
            )
            self.HealthCheckThread.start()
            logger.info("Health monitoring started")
        except Exception as e:
            logger.error(f"Error starting health monitoring: {str(e)}")
    
    def _start_transcoding_processing(self):
        """Start transcoding processing thread."""
        try:
            self.ProcessingThread = threading.Thread(
                target=self._transcoding_processing_loop,
                daemon=True,
                name="TranscodingProcessor"
            )
            self.ProcessingThread.start()
            logger.info("Transcoding processing started")
        except Exception as e:
            logger.error(f"Error starting transcoding processing: {str(e)}")
    
    def _health_monitoring_loop(self):
        """Health monitoring loop."""
        while not self.ShutdownEvent.is_set():
            try:
                # Update service status
                self._update_service_status("Running")
                
                # Check if transcoding is active
                status = self.ProcessTranscodeQueue.GetStatus()
                if status.get("Success", False):
                    is_transcoding = status.get("IsTranscoding", False)
                    active_jobs = status.get("ActiveJobsCount", 0)
                    logger.debug(f"Health check - Transcoding: {is_transcoding}, Active Jobs: {active_jobs}")
                
                # Sleep for 30 seconds
                self.ShutdownEvent.wait(30)
                
            except Exception as e:
                logger.error(f"Error in health monitoring: {str(e)}")
                self.ShutdownEvent.wait(30)
    
    def _transcoding_processing_loop(self):
        """Main transcoding processing loop."""
        while not self.ShutdownEvent.is_set():
            try:
                # Check if there are pending jobs
                pending_jobs = self.DatabaseManager.GetTranscodeQueueItemsByStatus("Pending")
                
                if pending_jobs and len(pending_jobs) > 0:
                    # Start transcoding if not already running
                    if not self.ProcessTranscodeQueue.IsProcessing:
                        logger.info(f"Found {len(pending_jobs)} pending jobs, starting transcoding...")
                        result = self.ProcessTranscodeQueue.Run(MaxConcurrentJobs=1)
                        if not result.get("Success", False):
                            logger.error(f"Failed to start transcoding: {result.get('ErrorMessage', 'Unknown error')}")
                else:
                    # No pending jobs, check if we should stop
                    if self.ProcessTranscodeQueue.IsProcessing:
                        # Check if there are any running jobs
                        running_jobs = self.DatabaseManager.GetTranscodeQueueItemsByStatus("Running")
                        if not running_jobs or len(running_jobs) == 0:
                            logger.info("No pending or running jobs, stopping transcoding...")
                            self.ProcessTranscodeQueue.Stop()
                
                # Sleep for 10 seconds before next check
                self.ShutdownEvent.wait(10)
                
            except Exception as e:
                logger.error(f"Error in transcoding processing loop: {str(e)}")
                self.ShutdownEvent.wait(10)
    
    def _main_loop(self):
        """Main application loop."""
        try:
            self.IsRunning = True
            logger.info("TranscodeService is running...")
            
            # Keep the main thread alive
            while self.IsRunning and not self.ShutdownEvent.is_set():
                self.ShutdownEvent.wait(1)
                
        except KeyboardInterrupt:
            logger.info("Received keyboard interrupt")
        except Exception as e:
            logger.error(f"Error in main loop: {str(e)}")
        finally:
            self.IsRunning = False
