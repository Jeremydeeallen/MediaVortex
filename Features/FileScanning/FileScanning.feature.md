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
17. [BUG] Scan progress is queryable mid-run. The `ScanJobs` row for an in-flight scan updates `Progress`, `CurrentDirectory`, `ProcessedFiles`, `NewFiles`, `UpdatedFiles`, `DeletedFiles` at least every 5 seconds (or every 100 files, whichever comes first), AND the operator can distinguish each phase of the scan (path validation / walk / reconcile / per-file processing / metadata extraction) from the `ScanJobs` row alone. The `scanning-on-activity-page.feature.md` UI is the consumer; this criterion owns the producer side of the contract. Verifiable: trigger a scan, poll `SELECT Progress, CurrentDirectory, ProcessedFiles, Status FROM ScanJobs WHERE Id=<id>` at 5s intervals, observe the values advance and the phase indicator change. **Confirmed violated 2026-05-15 (cadence dimension):** I9-2024 scans on M:\ and T:\ over NFS (89ms/dir, 18ms/dir) ran for minutes with `ProcessedFiles=0`, `CurrentDirectory=NULL`, `LastUpdated=StartTime`. Operator cannot distinguish a hung scan from a running one without reading `EndTime`. Stuck-scan detection (15-min default) is the only safety net. **Confirmed violated 2026-05-15 (phase dimension):** scan #64925's file walk completed (`ProcessedFiles=45716` = all files done) but `Status` stayed `Running` for the entire metadata-extraction phase that followed. PerformScan folds `MediaProbeService.ProbeFilesNeedingMetadata` inside its return, so `StartScanning`'s `UpdateJobStatus(Completed)` only fires after the probe pass. The heartbeat keeps writing `Status='Running'` throughout. Operator cannot tell "still walking files" from "files done, now FFprobing" -- which matters because probe is a different bottleneck profile (FFprobe per file at 1-5s each) than walk. Fix the phase dimension by either (a) adding a `ScanJobs.Phase` column with values like `Walking | Reconciling | Processing | Probing | Completed`, or (b) splitting the probe pass out of `PerformScan` so `ScanJobs` flips to `Completed` when the file walk finishes and a separate `ProbeJobs` (or equivalent) row tracks the probe phase.
18. Scanner has no code without a backing criterion. Specifically: (a) `FindTranscodedFileMatch` and `IsValidTranscodeResolutionChange` are removed -- post-`FileReplacement` there is no `_transcoded/` subdirectory in the data flow, so the path is dead; (b) the eight "is a scan running?" methods on `FileScanningBusinessService` (`CheckForExistingRunningScan`, `IsScanRunning`, `IsScanRunningForRootFolder`, `GetRunningScanCount`, `CanStartNewScan`, `GetScanJobStatus`, `GetCurrentScanStatus`, `GetAllRunningScans`) are consolidated to one repository query (`Repository.GetRunningScans(RootFolderPath=None)`); (c) the `MaxConcurrentScans` lever is removed -- criterion 11 makes it dead concept; (d) `ScanDirectories` CRUD is reconciled -- the duplicate methods on `FileScanningRepository` are deleted, the business-service wrappers and controller now route through `SystemSettingsRepository` (criteria 9-10 use `RootFolders` exclusively for path management; `ScanDir%` keys are legacy SystemSettings entries). Plus stuck-scan detection: `StuckJobDetectionService.DetectAndCleanStuckScanJobs` flags scans whose `LastUpdated` is older than `StuckScanThresholdMin` or whose `WorkerName` heartbeat is stale, and flips them to `Status='Failed'` so the per-rootfolder claim guard releases. Verifiable: `FileScanningBusinessService.py` dropped from 1815 to 1546 LOC; symbols from (a)-(c) do not resolve anywhere; `Scripts/SQLScripts/QueryDatabase.py sql "UPDATE ScanJobs SET LastUpdated=NOW()-INTERVAL '20 minutes' WHERE Id=<running>"` followed by the next stuck-detection cycle leaves the row in `Status='Failed'`. **18e (folding `ContinuousScanService`/`DuplicateDetectionService` into the business service) was reconsidered and dropped from scope:** `ContinuousScanService` has independent threading state and `DuplicateDetectionService` is a script-only utility -- neither merge would shrink real LOC.

