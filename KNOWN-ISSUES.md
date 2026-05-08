# Known Issues

## Open

### [BUG] Services resolve tool paths and file paths from SystemSettings instead of per-worker config
**Date:** 2026-05-08
**Affects:** FileReplacement, FileScanning, QualityTesting, MediaProbe -- any service that creates FFmpegService() or accesses media file paths without worker-specific config
**Criterion violated:** post-transcode-pipeline.feature.md criterion 4c, criterion 13

SystemSettings stores FFmpeg/FFprobe paths as Windows-relative values (`FFmpegMaster\bin\ffprobe.exe`). The Workers table stores correct per-worker paths (`/usr/local/bin/ffprobe`). Any service that creates `FFmpegService()` without an explicit override reads from SystemSettings, which breaks on non-Windows workers. This prevents running file replacement re-probe, media scanning, quality testing, or any FFprobe-dependent operation on Linux workers.

The broader issue: tool paths and path translation are per-worker facts, not system-wide settings. No service besides the transcode job itself can currently run on a non-Windows worker.

**Partial fix applied:** FFprobePath threaded through ProcessTranscodeQueueService -> ShouldQualityTestService -> FileReplacementBusinessService -> FileManagerService for the transcode flow. 64 stale MediaFiles records repaired via `Scripts/SQLScripts/FixStaleMediaFiles.py`.

**Remaining gaps:**
- QualityTestingBusinessService.CheckAndTriggerAutoReplace (line 974) and SkipQualityTest (line 1113) create FileReplacementBusinessService without FFprobePath
- FileScanning/MediaProbe create FFmpegService() with no worker override -- scanner cannot run on Linux workers
- Every new call site must remember to thread FFprobePath or it silently breaks

**Root fix:** Add a `WorkerContext` process-level singleton (set once at startup from Workers table). FFmpegService reads from WorkerContext before falling back to SystemSettings. All services get the right paths automatically with zero constructor threading. Remove FFmpegPath/FFprobePath from SystemSettings once WorkerContext is in place.

**Look first:** `Services/FFmpegService.py:19` (constructor reads SystemSettings), `Services/FileManagerService.py:18`, `Features/QualityTesting/QualityTestingBusinessService.py:974`

**Fix with:** `/t`

### [FIXED] LocalStaging mode crashes workers without StagingDirectory configured
**Date:** 2026-05-07
**Fixed:** 2026-05-07
**Affects:** TranscodeJob -- ProcessTranscodeQueueService.py, all job types (transcode, remux, subtitle fix)
**Criterion violated:** local-staging.feature.md -- LocalStaging should not crash workers that lack the required infrastructure

`TranscodeFileMode` is a global SystemSetting. When set to `LocalStaging` (for Docker workers on Larry), the Windows primary machine also enters LocalStaging mode. `ComputeCanonicalOutputPath()` calls `os.path.join(self.OutputDirectory, ...)` where `self.OutputDirectory` (from `Workers.StagingDirectory`) is NULL for the Windows worker, causing `TypeError: expected str, bytes or os.PathLike object, not NoneType`.

Secondary impact: when the Windows TranscodeService crashed and shut down, it set the shared `ServiceStatus` row to `Stopped`, which caused idle Larry workers (1 and 4) to stop picking up jobs.

**Fix:** All three job types (ProcessJob, ProcessRemuxJob, ProcessSubtitleFixJob) now validate `self.OutputDirectory` before entering LocalStaging mode. If NULL, fall back to InPlace with a warning log. Defense-in-depth guard added in `ComputeCanonicalOutputPath()`.

### [BUG] Second concurrent job shows first job's progress
**Date:** 2025-05-05
**Affects:** TranscodeJob feature -- concurrent job progress tracking
**Criterion violated:** TranscodeJob.feature.md -- each running job must report independent progress

When MaxConcurrentJobs > 1 and a second job starts while the first is still running, the second job displays the same progress percentage and ETA as the first (e.g., both show 20.5% / ETA 01:41:41). Only one FFmpeg process is actually running.

