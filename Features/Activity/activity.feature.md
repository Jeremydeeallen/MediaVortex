# Activity Dashboard -- live in-flight work visibility

**Slug:** activity

## What It Does

Renders `/Activity` -- the operator's live view of work IN FLIGHT RIGHT NOW. Two tables: Active Jobs + Active Scans, plus a queue-counts strip. Polls `/api/Activity/Snapshot` every 5 seconds. Pure consumer -- no transcoding work, no probe work, no policy writes. The vertical's job is "render what is happening RIGHT NOW, accurately and on time."

Worker tile UI lives at `/Admin/Workers` (see `admin-workers.feature.md`). Library compliance lives at `/Admin/Compliance` (see `admin-compliance.feature.md`). This page is exclusively about live work.

## Workflows

| # | User action | Surface element | Handler | Backing class.method |
|---|---|---|---|---|
| W1 | Open `/Activity` | nav link | `GET /Activity` | `ActivityController` renders `Templates/Activity.html` |
| W2 | View live in-flight snapshot | 5s page poll | `GET /api/Activity/Snapshot` | `DashboardSnapshotService.BuildSnapshot` (see `activity-dashboard.flow.md` ST2-ST6) |
| W3 | Filter Active Jobs by worker name | text input above Active Jobs table | client-side only | `Templates/Activity.html` -- see `active-jobs-filter-sort.feature.md` |
| W4 | Sort Active Jobs by column | click column headers | client-side only | `Templates/Activity.html` -- see `active-jobs-filter-sort.feature.md` |
| W5 | View nav badge counts | persistent nav | 10s nav-badge poll | `Templates/_navbar.html` polls `/api/SQLQueries/GetActiveJobs` |

## Success Criteria

C1. **Two tables only: Active Jobs + Active Scans.** Plus a queue-counts strip (Pending / Running / Failed by ProcessingMode). NO worker tiles, NO library-compliance card, NO settings modals on this page. Verifiable: `grep -E 'WorkersMount|VersionMismatchBanner|WorkerSettingsModal|ComplianceContainer' Templates/Activity.html` returns 0.

C2. **Active Jobs table columns**:
  - File / Size / Worker / Job Type / Speed / Progress / ETA
  - Target Resolution (e.g. `1080p -> 720p`)
  - Codec Change (e.g. `h264 -> av1`)
  - Estimated Savings (e.g. `-1.2 GB`; blank for Remux / AudioFix where the metric is not meaningful)
  - **Speed (multiplier vs realtime) replaces FPS universally** -- FPS is only meaningful for Transcode; Speed works for all three job types. Verifiable: `grep CurrentFPS Templates/Activity.html` returns 0; `grep CurrentSpeed Templates/Activity.html` >= 1.

C3. **Active Scans table columns**: Drive / Worker / Phase / Progress / Files (processed of total) / ETA. Verifiable: rendered page has the six column headers.

C4. **5-second polling cadence.** Page polls `/api/Activity/Snapshot` every 5 seconds; new data merges into rendered tables without scroll-position jump or flicker. Verifiable: poll observed at 5 +/-1s intervals in browser dev tools.

C5. **Snapshot envelope contract.** `/api/Activity/Snapshot` returns `{Success: bool, Data: {ActiveJobs, ActiveScans, QueueCounts, BadgeState, StaleProgressThresholdSec}}`. Five data keys stable contract. Verifiable: `curl /api/Activity/Snapshot | jq '.Data | keys'` returns the documented keys.

C6. **SharedTable renderer.** Both tables are rendered by SharedTable (`Static/js/TableRenderer/`). Adding a column is a config change in `Templates/Activity.html`; no edits to the renderer service. Verifiable: `grep -rn "TableRenderer\|ClientArrayDataSource" Templates/Activity.html` confirms instantiation; no hand-rolled `innerHTML` row construction.

C7. **Graceful degradation.** If `/api/Activity/Snapshot` errors or times out, the page renders an empty Active Jobs table with a "no live work" message rather than blank. No raw error text to the operator.

## Seams

| ID | Seam | Producer | Wire shape | Consumer expects | Verification |
|---|---|---|---|---|---|
| S1 | ActivityController -> page template | `ActivityController.RenderPage` | `Templates/Activity.html` with embedded module script | jQuery polls + SharedTable instances | Live page render |
| S2 | Snapshot endpoint contract | `DashboardSnapshotService.BuildSnapshot` -> `/api/Activity/Snapshot` | `{ActiveJobs, ActiveScans, QueueCounts, BadgeState, StaleProgressThresholdSec}` | `Templates/Activity.html` `LoadActivity` updates both tables | `activity-dashboard.flow.md` S1 |
| S3 | Snapshot -> SharedTable feed | `BuildSnapshot.Data.ActiveJobs[]` + `Data.ActiveScans[]` | row-shaped JSON | `ClientArrayDataSource.SetRows()` + `Table.Refresh()` | Browser console |
| S4 | ActiveJobs row enrichment | `ActivityRepository._EnrichActiveJob` | `(TargetResolution, CodecChange, EstimatedSavings)` derived per job | Renderer formats each cell from these fields | `TestActiveJobsInterestingColumns.py` |
