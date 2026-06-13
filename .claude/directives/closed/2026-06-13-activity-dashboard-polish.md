# Activity Dashboard Polish (Cluster C tail)

**Set:** 2026-06-13
**Status:** Active -- phase: IMPLEMENTING
**Slug:** activity-dashboard-polish

## Outcome

Land the deferred polish from `activity-dashboard-solid` + the remaining feature-doc criteria from `activity-dashboard-improvements.feature.md` that don't need new backend pipelines.

## Acceptance Criteria

1. **C1: Active Jobs card header reads `Active Transcode Jobs (<N> running)`**; omit parenthetical when N=0.
2. **C3: Active Jobs table footer** sums total Size and total FPS across visible rows.
3. **C4: Dead UI removed.** `Stop After This Job` button / `StopAfterJob()` JS / `POST /api/Transcode/Stop` endpoint / `SetTranscodingStopped()` helper -- all gone.
4. **C5: `Resume` button + handler removed** iff `git grep` shows no live caller other than the Activity page.
5. **C15: QT badge data-driven mapping** following the same pattern as `WorkerStatusMap` (Cluster C C4).
6. **Capability-toggle inline re-render** -- on success, refetch snapshot + re-render the worker tile/modal without operator close-reopen.
7. **Bulk-button JS hookup** -- "All Online" / "All Paused" fire one POST to `/api/TeamStatus/Workers/BulkStatus` instead of N serial fetches.
8. **ETACountdownTimer (client-side)** -- per-job timer decrements 1s/sec between polls; resets to server value on `|delta|>5s`.

Out of scope: C2 Target column (needs server-side ProfileThresholds join), C14 Current row echo (needs CurrentFile in worker payload).

## Files

```
Templates/Activity.html
Features/TranscodeJob/TranscodeJobController.py   -- if C4 endpoint lives here
Features/ServiceControl/ServiceStatusHelperService.py   -- if C4 helper lives here
```
