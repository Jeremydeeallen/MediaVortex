# Flow: WorkerService -- Unified Worker Lifecycle

## Entry Point

`WorkerService/Main.py` -- single process that handles transcoding, VMAF quality testing, and file scanning based on per-worker capability flags in the Workers table.

Replaces the former `TranscodeService/Main.py` + `QualityTestService/Main.py` dual-process model.

## Startup Pipeline

| Step | Function | What It Does |
|------|----------|--------------|
| 1. Identity | `WorkerServiceApp.__init__()` | `WorkerName = socket.gethostname()`, `WorkerPlatform = platform.system().lower()` |
| 2. Register worker | `_RegisterAndLoadWorkerConfig()` | UPSERT into Workers table (WorkerName, Platform, FFmpegPath via `shutil.which`, FFprobePath, Status=Online). Parses `MEDIAVORTEX_SHARE_MAPPINGS` env var and UPSERTs into WorkerShareMappings. Loads config (StagingDirectory, MaxConcurrentJobs, share mappings). |
| 3. WorkerContext | `WorkerContext.Initialize()` | Singleton stores FFmpegPath, FFprobePath, StagingDirectory, ShareMappings. All services in the process resolve tool paths from WorkerContext. |
| 4. Service status | `_EnsureServiceStatusExists()` | Ensures a ServiceStatus row exists for "WorkerService" |
| 5. Crash recovery | `_RecoverFromCrash()` | CrashRecoveryService resets orphaned Running/Processing jobs for this worker |
| 6. Stuck job cleanup | `_DetectAndCleanStuckJobs()` | StuckJobDetectionService cleans stuck transcode and quality test jobs |
| 7. Load capabilities | `_LoadCapabilitiesFromDB()` | Reads TranscodeEnabled, QualityTestEnabled, ScanEnabled, Status from Workers row |
| 8. Mark Online | `DatabaseManager.UpdateWorkerStatus()` | Sets Workers.Status = 'Online' |
| 9. Start health monitor | `_StartHealthMonitoring()` | Thread: updates Workers.LastHeartbeat every 30s |
| 10. Start status polling | `_StartStatusPolling()` | Thread: reads Workers.Status every 5s, calls `_HandleStatusChange()` on transitions |
| 11. Start capability polling | `_StartCapabilityPolling()` | Thread: reads capability flags every 60s, calls `_ApplyCapabilities()` on changes |
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

Each capability (Transcode, QualityTest, Scan) has Start/Stop methods:

| Capability | Start | Stop | Service Class |
|------------|-------|------|---------------|
| Transcode | `_StartTranscodeCapability()` | `_StopTranscodeCapability()` | `ProcessTranscodeQueueService` |
| QualityTest | `_StartQualityTestCapability()` | `_StopQualityTestCapability()` | `ProcessQualityTestQueueService` |
| Scan | `_StartScanCapability()` | `_StopScanCapability()` | `ContinuousScanService` |

Capabilities are created lazily -- only initialized when enabled for the first time. Stop methods wait for the current job to finish (transcode: up to 2 hour timeout).

Capability changes are detected by `_CapabilityPollingLoop()` (60s interval). When a flag changes in the DB, `_ApplyCapabilities()` starts newly-enabled capabilities and stops newly-disabled ones.

## Shutdown (SIGTERM/SIGINT)

| Step | Function | What It Does |
|------|----------|--------------|
| 1. Signal received | `SignalHandler()` | Catches SIGTERM (Docker stop) or SIGINT (Ctrl+C) |
| 2. Kill FFmpeg | iterates `VideoTranscoding.ActiveProcesses` | `proc.kill()` for each active FFmpeg subprocess |
| 3. Update DB | `UpdateServiceStatus()` + `UpdateWorkerStatus()` | Sets ServiceStatus=Stopped, Workers.Status=Offline |
| 4. Exit | `os._exit(0)` | Immediate process termination |

Queue items left in Running state by this worker are reset to Pending on next startup by crash recovery.

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
