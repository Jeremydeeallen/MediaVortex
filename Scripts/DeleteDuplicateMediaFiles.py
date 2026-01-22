#!/usr/bin/env python3
"""
Delete Duplicate MediaFiles Script

This script deletes duplicate MediaFiles entries based on FilePath.
For each duplicate group, it keeps the record with the smallest Id
and deletes all others in batches of 100 until all duplicates are removed.
After completion, it runs VACUUM to reclaim database space.

Usage:
    py Scripts/DeleteDuplicateMediaFiles.py
"""

import os
import sys
from pathlib import Path

# Add project root to path
ProjectRoot = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ProjectRoot)

from Services.DatabaseService import DatabaseService
from Services.LoggingService import LoggingService


def DeleteDuplicateMediaFiles():
    """Delete duplicate MediaFiles in batches of 100 until complete."""
    try:
        DatabaseServiceInstance = DatabaseService()
        BatchSize = 100
        TotalDeleted = 0
        BatchNumber = 0
        
        print("=" * 60)
        print("MediaVortex Duplicate MediaFiles Deletion")
        print("=" * 60)
        print(f"Batch size: {BatchSize} records per batch")
        print()
        
        # Check initial duplicate count
        CountQuery = """
            SELECT COUNT(*) as DuplicateCount
            FROM MediaFiles m
            WHERE m.FilePath IN (
                SELECT FilePath
                FROM MediaFiles
                GROUP BY FilePath
                HAVING COUNT(*) > 1
            )
            AND m.Id > (
                SELECT MIN(Id) 
                FROM MediaFiles m2 
                WHERE m2.FilePath = m.FilePath
            )
        """
        
        InitialResult = DatabaseServiceInstance.ExecuteQuery(CountQuery)
        InitialCount = InitialResult[0]['DuplicateCount'] if InitialResult else 0
        
        if InitialCount == 0:
            print("✅ No duplicates found in MediaFiles table.")
            return {'Success': True, 'TotalDeleted': 0}
        
        print(f"📊 Found {InitialCount} duplicate records to delete")
        print(f"🔄 Processing in batches of {BatchSize}...")
        print()
        
        # Delete duplicates in batches
        DeleteQuery = """
            DELETE FROM MediaFiles
            WHERE Id IN (
                SELECT m.Id
                FROM MediaFiles m
                INNER JOIN (
                    SELECT FilePath, MIN(Id) AS MinId
                    FROM MediaFiles
                    GROUP BY FilePath
                    HAVING COUNT(*) > 1
                ) dup ON m.FilePath = dup.FilePath
                WHERE m.Id > dup.MinId
                ORDER BY m.Id
                LIMIT ?
            )
        """
        
        RowsDeleted = BatchSize
        while RowsDeleted > 0:
            BatchNumber += 1
            Connection = DatabaseServiceInstance.GetConnection()
            try:
                Cursor = Connection.cursor()
                Cursor.execute(DeleteQuery, (BatchSize,))
                RowsDeleted = Cursor.rowcount
                Connection.commit()
                
                if RowsDeleted > 0:
                    TotalDeleted += RowsDeleted
                    RemainingCount = InitialCount - TotalDeleted
                    ProgressPercent = (TotalDeleted / InitialCount) * 100
                    print(f"Batch {BatchNumber}: Deleted {RowsDeleted} records | "
                          f"Total: {TotalDeleted}/{InitialCount} ({ProgressPercent:.1f}%) | "
                          f"Remaining: {RemainingCount}")
                else:
                    print(f"Batch {BatchNumber}: No more duplicates found")
                    
            except Exception as e:
                Connection.rollback()
                LoggingService.LogException(f"Error deleting batch {BatchNumber}", e,
                                          'DeleteDuplicateMediaFiles', 'DeleteDuplicateMediaFiles')
                raise
            finally:
                Connection.close()
        
        print()
        print(f"✅ Deletion complete: {TotalDeleted} duplicate records removed")
        
        # Verify no duplicates remain
        VerifyQuery = """
            SELECT FilePath, COUNT(*) as Count
            FROM MediaFiles
            GROUP BY FilePath
            HAVING COUNT(*) > 1
        """
        RemainingDuplicates = DatabaseServiceInstance.ExecuteQuery(VerifyQuery)
        
        if RemainingDuplicates:
            print(f"⚠️  Warning: {len(RemainingDuplicates)} duplicate FilePaths still remain")
            for Dup in RemainingDuplicates[:10]:  # Show first 10
                print(f"   {Dup['FilePath']}: {Dup['Count']} records")
            if len(RemainingDuplicates) > 10:
                print(f"   ... and {len(RemainingDuplicates) - 10} more")
        else:
            print("✅ Verification: No duplicates remaining")
        
        # Run VACUUM to reclaim space
        print()
        print("🧹 Running VACUUM to reclaim database space...")
        Connection = DatabaseServiceInstance.GetConnection()
        try:
            Connection.execute("VACUUM")
            Connection.commit()
            print("✅ VACUUM completed successfully")
        except Exception as e:
            LoggingService.LogException("Error running VACUUM", e,
                                      'DeleteDuplicateMediaFiles', 'DeleteDuplicateMediaFiles')
            print(f"⚠️  Warning: VACUUM failed: {str(e)}")
        finally:
            Connection.close()
        
        print()
        print("=" * 60)
        print("Process completed successfully")
        print("=" * 60)
        
        return {
            'Success': True,
            'TotalDeleted': TotalDeleted,
            'BatchesProcessed': BatchNumber
        }
        
    except KeyboardInterrupt:
        print("\n⚠️  Operation cancelled by user")
        return {'Success': False, 'Error': 'Cancelled by user'}
    except Exception as e:
        LoggingService.LogException("Error in duplicate deletion script", e,
                                   'DeleteDuplicateMediaFiles', 'DeleteDuplicateMediaFiles')
        print(f"\n❌ Error: {str(e)}")
        return {'Success': False, 'Error': str(e)}


def main():
    """Main entry point."""
    Result = DeleteDuplicateMediaFiles()
    
    if Result['Success']:
        sys.exit(0)
    else:
        sys.exit(1)


if __name__ == "__main__":
    main()






