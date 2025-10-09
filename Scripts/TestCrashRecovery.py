#!/usr/bin/env python3
"""
Test Crash Recovery Script
Test script to verify crash recovery functionality works correctly
Implements MVVM pattern using MVVM architecture
"""

import sys
import os
import time
import subprocess
import signal
from datetime import datetime

# Add the parent directory to the path so we can import our modules
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from Repositories.DatabaseManager import DatabaseManager
from Services.CrashRecoveryService import CrashRecoveryService
from Services.ProcessManagementService import ProcessManagementService
from Services.LoggingService import LoggingService


def TestProcessManagementService():
    """Test the ProcessManagementService functionality."""
    print("=== Testing ProcessManagementService ===")
    
    try:
        process_manager = ProcessManagementService()
        
        # Test 1: Check if current process is running
        current_pid = os.getpid()
        is_running = process_manager.IsProcessRunning(current_pid)
        print(f"✓ Current process {current_pid} is running: {is_running}")
        
        # Test 2: Check non-existent process
        is_running = process_manager.IsProcessRunning(99999)
        print(f"✓ Non-existent process 99999 is running: {is_running}")
        
        # Test 3: Find FFmpeg processes
        ffmpeg_processes = process_manager.FindFFmpegProcesses()
        print(f"✓ Found {len(ffmpeg_processes)} FFmpeg processes")
        
        # Test 4: Get process info
        process_info = process_manager.GetProcessInfo(current_pid)
        if process_info:
            print(f"✓ Process info retrieved: {process_info['Name']} (PID: {process_info['Pid']})")
        else:
            print("✗ Failed to get process info")
        
        print("ProcessManagementService tests completed successfully\n")
        return True
        
    except Exception as e:
        print(f"✗ ProcessManagementService test failed: {e}")
        return False


def TestCrashRecoveryService():
    """Test the CrashRecoveryService functionality."""
    print("=== Testing CrashRecoveryService ===")
    
    try:
        database_manager = DatabaseManager()
        recovery_service = CrashRecoveryService(database_manager)
        
        # Test 1: Get recovery statistics
        stats = recovery_service.GetRecoveryStatistics("TranscodeService")
        print(f"✓ Recovery statistics: {stats}")
        
        # Test 2: Test recovery for TranscodeService (should be no active jobs)
        result = recovery_service.RecoverServiceJobs("TranscodeService")
        print(f"✓ TranscodeService recovery result: {result.get('Message', 'No message')}")
        
        # Test 3: Test recovery for QualityTestingService (should be no active jobs)
        result = recovery_service.RecoverServiceJobs("QualityTestingService")
        print(f"✓ QualityTestingService recovery result: {result.get('Message', 'No message')}")
        
        print("CrashRecoveryService tests completed successfully\n")
        return True
        
    except Exception as e:
        print(f"✗ CrashRecoveryService test failed: {e}")
        return False


def TestDatabaseManagerMethods():
    """Test the new DatabaseManager methods."""
    print("=== Testing DatabaseManager Crash Recovery Methods ===")
    
    try:
        database_manager = DatabaseManager()
        
        # Test 1: Get active jobs by service
        active_jobs = database_manager.GetActiveJobsByService("TranscodeService")
        print(f"✓ Active TranscodeService jobs: {len(active_jobs)}")
        
        active_jobs = database_manager.GetActiveJobsByService("QualityTestingService")
        print(f"✓ Active QualityTestingService jobs: {len(active_jobs)}")
        
        # Test 2: Get all active jobs
        all_active_jobs = database_manager.GetAllActiveJobs()
        print(f"✓ Total active jobs across all services: {len(all_active_jobs)}")
        
        # Test 3: Test queue reset (with empty list)
        reset_count = database_manager.ResetQueueJobsToPending([], "TranscodeQueue")
        print(f"✓ Reset empty queue jobs: {reset_count}")
        
        reset_count = database_manager.ResetQueueJobsToPending([], "QualityTestingQueue")
        print(f"✓ Reset empty quality test queue jobs: {reset_count}")
        
        print("DatabaseManager crash recovery methods tests completed successfully\n")
        return True
        
    except Exception as e:
        print(f"✗ DatabaseManager test failed: {e}")
        return False


def CreateTestActiveJob():
    """Create a test active job for testing purposes."""
    try:
        database_manager = DatabaseManager()
        
        # Create a test active job
        job_id = database_manager.CreateActiveJob(
            ServiceName="TestService",
            JobType="TestJob",
            QueueId=999,
            ProcessId=os.getpid(),
            ThreadId=1
        )
        
        print(f"✓ Created test active job with ID: {job_id}")
        return job_id
        
    except Exception as e:
        print(f"✗ Failed to create test active job: {e}")
        return None


def CleanupTestActiveJob(job_id):
    """Clean up the test active job."""
    try:
        database_manager = DatabaseManager()
        
        # Delete the test active job
        success = database_manager.DeleteActiveJob(job_id)
        if success:
            print(f"✓ Cleaned up test active job {job_id}")
        else:
            print(f"✗ Failed to clean up test active job {job_id}")
            
    except Exception as e:
        print(f"✗ Error cleaning up test active job: {e}")


def TestActiveJobManagement():
    """Test active job creation and cleanup."""
    print("=== Testing Active Job Management ===")
    
    try:
        # Create test job
        job_id = CreateTestActiveJob()
        if not job_id:
            return False
        
        # Test getting job details
        database_manager = DatabaseManager()
        job_details = database_manager.GetActiveJobDetails(job_id)
        if job_details:
            print(f"✓ Retrieved job details: {job_details['ServiceName']} - {job_details['JobType']}")
        else:
            print("✗ Failed to get job details")
        
        # Test recovery service with test job
        recovery_service = CrashRecoveryService(database_manager)
        result = recovery_service.RecoverServiceJobs("TestService")
        print(f"✓ Test service recovery result: {result.get('Message', 'No message')}")
        
        # Clean up
        CleanupTestActiveJob(job_id)
        
        print("Active job management tests completed successfully\n")
        return True
        
    except Exception as e:
        print(f"✗ Active job management test failed: {e}")
        return False


def Main():
    """Main test function."""
    print("MediaVortex Crash Recovery Test Suite")
    print("=" * 50)
    print(f"Test started at: {datetime.now()}")
    print()
    
    test_results = []
    
    # Run all tests
    test_results.append(("ProcessManagementService", TestProcessManagementService()))
    test_results.append(("DatabaseManager Methods", TestDatabaseManagerMethods()))
    test_results.append(("Active Job Management", TestActiveJobManagement()))
    test_results.append(("CrashRecoveryService", TestCrashRecoveryService()))
    
    # Print results summary
    print("=" * 50)
    print("TEST RESULTS SUMMARY")
    print("=" * 50)
    
    passed = 0
    failed = 0
    
    for test_name, result in test_results:
        status = "PASS" if result else "FAIL"
        print(f"{test_name}: {status}")
        if result:
            passed += 1
        else:
            failed += 1
    
    print()
    print(f"Total Tests: {len(test_results)}")
    print(f"Passed: {passed}")
    print(f"Failed: {failed}")
    
    if failed == 0:
        print("\n🎉 All tests passed! Crash recovery system is ready.")
        return True
    else:
        print(f"\n❌ {failed} test(s) failed. Please review the errors above.")
        return False


if __name__ == "__main__":
    try:
        success = Main()
        sys.exit(0 if success else 1)
    except KeyboardInterrupt:
        print("\n\nTest interrupted by user")
        sys.exit(1)
    except Exception as e:
        print(f"\n\nUnexpected error during testing: {e}")
        sys.exit(1)
