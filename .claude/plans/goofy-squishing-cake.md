# MediaVortex Architecture Redesign

## Context

Services resolve FFmpeg/FFprobe paths from SystemSettings (a Windows-relative path) instead of per-worker config, breaking all non-transcode operations on Linux workers. FilePath is used as a natural key across 6 tables (67k+ rows) with no foreign keys. FileScanning is coupled to WebService and can't run on workers. Three separate service entry points (TranscodeService, QualityTestService, WebService) prevent workers from being general-purpose.

This plan fixes all three issues: centralized worker config, unified worker capabilities, and surrogate key normalization.

## Pre-Implementation

**Step 0: Backup.** Commit all current changes (FFprobe path fix, FixStaleMediaFiles.py, KNOWN-ISSUES updates, bug entries). Create a `pre-architecture-redesign` tag. This is the revert point.

## Phase 1: WorkerContext Singleton

Fixes the immediate bug -- services get the right FFprobe/FFmpeg path on any worker automatically.

### Files to create
- `Core/WorkerContext.py` -- process-level singleton storing WorkerName, Platform, FFmpegPath, FFprobePath, StagingDirectory, ShareMappings, PathTranslation. Set once at startup via `Initialize()`, read anywhere via `Current()`. Returns None if not initialized (graceful fallback).

### Files to modify
- `Services/FFmpegService.py:19` -- `__init__` checks `WorkerContext.Current()` before SystemSettings cache before `GetFFprobePathFromSettings()`. Single change fixes all 6 broken instantiation sites.
- `TranscodeService/Main.py:~47` -- call `WorkerContext.Initialize(...)` after `_RegisterAndLoadWorkerConfig()`, before creating ProcessTranscodeQueueService
- `QualityTestService/Main.py:~37` -- add worker identity detection + `WorkerContext.Initialize(...)` after DatabaseManager init
- `WebService/Main.py:~50` -- load worker config from Workers table by hostname, call `WorkerContext.Initialize(...)` before controller init
- `Features/FileReplacement/FileReplacementBusinessService.py:13` -- `__init__` reads PathTranslation from `WorkerContext.Current()` when not provided explicitly (fixes QualityTestingBusinessService gaps at lines 974, 1113)
- `Features/TranscodeJob/ProcessTranscodeQueueService.py:23-70` -- simplify: read from WorkerContext instead of manually extracting from WorkerConfig dict

### Feature doc
- Create `Core/WorkerContext.feature.md`

### Verification
- Deploy to one Linux worker. Transcode a file. Verify MediaFiles updated after replacement (TranscodedByMediaVortex=True, codec=av1).
- Check logs: no "Media analysis service not available" or "FFprobe path from settings not found" errors.

---

## Phase 2: Unified Worker Capabilities

Workers become general-purpose. Each worker can enable/disable: transcoding, VMAF, scanning. Any combination valid. One entry point replaces three.

### Schema migration
- `Scripts/SQLScripts/AddWorkerCapabilities.py` (idempotent)
  - `ALTER TABLE Workers ADD COLUMN IF NOT EXISTS TranscodeEnabled BOOLEAN DEFAULT TRUE`
  - `ALTER TABLE Workers ADD COLUMN IF NOT EXISTS ScanEnabled BOOLEAN DEFAULT FALSE`
  - `QualityTestEnabled` column already exists -- reuse it
  - Backfill: existing workers get TranscodeEnabled=TRUE, ScanEnabled=FALSE

### Files to create
- `WorkerService/Main.py` -- unified entry point. Reads capabilities from Workers table. Starts processing loops for enabled capabilities. Polls Workers table every 60s for capability changes (start/stop processors at runtime).
- `WorkerService/__init__.py`
- `WorkerService/WorkerService.feature.md`
- `WorkerService/WorkerService.flow.md`

### Files to modify
- `WebService/Main.py:84-124` -- remove ContinuousScanService initialization and auto-start. Web service keeps FileScanningController for on-demand API scans only.
- `deploy/Dockerfile:37` -- change ENTRYPOINT from `TranscodeService/Main.py` to `WorkerService/Main.py`
- `deploy/docker-compose.yml` -- update service definition
- `Features/ServiceControl/ServiceLifecycleManager.py:22-41` -- add WorkerService to SERVICES dict
- `StartMediaVortex.py` -- start WebService + WorkerService instead of WebService + TranscodeService

### How scanning works on workers
- When `ScanEnabled=TRUE`, WorkerService starts ContinuousScanService (same code, just runs inside WorkerService instead of WebService)
- PathTranslation from WorkerContext handles T:\ -> /mnt/media_tv/ translation for file existence checks
- FFmpegService reads FFprobe from WorkerContext -- scanning works on Linux
- On-demand scans from UI still go through WebService API -> FileScanningController

