# Activity Dashboard -- worker visibility, lifecycle, and active-job summary fixes

**Slug:** activity-dashboard-improvements

## What It Does

Tightens the Activity page so the operator can see at a glance: how many transcodes are running, fleet-wide FPS throughput, what each transcode is targeting, what each worker is currently doing, and the difference between operational state (Online / Draining / Stopped) and connectivity (process reachable / unreachable). Removes dead UI (`Stop After This Job`, `Resume`) whose backend the worker never reads. Replaces hard-coded badge logic with a data-driven status renderer so any value in `Workers.Status` displays correctly without code changes when new states are introduced. Adds the missing terminal `Stopped` state so a drained worker stops looking like a still-draining worker. Closes the related cleanup items the operator surfaced during scoping.

This feature does not introduce a new pipeline. It updates the visualization (Activity page), the per-worker status enum (one new value), and the existing `WorkerService.flow.md` per-worker status transitions.

## Concern

Operator reported (2026-05-09) that "Stop After This Job" did nothing -- it wrote `ServiceStatus.Status='Stopped'` on the singleton legacy `'TranscodeService'` row, but workers only honor `Status='Paused'`. Same investigation surfaced six related problems (the worker badge silently overrides operator-set `Workers.Status` when heartbeat is stale; drain has no terminal state so `Workers.Status` stays `'Draining'` forever; bulk action loops fire N serial requests; the heartbeat threshold is hard-coded; the operator-set `Offline` red badge reads as an error; and worker tiles don't echo the current job). All of these merge into one Activity-dashboard pass so the per-worker mental model is internally consistent. The 2026-05-08 `[TECH DEBT] Activity page conflates worker liveness and operational state` entry is subsumed by criteria C8-C10 below.

## Success Criteria

### A. Active Transcode Jobs panel

1. The card header on the Active Transcode Jobs panel reads `Active Transcode Jobs (<N> running)` where `<N>` is the number of jobs currently shown. When `<N>` is 0 the parenthetical is omitted. Verifiable: render with 0/1/3 active jobs and inspect the header text.

2. A new column **Target** is added to the Active Transcode Jobs table between **Size** and **Progress**. Each row's Target cell shows the destination resolution category (`480p`, `720p`, `1080p`, `2160p`, or `Same` if the assigned profile's `TranscodeDownTo` for that source resolution is unset / equals the source). Sourced server-side via the existing `MediaFiles.AssignedProfile` -> `ProfileThresholds.TranscodeDownTo` join. Verifiable: queue a 1080p file with a 720p-down profile and observe `Target: 720p` on its row.

3. A footer row at the bottom of the Active Transcode Jobs table sums the columns where a sum is meaningful: total Size and total FPS. File / Worker / Target / Progress / Speed / ETA / Action cells in the footer are blank. Total FPS is the arithmetic sum of `CurrentFPS` across all displayed jobs to one decimal; rows with NULL FPS contribute 0. Verifiable: with 3 jobs at 24.0, 61.7, 103.4 FPS, footer FPS = `189.1`.

3b. The **Activity** nav tab in the global nav bar displays a green pill badge showing the count of currently active transcode jobs. The badge polls `/api/SQLQueries/GetActiveJobs` every 10 seconds (same endpoint the Activity page uses). When the count is 0, the badge is hidden. Verifiable: start 2 transcode jobs, observe the nav badge shows "2" in green; stop all jobs, badge disappears. [DONE 2026-05-14, commit 148bd4b]

4. The **Stop After This Job** button (`Activity.html:26`), the `StopAfterJob()` JS function, the click handler, the `POST /api/Transcode/Stop` endpoint (`TranscodeJobController.py:58`), and the helper `SetTranscodingStopped()` (`ServiceStatusHelperService.py:92`) are all removed. Verifiable: `git grep "StopAfterJob\|/api/Transcode/Stop\|SetTranscodingStopped"` returns no live code references.

5. The **Resume** button (`Activity.html:29`), the `ResumeTranscoding()` JS function, the `POST /api/Transcode/Start` endpoint, and the helper `SetTranscodingStarted()` are removed at the same time **iff** `git grep` shows no live caller other than the Activity page. If another caller exists, the button still goes; only the dead helper goes. Verifiable: rendered HTML has no Resume button; remaining callers (if any) are listed in the commit message.

