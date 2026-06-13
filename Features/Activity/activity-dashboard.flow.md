# Flow: Activity Dashboard

**Slug:** activity-dashboard

## Entry Point

`GET /Activity` -- page poll fires every 5s. The page issues 3 parallel fetches: `/api/TeamStatus/Overview` (existing), `/api/QualityTesting/Progress` (existing), `/api/Activity/Snapshot` (NEW per activity-dashboard-solid.C1). Snapshot is the source of truth for smoothed FPS/Speed/ETA per `TranscodeAttemptId` AND the badge state (active job count, failed jobs count, QT in-flight count) used by the page header + nav badges.

## Stages

| ID | Stage | Code | What it does |
|---|---|---|---|
| ST1 | Page poll | `Templates/Activity.html:LoadOverview` | Fires the 3 fetches; merges smoothed values per AttemptId; renders. |
| ST2 | Snapshot assembly | `DashboardSnapshotService.BuildSnapshot` | Reads `StaleProgressThresholdSec` + `HeartbeatStaleThresholdSec` fresh from SystemSettings, then calls _BuildWorkers / _BuildActiveJobs / _BuildQueueCounts / _BuildBadgeState in a single in-process pass. |
| ST3 | Worker tiles | `_BuildWorkers` | `SELECT WorkerName, Status, LastHeartbeat, capability flags FROM Workers WHERE Enabled=TRUE`. Derives `HeartbeatAgeSec` from `LastHeartbeat`. Status verbatim. |
| ST4 | Active jobs | `_BuildActiveJobs` | `ActiveJobs LEFT JOIN TranscodeQueue + TranscodeAttempts + TranscodeProgress on QueueId/AttemptId; WHERE Success IS NULL`. Worker.Status NEVER filters (AC3 / BUG-0059). Each row gets smoothed FPS/Speed/ETA via `ProgressSmoothingService`. |
| ST5 | Smoothing | `ProgressSmoothingService.SmoothForAttempt` | Rolling 10-sample / 30s window arithmetic mean of CurrentFPS + CurrentSpeed for the attempt. Returns `(None, None, None)` if newest sample older than `StaleSec`. ETA computed as `(TotalFrames - CurrentFrame) / SmoothedFPS`. |
| ST6 | Badge state | `_BuildBadgeState` | ActiveJob count + `FailedJobsRepository.CountCapped()` + QT in-flight count. Cross-cluster contract: FailedJobs count is owned by Cluster A's repository. |
| ST7 | Render | `RenderActiveJobs` | Prefers `Job.SmoothedFPS / .SmoothedSpeed / .EtaSeconds` over the raw `CurrentFPS` / `CurrentSpeed` / `ETA` when present. Renders `--` for stale rows. |

## Seams

| ID | Transition | Producer | Wire shape | Consumer expects | Verification |
|---|---|---|---|---|---|
| S1 | `ST1 -> ST2` (page -> server) | `GET /api/Activity/Snapshot` | JSON envelope `{Success, Data:{Workers, ActiveJobs, QueueCounts, BadgeState, StaleProgressThresholdSec, HeartbeatStaleThresholdSec}}` | Template merges smoothed values into Overview's ActiveJobs by AttemptId | `curl /api/Activity/Snapshot` |
| S2 | `ST4 -> ST5` (per-row) | `_BuildActiveJobs` loop | `(AttemptId: int)` | Smoother queries TranscodeProgress for samples within 30s window | `TestProgressSmoothingService` |
| S3 | `ST5 -> ST7` (smoothed -> rendered) | `ActiveJobRow.SmoothedFPS / SmoothedSpeed / EtaSeconds` | `Optional[float] / Optional[float] / Optional[int]` | Renderer falls back to raw values when smoothed is None | Live page render |
| S4 | `ST6 cross-cluster` (Cluster A read) | `FailedJobsRepository.CountCapped` | `int` | Snapshot's `BadgeState.FailedJobs` carries it | `curl /api/Activity/Snapshot` |
| S5 | `SystemSettings -> snapshot` (state-store) | `_GetIntSetting('StaleProgressThresholdSec'/'HeartbeatStaleThresholdSec')` | TEXT value coerced to int | Threshold operator-tunable; default 15s / 300s | `UPDATE SystemSettings SET SettingValue='10' WHERE SettingKey='StaleProgressThresholdSec'` reflects on next poll |
| S6 | `Bulk worker status` (wire) | `POST /api/TeamStatus/Workers/BulkStatus` | `{Status, WorkerNames[]} -> {Results:[{WorkerName, Success, Message}], Summary:{OkCount, FailCount}}` | Activity.html bulk buttons fire one request; toast renders per-worker outcome | `curl` smoke |

## Failure Modes

| Failure | Symptom | Resolution |
|---|---|---|
| Smoothing service returns None (stale samples) | FPS/Speed/ETA cells render `--` instead of last value | By design (AC2). Operator can lower `StaleProgressThresholdSec` to be stricter or raise to be lenient. |
| Snapshot endpoint times out / errors | Template falls back to raw `CurrentFPS` from Overview endpoint -- old behavior preserved | Snapshot is additive; no degradation if it errors. |
| Worker.Status carries an unrecognized value (e.g. 'Maintenance') | Badge renders grey + raw string | By design (AC4). Adding to `WorkerStatusMap` upgrades the styling without changing code paths. |
| Bulk endpoint partial failure | Per-worker `Results[]` carries failures; client toast shows "X of N succeeded" | By design (AC9). Operator sees the failure list. |

## Out of Scope

- ETA per-second countdown on the client (AC6 DEFERRED -- root cause fixed by smoothing).
- Capability-toggle inline re-render (AC10 DEFERRED -- snapshot endpoint provides the data; UI hookup is follow-up).
- Per-panel ad-hoc fetches kept alongside Snapshot for backward compat; snapshot is additive, not strictly replacing.

## Code anchors

| Code | Anchor |
|---|---|
| `Features/Activity/Services/DashboardSnapshotService.py:BuildSnapshot` | `# see activity-dashboard.ST2` |
| `Features/Activity/Services/ProgressSmoothingService.py:SmoothForAttempt` | `# see activity-dashboard.ST5` |
| `Features/Activity/ActivityController.py:Snapshot` | `# see activity-dashboard.S1` |
| `Features/TeamStatus/TeamStatusController.py:BulkSetWorkerStatus` | `# see activity-dashboard.S6` |
| `Templates/Activity.html:LoadOverview` | `# see activity-dashboard.ST1` |
