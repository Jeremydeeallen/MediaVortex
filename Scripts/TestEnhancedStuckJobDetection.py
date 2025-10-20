#!/usr/bin/env python3
"""
TestEnhancedStuckJobDetection.py - Test the enhanced stuck job detection system
Tests the new orphaned FFmpeg process detection and correlation features.
"""

import sys
import os
from datetime import datetime

# Add parent directory to path to import shared services
current_dir = os.path.dirname(os.path.abspath(__file__))
parent_dir = os.path.dirname(current_dir)
root_dir = os.path.dirname(parent_dir)
sys.path.append(root_dir)

from Repositories.DatabaseManager import DatabaseManager
from Services.LoggingService import LoggingService
from Services.StuckJobDetectionService import StuckJobDetectionService
from Services.ProcessManagementService import ProcessManagementService


def TestEnhancedDetection():
    """Test the enhanced stuck job detection system."""
    try:
        LoggingService.LogInfo("Starting enhanced stuck job detection test", "TestEnhancedStuckJobDetection", "main")
        
        # Initialize services
        databaseManager = DatabaseManager()
        detectionService = StuckJobDetectionService(databaseManager)
        processService = ProcessManagementService()
        
        print("=== ENHANCED STUCK JOB DETECTION TEST ===")
        print(f"Timestamp: {datetime.now().isoformat()}")
        
        # Test 1: Find all FFmpeg processes
        print("\n1. Finding all FFmpeg processes...")
        ffmpegProcesses = processService.FindFFmpegProcesses()
        print(f"   Found {len(ffmpegProcesses)} FFmpeg processes")
        
        for i, process in enumerate(ffmpegProcesses, 1):
            print(f"   {i}. PID {process['Pid']}: {process['Name']}")
            if process.get('Cmdline'):
                cmdline = process['Cmdline']
                if len(cmdline) > 100:
                    cmdline = cmdline[:97] + "..."
                print(f"      Command: {cmdline}")
        
        # Test 2: Find orphaned FFmpeg processes
        print("\n2. Finding orphaned FFmpeg processes...")
        orphanedResult = detectionService.FindOrphanedFFmpegProcesses()
        
        if orphanedResult.get("Success", False):
            orphanedProcesses = orphanedResult.get("OrphanedProcesses", [])
            print(f"   Found {len(orphanedProcesses)} orphaned FFmpeg processes")
            
            for i, process in enumerate(orphanedProcesses, 1):
                print(f"   {i}. PID {process['Pid']}: {process.get('OperationType', 'Unknown')} operation")
                if process.get('InputFile'):
                    print(f"      Input: {process['InputFile']}")
                if process.get('OutputFile'):
                    print(f"      Output: {process['OutputFile']}")
                if process.get('Cmdline'):
                    cmdline = process['Cmdline']
                    if len(cmdline) > 100:
                        cmdline = cmdline[:97] + "..."
                    print(f"      Command: {cmdline}")
        else:
            print(f"   Error: {orphanedResult.get('ErrorMessage', 'Unknown error')}")
        
        # Test 3: Analyze FFmpeg command lines
        print("\n3. Analyzing FFmpeg command lines...")
        for process in ffmpegProcesses[:3]:  # Test first 3 processes
            if process.get('Cmdline'):
                cmdlineInfo = detectionService.AnalyzeFFmpegCommandLine(process['Cmdline'])
                print(f"   PID {process['Pid']}:")
                print(f"      Input File: {cmdlineInfo.get('InputFile', 'None')}")
                print(f"      Output File: {cmdlineInfo.get('OutputFile', 'None')}")
                print(f"      Operation Type: {cmdlineInfo.get('OperationType', 'Unknown')}")
                print(f"      Is Transcode: {cmdlineInfo.get('IsTranscode', False)}")
                print(f"      Is VMAF: {cmdlineInfo.get('IsVMAF', False)}")
        
        # Test 4: Correlate FFmpeg with jobs
        print("\n4. Correlating FFmpeg processes with database jobs...")
        correlationResult = detectionService.CorrelateFFmpegWithJobs()
        
        if correlationResult.get("Success", False):
            orphanedCount = correlationResult.get("OrphanedCount", 0)
            stuckCount = correlationResult.get("StuckCount", 0)
            healthyCount = correlationResult.get("HealthyCount", 0)
            
            print(f"   Orphaned Processes: {orphanedCount}")
            print(f"   Stuck Jobs: {stuckCount}")
            print(f"   Healthy Jobs: {healthyCount}")
            
            # Show details
            orphanedProcesses = correlationResult.get("OrphanedProcesses", [])
            if orphanedProcesses:
                print(f"\n   Orphaned FFmpeg Processes:")
                for process in orphanedProcesses:
                    print(f"     - PID {process['Pid']}: {process.get('OperationType', 'Unknown')}")
            
            stuckJobs = correlationResult.get("StuckJobs", [])
            if stuckJobs:
                print(f"\n   Stuck Jobs:")
                for job in stuckJobs:
                    print(f"     - {job['JobType']} Job {job['JobId']}: {job.get('FileName', 'Unknown')} - {job['Reason']}")
            
            healthyJobs = correlationResult.get("HealthyJobs", [])
            if healthyJobs:
                print(f"\n   Healthy Jobs:")
                for job in healthyJobs:
                    print(f"     - {job['JobType']} Job {job['JobId']}: {job.get('FileName', 'Unknown')}")
        else:
            print(f"   Error: {correlationResult.get('ErrorMessage', 'Unknown error')}")
        
        # Test 5: Enhanced detection with orphaned process check
        print("\n5. Running enhanced detection with orphaned process check...")
        enhancedResult = detectionService.DetectWithOrphanedProcessCheck()
        
        if enhancedResult.get("Success", False):
            totalStuckFound = enhancedResult.get("TotalStuckJobsFound", 0)
            totalJobsCleaned = enhancedResult.get("TotalJobsCleaned", 0)
            orphanedCount = enhancedResult.get("OrphanedCount", 0)
            
            print(f"   Total Stuck Jobs Found: {totalStuckFound}")
            print(f"   Total Jobs Cleaned: {totalJobsCleaned}")
            print(f"   Orphaned Processes: {orphanedCount}")
        else:
            print(f"   Error: {enhancedResult.get('ErrorMessage', 'Unknown error')}")
        
        # Test 6: Recovery workflow (dry run)
        print("\n6. Testing recovery workflow (dry run)...")
        recoveryResult = detectionService.RecoverFromOrphanedState()
        
        if recoveryResult.get("Success", False):
            orphanedFound = recoveryResult.get("OrphanedProcessesFound", 0)
            orphanedKilled = recoveryResult.get("OrphanedProcessesKilled", 0)
            stuckFound = recoveryResult.get("StuckJobsFound", 0)
            jobsCleaned = recoveryResult.get("JobsCleaned", 0)
            
            print(f"   Orphaned Processes Found: {orphanedFound}")
            print(f"   Orphaned Processes Killed: {orphanedKilled}")
            print(f"   Stuck Jobs Found: {stuckFound}")
            print(f"   Jobs Cleaned: {jobsCleaned}")
        else:
            print(f"   Error: {recoveryResult.get('ErrorMessage', 'Unknown error')}")
        
        print(f"\n=== TEST COMPLETED ===")
        LoggingService.LogInfo("Enhanced stuck job detection test completed", "TestEnhancedStuckJobDetection", "main")
        
        return True
        
    except Exception as e:
        LoggingService.LogException("Error during enhanced stuck job detection test", e, 
                                  "TestEnhancedStuckJobDetection", "main")
        print(f"❌ Test failed: {str(e)}")
        return False


def main():
    """Main entry point for test script."""
    print("Enhanced Stuck Job Detection Test")
    print("=" * 50)
    
    success = TestEnhancedDetection()
    
    if success:
        print("\n✅ All tests completed successfully")
        sys.exit(0)
    else:
        print("\n❌ Tests failed")
        sys.exit(1)


if __name__ == "__main__":
    main()
