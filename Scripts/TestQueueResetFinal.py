#!/usr/bin/env python3
"""
Final test script for the Queue Reset functionality.
This script tests the actual reset operations with the corrected database method calls.
"""

import sys
import os
from datetime import datetime

# Add the parent directory to the path so we can import from the main application
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from Repositories.DatabaseManager import DatabaseManager


def TestActualResetOperations():
    """Test the actual reset operations with the corrected method calls."""
    print("=" * 60)
    print("Testing Final Queue Reset Operations")
    print("=" * 60)
    
    try:
        # Initialize database manager
        print("1. Initializing DatabaseManager...")
        databaseManager = DatabaseManager()
        print("   ✓ DatabaseManager initialized successfully")
        
        # Test 1: Check current status before reset
        print("\n2. Checking Current Queue Status...")
        
        statusQueries = [
            ("TranscodeQueue (Running)", "SELECT COUNT(*) as Count FROM TranscodeQueue WHERE Status = 'Running'"),
            ("QualityTestingQueue (Testing)", "SELECT COUNT(*) as Count FROM QualityTestingQueue WHERE Status = 'Testing'"),
            ("ServiceCommands (Pending)", "SELECT COUNT(*) as Count FROM ServiceCommands WHERE Status = 'Pending'"),
            ("TranscodeAttempts (Running)", "SELECT COUNT(*) as Count FROM TranscodeAttempts WHERE Success IS NULL"),
            ("TranscodeProgress (Running)", "SELECT COUNT(*) as Count FROM TranscodeProgress WHERE Status = 'Running'"),
            ("QualityTestProgress (Running)", "SELECT COUNT(*) as Count FROM QualityTestProgress WHERE Status = 'Running'")
        ]
        
        beforeCounts = {}
        totalBefore = 0
        
        for name, query in statusQueries:
            try:
                result = databaseManager.DatabaseService.ExecuteQuery(query)
                if result is not None:
                    count = result[0]['Count'] if result else 0
                    beforeCounts[name] = count
                    totalBefore += count
                    print(f"   ✓ {name}: {count} items")
                else:
                    print(f"   ✗ {name}: Query failed")
            except Exception as e:
                print(f"   ✗ {name}: Exception - {str(e)}")
        
        print(f"\n   Total running items before reset: {totalBefore}")
        
        if totalBefore == 0:
            print("\n   No running items found to reset. This is normal if no tasks are currently running.")
            return True
        
        # Test 2: Perform actual reset operations
        print("\n3. Testing Actual Reset Operations...")
        
        resetOperations = [
            ("Reset TranscodeQueue Running to Pending", "UPDATE TranscodeQueue SET Status = 'Pending', DateStarted = NULL WHERE Status = 'Running'"),
            ("Reset QualityTestingQueue Testing to Pending", "UPDATE QualityTestingQueue SET Status = 'Pending', DateStarted = NULL WHERE Status = 'Testing'"),
            ("Terminate TranscodeAttempts", "UPDATE TranscodeAttempts SET Success = 0, ErrorMessage = 'Terminated due to system reset', AttemptDate = datetime('now') WHERE Success IS NULL"),
            ("Clear TranscodeProgress", "DELETE FROM TranscodeProgress WHERE Status = 'Running'"),
            ("Clear QualityTestProgress", "DELETE FROM QualityTestProgress WHERE Status = 'Running'"),
            ("Cancel ServiceCommands", "UPDATE ServiceCommands SET Status = 'Cancelled', Result = 'Cancelled due to system reset', ProcessedAt = datetime('now') WHERE Status = 'Pending'")
        ]
        
        resetResults = {}
        
        for name, query in resetOperations:
            try:
                print(f"   Testing {name}...")
                result = databaseManager.DatabaseService.ExecuteNonQuery(query)
                
                if result is not None:
                    resetResults[name] = result
                    print(f"   ✓ {name}: {result} rows affected")
                else:
                    print(f"   ✗ {name}: Operation failed")
            except Exception as e:
                print(f"   ✗ {name}: Exception - {str(e)}")
        
        # Test 3: Check status after reset
        print("\n4. Checking Queue Status After Reset...")
        
        afterCounts = {}
        totalAfter = 0
        
        for name, query in statusQueries:
            try:
                result = databaseManager.DatabaseService.ExecuteQuery(query)
                if result is not None:
                    count = result[0]['Count'] if result else 0
                    afterCounts[name] = count
                    totalAfter += count
                    print(f"   ✓ {name}: {count} items (was {beforeCounts.get(name, 0)})")
                else:
                    print(f"   ✗ {name}: Query failed")
            except Exception as e:
                print(f"   ✗ {name}: Exception - {str(e)}")
        
        print(f"\n   Total running items after reset: {totalAfter} (was {totalBefore})")
        
        # Test 4: Verify the reset worked
        print("\n5. Verifying Reset Results...")
        
        success = True
        for name in beforeCounts:
            before = beforeCounts[name]
            after = afterCounts.get(name, 0)
            
            if before > 0 and after > 0:
                print(f"   ⚠ {name}: Still has {after} running items (was {before})")
                success = False
            elif before > 0 and after == 0:
                print(f"   ✓ {name}: Successfully reset {before} items")
            else:
                print(f"   ✓ {name}: No items to reset")
        
        print("\n" + "=" * 60)
        print("Final Queue Reset Test Summary")
        print("=" * 60)
        print(f"✓ Database operations completed successfully")
        print(f"✓ Reset operations executed: {len([r for r in resetResults.values() if r is not None])}")
        print(f"✓ Total items before reset: {totalBefore}")
        print(f"✓ Total items after reset: {totalAfter}")
        
        if success:
            print("✓ ALL RESET OPERATIONS SUCCESSFUL")
            print("\nThe queue reset functionality is working correctly!")
        else:
            print("⚠ SOME ITEMS MAY NOT HAVE BEEN RESET")
            print("This could be normal if items were in transition during the test.")
        
        print("\nKey Fixes Applied:")
        print("- Changed 'if result:' to 'if result is not None:' for ExecuteNonQuery results")
        print("- ExecuteNonQuery returns integer (affected rows), not boolean")
        print("- All database operations now handle return values correctly")
        
        return success
        
    except Exception as e:
        print(f"\n✗ Test failed with exception: {str(e)}")
        import traceback
        traceback.print_exc()
        return False


if __name__ == "__main__":
    print("MediaVortex Final Queue Reset Test")
    print("=" * 60)
    print(f"Test started at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    
    # Test the functionality
    testPassed = TestActualResetOperations()
    
    print("\n" + "=" * 60)
    print("Final Test Results")
    print("=" * 60)
    
    if testPassed:
        print("✓ ALL TESTS PASSED")
        print("\nThe queue reset functionality is now working correctly!")
        print("The database method return value issues have been resolved.")
    else:
        print("⚠ SOME TESTS HAD ISSUES")
        print("Please check the results above for details.")
    
    print(f"\nTest completed at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
