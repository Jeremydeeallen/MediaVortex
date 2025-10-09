#!/usr/bin/env python3
"""
Fix DateTime Settings: Replace CURRENT_TIMESTAMP with datetime('now', 'localtime')
This script fixes the UTC time issue by replacing all CURRENT_TIMESTAMP usage with local time.
"""

import sys
import os
import re

# Add the project root to the Python path
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, project_root)

from Services.LoggingService import LoggingService


def FixCurrentTimestampInFile(FilePath: str) -> int:
    """
    Replace CURRENT_TIMESTAMP with datetime('now', 'localtime') in a file.
    Returns the number of replacements made.
    """
    try:
        LoggingService.LogInfo(f"Processing file: {FilePath}", "FixCurrentTimestampInFile", "FixDateTimeSettings")
        
        # Read the file
        with open(FilePath, 'r', encoding='utf-8') as file:
            content = file.read()
        
        # Count occurrences before replacement
        original_count = content.count('CURRENT_TIMESTAMP')
        
        if original_count == 0:
            LoggingService.LogInfo(f"No CURRENT_TIMESTAMP found in {FilePath}", "FixCurrentTimestampInFile", "FixDateTimeSettings")
            return 0
        
        # Replace CURRENT_TIMESTAMP with datetime('now', 'localtime')
        # Use word boundaries to avoid partial replacements
        new_content = re.sub(r'\bCURRENT_TIMESTAMP\b', "datetime('now', 'localtime')", content)
        
        # Write the file back
        with open(FilePath, 'w', encoding='utf-8') as file:
            file.write(new_content)
        
        LoggingService.LogInfo(f"Replaced {original_count} occurrences of CURRENT_TIMESTAMP in {FilePath}", 
                              "FixCurrentTimestampInFile", "FixDateTimeSettings")
        return original_count
        
    except Exception as e:
        LoggingService.LogException(f"Error processing file {FilePath}", e, "FixCurrentTimestampInFile", "FixDateTimeSettings")
        return 0


def FindFilesWithCurrentTimestamp() -> list:
    """Find all Python files that contain CURRENT_TIMESTAMP."""
    files_with_timestamp = []
    
    # Directories to search
    search_dirs = [
        'Repositories',
        'Services', 
        'Models',
        'Controllers',
        'ViewModels',
        'Scripts',
        'TranscodeService',
        'SystemOrchestratorService',
        'MicroServiceQualityTest'
    ]
    
    for search_dir in search_dirs:
        if not os.path.exists(search_dir):
            continue
            
        for root, dirs, files in os.walk(search_dir):
            for file in files:
                if file.endswith('.py'):
                    file_path = os.path.join(root, file)
                    try:
                        with open(file_path, 'r', encoding='utf-8') as f:
                            content = f.read()
                            if 'CURRENT_TIMESTAMP' in content:
                                files_with_timestamp.append(file_path)
                    except Exception as e:
                        LoggingService.LogWarning(f"Could not read file {file_path}: {e}", 
                                                "FindFilesWithCurrentTimestamp", "FixDateTimeSettings")
    
    return files_with_timestamp


def FixDateTimeSettings():
    """
    Main function to fix datetime settings across the entire codebase.
    Replaces all CURRENT_TIMESTAMP with datetime('now', 'localtime').
    """
    try:
        LoggingService.LogInfo("Starting datetime settings fix", "FixDateTimeSettings", "FixDateTimeSettings")
        
        # Find all files with CURRENT_TIMESTAMP
        files_to_fix = FindFilesWithCurrentTimestamp()
        
        if not files_to_fix:
            print("✅ No files found with CURRENT_TIMESTAMP")
            return True
        
        print(f"Found {len(files_to_fix)} files with CURRENT_TIMESTAMP:")
        for file_path in files_to_fix:
            print(f"  - {file_path}")
        
        print("\nFixing datetime settings...")
        
        total_replacements = 0
        for file_path in files_to_fix:
            replacements = FixCurrentTimestampInFile(file_path)
            total_replacements += replacements
            if replacements > 0:
                print(f"  ✅ Fixed {replacements} occurrences in {file_path}")
        
        print(f"\n✅ Total replacements made: {total_replacements}")
        print("\nDateTime settings have been fixed!")
        print("All CURRENT_TIMESTAMP usage has been replaced with datetime('now', 'localtime')")
        print("This ensures local time is stored in the database instead of UTC time.")
        
        return True
        
    except Exception as e:
        LoggingService.LogException("Error fixing datetime settings", e, "FixDateTimeSettings", "FixDateTimeSettings")
        print(f"❌ Error fixing datetime settings: {e}")
        return False


def main():
    """Main entry point for the datetime fix script."""
    print("=== DateTime Settings Fix ===")
    print("Replacing CURRENT_TIMESTAMP with datetime('now', 'localtime')")
    print("This fixes the UTC time issue in the database.")
    print()
    
    success = FixDateTimeSettings()
    
    if success:
        print()
        print("✅ DateTime settings fix completed successfully!")
        print()
        print("Changes made:")
        print("  - All CURRENT_TIMESTAMP replaced with datetime('now', 'localtime')")
        print("  - Database will now store local time instead of UTC time")
        print("  - Existing data will continue to work (UTC timestamps will be displayed as-is)")
        print("  - New data will be stored in local time")
        print()
        print("Next steps:")
        print("  1. Test the application to ensure datetime handling works correctly")
        print("  2. Consider running a data migration script if you want to convert existing UTC data")
    else:
        print()
        print("❌ DateTime settings fix failed!")
        sys.exit(1)


if __name__ == "__main__":
    main()
