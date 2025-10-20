#!/usr/bin/env python3
"""
Test script for StuckJobDetectionService
Tests the stuck job detection and cleanup functionality
"""

import os
import sys
from pathlib import Path

# Add the parent directory to the path so we can import our modules
sys.path.append(str(Path(__file__).parent.parent))

from Services.StuckJobDetectionService import StuckJobDetectionService
from Services.LoggingService import LoggingService
from Repositories.DatabaseManager import DatabaseManager

def TestStuckJobDetection():
    """Test the stuck job detection service."""
    try:
        LoggingService.LogInfo("Starting stuck job detection test", "TestStuckJobDetection", "main")
        
        # Create service instances
        database_manager = DatabaseManager()
        detection_service = StuckJobDetectionService(database_manager)
        
        # Test 1: Get stuck job summary
        LoggingService.LogInfo("Test 1: Getting stuck job summary", "TestStuckJobDetection", "main")
        summary = detection_service.GetStuckJobSummary()
        
        if summary.get("Success", False):
            LoggingService.LogInfo(f"Stuck job summary: {summary}", "TestStuckJobDetection", "main")
        else:
            LoggingService.LogError(f"Failed to get stuck job summary: {summary.get('ErrorMessage', 'Unknown error')}", 
                                  "TestStuckJobDetection", "main")
        
        # Test 2: Detect and clean stuck transcode jobs
        LoggingService.LogInfo("Test 2: Detecting and cleaning stuck transcode jobs", "TestStuckJobDetection", "main")
        transcode_result = detection_service.DetectAndCleanStuckTranscodeJobs()
        
        if transcode_result.get("Success", False):
            LoggingService.LogInfo(f"Transcode stuck job detection result: {transcode_result}", "TestStuckJobDetection", "main")
        else:
            LoggingService.LogError(f"Transcode stuck job detection failed: {transcode_result.get('ErrorMessage', 'Unknown error')}", 
                                  "TestStuckJobDetection", "main")
        
        # Test 3: Detect and clean stuck quality test jobs
        LoggingService.LogInfo("Test 3: Detecting and cleaning stuck quality test jobs", "TestStuckJobDetection", "main")
        quality_result = detection_service.DetectAndCleanStuckQualityTestJobs()
        
        if quality_result.get("Success", False):
            LoggingService.LogInfo(f"Quality test stuck job detection result: {quality_result}", "TestStuckJobDetection", "main")
        else:
            LoggingService.LogError(f"Quality test stuck job detection failed: {quality_result.get('ErrorMessage', 'Unknown error')}", 
                                  "TestStuckJobDetection", "main")
        
        # Test 4: Combined detection
        LoggingService.LogInfo("Test 4: Combined stuck job detection", "TestStuckJobDetection", "main")
        combined_result = detection_service.DetectAndCleanAllStuckJobs()
        
        if combined_result.get("Success", False):
            LoggingService.LogInfo(f"Combined stuck job detection result: {combined_result}", "TestStuckJobDetection", "main")
        else:
            LoggingService.LogError(f"Combined stuck job detection failed: {combined_result.get('ErrorMessage', 'Unknown error')}", 
                                  "TestStuckJobDetection", "main")
        
        LoggingService.LogInfo("Stuck job detection test completed", "TestStuckJobDetection", "main")
        
    except Exception as e:
        LoggingService.LogException("Error in stuck job detection test", e, "TestStuckJobDetection", "main")

if __name__ == "__main__":
    TestStuckJobDetection()

