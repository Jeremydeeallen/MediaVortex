#!/usr/bin/env python3
"""
Add File Replacement Fields to TranscodeAttempts Table
Database migration script for auto-replace VMAF feature
"""

import sys
import os
from datetime import datetime

# Add the project root to the Python path
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, project_root)

from Repositories.DatabaseManager import DatabaseManager
from Services.LoggingService import LoggingService


def AddFileReplacementFields():
    """Add file replacement tracking fields to TranscodeAttempts table."""
    try:
        LoggingService.LogInfo("Starting file replacement fields migration", "AddFileReplacementFields", "AddFileReplacementFields")
        
        database_manager = DatabaseManager()
        
        # Check if fields already exist
        check_query = """
            PRAGMA table_info(TranscodeAttempts)
        """
        columns = database_manager.DatabaseService.ExecuteQuery(check_query)
        
        existing_columns = [col['name'] for col in columns]
        
        fields_to_add = [
            {
                'name': 'FileReplaced',
                'type': 'BOOLEAN',
                'default': '0',
                'description': 'Whether the original file was replaced with transcoded version'
            },
            {
                'name': 'FileReplacedDate', 
                'type': 'DATETIME',
                'default': 'NULL',
                'description': 'When the file replacement occurred'
            },
            {
                'name': 'ReplacementType',
                'type': 'TEXT',
                'default': 'NULL',
                'description': 'Type of replacement: Auto or Manual'
            }
        ]
        
        added_count = 0
        for field in fields_to_add:
            if field['name'] not in existing_columns:
                # Add the column
                alter_query = f"ALTER TABLE TranscodeAttempts ADD COLUMN {field['name']} {field['type']}"
                
                result = database_manager.DatabaseService.ExecuteNonQuery(alter_query)
                
                if result:
                    LoggingService.LogInfo(f"Added column: {field['name']} ({field['type']})", 
                                         "AddFileReplacementFields", "AddFileReplacementFields")
                    added_count += 1
                else:
                    LoggingService.LogError(f"Failed to add column: {field['name']}", 
                                           "AddFileReplacementFields", "AddFileReplacementFields")
            else:
                LoggingService.LogInfo(f"Column already exists: {field['name']}", 
                                     "AddFileReplacementFields", "AddFileReplacementFields")
        
        LoggingService.LogInfo(f"File replacement fields migration completed. Added {added_count} new columns.", 
                              "AddFileReplacementFields", "AddFileReplacementFields")
        
        return True
        
    except Exception as e:
        LoggingService.LogException("Error adding file replacement fields", e, "AddFileReplacementFields", "AddFileReplacementFields")
        return False


if __name__ == "__main__":
    AddFileReplacementFields()

