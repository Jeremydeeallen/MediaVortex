# Flow: WorkerService -- Unified Worker Lifecycle

## Entry Point

`WorkerService/Main.py` -- single process that handles transcoding, VMAF quality testing, and file scanning based on per-worker capability flags in the Workers table.

Replaces the former `TranscodeService/Main.py` + `QualityTestService/Main.py` dual-process model.

## Startup Pipeline

| Step | Function | What It Does |
|------|----------|--------------|
| 0. Path verification (Windows-only) | `_VerifyRequiredPaths()` | Reads distinct drive-letter prefixes from MediaFiles, verifies each is accessible via `os.path.exists()`. Hard-fails before any DB writes if a required drive isn't mounted. Linux containers skip this step (bind mounts are validated by container orchestration). |
| 1. Identity | `WorkerServiceApp.__init__()` | `WorkerName = socket.gethostname()`, `WorkerPlatform = platform.system().lower()` |
| 2. Register worker | `_RegisterAndLoadWorkerConfig()` | Resolves FFmpeg/FFprobe via `_ResolveBundledOrPathBinary()` (project-bundled `FFmpegMaster/bin/<binary>{.exe?}` first, then `shutil.which`). Raises `RuntimeError` if neither resolves -- previously this silently registered NULL on Windows hosts where FFmpeg isn't on PATH. UPSERTs Workers row (WorkerName, Platform, FFmpegPath, FFprobePath, Status=Online). Parses `MEDIAVORTEX_SHARE_MAPPINGS` env var and UPSERTs into WorkerShareMappings. Loads config (StagingDirectory, MaxConcurrentJobs, share mappings). |
| 3. WorkerContext | `WorkerContext.Initialize()` | Singleton stores FFmpegPath, FFprobePath, StagingDirectory, ShareMappings. All services in the process resolve tool paths from WorkerContext. |
| 4. Service status | `_EnsureServiceStatusExists()` | Ensures a ServiceStatus row exists for "WorkerService" |
| 5. Crash recovery | `_RecoverFromCrash()` | CrashRecoveryService resets orphaned Running/Processing jobs for this worker |
| 6. Stuck job cleanup | `_DetectAndCleanStuckJobs()` | StuckJobDetectionService cleans stuck transcode and quality test jobs |
| 7. Load capabilities | `_LoadCapabilitiesFromDB()` | Reads TranscodeEnabled, QualityTestEnabled, ScanEnabled, Status from Workers row |
| 8. Mark Online | `DatabaseManager.UpdateWorkerStatus()` | Sets Workers.Status = 'Online' |
| 9. Start health monitor | `_StartHealthMonitoring()` | Thread: updates Workers.LastHeartbeat every 30s |
| 10. Start status polling | `_StartStatusPolling()` | Thread: reads Workers.Status every 5s, calls `_HandleStatusChange()` on transitions |
| 11. Start capability polling | `_StartCapabilityPolling()` | Thread: reads capability flags and concurrency columns every 60s, calls `_ApplyCapabilities()` on flag changes, `_ApplyConcurrencyChanges()` on concurrency changes |
| 12. Apply capabilities | `_ApplyCapabilities()` | Starts/stops TranscodeService, QualityTestService, ContinuousScanService based on flags |
| 13. Main loop | `_MainLoop()` | Blocks on ShutdownEvent, checking every 10s |

## Per-Worker Status Control

Workers poll their own `Workers.Status` column every 5 seconds:

| Status | Behavior |
|--------|----------|
| Online | All enabled capabilities are running, accepting new jobs |
| Draining | Finish current job, do not claim new work. Stops scan/quality test immediately. Waits for transcode to complete, then cleans up. |
| Offline | All capabilities stopped. Worker still sends heartbeats. |

Status changes are applied in `_HandleStatusChange()`:
- Online -> Draining: sets `StopRequested=True` on transcode, spawns drain waiter thread
- Online -> Offline: stops all capabilities immediately
- Draining -> Offline: no-op (already stopping)
- Offline -> Online or Draining -> Online: re-applies capabilities

Status is set via:
- `POST /api/TeamStatus/Workers/<name>/Status` (Activity page UI)
- Direct DB update: `UPDATE Workers SET Status = 'Draining' WHERE WorkerName = 'larry-worker-1'`

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

Capability changes are detected by `_CapabilityPollingLoop()` (60s interval). When a flag changes in the DB, `_ApplyCapabilities()` starts newly-enabled capabilities and stops newly-disabled ones.

Capability flags are set via:
- `POST /api/TeamStatus/Workers/<name>/Capability` -- Activity page UI per-worker toggle controls (added 2026-05-08 alongside the existing Status endpoint). Body: `{"TranscodeEnabled": true}` -- one or more keys per request, mirrors the Status endpoint shape so the operator does not need to think about partial writes.
- Direct DB update: `UPDATE Workers SET ScanEnabled = TRUE WHERE WorkerName = 'I9-2024'` (still works; the API endpoint is just a convenience).

The endpoint validates the column name against the allowlist `{TranscodeEnabled, QualityTestEnabled, ScanEnabled}` (rejecting arbitrary writes), accepts boolean values (true/false/null where null means "use global default" -- only meaningful for QualityTestEnabled), and returns the new row state. The worker's capability poller reads the change within 60s without restart.

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
