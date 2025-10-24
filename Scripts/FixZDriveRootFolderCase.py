#!/usr/bin/env python3
"""
Fix Z: Drive RootFolder Case Script

This script updates the remaining Z: drive RootFolder entries to use the correct
filesystem case (e.g., Z:\Videos\Couple instead of z:\videos\couple).

Usage:
    py Scripts/FixZDriveRootFolderCase.py [--dry-run] [--verbose]
"""

import os
import sys
import argparse
from pathlib import Path
from typing import List, Dict, Any

# Add project root to path
ProjectRoot = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ProjectRoot)

from Repositories.DatabaseManager import DatabaseManager
from Services.LoggingService import LoggingService


class ZDriveRootFolderCaseFixer:
    """Fixes the case of Z: drive RootFolder entries to match filesystem."""
    
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
                                     'GetCanonicalPathFromFilesystem', 'ZDriveRootFolderCaseFixer')
            return Path
    
    def GetZDriveRootFolders(self) -> List[Dict[str, Any]]:
        """Get all Z: drive RootFolder entries."""
        try:
            Query = "SELECT Id, RootFolder FROM RootFolders WHERE LOWER(RootFolder) LIKE 'z:%' ORDER BY RootFolder"
            Results = self.DatabaseManager.DatabaseService.ExecuteQuery(Query)
            
            RootFolders = []
            for Row in Results:
                RootFolder = {
                    'Id': Row['Id'],
                    'RootFolder': Row['RootFolder']
                }
                RootFolders.append(RootFolder)
                
            return RootFolders
            
        except Exception as e:
            LoggingService.LogException("Error getting Z: drive RootFolders", e, 
                                       'GetZDriveRootFolders', 'ZDriveRootFolderCaseFixer')
            return []
    
    def FixRootFolderCase(self, RootFolder: Dict[str, Any]) -> bool:
        """Fix the case of a single RootFolder entry."""
        try:
            RootFolderId = RootFolder['Id']
            CurrentPath = RootFolder['RootFolder']
            
            # Get canonical path from filesystem
            CanonicalPath = self.GetCanonicalPathFromFilesystem(CurrentPath)
            
            if CanonicalPath == CurrentPath:
                if self.Verbose:
                    print(f"✓ Path already correct: {CurrentPath}")
                return True
            
            # Update the RootFolder with correct case
            UpdateQuery = "UPDATE RootFolders SET RootFolder = ? WHERE Id = ?"
            
            if not self.DryRun:
                self.DatabaseManager.DatabaseService.ExecuteNonQuery(UpdateQuery, (CanonicalPath, RootFolderId))
            
            # Update all MediaFiles to use the correct case
            MediaFileUpdateQuery = """
                UPDATE MediaFiles 
                SET FilePath = REPLACE(FilePath, ?, ?)
                WHERE LOWER(FilePath) LIKE LOWER(?) || '%'
            """
            
            if not self.DryRun:
                self.DatabaseManager.DatabaseService.ExecuteNonQuery(MediaFileUpdateQuery, 
                                                                         (CurrentPath, CanonicalPath, CurrentPath))
            
            # Log the change
            Change = {
                'Action': 'Fixed RootFolder case',
                'Id': RootFolderId,
                'OldPath': CurrentPath,
                'NewPath': CanonicalPath
            }
            self.Changes.append(Change)
            
            if self.Verbose:
                print(f"✓ Fixed case: {CurrentPath} → {CanonicalPath}")
            
            return True
            
        except Exception as e:
            LoggingService.LogException("Error fixing RootFolder case", e,
                                       'FixRootFolderCase', 'ZDriveRootFolderCaseFixer')
            self.Errors.append(f"Failed to fix case for {RootFolder['RootFolder']}: {str(e)}")
            return False
    
    def Run(self) -> Dict[str, Any]:
        """Run the case fixing process."""
        try:
            print("🔍 Getting Z: drive RootFolders...")
            RootFolders = self.GetZDriveRootFolders()
            
            if not RootFolders:
                print("✅ No Z: drive RootFolders found")
                return {'Success': True, 'Changes': 0, 'Errors': 0}
            
            print(f"📊 Found {len(RootFolders)} Z: drive RootFolders")
            
            if self.DryRun:
                print("🔍 DRY RUN - No changes will be made")
            
            SuccessCount = 0
            for RootFolder in RootFolders:
                if self.Verbose:
                    print(f"\n📁 Processing: {RootFolder['RootFolder']} (ID: {RootFolder['Id']})")
                
                if self.FixRootFolderCase(RootFolder):
                    SuccessCount += 1
            
            Result = {
                'Success': True,
                'TotalRootFolders': len(RootFolders),
                'SuccessfulFixes': SuccessCount,
                'Changes': self.Changes,
                'Errors': self.Errors
            }
            
            print(f"\n📈 Results:")
            print(f"   RootFolders processed: {len(RootFolders)}")
            print(f"   Successful fixes: {SuccessCount}")
            print(f"   Errors: {len(self.Errors)}")
            
            if self.Errors:
                print(f"\n❌ Errors:")
                for Error in self.Errors:
                    print(f"   {Error}")
            
            return Result
            
        except Exception as e:
            LoggingService.LogException("Error in case fixing process", e, 'Run', 'ZDriveRootFolderCaseFixer')
            return {'Success': False, 'Error': str(e)}


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(description='Fix Z: drive RootFolder case to match filesystem')
    parser.add_argument('--dry-run', action='store_true', help='Preview changes without making them')
    parser.add_argument('--verbose', action='store_true', help='Show detailed logging')
    
    args = parser.parse_args()
    
    print("🚀 Z: Drive RootFolder Case Fixer")
    print("=" * 50)
    
    if args.dry_run:
        print("🔍 Running in DRY RUN mode - no changes will be made")
    
    Fixer = ZDriveRootFolderCaseFixer(DryRun=args.dry_run, Verbose=args.verbose)
    Result = Fixer.Run()
    
    if Result['Success']:
        print("\n✅ Case fixing process completed successfully")
        sys.exit(0)
    else:
        print(f"\n❌ Case fixing process failed: {Result.get('Error', 'Unknown error')}")
        sys.exit(1)


if __name__ == "__main__":
    main()
