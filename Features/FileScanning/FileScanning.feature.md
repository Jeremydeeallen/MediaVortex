# File Scanning

**Slug:** filescanning

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
17. Scan progress is queryable mid-run. The `ScanJobs` row for an in-flight scan updates `Progress`, `CurrentDirectory`, `ProcessedFiles`, `NewFiles`, `UpdatedFiles`, `DeletedFiles`, `Phase`, `FilesNeedingProbe`, `ProbedFiles`, `TopFiles` at least every 5 seconds (via the heartbeat in `FileScanningBusinessService._StartProgressHeartbeat`). The operator can distinguish each phase of the scan (`SizeSurvey` / `Walking` / `Reconciling` / `Probing` / `Completing`) from the `Phase` column alone. The /Activity Active Scans block is the consumer; this criterion owns the producer side of the contract. Closed by directives `.claude/directives/closed/2026-05-27-active-scan-visibility.md` and `2026-05-28-scan-largest-first.md`. Verifiable: trigger a scan, poll `SELECT Phase, Progress, ProcessedFiles FROM ScanJobs WHERE Id=<id>` at 5s intervals, observe the values advance and the phase change through all five states. **Confirmed violated 2026-05-15 (cadence dimension):** I9-2024 scans on M:\ and T:\ over NFS (89ms/dir, 18ms/dir) ran for minutes with `ProcessedFiles=0`, `CurrentDirectory=NULL`, `LastUpdated=StartTime`. Operator cannot distinguish a hung scan from a running one without reading `EndTime`. Stuck-scan detection (15-min default) is the only safety net. **Confirmed violated 2026-05-15 (phase dimension):** scan #64925's file walk completed (`ProcessedFiles=45716` = all files done) but `Status` stayed `Running` for the entire metadata-extraction phase that followed. PerformScan folds `MediaProbeService.ProbeFilesNeedingMetadata` inside its return, so `StartScanning`'s `UpdateJobStatus(Completed)` only fires after the probe pass. The heartbeat keeps writing `Status='Running'` throughout. Operator cannot tell "still walking files" from "files done, now FFprobing" -- which matters because probe is a different bottleneck profile (FFprobe per file at 1-5s each) than walk. Fix the phase dimension by either (a) adding a `ScanJobs.Phase` column with values like `Walking | Reconciling | Processing | Probing | Completed`, or (b) splitting the probe pass out of `PerformScan` so `ScanJobs` flips to `Completed` when the file walk finishes and a separate `ProbeJobs` (or equivalent) row tracks the probe phase.
18. Scanner has no code without a backing criterion. Specifically: (a) `FindTranscodedFileMatch` and `IsValidTranscodeResolutionChange` are removed -- post-`FileReplacement` there is no `_transcoded/` subdirectory in the data flow, so the path is dead; (b) the eight "is a scan running?" methods on `FileScanningBusinessService` (`CheckForExistingRunningScan`, `IsScanRunning`, `IsScanRunningForRootFolder`, `GetRunningScanCount`, `CanStartNewScan`, `GetScanJobStatus`, `GetCurrentScanStatus`, `GetAllRunningScans`) are consolidated to one repository query (`Repository.GetRunningScans(RootFolderPath=None)`); (c) the `MaxConcurrentScans` lever is removed -- criterion 11 makes it dead concept; (d) `ScanDirectories` CRUD is reconciled -- the duplicate methods on `FileScanningRepository` are deleted, the business-service wrappers and controller now route through `SystemSettingsRepository` (criteria 9-10 use `RootFolders` exclusively for path management; `ScanDir%` keys are legacy SystemSettings entries). Plus stuck-scan detection: `StuckJobDetectionService.DetectAndCleanStuckScanJobs` flags scans whose `LastUpdated` is older than `StuckScanThresholdMin` or whose `WorkerName` heartbeat is stale, and flips them to `Status='Failed'` so the per-rootfolder claim guard releases. Verifiable: `FileScanningBusinessService.py` dropped from 1815 to 1546 LOC; symbols from (a)-(c) do not resolve anywhere; `Scripts/SQLScripts/QueryDatabase.py sql "UPDATE ScanJobs SET LastUpdated=NOW()-INTERVAL '20 minutes' WHERE Id=<running>"` followed by the next stuck-detection cycle leaves the row in `Status='Failed'`. **18e (folding `ContinuousScanService`/`DuplicateDetectionService` into the business service) was reconsidered and dropped from scope:** `ContinuousScanService` has independent threading state and `DuplicateDetectionService` is a script-only utility -- neither merge would shrink real LOC.

