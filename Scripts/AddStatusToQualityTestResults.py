#!/usr/bin/env python3
"""
Database Migration: Add Status column to QualityTestResults table
Adds Status column to track Running/Success/Failed states
"""

import sys
import os

# Add the project root to the Python path
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, project_root)

from Repositories.DatabaseManager import DatabaseManager
from Services.LoggingService import LoggingService


def AddStatusToQualityTestResults():
    """Add Status column to QualityTestResults table."""
    try:
        LoggingService.LogInfo("Starting QualityTestResults Status column migration", "AddStatusToQualityTestResults", "AddStatusToQualityTestResults")
        
        database_manager = DatabaseManager()
        
        # Check if Status column already exists
        check_query = """
            PRAGMA table_info(QualityTestResults)
        """
        columns = database_manager.DatabaseService.ExecuteQuery(check_query)
        column_names = [col['name'] for col in columns]
        
        if 'Status' in column_names:
            print("✅ Status column already exists in QualityTestResults table")
            return True
        
        # Add Status column
        alter_query = """
            ALTER TABLE QualityTestResults ADD COLUMN Status TEXT DEFAULT 'Success'
        """
        
        database_manager.DatabaseService.ExecuteNonQuery(alter_query)
        
        # Update existing records to have appropriate Status based on VMAFScore and ErrorMessage
        update_query = """
            UPDATE QualityTestResults 
            SET Status = CASE 
                WHEN ErrorMessage IS NOT NULL AND ErrorMessage != '' THEN 'Failed'
                WHEN VMAFScore IS NOT NULL THEN 'Success'
                ELSE 'Success'
            END
        """
        
        affected_rows = database_manager.DatabaseService.ExecuteNonQuery(update_query)
        
        LoggingService.LogInfo(f"Added Status column to QualityTestResults and updated {affected_rows} existing records", 
                              "AddStatusToQualityTestResults", "AddStatusToQualityTestResults")
        
        print("✅ Added Status column to QualityTestResults table")
        print(f"✅ Updated {affected_rows} existing records with appropriate Status values")
        
        return True
        
    except Exception as e:
        LoggingService.LogException("Error adding Status column to QualityTestResults", e, 
                                   "AddStatusToQualityTestResults", "AddStatusToQualityTestResults")
        print(f"❌ Error adding Status column: {e}")
        return False


def main():
    """Main entry point for the migration script."""
    print("=== QualityTestResults Status Column Migration ===")
    print("Adding Status column to track Running/Success/Failed states")
    print()
    
    success = AddStatusToQualityTestResults()
    
    if success:
        print()
        print("✅ Migration completed successfully!")
        print("Status values:")
        print("  - 'Success': VMAF score recorded successfully")
        print("  - 'Failed': ErrorMessage present")
        print("  - 'Running': Will be used for new records created at start of testing")
    else:
        print()
        print("❌ Migration failed!")
        sys.exit(1)


if __name__ == "__main__":
    main()
