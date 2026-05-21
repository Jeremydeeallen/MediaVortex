# Worker Status Model -- Online / Paused / Draining + heartbeat liveness

## Summary

Replaces the current Online/Draining/Offline status enum with Online/Paused/Draining where Offline is no longer an operator-set value. Liveness (container running vs dead) is derived from heartbeat freshness -- independent of operational state. Draining auto-transitions to Paused when the current job finishes, so the operator only sees two buttons: Online and Pause.

## Concern

The Activity page conflates two independent axes -- "is the container alive?" and "should the worker accept jobs?" -- into one badge. Clicking Offline sets `Workers.Status='Offline'` in the DB, but the API returns status derived from heartbeat freshness, ignoring the DB value. Workers that restart also forced themselves Online, overriding operator intent. The startup-override bug is already fixed; this feature completes the model by fixing the API, UI, and state machine.

References: KNOWN-ISSUES.md line 393 "[TECH DEBT] Activity page conflates worker liveness and operational state"

## Surface

- Activity page worker cards (badge, card class, buttons)
- `GET /api/TeamStatus/Workers` (returns operational status + heartbeat liveness separately)
- `POST /api/TeamStatus/Workers/<name>/Status` (accepts Online, Paused only; Draining is set internally)
- Worker status polling loop in `WorkerService/Main.py`
- `WorkerService/WorkerService.flow.md` Per-Worker Status Control section

## Scope

- Features/TeamStatus/**
- WorkerService/**
- Templates/Activity.html
- Scripts/SQLScripts/MigrateWorkerStatusToPaused.py

## Success Criteria

1. The `Workers.Status` column accepts three values: `Online`, `Draining`, `Paused`. The value `Offline` is no longer written by any code path. Existing `Offline` rows are migrated to `Paused` by an idempotent migration script.

2. The Activity page worker cards show two buttons per worker: **Online** and **Pause**. Clicking Pause on a worker with an active job sets `Status='Draining'`; clicking Pause on an idle worker sets `Status='Paused'` directly. There is no Draining or Offline button.

3. When a draining worker finishes its last active job, the worker process auto-writes `Status='Paused'` to its own Workers row. The badge transitions from amber "Draining" to grey "Paused" on the next UI poll without operator intervention.

4. The `GET /api/TeamStatus/Workers` response includes two independent fields per worker: `Status` (the DB column value: Online/Draining/Paused) and `IsAlive` (boolean derived from heartbeat freshness < 300s). The response no longer overwrites `Status` based on heartbeat.

5. Each worker card shows two independent indicators: an operational-state badge (Online=green, Draining=amber, Paused=grey) and a heartbeat dot (green <60s, amber 60s-300s, red >300s or null). The badge and dot are independent -- a Paused worker that is still heartbeating shows a green dot with a grey "Paused" badge.

6. Clicking Online on a Draining worker cancels the drain and resumes accepting jobs (transition: Draining -> Online).

7. The `POST /api/TeamStatus/Workers/<name>/Status` endpoint accepts `Online` and `Paused` as valid values. The UI sends `Paused`; the worker or API decides whether to transition through `Draining` based on whether the worker has active jobs. The endpoint no longer accepts `Offline` or `Draining` as direct inputs.

8. The bulk "All Online" and "Pause All" buttons in the Workers card header use the same two-value model (Online, Paused).

9. **[BUG-0004]** `Workers.Status` gates capability claiming, not just display. A worker whose `Status` is `Paused` MUST NOT claim ANY queue rows regardless of the individual capability flags (`TranscodeEnabled`, `RemuxEnabled`, `QualityTestEnabled`, `ScanEnabled`). A worker whose `Status` is `Draining` MUST NOT claim NEW queue rows but MUST finish any already-claimed in-flight work. A worker whose `Status` is `Online` claims according to its capability flags (current behavior). Verifiable: set `Workers.Status='Paused'` and `Workers.TranscodeEnabled=true` for a worker with the daemon running; queue a Transcode row; observe the row stays `Pending` and is NOT claimed by that worker within the capability-poll interval; logs show "capability stopped" / "Paused -- not claiming" for that worker. Then flip `Status='Online'`; observe the row claimed within the next poll cycle without any capability-flag change.

## Status

COMPLETE (2026-05-14)

### Progress
- [x] Feature doc drafted
- [x] Migration script (13 workers migrated Offline -> Paused)
- [x] TeamStatusController API fix (returns DB Status + IsAlive)
- [x] WorkerService status handling (Paused replaces Offline, drain auto-transitions)
- [x] StuckJobDetectionService updated (Offline -> Paused check)
- [x] Activity.html UI (Online/Pause buttons, heartbeat dot, badge map)
- [x] Flow doc updated
- [x] Deploy to larry + wakko (2026-05-14, commit 76a9810)
- [x] Verify on Activity page (2026-05-14, all workers showing correct status)