### B. Per-worker status -- enum and lifecycle

6. The `Workers.Status` enum gains a new terminal value `'Stopped'`, replacing the operator-set semantics that `'Offline'` carried before. The accepted-values tuple in `TeamStatusController.py:436` becomes `('Online', 'Draining', 'Stopped')`. A migration script `Scripts/SQLScripts/RenameWorkerStatusOfflineToStopped.py` runs `UPDATE Workers SET Status='Stopped' WHERE Status='Offline'` (idempotent, no-op on subsequent runs). Verifiable: post-deploy `SELECT DISTINCT Status FROM Workers` returns only the new tuple.

7. The action button row on each worker card uses verbs that match the new enum: `Online` / `Drain` / `Stop` (the third currently labeled "Offline"). Pressing **Stop** writes `Workers.Status='Stopped'`. Verifiable: click Stop on a worker; `SELECT Status FROM Workers WHERE WorkerName=...` returns `Stopped`.

8. **Drain has a terminal state**. When `_DrainAndStop()` (`WorkerService/Main.py:528`) finishes joining the in-flight transcode thread, it writes `UPDATE Workers SET Status='Stopped' WHERE WorkerName=<self>`. The worker's own status-polling loop sees the change on its next 5s tick and treats the `Draining -> Stopped` transition as a no-op (already stopped). Verifiable: press Drain on a worker mid-job; after the current job finishes, the badge flips from `Draining` to `Stopped` within 5-7 seconds without operator intervention.

### C. Worker badge -- data-driven, two-axis

9. The badge next to each worker name is rendered from a single JS data table mapping `Workers.Status` -> `{label, badgeClass}`. Whatever string the column holds, the badge displays it -- no hard-coded fall-through. The current line `Activity.html:315` (`DisplayStatus = IsOnline ? W.Status : 'Offline'`) is removed. An unrecognised status value renders with a neutral grey badge plus the raw string (so future `'Maintenance'` or `'Updating'` values display gracefully without a code change). Verifiable: `UPDATE Workers SET Status='Maintenance' WHERE WorkerName='larry-worker-1'` -- the badge displays `Maintenance` in grey.

10. The badge color/label table for shipping values:
    - `Online` -> green (`bg-success`), label "Online"
    - `Draining` -> amber (`bg-warning text-dark`), label "Draining"
    - `Stopped` -> neutral grey (`bg-secondary`), label "Stopped" -- not red. Operator-set stop is not an error condition.
    - Any other value -> grey (`bg-secondary`), label = raw value
    Verifiable: visual inspection of each badge color matches the table.

11. A separate **connectivity indicator** (small dot to the left of the worker name) is driven solely by heartbeat freshness, independent of `Workers.Status`. Three buckets:
    - green: heartbeat age < 60s
    - amber: 60s -- `HeartbeatStaleThresholdSec`
    - red: > `HeartbeatStaleThresholdSec` or NULL
    The dot has tooltip "Last heartbeat: <X> ago" (e.g. "12s ago", "4 min ago", "Never"). The badge and dot are independent: an operator-set `Stopped` worker that is still heartbeating shows `green dot + grey "Stopped" badge`; a crashed worker last seen as `Online` shows `red dot + green "Online" badge` until either the heartbeat returns or the operator manually moves it. Verifiable: stop a worker process while leaving its DB row at `Status='Online'` and confirm the dot turns red after `HeartbeatStaleThresholdSec` while the badge stays green.

### D. Tunable thresholds and bulk operations

12. A new `SystemSettings` row `HeartbeatStaleThresholdSec` controls the connectivity dot's red-vs-amber boundary. Default `300` (matches today's hard-coded behavior). Read once on Activity page render and embedded as a JS constant in the page; no per-poll fetch. Verifiable: `UPDATE SystemSettings SET Value='60' WHERE Key='HeartbeatStaleThresholdSec'`, reload the page, confirm a 90s-stale worker now shows red instead of amber.

