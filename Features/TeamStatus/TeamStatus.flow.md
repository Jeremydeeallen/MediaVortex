# Stats Page Flow

**Slug:** teamstatus

Entry point: `GET /Stats` (renders `Templates/Status.html`)

## Data Sources

| Section | API Endpoint | Data Source |
|---------|-------------|-------------|
| Library Statistics | GET /api/Statistics | MediaFiles aggregate |
| Savings by Day (chart) | GET /api/TeamStatus/SavingsByDay | TranscodeAttempts aggregate |
| System Resources | GET /api/SystemResources | SystemMonitoringService (local psutil) |
| Active Transcode Jobs | GET /api/TeamStatus/Overview | TranscodeProgress + TranscodeQueue + TranscodeAttempts |
| Transcode Savings Summary | GET /api/TeamStatus/Overview | TranscodeAttempts aggregate |
| Savings by Volume | GET /api/TeamStatus/SavingsByVolume | TranscodeAttempts aggregate |
| Continuous Scanning | GET /api/Scan/ContinuousStatus | In-memory scan state |
| Services | GET /api/Status | ServiceStatus table |

## User Flow

| ID | User sees | System does |
|---|-----------|-------------|
| ST1 | Page loads, all sections show "Loading..." | JS calls all 7 API endpoints in parallel |
| ST2 | Library stats populate (file count, size, encoded, saved) | /api/Statistics returns MediaFiles aggregate |
| ST3 | Savings chart renders | /api/TeamStatus/SavingsByDay returns last 30 days |
| ST4 | System resources populate (CPU, temp, memory, disk) | /api/SystemResources returns psutil data from WebService host |
| ST5 | Active Transcode Jobs: table of running jobs with progress bars, FPS, ETA | /api/TeamStatus/Overview joins TranscodeProgress to TranscodeQueue |
| ST6 | Savings summary cards populate | Same /api/TeamStatus/Overview response |
| ST7 | Volume table populates | /api/TeamStatus/SavingsByVolume groups by drive letter |
| ST8 | Continuous scan status populates | /api/Scan/ContinuousStatus |
| ST9 | Services section: cards for each service with status badge | /api/Status reads ServiceStatus table |
| ST10 | Auto-refresh polls every 10s | All APIs re-fetched on timer |

## Seams

