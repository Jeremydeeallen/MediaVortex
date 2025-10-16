#!/usr/bin/env python3
"""
ProcessQualityTestQueueService
Orchestrates the complete quality testing queue processing workflow using MVVM architecture
"""

from typing import Dict, Any, Optional
from datetime import datetime
import threading
import time
import os
from Repositories.DatabaseManager import DatabaseManager
from Services.QualityTestingBusinessService import QualityTestingBusinessService
from Services.LoggingService import LoggingService


class ProcessQualityTestQueueService:
    """Orchestrates the complete quality testing queue processing workflow using MVVM architecture."""
    
    def __init__(self, DatabaseManagerInstance: DatabaseManager = None,
                 QualityTestingBusinessInstance: QualityTestingBusinessService = None):
        self.DatabaseManager = DatabaseManagerInstance or DatabaseManager()
        self.QualityTestingBusiness = QualityTestingBusinessInstance or QualityTestingBusinessService(self.DatabaseManager)
        
        # Processing state
        self.IsProcessing = False
        self.MaxConcurrentJobs = 1
        self.ActiveJobs = []
        self.ProcessingThread = None
        self.StopRequested = False
        
    def Run(self, MaxConcurrentJobs: int = 1) -> Dict[str, Any]:
        """Start processing the quality testing queue with specified concurrent jobs."""
        try:
            LoggingService.LogFunctionEntry("Run", "ProcessQualityTestQueueService", MaxConcurrentJobs)
            
            if self.IsProcessing:
                return {
                    "Success": False,
                    "ErrorMessage": "Quality testing is already in progress"
                }
            
            # Validate parameters
            if not isinstance(MaxConcurrentJobs, int) or MaxConcurrentJobs < 1 or MaxConcurrentJobs > 5:
                return {
                    "Success": False,
                    "ErrorMessage": "MaxConcurrentJobs must be an integer between 1 and 5"
                }
            
            self.MaxConcurrentJobs = MaxConcurrentJobs
            self.StopRequested = False
            self.IsProcessing = True
            
            # Start processing in background thread
            self.ProcessingThread = threading.Thread(target=self.ProcessQueueLoop, daemon=True)
            self.ProcessingThread.start()
            
            LoggingService.LogInfo(f"Started quality testing queue processing with {MaxConcurrentJobs} concurrent jobs", 
                                 "ProcessQualityTestQueueService", "Run")
            
            return {
                "Success": True,
                "Message": f"Started quality testing with {MaxConcurrentJobs} concurrent jobs",
                "MaxConcurrentJobs": MaxConcurrentJobs
            }
            
        except Exception as e:
            self.IsProcessing = False
            errorMsg = f"Exception starting quality testing: {str(e)}"
            LoggingService.LogException(errorMsg, e, "ProcessQualityTestQueueService", "Run")
            return {
                "Success": False,
                "ErrorMessage": errorMsg
            }
    
    def Stop(self) -> Dict[str, Any]:
        """Stop processing the quality testing queue."""
        try:
            LoggingService.LogFunctionEntry("Stop", "ProcessQualityTestQueueService")
            
            if not self.IsProcessing:
                return {
                    "Success": True,
                    "Message": "Quality testing is not currently running"
                }
            
            self.StopRequested = True
            
            # Wait for processing to stop
            if self.ProcessingThread and self.ProcessingThread.is_alive():
                self.ProcessingThread.join(timeout=10)
            
            self.IsProcessing = False
            self.ActiveJobs = []
            
            LoggingService.LogInfo("Quality testing queue processing stopped", 
                                 "ProcessQualityTestQueueService", "Stop")
            
            return {
                "Success": True,
                "Message": "Quality testing stopped successfully"
            }
            
        except Exception as e:
            errorMsg = f"Exception stopping quality testing: {str(e)}"
            LoggingService.LogException(errorMsg, e, "ProcessQualityTestQueueService", "Stop")
            return {
                "Success": False,
                "ErrorMessage": errorMsg
            }
    
    def ProcessQueueLoop(self):
        """Main processing loop that continuously checks for quality testing jobs."""
        try:
            LoggingService.LogInfo("Quality testing queue processing loop started", 
                                 "ProcessQualityTestQueueService", "ProcessQueueLoop")
            
            while not self.StopRequested:
                try:
                    # Check if we can process more jobs (concurrency limit)
                    if len(self.ActiveJobs) < self.MaxConcurrentJobs:
                        # Try to claim a job from the queue
                        job = self.ClaimNextJob()
                        
                        if job:
                            # Process the job in a separate thread
                            job_thread = threading.Thread(
                                target=self.ProcessJob,
                                args=(job,),
                                daemon=True
                            )
                            job_thread.start()
                            self.ActiveJobs.append(job_thread)
                            
                            LoggingService.LogInfo(f"Started processing quality test job {job['Id']}", 
                                                 "ProcessQualityTestQueueService", "ProcessQueueLoop")
                        else:
                            # No jobs available, wait a bit
                            time.sleep(2)
                    else:
                        # At concurrency limit, wait a bit
                        time.sleep(1)
                    
                    # Clean up completed threads
                    self.ActiveJobs = [thread for thread in self.ActiveJobs if thread.is_alive()]
                    
                except Exception as e:
                    LoggingService.LogException("Error in quality testing queue processing loop", e, 
                                             "ProcessQualityTestQueueService", "ProcessQueueLoop")
                    time.sleep(5)  # Wait before retrying
            
            LoggingService.LogInfo("Quality testing queue processing loop stopped", 
                                 "ProcessQualityTestQueueService", "ProcessQueueLoop")
            
        except Exception as e:
            LoggingService.LogException("Fatal error in quality testing queue processing loop", e, 
                                     "ProcessQualityTestQueueService", "ProcessQueueLoop")
            self.IsProcessing = False
    
    def ClaimNextJob(self) -> Optional[Dict[str, Any]]:
        """Claim the next available quality testing job from the queue."""
        try:
            # Use the DatabaseManager's atomic claiming method
            job = self.DatabaseManager.ClaimQualityTestJob()
            
            if job:
                LoggingService.LogInfo(f"Claimed quality test job {job['Id']}", 
                                     "ProcessQualityTestQueueService", "ClaimNextJob")
                return job
            else:
                # No jobs available or all jobs already claimed
                return None
                
        except Exception as e:
            LoggingService.LogException("Error claiming next quality test job", e, 
                                     "ProcessQualityTestQueueService", "ClaimNextJob")
            return None
    
    def ProcessJob(self, job: Dict[str, Any]):
        """Process a single quality testing job."""
        try:
            LoggingService.LogInfo(f"Processing quality test job {job['Id']}", 
                                 "ProcessQualityTestQueueService", "ProcessJob")
            
            # Use the business service to process the job
            result = self.QualityTestingBusiness.ProcessClaimedJob(job)
            
            if result.get('Success', False):
                LoggingService.LogInfo(f"Successfully processed quality test job {job['Id']}", 
                                     "ProcessQualityTestQueueService", "ProcessJob")
            else:
                LoggingService.LogError(f"Failed to process quality test job {job['Id']}: {result.get('Message', 'Unknown error')}", 
                                      "ProcessQualityTestQueueService", "ProcessJob")
                
        except Exception as e:
            LoggingService.LogException(f"Exception processing quality test job {job['Id']}", e, 
                                     "ProcessQualityTestQueueService", "ProcessJob")
        finally:
            # Job processing is complete (success or failure)
            LoggingService.LogInfo(f"Quality test job {job['Id']} processing completed", 
                                 "ProcessQualityTestQueueService", "ProcessJob")
    
    def GetStatus(self) -> Dict[str, Any]:
        """Get current processing status."""
        try:
            return {
                "Success": True,
                "IsProcessing": self.IsProcessing,
                "MaxConcurrentJobs": self.MaxConcurrentJobs,
                "ActiveJobsCount": len(self.ActiveJobs),
                "StopRequested": self.StopRequested
            }
        except Exception as e:
            LoggingService.LogException("Error getting quality testing status", e, 
                                     "ProcessQualityTestQueueService", "GetStatus")
            return {
                "Success": False,
                "ErrorMessage": str(e)
            }
    
    def IsStopRequested(self) -> bool:
        """Check if stop was requested."""
        return self.StopRequested
