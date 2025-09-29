#!/usr/bin/env python3
"""
Clean up test data from previous test runs.
"""

import sys
import os

# Add the parent directory to the path so we can import from the main application
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from Repositories.DatabaseManager import DatabaseManager


def CleanupTestData():
    """Clean up test data."""
    print("Cleaning up test data...")
    
    try:
        databaseManager = DatabaseManager()
        
        # Clean up in reverse order to avoid foreign key constraints
        cleanupQueries = [
            "DELETE FROM ServiceCommands WHERE CommandType LIKE 'TestCommand%'",
            "DELETE FROM QualityTestProgress WHERE Status = 'Running'",
            "DELETE FROM TranscodeProgress WHERE Status = 'Running'",
            "DELETE FROM TranscodeAttempts WHERE FilePath LIKE '/test/%'",
            "DELETE FROM QualityTestingQueue WHERE TranscodeAttemptId IN (1, 2, 3)",
            "DELETE FROM TranscodeQueue WHERE FilePath LIKE '/test/%'"
        ]
        
        for query in cleanupQueries:
            try:
                result = databaseManager.DatabaseService.ExecuteNonQuery(query)
                print(f"   ✓ Cleaned up: {result} rows affected")
            except Exception as e:
                print(f"   ⚠ Cleanup query failed: {str(e)}")
        
        print("   ✓ Test data cleanup completed")
        return True
        
    except Exception as e:
        print(f"   ✗ Failed to cleanup test data: {str(e)}")
        return False


if __name__ == "__main__":
    print("MediaVortex Test Data Cleanup")
    print("=" * 40)
    
    success = CleanupTestData()
    
    if success:
        print("\n✓ Test data cleanup completed successfully")
    else:
        print("\n✗ Test data cleanup failed")
