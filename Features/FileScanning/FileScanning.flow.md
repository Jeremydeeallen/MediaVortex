# Flow: File Scanning

## Entry Point

`POST /api/FileScanning/Scan/Start` (manual, from `/Scanning` page) **or** `ContinuousScanService` background thread on workers with `Workers.ScanEnabled=true` (kicks every `ContinuousScanIntervalMinutes`, default 60).

Both paths land in `FileScanningBusinessService.StartScan(rootfolderpath, recursive=true)` which writes a `ScanJobs` row with `Status='Pending'` and a freshly-generated UUID `JobId`.

## Pipeline

| Stage | File | What It Does |
|------|------|--------------|
| 1. Pick / start | `FileScanningBusinessService.StartScan` | UPSERTs ScanJobs row; if no other Running scan for this rootfolder, sets Status='Running', StartTime=NOW(), spawns a worker thread |
| 2. Walk filesystem | `FileScanningBusinessService._WalkRootFolder` | `os.walk` (or platform-equivalent) over `rootfolderpath`; updates `ScanJobs.CurrentDirectory` per directory enter; counts each candidate via `TotalFiles += 1` |
| 3. Per-file decision | same | For each file: `MediaFiles.Path = ?` lookup. If absent -> insert MediaFiles row (NewFiles += 1). If present and size/mtime changed -> update (UpdatedFiles += 1). If present and unchanged -> skip (SkippedFiles += 1). |
| 4. Mark deleted | `FileScanningBusinessService._MarkDeletedFiles` | After the walk, MediaFiles rows whose Path lives under this rootfolder but were not seen this pass have `Deleted=true` set (DeletedFiles += 1) |
| 5. Update RootFolders | `FileScanningBusinessService._UpdateRootFolderStats` | `RootFolders.LastScannedDate = NOW()`, `TotalSizeGB` recomputed from MediaFiles |
| 6. Mark complete | same | ScanJobs row: Status='Completed', EndTime=NOW(), Progress=100.0 |

## State Surface

`ScanJobs` columns the operator might see:
- `RootFolderPath` -- which mount is being scanned
- `Status` -- `Pending` / `Running` / `Completed` / `Failed` / `Stopped`
- `Progress` (0-100, double) -- updated periodically during the walk
- `CurrentDirectory` -- last-seen directory path (truncated for UI)
- `TotalFiles` / `ProcessedFiles` / `NewFiles` / `UpdatedFiles` / `DeletedFiles` / `SkippedFiles` / `EncodingErrors`
- `StartTime` / `EndTime` / `LastUpdated`
- `ErrorMessage` (when Status='Failed')

`RootFolders.LastScannedDate` is the operator-facing "last successful scan" anchor.

## Failure Modes

| Failure | Symptom | Resolution |
|---|---|---|
| Rootfolder unreachable (NFS mount down, drive unmapped) | ScanJobs.Status='Failed', ErrorMessage='[Errno ...] No such file or directory' | Verify mount on the worker host; fix mount; next continuous-scan tick retries |
| Application restart mid-scan | ScanJobs.Status='Completed' with ErrorMessage='Application restarted' (current convention) and partial counts | Acceptable: next scan picks up where this left off. The "Completed" status with an error message is a quirk -- a future cleanup may rename to 'Interrupted' |
| Permission denied on a subdirectory | EncodingErrors increments; specific file/dir logged at WARNING; scan continues | Normal operating mode -- counts surfaced in the result |
| Concurrent scan attempt for same rootfolder | StartScan returns `{'Success': False, 'ErrorMessage': 'Scan already running for ...'}` | Operator waits or stops the running scan first |
| Worker crash during scan | ScanJobs row left in 'Running' indefinitely | No recovery today -- the row stays Running until manually reset. Stuck-scan detection is not implemented. **[KNOWN GAP]** |
| File modified during scan | Stat-based change detection may flag the row twice (once during scan, once next pass) | Acceptable. Idempotent updates; no duplicate MediaFiles row is created |

## Continuous Mode Specifics

`ContinuousScanService` runs once per worker process when `Workers.ScanEnabled=true`. The thread loop:

1. Wait `ScanIntervalMinutes` (default 60) on a `StopEvent`.
2. If `StopEvent` fires, exit.
3. Otherwise, iterate every `RootFolders` row and call `StartScan(path, recursive=true)`.
4. Wait for each scan to complete before starting the next (serial within a worker).

Multiple workers with `ScanEnabled=true` may schedule scans of the same rootfolder concurrently; the per-rootfolder concurrent-scan guard at stage 1 ensures only one runs.

## Surface

`/Scanning` (FileScanning.html) -- the dedicated scan-management page (start/stop, history, progress).

`/` Home -- root-folder summaries (last-scanned date).

`/Activity` -- **gap today.** The operator cannot see active scans on the dashboard alongside transcodes and quality tests. Closed by the `scanning-on-activity-page.feature.md` feature.
