# Scanning on the Activity Page -- show what each worker is scanning right now

> **Superseded by `.claude/directives/closed/2026-05-27-active-scan-visibility.md`** (closed 2026-05-27):
> CEO directed scans render in the existing Active Jobs table alongside transcode + VMAF rows
> instead of in a dedicated "File Scanning" card. The implemented surface differs from the
> draft below in three ways: (1) no separate card, (2) Recent Scans is a one-line-per-scan
> strip inside the Active Jobs card rather than a full subsection, (3) the worker tile gains
> a single `Scan:` line (current rootfolder OR next-tick ETA) rather than two parallel lines.
> Phase visibility (Walking / Reconciling / Probing / Completing) and a per-row Stop button
> were added beyond the draft's scope. The draft text below is preserved as historical record.

## What It Does

Adds a "File Scanning" panel to the Activity page (between Workers and Quality Testing Queue) plus per-worker scan-current-job echoes, so the operator can see scans the same way they already see transcodes and VMAF jobs. Today scanning is invisible from the dashboard: a worker with `ScanEnabled=true` could be 5 minutes into walking T:\ for a 60-minute pass and the operator's only signal is `RootFolders.LastScannedDate` shifting an hour from now.

The panel shows:
1. **Active scans** -- ScanJobs rows with `Status='Running'`, with rootfolder, owning worker, current directory, progress %, processed/total counts, and elapsed time.
2. **Recent scan history** -- last 5 completed scans with rootfolder, duration, files added/updated/deleted, errors.
3. **Continuous-scan posture per worker** -- on each worker's tile (already redesigned by `activity-dashboard-improvements.feature.md`), if `Workers.ScanEnabled=true` shows "Next scan: <time-of-next-tick>" using `Last completed scan + ContinuousScanIntervalMinutes` as the estimate.

A small schema addition is required: `ScanJobs.WorkerName TEXT NULL`. Today the table records `ProcessId` but not the worker that owns the scan, so we can't say "I9-2024 is scanning T:\". `WorkerName` is set by `FileScanningBusinessService.StartScan` from `socket.gethostname()` or the caller's WorkerContext.

## Concern

Operator dogfood -- 2026-05-09. Scanning is the third long-running activity on every worker (alongside transcoding and VMAF), and it's the only one with no Activity-page surface. When a worker is "Online but idle" on the Activity page, today the operator can't tell whether it's *actually* idle or whether it's mid-scan eating disk and CPU. Same gap surfaced earlier today when verifying the deploy: I9-2024 sat with `Status='Draining'` and the operator had no way to know whether ContinuousScanService had been told to stop.

## Success Criteria

### A. Schema

1. `ScanJobs` table gains a nullable `WorkerName VARCHAR(255)` column. Migration script `Scripts/SQLScripts/AddScanJobsWorkerName.py` runs idempotently (`ADD COLUMN IF NOT EXISTS`). Verifiable: `\d ScanJobs` shows the column.

2. `FileScanningBusinessService.StartScan` writes `socket.gethostname()` into `WorkerName` for every new ScanJobs row. Pre-existing rows remain NULL and the UI handles NULL gracefully (`Worker: <unknown>`). Verifiable: trigger a scan, query `SELECT WorkerName FROM ScanJobs ORDER BY Id DESC LIMIT 1`, value matches the host that triggered it.

### B. Active Scans panel

3. A new card "File Scanning" is added to `Templates/Activity.html` between the Workers and Quality Testing Queue cards. Same visual style as the existing cards (table-sm, table-hover, dense layout). Verifiable: the page renders with three operational cards (Transcode / Workers / Scanning / QT) without layout regression.

4. The card header shows `File Scanning (<N> running)` parenthetical when N > 0, no parenthetical when N=0. Mirrors the Active Transcode Jobs header convention from `activity-dashboard-improvements.feature.md` criterion A1. Verifiable: with 0/1/3 active scans, header text matches.

5. The active scans table columns are: **Root Folder**, **Worker**, **Progress** (bar + %), **Current Directory** (truncated, full path on hover), **Processed / Total**, **New** / **Updated** / **Deleted** counters, **Elapsed**. Verifiable: visual inspection on a live scan.