19. [BUG] The "Possibly Corrupt" count on the /Status page is clickable and navigates the operator to a view of the affected files (file path, size, failure count, last error). Today the count is a static number with no drill-down; the operator must know to visit /Scanning and open the Corrupt Files modal to see which files are flagged. Fixed means: clicking the count on /Status either opens a modal with the file list (reusing the existing `/api/FileScanning/MediaFiles/Corrupt` endpoint) or navigates to /Scanning with the modal auto-opened.

20. [BUG] **A worker whose canonical path state is broken (share mappings missing, drives unmapped, `PathTranslation` failing) is detected and reported before it attempts scanning.** Today a worker with `ScanEnabled=true` but broken path resolution (e.g. `WorkerShareMappings` rows missing, drives not mounted, `_ToLocalPath` returning an untranslated Windows path on Linux) silently starts scanning, produces `os.walk` errors or inserts wrong paths into MediaFiles, and the operator has no signal until they notice garbage in the DB. Fixed means: before `ContinuousScanService` begins a scan pass, the worker validates that every `RootFolders` path it intends to scan resolves to an accessible local directory via `_ToLocalPath` + `os.path.isdir`. RootFolders that fail resolution are skipped with a WARNING log and a `ScanJobs` row recording `Status='Failed', ErrorMessage='Path not accessible: <canonical> -> <resolved>'`. The `/Activity` or `/Scanning` page surfaces which workers have path-resolution failures. Related: `memory/KNOWN-ISSUES.md` canonical path storage entry.

21. [BUG] **The operator can register and scan multiple drives/shares from any worker.** Today RootFolders are seeded under specific drive prefixes (T:\, M:\, Z:\) and a worker can only scan drives it has `WorkerShareMappings` rows for. Adding a new drive to scan requires: (a) manually inserting RootFolders rows with the correct canonical prefix, (b) adding `WorkerShareMappings` rows for every worker that can reach the new drive, and (c) restarting workers to pick up the new mappings. Fixed means: the `/settings` or `/Scanning` page lets the operator add a new RootFolder under any drive/share prefix, the system prompts for or auto-discovers which workers can access it, and `WorkerShareMappings` (or its `StorageRootResolutions` successor per `path-storage.feature.md`) is updated without requiring a worker restart. A worker whose share mappings are updated picks up the new drive on its next continuous-scan tick.

22. [BUG] **End-to-end smoke test: a single-file scan via the API on a real worker is non-destructive and non-duplicative.** Verifiable: pick one known file already in MediaFiles (record its `Id`, `FilePath`, `SizeMB`, `AssignedProfile`, `TranscodedByMediaVortex`). Trigger `POST /api/FileScanning/Scan/Start` with the file's parent RootFolder on a worker with `ScanEnabled=true`. After the scan completes: (a) `SELECT COUNT(*) FROM MediaFiles WHERE FilePath = <path>` returns exactly 1 (no duplicate created), (b) the row's `Id` is unchanged (not delete+reinsert), (c) `AssignedProfile`, `TranscodedByMediaVortex`, `IsCompliant`, `RecommendedMode` are unchanged (metadata preserved), (d) `ScanJobs` row shows `Status='Completed'` with `NewFiles=0` and `DeletedFiles=0` for this path, (e) no new orphaned `TranscodeAttempts` or `MediaFilesArchive` rows referencing a different `MediaFileId` for the same path. This test must pass on both a Windows worker (I9-2024) and a Linux worker (any larry-worker) to confirm path translation does not corrupt existing data.

