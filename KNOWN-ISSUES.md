# Known Issues

## Open

### [TECH DEBT] Activity page conflates worker liveness and operational state
**Date:** 2026-05-08
**Affects:** Templates/Activity.html (worker tag display), API endpoints that return worker status

The Activity page shows a single "Online/Offline" badge per worker. It appears to be driven by `Workers.LastHeartbeat` freshness (process-is-alive signal). But the `Workers.Status` column is a separate axis -- it carries the operational state set by the Drain/Offline buttons (`Online` / `Draining` / `Offline`). When the user clicked Offline, the DB column flipped correctly to `Offline`, but the UI badge stayed green because the worker process is still alive and heartbeating (alive AND stopped is a valid combination today).

The four real states from the combination:
- Status=Online + heartbeat fresh -- alive AND working (the green "Online" users expect)
- Status=Online + heartbeat stale -- should be working but process is dead (broken, needs investigation)
- Status=Offline + heartbeat fresh -- alive but stopped (process running, not picking up jobs)
- Status=Offline + heartbeat stale -- clean shutdown

**Fix:** show two separate visuals per worker row in the Activity table.
1. Connectivity indicator (dot or pill, color from heartbeat age: green <60s, yellow 60s-5m, red >5m)
2. Operational state pill (text + color from `Workers.Status`: Online green, Draining amber, Offline gray)

The connectivity indicator answers "can I reach this worker?". The operational state pill answers "should this worker be picking up jobs?". These are independent and both useful.

**Look first:** Templates/Activity.html worker-tag rendering, the API endpoint that feeds it (likely under `Features/TeamStatus/` or `Features/ServiceControl/`), and `Workers` schema (Status + LastHeartbeat already exist, no schema change needed).

**Fix with:** `/n` (template + API change, ~30 min)

---

### [TECH DEBT] Loud-failure sweep -- Phase 2
**Date:** 2026-05-08
**Affects:** Models/CommandBuilder.py, WebService/Main.py, WorkerService/Main.py, Repositories/DatabaseManager.py, Features/Profiles/, Features/FileScanning/, Features/TranscodeQueue/, Services/FFmpegAnalysisService.py, Features/MediaProbe/, Features/FileReplacement/

Phase 1 (commit 6bf51b2) addressed the four highest-risk silent swallows that hid today's Windows-worker FFmpegPath bug. Three parallel agent audits (silent-failure code patterns, recent DB Logs over 48h, FFmpeg path resolution chain) surfaced ~30 more sites and several systemic blind spots that need a follow-up pass. Documented here so the next session can pick it up cleanly.

**Remaining silent-swallow sites (high-risk, code path):**
- `Models/CommandBuilder.py:190-192, 215-217, 226-228, 359-361` -- `AddCodecParameters` / `BuildAudioFilters` silently drop codec/audio params on exception. Produces wrong-quality transcodes that are hard to diagnose.
- `Models/CommandBuilder.py:284-285` -- `ExtractResolutionFromFilename` returns None silently. Affects output naming.
- `Repositories/DatabaseManager.py:258-259, 503-504, 5083-5084` -- DeleteProfile / DeleteRootFolder / RecordProblemFile getsize. Destructive op failures masked as "no rows affected".
- `Features/FileScanning/FileScanningRepository.py:80-81` and `Features/Profiles/ProfileRepository.py:121-122` -- duplicate of the above in vertical-slice copies.
- `Features/TranscodeQueue/QueueManagementBusinessService.py:478-479` -- silent skip of show-override lookup; file gets wrong target resolution.
- `Features/MediaProbe/MediaProbeBusinessService.py:134-135` -- `_DeriveResolutionCategory` returns None silently; NULL `ResolutionCategory` leaks into queue logic.
- `Features/TranscodeJob/VideoTranscodingService.py:406-408` -- progress parser swallow, "not critical" comment.
- `Features/TranscodeJob/ProcessTranscodeQueueService.py:1660-1661` -- `_ExtractResolutionFromFilename` swallow.

**Worker lifecycle silent swallows:**
- `WorkerService/Main.py:251-252` -- scan interval setting parse error silent (falls back to 60min).
- `WorkerService/Main.py:488-489` -- drain mode silently swallows QualityTestService.Stop() failure; drain may never actually stop.
- `WorkerService/Main.py:623-626, 638-639` -- shutdown handler swallows FFmpeg-kill and UpdateWorkerStatus(Offline) failures. Worker can stay marked Online after crash exit; FFmpeg children can be leaked.
- `WorkerService/Main.py:646-647, 687-688` -- DB-pool-close / LogError fallback swallows; masks LoggingService problems.

