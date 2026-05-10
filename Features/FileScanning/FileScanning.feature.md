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
11. [BUG] Scan work is claimed by the worker with the fastest path to storage. When multiple workers have `ScanEnabled=true`, exactly one runs each rootfolder scan on each interval (no duplicate concurrent scans). Operator can express affinity (e.g. larry-worker-1 scans `T:\Shows`) so a backplane-attached worker handles the work instead of an SMB-over-LAN host. Today `ContinuousScanService` iterates every RootFolder on every ScanEnabled worker independently -- two workers can scan the same rootfolder at the same time, and there is no preference for the host with the fastest storage access.
12. [BUG] Move-detection runs against libraries of any size. The 10,000-file ceiling in `DetectMovedFiles` (`Features/FileScanning/FileScanningBusinessService.py:1488`) silently disables rename/move tracking for libraries larger than that, so renamed files become delete + new-create rather than carrying their MediaFiles metadata (probe data, AssignedProfile, IsCompliant, RecommendedMode, TranscodedByMediaVortex). The "performance optimization" saves zero time because `CleanupMissingFiles` immediately afterward walks the same row set with the same `os.path.exists` check and is not capped. Either raise the cap to a SystemSetting (default ~100k) or fold both passes into a single per-row check so renamed files reassign and only truly-missing rows delete.
13. Rename / re-download preserves metadata. When a file disappears at one path and another file with the same parsed show + season + episode and size within +/-10% appears in the same RootFolder, the existing `MediaFiles` row is updated in place (`FilePath`, `FileName`, `SizeMB`, `LastModifiedDate`) instead of being deleted and reinserted. Preserves `AssignedProfile`, `IsCompliant`, `RecommendedMode`, `TranscodedByMediaVortex`, `FFprobeFailureCount`, and any `MediaFilesArchive` / `TranscodeAttempts` rows that reference `MediaFileId`. Verifiable: rename a file outside MediaVortex (or replace it with a different release-group cut), run a scan, the row keeps its original `Id` and the four cached fields are intact. Implementation lives in `FindFuzzyFileMatch` / `IsFuzzyMatch`.
14. In-place modification re-probes. If a file at the same `FilePath` has a different `SizeMB` or `LastModifiedDate` than the DB row, the row is re-probed and metadata refreshed; identity (`Id`) is preserved. Covers re-download to the same path. Verifiable: replace a file at the same path, run a scan, observe same `Id` and updated `Resolution` / `Codec` / `SizeMB` / `LastModifiedDate`. Existing `HasFileChanged` already drives this; the criterion just makes it observable.
15. Genuine deletion deletes only the `MediaFiles` row. When `DetectMovedFiles` and `FindFuzzyFileMatch` both fail to find a replacement and the file is missing on disk, `CleanupMissingFiles` removes the `MediaFiles` row but related `TranscodeAttempts` and `MediaFilesArchive` rows persist for audit. Verifiable: delete a file outside MediaVortex, run a scan, row is removed, but `SELECT * FROM MediaFilesArchive WHERE OriginalMediaFileId = <id>` and `SELECT * FROM TranscodeAttempts WHERE MediaFileId = <id>` still return the historical rows.
16. [BUG] RootFolder removal is non-destructive to history. Today `DatabaseManager.DeleteRootFolder` hard-deletes every `MediaFiles` row whose `FilePath` LIKE-matches the rootfolder prefix in a single `DELETE FROM MediaFiles WHERE LOWER(FilePath) LIKE ...` -- no audit trail, no soft-delete, and any `TranscodeAttempts` / `MediaFilesArchive` rows that referenced those `MediaFileId` values become orphaned (no FK cascade). Operator who removes a rootfolder by mistake cannot recover. Decide the contract: confirm-and-delete (current behavior, but require a typed-confirmation token), soft-delete (set `RootFolders.IsActive=false`, leave `MediaFiles` rows in place but stop scanning them), or refuse-if-non-empty (force the operator to clear the folder first). Until decided, the destructive single-call delete is a sharp edge.
17. Scan progress is queryable mid-run. The `ScanJobs` row for an in-flight scan updates `Progress`, `CurrentDirectory`, `ProcessedFiles`, `NewFiles`, `UpdatedFiles`, `DeletedFiles` at least every 5 seconds (or every 100 files, whichever comes first). The `scanning-on-activity-page.feature.md` UI is the consumer; this criterion owns the producer side of the contract. Verifiable: trigger a scan, poll `SELECT Progress, CurrentDirectory, ProcessedFiles FROM ScanJobs WHERE Id=<id>` at 5s intervals, observe the values advance.
18. Scanner has no code without a backing criterion. Specifically: (a) `FindTranscodedFileMatch` and `IsValidTranscodeResolutionChange` are removed -- post-`FileReplacement` there is no `_transcoded/` subdirectory in the data flow, so the path is dead; (b) the eight "is a scan running?" methods on `FileScanningBusinessService` (`CheckForExistingRunningScan`, `IsScanRunning`, `IsScanRunningForRootFolder`, `GetRunningScanCount`, `CanStartNewScan`, `GetScanJobStatus`, `GetCurrentScanStatus`, `GetAllRunningScans`) are consolidated to one repository query (`Repository.GetRunningScans(RootFolderPath=None)`); (c) the `MaxConcurrentScans` lever is removed -- criterion 11 makes it dead concept; (d) `ScanDirectories` CRUD is reconciled -- the duplicate methods on `FileScanningRepository` are deleted, the business-service wrappers and controller now route through `SystemSettingsRepository` (criteria 9-10 use `RootFolders` exclusively for path management; `ScanDir%` keys are legacy SystemSettings entries). Plus stuck-scan detection: `StuckJobDetectionService.DetectAndCleanStuckScanJobs` flags scans whose `LastUpdated` is older than `StuckScanThresholdMin` or whose `WorkerName` heartbeat is stale, and flips them to `Status='Failed'` so the per-rootfolder claim guard releases. Verifiable: `FileScanningBusinessService.py` dropped from 1815 to 1546 LOC; symbols from (a)-(c) do not resolve anywhere; `Scripts/SQLScripts/QueryDatabase.py sql "UPDATE ScanJobs SET LastUpdated=NOW()-INTERVAL '20 minutes' WHERE Id=<running>"` followed by the next stuck-detection cycle leaves the row in `Status='Failed'`. **18e (folding `ContinuousScanService`/`DuplicateDetectionService` into the business service) was reconsidered and dropped from scope:** `ContinuousScanService` has independent threading state and `DuplicateDetectionService` is a script-only utility -- neither merge would shrink real LOC.

## Status

COMPLETE (criteria 1-10, 18) / [BUG] criteria 11, 12, 16 open / criteria 13-15, 17 to verify against current implementation

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
