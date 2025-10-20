#!/usr/bin/env python3
"""
Add StartTime column to TranscodeAttempts table
Migration script to add start time support for video transcoding
"""

import os
import sys
import sqlite3
from pathlib import Path

# Add the project root to the Python path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from Services.LoggingService import LoggingService


def AddStartTimeColumn():
    """Add StartTime column to TranscodeAttempts table."""
    try:
        LoggingService.LogInfo("Starting migration: Add StartTime column to TranscodeAttempts", "AddStartTimeToTranscodeAttempts", "AddStartTimeColumn")
        
        # Get database path
        db_path = os.path.join(project_root, "Data", "MediaVortex.db")
        
        if not os.path.exists(db_path):
            LoggingService.LogError(f"Database not found at: {db_path}", "AddStartTimeToTranscodeAttempts", "AddStartTimeColumn")
            return False
        
        # Connect to database
        connection = sqlite3.connect(db_path)
        cursor = connection.cursor()
        
        try:
            # Check if column already exists
            cursor.execute("PRAGMA table_info(TranscodeAttempts)")
            columns = [column[1] for column in cursor.fetchall()]
            
            if 'StartTime' in columns:
                LoggingService.LogInfo("StartTime column already exists in TranscodeAttempts table", "AddStartTimeToTranscodeAttempts", "AddStartTimeColumn")
                return True
            
            # Add StartTime column
            LoggingService.LogInfo("Adding StartTime column to TranscodeAttempts table", "AddStartTimeToTranscodeAttempts", "AddStartTimeColumn")
            cursor.execute("ALTER TABLE TranscodeAttempts ADD COLUMN StartTime TEXT")
            
            # Commit changes
            connection.commit()
            
            LoggingService.LogInfo("Successfully added StartTime column to TranscodeAttempts table", "AddStartTimeToTranscodeAttempts", "AddStartTimeColumn")
            return True
            
        except Exception as e:
            LoggingService.LogException("Error adding StartTime column", e, "AddStartTimeToTranscodeAttempts", "AddStartTimeColumn")
            connection.rollback()
            return False
            
        finally:
            connection.close()
            
    except Exception as e:
        LoggingService.LogException("Exception in AddStartTimeColumn", e, "AddStartTimeToTranscodeAttempts", "AddStartTimeColumn")
        return False


def main():
    """Main execution function."""
    try:
        LoggingService.LogInfo("Starting AddStartTimeToTranscodeAttempts migration", "AddStartTimeToTranscodeAttempts", "main")
        
        success = AddStartTimeColumn()
        
        if success:
            LoggingService.LogInfo("Migration completed successfully", "AddStartTimeToTranscodeAttempts", "main")
            print("Migration completed successfully: StartTime column added to TranscodeAttempts table")
        else:
            LoggingService.LogError("Migration failed", "AddStartTimeToTranscodeAttempts", "main")
            print("Migration failed: Could not add StartTime column to TranscodeAttempts table")
            sys.exit(1)
            
    except Exception as e:
        LoggingService.LogException("Exception in main", e, "AddStartTimeToTranscodeAttempts", "main")
        print(f"Migration failed with exception: {str(e)}")
        sys.exit(1)


if __name__ == "__main__":
    main()