**WebService stdout-vanishing pattern:**
- `WebService/Main.py:153, 340, 353, 362, 389, 420, 433, 446, 454, 473` -- 10 occurrences of `except: print(...)` in service-status / polling loops. When WebService is launched detached by `StartMediaVortex.py`, stdout has no consumer and the messages are lost forever. Convert all to `LoggingService.LogException`.
- `TranscodeService/config.py:110` -- same pattern (TranscodeService is being deprecated -- delete with the dir per the other tech-debt entry above).

**Systemic blind spots from the DB-log audit (48h window):**
- **439 hits** of `GetFFmpegPathFromSettings: "FFmpeg path from settings not found"` -- ERROR-level, no `ExceptionType`. Three distinct paths recur (`/opt/mediavortex/FFmpeg`, `/opt/mediavortex/MediaVortex/...`, `C:\Code\MediaVortex\...`). The function probes/falls back without surfacing the failure. Caller is silently degraded.
- **271+ hits** of `DatabaseManager: "Path does not exist, cannot normalize"` -- WARNING. Likely the dead-file pattern from `PrivateNormalizePathToFilesystemCase` running on stale MediaFiles rows. Phase 1's pre-flight check stops new occurrences from creating attempt rows but doesn't sweep the existing stale rows. Need a one-shot script that flags `MediaFiles` where the path doesn't exist on disk for any worker that can reach it.
- **121 hits** of `_ProcessCompleteFileReplacement: "Failed to update MediaFiles table: Failed to extract metadata"` -- WARNING. Two layers of "Failed to" with no underlying cause. The `ntpath.dirname` fix (commit f5021d2) addresses new occurrences but the wrapper still strips the original exception. Strip the wrapper, log the original.
- **80+ hits** of `AnalyzeMediaFile: "FFprobe failed for ..."` -- ERROR with no `ExceptionType` and no `StackTrace`. Caller logs only the path, not the FFprobe stderr. Capture stderr into ExceptionMessage so we can see *why* FFprobe failed.
- **3 occurrences** of `/bin/sh: 1: C:CodeAutomationMediaVortexFFm...` -- Linux Larry workers tried to execute a Windows-flavored path with backslashes shell-stripped. The path purge in commit 87aaf58 removed the source string, but find the call site that constructed it; some code is still concatenating Windows paths on Linux callers.

**Recommended order when picking this up:**
1. Sweep `WebService/Main.py` `except: print(...)` -> `LogException`. Mechanical, low-risk, big visibility win.
2. Fix the 4 `CommandBuilder.AddCodecParameters/BuildAudioFilters` silent swallows -- highest-risk because they corrupt transcode quality.
3. Strip the "Failed to update MediaFiles table:" wrapper in `_ProcessCompleteFileReplacement` so the original exception surfaces.
4. Capture FFprobe stderr in `AnalyzeMediaFile` exception-path log.
5. One-shot `Scripts/FlagMissingMediaFiles.py` to mark all existing MediaFiles where the path is unreadable from any registered worker.
6. Then the lifecycle / DB-delete swallows.

**Fix with:** `/n` (multi-feature sweep, ~2-3 hours)

---

### [BUG] Workers attempt jobs for MediaFiles entries whose source file no longer exists on disk
**Date:** 2026-05-08
**Affects:** TranscodeJob feature (ProcessTranscodeQueueService, FFprobe build step), TranscodeQueue feature (queue population)
**Criterion violated:** Worker should refuse to claim a job whose source path is unreadable. The pipeline must distinguish "file gone -- mark MediaFile missing, drop from queue, do not retry" from "file unreadable transiently -- retry."

Observed: Bachelor in Paradise S10E01 was successfully transcoded earlier today, but file replacement lost both the original (`T:\Bachelor in Paradise\Season 10\Bachelor in Paradise - S10E01 - Week 1 HDTV-720p.mkv`) and the new file. MediaFiles row 41437 still has the original FilePath, hevc codec, and TranscodedByMediaVortex=NULL. Queue items for it keep being created (Id 76218 most recent). Worker claims the queue item, calls FFprobe to build the command, FFprobe fails with "No such file or directory", attempt fails, and the queue item is removed -- but a new one will appear on the next queue population because the MediaFiles row is unchanged. No pre-flight check verifies the source file exists before claiming/probing/building.

