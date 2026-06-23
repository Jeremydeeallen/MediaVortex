# Admin / Workers

**Slug:** admin-workers

## What It Does

Renders the operator-facing worker fleet at `/Admin/Workers`. Displays per-worker tile with operator-set Status badge (Online / Paused) and an independent connectivity dot derived from heartbeat freshness. Each tile carries Online / Pause action buttons; clicks POST to `/api/TeamStatus/Workers/<name>/Status` and refresh.

Pure consumer of `Workers` rows. Workers self-report their `LastHeartbeat` and `Status` directly to PostgreSQL via the WorkerService process -- WebService is not in the telemetry path. Killing WebService does not affect what is shown on a future page load.

## Surface

- Operator visits `/Admin/Workers`.
- Page polls `/api/Admin/Workers/Snapshot` every 5s.
- Subnav link in `Templates/_admin_subnav.html`.

## Success Criteria

C1. `/Admin/Workers` returns HTTP 200 and renders one tile per row in `Workers WHERE Enabled = TRUE`. Verifiable: `curl -I /Admin/Workers` -> 200; page source contains every enabled worker's name.

C2. `/api/Admin/Workers/Snapshot` returns `{Success, Data: {Workers, HeartbeatStaleThresholdSec}}`. `Workers` is a list of dicts with `WorkerName`, `Status`, `LastHeartbeat`, `HeartbeatAgeSec`, capability flags, `Version`. Verifiable: `curl /api/Admin/Workers/Snapshot | jq '.Data | keys'`.

C3. Status badge maps `Online` -> green, `Paused` -> amber. Unknown values render grey with the raw string. Driven by JS data table, no per-status code path. Verifiable: `UPDATE Workers SET Status='Maintenance'` -- the badge displays `Maintenance` in grey without code change.

C4. Connectivity dot is derived: green when `HeartbeatAgeSec <= HeartbeatStaleThresholdSec`, red otherwise. Independent of Status badge. Verifiable: a Paused worker with fresh heartbeat shows green dot + amber Status; a worker whose process is dead shows red dot regardless of badge.

C5. Tile actions: Online / Pause buttons POST to `/api/TeamStatus/Workers/<name>/Status`. Page re-fetches snapshot on success. Verifiable: click Pause; the badge flips to amber on the next poll.

## Files

| File | Role |
|------|------|
| `Features/Admin/Workers/AdminWorkersController.py` | Blueprint with `/Admin/Workers` route + `/api/Admin/Workers/Snapshot` endpoint |
| `Features/Admin/Workers/AdminWorkersRepository.py` | Single-shot tile data (SRP) |
| `Templates/AdminWorkers.html` | Tile renderer; subnav include; 5s polling JS |
| `Templates/_admin_subnav.html` | Workers link |

## Status

ACTIVE 2026-06-23. Tests: `Tests/Contract/TestAdminWorkersEndpoint.py` covers the page + snapshot shape.
