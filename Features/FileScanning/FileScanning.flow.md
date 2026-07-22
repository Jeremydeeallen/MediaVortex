# Flow: File Scanning

**Slug:** filescanning

## Entry Point

`POST /api/FileScanning/Scan/Start` (manual, from `/Scanning` page) **or** `ContinuousScanService` background thread on workers with `Workers.ScanEnabled=true` (kicks every `ContinuousScanIntervalMinutes`, default 60).

Both paths land in `FileScanningBusinessService.StartScan(rootfolderpath, recursive=true)` which writes a `ScanJobs` row with `Status='Pending'` and a freshly-generated UUID `JobId`.

## Pipeline

| ID | Stage | File | What It Does |
|---|------|------|--------------|
| ST1 | Pick / start | `FileScanningBusinessService.StartScan` | UPSERTs ScanJobs row; if no other Running scan for this rootfolder, sets Status='Running', StartTime=NOW(), spawns a worker thread. Phase initialized to `Walking`; SizeSurvey transition follows immediately in PerformScan. |
| ST2 | SizeSurvey | `FileScanningBusinessService._RunSizeSurvey` | Stat-only recursive enumeration via `os.scandir`; heap-based top-N selection (default 100, configurable via `SystemSettings('SizeSurveyTopN')`, soft-cap 500). Top-N files UPSERTed into `MediaFiles` with size + mtime; full list persisted to `ScanJobs.TopFiles` JSONB for /Activity surfacing. Budget ~30s per share on Larry NFS. Front-loads biggest savings opportunities before the long walk. Owns directive 2026-05-28 (closed). |
| ST3 | Walk filesystem | `FileScanningBusinessService._WalkRootFolder` | `os.walk` (or platform-equivalent) over `rootfolderpath`; updates `ScanJobs.CurrentDirectory` per directory enter; counts each candidate via `TotalFiles += 1` |
| ST4 | Per-file decision | same | For each file: `MediaFiles.Path = ?` lookup. If absent -> insert MediaFiles row (NewFiles += 1). If present and size/mtime changed -> update (UpdatedFiles += 1). If present and unchanged -> skip (SkippedFiles += 1). |
| ST5 | Reconcile DB vs disk | `FileScanningBusinessService.ReconcileWithDisk` | Single pass over the disk file list returned by ScanDirectory. Builds a path set + filename->paths index, iterates DB rows for this rootfolder: row in disk set -> skip (handled by per-file processor); row missing but basename matches a disk path AND `IsSameFile` confirms (size/mtime within tolerance) -> reassign FilePath / FileName / StorageRootId / RelativePath in place; row missing with no fuzzy match -> delete. Replaces the prior `DetectMovedFiles` + `CleanupMissingFiles` sequence which serially stat-checked each DB row twice over NFS. Move-detection cap (criterion 12) preserved -- above the cap, fuzzy-match step is skipped. |
| ST6 | Update RootFolders | `FileScanningBusinessService._UpdateRootFolderStats` | `RootFolders.LastScannedDate = NOW()`, `TotalSizeGB` recomputed from MediaFiles |
| ST7 | Mark complete | same | ScanJobs row: Status='Completed', EndTime=NOW(), Progress=100.0 |

## Seams

