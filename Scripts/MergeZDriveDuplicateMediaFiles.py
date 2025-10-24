#!/usr/bin/env python3
"""
Merge Z: Drive Duplicate MediaFiles Script

This script merges duplicate MediaFile entries that were created due to 
RootFolder case sensitivity issues. It prioritizes transcoded files and
archives non-kept versions for learning purposes.

Usage:
    py Scripts/MergeZDriveDuplicateMediaFiles.py [--dry-run] [--verbose]

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


class ZDriveMediaFileMerger:
    """Merges duplicate MediaFile entries after RootFolders are cleaned."""
    
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
                                     'GetCanonicalPathFromFilesystem', 'ZDriveMediaFileMerger')
            return Path
    
    def FindDuplicateMediaFiles(self) -> List[Dict[str, Any]]:
        """Find duplicate MediaFiles using case-insensitive FilePath comparison."""
        try:
            # Query to find duplicates using case-insensitive comparison
            Query = """
                SELECT 
                    LOWER(FilePath) as LowercasePath,
                    COUNT(*) as DuplicateCount,
                    GROUP_CONCAT(Id) as MediaFileIds,
                    GROUP_CONCAT(FilePath) as AllPaths,
                    GROUP_CONCAT(TranscodedByMediaVortex) as TranscodedFlags,
                    GROUP_CONCAT(LastScannedDate) as ScanDates,
                    GROUP_CONCAT(SizeMB) as Sizes
                FROM MediaFiles 
                WHERE LOWER(FilePath) LIKE 'z:%'
                GROUP BY LOWER(FilePath)
                HAVING COUNT(*) > 1
                ORDER BY DuplicateCount DESC, LowercasePath
            """
            
            Results = self.DatabaseManager.DatabaseService.ExecuteQuery(Query)
            
            DuplicateGroups = []
            for Row in Results:
                Group = {
                    'LowercasePath': Row['LowercasePath'],
                    'DuplicateCount': Row['DuplicateCount'],
                    'MediaFileIds': [int(x) for x in Row['MediaFileIds'].split(',')],
                    'AllPaths': Row['AllPaths'].split(','),
                    'TranscodedFlags': [int(x) if x else 0 for x in Row['TranscodedFlags'].split(',')],
                    'ScanDates': Row['ScanDates'].split(','),
                    'Sizes': [float(x) if x else 0 for x in Row['Sizes'].split(',')]
                }
                DuplicateGroups.append(Group)
                
            return DuplicateGroups
            
        except Exception as e:
            LoggingService.LogException("Error finding duplicate MediaFiles", e, 
                                       'FindDuplicateMediaFiles', 'ZDriveMediaFileMerger')
            return []
    
    def DetermineCanonicalMediaFile(self, DuplicateGroup: Dict[str, Any]) -> Optional[int]:
        """Determine which MediaFile to keep based on priority rules."""
        try:
            # Priority 1: Keep transcoded files (TranscodedByMediaVortex = 1)
            TranscodedIndices = [i for i, flag in enumerate(DuplicateGroup['TranscodedFlags']) if flag == 1]
            
            if TranscodedIndices:
                # If multiple transcoded files, keep the most recent
                if len(TranscodedIndices) > 1:
                    MostRecentIndex = TranscodedIndices[0]
                    MostRecentDate = datetime.min
                    
                    for i in TranscodedIndices:
                        try:
                            Date = datetime.fromisoformat(DuplicateGroup['ScanDates'][i].replace('Z', '+00:00'))
                            if Date > MostRecentDate:
                                MostRecentDate = Date
                                MostRecentIndex = i
                        except:
                            continue
                    
                    return DuplicateGroup['MediaFileIds'][MostRecentIndex]
                else:
                    return DuplicateGroup['MediaFileIds'][TranscodedIndices[0]]
            
            # Priority 2: Keep most recently scanned if no transcoded versions
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
            
            return DuplicateGroup['MediaFileIds'][MostRecentIndex]
                
        except Exception as e:
            LoggingService.LogException("Error determining canonical MediaFile", e,
                                       'DetermineCanonicalMediaFile', 'ZDriveMediaFileMerger')
            return None
    
    def ArchiveMediaFile(self, MediaFileId: int) -> bool:
        """Archive a MediaFile to MediaFilesArchive for learning purposes."""
        try:
            # Get MediaFile details
            MediaFileQuery = "SELECT * FROM MediaFiles WHERE Id = ?"
            MediaFileResult = self.DatabaseManager.DatabaseService.ExecuteQuery(MediaFileQuery, (MediaFileId,))
            
            if not MediaFileResult:
                return False
            
            MediaFile = MediaFileResult[0]
            
            # Create archive entry
            ArchiveQuery = """
                INSERT INTO MediaFilesArchive (
                    OriginalMediaFileId, FilePath, FileName, SizeMB, VideoBitrateKbps,
                    AudioBitrateKbps, Resolution, Codec, DurationMinutes, FrameRate,
                    LastScannedDate, CompressionPotential, AssignedProfile,
                    FileModificationTime, ArchiveDate, ArchiveReason
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, datetime('now', 'localtime'), ?)
            """
            
            ArchiveReason = "Duplicate case sensitivity cleanup"
            ArchiveParams = (
                MediaFileId, MediaFile['FilePath'], MediaFile['FileName'], MediaFile['SizeMB'],
                MediaFile['VideoBitrateKbps'], MediaFile['AudioBitrateKbps'], MediaFile['Resolution'],
                MediaFile['Codec'], MediaFile['DurationMinutes'], MediaFile['FrameRate'],
                MediaFile['LastScannedDate'], MediaFile['CompressionPotential'], MediaFile['AssignedProfile'],
                MediaFile['FileModificationTime'], ArchiveReason
            )
            
            if not self.DryRun:
                self.DatabaseManager.DatabaseService.ExecuteNonQuery(ArchiveQuery, ArchiveParams)
            
            return True
            
        except Exception as e:
            LoggingService.LogException("Error archiving MediaFile", e,
                                       'ArchiveMediaFile', 'ZDriveMediaFileMerger')
            return False
    
    def UpdateReferencesToMediaFile(self, OldMediaFileId: int, NewMediaFileId: int) -> bool:
        """Update all references to point to the canonical MediaFile."""
        try:
            # Update TranscodeQueue
            QueueUpdateQuery = "UPDATE TranscodeQueue SET MediaFileId = ? WHERE MediaFileId = ?"
            if not self.DryRun:
                self.DatabaseManager.DatabaseService.ExecuteNonQuery(QueueUpdateQuery, (NewMediaFileId, OldMediaFileId))
            
            # Update TranscodeAttempts
            AttemptUpdateQuery = "UPDATE TranscodeAttempts SET MediaFileId = ? WHERE MediaFileId = ?"
            if not self.DryRun:
                self.DatabaseManager.DatabaseService.ExecuteNonQuery(AttemptUpdateQuery, (NewMediaFileId, OldMediaFileId))
            
            return True
            
        except Exception as e:
            LoggingService.LogException("Error updating references", e,
                                       'UpdateReferencesToMediaFile', 'ZDriveMediaFileMerger')
            return False
    
    def MergeDuplicateGroup(self, DuplicateGroup: Dict[str, Any]) -> bool:
        """Merge a group of duplicate MediaFiles."""
        try:
            CanonicalId = self.DetermineCanonicalMediaFile(DuplicateGroup)
            if not CanonicalId:
                self.Errors.append(f"Could not determine canonical MediaFile for {DuplicateGroup['LowercasePath']}")
                return False
            
            # Get canonical path from filesystem
            CanonicalPath = self.GetCanonicalPathFromFilesystem(DuplicateGroup['LowercasePath'])
            
            # Update the canonical MediaFile with correct case
            UpdateQuery = """
                UPDATE MediaFiles 
                SET FilePath = ?, LastScannedDate = datetime('now', 'localtime')
                WHERE Id = ?
            """
            
            if not self.DryRun:
                self.DatabaseManager.DatabaseService.ExecuteNonQuery(UpdateQuery, (CanonicalPath, CanonicalId))
            
            # Process duplicate MediaFiles
            DuplicateIds = [Id for Id in DuplicateGroup['MediaFileIds'] if Id != CanonicalId]
            ArchivedCount = 0
            
            for DuplicateId in DuplicateIds:
                # Archive the duplicate
                if self.ArchiveMediaFile(DuplicateId):
                    ArchivedCount += 1
                
                # Update references
                self.UpdateReferencesToMediaFile(DuplicateId, CanonicalId)
            
            # Delete duplicate MediaFile entries
            if DuplicateIds:
                DeleteQuery = f"DELETE FROM MediaFiles WHERE Id IN ({','.join('?' * len(DuplicateIds))})"
                
                if not self.DryRun:
                    self.DatabaseManager.DatabaseService.ExecuteNonQuery(DeleteQuery, DuplicateIds)
            
            # Log the changes
            Change = {
                'Action': 'Merged MediaFiles',
                'CanonicalId': CanonicalId,
                'CanonicalPath': CanonicalPath,
                'DeletedIds': DuplicateIds,
                'ArchivedCount': ArchivedCount,
                'OldPaths': DuplicateGroup['AllPaths']
            }
            self.Changes.append(Change)
            
            if self.Verbose:
                print(f"✓ Merged {DuplicateGroup['DuplicateCount']} MediaFiles for {CanonicalPath}")
                print(f"  Kept ID {CanonicalId}, deleted IDs {DuplicateIds}, archived {ArchivedCount}")
            
            return True
            
        except Exception as e:
            LoggingService.LogException("Error merging duplicate group", e,
                                       'MergeDuplicateGroup', 'ZDriveMediaFileMerger')
            self.Errors.append(f"Failed to merge group for {DuplicateGroup['LowercasePath']}: {str(e)}")
            return False
    
    def Run(self) -> Dict[str, Any]:
        """Run the merge process."""
        try:
            print("🔍 Finding duplicate Z: drive MediaFiles...")
            DuplicateGroups = self.FindDuplicateMediaFiles()
            
            if not DuplicateGroups:
                print("✅ No duplicate MediaFiles found on Z: drive")
                return {'Success': True, 'Changes': 0, 'Errors': 0}
            
            print(f"📊 Found {len(DuplicateGroups)} duplicate groups")
            
            if self.DryRun:
                print("🔍 DRY RUN - No changes will be made")
            
            SuccessCount = 0
            for Group in DuplicateGroups:
                if self.Verbose:
                    print(f"\n📁 Processing: {Group['LowercasePath']} ({Group['DuplicateCount']} duplicates)")
                    print(f"   IDs: {Group['MediaFileIds']}")
                    print(f"   Paths: {Group['AllPaths']}")
                    print(f"   Transcoded: {Group['TranscodedFlags']}")
                
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
            LoggingService.LogException("Error in merge process", e, 'Run', 'ZDriveMediaFileMerger')
            return {'Success': False, 'Error': str(e)}


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(description='Merge Z: drive duplicate MediaFiles')
    parser.add_argument('--dry-run', action='store_true', help='Preview changes without making them')
    parser.add_argument('--verbose', action='store_true', help='Show detailed logging')
    
    args = parser.parse_args()
    
    print("🚀 Z: Drive MediaFile Duplicate Merger")
    print("=" * 50)
    
    if args.dry_run:
        print("🔍 Running in DRY RUN mode - no changes will be made")
    
    Merger = ZDriveMediaFileMerger(DryRun=args.dry_run, Verbose=args.verbose)
    Result = Merger.Run()
    
    if Result['Success']:
        print("\n✅ Merge process completed successfully")
        sys.exit(0)
    else:
        print(f"\n❌ Merge process failed: {Result.get('Error', 'Unknown error')}")
        sys.exit(1)


if __name__ == "__main__":
    main()
