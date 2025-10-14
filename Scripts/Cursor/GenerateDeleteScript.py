#!/usr/bin/env python3
"""
Generate SQL delete script for MediaFiles duplicates.
This script creates the DELETE statements for duplicate records.
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from Repositories.DatabaseManager import DatabaseManager
from Services.LoggingService import LoggingService
from typing import List, Dict, Any

def GenerateDeleteScript():
    """Generate SQL delete script for duplicate MediaFiles records."""
    try:
        LoggingService.LogInfo("Generating delete script for MediaFiles duplicates", "GenerateDeleteScript", "GenerateDeleteScript")
        
        db = DatabaseManager()
        
        # Get case-insensitive duplicates
        print("=== GENERATING DELETE SCRIPT FOR MEDIAFILES DUPLICATES ===")
        
        query = """
            SELECT 
                LOWER(FilePath) as LowerPath,
                COUNT(*) as Count,
                GROUP_CONCAT(Id) as Ids,
                GROUP_CONCAT(FilePath) as OriginalPaths
            FROM MediaFiles 
            GROUP BY LOWER(FilePath)
            HAVING COUNT(*) > 1
            ORDER BY COUNT(*) DESC
        """
        
        duplicates = db.DatabaseService.ExecuteQuery(query)
        
        if not duplicates:
            print("No case-insensitive duplicates found.")
            return
        
        # Collect all IDs to delete
        ids_to_delete = []
        delete_details = []
        
        for duplicate in duplicates:
            ids = [int(id_str) for id_str in duplicate['Ids'].split(',')]
            
            # Get detailed records to determine which to keep/delete
            detail_query = f"""
                SELECT Id, FilePath, TranscodedByMediaVortex, LastScannedDate
                FROM MediaFiles 
                WHERE Id IN ({','.join(map(str, ids))})
                ORDER BY TranscodedByMediaVortex DESC, LastScannedDate DESC
            """
            
            records = db.DatabaseService.ExecuteQuery(detail_query)
            if records:
                records = [dict(row) for row in records]
                
                # Keep the first record (highest priority), delete the rest
                keep_record = records[0]
                delete_records = records[1:]
                
                for delete_record in delete_records:
                    ids_to_delete.append(delete_record['Id'])
                    delete_details.append({
                        'Id': delete_record['Id'],
                        'FilePath': delete_record['FilePath'],
                        'KeepId': keep_record['Id'],
                        'KeepFilePath': keep_record['FilePath'],
                        'Reason': 'TranscodedByMediaVortex = TRUE' if keep_record.get('TranscodedByMediaVortex', False) else 'Most recent LastScannedDate'
                    })
        
        # Get exact duplicates
        exact_query = """
            SELECT 
                FilePath,
                COUNT(*) as Count,
                GROUP_CONCAT(Id) as Ids
            FROM MediaFiles 
            GROUP BY FilePath
            HAVING COUNT(*) > 1
            ORDER BY COUNT(*) DESC
        """
        
        exact_duplicates = db.DatabaseService.ExecuteQuery(exact_query)
        
        if exact_duplicates:
            for duplicate in exact_duplicates:
                ids = [int(id_str) for id_str in duplicate['Ids'].split(',')]
                
                # Get detailed records
                detail_query = f"""
                    SELECT Id, FilePath, TranscodedByMediaVortex, LastScannedDate
                    FROM MediaFiles 
                    WHERE Id IN ({','.join(map(str, ids))})
                    ORDER BY TranscodedByMediaVortex DESC, LastScannedDate DESC
                """
                
                records = db.DatabaseService.ExecuteQuery(detail_query)
                if records:
                    records = [dict(row) for row in records]
                    
                    # Keep the first record, delete the rest
                    keep_record = records[0]
                    delete_records = records[1:]
                    
                    for delete_record in delete_records:
                        ids_to_delete.append(delete_record['Id'])
                        delete_details.append({
                            'Id': delete_record['Id'],
                            'FilePath': delete_record['FilePath'],
                            'KeepId': keep_record['Id'],
                            'KeepFilePath': keep_record['FilePath'],
                            'Reason': 'TranscodedByMediaVortex = TRUE' if keep_record.get('TranscodedByMediaVortex', False) else 'Most recent LastScannedDate'
                        })
        
        from datetime import datetime
        timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        
        # Generate SQL script
        sql_script = f"""-- MediaFiles Duplicate Cleanup Script
-- Generated on: {timestamp}
-- Total records to delete: {len(ids_to_delete)}

-- Backup recommendation (run before executing delete):
-- CREATE TABLE MediaFiles_Backup_{timestamp} AS SELECT * FROM MediaFiles;

-- Delete duplicate records
DELETE FROM MediaFiles WHERE Id IN ({','.join(map(str, ids_to_delete))});

-- Verification query (run after delete):
-- SELECT COUNT(*) as RemainingRecords FROM MediaFiles;
-- SELECT COUNT(DISTINCT LOWER(FilePath)) as UniquePaths FROM MediaFiles;

-- Delete details for reference:
"""
        
        for detail in delete_details:
            sql_script += f"-- Deleted ID {detail['Id']}: {detail['FilePath']} (Kept ID {detail['KeepId']}: {detail['KeepFilePath']} - {detail['Reason']})\n"
        
        # Write to file
        script_filename = f"MediaFiles_Duplicate_Cleanup_{timestamp}.sql"
        script_path = os.path.join(os.path.dirname(__file__), script_filename)
        
        with open(script_path, 'w', encoding='utf-8') as f:
            f.write(sql_script)
        
        print(f"SQL delete script generated: {script_path}")
        print(f"Total records to delete: {len(ids_to_delete)}")
        print(f"Total duplicate groups processed: {len(duplicates) + (len(exact_duplicates) if exact_duplicates else 0)}")
        
        # Show first 10 delete details for verification
        print("\n=== FIRST 10 DELETE OPERATIONS ===")
        for i, detail in enumerate(delete_details[:10], 1):
            print(f"{i}. Delete ID {detail['Id']}: {detail['FilePath']}")
            print(f"   Keep ID {detail['KeepId']}: {detail['KeepFilePath']} ({detail['Reason']})")
        
        if len(delete_details) > 10:
            print(f"... and {len(delete_details) - 10} more records")
        
    except Exception as e:
        LoggingService.LogException("Error generating delete script", e, "GenerateDeleteScript", "GenerateDeleteScript")
        print(f"Error: {e}")

if __name__ == "__main__":
    GenerateDeleteScript()
