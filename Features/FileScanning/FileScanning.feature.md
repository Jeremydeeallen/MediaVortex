# File Scanning

## What It Does

Discovers media files in configured root directories, extracts metadata via FFprobe, and tracks file changes over time. Provides the file inventory that feeds every downstream feature (queue population, transcoding, quality testing).

## Success Criteria

1. Scanning recursively discovers all media files under each registered RootFolder and inserts them into MediaFiles.
2. Incremental scanning skips unchanged files by comparing LastModifiedDate, so re-scans do not re-process the entire library.
3. Files that fail FFprobe 3 or more times are skipped on subsequent scans (FFprobe failure limit).
4. Duplicate detection identifies files with the same canonical path and cleans up the duplicate, prioritizing transcode history over recency over metadata completeness.
5. Continuous background scanning runs at a configurable interval (SystemSettings) and can be enabled/disabled from the UI.
6. Unicode filenames are handled correctly (database encoding is UTF-8).
7. The /Scanning page shows scan progress, discovered file counts, and database statistics.
8. Manual scan can be triggered from the UI via POST /api/Scan/Start.
9. RootFolders can be added and removed from the /settings page.
10. Excluded directories (configured in SystemSettings) are skipped during scanning.

## Status

COMPLETE

## Scope

```
Features/FileScanning/**
```

## Files

| File | Role |
|------|------|
| Features/FileScanning/FileScanningController.py | Flask Blueprint -- scan endpoints |
| Features/FileScanning/FileScanningBusinessService.py | Scan logic, duplicate detection, incremental filtering |
| Features/FileScanning/FileScanningRepository.py | MediaFiles and RootFolders database queries |
| Templates/FileScanning.html | Scanning UI page |
