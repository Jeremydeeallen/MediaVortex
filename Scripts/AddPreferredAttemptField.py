#!/usr/bin/env python3
"""
Add PreferredAttempt Field to TranscodeAttempts Table
Database migration script for preferred transcode attempt feature
"""

import sys
import os
from datetime import datetime

# Add the project root to the Python path
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, project_root)

from Repositories.DatabaseManager import DatabaseManager
from Services.LoggingService import LoggingService


def AddPreferredAttemptField():
    """Add PreferredAttempt field to TranscodeAttempts table."""
    try:
        LoggingService.LogInfo("Starting PreferredAttempt field migration", "AddPreferredAttemptField", "AddPreferredAttemptField")
        
        database_manager = DatabaseManager()
        
        # Check if field already exists
        check_query = """
            PRAGMA table_info(TranscodeAttempts)
        """
        columns = database_manager.DatabaseService.ExecuteQuery(check_query)
        
        existing_columns = [col['name'] for col in columns]
        
        if 'PreferredAttempt' not in existing_columns:
            # Add the column
            alter_query = "ALTER TABLE TranscodeAttempts ADD COLUMN PreferredAttempt BOOLEAN DEFAULT 0"
            
            result = database_manager.DatabaseService.ExecuteNonQuery(alter_query)
            
            if result:
                LoggingService.LogInfo("Added column: PreferredAttempt (BOOLEAN)", 
                                     "AddPreferredAttemptField", "AddPreferredAttemptField")
                print("✅ Successfully added PreferredAttempt field to TranscodeAttempts table")
                return True
            else:
                LoggingService.LogError("Failed to add column: PreferredAttempt", 
                                       "AddPreferredAttemptField", "AddPreferredAttemptField")
                print("❌ Failed to add PreferredAttempt field")
                return False
        else:
            LoggingService.LogInfo("Column already exists: PreferredAttempt", 
                                 "AddPreferredAttemptField", "AddPreferredAttemptField")
            print("✅ PreferredAttempt column already exists in TranscodeAttempts table")
            return True
        
    except Exception as e:
        LoggingService.LogException("Error adding PreferredAttempt field", e, "AddPreferredAttemptField", "AddPreferredAttemptField")
        print(f"❌ Error: {str(e)}")
        return False


if __name__ == "__main__":
    AddPreferredAttemptField()