**Look first:** `Features/TranscodeJob/ProcessTranscodeQueueService.py:169` (`GetStatus` returns single `currentProgress`), `GetCurrentTranscodeProgress()` in DatabaseManager (likely returns one row, not per-job), and `VideoTranscodingService.TranscodeVideo` (process spawning).

**Fix with:** `/t`

### [FIXED] Post-transcode pipeline does not complete (VMAF + file replacement not firing)
**Date:** 2026-05-07
**Fixed:** 2026-05-07
**Affects:** QualityTesting, FileReplacement -- transcode.flow.md stages 6-7

**Root cause (2 compounding issues):**
1. ShouldQualityTestService.ShouldTestFile() always returned True, ignoring QualityTestRequired.
2. FileReplacementBusinessService had no path translation (hardcoded Windows paths).

**Fix:** Removed dead ShouldTestFile(). ProcessTranscodedFile() now reads QualityTestRequired from TranscodeAttempt -- when False, calls FileReplacement directly with BypassVMAFCheck=True. FileReplacementBusinessService accepts PathTranslation, translates canonical paths before all filesystem ops, skips shutil.move for InPlace mode. HandleJobFailure cleans up partial output files and TemporaryFilePaths rows on failure. See post-transcode-pipeline.feature.md.

### [FIXED] Concurrent job progress invisible in UI
**Date:** 2026-05-08
**Fixed:** 2026-05-08
**Affects:** TranscodeJob -- progress display when MaxConcurrentJobs > 1
**Root cause:** `GetCurrentTranscodeProgress()` and `GetAllCurrentTranscodeProgress()` in `DatabaseManager.py` used `INNER JOIN TranscodeQueue ... AND tq.Status = 'Running'` to filter active jobs. Progress display depended on a transient queue row instead of the authoritative `TranscodeAttempts.Success IS NULL`. When a concurrent job's queue row disappeared, the still-running sibling became invisible.
**Fix:** Removed the `INNER JOIN TranscodeQueue` from both progress queries. Progress now uses `TranscodeProgress + TranscodeAttempts WHERE Success IS NULL` -- no queue dependency.

**Note:** The queue rows for concurrent jobs are still disappearing (cause unknown). An audit trigger (`trg_transcodequeue_delete`) is in place on the DB to capture the next occurrence. The progress fix makes the UI resilient to this regardless.

### [BUG] DatabaseManager.py monolith -- dual database access paths
**Date:** 2026-05-07
**Affects:** All features that still import from Repositories/DatabaseManager.py instead of their own Repository
**Criterion violated:** Feature vertical isolation -- each feature should access the database exclusively through its own Repository

`Repositories/DatabaseManager.py` (630+ lines) is the legacy data access layer. Features are supposed to use `Features/<Name>/<Name>Repository.py`, but some still call DatabaseManager directly. This creates two paths to the database: the feature Repository and the legacy monolith. Unclear where new queries should go, and changing a query may need updates in two places.

**Look first:** `Repositories/DatabaseManager.py` -- audit which features import from it. Cross-reference with each `Features/<Name>/<Name>Repository.py` to find overlap.

**Fix with:** `/n` (this is a migration, not a quick fix -- needs audit of all callers first)

### [BUG] Feature vertical boundaries do not match governed code
**Date:** 2026-05-07
**Affects:** TranscodeJob.feature.md, FileReplacement.feature.md, Services/CommandBuilderService.py, Services/FFmpegAnalysisService.py, Core/Services/PathTranslationService.py
**Criterion violated:** TranscodeJob.feature.md scope/criteria mismatch; FileReplacement.feature.md cross-feature dependency

TranscodeJob.feature.md declares scope `Features/TranscodeJob/**` + `TranscodeService/Main.py`, but its criteria govern behavior in CommandBuilderService (conditional yadif, output mode), FFmpegAnalysisService (per-worker FFprobe), PathTranslationService (multi-prefix translation), and ProcessTranscodeQueueService (VMAF toggle, worker config loading). Separately, FileReplacement depends on MediaProbe for re-probing with no explicit contract.

