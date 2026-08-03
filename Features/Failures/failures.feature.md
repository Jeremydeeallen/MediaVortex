# Failures

**Slug:** failures

## What It Does

Operator surface for stuck files: scans that failed and probes that hit the failure cap. Table view with reason + count + per-row Retry button. Retry unblocks the row so the pipeline picks it up on the next tick.

## Workflows

| # | User action | Surface element | Handler | Backing class.method |
|---|---|---|---|---|
| W1 | View all stuck files | `/Failures` page | `GET /api/Failures` | `Features/Failures/FailuresController.List` |
| W2 | Retry one row | per-row Retry button | `POST /api/Failures/<MediaFileId>/Retry` | `Features/Failures/FailuresController.Retry` |
| W3 | Filter by failure type | `/Failures` filter pills | client-side filter on same payload | JS |
| W4 | See scan failures | separate section on `/Failures` | `GET /api/Failures?type=scan` | reads `ScanJobs WHERE Status='Failed'` |

## Success Criteria

C1. **`/Failures` page exists.** Renders two sections: (1) Probe failures (MediaFiles rows with `FFprobeFailureCount >= MaxFFprobeFailures`), (2) Scan failures (ScanJobs rows with `Status='Failed'`, excluding housekeeping messages per existing `GetRecentScanRuns` classification). Contract: `TestFailuresPage.py`.

C2. **Probe failures table columns.** Filename, Path (canonical), FFprobeFailureCount, LastFFprobeError, LastFFprobeAttemptDate, [Retry] button. Ordered by LastFFprobeAttemptDate DESC.

C3. **Scan failures table columns.** RootFolderPath, WorkerName, ErrorMessage, EndTime, [Retry] button (retries via re-enqueuing a ScanJobs row for the same RootFolder). Ordered by EndTime DESC.

C4. **`POST /api/Failures/<MediaFileId>/Retry` resets probe state.** SQL: `UPDATE MediaFiles SET FFprobeFailureCount=0, LastFFprobeError=NULL, NeedsReprobe=TRUE WHERE Id=%s`. Returns `{Success, Message}`. Contract test.

C5. **Retry produces observable state change within one ProbeWorker tick.** ProbeWorker's claim predicate picks up rows where `Resolution IS NULL OR NeedsReprobe=TRUE AND FFprobeFailureCount < MaxFFprobeFailures`; retried row satisfies. Contract test asserts row disappears from `/Failures` after successful probe.

C6. **Scan failure retry re-enqueues ScanJobs row for the same RootFolder.** `POST /api/Failures/scan/<RootFolderPath>/Retry` -> writes fresh `ScanJobs(Status='Pending', RootFolderPath=?)`. Per-RootFolder claim guard still applies.

C7. **Failure counts on `/Status` page drill-down clickable.** Existing "Possibly Corrupt" count on `/Status` links to `/Failures` filtered to probe failures. Existing endpoint `/api/FileScanning/MediaFiles/Corrupt` folds into this feature's `GET /api/Failures`.

C8. **GUI-editable retry (per gui-editable-knobs rule).** Retry is a GUI action, not a SQL-only knob. Operator does not need to know which columns to update.

## Seams

| ID | Seam | Producer | Wire shape | Consumer expects | Verification |
|---|---|---|---|---|---|
| S1 | Controller -> BusinessService | HTTP GET/POST | `GetFailures()` returns `{Probe: [...], Scan: [...]}`; `Retry(Id)` returns `{Success, Message}` | jQuery renders / toasts | contract test |
| S2 | BusinessService -> Repository | `GetFailures()` | `SELECT ... FROM MediaFiles WHERE FFprobeFailureCount >= <cap>` + `SELECT ... FROM ScanJobs WHERE Status='Failed' AND ErrorMessage NOT IN (<housekeeping>)` | returns two lists | contract test |
| S3 | BusinessService -> Repository (retry probe) | `Retry(MediaFileId)` | `UPDATE MediaFiles SET FFprobeFailureCount=0, LastFFprobeError=NULL, NeedsReprobe=TRUE WHERE Id=%s` | single UPDATE | contract test |
| S4 | BusinessService -> ProbeWorker (implicit) | retry sets `NeedsReprobe=TRUE` | ProbeWorker polls that predicate | claim within N seconds | contract test |

## Housekeeping message classification

Scan failures excluded from `/Failures` (they're not real failures, they're lifecycle events):

- `%Application restarted%`
- `%Zombie%`
- `%pre-redeploy%`
- `%Stuck scan cleaned by StuckJobDetectionService%`
- `%post-deploy mass clear%`
- `%cleared post-restart%`
- `%cleared post-deploy%`
- `%Stopped pre-redeploy%`

Pattern list reused from existing `SQLQueriesController.GetRecentScanRuns`.

## What this feature does NOT own

- Probe execution: `Features/MediaProbe/probe.feature.md`
- Scan execution: `Features/FileScanning/scan.feature.md`
- Transcode failures: `Features/FailureAccounting/failure-accounting.feature.md`

## Status

DRAFTED under directive `ingest-pipeline-kiss`. New surface; folds `/api/MediaProbe/Failed` + `/api/MediaProbe/ResetFailures/<id>` into one place.
