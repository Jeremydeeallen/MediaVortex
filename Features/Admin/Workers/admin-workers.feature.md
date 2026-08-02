# Admin / Workers

**Slug:** admin-workers

## What It Does

Renders the operator-facing worker fleet at `/Admin/Workers`. Each tile shows TWO badges per worker:

- **Intent badge** -- `Workers.Status` (operator-set: `Online` / `Paused`). The operator's intent.
- **Truth badge** -- `Workers.RuntimeState` (worker-authored: `Initializing` / `Idle` / `ClaimingJob` / `Encoding` / `Scanning` / `Draining` / `Paused` / `Faulted:<reason>`). What the worker is actually doing right now.

When the two values disagree AND the worker is fresh (heartbeat within `SystemSettings.HeartbeatStaleThresholdSec`, default 300), the tile renders with an amber border + tooltip explaining the disagreement. Stale workers show a gray connectivity dot (offline) instead -- stale is not divergence.

Tiles also display a connectivity dot independent of either badge: green when `(NOW() - LastHeartbeat) <= HeartbeatStaleThresholdSec` (default 300), red otherwise.

## Source-of-truth model

Two columns on `Workers` are worker-authored ONLY -- WebService never writes them. The single SRP writer is `WorkerService/WorkerStateReporter.py`:

| Column | Type | Worker-writes when |
|---|---|---|
| `RuntimeState` | TEXT | Every lifecycle transition |
| `CurrentAttemptId` | BIGINT NULL | Non-null exactly when `RuntimeState='Encoding'`; points at `TranscodeAttempts.Id` |

Freshness is derived from `Workers.LastHeartbeat` alone (written every 30s by the health-monitor tick). Divergence and IsHung both gate on heartbeat age against `HeartbeatStaleThresholdSec`. If WebService is down, heartbeat + RuntimeState writes continue. When WebService comes back, the page reflects worker truth immediately without manual recompute.

## Surface

- Operator visits `/Admin/Workers`.
- Page polls `/api/Admin/Workers/Snapshot` every 5s.
- Subnav link in `Templates/_admin_subnav.html`.

## Success Criteria

C1. `/Admin/Workers` returns HTTP 200 and renders one tile per row in `Workers WHERE Enabled = TRUE`. Verifiable: `curl -I /Admin/Workers` -> 200; page source contains every enabled worker's name.

C2. `/api/Admin/Workers/Snapshot` returns `{Success, Data: {Workers, HeartbeatStaleThresholdSec, HungEncodeThresholdSec}}`. `Workers` is a list of dicts with `WorkerName`, `Status`, `RuntimeState`, `CurrentAttemptId`, `LastHeartbeat`, `HeartbeatAgeSec`, `IntentDiverges` (bool), capability flags, `Version`. Verifiable: `curl /api/Admin/Workers/Snapshot | jq '.Data.Workers[0] | keys'` includes the new keys.

C3. Intent badge maps `Online` -> green, `Paused` -> amber. Unknown values render grey with the raw string. Same data-driven table approach for Truth badge: `Idle` -> light, `Encoding` -> blue, `Scanning` -> cyan, `Draining` -> amber, `Paused` -> grey, `Faulted` -> red, unknown -> grey. Verifiable: `UPDATE Workers SET Status='Maintenance'` -- the Intent badge displays `Maintenance` in grey without code change.

C4. Connectivity dot derived from heartbeat freshness only, independent of either badge. Green when `HeartbeatAgeSec <= 300`; red otherwise. Verifiable: a `Paused` worker with fresh heartbeat shows green dot + amber Intent badge.

C5. Tile actions: Online / Pause buttons POST to `/api/TeamStatus/Workers/<name>/Status`. Page re-fetches snapshot on success. Verifiable: click Pause; the Intent badge flips to amber on the next poll.

C6. **Two-badge divergence warning.** When the worker is FRESH (heartbeat age <= `HeartbeatStaleThresholdSec`) AND `Status` and `RuntimeState` carry semantically-incompatible values (e.g. `Status='Online'` but `RuntimeState='Paused'`), the tile renders with an amber border. Tooltip text: `"Operator intent: Online; worker reports: Paused. Fresh heartbeat but worker is not honoring the intent."` Stale workers render with a red connectivity dot instead (offline, not divergence). Verifiable: `UPDATE Workers SET Status='Paused', LastHeartbeat=NOW()` on a worker whose `RuntimeState='Encoding'` -- tile shows amber border immediately.

