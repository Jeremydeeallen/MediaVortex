# File Organization Script - MediaVortex

This script automatically organizes media files based on search terms and their corresponding destination folders. It follows the MVVM pattern using MVVM architecture.

## Files

- `FileOrganizationScript.ps1` - Main PowerShell script
- `FileOrganizationConfig.json` - Configuration file
- `README.md` - This documentation

## Usage

### Basic Usage

```powershell
# Run with default configuration
.\FileOrganizationScript.ps1

# Dry run (preview what would be moved)
.\FileOrganizationScript.ps1 -DryRun

# Verbose output
.\FileOrganizationScript.ps1 -Verbose

# Skip empty folder cleanup
.\FileOrganizationScript.ps1 -CleanupEmptyFolders:$false
```

### Configuration

Edit `FileOrganizationConfig.json` to customize:

- **SearchTerms**: Dictionary of search terms and their destination folders
- **RootFolder**: Source folder to scan for files
- **CaseSensitive**: Whether search is case-sensitive
- **CreateDirectories**: Whether to create destination directories if they don't exist
- **MoveFiles**: Whether to actually move files (vs. just logging)
- **FileExtensions**: List of file extensions to process
- **ExcludeFolders**: Folders to exclude from processing

### Example Configuration

```json
{
  "SearchTerms": {
    "Backdoor": "Z:\\videos\\anal",
    "Documentary": "Z:\\videos\\documentaries",
    "Comedy": "Z:\\videos\\comedy"
  },
  "RootFolder": "Z:\\videos\\downloads",
  "CaseSensitive": false,
  "CreateDirectories": true,
  "MoveFiles": true
}
```

## Features

- **Automatic File Organization**: Moves files based on search terms in filenames
- **Duplicate Handling**: Automatically handles duplicate filenames by adding numbers
- **Directory Creation**: Creates destination directories if they don't exist
- **File Extension Filtering**: Only processes specified media file extensions
- **Exclude Folders**: Skips system and temporary folders
- **Empty Folder Cleanup**: Removes empty folders after file organization
- **Comprehensive Logging**: Logs all operations to console and file
- **Dry Run Mode**: Preview operations without actually moving files
- **UTF-8 Support**: Handles Unicode characters in filenames and paths

## Logging

The script creates a log file `FileOrganization.log` in the same directory with detailed information about:
- Files processed
- Files moved
- Files skipped
- Errors encountered
- Directory operations

## Exit Codes

- `0`: Success
- `1`: Error occurred

## Requirements

- PowerShell 5.1 or later
- Windows operating system
- Appropriate file system permissions for source and destination folders
