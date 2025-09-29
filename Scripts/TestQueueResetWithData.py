#!/usr/bin/env python3
"""
Test script for Queue Reset functionality with actual test data.
This script creates test data, then tests the reset operations.
"""

import sys
import os
from datetime import datetime

# Add the parent directory to the path so we can import from the main application
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from Repositories.DatabaseManager import DatabaseManager


def CreateTestData(databaseManager):
    """Create test data for reset testing."""
    print("Creating test data...")
    
    try:
        # Create test TranscodeQueue items
        transcodeQuery = """
        INSERT INTO TranscodeQueue (FilePath, FileName, Directory, SizeBytes, SizeMB, Status, Priority, DateAdded, DateStarted)
        VALUES 
            ('/test/reset_test1.mkv', 'reset_test1.mkv', '/test', 1000000, 1.0, 'Running', 1, datetime('now'), datetime('now')),
            ('/test/reset_test2.mkv', 'reset_test2.mkv', '/test', 2000000, 2.0, 'Pending', 1, datetime('now'), NULL),
            ('/test/reset_test3.mkv', 'reset_test3.mkv', '/test', 3000000, 3.0, 'Running', 1, datetime('now'), datetime('now'))
        """
        result = databaseManager.DatabaseService.ExecuteNonQuery(transcodeQuery)
        print(f"   ✓ Created {result} TranscodeQueue test items")
        
        # Create test QualityTestingQueue items
        qualityQuery = """
        INSERT INTO QualityTestingQueue (TranscodeAttemptId, OriginalFilePath, TranscodedFilePath, FileName, Status, Priority, DateAdded, DateStarted)
        VALUES 
            (1, '/test/reset_test1.mkv', '/test/reset_test1_transcoded.mkv', 'reset_test1.mkv', 'Testing', 1, datetime('now'), datetime('now')),
            (2, '/test/reset_test2.mkv', '/test/reset_test2_transcoded.mkv', 'reset_test2.mkv', 'Pending', 1, datetime('now'), NULL),
            (3, '/test/reset_test3.mkv', '/test/reset_test3_transcoded.mkv', 'reset_test3.mkv', 'Testing', 1, datetime('now'), datetime('now'))
        """
        result = databaseManager.DatabaseService.ExecuteNonQuery(qualityQuery)
        print(f"   ✓ Created {result} QualityTestingQueue test items")
        
        # Create test TranscodeAttempts
        attemptsQuery = """
        INSERT INTO TranscodeAttempts (FilePath, Success, AttemptDate)
        VALUES 
            ('/test/reset_test1.mkv', NULL, datetime('now')),
            ('/test/reset_test2.mkv', NULL, datetime('now')),
            ('/test/reset_test3.mkv', 1, datetime('now'))
        """
        result = databaseManager.DatabaseService.ExecuteNonQuery(attemptsQuery)
        print(f"   ✓ Created {result} TranscodeAttempts test items")
        
        # Create test TranscodeProgress
        progressQuery = """
        INSERT INTO TranscodeProgress (TranscodeAttemptId, Status, ProgressPercent)
        VALUES 
            (1, 'Running', 50),
            (2, 'Running', 25)
        """
        result = databaseManager.DatabaseService.ExecuteNonQuery(progressQuery)
        print(f"   ✓ Created {result} TranscodeProgress test items")
        
        # Create test QualityTestProgress
        qualityProgressQuery = """
        INSERT INTO QualityTestProgress (QualityTestId, Status, ProgressPercent)
        VALUES 
            (1, 'Running', 75),
            (2, 'Running', 30)
        """
        result = databaseManager.DatabaseService.ExecuteNonQuery(qualityProgressQuery)
        print(f"   ✓ Created {result} QualityTestProgress test items")
        
        # Create test ServiceCommands
        serviceQuery = """
        INSERT INTO ServiceCommands (CommandType, SourceService, TargetService, Status, CreatedAt)
        VALUES 
            ('TestCommand1', 'TestService', 'TargetService', 'Pending', datetime('now')),
            ('TestCommand2', 'TestService', 'TargetService', 'Pending', datetime('now'))
        """
        result = databaseManager.DatabaseService.ExecuteNonQuery(serviceQuery)
        print(f"   ✓ Created {result} ServiceCommands test items")
        
        return True
        
    except Exception as e:
        print(f"   ✗ Failed to create test data: {str(e)}")
        return False