23. [BUG] **Scan stat-checks the same DB rows three times and runs them single-threaded over NFS.** Confirmed against I9-2024 scan #64923 on 2026-05-15: T:\ scan walked 45,716 files in 10s (NFS perf is fine), then blocked 20+ minutes in `DetectMovedFiles` doing serial `os.path.exists` on all 47,970 DB rows; `CleanupMissingFiles` immediately afterward repeats the same 47,970 stats; `ProcessMediaFiles` (parallel x5) then stats each file a third time plus a DB lookup. For files declared missing, `FindMovedFile` walks every one of 587 RootFolders via `os.walk` per missing file (exponential cost). Memory is fine (~279 MB worker), wall-clock is 3-6x what NFS speed allows. Fixed means: existence-check work is parallelized with the same `ThreadPoolExecutor` pattern `ProcessMediaFiles` already uses; the `DetectMovedFiles` and `CleanupMissingFiles` passes are merged into a single per-row decision so each file is stat'd at most once per scan; `FindMovedFile` builds a single `{filename: [paths]}` index once per scan and looks up missing files in O(1) instead of `os.walk` per missing file. Verifiable: re-run a T:\ scan after the fix and observe wall-clock under 5 minutes for a no-change pass on ~50k rows. Complements criterion 12 (cap behavior) -- this owns the throughput dimension of the same code path.

24. [BUG] **`ScanJobs.NewFiles`, `UpdatedFiles`, `DeletedFiles` stay at zero for the whole scan even when rows are inserted, updated, or deleted.** Confirmed mid-scan on 2026-05-15: scan #64925 inserted MediaFiles rows (verified by querying recent IDs 622023-622032) but the heartbeat read `NewFiles=0, UpdatedFiles=0, DeletedFiles=0` throughout. Root cause: `FileScanResultModel` only tracks `TotalFilesFound / TotalFilesProcessed / TotalFilesSkipped / TotalFilesWithErrors`. There is no per-disposition counter (new vs updated vs deleted). `ProcessSingleMediaFile` increments `TotalFilesProcessed` for both inserts and updates uniformly; `ReconcileWithDisk` decides deletions but doesn't surface a delete count to ScanResults. The `UpdateJobStatus` writer only sets these columns when a `ScanResults` model is passed, and even then the model has no fields for them. Fixed means: add `NewFilesCount`, `UpdatedFilesCount`, `DeletedFilesCount` (or equivalent) to `FileScanResultModel`; have the relevant writers (`ProcessSingleMediaFile` insert branch, `ProcessSingleMediaFile` update branch, `ReconcileWithDisk` delete branch) increment them under the existing thread-safe lock; have `UpdateJobStatus` write them through. Verifiable: trigger a scan that creates a known number of new files, updates a known number, deletes a known number; observe the three counters in `ScanJobs` match. Owns the per-disposition slice of criterion 17's contract; criterion 17 itself owns the heartbeat-cadence dimension.

25. [BUG] **`FindFuzzyFileMatch` reloads all RootFolder MediaFiles from DB and regex-parses every row per new file (O(N x M)).** Confirmed against I9-2024 scan #64925 on 2026-05-15: ~22 new Graham Norton episodes were taking 3-5 seconds each. Per new file, `FindFuzzyFileMatch` calls `Repository.GetMediaFilesByRootFolderId(RootFolderId)` returning all ~45,000 T:\ rows, then iterates the full set calling `ExtractShowInfo` (regex parse) on every `DbFile.FileName`, then stats candidate paths over NFS. Across the 5-thread parallel pool, each new file triggers an independent 45k-row DB load + 45k regex-parse storm. For 22 new files that is 990,000 ops where 22 dict lookups would suffice. Same anti-pattern family as criterion 23 (per-file work that should be precomputed once per scan), but distinct code path -- `FindMovedFile` vs `FindFuzzyFileMatch`. Fixed means: build a `{(ShowName, Season, Episode): [DbFile, ...]}` index once in `PerformScan` from a single `GetMediaFilesByRootFolderId` call, pass it down through `ProcessMediaFiles` -> `ProcessSingleMediaFile` -> `FindFuzzyFileMatch`, look up in O(1). Preserves the existing `IsFuzzyMatch` + `os.path.exists` candidate-validation step. Same threading concerns as `ReconcileWithDisk`'s filename index -- read-only after build, safe for the parallel pool. Verifiable: trigger a scan that introduces N new files; observe per-new-file wall-clock under 100ms instead of seconds.

