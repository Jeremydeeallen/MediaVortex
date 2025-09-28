#!/usr/bin/env python3
"""
Migration script to add new fields to QualityTestProgress table
"""
import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from Repositories.DatabaseManager import DatabaseManager
from Services.LoggingService import LoggingService

def AddQualityTestProgressFields():
    """Add new fields to QualityTestProgress table."""
    try:
        LoggingService.LogInfo("Starting QualityTestProgress schema migration", "AddQualityTestProgressFields")
        
        DatabaseManagerInstance = DatabaseManager()
        
        # Add new columns to QualityTestProgress table
        MigrationQueries = [
            "ALTER TABLE QualityTestProgress ADD COLUMN CurrentTime TEXT",
            "ALTER TABLE QualityTestProgress ADD COLUMN CurrentFrame INTEGER", 
            "ALTER TABLE QualityTestProgress ADD COLUMN TotalFrames INTEGER",
            "ALTER TABLE QualityTestProgress ADD COLUMN ProcessingSpeed TEXT"
        ]
        
        for Query in MigrationQueries:
            try:
                DatabaseManagerInstance.DatabaseService.ExecuteNonQuery(Query)
                LoggingService.LogInfo(f"Successfully executed: {Query}", "AddQualityTestProgressFields")
            except Exception as e:
                if "duplicate column name" in str(e).lower():
                    LoggingService.LogInfo(f"Column already exists, skipping: {Query}", "AddQualityTestProgressFields")
                else:
                    LoggingService.LogError(f"Error executing {Query}: {str(e)}", "AddQualityTestProgressFields")
                    raise
        
        LoggingService.LogInfo("QualityTestProgress schema migration completed successfully", "AddQualityTestProgressFields")
        return True
        
    except Exception as e:
        LoggingService.LogException("Exception during QualityTestProgress migration", e, "AddQualityTestProgressFields")
        return False

if __name__ == "__main__":
    Success = AddQualityTestProgressFields()
    if Success:
        print("✅ QualityTestProgress migration completed successfully")
    else:
        print("❌ QualityTestProgress migration failed")
        sys.exit(1)
