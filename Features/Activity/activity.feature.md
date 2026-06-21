# Activity Dashboard -- live worker / job / scan visibility

**Slug:** activity

## What It Does

Renders the operator's live dashboard at `/Activity`. Aggregates worker tiles, active transcode jobs, active VMAF jobs, active scans, queue counts, and per-failed-job badges into a single 5-second-polled page. Every table on the page uses the SharedTable renderer. Pure consumer -- no transcoding work, no probe work, no policy writes. The vertical's job is "render what the rest of the system is doing, accurately and on time."

This top-level feature doc unifies the page-level contract; the sub-feature docs and flow doc own the specific surface details.

## Workflows

| # | User action | Surface element | Handler | Backing class.method |
|---|---|---|---|---|
| W1 | Open `/Activity` | nav link | `GET /Activity` | `ActivityController` renders `Templates/Activity.html` |
| W2 | View live worker / job snapshot | 5s page poll | `GET /api/Activity/Snapshot` | `DashboardSnapshotService.BuildSnapshot` (see `activity-dashboard.flow.md` ST2-ST7) |
| W3 | View library-compliance card | /Status / /Activity panel | `GET /api/Activity/LibraryCompliance` | `ActivityRepository.GetLibraryCompliance` (includes the AudioVerticalHealth sub-section per `audio-normalization.feature.md` W8) |
| W4 | Filter Active Jobs by worker name | text input above Active Jobs table | client-side only | `Templates/Activity.html` -- see `active-jobs-filter-sort.feature.md` |
| W5 | Sort Active Jobs by column | click column headers | client-side only | `Templates/Activity.html` -- see `active-jobs-filter-sort.feature.md` |
| W6 | Click worker tile action (Online / Drain / Stop) | per-worker action buttons | `POST /api/TeamStatus/Workers/BulkStatus` | (handled by TeamStatus vertical; Activity is the surface only) |
| W7 | Reset stuck transcode job | per-job action button | `POST /api/TeamStatus/ResetStuckJob` | (handled by TeamStatus vertical) |
| W8 | View nav badge counts | persistent nav | 10s nav-badge poll | `Templates/_navbar.html` polls `/api/SQLQueries/GetActiveJobs` |

## Success Criteria

C1. `/Activity` page renders worker tiles, Active Transcode Jobs table, Active Scans table, and QT Progress card on initial load within 2 seconds (subject to `DashboardSnapshotService` response time).

C2. The page polls `/api/Activity/Snapshot` every 5 seconds; new data merges into rendered tables without scroll-position jump or flicker. Verifiable: poll observed at 5 +/-1s intervals in browser dev tools.

C3. `/api/Activity/Snapshot` returns a JSON envelope shaped `{Success: bool, Data: {Workers, ActiveJobs, QueueCounts, BadgeState, StaleProgressThresholdSec, HeartbeatStaleThresholdSec}}`. The four data keys and two threshold keys are stable contract. Verifiable: `curl /api/Activity/Snapshot | jq 'keys'` returns the documented keys.

C4. Every table on the page is rendered by SharedTable (`Static/js/TableRenderer/`). Adding a column is a config change in `Templates/Activity.html`; no edits to the renderer service. Verifiable: `grep -rn "TableRenderer\|ClientArrayDataSource" Templates/Activity.html` confirms instantiation; no hand-rolled `innerHTML` row construction.

C5. Sub-feature contracts: `active-jobs-filter-sort.feature.md` owns the Active Jobs table filter + sort behavior; `activity-dashboard-improvements.feature.md` owns the per-worker badge + lifecycle + dead-button cleanup. This top-level doc OWNS only the page-level shape; it does NOT redefine criteria covered by sub-features.

C6. The snapshot assembly pipeline is documented in `activity-dashboard.flow.md` (ST1-ST7 stages); seams S1-S6 there are the source of truth for cross-stage contracts. This top-level doc DOES NOT restate those seams.

C7. The page degrades gracefully when `/api/Activity/Snapshot` errors or times out: the page falls back to the existing `/api/TeamStatus/Overview` raw data and renders without smoothed FPS/Speed/ETA. No blank screen. Verifiable: temporarily break the snapshot endpoint; page still renders worker tiles + active jobs with raw values.

## Seams

