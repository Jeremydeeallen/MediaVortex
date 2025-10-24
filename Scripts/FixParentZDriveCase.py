#!/usr/bin/env python3
"""
Fix Parent Z: Drive RootFolder Case Script

This script updates the parent Z:\videos path to use the correct
filesystem case Z:\Videos.

Usage:
    py Scripts/FixParentZDriveCase.py [--dry-run] [--verbose]
"""

import os
import sys
import argparse

# Add project root to path
ProjectRoot = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ProjectRoot)

from Repositories.DatabaseManager import DatabaseManager
from Services.LoggingService import LoggingService


class ParentZDriveCaseFixer:
    """Fixes the parent Z: drive RootFolder entry to match actual filesystem case."""
    
    def __init__(self, DryRun: bool = False, Verbose: bool = False):
        self.DryRun = DryRun
        self.Verbose = Verbose
        self.DatabaseManager = DatabaseManager()
        self.Changes = []
        self.Errors = []
    
    def FixParentPath(self) -> bool:
        """Fix the parent Z:\videos path to Z:\Videos."""
        try:
            if self.Verbose:
                print("🔧 Fixing parent path: Z:\\videos → Z:\\Videos")
            
            # Update RootFolder
            RootFolderQuery = "UPDATE RootFolders SET RootFolder = ? WHERE RootFolder = ?"
            if not self.DryRun:
                self.DatabaseManager.DatabaseService.ExecuteNonQuery(RootFolderQuery, ("Z:\\Videos", "Z:\\videos"))
            
            # Update MediaFiles that start with the old path
            MediaFileQuery = """
                UPDATE MediaFiles 
                SET FilePath = REPLACE(FilePath, ?, ?)
                WHERE FilePath LIKE ? || '%'
            """
            if not self.DryRun:
                self.DatabaseManager.DatabaseService.ExecuteNonQuery(MediaFileQuery, 
                                                                     ("Z:\\videos", "Z:\\Videos", "Z:\\videos"))
            
            # Log the change
            Change = {
                'Action': 'Fixed parent path case',
                'OldPath': 'Z:\\videos',
                'NewPath': 'Z:\\Videos'
            }
            self.Changes.append(Change)
            
            if self.Verbose:
                print("✓ Fixed parent path: Z:\\videos → Z:\\Videos")
            
            return True
            
        except Exception as e:
            LoggingService.LogException("Error fixing parent path", e,
                                       'FixParentPath', 'ParentZDriveCaseFixer')
            self.Errors.append(f"Failed to fix parent path: {str(e)}")
            return False
    
    def Run(self) -> dict:
        """Run the case fixing process."""
        try:
            print("🔍 Fixing parent Z: drive RootFolder case...")
            
            if self.DryRun:
                print("🔍 DRY RUN - No changes will be made")
            
            if self.FixParentPath():
                Result = {
                    'Success': True,
                    'Changes': len(self.Changes),
                    'Errors': len(self.Errors)
                }
                
                print(f"\n📈 Results:")
                print(f"   Changes made: {len(self.Changes)}")
                print(f"   Errors: {len(self.Errors)}")
                
                if self.Errors:
                    print(f"\n❌ Errors:")
                    for Error in self.Errors:
                        print(f"   {Error}")
                
                return Result
            else:
                return {'Success': False, 'Error': 'Failed to fix parent path'}
            
        except Exception as e:
            LoggingService.LogException("Error in case fixing process", e, 'Run', 'ParentZDriveCaseFixer')
            return {'Success': False, 'Error': str(e)}


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(description='Fix parent Z: drive RootFolder case')
    parser.add_argument('--dry-run', action='store_true', help='Preview changes without making them')
    parser.add_argument('--verbose', action='store_true', help='Show detailed logging')
    
    args = parser.parse_args()
    
    print("🚀 Parent Z: Drive RootFolder Case Fixer")
    print("=" * 50)
    
    if args.dry_run:
        print("🔍 Running in DRY RUN mode - no changes will be made")
    
    Fixer = ParentZDriveCaseFixer(DryRun=args.dry_run, Verbose=args.verbose)
    Result = Fixer.Run()
    
    if Result['Success']:
        print("\n✅ Case fixing process completed successfully")
        sys.exit(0)
    else:
        print(f"\n❌ Case fixing process failed: {Result.get('Error', 'Unknown error')}")
        sys.exit(1)


if __name__ == "__main__":
    main()
