# Known Issues

## Open

### [BUG] Second concurrent job shows first job's progress
**Date:** 2025-05-05
**Affects:** TranscodeJob feature -- concurrent job progress tracking
**Criterion violated:** TranscodeJob.feature.md -- each running job must report independent progress

When MaxConcurrentJobs > 1 and a second job starts while the first is still running, the second job displays the same progress percentage and ETA as the first (e.g., both show 20.5% / ETA 01:41:41). Only one FFmpeg process is actually running.

**Look first:** `Features/TranscodeJob/ProcessTranscodeQueueService.py:169` (`GetStatus` returns single `currentProgress`), `GetCurrentTranscodeProgress()` in DatabaseManager (likely returns one row, not per-job), and `VideoTranscodingService.TranscodeVideo` (process spawning).

**Fix with:** `/t`

### [FIXED] Yadif deinterlacing applied to progressive files
**Date:** 2026-05-05
**Fixed:** 2026-05-05
**Affects:** All profiles, CommandBuilder video filter chain

All 12 profiles had YadifMode=1/YadifParity=1/YadifDeint=1 hardcoded. CommandBuilder.BuildVideoFilters applied yadif unconditionally based on profile settings without checking MediaFiles.IsInterlaced. This caused:
1. Unnecessary deinterlacing on progressive content (majority of queue)
2. yadif is single-threaded per-frame -- bottlenecked SVT-AV1 to ~2 cores regardless of -threads setting
3. Encode speed ~8.4 FPS on progressive files vs ~10+ FPS without yadif

**Fix:** Set YadifMode=NULL, YadifParity=NULL on all profiles. CommandBuilder already skips yadif when these values are NULL/blank. Future: CommandBuilder should check IsInterlaced from MediaFile and only apply yadif when the source is actually interlaced.

### [BUG] FilePath used as denormalized natural key across 6+ tables
**Date:** 2026-05-05
**Affects:** Schema-wide -- MediaFiles, TranscodeAttempts, TranscodeFiles, TranscodeQueue, CompliantFiles, ProblemFiles
**Criterion violated:** Data normalization -- same filepath (with platform-specific drive letter prefix) stored redundantly across tables instead of referencing MediaFiles.Id as a foreign key.

Full Windows paths (e.g., `T:\Shows\file.mkv`) are stored as natural keys in at least 6 tables. This causes:
1. Case inconsistencies already present in production data (`T:\` vs `t:\`, `Z:\` vs `z:\`)
2. Platform coupling -- every table embeds Windows drive letters, making cross-platform workers depend on prefix translation at query boundaries
3. No referential integrity -- deleting/renaming a file in MediaFiles does not cascade to dependent tables
4. Path changes (drive letter remapping, share migration) require updating every table

**Scale:** ~67k rows in MediaFiles, ~3.8k in TranscodeFiles, ~2.9k in TranscodeAttempts, ~1.4k in CompliantFiles.

**Look first:** `/data-expert` for schema analysis, then `Scripts/SQLScripts/AddDistributedColumns.py` for migration patterns.

**Fix with:** `/n` (this is a schema redesign, not a quick fix)

### [FIXED] StuckJobDetector breaks distributed transcoding -- orphaned FFmpeg, corrupted results
**Date:** 2026-05-05
**Fixed:** 2026-05-05
**Affects:** Features/ServiceControl/StuckJobDetectionService.py, TranscodeService worker flow

**Root cause (5 compounding failures):**
1. `GetActiveJobsByService` did not SELECT WorkerName, so Tier 1 heartbeat check never ran and all jobs were treated as local
2. `IsProcessAlive` checked `'ffmpeg' in process.name()` on the Python worker PID -- always false
3. `SignalHandler` reset ALL workers' queue items and active jobs, not just its own
4. `CrashRecoveryService` operated on ALL workers' active jobs, incorrectly resetting remote jobs
5. `QueueManagementService.Stop()` reset ALL running jobs globally

**Fix:** All destructive operations scoped by WorkerName/ClaimedBy:
- `GetActiveJobsByService` now includes WorkerName in SELECT + optional filter
- `IsProcessAlive` checks `process.is_running()` only (PID reuse guarded by Tier 1 heartbeat)
- `SignalHandler` uses `AND ClaimedBy = %s` and `AND WorkerName = %s`
- `CrashRecoveryService` accepts WorkerName, scopes all queries and cleanup
- `QueueManagementService.ResetTranscodeQueueRunningJobs` accepts WorkerName filter
- All cleanup also clears ClaimedBy/ClaimedAt when resetting to Pending

### [FIXED] QueryDatabase.py sql command silently rolls back writes
**Date:** 2026-05-05
**Fixed:** 2026-05-05

Added `--commit` flag to `QueryDatabase.py sql`. Default behavior unchanged (rollback for safety). setup.sh updated to use `--commit` for worker registration and share mapping writes. Output now explicitly says "(rolled back -- use --commit to persist)" when writes are not committed.