19. [BUG] The "Possibly Corrupt" count on the /Status page is clickable and navigates the operator to a view of the affected files (file path, size, failure count, last error). Today the count is a static number with no drill-down; the operator must know to visit /Scanning and open the Corrupt Files modal to see which files are flagged. Fixed means: clicking the count on /Status either opens a modal with the file list (reusing the existing `/api/FileScanning/MediaFiles/Corrupt` endpoint) or navigates to /Scanning with the modal auto-opened.

20. [BUG] **A worker whose canonical path state is broken (share mappings missing, drives unmapped, `PathTranslation` failing) is detected and reported before it attempts scanning.** Today a worker with `ScanEnabled=true` but broken path resolution (e.g. `WorkerShareMappings` rows missing, drives not mounted, `_ToLocalPath` returning an untranslated Windows path on Linux) silently starts scanning, produces `os.walk` errors or inserts wrong paths into MediaFiles, and the operator has no signal until they notice garbage in the DB. Fixed means: before `ContinuousScanService` begins a scan pass, the worker validates that every `RootFolders` path it intends to scan resolves to an accessible local directory via `_ToLocalPath` + `os.path.isdir`. RootFolders that fail resolution are skipped with a WARNING log and a `ScanJobs` row recording `Status='Failed', ErrorMessage='Path not accessible: <canonical> -> <resolved>'`. The `/Activity` or `/Scanning` page surfaces which workers have path-resolution failures. Related: `KNOWN-ISSUES.md` canonical path storage entry.

21. [BUG] **The operator can register and scan multiple drives/shares from any worker.** Today RootFolders are seeded under specific drive prefixes (T:\, M:\, Z:\) and a worker can only scan drives it has `WorkerShareMappings` rows for. Adding a new drive to scan requires: (a) manually inserting RootFolders rows with the correct canonical prefix, (b) adding `WorkerShareMappings` rows for every worker that can reach the new drive, and (c) restarting workers to pick up the new mappings. Fixed means: the `/settings` or `/Scanning` page lets the operator add a new RootFolder under any drive/share prefix, the system prompts for or auto-discovers which workers can access it, and `WorkerShareMappings` (or its `StorageRootResolutions` successor per `path-storage.feature.md`) is updated without requiring a worker restart. A worker whose share mappings are updated picks up the new drive on its next continuous-scan tick.

22. [BUG] **End-to-end smoke test: a single-file scan via the API on a real worker is non-destructive and non-duplicative.** Verifiable: pick one known file already in MediaFiles (record its `Id`, `FilePath`, `SizeMB`, `AssignedProfile`, `TranscodedByMediaVortex`). Trigger `POST /api/FileScanning/Scan/Start` with the file's parent RootFolder on a worker with `ScanEnabled=true`. After the scan completes: (a) `SELECT COUNT(*) FROM MediaFiles WHERE FilePath = <path>` returns exactly 1 (no duplicate created), (b) the row's `Id` is unchanged (not delete+reinsert), (c) `AssignedProfile`, `TranscodedByMediaVortex`, `IsCompliant`, `RecommendedMode` are unchanged (metadata preserved), (d) `ScanJobs` row shows `Status='Completed'` with `NewFiles=0` and `DeletedFiles=0` for this path, (e) no new orphaned `TranscodeAttempts` or `MediaFilesArchive` rows referencing a different `MediaFileId` for the same path. This test must pass on both a Windows worker (I9-2024) and a Linux worker (any larry-worker) to confirm path translation does not corrupt existing data.

