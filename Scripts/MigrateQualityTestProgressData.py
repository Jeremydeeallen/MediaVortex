#!/usr/bin/env python3
"""
Migration script to extract ETA from CurrentStep and populate new fields
"""
import sys
import os
import re
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from Repositories.DatabaseManager import DatabaseManager
from Services.LoggingService import LoggingService

def MigrateQualityTestProgressData():
    """Extract ETA from CurrentStep and populate new fields."""
    try:
        LoggingService.LogInfo("Starting QualityTestProgress data migration", "MigrateQualityTestProgressData")
        
        DatabaseManagerInstance = DatabaseManager()
        
        # Get all existing records with embedded ETA
        Query = """
            SELECT Id, CurrentStep, ETA 
            FROM QualityTestProgress 
            WHERE CurrentStep LIKE '%(ETA:%' AND (ETA IS NULL OR ETA = '')
        """
        
        Records = DatabaseManagerInstance.DatabaseService.ExecuteQuery(Query)
        LoggingService.LogInfo(f"Found {len(Records)} records to migrate", "MigrateQualityTestProgressData")
        
        UpdatedCount = 0
        for Record in Records:
            RecordId = Record['Id']
            CurrentStep = Record['CurrentStep']
            CurrentETA = Record['ETA']
            
            # Extract ETA from CurrentStep if it contains "(ETA: XX:XX:XX)"
            ExtractedETA = None
            if "(ETA:" in CurrentStep:
                EtaMatch = re.search(r'\(ETA:\s*([^)]+)\)', CurrentStep)
                if EtaMatch:
                    ExtractedETA = EtaMatch.group(1).strip()
            
            # Clean up CurrentStep to remove embedded ETA
            CleanCurrentStep = re.sub(r'\s*\(ETA:[^)]+\)', '', CurrentStep).strip()
            
            # Update the record with extracted data
            if ExtractedETA or CleanCurrentStep != CurrentStep:
                UpdateQuery = """
                    UPDATE QualityTestProgress 
                    SET CurrentStep = ?, ETA = ?
                    WHERE Id = ?
                """
                
                DatabaseManagerInstance.DatabaseService.ExecuteNonQuery(
                    UpdateQuery, 
                    (CleanCurrentStep, ExtractedETA, RecordId)
                )
                
                UpdatedCount += 1
                LoggingService.LogInfo(f"Updated record {RecordId}: CurrentStep='{CleanCurrentStep}', ETA='{ExtractedETA}'", "MigrateQualityTestProgressData")
        
        LoggingService.LogInfo(f"QualityTestProgress data migration completed. Updated {UpdatedCount} records.", "MigrateQualityTestProgressData")
        return True
        
    except Exception as e:
        LoggingService.LogException("Exception during QualityTestProgress data migration", e, "MigrateQualityTestProgressData")
        return False

if __name__ == "__main__":
    Success = MigrateQualityTestProgressData()
    if Success:
        print("✅ QualityTestProgress data migration completed successfully")
    else:
        print("❌ QualityTestProgress data migration failed")
        sys.exit(1)
