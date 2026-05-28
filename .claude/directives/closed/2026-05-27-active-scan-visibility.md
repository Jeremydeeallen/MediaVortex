# Current Directive

**Set:** 2026-05-27
**Closed:** 2026-05-27
**Status:** Closed -- Partial (producer-side shipped clean; UI shipped but operator-rejected for cramming scan data into transcode-shaped columns; superseded by `.claude/directive.md` "scan -- largest files first").
**Replaces:** `directives/closed/2026-05-27-version-stamping.md` (closed Success)

## Outcome

The /Activity page becomes the operator's home base for scans. Today: invisible -- a worker scanning T:\ at 80% looks identical on /Activity to a worker doing nothing. After: every in-flight scan appears as a row in the existing Active Jobs table next to transcodes and VMAF jobs, with the same fidelity as a transcode row (rate, ETA, stop button), PLUS a clear phase indicator (Walking / Reconciling / Probing -- so a busy scan and a hung scan are not indistinguishable), PLUS each worker tile shows its scan posture (last scan + next scheduled), PLUS a Recent Scans strip below the Active Jobs table shows the last 5 completed/failed scans with counts so the operator can answer "what just happened" without leaving /Activity. The operator can start, watch, distinguish, stop, and review scans from one page.

## Acceptance Criteria

### A. Scan rows in the existing Active Jobs table

1. **Scan rows render in `<table id="ActiveJobsTable">` alongside transcode + VMAF rows.** No new card, no new table. When zero scans are running, the table looks identical to today. Verifiable: with at least one `ScanJobs.Status='Running'` row, the row appears in the same table that today holds transcode + VMAF jobs.

2. **Type cell reads `Scan` with a distinct badge color** (not the existing transcode-blue or VMAF-color). Verifiable: visual inspection -- badge text is exactly `Scan`, color is distinct from the other two types.