C7. **Worker is the only writer.** `grep -rn 'UPDATE Workers SET .* RuntimeState\|UPDATE Workers SET .* CurrentAttemptId' Features/ WebService/` returns 0 matches. The two columns are written only by `WorkerService/WorkerStateReporter.py`.

C8. **WebService-outage resilience verified end-to-end.** Stop WebService; observe `Workers.RuntimeState` continues to update through normal worker lifecycle. Bring WebService back; `/api/Admin/Workers/Snapshot` reflects the truth immediately. Contract test `Tests/Contract/TestWorkerStateReporterResilience.py`.

C9. **Hung-encode detector.** A worker is classified `IsHung=true` when `RuntimeState='Encoding'` AND `Workers.LastHeartbeat` is older than `SystemSettings.HungEncodeThresholdSec` (default 600) AND `TranscodeProgress.LastProgressUpdate` for that attempt has not advanced within the same window. Auto-recovery: `StuckJobDetectionService` kills the ffmpeg subprocess by `FFmpegPid`, flips `TranscodeAttempts.Success=FALSE` with `ErrorMessage='hung_encode_detector'`, deletes the `ActiveJobs` row, and the worker on next lifecycle tick transitions `RuntimeState` to `Idle`. Verifiable: `Tests/Contract/TestHungEncodeDetector.py` simulates a stale progress row for an in-flight attempt and asserts auto-reset within the next detection sweep.

C10. **Hung tile rendering.** A tile with `IsHung=true` renders with a red border + tooltip `"Encoding attempt N for X minutes without progress -- auto-reset pending."`. Operator visual signal independent of the amber-intent-divergence border. Verifiable: insert a synthetic hung attempt; the tile's class list contains `hung-border` within next poll.

C11. **`Faulted:<reason>` writes happen.** Worker uncaught-exception paths (the top-level main loop, `_ApplyCapabilities`) transition to `RuntimeState='Faulted:<reason>'` via best-effort try/except around `WorkerStateReporter.Transition` BEFORE process exit. On next boot, `_RecoverFromCrash` clears any `Faulted:*` row by transitioning through normal `Initializing -> Idle` (or `Paused` per DB Status). Verifiable: `Tests/Contract/TestFaultedStateOnCrashRecovery.py` injects an uncaught exception; DB shows `RuntimeState` starting with `Faulted:`; restart clears it.

C12. **Hung-encode threshold is operator-tunable** via `SystemSettings.HungEncodeThresholdSec` (default 600). Verifiable: `UPDATE SystemSettings SET SettingValue='120'` -- next detection sweep observes the new threshold without restart.

## Files

| File | Role |
|------|------|
| `Features/Admin/Workers/AdminWorkersController.py` | Blueprint with `/Admin/Workers` route + `/api/Admin/Workers/Snapshot` endpoint |
| `Features/Admin/Workers/AdminWorkersRepository.py` | Tile data + IntentDiverges flag (pure-function divergence calc) |
| `Templates/AdminWorkers.html` | Two-badge tile renderer; divergence amber border; 5s polling JS |
| `Templates/_admin_subnav.html` | Workers link |
| `WorkerService/WorkerStateReporter.py` | NEW SRP writer (the only writer of the 3 worker-truth columns) |
| `WorkerService/Main.py` | Wires WorkerStateReporter into lifecycle transitions |
| `Scripts/SQLScripts/AddWorkerRuntimeStateColumns.py` | Idempotent migration: adds worker-truth columns |
| `Scripts/SQLScripts/AddHungEncodeThresholdSetting.py` | Idempotent: seeds `SystemSettings.HungEncodeThresholdSec=600` |
| `Features/StuckJobDetection/HungEncodeDetector.py` | Pure detector function (RuntimeState, HeartbeatAge, ProgressAge, Threshold) -> bool |
| `Features/StuckJobDetection/StuckJobDetectionService.py` | Sweep invokes detector + executes auto-recovery |
| `Templates/Activity.html` | Hung-attempts red banner with Reset buttons |

## Status

ACTIVE 2026-06-23 -- worker-runtime-state directive in flight. Tests cover: `TestAdminWorkersEndpoint.py` (page + snapshot shape), `TestWorkerStateReporterResilience.py` (WebService-outage resilience), `TestWorkerRuntimeStateAuthorship.py` (grep that only the SRP class writes the columns), `TestAdminWorkersDivergence.py` (IntentDiverges flag).