6. Empty-state message when no scans are running: `<em>No active scans</em>` -- consistent with the "No active transcode jobs" empty state. Verifiable: with zero `Status='Running'` rows, the message renders and the table is hidden.

### C. Recent History panel

7. Below the active-scans table, a "Recent scans" subsection lists the last 5 ScanJobs rows ordered by `EndTime DESC` where `Status` is `Completed` or `Failed`. Columns: **Root Folder**, **Worker**, **Started**, **Duration**, **Files (new/updated/deleted)**, **Errors**, **Status**. Failed rows are highlighted (table-warning). Verifiable: queue 5+ scans, observe the most recent 5 in the panel; trigger a fail (e.g. unmount a drive) and observe the warning highlight.

### D. Per-worker scan posture

8. The worker tile (already redesigned by `activity-dashboard-improvements.feature.md` criterion E14) gains a one-line "Next scan" row when `Workers.ScanEnabled=true`:
    `Next scan: <human-formatted ETA>` based on `MAX(EndTime) FROM ScanJobs WHERE WorkerName=<this> AND Status='Completed'` plus `ContinuousScanIntervalMinutes`. If the worker has never completed a scan, shows `Next scan: imminent`. If `ScanEnabled=false`, the row is omitted entirely.
    Verifiable: with worker last-scanned-at 14:00 and interval=60, observe `Next scan: 15:00` (or "in 23 min" depending on chosen format).

9. While a scan is *currently in flight* on that worker (matching `Status='Running'` ScanJobs row), the tile's "Current" line (introduced by activity-dashboard E14 for transcodes) extends with a parallel `Scan: <rootfolder> (<progress>%)` line. The two Current lines coexist if the worker is doing both at once (transcode + scan). Verifiable: worker with both an active transcode and an active scan shows two distinct Current rows.

### E. API contract

10. `/api/TeamStatus/Overview` payload gains an `ActiveScans` array (alongside the existing `ActiveJobs` for transcodes), each entry containing: `JobId`, `RootFolderPath`, `WorkerName`, `Progress`, `CurrentDirectory`, `TotalFiles`, `ProcessedFiles`, `NewFiles`, `UpdatedFiles`, `DeletedFiles`, `StartTime`, `ElapsedSec`. Verifiable: GET the endpoint, response includes the new array.

11. New endpoint `GET /api/TeamStatus/RecentScans?limit=5` returns the last N completed/failed ScanJobs rows for the Recent History panel. Default limit 5, max 50. Verifiable: with limit=3, response has exactly 3 entries (or fewer if history is shorter).

12. `/api/TeamStatus/Workers` payload gains optional `LastScanCompleted` (timestamp) and `NextScanEstimate` (timestamp, NULL if `ScanEnabled=false`) fields per worker. Computed server-side -- the client renders them, doesn't compute. Verifiable: GET, fields populated for ScanEnabled workers, NULL for the others.

### F. Refresh cadence

13. The Active Scans panel refreshes on the same `LoadOverview()` polling tick already running on Activity (currently every ~5s). No new poller. Verifiable: code inspection -- `RenderActiveScans(Result.Data)` is called from the existing `LoadOverview()` chain, not a new `setInterval`.

### G. Failure modes (UI)

14. When `ScanJobs.Status='Failed'`, the active-scans row is replaced by a single highlighted line in the Recent History panel showing `ErrorMessage` truncated to 120 chars (full text on hover). The active-scans table only shows `Running`. Verifiable: induce a fail by unmounting a drive mid-scan, refresh: row drops out of Active and appears highlighted in Recent.

15. The "stuck scan" case (`Status='Running'` but `LastUpdated` older than 10 minutes) renders the row with an amber `IsStuck` indicator (same icon style as the stuck-transcode marker on the Active Transcode Jobs table). No automatic cleanup is performed by this feature -- the indicator is purely informational. Note: a future stuck-*scan*-detection service is out of scope and has been recorded as a [BUG] in `KNOWN-ISSUES.md` per `/b`. Verifiable: hand-craft a row by `UPDATE ScanJobs SET LastUpdated = NOW() - INTERVAL '15 minutes' WHERE Id = ...`, observe the amber marker on the table row.

