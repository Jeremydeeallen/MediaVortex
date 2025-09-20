#!/usr/bin/env python3
"""
Database migration script to add FileModificationTime column to MediaFiles table.
This script adds the FileModificationTime column to track when files were last modified.
"""

import os
import sys
from pathlib import Path

# Add the parent directory to the path so we can import our modules
sys.path.append(str(Path(__file__).parent.parent))

from Services.DatabaseService import DatabaseService
from Services.LoggingService import LoggingService

def AddFileModificationTimeColumn():
    """Add FileModificationTime column to MediaFiles table."""
    try:
        LoggingService.LogInfo("Starting database migration: Add FileModificationTime column", 'AddFileModificationTimeColumn', 'Migration')
        
        DatabaseServiceInstance = DatabaseService()
        
        # Check if column already exists
        CheckColumnQuery = """
            PRAGMA table_info(MediaFiles)
        """
        Columns = DatabaseServiceInstance.ExecuteQuery(CheckColumnQuery)
        
        ColumnExists = any(column['name'] == 'FileModificationTime' for column in Columns)
        
        if ColumnExists:
            LoggingService.LogInfo("FileModificationTime column already exists, skipping migration", 'AddFileModificationTimeColumn', 'Migration')
            return True
        
        # Add the column
        AddColumnQuery = """
            ALTER TABLE MediaFiles 
            ADD COLUMN FileModificationTime DATETIME
        """
        
        DatabaseServiceInstance.ExecuteNonQuery(AddColumnQuery)
        LoggingService.LogInfo("Successfully added FileModificationTime column to MediaFiles table", 'AddFileModificationTimeColumn', 'Migration')
        
        return True
        
    except Exception as e:
        LoggingService.LogException("Error adding FileModificationTime column", e, 'AddFileModificationTimeColumn', 'Migration')
        return False

def main():
    """Main function for the migration script."""
    try:
        print("Adding FileModificationTime column to MediaFiles table...")
        
        Success = AddFileModificationTimeColumn()
        
        if Success:
            print("Migration completed successfully!")
        else:
            print("Migration failed!")
            sys.exit(1)
            
    except Exception as e:
        print(f"Fatal error in migration: {str(e)}")
        LoggingService.LogException("Fatal error in migration", e, 'main', 'Migration')
        sys.exit(1)

if __name__ == "__main__":
    main()
