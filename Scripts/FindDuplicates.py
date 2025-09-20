#!/usr/bin/env python3
"""
Script to find and optionally clean up duplicate media files.
This script demonstrates how to use the DuplicateDetectionService.
"""

import sys
from pathlib import Path

# Add the parent directory to the path so we can import our modules
sys.path.append(str(Path(__file__).parent.parent))

from Services.DuplicateDetectionService import DuplicateDetectionService
from Repositories.DatabaseManager import DatabaseManager
from Services.LoggingService import LoggingService

def main():
    """Main function for duplicate detection."""
    try:
        print("MediaVortex Duplicate File Detection")
        print("=" * 40)
        
        # Initialize services
        DatabaseManagerInstance = DatabaseManager()
        DuplicateService = DuplicateDetectionService(DatabaseManagerInstance)
        
        # Get all root folders
        RootFolders = DatabaseManagerInstance.GetAllRootFolders()
        
        if not RootFolders:
            print("No root folders found in database.")
            print("Please run a file scan first to populate the database.")
            return
        
        print(f"Found {len(RootFolders)} root folders:")
        for i, folder in enumerate(RootFolders, 1):
            print(f"  {i}. {folder.RootFolder}")
        
        # Let user select a root folder
        try:
            Choice = input(f"\nSelect root folder (1-{len(RootFolders)}) or 'all' for all folders: ").strip()
            
            if Choice.lower() == 'all':
                SelectedFolders = RootFolders
            else:
                FolderIndex = int(Choice) - 1
                if 0 <= FolderIndex < len(RootFolders):
                    SelectedFolders = [RootFolders[FolderIndex]]
                else:
                    print("Invalid selection.")
                    return
        except ValueError:
            print("Invalid input.")
            return
        
        # Process each selected folder
        TotalDuplicateFiles = 0
        TotalWastedSpace = 0
        
        for RootFolder in SelectedFolders:
            print(f"\nAnalyzing: {RootFolder.RootFolder}")
            print("-" * 50)
            
            # Generate duplicate report
            Report = DuplicateService.GetDuplicateReport(RootFolder.Id)
            
            if not Report['Success']:
                print(f"Error: {Report['Message']}")
                continue
            
            if Report['TotalDuplicateFiles'] == 0:
                print("No duplicate files found.")
                continue
            
            print(f"Found {Report['TotalDuplicateFiles']} duplicate files")
            print(f"Wasted space: {Report['TotalWastedSpaceGB']:.2f} GB")
            print(f"Duplicate groups: {len(Report['DuplicateGroups'])}")
            
            # Show details for each group
            for i, Group in enumerate(Report['DuplicateGroups'], 1):
                print(f"\nGroup {i}: {Group['Count']} files, {Group['WastedSpaceMB']:.2f} MB wasted")
                print(f"  Best file: {Path(Group['BestFile']).name}")
                for FileToDelete in Group['FilesToDelete']:
                    print(f"  Duplicate: {Path(FileToDelete).name}")
            
            TotalDuplicateFiles += Report['TotalDuplicateFiles']
            TotalWastedSpace += Report['TotalWastedSpace']
            
            # Ask if user wants to clean up this folder
            if Report['TotalDuplicateFiles'] > 0:
                Cleanup = input(f"\nClean up duplicates in {RootFolder.RootFolder}? (y/N): ").strip().lower()
                if Cleanup == 'y':
                    print("Cleaning up duplicates...")
                    Result = DuplicateService.CleanupDuplicateMediaFiles(RootFolder.Id, KeepBestQuality=True)
                    if Result['Success']:
                        print(f"Cleaned up {Result['DeletedCount']} duplicate files from {Result['ProcessedGroups']} groups")
                    else:
                        print(f"Error: {Result['Message']}")
        
        # Summary
        if len(SelectedFolders) > 1:
            print(f"\nSummary:")
            print(f"Total duplicate files found: {TotalDuplicateFiles}")
            print(f"Total wasted space: {TotalWastedSpace / (1024**3):.2f} GB")
        
        print("\nDuplicate detection completed.")
        
    except KeyboardInterrupt:
        print("\nOperation cancelled by user.")
    except Exception as e:
        print(f"Error: {str(e)}")
        LoggingService.LogException("Error in duplicate detection script", e, 'main', 'FindDuplicates')

if __name__ == "__main__":
    main()
