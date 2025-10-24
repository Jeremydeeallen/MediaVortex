#!/usr/bin/env python3
"""
Fix Specific Z: Drive RootFolder Case Script

This script updates specific Z: drive RootFolder entries to use the correct
filesystem case based on the actual folder structure.

Usage:
    py Scripts/FixSpecificZDriveCase.py [--dry-run] [--verbose]
"""

import os
import sys
import argparse

# Add project root to path
ProjectRoot = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ProjectRoot)

from Repositories.DatabaseManager import DatabaseManager
from Services.LoggingService import LoggingService


class SpecificZDriveCaseFixer:
    """Fixes specific Z: drive RootFolder entries to match actual filesystem case."""
    
    def __init__(self, DryRun: bool = False, Verbose: bool = False):
        self.DryRun = DryRun
        self.Verbose = Verbose
        self.DatabaseManager = DatabaseManager()
        self.Changes = []
        self.Errors = []
        
        # Define the correct mappings based on actual filesystem
        self.CaseMappings = {
            'z:\\videos\\anal': 'Z:\\Videos\\Anal',
            'z:\\videos\\couple': 'Z:\\Videos\\Couple', 
            'z:\\videos\\lesbian': 'Z:\\Videos\\Lesbian'
        }
    
    def FixSpecificCases(self) -> bool:
        """Fix the specific case issues we know about."""
        try:
            for LowercasePath, CorrectPath in self.CaseMappings.items():
                if self.Verbose:
                    print(f"🔧 Fixing: {LowercasePath} → {CorrectPath}")
                
                # Update RootFolder
                RootFolderQuery = "UPDATE RootFolders SET RootFolder = ? WHERE LOWER(RootFolder) = ?"
                if not self.DryRun:
                    self.DatabaseManager.DatabaseService.ExecuteNonQuery(RootFolderQuery, (CorrectPath, LowercasePath))
                
                # Update MediaFiles
                MediaFileQuery = """
                    UPDATE MediaFiles 
                    SET FilePath = REPLACE(FilePath, ?, ?)
                    WHERE LOWER(FilePath) LIKE LOWER(?) || '%'
                """
                if not self.DryRun:
                    self.DatabaseManager.DatabaseService.ExecuteNonQuery(MediaFileQuery, 
                                                                         (LowercasePath, CorrectPath, LowercasePath))
                
                # Log the change
                Change = {
                    'Action': 'Fixed specific case',
                    'OldPath': LowercasePath,
                    'NewPath': CorrectPath
                }
                self.Changes.append(Change)
                
                if self.Verbose:
                    print(f"✓ Fixed: {LowercasePath} → {CorrectPath}")
            
            return True
            
        except Exception as e:
            LoggingService.LogException("Error fixing specific cases", e,
                                       'FixSpecificCases', 'SpecificZDriveCaseFixer')
            self.Errors.append(f"Failed to fix specific cases: {str(e)}")
            return False
    
    def Run(self) -> dict:
        """Run the case fixing process."""
        try:
            print("🔍 Fixing specific Z: drive RootFolder case issues...")
            
            if self.DryRun:
                print("🔍 DRY RUN - No changes will be made")
            
            if self.FixSpecificCases():
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
                return {'Success': False, 'Error': 'Failed to fix specific cases'}
            
        except Exception as e:
            LoggingService.LogException("Error in case fixing process", e, 'Run', 'SpecificZDriveCaseFixer')
            return {'Success': False, 'Error': str(e)}


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(description='Fix specific Z: drive RootFolder case issues')
    parser.add_argument('--dry-run', action='store_true', help='Preview changes without making them')
    parser.add_argument('--verbose', action='store_true', help='Show detailed logging')
    
    args = parser.parse_args()
    
    print("🚀 Specific Z: Drive RootFolder Case Fixer")
    print("=" * 50)
    
    if args.dry_run:
        print("🔍 Running in DRY RUN mode - no changes will be made")
    
    Fixer = SpecificZDriveCaseFixer(DryRun=args.dry_run, Verbose=args.verbose)
    Result = Fixer.Run()
    
    if Result['Success']:
        print("\n✅ Case fixing process completed successfully")
        sys.exit(0)
    else:
        print(f"\n❌ Case fixing process failed: {Result.get('Error', 'Unknown error')}")
        sys.exit(1)


if __name__ == "__main__":
    main()
