#!/usr/bin/env python3
"""
Fix UNC Paths Script

This script converts UNC paths back to drive letters in the database.
It finds paths that start with \\ and converts them to the appropriate drive letter.

Usage:
    py Scripts/FixUNCPaths.py [--dry-run] [--verbose]
"""

import os
import sys
import argparse
import re

# Add project root to path
ProjectRoot = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ProjectRoot)

from Repositories.DatabaseManager import DatabaseManager
from Services.LoggingService import LoggingService


class UNCPathFixer:
    """Fixes UNC paths by converting them back to drive letters."""
    
    def __init__(self, DryRun: bool = False, Verbose: bool = False):
        self.DryRun = DryRun
        self.Verbose = Verbose
        self.DatabaseManager = DatabaseManager()
        self.Changes = []
        self.Errors = []
        
        # Common UNC to drive letter mappings
        self.UNCMappings = {
            r'\\\\allen\\xxx\\': 'Z:\\',
            r'\\\\allen\\': 'Z:\\',
            # Add more mappings as needed
        }
    
    def ConvertUNCPathToDrive(self, UNCPath: str) -> str:
        """Convert UNC path to drive letter path."""
        try:
            for unc_pattern, drive_letter in self.UNCMappings.items():
                if re.match(unc_pattern.replace('\\', '\\\\'), UNCPath, re.IGNORECASE):
                    # Replace the UNC prefix with drive letter
                    converted_path = re.sub(unc_pattern.replace('\\', '\\\\'), drive_letter, UNCPath, flags=re.IGNORECASE)
                    return converted_path
            
            # If no mapping found, return original
            return UNCPath
            
        except Exception as e:
            LoggingService.LogException("Error converting UNC path", e, 'ConvertUNCPathToDrive', 'UNCPathFixer')
            return UNCPath
    
    def FixRootFolders(self) -> int:
        """Fix UNC paths in RootFolders table."""
        try:
            # Find RootFolders with UNC paths
            Query = "SELECT Id, RootFolder FROM RootFolders WHERE RootFolder LIKE '\\\\%'"
            Results = self.DatabaseManager.DatabaseService.ExecuteQuery(Query)
            
            FixedCount = 0
            for Row in Results:
                RootFolderId = Row['Id']
                OriginalPath = Row['RootFolder']
                ConvertedPath = self.ConvertUNCPathToDrive(OriginalPath)
                
                if ConvertedPath != OriginalPath:
                    if not self.DryRun:
                        UpdateQuery = "UPDATE RootFolders SET RootFolder = ? WHERE Id = ?"
                        self.DatabaseManager.DatabaseService.ExecuteNonQuery(UpdateQuery, (ConvertedPath, RootFolderId))
                    
                    self.Changes.append({
                        'Table': 'RootFolders',
                        'Id': RootFolderId,
                        'OriginalPath': OriginalPath,
                        'ConvertedPath': ConvertedPath
                    })
                    FixedCount += 1
                    
                    if self.Verbose:
                        print(f"✓ Fixed RootFolder ID {RootFolderId}: {OriginalPath} → {ConvertedPath}")
            
            return FixedCount
            
        except Exception as e:
            LoggingService.LogException("Error fixing RootFolders", e, 'FixRootFolders', 'UNCPathFixer')
            self.Errors.append(f"Failed to fix RootFolders: {str(e)}")
            return 0
    
    def FixMediaFiles(self) -> int:
        """Fix UNC paths in MediaFiles table."""
        try:
            # Find MediaFiles with UNC paths
            Query = "SELECT Id, FilePath FROM MediaFiles WHERE FilePath LIKE '\\\\%'"
            Results = self.DatabaseManager.DatabaseService.ExecuteQuery(Query)
            
            FixedCount = 0
            for Row in Results:
                MediaFileId = Row['Id']
                OriginalPath = Row['FilePath']
                ConvertedPath = self.ConvertUNCPathToDrive(OriginalPath)
                
                if ConvertedPath != OriginalPath:
                    if not self.DryRun:
                        UpdateQuery = "UPDATE MediaFiles SET FilePath = ? WHERE Id = ?"
                        self.DatabaseManager.DatabaseService.ExecuteNonQuery(UpdateQuery, (ConvertedPath, MediaFileId))
                    
                    self.Changes.append({
                        'Table': 'MediaFiles',
                        'Id': MediaFileId,
                        'OriginalPath': OriginalPath,
                        'ConvertedPath': ConvertedPath
                    })
                    FixedCount += 1
                    
                    if self.Verbose:
                        print(f"✓ Fixed MediaFile ID {MediaFileId}: {OriginalPath} → {ConvertedPath}")
            
            return FixedCount
            
        except Exception as e:
            LoggingService.LogException("Error fixing MediaFiles", e, 'FixMediaFiles', 'UNCPathFixer')
            self.Errors.append(f"Failed to fix MediaFiles: {str(e)}")
            return 0
    
    def FixTemporaryFilePaths(self) -> int:
        """Fix UNC paths in TemporaryFilePaths table."""
        try:
            # Find TemporaryFilePaths with UNC paths
            Query = "SELECT Id, OriginalPath, LocalSourcePath, LocalOutputPath FROM TemporaryFilePaths WHERE OriginalPath LIKE '\\\\%' OR LocalSourcePath LIKE '\\\\%' OR LocalOutputPath LIKE '\\\\%'"
            Results = self.DatabaseManager.DatabaseService.ExecuteQuery(Query)
            
            FixedCount = 0
            for Row in Results:
                TempPathId = Row['Id']
                OriginalPath = Row['OriginalPath']
                LocalSourcePath = Row['LocalSourcePath']
                LocalOutputPath = Row['LocalOutputPath']
                
                # Convert paths
                ConvertedOriginalPath = self.ConvertUNCPathToDrive(OriginalPath) if OriginalPath else OriginalPath
                ConvertedLocalSourcePath = self.ConvertUNCPathToDrive(LocalSourcePath) if LocalSourcePath else LocalSourcePath
                ConvertedLocalOutputPath = self.ConvertUNCPathToDrive(LocalOutputPath) if LocalOutputPath else LocalOutputPath
                
                if (ConvertedOriginalPath != OriginalPath or 
                    ConvertedLocalSourcePath != LocalSourcePath or 
                    ConvertedLocalOutputPath != LocalOutputPath):
                    
                    if not self.DryRun:
                        UpdateQuery = "UPDATE TemporaryFilePaths SET OriginalPath = ?, LocalSourcePath = ?, LocalOutputPath = ? WHERE Id = ?"
                        self.DatabaseManager.DatabaseService.ExecuteNonQuery(UpdateQuery, 
                                                                             (ConvertedOriginalPath, ConvertedLocalSourcePath, ConvertedLocalOutputPath, TempPathId))
                    
                    self.Changes.append({
                        'Table': 'TemporaryFilePaths',
                        'Id': TempPathId,
                        'OriginalPath': OriginalPath,
                        'ConvertedPath': ConvertedOriginalPath
                    })
                    FixedCount += 1
                    
                    if self.Verbose:
                        print(f"✓ Fixed TemporaryFilePath ID {TempPathId}: {OriginalPath} → {ConvertedOriginalPath}")
            
            return FixedCount
            
        except Exception as e:
            LoggingService.LogException("Error fixing TemporaryFilePaths", e, 'FixTemporaryFilePaths', 'UNCPathFixer')
            self.Errors.append(f"Failed to fix TemporaryFilePaths: {str(e)}")
            return 0
    
    def Run(self) -> dict:
        """Run the UNC path fixing process."""
        try:
            print("🔍 Finding and fixing UNC paths...")
            
            if self.DryRun:
                print("🔍 DRY RUN - No changes will be made")
            
            # Fix each table
            RootFolderCount = self.FixRootFolders()
            MediaFileCount = self.FixMediaFiles()
            TempPathCount = self.FixTemporaryFilePaths()
            
            TotalFixed = RootFolderCount + MediaFileCount + TempPathCount
            
            Result = {
                'Success': True,
                'TotalFixed': TotalFixed,
                'RootFoldersFixed': RootFolderCount,
                'MediaFilesFixed': MediaFileCount,
                'TemporaryFilePathsFixed': TempPathCount,
                'Changes': self.Changes,
                'Errors': self.Errors
            }
            
            print(f"\n📈 Results:")
            print(f"   RootFolders fixed: {RootFolderCount}")
            print(f"   MediaFiles fixed: {MediaFileCount}")
            print(f"   TemporaryFilePaths fixed: {TempPathCount}")
            print(f"   Total fixed: {TotalFixed}")
            print(f"   Errors: {len(self.Errors)}")
            
            if self.Errors:
                print(f"\n❌ Errors:")
                for Error in self.Errors:
                    print(f"   {Error}")
            
            return Result
            
        except Exception as e:
            LoggingService.LogException("Error in UNC path fixing process", e, 'Run', 'UNCPathFixer')
            return {'Success': False, 'Error': str(e)}


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(description='Fix UNC paths by converting them to drive letters')
    parser.add_argument('--dry-run', action='store_true', help='Preview changes without making them')
    parser.add_argument('--verbose', action='store_true', help='Show detailed logging')
    
    args = parser.parse_args()
    
    print("🚀 UNC Path Fixer")
    print("=" * 50)
    
    if args.dry_run:
        print("🔍 Running in DRY RUN mode - no changes will be made")
    
    Fixer = UNCPathFixer(DryRun=args.dry_run, Verbose=args.verbose)
    Result = Fixer.Run()
    
    if Result['Success']:
        print("\n✅ UNC path fixing process completed successfully")
        sys.exit(0)
    else:
        print(f"\n❌ UNC path fixing process failed: {Result.get('Error', 'Unknown error')}")
        sys.exit(1)


if __name__ == "__main__":
    main()
