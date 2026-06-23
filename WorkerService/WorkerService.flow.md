# Flow: WorkerService -- Unified Worker Lifecycle

**Slug:** workerservice

## Entry Point

`WorkerService/Main.py` -- single process that handles transcoding, VMAF quality testing, and file scanning based on per-worker capability flags in the Workers table.

Replaces the former `TranscodeService/Main.py` + `QualityTestService/Main.py` dual-process model.

## Startup Pipeline

| ID | Function | What It Does |
|---|----------|--------------|
| ST0 | `_VerifyRequiredPaths()` (Windows-only path verification) | Reads distinct drive-letter prefixes from MediaFiles, verifies each is accessible via `os.path.exists()`. Hard-fails before any DB writes if a required drive isn't mounted. Linux containers skip this step (per-worker mount validation in ST7a handles them). |
| ST1 | `WorkerServiceApp.__init__()` (identity) | `WorkerName = socket.gethostname()`, `WorkerPlatform = platform.system().lower()` |
| ST2 | `_RegisterAndLoadWorkerConfig()` (register worker) | Resolves FFmpeg/FFprobe via `_ResolveBundledOrPathBinary()` (project-bundled `FFmpegMaster/bin/<binary>{.exe?}` first, then `shutil.which`). Raises `RuntimeError` if neither resolves. UPSERTs Workers row (WorkerName, Platform, FFmpegPath, FFprobePath, Status=Online). Parses `MEDIAVORTEX_SHARE_MAPPINGS` env var and UPSERTs into WorkerShareMappings. Loads config (MaxConcurrentJobs, share mappings). |
| ST3 | `WorkerContext.Initialize()` | Singleton stores FFmpegPath, FFprobePath, ShareMappings. All services in the process resolve tool paths from WorkerContext. |
| ST4 | `_EnsureServiceStatusExists()` (service status) | Ensures a ServiceStatus row exists for "WorkerService" |
| ST5 | `_RecoverFromCrash()` (crash recovery) | CrashRecoveryService resets orphaned Running/Processing jobs for this worker |
| ST6 | `_DetectAndCleanStuckJobs()` (stuck job cleanup) | StuckJobDetectionService cleans stuck transcode and quality test jobs |
| ST7 | `_LoadCapabilitiesFromDB()` (load capabilities) | Reads TranscodeEnabled, QualityTestEnabled, ScanEnabled, Status from Workers row |
| ST7a | `_ValidateStorageMounts()` + `_ApplyMountValidationResult()` (mount validation) | Cross-platform. For each `StorageRootResolutions` row for this worker, checks the `AbsolutePath` is a directory, readable, and non-empty. Empty = local filesystem showing through where a share should be mounted. On failure: writes a single-line summary to `Workers.MountValidationError`, forces `Workers.Status='Paused'`, logs ERROR per mount, and capabilities never start. On success: clears `MountValidationError`. Re-runs on every Paused -> Online transition in `_HandleStatusChange()`. |
| ST8 | `DatabaseManager.UpdateWorkerStatus()` (mark Online) | Sets Workers.Status = 'Online' only if mount validation passed |
| ST9 | `_StartHealthMonitoring()` (start health monitor) | Thread: updates Workers.LastHeartbeat every 30s |
| ST10 | `_StartStatusPolling()` (start status polling) | Thread: reads Workers.Status every 5s, calls `_HandleStatusChange()` on transitions |
| ST11 | `_StartCapabilityPolling()` (start capability polling) | Thread: reads capability flags and concurrency columns every N seconds (default 15, configurable via `SystemSettings.CapabilityPollingIntervalSec`), calls `_ApplyCapabilities()` on flag changes, `_ApplyConcurrencyChanges()` on concurrency changes |
| ST12 | `_ApplyCapabilities()` (apply capabilities) | Starts/stops TranscodeService, QualityTestService, ContinuousScanService based on flags |
| ST13 | `_MainLoop()` (main loop) | Blocks on ShutdownEvent, checking every 10s |
| ST14 | `WorkerStateReporter.Transition()` (runtime state) | The SRP writer for the worker-authored truth columns on `Workers`: `RuntimeState`, `CurrentAttemptId`, `LastRuntimeStateUpdate`. Called at every lifecycle transition: Initializing -> Idle -> ClaimingJob -> Encoding -> Idle (success) or Faulted (error); plus every health-monitor tick to refresh `LastRuntimeStateUpdate`. WebService never writes these columns. |

## Seams