### Feature docs to update
- `Features/FileScanning/FileScanning.feature.md` -- scanning as worker capability
- `Features/ServiceControl/ServiceControl.feature.md` -- per-worker capability control
- `deploy/worker-deploy.feature.md` -- WorkerService entry point
- `deploy/worker-deploy.flow.md` -- updated runtime pipeline

### Verification
- Deploy WorkerService on one Linux worker with TranscodeEnabled=TRUE only. Verify transcoding works.
- Enable QualityTestEnabled via DB. Verify VMAF runs.
- Enable ScanEnabled via DB. Verify file scanning discovers files on NFS mount.
- Disable all three. Verify worker goes idle (heartbeat continues, no processing).
- Toggle capabilities via DB while worker is running. Verify it picks up changes within 60s.

---

## Phase 3: Surrogate Key Migration (Clean Break)

Replace filepath natural keys with MediaFiles.Id foreign keys across all child tables.

### Migration scripts (idempotent, run in order)
1. `Scripts/SQLScripts/AddMediaFileIdColumns.py` -- add `MediaFileId BIGINT` + index to: TranscodeFiles, TranscodeAttempts, TranscodeQueue, CompliantFiles, ProblemFiles
2. `Scripts/SQLScripts/BackfillMediaFileIds.py` -- backfill from `JOIN MediaFiles ON LOWER(child.filepath) = LOWER(mf.filepath)`. Report orphans.
3. `Scripts/SQLScripts/AddMediaFileForeignKeys.py` -- add FK constraints after code deploy:
   - TranscodeFiles, TranscodeAttempts: `ON DELETE SET NULL` (preserve history)
   - TranscodeQueue, CompliantFiles, ProblemFiles: `ON DELETE CASCADE`

### Model changes
- `Models/TranscodeAttemptModel.py` -- add MediaFileId field
- `Features/TranscodeQueue/Models/TranscodeQueueModel.py` -- add MediaFileId field
- `Core/Models/TranscodeFileModel.py` -- add MediaFileId field (if exists, else create)

### Code changes (JOINs and INSERTs)
All `JOIN ... ON filepath = filepath` become `JOIN ... ON MediaFileId = Id`. All INSERTs into child tables must include MediaFileId. Key files:

- `Repositories/DatabaseManager.py` -- multiple filepath JOINs (~lines 1630, 2840, 2915, 3350) and INSERTs (~lines 1476, 2004, 2257, 5067)
- `Features/TranscodeJob/TranscodeJobRepository.py` -- JOINs at ~671, 779; INSERTs at ~196, 420
- `Features/TranscodeJob/ProcessTranscodeQueueService.py` -- JOIN at ~1789
- `Features/TranscodeQueue/TranscodeQueueRepository.py` -- INSERT at ~74
- `Features/FileScanning/FileScanningRepository.py` -- JOIN at ~529
- `Features/TeamStatus/TeamStatusController.py` -- JOINs at ~61, 312
- `Scripts/SQLScripts/FixStaleMediaFiles.py` -- JOIN at ~32
- `Scripts/FixFalseTranscodeFlags.py` -- JOIN at ~37

### Deferred (1+ week after code deploy)
- Drop filepath columns from child tables (point of no return)
- Remove `LOWER()` comparisons (no longer needed with integer FK joins)

### Verification
- Run backfill script. Verify 0 NULL MediaFileId rows in each child table (or document orphans).
- Run existing contract tests.
- Verify TranscodeQueue population creates items with MediaFileId.
- Verify transcode completion creates TranscodeAttempts/TranscodeFiles rows with MediaFileId.
- Verify TeamStatus/Stats page loads correctly.
- Spot-check: `SELECT COUNT(*) FROM TranscodeAttempts WHERE MediaFileId IS NULL` = 0 (excluding orphans).

---

## Phase 4: Cleanup (after all phases stable)

- Remove FFmpegPath, FFprobePath, TranscodeFileMode, TranscodeOutputMode, MaxConcurrentJobs from SystemSettings
- Remove FFprobePath threading from Phase 1 partial fix (ShouldQualityTestService, FileReplacementBusinessService constructors) -- WorkerContext makes it redundant
- Deprecate TranscodeService/Main.py and QualityTestService/Main.py
- Drop filepath columns from child tables
- Update KNOWN-ISSUES.md: mark path resolution bug and filepath natural key bug as FIXED

## Rollback Strategy

- **Phase 1**: Remove `WorkerContext.Initialize()` calls from entry points. FFmpegService falls back to SystemSettings. Zero risk.
- **Phase 2**: Revert Dockerfile ENTRYPOINT to `TranscodeService/Main.py`. Old entry points untouched in codebase. Rebuild containers.
- **Phase 3**: MediaFileId columns are nullable and harmless. Revert code to use filepath JOINs. Drop FK constraints if added. No data loss.
- **Nuclear**: Revert to `pre-architecture-redesign` git tag.