| ID | Transition | Producer (writer) | Wire shape | Consumer (reader) expects | Verification |
|---|---|---|---|---|---|
| S1 | `ST1 -> ST2` (start -> survey) | `StartScan` writes `ScanJobs.(Id UUID, Status='Running', Phase='SizeSurvey', WorkerName, RootFolderPath, StorageRootId, RelativePath)` -- typed pair added 2026-06-05 (`path-perfect-implementation` Step 1); app-level dual-write with legacy `RootFolderPath` lands Step 2; legacy column dropped Step 6 | `ScanJobs` row visible | `_RunSizeSurvey` reads, walks `rootfolderpath` via `os.scandir` | `SELECT Phase, WorkerName FROM ScanJobs WHERE Id=<id>` -- `Phase='SizeSurvey'`, `WorkerName` set |
| S2 | `ST4 -> ST5` (insert/update -> reconcile) | `ProcessSingleMediaFile` UPSERTs `MediaFiles.(StorageRootId, RelativePath, FilePath, SizeMB, FileModificationTime)` -- mtime stored as naive UTC | Per-file rows present in `MediaFiles` for this rootfolder | `ReconcileWithDisk` enumerates DB rows for the rootfolder + builds the disk-path set | `SELECT COUNT(*) FROM MediaFiles WHERE StorageRootId=<root> AND LastScannedDate > <scan-start>` matches `ScanJobs.NewFiles + UpdatedFiles` |
| S3 | `ST4 -> transcode.ST2` (probe handoff) | Inline probe pass triggered by the scan worker per `FileScanning.feature.md C28` | `MediaFiles.(Resolution, AudioCodec, VideoBitrateKbps, ...)` populated; `LoudnessAnalysisService.MeasureAndPersist` writes `SourceIntegratedLufs`, `SourceLoudnessRangeLU`, `SourceTruePeakDbtp`, `LoudnessMeasuredAt`; probe hook chain fires `QueueManagementBusinessService.RecomputeForFiles([Id])` -> `AudioVertical` + `VideoVertical` + `ContainerVertical` `.RecomputeFor([Id])` (all profile-independent per `work-bucket.feature.md` C8); `ContentClassifier.ClassifyAndAssign(Id)` runs last as a HINT writer for `AssignedProfile`. On exit: every row has `AudioCompliant`/`VideoCompliant`/`ContainerCompliant` non-NULL, generated column `WorkBucket` reflects one of `{Compliant,Unclassified,Transcode,Remux,AudioFix}`. See `content-classifier.flow.md` + downstream vertical feature docs for baseline rules. | `transcode.flow.md` Stage 2 (PROBE) treats this as already done | `SELECT Resolution, LoudnessMeasuredAt, WorkBucket FROM MediaFiles WHERE Id IN (<rows scanned this run>)` -- all three non-NULL within scan wall-clock |
| S4 | `ST5 -> ST6` (reconcile -> rootfolder stats) | `ReconcileWithDisk` final DELETE of unmatched DB rows | `MediaFiles` row count for this rootfolder reflects disk truth | `_UpdateRootFolderStats` recomputes `RootFolders.(LastScannedDate, TotalSizeGB, StorageRootId, RelativePath)` -- typed pair on `RootFolders` added 2026-06-05 (`path-perfect-implementation` Step 1); operator-typed string still accepted via `RootFolder` legacy column, dual-write lands Step 2, legacy dropped Step 6 | `SELECT LastScannedDate, TotalSizeGB FROM RootFolders WHERE Id=<root>` matches NOW() and the post-scan SUM(SizeMB)/1024 |
| S5 | uniqueness invariant | every writer of MediaFiles | `idx_mediafiles_storageroot_relpath_unique` on `(StorageRootId, LOWER(RelativePath))` | psycopg2 `UniqueViolation` for any escape-variant duplicate insert | `SELECT COUNT(*) FROM (SELECT StorageRootId, LOWER(RelativePath), COUNT(*) FROM MediaFiles WHERE StorageRootId IS NOT NULL GROUP BY 1,2 HAVING COUNT(*)>1) sq` -> 0 |

## State Surface

`ScanJobs` columns the operator might see:
- `RootFolderPath` -- which mount is being scanned
- `Status` -- `Pending` / `Running` / `Stopping` / `Completed` / `Failed` / `Stopped`
- `Phase` -- `SizeSurvey` / `Walking` / `Reconciling` / `Probing` / `Completing` (NULL on legacy rows and after Status flips terminal); written by `FileScanningBusinessService._SetPhase` at each transition for /Activity-page visibility. SizeSurvey is the new initial phase (directive 2026-05-28); the prior chain (Walking -> Reconciling -> Probing -> Completing) is preserved.
- `TopFiles` (JSONB) -- array of `{path, fileName, sizeMB, modifiedAt}` for the top-N largest files found by SizeSurvey; surfaced on /Activity under each running scan row. NULL on legacy rows and on scans where SizeSurvey failed (caught + logged; full scan still proceeds).
- `Progress` (0-100, double) -- written by `_StartProgressHeartbeat` via `_ComputeRealProgress()`. Per-phase bands: SizeSurvey 10-30%, Walking 30%, Reconciling 50%, Probing 90-100%, Completing 100%. Phases that carry a `ProbedFiles / FilesNeedingProbe` ratio (SizeSurvey, Probing) interpolate within their band using that ratio so the bar advances continuously instead of stepping in fixed jumps. Owns feature-doc C29.
- `CurrentDirectory` -- last-seen directory path (truncated for UI)
- `TotalFiles` / `ProcessedFiles` / `NewFiles` / `UpdatedFiles` / `DeletedFiles` / `SkippedFiles` / `EncodingErrors`
- `FilesNeedingProbe` / `ProbedFiles` -- populated during `Phase='Probing'` so the Activity page shows a real per-probe bar instead of a spinner
- `StartTime` / `EndTime` / `LastUpdated`
- `ErrorMessage` (when Status='Failed')

