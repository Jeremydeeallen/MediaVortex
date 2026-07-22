# scanners.feature.md

**Slug:** scanners

## What It Does

Shared orchestrator for every periodic-DB-scan service in MediaVortex.
One row in the `Scanners` table per service. Each service reads its
row fresh per cycle (`db-is-authority`) for `Enabled`, `IntervalSec`,
`BatchSize`, `DryRun`. The operator controls all of them from one
page (`/Admin/Scanners`). Adding a new periodic scan service = one
INSERT into `Scanners` + one Repository read in the new service's
loop. No new control-plane code per service.

## Workflows

| #  | User action | Surface | Handler | Backing |
|----|-------------|---------|---------|---------|
| W1 | View every scanner + its state | `/Admin/Scanners` page | `GET /Admin/Scanners` | `Features/FileScanning/ScannersController.render_page` |
| W2 | Toggle a scanner Enabled / change Interval / BatchSize / DryRun | per-row Save button | `POST /api/Scanners/<name>` | `Features/FileScanning/ScannersController.update_scanner` |
| W3 | Master kill switch ("Pause all") | red button | `POST /api/Scanners/PauseAll` | `ScannersRepository.PauseAll` |
| W4 | Read scanner state from a daemon loop | n/a (in-process) | `ScannersRepository.Get(Name)` per cycle | `Features/FileScanning/ScannersRepository.Get` |

## Success Criteria

C1. Every periodic-scan service in the codebase reads its config from
the `Scanners` table per cycle, not from process-level constants or
SystemSettings keys. Test: `grep -rn 'while True' Features/` to find
loops; each one must `ScannersRepository().Get(<name>)` inside its
body.

C2. Adding a new scanner is one migration + one row. The control
surface (page, API, persistence) does not need per-service work.

C3. `DryRun=True` on any scanner row means the scanner runs its
detection / probe phase but skips its remediation / write phase, and
records a `DRY_RUN: would have done X` audit note. The contract is
that DryRun is observable but inert.

C4. `Pause all` flips every `Enabled=TRUE` row to FALSE in one
statement. Returns the count of rows that were Enabled. Idempotent on
already-paused tables.

## Seams

| ID | Seam | Producer | Wire shape | Consumer | Verification |
|---|---|---|---|---|---|
| S1 | Repository -> ScannerLoop | `ScannersRepository.Get(Name)` | dict `{ScannerName, Enabled, IntervalSec, BatchSize, DryRun, LastRunAt, LastUpdated}` keys all PascalCase | Each scanner's loop reads `Enabled` / `IntervalSec` / `BatchSize` / `DryRun` fresh per iteration | `TestScannersRepository.test_update_round_trips` |
| S2 | UI -> Repository | `Templates/Scanners.html` Save button | POST `/api/Scanners/<name>` body `{Enabled, IntervalSec, BatchSize, DryRun}` PascalCase | `ScannersController.update_scanner` calls `ScannersRepository.Update`; clamps IntervalSec >= 60 and BatchSize >= 1 | live: API round-trip GET -> POST -> GET |
| S3 | ScannerLoop -> Repository (heartbeat) | scanner records `LastRunAt` after each successful cycle | `ScannersRepository.RecordRun(Name)` -> SQL `UPDATE Scanners SET LastRunAt = NOW()` | Operator sees freshness on `/Admin/Scanners` | live UI |

## Status

Seeded scanners at ship time:
- `ContinuousScan` (Enabled=TRUE; FileScanning periodic file discovery)

### Files

- `Scripts/SQLScripts/CreateScannersConfig.py` -- idempotent migration
- `Features/FileScanning/ScannersRepository.py` -- Get / List / Update / RecordRun / PauseAll
- `Features/FileScanning/ScannersController.py` -- GET/POST endpoints + page render
- `Templates/Scanners.html` -- per-row inline editor + master Pause-all
- `Tests/Contract/TestScannersRepository.py` -- live-DB contract tests
