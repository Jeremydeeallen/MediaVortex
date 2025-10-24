#!/usr/bin/env python3
"""
Merge Z: Drive Duplicate RootFolders Script

This script merges duplicate RootFolder entries on the Z: drive that were created
due to case sensitivity issues. It uses filesystem validation to determine the
correct case and merges all duplicates into a single canonical entry.

Usage:
    py Scripts/MergeZDriveDuplicateRootFolders.py [--dry-run] [--verbose]

Options:
    --dry-run    Preview changes without making them
    --verbose    Show detailed logging
"""

import os
import sys
import argparse
from pathlib import Path
from typing import List, Dict, Any, Optional
from datetime import datetime

# Add project root to path
ProjectRoot = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ProjectRoot)

from Repositories.DatabaseManager import DatabaseManager
from Services.LoggingService import LoggingService


class ZDriveRootFolderMerger:
    """Merges duplicate Z: drive RootFolder entries using filesystem validation."""
    
    def __init__(self, DryRun: bool = False, Verbose: bool = False):
        self.DryRun = DryRun
        self.Verbose = Verbose
        self.DatabaseManager = DatabaseManager()
        self.Changes = []
        self.Errors = []
        
    def GetCanonicalPathFromFilesystem(self, Path: str) -> str:
        """Get the actual case-sensitive path as it exists on the filesystem."""
        try:
            if not Path:
                return Path
            
            # Use pathlib to resolve the actual path from filesystem
            resolved_path = Path(Path).resolve()
            
            # Return as string with actual filesystem case
            return str(resolved_path)
            
        except Exception as e:
            LoggingService.LogWarning(f"Could not resolve canonical path for {Path}, using original", 
                                     'GetCanonicalPathFromFilesystem', 'ZDriveRootFolderMerger')
            return Path
    
    def FindDuplicateRootFolders(self) -> List[Dict[str, Any]]:
        """Find duplicate RootFolders using case-insensitive grouping."""
        try:
            # Query to find duplicates using case-insensitive comparison
            Query = """
                SELECT 
                    LOWER(RootFolder) as LowercasePath,
                    COUNT(*) as DuplicateCount,
                    GROUP_CONCAT(Id) as RootFolderIds,
                    GROUP_CONCAT(RootFolder) as AllPaths,
                    GROUP_CONCAT(LastScannedDate) as ScanDates
                FROM RootFolders 
                WHERE LOWER(RootFolder) LIKE 'z:%'
                GROUP BY LOWER(RootFolder)
                HAVING COUNT(*) > 1
                ORDER BY DuplicateCount DESC, LowercasePath
            """
            
            Results = self.DatabaseManager.DatabaseService.ExecuteQuery(Query)
            
            DuplicateGroups = []
            for Row in Results:
                Group = {
                    'LowercasePath': Row['LowercasePath'],
                    'DuplicateCount': Row['DuplicateCount'],
                    'RootFolderIds': [int(x) for x in Row['RootFolderIds'].split(',')],
                    'AllPaths': Row['AllPaths'].split(','),
                    'ScanDates': Row['ScanDates'].split(',')
                }
                DuplicateGroups.append(Group)
                
            return DuplicateGroups
            
        except Exception as e:
            LoggingService.LogException("Error finding duplicate RootFolders", e, 
                                       'FindDuplicateRootFolders', 'ZDriveRootFolderMerger')
            return []
    
    def DetermineCanonicalRootFolder(self, DuplicateGroup: Dict[str, Any]) -> Optional[int]:
        """Determine which RootFolder to keep based on filesystem case."""
        try:
            # Get canonical path from filesystem
            CanonicalPath = self.GetCanonicalPathFromFilesystem(DuplicateGroup['LowercasePath'])
            
            # Find which entry matches the filesystem case
            MatchingIds = []
            for i, Path in enumerate(DuplicateGroup['AllPaths']):
                if Path == CanonicalPath:
                    MatchingIds.append(DuplicateGroup['RootFolderIds'][i])
            
            if MatchingIds:
                # Use the first match (or could use most recent)
                return MatchingIds[0]
            else:
                # If no exact match, use the most recently scanned
                MostRecentIndex = 0
                MostRecentDate = datetime.min
                
                for i, DateStr in enumerate(DuplicateGroup['ScanDates']):
                    try:
                        Date = datetime.fromisoformat(DateStr.replace('Z', '+00:00'))
                        if Date > MostRecentDate:
                            MostRecentDate = Date
                            MostRecentIndex = i
                    except:
                        continue
                
                return DuplicateGroup['RootFolderIds'][MostRecentIndex]
                
        except Exception as e:
            LoggingService.LogException("Error determining canonical RootFolder", e,
                                       'DetermineCanonicalRootFolder', 'ZDriveRootFolderMerger')
            return None
    
    def MergeDuplicateGroup(self, DuplicateGroup: Dict[str, Any]) -> bool:
        """Merge a group of duplicate RootFolders."""
        try:
            CanonicalId = self.DetermineCanonicalRootFolder(DuplicateGroup)
            if not CanonicalId:
                self.Errors.append(f"Could not determine canonical RootFolder for {DuplicateGroup['LowercasePath']}")
                return False
            
            # Get canonical path from filesystem
            CanonicalPath = self.GetCanonicalPathFromFilesystem(DuplicateGroup['LowercasePath'])
            
            # Update the canonical RootFolder with correct case
            UpdateQuery = """
                UPDATE RootFolders 
                SET RootFolder = ?, LastScannedDate = datetime('now', 'localtime')
                WHERE Id = ?
            """
            
            if not self.DryRun:
                self.DatabaseManager.DatabaseService.ExecuteNonQuery(UpdateQuery, (CanonicalPath, CanonicalId))
            
            # Update all MediaFiles to reference the canonical RootFolder
            MediaFileUpdateQuery = """
                UPDATE MediaFiles 
                SET FilePath = REPLACE(FilePath, ?, ?)
                WHERE LOWER(FilePath) LIKE LOWER(?) || '%'
                AND Id IN (
                    SELECT Id FROM MediaFiles 
                    WHERE LOWER(FilePath) LIKE LOWER(?) || '%'
                )
            """
            
            # Update MediaFiles for each duplicate path
            for i, OldPath in enumerate(DuplicateGroup['AllPaths']):
                if i < len(DuplicateGroup['RootFolderIds']) and DuplicateGroup['RootFolderIds'][i] != CanonicalId:
                    if not self.DryRun:
                        self.DatabaseManager.DatabaseService.ExecuteNonQuery(MediaFileUpdateQuery, 
                                                                             (OldPath, CanonicalPath, OldPath, OldPath))
            
            # Delete duplicate RootFolder entries
            DuplicateIds = [Id for Id in DuplicateGroup['RootFolderIds'] if Id != CanonicalId]
            if DuplicateIds:
                DeleteQuery = f"DELETE FROM RootFolders WHERE Id IN ({','.join('?' * len(DuplicateIds))})"
                
                if not self.DryRun:
                    self.DatabaseManager.DatabaseService.ExecuteNonQuery(DeleteQuery, DuplicateIds)
            
            # Log the changes
            Change = {
                'Action': 'Merged RootFolders',
                'CanonicalId': CanonicalId,
                'CanonicalPath': CanonicalPath,
                'DeletedIds': DuplicateIds,
                'OldPaths': DuplicateGroup['AllPaths']
            }
            self.Changes.append(Change)
            
            if self.Verbose:
                print(f"✓ Merged {DuplicateGroup['DuplicateCount']} RootFolders for {CanonicalPath}")
                print(f"  Kept ID {CanonicalId}, deleted IDs {DuplicateIds}")
            
            return True
            
        except Exception as e:
            LoggingService.LogException("Error merging duplicate group", e,
                                       'MergeDuplicateGroup', 'ZDriveRootFolderMerger')
            self.Errors.append(f"Failed to merge group for {DuplicateGroup['LowercasePath']}: {str(e)}")
            return False
    
    def Run(self) -> Dict[str, Any]:
        """Run the merge process."""
        try:
            print("🔍 Finding duplicate Z: drive RootFolders...")
            DuplicateGroups = self.FindDuplicateRootFolders()
            
            if not DuplicateGroups:
                print("✅ No duplicate RootFolders found on Z: drive")
                return {'Success': True, 'Changes': 0, 'Errors': 0}
            
            print(f"📊 Found {len(DuplicateGroups)} duplicate groups")
            
            if self.DryRun:
                print("🔍 DRY RUN - No changes will be made")
            
            SuccessCount = 0
            for Group in DuplicateGroups:
                if self.Verbose:
                    print(f"\n📁 Processing: {Group['LowercasePath']} ({Group['DuplicateCount']} duplicates)")
                    print(f"   IDs: {Group['RootFolderIds']}")
                    print(f"   Paths: {Group['AllPaths']}")
                
                if self.MergeDuplicateGroup(Group):
                    SuccessCount += 1
            
            Result = {
                'Success': True,
                'TotalGroups': len(DuplicateGroups),
                'SuccessfulMerges': SuccessCount,
                'Changes': self.Changes,
                'Errors': self.Errors
            }
            
            print(f"\n📈 Results:")
            print(f"   Groups processed: {len(DuplicateGroups)}")
            print(f"   Successful merges: {SuccessCount}")
            print(f"   Errors: {len(self.Errors)}")
            
            if self.Errors:
                print(f"\n❌ Errors:")
                for Error in self.Errors:
                    print(f"   {Error}")
            
            return Result
            
        except Exception as e:
            LoggingService.LogException("Error in merge process", e, 'Run', 'ZDriveRootFolderMerger')
            return {'Success': False, 'Error': str(e)}


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(description='Merge Z: drive duplicate RootFolders')
    parser.add_argument('--dry-run', action='store_true', help='Preview changes without making them')
    parser.add_argument('--verbose', action='store_true', help='Show detailed logging')
    
    args = parser.parse_args()
    
    print("🚀 Z: Drive RootFolder Duplicate Merger")
    print("=" * 50)
    
    if args.dry_run:
        print("🔍 Running in DRY RUN mode - no changes will be made")
    
    Merger = ZDriveRootFolderMerger(DryRun=args.dry_run, Verbose=args.verbose)
    Result = Merger.Run()
    
    if Result['Success']:
        print("\n✅ Merge process completed successfully")
        sys.exit(0)
    else:
        print(f"\n❌ Merge process failed: {Result.get('Error', 'Unknown error')}")
        sys.exit(1)


if __name__ == "__main__":
    main()