**Look first:**
- `Features/TranscodeJob/ProcessTranscodeQueueService.py` -- ProcessJob entry, where to add `os.path.exists(LocalSourcePath)` check after `SetupFilePreparation` returns the InPlace path. Failing here should set MediaFiles.LastFFprobeError = "Source file missing" + LastFFprobeAttemptDate, optionally bump FFprobeFailureCount, and DELETE the queue item without creating a TranscodeAttempt row.
- Queue-population caller (likely `Features/TranscodeQueue/QueueManagementBusinessService.py`) -- should skip MediaFiles where FFprobeFailureCount >= 3 (existing safety guard per CLAUDE.md). Verify it actually does for the "missing file" case.
- `Features/FileReplacement/FileReplacementBusinessService.py` -- the move-then-update sequence that lost Bachelor S10E01 in the first place. Need atomic semantics so a failed re-probe does not leave the original deleted and the new file in an unknown state.

**Fix with:** `/t` -- single-feature work, scope is clear

---

### [TECH DEBT] Remove legacy TranscodeService/ and QualityTestService/ directories
**Date:** 2026-05-08
**Affects:** TranscodeService/, QualityTestService/, Features/ServiceControl/ServiceLifecycleManager.py, Scripts/StopAllTranscodeServices.py, CLAUDE.md, transcode.flow.md

Phase 2 of the architecture redesign unified both services into WorkerService. The directories still exist but nothing imports them as Python modules (zero hard dependencies). They are dead code reachable only via Scripts/StopAllTranscodeServices.py and the SERVICES dict in ServiceLifecycleManager.py. The string identifiers "TranscodeService" / "QualityTestService" remain valid as logical job-type tags in ActiveJobs.ServiceName, ServiceStatus.ServiceName, and CrashRecoveryService — those must NOT be removed.

**Look first:** `TranscodeService/` and `QualityTestService/` directory contents, `Features/ServiceControl/ServiceLifecycleManager.py:29-40` (drop the two SERVICES dict entries), `Scripts/StopAllTranscodeServices.py` (delete or repoint), CLAUDE.md "Two Microservices" section.

**Fix with:** `/n` (cleanup migration -- estimated 30 min: delete two dirs, prune SERVICES dict, sweep docs, leave string literals alone)

### [TECH DEBT] LocalStaging fallback decision duplicated across four sites
**Date:** 2026-05-08
**Affects:** Features/TranscodeJob/ProcessTranscodeQueueService.py

`ProcessJob`, `ProcessRemuxJob`, `ProcessSubtitleFixJob`, and `SetupFilePreparation` each independently decide whether LocalStaging mode falls back to InPlace when the worker has no StagingDirectory configured. The first three fix used a local variable that didn't propagate; the fourth re-read the system setting and silently kept building staging paths. Today's fix added the same guard to `SetupFilePreparation` so the four sites agree, but a future change to the fallback logic still has to be made in four places.

**Look first:** `Features/TranscodeJob/ProcessTranscodeQueueService.py:384-390, 526-530, 642-646, 828-836` -- four places computing `IsLocalStaging`. Extract `_GetEffectiveFileMode()` returning the resolved mode after applying the fallback.

**Fix with:** `/t` (single-file refactor)

### [BUG] Second concurrent job shows first job's progress
**Date:** 2025-05-05
**Affects:** TranscodeJob feature -- concurrent job progress tracking
**Criterion violated:** TranscodeJob.feature.md -- each running job must report independent progress

When MaxConcurrentJobs > 1 and a second job starts while the first is still running, the second job displays the same progress percentage and ETA as the first (e.g., both show 20.5% / ETA 01:41:41). Only one FFmpeg process is actually running.

**Look first:** `Features/TranscodeJob/ProcessTranscodeQueueService.py:169` (`GetStatus` returns single `currentProgress`), `GetCurrentTranscodeProgress()` in DatabaseManager (likely returns one row, not per-job), and `VideoTranscodingService.TranscodeVideo` (process spawning).

**Fix with:** `/t`

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

TranscodeJob.feature.md declares scope `Features/TranscodeJob/**` + `WorkerService/Main.py`, but its criteria govern behavior in CommandBuilderService (conditional yadif, output mode), FFmpegAnalysisService (per-worker FFprobe), PathTranslationService (multi-prefix translation), and ProcessTranscodeQueueService (VMAF toggle, worker config loading). Separately, FileReplacement depends on MediaProbe for re-probing with no explicit contract.

**Look first:** TranscodeJob.feature.md criteria list -- each criterion that references a file outside the declared scope. `Features/FileReplacement/FileReplacementBusinessService.py` for the MediaProbe call.

**Fix with:** `/n` (architectural boundary redesign -- either expand TranscodeJob scope or extract worker/command-building into separate feature verticals)

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