13. The `Drain All` / `All Online` / `All Stopped` buttons issue a **single** server-side bulk request, not N serial fetches as today (`Activity.html:377-382`). New endpoint `POST /api/TeamStatus/Workers/BulkStatus` body `{"Status": "Draining", "WorkerNames": ["larry-worker-1", "moe-worker-1"]}` returns per-worker success/failure in one call. The client renders the result toast as either "All N workers set to Draining" or, on partial failure, "X of N succeeded; failed: <names>". Verifiable: open browser dev tools, click Drain All with 5 workers, confirm exactly one network call to `/BulkStatus`.

### E. Worker tile -- current job echo

14. When a worker has an active transcode (`TranscodeQueue.ClaimedBy = WorkerName AND Status='Running'`), its card body shows a one-line "Current" row above the action buttons:
    `Current: <FileName> (<FPS> fps)`
    where `<FPS>` is the latest `TranscodeProgress.CurrentFPS` for that job, or `--` if not yet reported. When the worker has no active job, the row is omitted (no empty placeholder). Sourced server-side -- `/api/TeamStatus/Workers` payload gains optional `CurrentFile` + `CurrentFPS` fields per worker. Verifiable: with one transcode running on `larry-worker-1`, the larry tile shows the file and FPS; the other tiles show no Current row.

### F. Quality Testing Queue panel -- data-driven status

15. `GetQTStatusBadgeClass` (`Activity.html:158-161`) is replaced by the same data-table pattern used for the worker badge in C9. Unknown statuses fall through to grey + raw value. The same shipping mapping (`Pending` warning amber, `Running` info blue, `Completed` success green, `Failed` danger red) renders identically to today. Verifiable: visual parity check (no UI regression) plus a deliberate `UPDATE QualityTestQueue SET Status='Cancelled'` on one row showing `Cancelled` in grey instead of falling through to the unhelpful default.

### G. Documentation

16. `WorkerService/WorkerService.flow.md` Per-Worker Status Control section (line 28) is updated:
    - Status table replaces `Offline` row with `Stopped` row, semantics unchanged ("All capabilities stopped. Worker still sends heartbeats.")
    - Status changes block (line 38) updates transitions: `Online -> Stopped`, `Draining -> Stopped` (auto on drain completion -- new), `Stopped -> Online` re-applies capabilities.
    - One sentence noting "Offline" is now a UI/connectivity term meaning "process unreachable", derived from `LastHeartbeat`, not a `Workers.Status` value.

17. `memory/KNOWN-ISSUES.md` `[TECH DEBT] Activity page conflates worker liveness and operational state` entry is annotated with `[MERGED INTO Features/Activity/activity-dashboard-improvements.feature.md 2026-05-09]` and moved to the Resolved section once this feature ships.

18. **[BUG-0007] Toggling a worker capability on the Activity page updates the rendered state immediately, without requiring the operator to close and reopen the modal.** Today after clicking a capability switch (TranscodeEnabled / QualityTestEnabled / ScanEnabled / RemuxEnabled), the `POST /api/TeamStatus/Workers/<name>/<Capability>` request succeeds and the DB row updates, but the on-screen toggle and any derived UI (status badge, capability row, action-button enable state) keep showing the pre-click value until the operator closes the worker modal and reopens it (or reloads the page). Fixed means: after the API call returns Success, the worker's tile / modal re-renders from the fresh server payload so the operator sees the new state without navigating. Verifiable: click TranscodeEnabled from on to off on a worker; without closing the modal, observe the toggle is now off and the capability-row indicator reflects the new value within one poll tick (or immediately if the handler refetches inline).

## Status

DRAFTED -- awaiting operator approval.

### Progress

- [x] Read prior issues (`memory/KNOWN-ISSUES.md`, `WorkerService.flow.md`)
- [x] Surveyed Activity page UI + JS
- [x] First draft -- main asks captured
- [x] Folded all six "other weaknesses" into criteria (operator approved 2026-05-09)
- [ ] Operator approval to begin implementation
- [ ] Implement A1-A5 (panel header count, Target column, FPS sum, Stop+Resume removal)
- [ ] Implement B6-B8 (Status enum migration, action button rename, drain terminal-state writeback)
- [ ] Implement C9-C11 (data-driven badge, connectivity dot, removed implicit override)
- [ ] Implement D12-D13 (HeartbeatStaleThresholdSec setting, bulk endpoint)
- [ ] Implement E14 (worker tile current-job echo)
- [ ] Implement F15 (Quality Testing Queue data-driven badge)
- [ ] Implement G16-G17 (flow doc + KNOWN-ISSUES updates)
- [ ] Smoke test: 3 simultaneous transcodes display Target/FPS sum correctly; one worker manually moved to `Status='Maintenance'` displays gracefully; drain completes and auto-flips to Stopped; Drain All issues exactly one bulk call
- [ ] Live verify: heartbeat-stale worker shows red dot + last-known badge color (badge does not silently rewrite to "Stopped")