**Look first:** TranscodeJob.feature.md criteria list -- each criterion that references a file outside the declared scope. `Features/FileReplacement/FileReplacementBusinessService.py` for the MediaProbe call.

**Fix with:** `/n` (architectural boundary redesign -- either expand TranscodeJob scope or extract worker/command-building into separate feature verticals)

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

### [FIXED] Thread-limiting changes degraded worker transcode performance
**Date:** 2026-05-07
**Fixed:** 2026-05-07
**Affects:** TranscodeJob -- CommandBuilder.py svtav1-params, docker-compose CPU settings
**Criterion violated:** local-staging.feature.md criterion 8 -- CPU utilization >90% with 4 concurrent workers

Changes added to fix thread contention (`lp=8` in svtav1-params, `-threads 8`, `MEDIAVORTEX_MAX_CPU_THREADS=8` env var, Docker `cpus: "8"` limit) resulted in 10% total CPU utilization, load average >90, and ~1 hour per episode. SVT-AV1 creates ~120-132 OS threads per process regardless of `lp` value. Docker CFS throttling starved encoding threads; `lp` added overhead without reducing thread count.

**Fix:** Reverted all three changes: removed `lp=N` from `AddFilmGrainParameter()`, removed `MEDIAVORTEX_MAX_CPU_THREADS` env var from docker-compose.yml, cleared `MaxCpuThreads` from Workers table. Rebuilt image, redeployed. Workers returned to ~100-200% CPU per process (pre-change baseline).

**Lesson:** SVT-AV1's `lp=N` does NOT reduce OS thread count — it only limits encoding pipeline parallelism while still creating the full thread pool. Docker `cpus` CFS throttling is counterproductive when the process has many idle threads that consume quota on wakeup. Any future thread-limiting work needs isolated benchmarking with controlled variables, not live tweaking.

**Remaining:** 4 workers at 480p preset 6 still only use ~10% of a 64-CPU system. This is a separate investigation (480p frame size limits SVT-AV1 parallelism). Do not attempt to fix in the same session as deployment work.

### [FIXED] FFmpegService.py cpu_affinity overrides Docker cpuset pinning
**Date:** 2026-05-07
**Fixed:** 2026-05-07
**Affects:** TranscodeJob -- FFmpegService.py, VideoTranscodingService.py, Docker worker performance
**Criterion violated:** local-staging.feature.md criterion 8 -- CPU utilization >90% with 4 concurrent workers

`FFmpegService.py:292` unconditionally called `psutil.cpu_affinity(list(range(MaxCpuThreads)))` on every FFmpeg process. Inside Docker containers with NUMA-aligned cpuset (only even or odd CPU IDs), `range(N)` includes CPU IDs that don't exist in the container. psutil intersects with available CPUs, leaving FFmpeg pinned to as few as 4 cores instead of 16. Separately, `VideoTranscodingService.py:68` raised `ValueError` when `MaxCpuThreads` was NULL in SystemSettings, crashing all jobs.

**Root cause:** Two independent app-level affinity code paths (`FFmpegService.py` and `CpuAffinityService.py` via `VideoTranscodingService.py`) that assume sequential CPU IDs starting at 0. Docker cpuset already handles CPU isolation; app-level affinity is redundant and harmful in containerized deployments.

**Fix:** Both `FFmpegService.py` and `VideoTranscodingService.py` now skip affinity calls when `/.dockerenv` exists. Docker cpuset is the sole CPU isolation mechanism in container deployments. The `CpuAffinityEnabled = false` DB setting was already set but only controlled `CpuAffinityService` — `FFmpegService` had its own unchecked path.

### [FIXED] QueryDatabase.py sql command silently rolls back writes
**Date:** 2026-05-05
**Fixed:** 2026-05-05

Added `--commit` flag to `QueryDatabase.py sql`. Default behavior unchanged (rollback for safety). setup.sh updated to use `--commit` for worker registration and share mapping writes. Output now explicitly says "(rolled back -- use --commit to persist)" when writes are not committed.
