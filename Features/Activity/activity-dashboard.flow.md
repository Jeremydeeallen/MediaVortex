# Flow: Activity Dashboard

**Slug:** activity-dashboard

## Entry Point

`GET /Activity` -- page poll fires every 5s. The page issues 1 primary fetch: `/api/Activity/Snapshot`. Snapshot is the source of truth for Active Jobs + Active Scans + queue counts + badge state. Worker tiles + library compliance are owned by their own admin pages (`/Admin/Workers`, `/Admin/Compliance`).

## Stages

| ID | Stage | Code | What it does |
|---|---|---|---|
| ST1 | Page poll | `Templates/Activity.html:LoadActivity` | Fires `/api/Activity/Snapshot`; renders Active Jobs + Active Scans tables; updates queue-counts strip. |
| ST2 | Snapshot assembly | `DashboardSnapshotService.BuildSnapshot` | Reads `StaleProgressThresholdSec` fresh from SystemSettings, then calls `_BuildActiveJobs / _BuildActiveScans / _BuildQueueCounts / _BuildBadgeState` in a single in-process pass. |
| ST3 | Active jobs | `_BuildActiveJobs` | `ActiveJobs LEFT JOIN TranscodeQueue + TranscodeAttempts + TranscodeProgress on QueueId/AttemptId; WHERE Success IS NULL`. Each row gets smoothed Speed/ETA via `ProgressSmoothingService`. Per-row enrichment: TargetResolution / CodecChange / EstimatedSavings. |
| ST4 | Active scans | `_BuildActiveScans` | `SELECT FROM ScanJobs WHERE Status IN ('Running')`. Joins ScanProgress for phase + processed/total file counts. |
| ST5 | Smoothing | `ProgressSmoothingService.SmoothForAttempt` | Rolling 10-sample / 30s window arithmetic mean of CurrentSpeed for the attempt. Returns `(None, None)` if newest sample older than `StaleSec`. ETA computed as `(TotalFrames - CurrentFrame) / SmoothedSpeed`. |
| ST6 | Badge state | `_BuildBadgeState` | ActiveJob count + `FailedJobsRepository.CountCapped()` + queue counts per ProcessingMode. |

## Seams

| ID | Transition | Producer | Wire shape | Consumer expects | Verification |
|---|---|---|---|---|---|
| S1 | `ST1 -> ST2` (page -> server) | `GET /api/Activity/Snapshot` | JSON envelope `{Success, Data:{ActiveJobs, ActiveScans, QueueCounts, BadgeState, StaleProgressThresholdSec}}` | Template populates two SharedTables + queue-counts strip | `curl /api/Activity/Snapshot` |
| S2 | `ST3 -> ST5` (per-row) | `_BuildActiveJobs` loop | `(AttemptId: int)` | Smoother queries TranscodeProgress for samples within 30s window | `TestProgressSmoothingService` |
| S3 | `ST5 -> ST1` (smoothed -> rendered) | `ActiveJobRow.SmoothedSpeed / EtaSeconds` | `Optional[float] / Optional[int]` | Renderer falls back to `--` when smoothed is None | Live page render |
| S4 | `ST3 cross-table read` (TargetResolution / CodecChange / Savings) | `_EnrichActiveJob` | `(TargetResolution: str, CodecChange: str, EstimatedSavings: int_bytes_or_None)` | Renderer formats each cell | `TestActiveJobsInterestingColumns.py` |
| S5 | `ST6 cross-cluster` (Cluster A read) | `FailedJobsRepository.CountCapped` | `int` | Snapshot's `BadgeState.FailedJobs` carries it | `curl /api/Activity/Snapshot` |
| S6 | `SystemSettings -> snapshot` (state-store) | `_GetIntSetting('StaleProgressThresholdSec')` | TEXT value coerced to int | Threshold operator-tunable; default 15s | `UPDATE SystemSettings SET SettingValue='10' WHERE SettingKey='StaleProgressThresholdSec'` reflects on next poll |

## Failure Modes

| Failure | Symptom | Resolution |
|---|---|---|
| Smoothing service returns None (stale samples) | Speed/ETA cells render `--` instead of last value | By design. Operator can lower `StaleProgressThresholdSec` to be stricter or raise to be lenient. |
| Snapshot endpoint times out / errors | Page renders "no live work" message rather than blank or raw error | C7. |
| ActiveJobs row carries a NULL TargetResolution (profile not assigned) | Cell renders `--` | By design. |

## Code anchors

| Code | Anchor |
|---|---|
| `Features/Activity/Services/DashboardSnapshotService.py:BuildSnapshot` | `# see activity-dashboard.ST2` |
| `Features/Activity/Services/ProgressSmoothingService.py:SmoothForAttempt` | `# see activity-dashboard.ST5` |
| `Features/Activity/ActivityController.py:Snapshot` | `# see activity-dashboard.S1` |
| `Features/Activity/ActivityRepository.py:_EnrichActiveJob` | `# see activity-dashboard.S4` |
| `Templates/Activity.html:LoadActivity` | `# see activity-dashboard.ST1` |