## Status

DRAFTED -- awaiting operator approval.

### Progress

- [x] Read prior issues (no related entry)
- [x] Drafted `FileScanning.flow.md` (was missing -- created in this `/n` step 4)
- [x] Drafted feature doc (this file)
- [x] `/b` recorded the "stuck-scan detection" gap surfaced during drafting (per `/n` step 11 -- not in scope here)
- [ ] Operator approval
- [ ] Implement A1-A2 (ScanJobs.WorkerName migration + StartScan write)
- [ ] Implement B3-B6 (Active Scans card)
- [ ] Implement C7 (Recent History subsection)
- [ ] Implement D8-D9 (per-worker tile additions -- depends on activity-dashboard-improvements E14 having shipped or being co-developed)
- [ ] Implement E10-E12 (API payload extensions + new endpoint)
- [ ] Implement F13 (refresh wiring)
- [ ] Implement G14-G15 (failure-mode rendering)
- [ ] Smoke test: kick a manual scan; observe the new panel populate and update; let the scan complete; observe the row migrate from Active to Recent History; verify the worker tile's Next-Scan ETA matches `EndTime + IntervalMinutes`

NEXT: operator approval. Note the dependency on activity-dashboard-improvements criterion E14 for the worker-tile Current line; if that ships first, D9 here is a small extension. If this ships first, D9 introduces the Current-line pattern and activity-dashboard E14 then adapts.

## Scope

```
Templates/Activity.html                                   -- new File Scanning card, per-worker tile additions
Features/TeamStatus/TeamStatusController.py               -- /Overview gains ActiveScans; new /RecentScans endpoint; /Workers gains LastScanCompleted + NextScanEstimate
Features/FileScanning/FileScanningBusinessService.py      -- StartScan writes WorkerName
Features/FileScanning/FileScanningRepository.py           -- helper(s) to query running + recent scans for the API
Features/FileScanning/FileScanning.flow.md                -- already drafted in this /n; references this feature in the Surface section
Scripts/SQLScripts/AddScanJobsWorkerName.py               -- NEW. Idempotent ALTER TABLE ScanJobs ADD COLUMN IF NOT EXISTS WorkerName VARCHAR(255)
KNOWN-ISSUES.md                                           -- /b entry for "stuck-scan detection" (the running-but-stale case G15 surfaces but does not fix)
```

## Files

| File | Role |
|------|------|
| `Templates/Activity.html` | Adds the File Scanning card (Active + Recent subsections) and the two new lines on the worker tile (Next Scan ETA, optional Scan Current) |
| `Features/TeamStatus/TeamStatusController.py` | Extends `/Overview` payload with `ActiveScans`. Adds `GET /RecentScans?limit=N` endpoint. Extends `/Workers` payload with `LastScanCompleted` + `NextScanEstimate` |
| `Features/FileScanning/FileScanningBusinessService.py` | `StartScan` captures `socket.gethostname()` and passes to repository on insert |
| `Features/FileScanning/FileScanningRepository.py` | Add `GetRunningScans()`, `GetRecentScans(limit)`, `GetWorkerLastScanCompleted(workerName)` query helpers |
| `Features/FileScanning/FileScanning.flow.md` | Drafted in this `/n` step 4; references this feature's surface in the Surface section |
| `Scripts/SQLScripts/AddScanJobsWorkerName.py` | NEW. `ALTER TABLE ScanJobs ADD COLUMN IF NOT EXISTS WorkerName VARCHAR(255);` |
| `KNOWN-ISSUES.md` | Record stuck-scan detection as a `[BUG]` recorded via `/b` (not in this feature's scope) |

## Deviation from conventions

None. Each criterion is observable: page render, network response, DB read. The schema addition is nullable so older ScanJobs rows continue to work. The dependency between D9 and `activity-dashboard-improvements.feature.md` E14 is explicit; whichever ships second extends the existing line rather than redefining it.