`Status='Stopping'` is the soft-stop signal: a row flipped to `Stopping` by `POST /api/Scan/<JobId>/Stop` is observed by the owning worker's heartbeat (~5s), which flips an in-process flag; the per-file and per-probe loops exit cleanly and the worker writes `Status='Stopped'` with `EndTime=NOW()`.

`RootFolders.LastScannedDate` is the operator-facing "last successful scan" anchor.

## Failure Modes

| Failure | Symptom | Resolution |
|---|---|---|
| Rootfolder unreachable (NFS mount down, drive unmapped) | ScanJobs.Status='Failed', ErrorMessage='[Errno ...] No such file or directory' | Verify mount on the worker host; fix mount; next continuous-scan tick retries |
| Application restart mid-scan | ScanJobs.Status='Completed' with ErrorMessage='Application restarted' (current convention) and partial counts | Acceptable: next scan picks up where this left off. The "Completed" status with an error message is a quirk -- a future cleanup may rename to 'Interrupted' |
| Permission denied on a subdirectory | EncodingErrors increments; specific file/dir logged at WARNING; scan continues | Normal operating mode -- counts surfaced in the result |
| Concurrent scan attempt for same rootfolder | StartScan returns `{'Success': False, 'ErrorMessage': 'Scan already running for ...'}` | Operator waits or stops the running scan first |
| Worker crash during scan | ScanJobs row left in 'Running' until next stuck-scan detection cycle | `StuckJobDetectionService.DetectAndCleanStuckScanJobs` runs every `StuckJobDetectionIntervalSec` (default 120) on every worker. A scan is flagged stuck when (a) `WorkerName` is set and that worker's heartbeat is stale (`WORKER_HEARTBEAT_STALE_MINUTES`, default 5) or (b) `LastUpdated` is older than `StuckScanThresholdMin` (default 15, configurable via SystemSettings). Stuck rows flip to `Status='Failed'` with an explanatory `ErrorMessage`; the per-rootfolder claim guard then lets the next continuous-scan tick pick the rootfolder back up. |
| File modified during scan | Stat-based change detection may flag the row twice (once during scan, once next pass) | Acceptable. Idempotent updates; no duplicate MediaFiles row is created |
| Escape-variant insert (e.g. doubled-backslash `FilePath` from a buggy writer) | `psycopg2.errors.UniqueViolation` on `idx_mediafiles_storageroot_relpath_unique` -- the row is identified by `(StorageRootId, LOWER(RelativePath))` which is identical across variants | Loud-fail by design. `SaveMediaFile` first checks `(StorageRootId, LOWER(RelativePath))` and converts to UPDATE on hit, so well-behaved writers never trigger the constraint; the index is the safety net for any code path that bypasses the existence check. |
| Cross-worker mtime drift on unchanged files | Historical: workers in different system timezones produced different stored `FileModificationTime` values for the SAME file because `GetFileModificationTime` used naive `datetime.fromtimestamp` (interpreted in local tz). Two workers in different tz then thrashed on each other's writes (criterion 26). Resolved 2026-05-16: `GetFileModificationTime` and `IsSameFile` now compute mtime as naive UTC via `datetime.fromtimestamp(ts, tz=timezone.utc).replace(tzinfo=None)`. Worker-independent. **One-time correction storm expected on first scan after the fix:** every existing row whose stored mtime was written in a non-UTC local tz will be UpdatedFiles=True on the next scan (~7 hours off for MST-written rows). After that pass, values are uniform and the column is stable. |

## Continuous Mode Specifics

`ContinuousScanService` runs once per worker process when `Workers.ScanEnabled=true`. The thread loop:

1. Wait `ScanIntervalMinutes` (default 60) on a `StopEvent`.
2. If `StopEvent` fires, exit.
3. Resolve this worker's name from `WorkerContext.Current().WorkerName` (fallback: `socket.gethostname()`).
4. Pull `RootFolders`; reduce to top-level paths (parents cover their children).
5. **Affinity filter:** drop any rootfolder whose `PreferredWorkerName` is set and not equal to this worker's name. NULL = any ScanEnabled worker may scan.
6. For each remaining rootfolder, call `StartScanning(path, Recursive=True, WorkerName=ThisWorkerName)`.
7. Wait for each scan to complete before starting the next (serial within a worker).

`StartScanning` is the gate. One check fires before any work begins:

- **Per-rootfolder claim guard:** `Repository.GetRunningScans(RootFolderPath)` -- if any row exists in `Status IN ('Pending','Running')` for this path, `StartScanning` rejects with `Error='ScanAlreadyRunning'`. This is the claim-semantics protection against two ScanEnabled workers racing on the same rootfolder when their continuous-scan ticks coincide.

The legacy global concurrency cap (max 2 scans across all rootfolders) was retired with `FileScanning.feature.md` criterion 18c -- it contradicted per-rootfolder claim semantics on multi-worker setups.