26. **`HasFileChanged` must return False for an unchanged file regardless of which worker reads it.** Two workers scanning the same physical file must produce the same change-detection verdict; the disposition of a row cannot depend on which worker last saw it. Confirmed violated against larry-worker-1 scan #64930 (M:\) and #64931 (T:\) on 2026-05-16: I9-2024 had scanned the same files hours earlier and `HasFileChanged` returned False uniformly (UpdatedFiles=0); larry-worker-1 then scanned them and `HasFileChanged` returned True for **every single file** (M:\ UpdatedFiles=3,291 = all rows; T:\ UpdatedFiles=1,923+ in flight before stop). **Root cause confirmed empirically (2026-05-16):** `GetFileModificationTime` called `datetime.fromtimestamp(ts)` without a `tz=` parameter, returning a naive datetime in the worker's local timezone. The DB column `MediaFiles.FileModificationTime` is `timestamp without time zone` so the offset was lost. I9 (MST) and Larry (UTC container) wrote the same POSIX timestamp as values 25,200 seconds (= 7 hour MST/UTC offset) apart. **Fix shipped 2026-05-16:** `GetFileModificationTime` and `IsSameFile` now return `datetime.fromtimestamp(ts, tz=timezone.utc).replace(tzinfo=None)` -- naive UTC, worker-independent. Cross-worker delta verified at 0s. **One-time storm expected:** the first scan after the fix on any worker will UpdatedFiles=True for every row whose stored mtime was written by a non-UTC worker (most existing rows). After that single pass the column heals to uniform UTC. Verifiable post-storm: scan rootfolder on worker A, capture UpdatedFiles. Re-run on worker B (no disk changes). UpdatedFiles for B = 0.

27. **MediaFiles cannot have duplicate rows for the same logical file: `(StorageRootId, LOWER(RelativePath))` is unique.** A logical file is identified by the tuple `(StorageRootId, RelativePath)` (forward-slash form), NOT by the legacy `FilePath` string -- so two rows that disagree only on backslash escaping (`T:\Show\f.mkv` vs `T:\\Show\f.mkv`) must not coexist. Verifiable: `SELECT COUNT(*) FROM (SELECT StorageRootId, LOWER(RelativePath), COUNT(*) FROM MediaFiles WHERE StorageRootId IS NOT NULL AND RelativePath IS NOT NULL GROUP BY StorageRootId, LOWER(RelativePath) HAVING COUNT(*) > 1) sq` returns 0; a unique index on `(StorageRootId, LOWER(RelativePath))` exists; attempting an insert that violates it raises `psycopg2.errors.UniqueViolation`.

28. **Probe + loudness measurement runs inline with every scan.** A scan that discovers new files or detects existing files needing metadata MUST run the metadata pipeline (ffprobe via `MediaProbeBusinessService._ExecuteProbe`, which already chains `LoudnessAnalysisService.MeasureAndPersist` per `media-tabs-and-loudness.feature.md` criterion 7) on those files before the scan reports `Completed`. After a scan completes, the rows it touched have populated probe metadata AND populated loudness columns (`SourceIntegratedLufs`, `SourceLoudnessRangeLU`, `SourceTruePeakDbtp`, `LoudnessMeasuredAt`) -- a follow-up sweep by an external probe pass is not required. Reasoning: the worker has the file open during scan reconciliation; piggybacking the probe + ebur128 in the same scan-time access avoids a second file-open later and gets newly-discovered media into the cascade (Quick Fix / Transcode routing) on the same scan tick. Verifiable: pick a fresh MediaFiles row inserted by a scan; query `SELECT Resolution, AudioCodec, LoudnessMeasuredAt, SourceIntegratedLufs FROM MediaFiles WHERE Id=<id>` -- all four are non-NULL within the scan's wall time. (Skip applies to files where `FFprobeFailureCount >= MaxFFprobeFailures`, files flagged `AudioCorruptSuspect=true`, or files where the worker cannot resolve the local path -- the existing _ExecuteProbe gates already handle these.)