**Migration in progress (Phase 3 of architecture redesign):**
- [x] MediaFileId BIGINT columns + indexes added to 5 child tables (AddMediaFileIdColumns.py)
- [x] Backfill completed: 1,952 rows linked, 6,867 orphans (old history with deleted files)
- [x] All JOINs and INSERTs updated in code to use MediaFileId
- [x] FK constraints added (AddMediaFileForeignKeys.py) -- TranscodeFiles/TranscodeAttempts ON DELETE SET NULL, TranscodeQueue/CompliantFiles/ProblemFiles ON DELETE CASCADE
- [x] All WHERE/JOIN reads switched from FilePath to MediaFileId (Phase 3b Step 1)
- [x] FilePath removed from INSERT/UPDATE statements for TranscodeAttempts, TranscodeFiles, ProblemFiles (Phase 3b Step 2)
- [x] NOT NULL constraint dropped from FilePath on TranscodeAttempts, TranscodeFiles, ProblemFiles (was blocking INSERTs)
- [x] Deploy verification -- workers Online and heartbeating (root cause: CrashRecoveryService killed itself because Python is PID 1 in Docker and the recorded ProcessId from a prior crash matched the new container's own PID; also bumped postgres max_connections 30->200 and added pool closeall() before os._exit() to stop connection-leak death spiral)
- [ ] Run RenameFilePathColumns.py to soft-rename columns (Phase 3b Step 4)
- [ ] Drop FilePath_Deprecated columns (Phase 4 -- point of no return)

---

## Fixed

### [FIXED] Services resolve tool paths from SystemSettings instead of per-worker config
**Date:** 2026-05-08 | **Fixed:** 2026-05-08
**Fix:** WorkerContext singleton. FFmpegService resolves: explicit arg > WorkerContext > cached > SystemSettings. FileReplacementBusinessService auto-reads PathTranslation from WorkerContext.

### [FIXED] LocalStaging mode crashes workers without StagingDirectory configured
**Date:** 2026-05-07 | **Fixed:** 2026-05-07
**Fix:** All three job types validate `self.OutputDirectory` before entering LocalStaging mode. NULL falls back to InPlace.

### [FIXED] Post-transcode pipeline does not complete (VMAF + file replacement not firing)
**Date:** 2026-05-07 | **Fixed:** 2026-05-07
**Fix:** Removed dead ShouldTestFile(). ProcessTranscodedFile() reads QualityTestRequired from TranscodeAttempt. FileReplacementBusinessService accepts PathTranslation, translates canonical paths before filesystem ops.

### [FIXED] Concurrent job progress invisible in UI
**Date:** 2026-05-08 | **Fixed:** 2026-05-08
**Fix:** Removed `INNER JOIN TranscodeQueue` from progress queries. Progress now uses `TranscodeProgress + TranscodeAttempts WHERE Success IS NULL`.
**Note:** Queue rows for concurrent jobs still disappear (cause unknown). Audit trigger `trg_transcodequeue_delete` is in place.

### [FIXED] Yadif deinterlacing applied to progressive files
**Date:** 2026-05-05 | **Fixed:** 2026-05-05
**Fix:** Set YadifMode=NULL, YadifParity=NULL on all profiles. CommandBuilder skips yadif when NULL.

### [FIXED] StuckJobDetector breaks distributed transcoding
**Date:** 2026-05-05 | **Fixed:** 2026-05-05
**Fix:** All destructive operations scoped by WorkerName/ClaimedBy. GetActiveJobsByService includes WorkerName. SignalHandler, CrashRecoveryService, QueueManagementService all filter by worker.

### [FIXED] Thread-limiting changes degraded worker transcode performance
**Date:** 2026-05-07 | **Fixed:** 2026-05-07
**Fix:** Reverted `lp=N`, `MEDIAVORTEX_MAX_CPU_THREADS`, Docker `cpus` limit. SVT-AV1 `lp` does not reduce OS thread count; Docker CFS throttling is counterproductive with many idle threads.
**Remaining:** 4 workers at 480p preset 6 still only use ~10% of a 64-CPU system (480p frame size limits SVT-AV1 parallelism -- separate investigation).

### [FIXED] FFmpegService.py cpu_affinity overrides Docker cpuset pinning
**Date:** 2026-05-07 | **Fixed:** 2026-05-07
**Fix:** FFmpegService.py and VideoTranscodingService.py skip affinity calls when `/.dockerenv` exists. Docker cpuset is the sole CPU isolation mechanism in containers.

### [FIXED] QueryDatabase.py sql command silently rolls back writes
**Date:** 2026-05-05 | **Fixed:** 2026-05-05
**Fix:** Added `--commit` flag. Default unchanged (rollback for safety).