| ID | Seam | Producer | Wire shape | Consumer expects | Verification |
|---|---|---|---|---|---|
| S1 | ActivityController -> page template | `ActivityController.RenderPage` | `Templates/Activity.html` with embedded module script | jQuery polls + SharedTable instances | Live page render |
| S2 | Snapshot endpoint contract | `DashboardSnapshotService.BuildSnapshot` -> `/api/Activity/Snapshot` | `{Workers, ActiveJobs, QueueCounts, BadgeState, StaleProgressThresholdSec, HeartbeatStaleThresholdSec}` | `Templates/Activity.html` `LoadOverview` merges into existing Overview rows by AttemptId | `activity-dashboard.flow.md` S1 (covers full cross-stage contract) |
| S3 | Snapshot -> SharedTable feed | `BuildSnapshot.Data.ActiveJobs[]` | row-shaped JSON | `ClientArrayDataSource.SetRows()` + `Table.Refresh()` | Browser console: tables render rows post-poll |
| S4 | Library Compliance card data | `GET /api/Activity/LibraryCompliance` | `{TotalFiles, CompliantCount, IncompliantCount, ByBucket, AudioVerticalHealth}` | Page section renders per-bucket counts + self-healing sub-section | curl |

(For the cross-stage snapshot-pipeline seams (S1-S6 covering ST1 -> ST7 transitions), see `activity-dashboard.flow.md#seams`. They are not restated here per `doc-layering.md`.)

## Status

ACTIVE. Created 2026-06-20 to fill the ARCHITECTURE.md gap row "Create top-level Activity.feature.md."

## Files

| File | Role |
|---|---|
| `ActivityController.py` | Flask blueprint -- page route + snapshot route + library compliance route |
| `ActivityRepository.py` | Data access for library compliance + per-volume savings + AudioVerticalHealth aggregation |
| `ActivityViewModel.py` | View-model layer for snapshot assembly |
| `Services/DashboardSnapshotService.py` | Snapshot assembly orchestration (see flow ST2) |
| `Services/ProgressSmoothingService.py` | Per-attempt rolling FPS/Speed/ETA smoothing (see flow ST5) |
| `Templates/Activity.html` | Page template + JS rendering via SharedTable |

## See also

- `active-jobs-filter-sort.feature.md` -- Active Jobs table filter + sort behaviors
- `activity-dashboard-improvements.feature.md` -- worker badge + lifecycle + dead-button cleanup
- `activity-dashboard.flow.md` -- snapshot assembly pipeline (ST1-ST7 + S1-S6 seams)

## Cross-Vertical Contract

### Columns the Activity vertical WRITES

| Column | Written by |
|---|---|
| (none) | Activity is a pure consumer; reads everything, writes nothing to MediaFiles |

### Columns the Activity vertical READS from external tables

| Column | Read by | Owner |
|---|---|---|
| Workers.* (Status, LastHeartbeat, capability flags) | _BuildWorkers | Workers data accessor |
| ActiveJobs + TranscodeQueue + TranscodeAttempts + TranscodeProgress | _BuildActiveJobs | TranscodeJob |
| ScanJobs.* | Active scans panel | FileScanning |
| MediaFiles.WorkBucket aggregations | Library compliance card | per-vertical (WorkBucket is GENERATED) |
| SystemSettings.{StaleProgressThresholdSec, HeartbeatStaleThresholdSec} | _GetIntSetting | SystemSettings |

### Stable function entry points

| Class.method | External caller(s) |
|---|---|
| DashboardSnapshotService.BuildSnapshot() -> dict | Activity page poll endpoint |
| ProgressSmoothingService.SmoothForAttempt(AttemptId) -> tuple | Snapshot per-row smoothing |

### HTTP API surface

| Method + URL | Purpose |
|---|---|
| GET /Activity | Render the page |
| GET /api/Activity/Snapshot | Live snapshot (5s poll) |
| GET /api/Activity/LibraryCompliance | Library compliance card |

### What is EXPLICITLY NOT a contract

- Rolling-window size of smoothing (10 samples / 30s) -- tunable
- The per-tile JS rendering (handled by SharedTable; Activity owns the data, SharedTable owns the rendering)
- Threshold values (StaleProgressThresholdSec etc.) -- SystemSettings-driven
- Sub-feature doc internals -- see colocated active-jobs-filter-sort + activity-dashboard-improvements