## Status

IN PROGRESS -- scanning vertical revival. Active work: criteria 20, 21, 11, 22 in
that order (path validation gates the rest; multi-drive workflow gates parallel
work; smoke test verifies the full vertical end-to-end). Criteria 1-10, 18 remain
COMPLETE. Criteria 12, 16, 19 stay [BUG] and are out of scope for this slice.
Criteria 13-15, 17 to verify against current implementation as part of criterion 22.

Criterion 17 promoted to [BUG] on 2026-05-15 -- producer-side progress writer
is silent during the walk; recorded separately in memory/KNOWN-ISSUES.md.

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
      indistinguishable. Tracked in `memory/KNOWN-ISSUES.md` Open section. Fix
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

- [x] 3.8. **Criterion 26 + FileName corruption shipped + verified (2026-05-16).**
      Cross-worker mtime drift root-caused to `GetFileModificationTime`
      returning local-tz naive datetimes; fix uses naive UTC via
      `fromtimestamp(ts, tz=timezone.utc).replace(tzinfo=None)` (commit
      5f1f6f8). Symptom investigation revealed a SECOND bug:
      `GetFileNameFromPath` used `os.path.basename` which on Linux does
      not recognize backslash, so canonical Windows paths stored the
      whole FilePath as FileName -- 91,588 of 102,576 rows (89%)
      corrupted. Fix uses OS-agnostic
      `normalized = filePath.replace('\\\\', '/'); rsplit('/', 1)[-1]`
      (commit 706f2bc). `Scripts/SQLScripts/BackfillFileNameCorruption.py`
      repaired 84,510 rows. 3-way smoke test (I9-2024 Windows MST,
      larry-worker-1 Linux UTC, wakko-worker-1 Linux UTC) produced
      byte-identical canonical_filepath / size_bytes / filename / mtime
      via `Scripts/smoke_cross_worker.py`. Larry + Wakko containers
      redeployed with both fixes.
      **PICKUP (when resuming FileScanning):** I9 WorkerService is
      currently Paused, ScanEnabled=false; needs to be restarted by
      operator so PID 19224 picks up the new FileManagerService code
      from disk. After restart, flip ScanEnabled=true + Status='Online'
      on I9-2024 and verify a fresh M:\ scan reports UpdatedFiles=0
      (clean incremental skip end-to-end across both fixes). If passes,
      multi-worker scanning is safe to enable (criterion 11 multi-worker
      affinity work becomes unblocked).

- [x] 3.7. **ReconcileWithDisk moved to path-storage Phase 4 read pattern (2026-05-15).**
      Set membership now keyed on `(StorageRootId, RelativePath.lower())`
      tuples computed via `PathStorage.Parse`, not on OS-coupled `FilePath`
      strings. Same comparison works identically on Windows and Linux
      workers -- no `_ToCanonicalPath` round-trip in the comparison hot
      path. DB rows with NULL StorageRootId (the ~2 rows that missed the
      Phase 2 backfill) are preserved, never deleted. Unparseable disk
      paths (no matching StorageRoot prefix) are excluded from the disk
      set with a WARNING log. **Safety guard added:** if proposed delete
      count exceeds 90% of DatabaseFiles, the reconcile aborts with an
      ERROR log and zero mutations -- catches the catastrophic
      translation-failure case where a misconfigured worker would
      otherwise wipe an entire RootFolder. First consumer to use
      `(StorageRootId, RelativePath)` as the canonical lookup key;
      moves path-storage Phase 4 forward by one concrete code path.

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
| Features/FileScanning/FileScanningBusinessService.py | Scan logic, duplicate detection, incremental filtering. Holds two repository handles: `self.Repository` (FileScanningRepository for RootFolders + scan-state + MediaFiles list/lookup queries) and `self.MediaFilesRepository` (MediaFilesRepository for per-row MediaFile CRUD -- Get/Save/Delete by id and by Path). Both share one DatabaseService instance. |
| Features/FileScanning/FileScanningRepository.py | RootFolders CRUD, scan-state queries (GetRunningScans, etc.), MediaFiles list/lookup queries (GetMediaFilesPaginated, GetMediaFileByFileName, GetTranscodeCandidates*). Does not own per-row MediaFile CRUD -- that lives in MediaFilesRepository. |
| Features/MediaFiles/MediaFilesRepository.py | Per-row MediaFile CRUD (GetMediaFileById, GetMediaFileByPath, SaveMediaFile, DeleteMediaFile, DeleteMediaFileByPath). Accepts canonical-string paths or Path objects; typed-pair WHERE clauses. |
| Templates/FileScanning.html | Scanning UI page |

