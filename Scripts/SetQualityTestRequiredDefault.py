#!/usr/bin/env python3
"""
Database Migration: Set QualityTestRequired Default to 1
Updates existing TranscodeAttempts records to have QualityTestRequired = 1
"""

import sys
import os

# Add the project root to the Python path
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, project_root)

from Repositories.DatabaseManager import DatabaseManager
from Services.LoggingService import LoggingService


def SetQualityTestRequiredDefault():
    """Set QualityTestRequired column to default to 1."""
    try:
        LoggingService.LogInfo("Starting QualityTestRequired default migration", "SetQualityTestRequiredDefault", "SetQualityTestRequiredDefault")
        
        database_manager = DatabaseManager()
        
        # First, update existing NULL values to 1
        update_query = """
            UPDATE TranscodeAttempts 
            SET QualityTestRequired = 1 
            WHERE QualityTestRequired IS NULL
        """
        
        affected_rows = database_manager.DatabaseService.ExecuteNonQuery(update_query)
        
        LoggingService.LogInfo(f"Updated {affected_rows} TranscodeAttempts records to have QualityTestRequired = 1", 
                              "SetQualityTestRequiredDefault", "SetQualityTestRequiredDefault")
        
        # Also update any records that might have 0 to 1 (optional - uncomment if needed)
        # update_zero_query = """
        #     UPDATE TranscodeAttempts 
        #     SET QualityTestRequired = 1 
        #     WHERE QualityTestRequired = 0
        # """
        # zero_affected = database_manager.DatabaseService.ExecuteNonQuery(update_zero_query)
        # LoggingService.LogInfo(f"Updated {zero_affected} TranscodeAttempts records from 0 to 1", 
        #                       "SetQualityTestRequiredDefault", "SetQualityTestRequiredDefault")
        
        print("✅ Updated existing TranscodeAttempts to have QualityTestRequired = 1")
        print(f"✅ Affected {affected_rows} records")
        
        return True
        
    except Exception as e:
        LoggingService.LogException("Error setting QualityTestRequired default", e, 
                                   "SetQualityTestRequiredDefault", "SetQualityTestRequiredDefault")
        print(f"❌ Error setting QualityTestRequired default: {e}")
        return False


def main():
    """Main entry point for the migration script."""
    print("=== QualityTestRequired Default Migration ===")
    print("Setting QualityTestRequired = 1 for all existing TranscodeAttempts records")
    print()
    
    success = SetQualityTestRequiredDefault()
    
    if success:
        print()
        print("✅ Migration completed successfully!")
        print("Note: SQLite doesn't support ALTER COLUMN DEFAULT directly.")
        print("The default should be set in the application code when creating new records.")
    else:
        print()
        print("❌ Migration failed!")
        sys.exit(1)


if __name__ == "__main__":
    main()
