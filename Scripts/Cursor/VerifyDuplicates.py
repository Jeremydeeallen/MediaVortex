#!/usr/bin/env python3
"""
Double-check script to verify MediaFiles duplicates before cleanup.
This script will show sample duplicate groups for manual verification.
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from Repositories.DatabaseManager import DatabaseManager
from Services.LoggingService import LoggingService
from typing import List, Dict, Any

def VerifyDuplicates():
    """Verify duplicate records in MediaFiles table for manual review."""
    try:
        LoggingService.LogInfo("Starting duplicate verification", "VerifyDuplicates", "VerifyDuplicates")
        
        db = DatabaseManager()
        
        # Get case-insensitive duplicates
        print("=== CASE-INSENSITIVE DUPLICATES VERIFICATION ===")
        print("Checking first 10 duplicate groups for manual verification...\n")
        
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
            LIMIT 10
        """
        
        duplicates = db.DatabaseService.ExecuteQuery(query)
        
        if not duplicates:
            print("No case-insensitive duplicates found.")
            return
        
        for i, duplicate in enumerate(duplicates, 1):
            print(f"--- Group {i}: Case-Insensitive Duplicate ---")
            print(f"Lower Path: {duplicate['LowerPath']}")
            print(f"Count: {duplicate['Count']}")
            print(f"IDs: {duplicate['Ids']}")
            print(f"Original Paths:")
            
            # Get detailed records for this group
            ids = [int(id_str) for id_str in duplicate['Ids'].split(',')]
            detail_query = f"""
                SELECT Id, FilePath, TranscodedByMediaVortex, LastScannedDate, SizeMB, Codec, Resolution
                FROM MediaFiles 
                WHERE Id IN ({','.join(map(str, ids))})
                ORDER BY TranscodedByMediaVortex DESC, LastScannedDate DESC
            """
            
            records = db.DatabaseService.ExecuteQuery(detail_query)
            if records:
                records = [dict(row) for row in records]
                
                for j, record in enumerate(records, 1):
                    transcoded_marker = " [TRANSCODED]" if record.get("TranscodedByMediaVortex", False) else ""
                    print(f"  {j}. ID {record['Id']}: {record['FilePath']}{transcoded_marker}")
                    print(f"     LastScanned: {record.get('LastScannedDate', 'N/A')}")
                    print(f"     Size: {record.get('SizeMB', 'N/A')}MB, Codec: {record.get('Codec', 'N/A')}, Resolution: {record.get('Resolution', 'N/A')}")
            
            print()
        
        # Get exact duplicates
        print("=== EXACT DUPLICATES VERIFICATION ===")
        print("Checking for exact duplicate FilePaths...\n")
        
        exact_query = """
            SELECT 
                FilePath,
                COUNT(*) as Count,
                GROUP_CONCAT(Id) as Ids
            FROM MediaFiles 
            GROUP BY FilePath
            HAVING COUNT(*) > 1
            ORDER BY COUNT(*) DESC
            LIMIT 5
        """
        
        exact_duplicates = db.DatabaseService.ExecuteQuery(exact_query)
        
        if not exact_duplicates:
            print("No exact duplicates found.")
        else:
            for i, duplicate in enumerate(exact_duplicates, 1):
                print(f"--- Group {i}: Exact Duplicate ---")
                print(f"Exact Path: {duplicate['FilePath']}")
                print(f"Count: {duplicate['Count']}")
                print(f"IDs: {duplicate['Ids']}")
                
                # Get detailed records
                ids = [int(id_str) for id_str in duplicate['Ids'].split(',')]
                detail_query = f"""
                    SELECT Id, FilePath, TranscodedByMediaVortex, LastScannedDate, SizeMB, Codec, Resolution
                    FROM MediaFiles 
                    WHERE Id IN ({','.join(map(str, ids))})
                    ORDER BY TranscodedByMediaVortex DESC, LastScannedDate DESC
                """
                
                records = db.DatabaseService.ExecuteQuery(detail_query)
                if records:
                    records = [dict(row) for row in records]
                    
                    for j, record in enumerate(records, 1):
                        transcoded_marker = " [TRANSCODED]" if record.get("TranscodedByMediaVortex", False) else ""
                        print(f"  {j}. ID {record['Id']}: {record['FilePath']}{transcoded_marker}")
                        print(f"     LastScanned: {record.get('LastScannedDate', 'N/A')}")
                        print(f"     Size: {record.get('SizeMB', 'N/A')}MB, Codec: {record.get('Codec', 'N/A')}, Resolution: {record.get('Resolution', 'N/A')}")
                
                print()
        
        # Summary statistics
        total_case_insensitive = len(duplicates)
        total_exact = len(exact_duplicates) if exact_duplicates else 0
        
        print("=== SUMMARY ===")
        print(f"Case-insensitive duplicate groups: {total_case_insensitive}")
        print(f"Exact duplicate groups: {total_exact}")
        print(f"Total duplicate groups: {total_case_insensitive + total_exact}")
        
        # Count total records to delete
        total_records_to_delete = 0
        for duplicate in duplicates:
            total_records_to_delete += duplicate['Count'] - 1  # Keep 1, delete the rest
        
        if exact_duplicates:
            for duplicate in exact_duplicates:
                total_records_to_delete += duplicate['Count'] - 1  # Keep 1, delete the rest
        
        print(f"Total records to delete: {total_records_to_delete}")
        print(f"Records to keep: {total_case_insensitive + total_exact}")
        
    except Exception as e:
        LoggingService.LogException("Error during duplicate verification", e, "VerifyDuplicates", "VerifyDuplicates")
        print(f"Error: {e}")

if __name__ == "__main__":
    VerifyDuplicates()