| ID | Transition | Producer (writer) | Wire shape | Consumer (reader) expects | Verification |
|---|---|---|---|---|---|
| S1 | `ST2` worker registration | `_RegisterAndLoadWorkerConfig()` | `Workers.(WorkerName TEXT PK, Platform TEXT, FFmpegPath TEXT NOT NULL, FFprobePath TEXT NOT NULL, Status, Version, BuildInfo)` UPSERT | `WorkerContext` + all downstream service constructors read from Workers row | `SELECT FFmpegPath, FFprobePath, Version FROM Workers WHERE WorkerName=<host>` -- non-NULL after a clean start |
| S2 | `ST2` share mappings | Env var `MEDIAVORTEX_SHARE_MAPPINGS` parsed -> UPSERT into `WorkerShareMappings` + `StorageRootResolutions` | `StorageRootResolutions.(StorageRootId, WorkerName, Platform, AbsolutePath, IsActive=TRUE)` | `Core.PathStorage.Resolve` (`path-storage.flow.md::S1`) reads these rows | `SELECT AbsolutePath FROM StorageRootResolutions WHERE WorkerName=<host>` returns one row per mounted root |
| S3 | `ST7a` mount validation | `_ValidateStorageMounts()` | `Workers.(MountValidationError TEXT NULL, Status='Paused' on failure)` | `_HandleStatusChange` blocks Paused -> Online unless `MountValidationError IS NULL` | `SELECT Status, MountValidationError FROM Workers WHERE WorkerName=<host>` -- both reflect the latest validation result |
| S4 | `ST9` heartbeat | `_StartHealthMonitoring` thread | `Workers.LastHeartbeat=NOW()` every 30s | `teamstatus.flow.md::S2` consumer + `stuck-job-detection.flow.md::ST3` Tier 1 | `SELECT NOW() - LastHeartbeat FROM Workers WHERE WorkerName=<host>` < 60s |
| S5 | `ST10` status polling | `_StartStatusPolling` thread reads | `Workers.Status` column | `_HandleStatusChange` triggers `_StopAllCapabilities` (Paused) / `_ApplyCapabilities` (Online) | UPDATE `Workers.Status='Paused'`; observe `_StopAllCapabilities` log within 5s |
| S6 | `ST11` capability polling | `_StartCapabilityPolling` thread reads | `Workers.(TranscodeEnabled, QualityTestEnabled, ScanEnabled, RemuxEnabled, MaxConcurrent*Jobs)` | `_ApplyCapabilities` + `_ApplyConcurrencyChanges` start/stop services and rebind pool size | UPDATE `Workers.TranscodeEnabled=FALSE`; observe `_StopTranscodeCapability` within `CapabilityPollingIntervalSec` |
| S7 | `ST12` queue producers/consumers | Services started here drive the seams in `transcode.flow.md::S1` and `remux.flow.md::S1` | per-capability claim queries | Pending rows in `TranscodeQueue` / `QualityTestingQueue` / `RootFolders` are consumed | The cross-flow verifications listed in those seams |
| S8 | `ST14` worker-authored truth columns | `WorkerStateReporter.Transition()` -- the only writer | `Workers.(RuntimeState TEXT, CurrentAttemptId BIGINT NULL, LastRuntimeStateUpdate TIMESTAMP)` UPDATE | `AdminWorkersRepository.GetTiles` reads + derives `IntentDiverges` flag against `Workers.Status`; `/Admin/Workers` Truth badge renders the RuntimeState | `grep -rn 'UPDATE Workers SET .*RuntimeState\|CurrentAttemptId\|LastRuntimeStateUpdate' Features/ WebService/` returns 0 matches; `Tests/Contract/TestWorkerRuntimeStateAuthorship.py` |

## Version

Each worker stamps `Workers.Version` (and `BuildInfo` when available) at registration so the operator can see what code each worker is running from the Activity page. Resolver (`WorkerService/Main.py::_ResolveWorkerVersion`):

1. Read `<repo>/VERSION` (and `<repo>/BUILD_INFO` when present) -- written by the deploy event for this worker.
2. Return the literal `"unknown"` when the file is missing or empty.

The worker never resolves the version live (no `git rev-parse HEAD`, no environment lookup), so the displayed value cannot drift past the code the process actually loaded at startup.