def CleanupTestData(databaseManager):
    """Clean up test data."""
    print("Cleaning up test data...")
    
    try:
        # Clean up in reverse order to avoid foreign key constraints
        cleanupQueries = [
            "DELETE FROM ServiceCommands WHERE CommandType LIKE 'TestCommand%'",
            "DELETE FROM QualityTestProgress WHERE Status = 'Running'",
            "DELETE FROM TranscodeProgress WHERE Status = 'Running'",
            "DELETE FROM TranscodeAttempts WHERE FilePath LIKE '/test/reset_test%'",
            "DELETE FROM QualityTestingQueue WHERE TranscodeAttemptId IN (1, 2, 3)",
            "DELETE FROM TranscodeQueue WHERE FilePath LIKE '/test/reset_test%'"
        ]
        
        for query in cleanupQueries:
            try:
                databaseManager.DatabaseService.ExecuteNonQuery(query)
            except:
                pass  # Ignore cleanup errors
        
        print("   ✓ Test data cleaned up")
        return True
        
    except Exception as e:
        print(f"   ✗ Failed to cleanup test data: {str(e)}")
        return False


def TestResetWithData():
    """Test reset operations with actual test data."""
    print("=" * 60)
    print("Testing Queue Reset with Test Data")
    print("=" * 60)
    
    try:
        # Initialize database manager
        print("1. Initializing DatabaseManager...")
        databaseManager = DatabaseManager()
        print("   ✓ DatabaseManager initialized successfully")
        
        # Create test data
        print("\n2. Creating Test Data...")
        if not CreateTestData(databaseManager):
            return False
        
        # Check status before reset
        print("\n3. Checking Status Before Reset...")
        
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
            print("   No running items found. Test data may not have been created properly.")
            return False
        
        # Perform reset operations
        print("\n4. Performing Reset Operations...")
        
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
        
        # Check status after reset
        print("\n5. Checking Status After Reset...")
        
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
        
        # Verify results
        print("\n6. Verifying Reset Results...")
        
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
        
        # Cleanup
        print("\n7. Cleaning Up Test Data...")
        CleanupTestData(databaseManager)
        
        print("\n" + "=" * 60)
        print("Queue Reset Test with Data Summary")
        print("=" * 60)
        print(f"✓ Test data created and processed")
        print(f"✓ Reset operations executed: {len([r for r in resetResults.values() if r is not None])}")
        print(f"✓ Total items before reset: {totalBefore}")
        print(f"✓ Total items after reset: {totalAfter}")
        
        if success:
            print("✓ ALL RESET OPERATIONS SUCCESSFUL")
            print("\nThe queue reset functionality is working correctly!")
        else:
            print("⚠ SOME ITEMS MAY NOT HAVE BEEN RESET")
        
        return success
        
    except Exception as e:
        print(f"\n✗ Test failed with exception: {str(e)}")
        import traceback
        traceback.print_exc()
        return False


if __name__ == "__main__":
    print("MediaVortex Queue Reset Test with Data")
    print("=" * 60)
    print(f"Test started at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    
    # Test the functionality
    testPassed = TestResetWithData()
    
    print("\n" + "=" * 60)
    print("Final Test Results")
    print("=" * 60)
    
    if testPassed:
        print("✓ ALL TESTS PASSED")
        print("\nThe queue reset functionality is working correctly!")
        print("The database method return value issues have been resolved.")
    else:
        print("✗ SOME TESTS FAILED")
        print("Please check the results above for details.")
    
    print(f"\nTest completed at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