| ID | Transition | Producer (writer) | Wire shape | Consumer (reader) expects | Verification |
|---|---|---|---|---|---|
| S1 | `ST5` reads `TranscodeProgress` | `ProcessTranscodeQueueService` heartbeat (`transcode.flow.md::ST6`) | `TranscodeProgress.(TranscodeAttemptId BIGINT UNIQUE, CurrentFPS, AverageFPS, CurrentFrame, LastUpdate TIMESTAMP)` | `/api/TeamStatus/Overview` joins TranscodeProgress to TranscodeQueue active rows | Open `/Stats` -- active job rows show non-zero FPS within seconds of claim |
| S2 | `ST5` reads `Workers.LastHeartbeat` | `WorkerService._StartHealthMonitoring` writes every 30s (`workerservice.flow.md::ST9`) | `Workers.(WorkerName, LastHeartbeat TIMESTAMP NOT NULL, Status TEXT IN ('Online','Paused','Draining'))` | Per-row stuck detection: if `LastHeartbeat > NOW() - INTERVAL '5 min'` for Running job's `ClaimedBy`, mark stuck | `SELECT WorkerName, NOW() - LastHeartbeat FROM Workers` -- < 60s on healthy workers |
| S3 | `ST9` reads `ServiceStatus` | `ServiceStatusTracker` thread | `ServiceStatus.(servicename TEXT, processid BIGINT, status TEXT, lastheartbeat TIMESTAMP)` -- informational only per `capability-control-plane.feature.md` | Status badge color per service | `SELECT servicename, status FROM ServiceStatus` matches the badge state on /Stats |
| S4 | `ST10` auto-refresh cadence | `Templates/Status.html` setInterval | All 7 endpoints re-fetched every 10s | Live UI without manual reload | DevTools Network: every 10s, the 7 endpoints fire again |
| S5 | `ST3 -> server` SQL bucketing seam | `/api/TeamStatus/SavingsByDay` reads `TranscodeAttempts` aggregated by day | `SELECT DATE(CompletedDate AT TIME ZONE 'UTC' AT TIME ZONE %s), SUM(OldSizeBytes - NewSizeBytes) ...` per `display-timezone.flow.md::S4` (server-side day bucketing in operator's TZ) | Chart axis labels use `formatTime(d, 'date')` on the client, also TZ-aware. **Non-obvious:** a TranscodeAttempt completing 23:45 Chicago time = 04:45 UTC next day; with naive `DATE()` it falls into the wrong bucket. The TZ-aware bucketing is load-bearing for the chart matching the operator's wall clock | Operator changes `SystemSettings.DisplayTimezone`, restarts WebService, observes the chart re-buckets and axis labels shift consistently |
| S6 | `ST7` reads `TranscodeAttempts` aggregated by drive prefix | `/api/TeamStatus/SavingsByVolume` runs `GROUP BY SUBSTRING(FilePath, 1, 3)` (or the per-storage-root equivalent post path-storage migration) | Per-drive savings rollup -- relies on `FilePath` shape `T:\...`, `M:\...`, `Z:\...` | Volume table on `/Stats` | **Non-obvious:** after `path-storage.flow.md` Phase 4 read-switch lands, `FilePath` may be NULL for canonical-only rows; the rollup must join through `StorageRoots.Name` to keep working. Drive-letter substring works today; tomorrow it doesn't |
| S7 | `ST5` "Reset Stuck Job" POST | `POST /api/TeamStatus/ResetStuckJob` body `{QueueId}` | Server-side: `UPDATE TranscodeQueue SET Status='Pending', ClaimedBy=NULL, ClaimedAt=NULL, DateStarted=NULL; DELETE FROM ActiveJobs WHERE QueueId=%s AND ServiceName='TranscodeService'` | UI button on stuck job rows | **Non-obvious cross-flow seam:** this duplicates the DB-state cleanup that `stuck-job-detection.flow.md::ST8` performs, but WITHOUT the host-locality kill step. Using Reset on a job whose FFmpeg is actually still alive on a remote worker leaves the orphaned FFmpeg running until the worker's next stuck-detect cycle. **Operator hazard:** Reset is a UI lie when the worker is heartbeating fine and just slow | Trigger Reset on a row; observe TranscodeQueue.Status reverts to Pending AND ActiveJobs row deleted; verify no kill log entry on the remote worker host |
| S8 | `ST9` `psutil` host scope limitation | `SystemMonitoringService` runs on the WebService host process only | `/api/SystemResources` returns CPU%/memory/temperature for the WebService host's `os.getpid()` tree, NOT per-worker | Operator may misread as fleet-wide. **Non-obvious:** I9-2024 hosts both WebService AND a co-located WorkerService, so its CPU% reflects both; larry/wakko/dot worker CPU is INVISIBLE from this endpoint | `curl /api/SystemResources` returns one host's data; cross-check `Get-Process` on each remote worker for actual saturation |

## Failure Modes

| Failure | Current behavior | Expected behavior |
|---------|-----------------|-------------------|
| Worker offline but has Running queue items | Active Jobs shows stale Running jobs indefinitely | Stuck jobs should be detectable and cleanable from the UI |
| Multiple workers transcoding simultaneously | All jobs shown in one flat list, no worker attribution | Each job should show which worker is processing it |
| Remote worker not in ServiceStatus table | Services section shows only local services | Workers section should list all registered workers from Workers table |
| WebService not on same host as worker | System Resources shows WebService host only | Per-worker resources would need a separate monitoring path (out of scope) |
