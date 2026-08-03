# Scan

**Slug:** scan

## What It Does

Discovers media files under registered RootFolders. Writes MediaFiles rows (one per file) with `filesize` + `filemodificationtime` + `LastScannedDate`. Does NOT open files. Does NOT probe. Auto-chains to probe via shared column state (`Resolution IS NULL OR NeedsReprobe = TRUE`).

Pipeline stage `ST1..ST3` in `ingest.flow.md`. This feature owns the scan vertical's contract; the flow doc owns the cross-stage seams.

## Workflows

| # | User action | Surface element | Handler | Backing class.method |
|---|---|---|---|---|
| W1 | Enter a canonical path + hit Sync Path | `/Settings` Sync Path input + button | `POST /api/Sync/Path` | `Features/Sync/SyncPathController.SyncPath` |
| W2 | Click Scan Now on a RootFolder row | `/Settings` Registered Drives Scan Now button | `POST /api/RootFolders/<id>/ScanNow` | `Features/FileScanning/FileScanningController.ScanNow` (existing) |
| W3 | Toggle a RootFolder's ScanEnabled | `/Settings` Registered Drives switch | `PATCH /api/RootFolders/<id>` | `Features/FileScanning/FileScanningController.UpdateRootFolder` (existing) |
| W4 | View in-flight scans | `/Activity` Active Scans block | reads `/api/TeamStatus/Overview` | existing |
| W5 | View scan history | `/Operations` Recent Scans card | reads `/api/SQLQueries/GetRecentScanRuns` | existing |
| W6 | Stop a running scan | `/Activity` per-row Stop button | `POST /api/Scan/<JobId>/Stop` | existing (soft-stop via `ScanJobs.Status='Stopping'`) |

## Success Criteria

C1. **Scan discovers all media files under the requested subtree and INSERTs one MediaFiles row per new file.** Idempotent identity: `(StorageRootId, LOWER(RelativePath))` via `idx_mediafiles_storageroot_relpath_unique` (existing). Verifiable: seed empty subtree, add N files, run scan, `SELECT COUNT(*) FROM MediaFiles WHERE StorageRootId=? AND RelativePath LIKE ?%` returns N.

C2. **Unchanged file produces zero DB write.** ScanJob over a subtree where every file's `(filesize, filemodificationtime)` matches the DB row completes with `NewFiles=0, UpdatedFiles=0, DeletedFiles=0, SkippedFiles=N`. Contract: `TestScanIdempotence.py`.

C3. **Changed file (size or mtime differs) UPDATEs row + sets `NeedsReprobe = TRUE`.** ProbeWorker picks up on its next tick without any auto-chain plumbing. Contract test.

C4. **One SQL per RootFolder per scan tick.** `BatchFetchForRootFolder` returns all rows for the RootFolder in one SELECT; in-memory diff produces new/changed/deleted/renamed sets; batch write via `execute_values` INSERT/UPDATE + batch soft-delete. No per-file SQL. Contract asserts query log shape.

C5. **Rename detection preserves row identity.** When a file with `(filesize, filename)` matches a deleted row's `(filesize, filename)`, the row's `RelativePath` is UPDATED in place (not delete + insert). Preserves `Id`, `AssignedProfile`, `TranscodedByMediaVortex`, `IsCompliant`, probe metadata, `MediaFilesArchive` FK, `TranscodeAttempts` FK. Rename cap at `SystemSettings('MoveDetectionMaxFiles')` (default 100000). Contract: `TestScanRenameDetection.py`.

C6. **Genuine deletion removes MediaFiles row only.** `TranscodeAttempts` + `MediaFilesArchive` rows referencing the deleted MediaFileId persist (no FK CASCADE per `polymorphic-fk-no-cascade` memory). Contract test.

C7. **Full-library scan cycle over unchanged tree completes < 5 min.** Instrumented + measured on target hardware. Target: 20-min operator budget with margin.

