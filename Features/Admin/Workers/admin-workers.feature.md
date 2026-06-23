# Admin / Workers

**Slug:** admin-workers

## What It Does

Renders the operator-facing worker fleet at `/Admin/Workers`. Each tile shows TWO badges per worker:

- **Intent badge** -- `Workers.Status` (operator-set: `Online` / `Paused`). The operator's intent.
- **Truth badge** -- `Workers.RuntimeState` (worker-authored: `Initializing` / `Idle` / `ClaimingJob` / `Encoding` / `Scanning` / `Draining` / `Paused` / `Faulted:<reason>`). What the worker is actually doing right now.

When the two values disagree for more than the divergence threshold, the tile renders with an amber border + tooltip explaining the disagreement. The threshold lives in `SystemSettings.WorkerIntentDivergenceSec` (default 60). Operator-tunable per `worker-runtime-state` directive.

Tiles also display a connectivity dot independent of either badge: green when `(NOW() - LastHeartbeat) <= HeartbeatStaleThresholdSec` (default 300), red otherwise.

## Source-of-truth model

Three columns on `Workers` are worker-authored ONLY -- WebService never writes them. The single SRP writer is `WorkerService/WorkerStateReporter.py`:

| Column | Type | Worker-writes when |
|---|---|---|
| `RuntimeState` | TEXT | Every lifecycle transition + every heartbeat tick |
| `CurrentAttemptId` | BIGINT NULL | Non-null exactly when `RuntimeState='Encoding'`; points at `TranscodeAttempts.Id` |
| `LastRuntimeStateUpdate` | TIMESTAMP | Every state change or heartbeat tick |

If WebService is down, RuntimeState writes continue. When WebService comes back, the page reflects worker truth immediately without manual recompute.

## Surface

- Operator visits `/Admin/Workers`.
- Page polls `/api/Admin/Workers/Snapshot` every 5s.
- Subnav link in `Templates/_admin_subnav.html`.

## Success Criteria

C1. `/Admin/Workers` returns HTTP 200 and renders one tile per row in `Workers WHERE Enabled = TRUE`. Verifiable: `curl -I /Admin/Workers` -> 200; page source contains every enabled worker's name.

C2. `/api/Admin/Workers/Snapshot` returns `{Success, Data: {Workers, HeartbeatStaleThresholdSec, WorkerIntentDivergenceSec}}`. `Workers` is a list of dicts with `WorkerName`, `Status`, `RuntimeState`, `CurrentAttemptId`, `LastHeartbeat`, `LastRuntimeStateUpdate`, `HeartbeatAgeSec`, `IntentDiverges` (bool), capability flags, `Version`. Verifiable: `curl /api/Admin/Workers/Snapshot | jq '.Data.Workers[0] | keys'` includes the new keys.

C3. Intent badge maps `Online` -> green, `Paused` -> amber. Unknown values render grey with the raw string. Same data-driven table approach for Truth badge: `Idle` -> light, `Encoding` -> blue, `Scanning` -> cyan, `Draining` -> amber, `Paused` -> grey, `Faulted` -> red, unknown -> grey. Verifiable: `UPDATE Workers SET Status='Maintenance'` -- the Intent badge displays `Maintenance` in grey without code change.

C4. Connectivity dot derived from heartbeat freshness only, independent of either badge. Green when `HeartbeatAgeSec <= 300`; red otherwise. Verifiable: a `Paused` worker with fresh heartbeat shows green dot + amber Intent badge.

C5. Tile actions: Online / Pause buttons POST to `/api/TeamStatus/Workers/<name>/Status`. Page re-fetches snapshot on success. Verifiable: click Pause; the Intent badge flips to amber on the next poll.

C6. **Two-badge divergence warning.** When `Status` and `RuntimeState` carry semantically-incompatible values (e.g. `Status='Online'` but `RuntimeState='Paused'`) for more than `WorkerIntentDivergenceSec` seconds (default 60, operator-tunable in `SystemSettings`), the tile renders with an amber border. Tooltip text: `"Operator intent: Online; worker reports: Paused. Worker may be stuck or unable to honor the intent."` Verifiable: stop a worker process while its `Status='Online'`; the tile shows the amber border within ~60s of `LastRuntimeStateUpdate` going stale.

C7. **Worker is the only writer.** `grep -rn 'UPDATE Workers SET .* RuntimeState\|UPDATE Workers SET .* CurrentAttemptId\|UPDATE Workers SET .* LastRuntimeStateUpdate' Features/ WebService/` returns 0 matches. The three columns are written only by `WorkerService/WorkerStateReporter.py`.

C8. **WebService-outage resilience verified end-to-end.** Stop WebService; observe `Workers.RuntimeState` continues to update through normal worker lifecycle. Bring WebService back; `/api/Admin/Workers/Snapshot` reflects the truth immediately. Contract test `Tests/Contract/TestWorkerStateReporterResilience.py`.

## Files

| File | Role |
|------|------|
| `Features/Admin/Workers/AdminWorkersController.py` | Blueprint with `/Admin/Workers` route + `/api/Admin/Workers/Snapshot` endpoint |
| `Features/Admin/Workers/AdminWorkersRepository.py` | Tile data + IntentDiverges flag (pure-function divergence calc) |
| `Templates/AdminWorkers.html` | Two-badge tile renderer; divergence amber border; 5s polling JS |
| `Templates/_admin_subnav.html` | Workers link |
| `WorkerService/WorkerStateReporter.py` | NEW SRP writer (the only writer of the 3 worker-truth columns) |
| `WorkerService/Main.py` | Wires WorkerStateReporter into lifecycle transitions |
| `Scripts/SQLScripts/AddWorkerRuntimeStateColumns.py` | Idempotent migration: adds 3 columns + seeds `SystemSettings.WorkerIntentDivergenceSec=60` |

## Status

ACTIVE 2026-06-23 -- worker-runtime-state directive in flight. Tests cover: `TestAdminWorkersEndpoint.py` (page + snapshot shape), `TestWorkerStateReporterResilience.py` (WebService-outage resilience), `TestWorkerRuntimeStateAuthorship.py` (grep that only the SRP class writes the columns), `TestAdminWorkersDivergence.py` (IntentDiverges flag).