3. **File cell shows RootFolder primary, current directory secondary.** Primary line: `RootFolderPath` (e.g. `T:\`). Secondary line (smaller, muted): `CurrentDirectory` truncated to fit, full path on hover. If `CurrentDirectory` is NULL or equal to `RootFolderPath`, only the primary line shows. Verifiable: pick a scan whose CurrentDirectory is several levels deep; both lines render; hover tooltip shows the full path.

4. **Worker cell shows `ScanJobs.WorkerName`.** NULL renders as `<unknown>`. Verifiable: SQL value matches rendered value.

5. **Progress cell shows phase-aware progress bar + count.** During `Walking` phase: bar = `Progress %`, label = `<ProcessedFiles> / <TotalFiles> files walked` (label = `<ProcessedFiles> files` if TotalFiles=0). During `Probing` phase: bar = probe progress, label = `<ProbedFiles> / <FilesNeedingProbe> probed`. During `Reconciling`: indeterminate bar, label = `reconciling DB vs disk`. During `Completing`: bar = 100%, label = `finalizing`. Verifiable: kick a scan; watch the bar label change as phase transitions; SQL `SELECT Phase, Progress FROM ScanJobs WHERE Id=<id>` matches.

6. **Size cell shows file-disposition counters `+N ~U -D`.** Format: `+<NewFiles> ~<UpdatedFiles> -<DeletedFiles>` (e.g. `+2 ~0 -0`). Tooltip on hover: `2 new, 0 updated, 0 deleted`. Verifiable: counters in SQL match rendered cell.

7. **FPS cell shows files-per-second throughput.** Computed as `(delta-ProcessedFiles) / (delta-LastUpdated)` over the most recent two heartbeats, rendered as `<N> f/s`. Blank if fewer than two heartbeats yet observed. Verifiable: hit /api/TeamStatus/Overview twice 5s apart, the f/s value in the response equals `(processed_t2 - processed_t1) / 5`.

8. **Speed cell shows phase indicator** -- one of `Walking`, `Reconciling`, `Probing`, `Completing`, or a phase-specific sub-state when available (e.g. `Probing (1234/45716)`). Same column the transcode rows use for "Speed" (1.5x etc). Verifiable: scan in the Probing phase shows `Probing` (or `Probing (X/Y)`) in this cell, not `Walking`.

9. **ETA cell shows estimated time to completion.** During Walking: `(TotalFiles - ProcessedFiles) / FilesPerSecond`. During Probing: `(FilesNeedingProbe - ProbedFiles) / ProbesPerSecond`. During Reconciling: `--` (no ETA). Format matches the transcode-row ETA format (e.g. `3m 42s`, `42s`, `~`). Verifiable: pick a running scan, manually compute ETA from the underlying counters, value within 10% of rendered.

10. **Action cell shows a Stop button for scans.** Same component as the transcode Stop button. Clicking it calls a new endpoint that flips the ScanJobs row to `Status='Stopping'`; the producer-side scan loop checks Status each iteration and exits cleanly to `Status='Stopped'`. Verifiable: kick a scan, click Stop, observe Status='Stopping' immediately in SQL, then Status='Stopped' within ~5s, row drops out of Active table on next refresh.

11. **Stuck-scan visual indicator on the row.** If `LastUpdated > 10 minutes ago` while Status='Running', the row gets `table-warning` class and a small warning icon next to the Worker name with tooltip `Heartbeat stale (last update: 14m ago)`. Verifiable: `UPDATE ScanJobs SET LastUpdated = NOW() - INTERVAL '15 minutes' WHERE Id=<running>`; refresh /Activity; row is amber with the icon.

### B. Phase column (producer-side)

12. **`ScanJobs.Phase TEXT NULL` column exists** with idempotent migration. Values: `Walking | Reconciling | Probing | Completing | NULL`. Verifiable: `\d ScanJobs` shows the column; migration is re-runnable without error.

13. **Producer writes Phase at every transition** in `FileScanningBusinessService.PerformScan`: set to `Walking` at scan start, `Reconciling` when the walk completes and `ReconcileWithDisk` is entered, `Probing` when control passes to `MediaProbeBusinessService.ProbeFilesNeedingMetadata`, `Completing` for final stats/RootFolder update, then `Status='Completed'`+`Phase=NULL`. Heartbeat continues to fire. Verifiable: kick a scan, poll `SELECT Phase, Status FROM ScanJobs WHERE Id=<id>` every 5s, observe each phase appear in order before Status flips to Completed.

14. **Probe phase tracks per-probe progress on the same ScanJobs row.** Two new columns: `FilesNeedingProbe INTEGER NULL` (set at Probing-phase entry), `ProbedFiles INTEGER NULL` (incremented per probe completion). Reused by criterion 5 / 9 for the bar + ETA during Probing. Verifiable: during a Probing phase, both columns are non-NULL and `ProbedFiles` advances.

### C. Recent Scans strip (last 5)

15. **Below the Active Jobs table, a one-line-per-scan "Recent Scans" strip shows the last 5 ScanJobs rows** with `Status IN ('Completed', 'Failed', 'Stopped')` ordered by `EndTime DESC`. Each line: `<status icon> <RootFolderPath> on <WorkerName> -- <duration> -- +<N> ~<U> -<D> -- <ended-relative-time>` (e.g. `[OK] T:\ on larry-worker-3 -- 14m 22s -- +47 ~3 -0 -- 4m ago`). Failed rows use a red icon and append the truncated ErrorMessage; Stopped rows use a grey icon. Verifiable: trigger a quick scan, let it complete, observe the new entry as the first line of the strip within one /Activity polling tick.

16. **Recent Scans strip hides when there are zero rows** in the last 7 days; otherwise always renders even if no active scans. Verifiable: with empty ScanJobs, the strip's container has display:none; with at least one recent row, it renders.

### D. Per-worker tile -- scan posture

17. **Worker tile gains a `Scan` line when `Workers.ScanEnabled=true`.** Format -- one of:
    - Currently scanning (matching `ScanJobs.Status='Running'` row for this WorkerName): `Scan: <RootFolderPath> (<Phase>, <Progress>%)` -- e.g. `Scan: T:\ (Probing, 87%)`
    - Idle with prior history: `Scan: idle -- next ~<HH:MM>` where next = `(MAX(EndTime) WHERE WorkerName=<this> AND Status='Completed') + ContinuousScanIntervalMinutes`
    - Idle with no prior history: `Scan: idle -- next imminent`
    
    If `ScanEnabled=false`, line is omitted entirely. Verifiable: each of the three states reproducible by manipulating ScanJobs + Workers rows; renders match.

### E. API contract

18. **`/api/TeamStatus/Overview` payload gains `ActiveScans` array.** Each entry: `JobId, WorkerName, RootFolderPath, CurrentDirectory, Phase, Progress, TotalFiles, ProcessedFiles, FilesNeedingProbe, ProbedFiles, NewFiles, UpdatedFiles, DeletedFiles, StartTime, LastUpdated, ElapsedSec, FilesPerSec, EtaSec, IsStuck`. Server-computed where reasonable (ElapsedSec, FilesPerSec, EtaSec, IsStuck) -- the client renders, doesn't recompute. Verifiable: GET endpoint, array present with all listed fields.

19. **`/api/TeamStatus/Overview` payload gains `RecentScans` array (length <=5).** Same shape as ActiveScans plus `Status, EndTime, DurationSec, ErrorMessage`. Verifiable: GET endpoint, RecentScans present with up to 5 entries ordered by EndTime DESC.

20. **`/api/TeamStatus/Workers` per-worker payload gains `LastScanCompleted` (timestamp), `NextScanEstimate` (timestamp, NULL if ScanEnabled=false), `CurrentScanRootFolder` (string, NULL if no Running scan for this worker).** Verifiable: GET endpoint, fields present on each worker entry with correct values matching SQL.

21. **New endpoint `POST /api/FileScanning/Scan/<JobId>/Stop`** flips `ScanJobs.Status='Stopping'`. Returns `{'Success': true}` if the row existed and was Running. The producer-side scan loop polls Status each iteration and exits cleanly to `Status='Stopped'` with `EndTime=NOW()`. Verifiable: kick a scan, POST to the endpoint, observe Status='Stopping' immediately and Status='Stopped' within ~5s.

### F. Refresh + plumbing

22. **No new background poller on the page.** The existing `LoadOverview()` tick (~5s) pulls everything via the extended `/Overview` payload. Verifiable: code inspection -- no new `setInterval`, no new top-level `fetch()` for scans / recent / worker-posture data; all three come from the single existing tick.

23. **Empty-state behavior preserved.** When the table has zero rows (no transcode + no VMAF + no scan), the existing `<div id="NoJobInfo">No active jobs</div>` shows just as today. Verifiable: stop all activity, observe the empty-state message.

## Out of Scope

- `/Scanning` page redesign -- this directive touches /Activity only. /Scanning stays as-is.
- Multi-worker scan dispatch / scheduling changes -- existing `ContinuousScanService` + claim-guard behavior is unchanged.
- Editing `Workers.ScanEnabled` from the row's action cell -- the worker tile's existing controls already cover this.
- Pause-scan (different from Stop). Only Stop is in scope.
- Persistent scan history beyond the last 5 -- /Scanning's existing history view covers deeper lookback.

## Constraints

- One new producer-side migration: `ScanJobs.Phase`, `ScanJobs.FilesNeedingProbe`, `ScanJobs.ProbedFiles`. All nullable, all idempotent ADD COLUMN IF NOT EXISTS. Pre-existing rows stay NULL; the UI handles NULL Phase as "Running" with no sub-state.
- No changes to the Active Jobs table's column layout (same 9 columns) -- scan rows reuse columns by repurposing semantics (Size -> counters, Speed -> Phase, FPS -> files/sec). Transcode and VMAF rows render identically to today.
- All settings stay data-driven: scan interval is already `Workers.ContinuousScanIntervalMinutes`; stuck threshold is the existing `SystemSettings('StuckScanThresholdMin')` if present, fallback 10 minutes for the row indicator.
- No new env vars.

## Escalation Defaults

- Tradeoff between visual consistency and information density -> consistency. Scans use the same row shape as transcode/VMAF; if a field doesn't fit, leave blank rather than introduce a scan-specific layout.
- If the FPS / ETA computation produces noisy / spiky numbers in the Probing phase (probes have high per-file variance), smooth via 3-heartbeat moving average rather than expose volatility to the operator.
- Risk tolerance: medium. The producer-side Phase + Probe-counter writes touch the scan hot path. Worker restarts are required to pick up the new producer code; pre-deploy rows continue to work as Phase=NULL.

## Engineering Calls Already Made

- Reuse the existing Active Jobs table per CEO answer 2026-05-27. The prior `scanning-on-activity-page.feature.md` draft (separate "File Scanning" card between Workers and Quality Testing) is **superseded by this directive** -- doc supersession sweep at closure will update it.
- Pull active rows from `ScanJobs WHERE Status='Running'` so manual and continuous scans appear identically.
- Phase is a text column not an enum -- text is cheaper to migrate and the producer-side writers control the value set; the UI renders unknown values literally.
- Stop is a soft-stop via Status flag, not a thread.kill -- consistent with how transcode-stop already works and avoids leaving partial scan state.
- ETA + FPS are server-computed in the controller (not the producer) so they're cheap re-derivations and never stale relative to the heartbeat the controller is reading.

## Status

Active 2026-05-27 -- code complete; awaiting worker redeploy before closure.

Shipped 2026-05-27:
- [x] 1. Migration `Scripts/SQLScripts/AddScanJobsPhaseAndProbeCounters.py` run against live DB. Three nullable columns added on ScanJobs (Phase, FilesNeedingProbe, ProbedFiles). 73,125 existing rows untouched (Phase=NULL fallback in UI).
- [x] 2. Producer-side phase writes in `FileScanningBusinessService.PerformScan` (Walking -> Reconciling -> Walking -> Probing -> Completing -> terminal+ClearPhase). Probe-progress callback wired into `MediaProbeBusinessService.ProbeFilesNeedingMetadata` (new optional `ProgressCallback` parameter, also serves as soft-stop signal). Heartbeat extended to re-assert Phase / FilesNeedingProbe / ProbedFiles each tick.
- [x] 3. `_BuildActiveScans` + `_BuildRecentScans` helpers in `Features/TeamStatus/TeamStatusController.py` -- server-computed `FilesPerSec` (rolling delta via module-level `_ScanRateCache`, evicted on terminal status), `EtaSec` (phase-aware), `IsStuck` (StaleSec>600). `/Overview` payload gains both arrays; `/Workers` payload gains `LastScanCompleted`, `NextScanEstimate`, `CurrentScanRootFolder` per worker via a single round-trip aggregate query.
- [x] 4. `POST /api/Scan/<JobId>/Stop` endpoint -- flips DB row to Status='Stopping'; soft-stop polling in scan heartbeat thread observes and sets `_StopRequested`; per-file loop in `ProcessSingleFile` and per-probe loop in `ProbeFilesNeedingMetadata` exit cleanly; terminal write is Status='Stopped' with `ClearPhase=True`.
- [x] 5. `Templates/Activity.html` -- `RenderScanRow` for the merged Active Jobs table (badge=`Scan` green, phase-aware progress bar, files/sec, ETA, Stop button), `RenderRecentScans` strip below the table (last 5 with status icon, duration, counters, relative time), worker-tile `Scan:` line (current rootfolder when active / next-tick relative ETA when idle).
- [x] 6. Smoke tests against live DB: `_BuildActiveScans` returns the 3 in-flight larry-worker scans correctly; `_BuildRecentScans` returns the last 5 (3 Failed + 2 Completed); IsStuck verified via fake row (LastUpdated 15 min ago) -- `True`; controller imports green; Flask route `/api/Scan/<string:JobId>/Stop` registered.
- [x] 7. Doc sweep: `scanning-on-activity-page.feature.md` marked superseded with a header block pointing to this directive (draft preserved as historical record). `FileScanning.flow.md` State Surface lists the three new columns and Status='Stopping'; Surface section now describes the merged-into-Active-Jobs design instead of the old "gap today" stub.

Not yet verified (requires worker redeploy):
- Phase transitions observable in-flight (Walking -> Reconciling -> Probing). The 3 active scans in the DB right now run on pre-deploy producer code -- they will continue with Phase=NULL until restart.
- Soft-stop end-to-end (currently the DB flip will register, but no live worker is yet running the new heartbeat that polls for it).
- Probe-phase per-probe bar advancement.

### Operator -- what to execute to verify acceptance

1. Redeploy the three larry-worker containers (or restart the WorkerService process on each). This picks up the producer-side phase + probe-counter writes and the soft-stop poller.
2. Restart the WebService (it serves the new payloads + UI; old workers do not need it).
3. Open `/Activity`. Existing scan rows render with Phase fallback (Walking); new scans started after restart should advance through Walking -> Reconciling -> Probing -> Completing in the Speed column.
4. (Optional) Click Stop on a fresh scan row; observe Status='Stopping' immediately in SQL, Status='Stopped' within ~5s, row drops from Active table on next tick.
5. (Optional) Manually `UPDATE ScanJobs SET LastUpdated = NOW() - INTERVAL '15 minutes' WHERE Id=<running>` to verify amber stuck-row rendering.

Once 1-3 are confirmed working, close this directive (Success).