C8. **RootFolders.TotalSizeGB = post-scan aggregate.** Single UPDATE from `SUM(MediaFiles.filesize) WHERE StorageRootId = ? AND RelativePath LIKE ?%`. Not pre-scan disk walk. Contract test.

C9. **Continuous scanner honors per-RootFolder ScanEnabled + per-worker ScanEnabled + PreferredWorkerName affinity.** Existing contract preserved from `ad-hoc-drive-scans.feature.md`.

C10. **Pre-scan path validation.** Before `PerformScan` claims, `_ToLocalPath(canonical)` + `LocalIsDir(local)` must succeed. Failure -> `ScanJobs.Status='Failed', ErrorMessage='Path not accessible: <canonical> -> <local>'`. Existing behavior preserved.

C11. **Scan never opens files.** Grep production scan code paths for `open(` on file objects: zero hits (dir handles from `os.scandir` OK). Contract test.

C12. **Sync Path GUI endpoint.** `POST /api/Sync/Path` `{CanonicalPath}` validates prefix against StorageRoots; on match, enqueues ScanJobs row scoped to that path; returns `{Success, ScanJobId}`. Contract test.

C13. **ContinuousScanService cadence unchanged.** Existing `ScanIntervalMinutes` (default 60) + per-worker alphabetical iteration + affinity filter preserved.

C14. **Concurrent scan on same rootfolder refused.** `StartScanning` rejects with `Error='ScanAlreadyRunning'` when partial UNIQUE index `sj_one_active_per_root` (existing) conflicts.

## Seams

Intra-feature seams. Cross-stage seams (scan -> probe, scan -> compliance) live in `ingest.flow.md` `## Seams`.

| ID | Seam | Producer | Wire shape | Consumer expects | Verification |
|---|---|---|---|---|---|
| S1 | Controller -> BusinessService | any entry-point controller (`SyncPathController` / `FileScanningController.ScanNow` / `ContinuousScanService`) | `StartScanning(canonicalpath, WorkerName)` | writes ScanJobs row, returns `{Success, JobId}` | contract test per entry |
| S2 | BusinessService -> Repository (batch fetch) | `PerformScan` | `BatchFetchForRootFolder(StorageRootId, RelativePathPrefix)` | returns `dict[RelativePath] -> (filesize, filemodificationtime)` | contract test |
| S3 | BusinessService -> Repository (batch write) | `PerformScan` after diff | `BatchUpsert(new + changed)` + `BatchSoftDelete(deleted)` | executes `execute_values` INSERT/UPDATE; sets `NeedsReprobe=TRUE` on changed | contract test |
| S4 | BusinessService -> RootFolder aggregate | post-scan | `UPDATE RootFolders SET TotalSizeGB = ...` via aggregate query | one UPDATE per RootFolder | contract test |
| S5 | ScanJobs heartbeat | `_StartProgressHeartbeat` | writes `Progress, ProcessedFiles, CurrentDirectory, LastUpdated` every 5s | `/Activity` polls | existing behavior preserved |

## What this feature does NOT own

- Probe: `Features/MediaProbe/probe.feature.md`
- Classifier: `Features/ContentClassifier/classifier.feature.md`
- Compliance recompute: cascade fires from probe/classifier per `.claude/rules/writer-owns-cascade.md`
- WorkBucket derivation: `Features/WorkBucket/work-bucket.flow.md`
- Sonarr/Radarr webhook: `Features/Ingest/ingest-webhook.feature.md`
- /Failures page: `Features/Failures/failures.feature.md`
- Per-RootFolder registration + ScanEnabled column: `Features/FileScanning/ad-hoc-drive-scans.feature.md`
- Shared scanner config (Scanners table): `Features/FileScanning/scanners.feature.md`

## Status

DRAFTED under directive `ingest-pipeline-kiss`. Code lands in IMPLEMENTING phase.