23. [BUG] **Scan stat-checks the same DB rows three times and runs them single-threaded over NFS.** Confirmed against I9-2024 scan #64923 on 2026-05-15: T:\ scan walked 45,716 files in 10s (NFS perf is fine), then blocked 20+ minutes in `DetectMovedFiles` doing serial `os.path.exists` on all 47,970 DB rows; `CleanupMissingFiles` immediately afterward repeats the same 47,970 stats; `ProcessMediaFiles` (parallel x5) then stats each file a third time plus a DB lookup. For files declared missing, `FindMovedFile` walks every one of 587 RootFolders via `os.walk` per missing file (exponential cost). Memory is fine (~279 MB worker), wall-clock is 3-6x what NFS speed allows. Fixed means: existence-check work is parallelized with the same `ThreadPoolExecutor` pattern `ProcessMediaFiles` already uses; the `DetectMovedFiles` and `CleanupMissingFiles` passes are merged into a single per-row decision so each file is stat'd at most once per scan; `FindMovedFile` builds a single `{filename: [paths]}` index once per scan and looks up missing files in O(1) instead of `os.walk` per missing file. Verifiable: re-run a T:\ scan after the fix and observe wall-clock under 5 minutes for a no-change pass on ~50k rows. Complements criterion 12 (cap behavior) -- this owns the throughput dimension of the same code path.

24. [BUG] **`ScanJobs.NewFiles`, `UpdatedFiles`, `DeletedFiles` stay at zero for the whole scan even when rows are inserted, updated, or deleted.** Confirmed mid-scan on 2026-05-15: scan #64925 inserted MediaFiles rows (verified by querying recent IDs 622023-622032) but the heartbeat read `NewFiles=0, UpdatedFiles=0, DeletedFiles=0` throughout. Root cause: `FileScanResultModel` only tracks `TotalFilesFound / TotalFilesProcessed / TotalFilesSkipped / TotalFilesWithErrors`. There is no per-disposition counter (new vs updated vs deleted). `ProcessSingleMediaFile` increments `TotalFilesProcessed` for both inserts and updates uniformly; `ReconcileWithDisk` decides deletions but doesn't surface a delete count to ScanResults. The `UpdateJobStatus` writer only sets these columns when a `ScanResults` model is passed, and even then the model has no fields for them. Fixed means: add `NewFilesCount`, `UpdatedFilesCount`, `DeletedFilesCount` (or equivalent) to `FileScanResultModel`; have the relevant writers (`ProcessSingleMediaFile` insert branch, `ProcessSingleMediaFile` update branch, `ReconcileWithDisk` delete branch) increment them under the existing thread-safe lock; have `UpdateJobStatus` write them through. Verifiable: trigger a scan that creates a known number of new files, updates a known number, deletes a known number; observe the three counters in `ScanJobs` match. Owns the per-disposition slice of criterion 17's contract; criterion 17 itself owns the heartbeat-cadence dimension.

25. [BUG] **`FindFuzzyFileMatch` reloads all RootFolder MediaFiles from DB and regex-parses every row per new file (O(N x M)).** Confirmed against I9-2024 scan #64925 on 2026-05-15: ~22 new Graham Norton episodes were taking 3-5 seconds each. Per new file, `FindFuzzyFileMatch` calls `Repository.GetMediaFilesByRootFolderId(RootFolderId)` returning all ~45,000 T:\ rows, then iterates the full set calling `ExtractShowInfo` (regex parse) on every `DbFile.FileName`, then stats candidate paths over NFS. Across the 5-thread parallel pool, each new file triggers an independent 45k-row DB load + 45k regex-parse storm. For 22 new files that is 990,000 ops where 22 dict lookups would suffice. Same anti-pattern family as criterion 23 (per-file work that should be precomputed once per scan), but distinct code path -- `FindMovedFile` vs `FindFuzzyFileMatch`. Fixed means: build a `{(ShowName, Season, Episode): [DbFile, ...]}` index once in `PerformScan` from a single `GetMediaFilesByRootFolderId` call, pass it down through `ProcessMediaFiles` -> `ProcessSingleMediaFile` -> `FindFuzzyFileMatch`, look up in O(1). Preserves the existing `IsFuzzyMatch` + `os.path.exists` candidate-validation step. Same threading concerns as `ReconcileWithDisk`'s filename index -- read-only after build, safe for the parallel pool. Verifiable: trigger a scan that introduces N new files; observe per-new-file wall-clock under 100ms instead of seconds.

## Status

IN PROGRESS -- scanning vertical revival. Active work: criteria 20, 21, 11, 22 in
that order (path validation gates the rest; multi-drive workflow gates parallel
work; smoke test verifies the full vertical end-to-end). Criteria 1-10, 18 remain
COMPLETE. Criteria 12, 16, 19 stay [BUG] and are out of scope for this slice.
Criteria 13-15, 17 to verify against current implementation as part of criterion 22.