`ScanJobs.WorkerName` records the worker that performed each scan, so the operator can confirm work landed on the intended host (e.g. larry-worker-1 for a backplane-attached TV scan vs an SMB-routed WebService).

### Pre-scan path validation (criterion 20)

Before calling `StartScanning` for each rootfolder, `ContinuousScanService._ExecuteScan` validates:
1. `_ToLocalPath(RootFolder.RootFolder)` produces a path (translation succeeds)
2. `os.path.exists(LocalRootPath)` confirms the resolved path is accessible

If validation fails, the worker:
- Logs a WARNING with both canonical and resolved paths
- Writes a `ScanJobs` row with `Status='Failed'`, `ErrorMessage='Path not accessible: <canonical> -> <resolved>'`
- Skips to the next rootfolder (no scan attempt)

This makes path-resolution failures visible in the /Scanning page's scan history.

### Runtime share-mapping refresh (criterion 21)

At the start of each scan iteration, `_RefreshShareMappings(WorkerName)` reloads `WorkerShareMappings` from the database into `WorkerContext.PathTranslation.MountMap`. New drive mappings added via the Settings page or direct DB update take effect on the next continuous-scan tick without requiring a worker restart.

### Adding a root folder

`POST /api/RootFolders` registers a new root folder:
- Body: `{"RootFolderPath": "Z:\\NewShare", "PreferredWorkerName": "larry-worker-1"}` (worker optional)
- Validates: non-empty, no duplicate (case-insensitive), normalizes drive-root trailing backslash
- Does NOT require path accessibility from WebService -- the worker validates at scan time
- UI: /Scanning page "Add Root Folder" section

### Pinning a rootfolder to a specific worker

```sql
UPDATE RootFolders SET PreferredWorkerName = 'larry-worker-1' WHERE RootFolder = 'T:\';
UPDATE RootFolders SET PreferredWorkerName = NULL WHERE RootFolder = 'T:\';  -- unpin
```

No worker restart required -- the affinity filter reads the column on each tick.

### Move-detection cap

`ReconcileWithDisk` skips the fuzzy-match (move detection) step when `MediaFiles` row count exceeds `SystemSettings('MoveDetectionMaxFiles')` (default `100000`); above the cap, missing rows are deleted directly rather than reassigned. The cap is read fresh on every scan -- raise the value at runtime via:

```sql
UPDATE SystemSettings SET SettingValue = '200000' WHERE SettingKey = 'MoveDetectionMaxFiles';
```

Skipping move detection means a rename/move outside MediaVortex degrades to delete + create, dropping `AssignedProfile` / `IsCompliant` / `RecommendedMode` / `TranscodedByMediaVortex` / probe metadata. Keep the cap above the actual library size.

## Surface

`/Scanning` (FileScanning.html) -- the dedicated scan-management page (start/stop, history, progress).

`/` Home -- root-folder summaries (last-scanned date).

`/Activity` -- **in-flight** scans only. Render as a dedicated Active Scans block under the Active Jobs card with columns: Drive | Worker | Phase | Progress | Files (+N ~U -D) | Rate | ETA | Stop. Inline top-5 largest files from SizeSurvey shown under each row. Phase badge color-codes per phase. Stale-heartbeat rows (>10 min) render amber (`table-warning`). Worker tiles gain a `Scan:` line when `ScanEnabled=true`. Payload: `/api/TeamStatus/Overview` (`ActiveScans` array with `TopFiles`), `/api/TeamStatus/Workers` (`LastScanCompleted`, `NextScanEstimate`, `CurrentScanRootFolder`), `POST /api/Scan/<JobId>/Stop`.

`/Operations` -- **completed and failed scan history**. Recent Scans card alongside the existing Recent Successes (transcodes) and Recent Failures (transcode failures). Backed by `GET /api/SQLQueries/GetRecentScanRuns?limit=N` (default 15, max 50). Ordered by `EndTime DESC`. "Real failure" classification (directive 2026-05-28): includes `Status='Completed'` always; includes `Status='Failed'` UNLESS `ErrorMessage` matches any of the housekeeping patterns (`%Application restarted%`, `%Zombie%`, `%pre-redeploy%`, `%Stuck scan cleaned by StuckJobDetectionService%`, `%post-deploy mass clear%`, `%cleared post-restart%`, `%cleared post-deploy%`, `%Stopped pre-redeploy%`); excludes `Status='Stopped'` entirely (soft-stop is an operator action, not a failure). The pattern list lives in `SQLQueriesController.GetRecentScanRuns` -- add a new substring there if a new housekeeping message starts surfacing as noise.
