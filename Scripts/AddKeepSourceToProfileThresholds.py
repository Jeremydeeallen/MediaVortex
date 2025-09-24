#!/usr/bin/env python3
"""
Add KeepSource column to ProfileThresholds table
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from Repositories.DatabaseManager import DatabaseManager
from Services.LoggingService import LoggingService

def AddKeepSourceToProfileThresholds():
    """Add KeepSource boolean column to ProfileThresholds table."""
    try:
        LoggingService.LogInfo("Starting AddKeepSourceToProfileThresholds script", "AddKeepSourceToProfileThresholds", "AddKeepSourceToProfileThresholds")
        
        db = DatabaseManager()
        
        # Check if column already exists
        check_query = """
        SELECT COUNT(*) as count 
        FROM pragma_table_info('ProfileThresholds') 
        WHERE name = 'KeepSource'
        """
        
        result = db.DatabaseService.ExecuteQuery(check_query)
        if result and result[0]['count'] > 0:
            print("✅ KeepSource column already exists in ProfileThresholds table")
            return
        
        # Add the KeepSource column
        alter_query = """
        ALTER TABLE ProfileThresholds 
        ADD COLUMN KeepSource BOOLEAN DEFAULT 0
        """
        
        db.DatabaseService.ExecuteNonQuery(alter_query)
        print("✅ Successfully added KeepSource column to ProfileThresholds table")
        
        # Update existing records to default to False (0)
        update_query = """
        UPDATE ProfileThresholds 
        SET KeepSource = 0 
        WHERE KeepSource IS NULL
        """
        
        db.DatabaseService.ExecuteNonQuery(update_query)
        print("✅ Updated existing ProfileThresholds records with default KeepSource value")
        
        LoggingService.LogInfo("Successfully completed AddKeepSourceToProfileThresholds script", "AddKeepSourceToProfileThresholds", "AddKeepSourceToProfileThresholds")
        
    except Exception as e:
        error_msg = f"Error adding KeepSource column to ProfileThresholds: {str(e)}"
        print(f"❌ {error_msg}")
        LoggingService.LogException("Error in AddKeepSourceToProfileThresholds script", e, "AddKeepSourceToProfileThresholds", "AddKeepSourceToProfileThresholds")

if __name__ == '__main__':
    AddKeepSourceToProfileThresholds()