NEXT: operator approval to start implementation. Recommended implementation order: G16/G17 doc updates first (the contract), then B6 migration (DB shape), then C9-C11 (badge), then A/D/E/F (UI polish on top of the now-correct data shape).

## Scope

```
Templates/Activity.html                                       -- header count, Target column, FPS sum row, button removal, badge data-table, connectivity dot, worker-tile Current row, QT badge data-table
Features/TeamStatus/TeamStatusController.py                   -- /Overview ActiveJobs payload gains TargetResolution; /Workers payload gains CurrentFile + CurrentFPS; new /Workers/BulkStatus endpoint; status enum tuple updated to {Online, Draining, Stopped}
Features/Activity/ActivityViewModel.py                        -- if any per-worker join logic moves here from Controller
Features/TranscodeJob/TranscodeJobController.py               -- delete POST /Stop and POST /Start
Features/ServiceControl/ServiceStatusHelperService.py         -- delete SetTranscodingStopped + SetTranscodingStarted (zero callers after A4/A5)
WorkerService/Main.py                                         -- _HandleStatusChange branch rename Offline -> Stopped; _DrainAndStop writes Workers.Status='Stopped' on completion
Scripts/SQLScripts/RenameWorkerStatusOfflineToStopped.py      -- NEW. Idempotent UPDATE Workers SET Status='Stopped' WHERE Status='Offline'
WorkerService/WorkerService.flow.md                           -- Per-Worker Status Control section updates per G16
memory/KNOWN-ISSUES.md                                               -- annotate prior [TECH DEBT] entry as merged per G17
SystemSettings table (no migration file)                      -- new row HeartbeatStaleThresholdSec=300 inserted by RenameWorkerStatusOfflineToStopped.py same script (or a sibling) so the deploy is one shot
```

## Files

| File | Role |
|------|------|
| `Templates/Activity.html` | All UI changes -- header count, Target column, FPS sum row, button removal, badge data-table, connectivity dot, worker-tile current-job line, QT badge data-table, single bulk-fetch for Drain All / All Online / All Stopped |
| `Features/TeamStatus/TeamStatusController.py` | `/Overview` adds `TargetResolution` to ActiveJobs payload via `ProfileThresholds.TranscodeDownTo` join. `/Workers` adds `CurrentFile` + `CurrentFPS`. New endpoint `POST /Workers/BulkStatus`. Status validation tuple updated. |
| `Features/TranscodeJob/TranscodeJobController.py` | Delete `/Stop` (lines 58-83) and `/Start` route + handler |
| `Features/ServiceControl/ServiceStatusHelperService.py` | Delete `SetTranscodingStopped` (line 92) and `SetTranscodingStarted` (line 108) |
| `WorkerService/Main.py` | `_HandleStatusChange` branch `"Offline"` renamed to `"Stopped"` (line 520). `_DrainAndStop` (line 528) calls `DatabaseManager.UpdateWorkerStatus(self.WorkerName, 'Stopped')` after the join completes. |
| `Scripts/SQLScripts/RenameWorkerStatusOfflineToStopped.py` | NEW. Idempotent `UPDATE Workers SET Status='Stopped' WHERE Status='Offline'`; INSERT `HeartbeatStaleThresholdSec=300` into SystemSettings ON CONFLICT DO NOTHING |
| `WorkerService/WorkerService.flow.md` | Status table + transition list updated per G16 |
| `memory/KNOWN-ISSUES.md` | Prior `[TECH DEBT]` entry annotated as merged per G17 |

## Deviation from conventions

None. Every criterion is observable from outside the code (DOM inspection, network response, DB read, log entry). The `Workers.Status='Offline' -> 'Stopped'` rename is a backwards-incompatible value change, but the migration script is idempotent and the worker code is updated in the same deploy, so there is no period where the DB has values the code rejects.