## Cross-Vertical Contract

This section locks the FileScanning vertical's public surface. Other verticals interact ONLY through what is listed below.

### Columns the FileScanning vertical WRITES

| Column | Written by |
|---|---|
| `MediaFiles` row INSERT/DELETE | `FileScanningBusinessService.PerformScan` + `CleanupMissingFiles` |
| `MediaFiles.{FilePath, FileName, SizeMB, LastModifiedDate, RootFolderId, StorageRootId, RelativePath}` | Scan insert; updated on rename-detect + in-place-update |
| `MediaFiles.FFprobeFailureCount` | `MediaProbe` writes via the failure-tracking path; FileScanning's `CleanupMissingFiles` may reset |
| `ScanJobs.*` (all columns) | `FileScanningBusinessService.PerformScan` (heartbeat + phase + counts) |
| `RootFolders.*` | `DatabaseManager.AddRootFolder / DeleteRootFolder` |
| `MediaFilesArchive` row (read-only audit; preserved on deletion) | `FileReplacement` writes original metadata before swap; FileScanning's `CleanupMissingFiles` does NOT delete these |

### Columns the FileScanning vertical READS from external tables

| Column | Read by | Owner |
|---|---|---|
| `SystemSettings.{ContinuousScanIntervalMinutes, ExcludedDirectories, AllowedExtensions}` | `ContinuousScanService` | SystemSettings vertical |
| `Workers.{ScanEnabled, Status}` | `ContinuousScanService` claim path | Workers data accessor |
| Filesystem at root paths | Walk + stat | OS |

### Stable function entry points (cross-vertical callers)

| Class.method | External caller(s) |
|---|---|
| `FileScanningBusinessService.PerformScan(RootFolderId, WorkerName) -> ScanJob` | Manual UI trigger; ContinuousScanService |
| `FileScanningRepository.GetMediaFileById(Id) -> Optional[MediaFileModel]` | Every vertical that needs a MediaFile by id (re-exposed via `Repositories.DatabaseManager`) |
| `Repository.GetRunningScans(RootFolderPath=None) -> List[ScanJob]` | Activity, TeamStatus |

### HTTP API surface

| Method + URL | Purpose |
|---|---|
| `POST /api/Scan/Start` | Trigger manual scan |
| `GET /api/Scan/Status` | Current scan job status |
| `GET /api/FileScanning/MediaFiles/Corrupt` | Files exceeding FFprobe failure cap |
| `POST /api/RootFolders` | Add a root folder |
| `DELETE /api/RootFolders/<id>` | Remove a root folder |

### What is EXPLICITLY NOT a contract

- Internal scan-phase state machine (Walking / Reconciling / Probing / etc.) -- the `ScanJobs.Phase` column is the contract; internal transitions may change
- Fuzzy-match heuristic (`FindFuzzyFileMatch` parsing + size-tolerance window) -- tunable
- The exact order of insert vs delete during rename-detection -- atomic from the consumer's perspective
- Whether `ContinuousScanService` runs in-process or as a separate thread -- runtime detail
- Internal class names (`FileScanningBusinessService`, etc. may be split as the vertical grows)
