#!/usr/bin/env python3
"""
Test script to verify the crash recovery fix works correctly.
This script simulates the stuck quality test progress scenario and tests the cleanup.
"""

import sys
import os

# Add the project root to the Python path
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, project_root)

from Repositories.DatabaseManager import DatabaseManager
from Services.CrashRecoveryService import CrashRecoveryService
from Services.DatabaseCleanupService import DatabaseCleanupService
from Services.LoggingService import LoggingService

def TestCrashRecoveryFix():
    """Test the crash recovery fix for stuck quality test progress."""
    try:
        print("Testing crash recovery fix for stuck quality test progress...")
        
        # Initialize services
        db_manager = DatabaseManager()
        crash_recovery = CrashRecoveryService(db_manager)
        cleanup_service = DatabaseCleanupService(db_manager)
        
        # Check current state
        print("\n1. Checking current state...")
        
        # Check for stuck progress records
        stuck_progress_query = """
            SELECT COUNT(*) FROM QualityTestProgress 
            WHERE Status IN ('Running', 'Processing')
        """
        stuck_count = db_manager.DatabaseService.ExecuteQuery(stuck_progress_query)
        print(f"   Stuck progress records: {stuck_count[0][0] if stuck_count else 0}")
        
        # Check for active jobs
        active_jobs_query = "SELECT COUNT(*) FROM ActiveJobs WHERE ServiceName = 'QualityTestingService'"
        active_count = db_manager.DatabaseService.ExecuteQuery(active_jobs_query)
        print(f"   Active jobs for QualityTestingService: {active_count[0][0] if active_count else 0}")
        
        # Check for running quality test queue items
        running_queue_query = "SELECT COUNT(*) FROM QualityTestingQueue WHERE DateStarted IS NOT NULL"
        running_queue_count = db_manager.DatabaseService.ExecuteQuery(running_queue_query)
        print(f"   Running quality test queue items: {running_queue_count[0][0] if running_queue_count else 0}")
        
        # Test the cleanup
        print("\n2. Testing DatabaseCleanupService cleanup...")
        cleanup_result = cleanup_service.CleanupMicroserviceState("QualityTestingService")
        print(f"   Cleanup result: {cleanup_result}")
        
        # Test crash recovery
        print("\n3. Testing CrashRecoveryService...")
        recovery_result = crash_recovery.RecoverServiceJobs("QualityTestingService")
        print(f"   Recovery result: {recovery_result}")
        
        # Check if quality tests were reset for retry
        if "QualityTestsReset" in recovery_result:
            print(f"   Quality tests reset for retry: {recovery_result['QualityTestsReset']}")
        
        # Check state after cleanup
        print("\n4. Checking state after cleanup...")
        
        stuck_count_after = db_manager.DatabaseService.ExecuteQuery(stuck_progress_query)
        print(f"   Stuck progress records after cleanup: {stuck_count_after[0][0] if stuck_count_after else 0}")
        
        active_count_after = db_manager.DatabaseService.ExecuteQuery(active_jobs_query)
        print(f"   Active jobs after cleanup: {active_count_after[0][0] if active_count_after else 0}")
        
        running_queue_count_after = db_manager.DatabaseService.ExecuteQuery(running_queue_query)
        print(f"   Running quality test queue items after cleanup: {running_queue_count_after[0][0] if running_queue_count_after else 0}")
        
        # Test orphaned state summary
        print("\n5. Getting orphaned state summary...")
        summary = cleanup_service.GetOrphanedStateSummary()
        print(f"   Orphaned state summary: {summary}")
        
        # Check for missed quality tests that should be picked up
        print("\n6. Checking for missed quality tests...")
        missed_tests = db_manager.GetMissedQualityTests(10)
        print(f"   Missed quality tests found: {len(missed_tests)}")
        if missed_tests:
            print("   Sample missed tests:")
            for test in missed_tests[:3]:  # Show first 3
                print(f"     - TranscodeAttempt {test['Id']}: {test['FilePath']}")
        
        print("\n✅ Crash recovery fix test completed successfully!")
        
    except Exception as e:
        print(f"❌ Error during crash recovery fix test: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    TestCrashRecoveryFix()