Criterion 17 promoted to [BUG] on 2026-05-15 -- producer-side progress writer
is silent during the walk; recorded separately in KNOWN-ISSUES.md.

Triggering context (2026-05-15):
- Zero workers have `ScanEnabled=true`; last scan was 2026-05-10 (5 days stale).
- All 59,127 `MediaFiles.FilePath` rows are Windows drive-letter style. Linux
  workers cannot scan without correct `WorkerShareMappings` translation, so any
  Linux scan attempt today would either fail validation (criterion 20) or
  insert path-translated duplicates (criterion 21 + `path-storage.feature.md`).
- `MediaFiles.FilePath` already has `idx_mediafiles_filepath_unique`, so
  duplicate prevention at the DB level is enforced. The remaining duplicate
  vector is cross-worker canonical-path divergence -- owned by `path-storage`,
  not this feature.
- 587 RootFolders rows (3 drive roots + 584 individual subfolders). Sprawl
  cleanup is recorded separately via /b -- not pulled into this slice.

### Progress

- [x] 1. Diagnostic baseline on I9-2024 (2026-05-15). Findings:
      (a) capability poller picked up ScanEnabled+Online flips within ~15s and
      called `ContinuousScanService.StartContinuousScanning` correctly;
      (b) criterion 20 back-end ALREADY implemented at
      `ContinuousScanService.py:319-328` using `os.path.exists`;
      (c) criterion 21 back-end ALREADY implemented at line 278
      (`_RefreshShareMappings`); (d) **criterion 17 violated** -- M:\ scan ran
      2m+ with `ProcessedFiles=0`, `CurrentDirectory=NULL`, `LastUpdated`
      never advanced from `StartTime`; (e) **criterion 20 hole**:
      `os.path.exists` returns True for slow/degraded mounts -- the scan
      proceeds and hangs inside `os.walk`. Drives on I9-2024 confirmed
      healthy (T:→brain 88ms/dir, M:→allen 5.7s/dir, Z:→allen 46ms);
      slow-progress is a real-time perf characteristic of `\\allen\` shares,
      not a missing mount. NFS client is installed on Windows but unused;
      Linux workers use NFS at `/mnt/*` while Windows uses SMB to the same
      shares. Reverted via `ScanEnabled=false` and aborted scan #64918.
- [x] 2. Criterion 20 back-end hardened (`ContinuousScanService.py:323-331`,
      2026-05-15). Replaces single `os.path.exists` with three explicit
      states: `not isdir`, `unreadable` (OSError on `os.scandir`), and
      `empty` (the local-FS-showing-through pattern from worker-lifecycle).
      Logic verified locally against four cases (missing / file-not-dir /
      empty / healthy). `_RecordPathValidationFailure` and the existing
      `Path not accessible:` ScanJobs row contract are unchanged; only the
      gate is stricter and the error message now names which sub-state
      failed. Deployment pending: I9-2024 WorkerService restart for local
      pickup; Linux workers need code-only redeploy when next scanned.
      UI surface for the failure (criterion 20 second sentence) deferred
      to step 4.
- [ ] 3. **Criterion 17 (progress writer) -- INSERTED 2026-05-15.** Producer
      side: lift `ProcessedFiles` increment to the `os.walk` yield (so it
      counts files visited, not just files written), and add a heartbeat
      that updates `ScanJobs.LastUpdated` + `CurrentDirectory` every N
      seconds (5s target) regardless of file count. Without this, no later
      step is verifiable -- a "successful" scan and a hung scan are
      indistinguishable. Tracked in `KNOWN-ISSUES.md` Open section. Fix
      lives in `Features/FileScanning/FileScanningBusinessService.py` (the
      walk implementation called from `ContinuousScanService._ExecuteScan`
      via `StartScanning`). Verifiable: trigger a scan, poll `SELECT
      LastUpdated, CurrentDirectory, ProcessedFiles FROM ScanJobs WHERE
      Id=<id>` every 5s, observe values advance well before `EndTime`.
- [x] 3.5. **Criterion 23 back-end fixed (2026-05-15).** Added
      `ReconcileWithDisk(MediaFiles, RootFolderId)` in
      `FileScanningBusinessService.py` -- single pass over the disk list
      already produced by `ScanDirectory`. Builds a lower-case path set
      and a `{basename: [paths]}` index, then iterates DB rows: in-set =
      skip; out-of-set with fuzzy basename match + `IsSameFile` = reassign
      in place (preserves Id, metadata, and StorageRootId/RelativePath);
      out-of-set with no candidate = delete. Replaces both
      `DetectMovedFiles` (legacy) and `CleanupMissingFiles` (legacy) in
      `ProcessMediaFilesWithMetadata`; legacy methods kept in source but
      unreferenced by the scan path -- candidates for /simplify removal
      after a burn-in. Move-detection cap (criterion 12) preserved.
      Verified locally against four cases (exists / moved / deleted /
      case-insensitive). Verifiable in production: re-run T:\ scan and
      observe wall-clock under 5 minutes for a no-change pass on ~50k
      rows. Deployment pending: I9-2024 + Larry + Wakko WorkerService
      restarts/redeploys for code pickup.

- [x] 3.6. **Criteria 24 + 25 fixed (2026-05-15).**
      24: Added `NewFilesCount`, `UpdatedFilesCount`, `DeletedFilesCount` to
      `FileScanResultModel`. Increment sites: `ProcessSingleMediaFile`
      insert branch (NewFiles), update branch (UpdatedFiles), fuzzy-match
      branch (UpdatedFiles); `ReconcileWithDisk` reassign branch
      (UpdatedFiles), delete branch (DeletedFiles). `UpdateJobStatus`
      extended to write the three columns when ScanResults is passed --
      heartbeat picks them up automatically with no further plumbing.
      Fixed the pre-existing carryover bug for free by resetting
      `self.ScanResults = FileScanResultModel()` at the top of `PerformScan`.
      25: New `_BuildShowEpisodeIndex(RootFolderId)` builds a
      `{(showname.lower(), Season, Episode): [DbFile, ...]}` dict via a
      single `GetMediaFilesByRootFolderId` call. `PerformScan` sets
      `self._ShowEpisodeIndex` before `ProcessMediaFiles` and clears it in
      a finally. `FindFuzzyFileMatch` uses the index when present (O(1)
      lookup + tight size check) and falls back to the legacy O(N) scan
      when called out-of-band. Index is read-only after build, safe for
      the parallel pool. Verifiable: per-new-file wall-clock drops from
      3-5 seconds to <100ms; ScanJobs.NewFiles/UpdatedFiles/DeletedFiles
      reflect actual disposition counts. Deployment pending: I9-2024
      WorkerService restart for code pickup; Linux workers also need
      redeploy when next used.

- [ ] 4. Criterion 21 (multi-drive registration without restart): add UI on
      `/settings` or `/Scanning` to register new RootFolder + associate with
      workers. Update `WorkerShareMappings` (or `StorageRootResolutions` per
      `path-storage`) without requiring worker restart. Worker picks up new
      mapping on next continuous-scan tick via `_RefreshShareMappings`.
- [ ] 5. Criterion 11 (parallel claim semantics): per-rootfolder claim guard
      already exists (`Repository.GetRunningScans`). Add `PreferredWorkerName`
      affinity filter to `ContinuousScanService._ScanLoop` so a backplane-
      attached worker can be pinned to a specific rootfolder. Verify two
      `ScanEnabled=true` workers do not double-scan the same rootfolder.
- [ ] 6. Criterion 22 (end-to-end smoke test): scripted test that runs a
      single-file scan via API on Windows worker (I9-2024) and on a Linux
      worker (e.g. larry-worker-1, after path-storage groundwork lets it scan
      safely). Asserts: row count 1, Id unchanged, AssignedProfile preserved,
      no orphaned MediaFilesArchive/TranscodeAttempts. Now meaningful because
      step 3 makes scan progress observable.
- [ ] 7. Verify criteria 13-15 still hold against current code (criterion 17
      verified by step 3; status audit on the rest, record any drift via /b).

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