**Who writes `VERSION` + `BUILD_INFO`:**
- **Linux (Docker):** `deploy/deploy-linux-worker.py` passes `--build-arg COMMIT_SHA=<dev HEAD>`; `deploy/Dockerfile` writes both files into `/opt/mediavortex/` at image build time.
- **Windows native:** `deploy/deploy-windows-worker.py` step 5 (`StepStampVersion`) writes both files to `C:\Code\MediaVortex\` on the target via SSH/PowerShell. `StartWorker.py` also runs `Scripts/StampVersion.py` at every launch as belt-and-suspenders, so an operator restart picks up the local HEAD even without re-running the full deploy.

Both deploy scripts assert, after restart, that `Workers.Version` equals the SHA they just stamped. Mismatch fails the deploy with exit code 3.

The Activity page tile shows the short SHA next to the worker name; the tooltip shows the full SHA + BuildInfo. A fleet-wide mismatch banner (`/api/TeamStatus/Workers/VersionStatus`) appears when two or more enabled workers report different non-unknown versions. See `deploy/version-on-deploy.feature.md` for the current contract; `Features/TeamStatus/worker-versioning.feature.md` documents the original 3-tier shape (tier 2 removed 2026-05-27).

## Per-Worker Status Control

Workers poll their own `Workers.Status` column every 5 seconds:

| Status | Behavior |
|--------|----------|
| Online | All enabled capabilities are running, accepting new jobs |
| Draining | Finish current job, do not claim new work. Stops scan/quality test immediately. Waits for transcode to complete, then auto-transitions to Paused. |
| Paused | All capabilities stopped. Worker still sends heartbeats. |

Liveness (container running vs dead) is derived from heartbeat freshness, not from `Workers.Status`:
- Heartbeat < 60s: alive (green dot)
- Heartbeat 60s-300s: stale (amber dot)
- Heartbeat > 300s or NULL: dead (red dot)

Status changes are applied in `_HandleStatusChange()`:
- Online -> Draining: sets `StopRequested=True` on transcode, spawns drain waiter thread
- Online -> Paused: stops all capabilities immediately
- Draining -> Paused: no-op (drain waiter will auto-transition when job finishes)
- Paused -> Online or Draining -> Online: re-applies capabilities

The UI exposes two buttons per worker: Online and Pause. Clicking Pause on an idle worker writes `Paused` directly. Draining is a transient state the badge shows while current work finishes.

Status is set via:
- `POST /api/TeamStatus/Workers/<name>/Status` (Activity page UI, accepts Online or Paused)
- Direct DB update: `UPDATE Workers SET Status = 'Paused' WHERE WorkerName = 'larry-worker-1'`

On shutdown, `Workers.Status` is NOT changed -- the heartbeat going stale tells the UI the process died. This preserves operator intent across restarts.

## Capability Lifecycle

Each capability (Transcode, QualityTest, Remux, Scan) has Start/Stop methods:

| Capability | Start | Stop | Service Class |
|------------|-------|------|---------------|
| Transcode | `_StartTranscodeCapability()` | `_StopTranscodeCapability()` | `ProcessTranscodeQueueService` |
| QualityTest | `_StartQualityTestCapability()` | `_StopQualityTestCapability()` | `ProcessQualityTestQueueService` |
| Remux | `_StartRemuxCapability()` | `_StopRemuxCapability()` | `ProcessRemuxQueueService` |
| Scan | `_StartScanCapability()` | `_StopScanCapability()` | `ContinuousScanService` |

### Per-Capability Concurrency

Each capability reads its own concurrency column from the Workers table at start time, and the capability polling loop updates it dynamically every 60 seconds:

| Capability | Column | Default | Rationale |
|------------|--------|---------|-----------|
| Transcode | `MaxConcurrentTranscodeJobs` | 1 | CPU-bound (FFmpeg saturates cores) |
| QualityTest | `MaxConcurrentQualityTestJobs` | 2 | I/O-bound (VMAF reads two files) |
| Remux | `MaxConcurrentRemuxJobs` | 2 | I/O-bound (container copy, no re-encode) |

`_LoadCapabilitiesFromDB()` reads all three columns alongside the enabled flags. `_ApplyConcurrencyChanges()` compares old vs new values and directly updates `service.MaxConcurrentJobs` on running service instances. The queue loop checks `len(ActiveJobs) < MaxConcurrentJobs` on every iteration, so the new value takes effect immediately without stopping the service. Range-clamped to 1-5.

### Remux Queue Separation

`ProcessRemuxQueueService` claims only `ProcessingMode='Remux'` rows via `ClaimNextPendingRemuxJob`. `ProcessTranscodeQueueService.ClaimNextPendingTranscodeJob` excludes remux rows (`ProcessingMode IS NULL OR ProcessingMode != 'Remux'`). This allows remux to run at higher concurrency without competing for transcode slots.

Capabilities are created lazily -- only initialized when enabled for the first time. Stop methods wait for the current job to finish (transcode: up to 2 hour timeout).

Capability changes are detected by `_CapabilityPollingLoop()` (interval configurable via `SystemSettings.CapabilityPollingIntervalSec`, default 15s). When a flag changes in the DB, `_ApplyCapabilities()` starts newly-enabled capabilities and stops newly-disabled ones.

Capability flags are set via:
- `POST /api/TeamStatus/Workers/<name>/Capability` -- Activity page UI per-worker toggle controls (added 2026-05-08 alongside the existing Status endpoint). Body: `{"TranscodeEnabled": true}` -- one or more keys per request, mirrors the Status endpoint shape so the operator does not need to think about partial writes.
- Direct DB update: `UPDATE Workers SET ScanEnabled = TRUE WHERE WorkerName = 'I9-2024'` (still works; the API endpoint is just a convenience).

The endpoint validates the column name against the allowlist `{TranscodeEnabled, QualityTestEnabled, ScanEnabled}` (rejecting arbitrary writes), accepts boolean values (true/false/null where null means "use global default" -- only meaningful for QualityTestEnabled), and returns the new row state. The worker's capability poller reads the change within one polling interval (default 15s) without restart.

## Shutdown (SIGTERM/SIGINT)

| Step | Function | What It Does |
|------|----------|--------------|
| 1. Signal received | `SignalHandler()` | Catches SIGTERM (Docker stop) or SIGINT (Ctrl+C) |
| 2. Kill FFmpeg | iterates `VideoTranscoding.ActiveProcesses` | `proc.kill()` for each active FFmpeg subprocess |
| 3. Update DB | `UpdateServiceStatus()` + `UpdateWorkerStatus()` | Sets ServiceStatus=Stopped, Workers.Status=Offline |
| 4. Release DB pool | `DatabaseService._pool.closeall()` | Closes all idle psycopg2 connections so they don't linger after `os._exit` bypasses atexit. Required to prevent connection leaks during crash-restart loops. |
| 5. Exit | `os._exit(0)` | Immediate process termination |

Queue items left in Running state by this worker are reset to Pending on next startup by crash recovery.

## Crash Recovery (PID 1 self-kill guard)

`Features/ServiceControl/CrashRecoveryService.RecoverServiceJobs()` walks ActiveJobs left over from a prior run and tries to kill any still-running OS process referenced by `ActiveJobs.ProcessId`. In Docker, every Python entrypoint is PID 1 -- so a naive recorded-PID match always finds the new container's own process. Pre-2026-05-08 the worker would SIGTERM itself during recovery, exit cleanly via SignalHandler, and Docker's `restart: unless-stopped` would loop forever.

The guard:

```python
own_pid = os.getpid()
if process_id and process_id == own_pid:
    process_exists = False  # treat as stale, skip kill, just clean up DB rows
