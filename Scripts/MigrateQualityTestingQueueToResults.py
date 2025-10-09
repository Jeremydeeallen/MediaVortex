#!/usr/bin/env python3
"""
Database Migration: Migrate QualityTestingQueue to QualityTestResults
Converts existing QualityTestingQueue records to QualityTestResults and removes Status column from queue
"""

import sys
import os

# Add the project root to the Python path
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, project_root)

from Repositories.DatabaseManager import DatabaseManager
from Services.LoggingService import LoggingService
from Models.QualityTestResultModel import QualityTestResultModel


def MigrateQualityTestingQueue():
    """
    Migrate existing QualityTestingQueue records to QualityTestResults.
    - Convert Completed/Failed records to QualityTestResults
    - Delete all non-Pending records from QualityTestingQueue
    - Keep Pending records for processing
    """
    try:
        LoggingService.LogInfo("Starting QualityTestingQueue migration", "MigrateQualityTestingQueue", "MigrateQualityTestingQueue")
        
        database_manager = DatabaseManager()
        
        # First, ensure Status column exists in QualityTestResults
        print("Step 1: Ensuring Status column exists in QualityTestResults...")
        check_query = """
            PRAGMA table_info(QualityTestResults)
        """
        columns = database_manager.DatabaseService.ExecuteQuery(check_query)
        column_names = [col['name'] for col in columns]
        
        if 'Status' not in column_names:
            print("Adding Status column to QualityTestResults...")
            alter_query = """
                ALTER TABLE QualityTestResults ADD COLUMN Status TEXT DEFAULT 'Success'
            """
            database_manager.DatabaseService.ExecuteNonQuery(alter_query)
            print("✅ Added Status column to QualityTestResults")
        else:
            print("✅ Status column already exists in QualityTestResults")
        
        # Get all non-Pending records from QualityTestingQueue
        print("Step 2: Getting non-Pending records from QualityTestingQueue...")
        query = """
            SELECT Id, TranscodeAttemptId, OriginalFilePath, TranscodedFilePath, 
                   Status, DateAdded, DateStarted
            FROM QualityTestingQueue 
            WHERE Status != 'Pending'
        """
        records = database_manager.DatabaseService.ExecuteQuery(query)
        
        print(f"Found {len(records)} non-Pending records to migrate")
        
        migrated_count = 0
        for record in records:
            # Check if QualityTestResult already exists for this TranscodeAttemptId
            existing_query = """
                SELECT Id FROM QualityTestResults 
                WHERE TranscodeAttemptId = ?
            """
            existing_results = database_manager.DatabaseService.ExecuteQuery(existing_query, (record['TranscodeAttemptId'],))
            
            if not existing_results:
                # Create QualityTestResult from queue record
                # For failed/incomplete tests, use 0.0 as VMAFScore (not NULL)
                vmaf_score = 0.0 if record['Status'] in ['Failed', 'Running'] else None
                
                result = QualityTestResultModel(
                    VMAFQueueId=record['Id'],  # Use the queue ID as VMAFQueueId
                    TranscodeAttemptId=record['TranscodeAttemptId'],
                    Status=record['Status'],  # Use existing status
                    ErrorMessage=f"Migrated from queue - original status: {record['Status']}",
                    DateTested=record['DateStarted'] or record['DateAdded'],
                    VMAFScore=vmaf_score,  # Use 0.0 for failed tests, NULL for incomplete
                    FileSize=0  # Will be calculated if needed
                )
                
                # Get ProfileName from TranscodeAttempt and find ProfileId
                profile_query = """
                    SELECT ProfileName FROM TranscodeAttempts WHERE Id = ?
                """
                profile_results = database_manager.DatabaseService.ExecuteQuery(profile_query, (record['TranscodeAttemptId'],))
                profile_name = profile_results[0]['ProfileName'] if profile_results else "Unknown"
                
                # Get ProfileId from Profiles table
                profile_id_query = """
                    SELECT Id FROM Profiles WHERE ProfileName = ?
                """
                profile_id_results = database_manager.DatabaseService.ExecuteQuery(profile_id_query, (profile_name,))
                profile_id = profile_id_results[0]['Id'] if profile_id_results else 0
                
                # Save the result with all required fields
                save_query = """
                    INSERT INTO QualityTestResults 
                    (TranscodeAttemptId, TestDuration, PassesThreshold, Rank, ErrorMessage, DateTested, FFmpegCommand, Status, VMAFScore)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """
                database_manager.DatabaseService.ExecuteNonQuery(save_query, (
                    result.TranscodeAttemptId,
                    0.0,  # TestDuration
                    False,  # PassesThreshold
                    None,  # Rank
                    result.ErrorMessage,
                    result.DateTested,
                    None,  # FFmpegCommand
                    result.Status,
                    result.VMAFScore
                ))
                migrated_count += 1
                print(f"  Migrated record {record['Id']} (TranscodeAttemptId: {record['TranscodeAttemptId']})")
            else:
                print(f"  Skipped record {record['Id']} - QualityTestResult already exists")
            
            # Delete from queue
            delete_query = "DELETE FROM QualityTestingQueue WHERE Id = ?"
            database_manager.DatabaseService.ExecuteNonQuery(delete_query, (record['Id'],))
        
        print(f"✅ Migrated {migrated_count} records to QualityTestResults")
        print(f"✅ Cleaned up {len(records)} non-Pending records from QualityTestingQueue")
        
        # Step 3: Remove Status column from QualityTestingQueue
        print("Step 3: Removing Status column from QualityTestingQueue...")
        
        # SQLite doesn't support DROP COLUMN directly, so we need to recreate the table
        create_new_table_query = """
            CREATE TABLE QualityTestingQueue_New (
                Id INTEGER PRIMARY KEY AUTOINCREMENT,
                TranscodeAttemptId INTEGER,
                OriginalFilePath TEXT,
                TranscodedFilePath TEXT,
                LocalSourcePath TEXT,
                DateAdded TIMESTAMP DEFAULT datetime('now', 'localtime'),
                DateStarted TIMESTAMP,
                DateCompleted TIMESTAMP
            )
        """
        
        # Create new table
        database_manager.DatabaseService.ExecuteNonQuery(create_new_table_query)
        
        # Copy Pending records to new table
        copy_query = """
            INSERT INTO QualityTestingQueue_New 
            (Id, TranscodeAttemptId, OriginalFilePath, TranscodedFilePath, LocalSourcePath, DateAdded, DateStarted, DateCompleted)
            SELECT Id, TranscodeAttemptId, OriginalFilePath, TranscodedFilePath, LocalSourcePath, DateAdded, DateStarted, DateCompleted
            FROM QualityTestingQueue
            WHERE Status = 'Pending'
        """
        
        copied_count = database_manager.DatabaseService.ExecuteNonQuery(copy_query)
        
        # Drop old table and rename new one
        database_manager.DatabaseService.ExecuteNonQuery("DROP TABLE QualityTestingQueue")
        database_manager.DatabaseService.ExecuteNonQuery("ALTER TABLE QualityTestingQueue_New RENAME TO QualityTestingQueue")
        
        print(f"✅ Recreated QualityTestingQueue without Status column")
        print(f"✅ Copied {copied_count} Pending records to new table")
        
        return True
        
    except Exception as e:
        LoggingService.LogException("Error migrating QualityTestingQueue", e, 
                                   "MigrateQualityTestingQueue", "MigrateQualityTestingQueue")
        print(f"❌ Migration failed: {e}")
        return False


def main():
    """Main entry point for the migration script."""
    print("=== QualityTestingQueue Migration ===")
    print("Converting QualityTestingQueue to pure work queue:")
    print("1. Migrate non-Pending records to QualityTestResults")
    print("2. Remove Status column from QualityTestingQueue")
    print("3. Keep Pending records for processing")
    print()
    
    success = MigrateQualityTestingQueue()
    
    if success:
        print()
        print("✅ Migration completed successfully!")
        print()
        print("QualityTestingQueue is now a pure work queue:")
        print("  - No Status column")
        print("  - Only contains jobs that need to be processed")
        print("  - Jobs are deleted after processing (success or failure)")
        print()
        print("QualityTestResults now contains:")
        print("  - Complete history of all quality test attempts")
        print("  - Status column (Running/Success/Failed)")
        print("  - ErrorMessage for failed tests")
    else:
        print()
        print("❌ Migration failed!")
        sys.exit(1)


if __name__ == "__main__":
    main()
