#!/usr/bin/env python3
"""
QuickStuckJobDiagnostic.py - Quick diagnostic for stuck jobs
"""

import sys
import os
import psutil
from datetime import datetime

# Add current directory to path
sys.path.append('.')

try:
    from Repositories.DatabaseManager import DatabaseManager
    from Services.LoggingService import LoggingService
    from Services.StuckJobDetectionService import StuckJobDetectionService
    from Services.ProcessManagementService import ProcessManagementService
    
    def main():
        print("=== QUICK STUCK JOB DIAGNOSTIC ===")
        print(f"Timestamp: {datetime.now().isoformat()}")
        
        # Initialize services
        databaseManager = DatabaseManager()
        detectionService = StuckJobDetectionService(databaseManager)
        processService = ProcessManagementService()
        
        # 1. Find all FFmpeg processes
        print("\n1. FFmpeg Processes:")
        ffmpegProcesses = processService.FindFFmpegProcesses()
        print(f"   Found {len(ffmpegProcesses)} FFmpeg processes")
        
        for i, process in enumerate(ffmpegProcesses, 1):
            print(f"   {i}. PID {process['Pid']}: {process['Name']}")
            if process.get('Cmdline'):
                cmdline = process['Cmdline']
                if len(cmdline) > 100:
                    cmdline = cmdline[:97] + "..."
                print(f"      Command: {cmdline}")
        
        # 2. Get running jobs from database
        print("\n2. Running Jobs from Database:")
        transcodeJobs = databaseManager.GetTranscodeQueueItemsByStatus("Running")
        qualityTestQueue = databaseManager.GetQualityTestQueue()
        from Features.ServiceControl.ActiveJobRepository import ActiveJobRepository as _AJR
        activeQualityJobs = databaseManager.GetActiveJobsByService(_AJR.BuildActiveJobsQuery("QualityTest"))
        
        print(f"   Transcode Jobs: {len(transcodeJobs)}")
        for job in transcodeJobs:
            print(f"     - Job {job.Id}: {job.FileName}")
            print(f"       Status: {job.Status}")
        
        print(f"   Quality Test Queue: {len(qualityTestQueue)}")
        for job in qualityTestQueue:
            print(f"     - Job {job['Id']}: {job.get('OriginalFilePath', 'Unknown')}")
            print(f"       Date Added: {job.get('DateAdded', 'Unknown')}")
            print(f"       Date Started: {job.get('DateStarted', 'Not started')}")
        
        print(f"   Active Quality Test Jobs: {len(activeQualityJobs)}")
        for job in activeQualityJobs:
            print(f"     - Active Job {job['Id']}: Queue ID {job.get('QueueId', 'Unknown')}")
            print(f"       Process ID: {job.get('ProcessId', 'None')}")
            print(f"       Started: {job.get('StartedAt', 'Unknown')}")
        
        # 3. Find orphaned processes
        print("\n3. Orphaned FFmpeg Processes:")
        orphanedResult = detectionService.FindOrphanedFFmpegProcesses()
        
        if orphanedResult.get("Success", False):
            orphanedProcesses = orphanedResult.get("OrphanedProcesses", [])
            print(f"   Found {len(orphanedProcesses)} orphaned processes")
            
            for process in orphanedProcesses:
                print(f"     - PID {process['Pid']}: {process.get('OperationType', 'Unknown')}")
                if process.get('InputFile'):
                    print(f"       Input: {process['InputFile']}")
                if process.get('OutputFile'):
                    print(f"       Output: {process['OutputFile']}")
        else:
            print(f"   Error: {orphanedResult.get('ErrorMessage', 'Unknown error')}")
        
        # 4. Run correlation
        print("\n4. Job Correlation:")
        correlationResult = detectionService.CorrelateFFmpegWithJobs()
        
        if correlationResult.get("Success", False):
            orphanedCount = correlationResult.get("OrphanedCount", 0)
            stuckCount = correlationResult.get("StuckCount", 0)
            healthyCount = correlationResult.get("HealthyCount", 0)
            
            print(f"   Orphaned Processes: {orphanedCount}")
            print(f"   Stuck Jobs: {stuckCount}")
            print(f"   Healthy Jobs: {healthyCount}")
            
            # Show stuck jobs
            stuckJobs = correlationResult.get("StuckJobs", [])
            if stuckJobs:
                print(f"\n   Stuck Jobs Details:")
                for job in stuckJobs:
                    print(f"     - {job['JobType']} Job {job['JobId']}: {job.get('FileName', 'Unknown')}")
                    print(f"       Reason: {job['Reason']}")
        else:
            print(f"   Error: {correlationResult.get('ErrorMessage', 'Unknown error')}")
        
        # 5. Recommendations
        print("\n5. Recommendations:")
        if orphanedResult.get("OrphanedCount", 0) > 0 or correlationResult.get("StuckCount", 0) > 0:
            print("   🔧 Issues found! Run auto-fix:")
            print("   py Scripts\\DiagnoseStuckJobs.py --auto-fix")
        else:
            print("   ✅ No issues found - system appears healthy")
        
        print(f"\n=== DIAGNOSTIC COMPLETE ===")
        
    if __name__ == "__main__":
        main()
        
except Exception as e:
    print(f"Error: {str(e)}")
    import traceback
    traceback.print_exc()