```

## Environment Variables

| Variable | Default | Purpose |
|----------|---------|---------|
| `MEDIAVORTEX_DB_HOST` | localhost | PostgreSQL host |
| `MEDIAVORTEX_DB_PORT` | 5432 | PostgreSQL port |
| `MEDIAVORTEX_DB_NAME` | mediavortex | Database name |
| `MEDIAVORTEX_DB_USER` | mediavortex | Database user |
| `MEDIAVORTEX_DB_PASSWORD` | mediavortex | Database password |
| `MEDIAVORTEX_SHARE_MAPPINGS` | (none) | Drive letter to local mount path mappings (e.g. `T=/mnt/media_tv/,M=/mnt/movies/`) |
| `MEDIAVORTEX_MAX_CPU_THREADS` | (none) | Override MaxCpuThreads for FFmpeg -threads |

## Failure Modes

| Failure | Symptom | Resolution |
|---------|---------|------------|
| Workers row missing | Defaults to TranscodeEnabled=True, all others False | Worker auto-creates its row on startup via RegisterWorker |
| DB unreachable during polling | Exception logged, retry on next poll interval | Check PostgreSQL connectivity |
| Capability start fails | Exception logged, capability stays None | Check service dependencies (e.g. ProcessTranscodeQueueService import) |
| Drain timeout (>2 hours) | Thread join times out, transcode service object orphaned | Worker will clean up on next startup via crash recovery |
| Multiple workers claim same job | Prevented by `SELECT FOR UPDATE SKIP LOCKED` in ClaimNextPendingTranscodeJob |
| Storage mount missing / empty / unreadable | Worker stays Paused; `Workers.MountValidationError` set; capabilities never start; zero jobs claimed | Fix the host mount (e.g. NFS share remount), then resume the worker via Activity page or `UPDATE Workers SET Status='Online'`. The Paused → Online transition re-runs validation. |
| No `StorageRootResolutions` rows for this worker | Treated as broken mount; worker stays Paused | Re-register via `MEDIAVORTEX_SHARE_MAPPINGS` env var (Linux) or `RegisterStorageRootResolutionsFromCanonical` (Windows) and restart |
