# Activity, Admin, and Worker Telemetry

**Slug:** activity-admin-and-worker-telemetry
**Set:** 2026-06-23
**Status:** Active -- phase: IMPLEMENTING

## Discovery (NEEDS_DOC_PREREAD findings, 2026-06-23)

Reading `WorkerService/WorkerService.flow.md` (ST9 + S4), `worker-lifecycle.feature.md` (C2 + C3), and `WorkerService/Main.py:_HealthCheckLoop` confirms:

- **C4 (worker self-report) is ALREADY IMPLEMENTED.** Each WorkerService process runs a `_HealthCheckLoop` thread that calls `WorkersRepository.UpdateWorkerHeartbeat(self.WorkerName)` direct-to-DB every 30s. WebService is not in this path. Bringing WebService down does not affect heartbeat writes.
- **C5 (heartbeat-staleness as derived UI concept) is ALREADY TRUE.** Per `worker-lifecycle.feature.md` C3, `Offline` is NOT a column value -- it is a UI-derived state when `(NOW() - LastHeartbeat) > HeartbeatStaleThresholdSec`.
- **C6 (Stopped enum migration) is SUPERSEDED by `worker-lifecycle.feature.md`** which already simplified the worker enum to `Online`/`Paused` only. Current DB confirms: `SELECT DISTINCT Status FROM Workers` returns `Online` + `Paused`. No `Draining`/`Stopped`/`Offline` rows exist. Migration NOT NEEDED.
- **`SystemSettings.HeartbeatStaleThresholdSec=300`** + **`StaleProgressThresholdSec=15`** already seeded.
- **`Features/Activity/Services/ProgressSmoothingService.py`** + **`DashboardSnapshotService.py`** already exist. C9 (smoothing) is partially or fully shipped.

So the directive's real surface narrows. Criteria revised below.

## Revised Acceptance Criteria

C1. `/Activity` page contents whitelist: ONLY Active Transcode Jobs, Active Scans, QT Progress, queue counts. Worker tiles + Library Compliance card + AudioVerticalHealth sub-section removed from `Templates/Activity.html`. Verifiable: `grep -c -E 'Worker|Compliance|AudioVerticalHealth' Templates/Activity.html` returns 0 (case-sensitive code grep; non-code text mentions OK).

C2. `/Admin/Workers` new route + template. Renders worker tiles + Online/Paused action buttons (operating on the existing two-state model per `worker-lifecycle.feature.md`). Subnav at `Templates/_admin_subnav.html` gains a Workers link. `curl /Admin/Workers` returns 200.

C3. `/Admin/Compliance` new route + template. Library compliance card + AudioVerticalHealth sub-section move from `/Activity` to here. Subnav gains a Compliance link. `curl /Admin/Compliance` returns 200.

C4. Worker self-report verified resilient: kill WebService, observe `Workers.LastHeartbeat` continues to advance for at least 90 seconds on a live worker. (Already implemented per discovery; this criterion just adds the verification step + an integration test.)

C5. `/Compliance` top-level URL responds with 301 redirect to `/Admin/Compliance`. Verifiable: `curl -I /Compliance` returns `301` + `Location: /Admin/Compliance`.

C6. SRP-clean new units (per the SOLID plan above): `AdminWorkersController` + `AdminWorkersRepository` + `AdminComplianceController` + `AdminComplianceRepository` are each their own file, constructor-DI, narrow public surface.

C7. Doc consolidation per the single-source-of-truth rule:
  - `Features/Activity/activity-dashboard-improvements.feature.md` pruned: sections whose criteria the system already satisfies (or this directive moves) are replaced with a single-line pointer.
  - New `Features/Admin/Workers/admin-workers.feature.md` documents the new sub-tab.
  - New `Features/Admin/Compliance/admin-compliance.feature.md` documents the new sub-tab.
  - `Features/Activity/activity.feature.md` updated to reflect the refocused contract (sections that mention Workers / Compliance get removed or pointed at the admin docs).

C8. Contract tests under `Tests/Contract/`:
  - `TestActivityContentsRefocus.py`: grep `Templates/Activity.html`; assert Workers + Compliance markup absent.
  - `TestAdminWorkersEndpoint.py`: curl `/Admin/Workers` 200; payload contains worker tiles.
  - `TestAdminComplianceEndpoint.py`: curl `/Admin/Compliance` 200; payload contains compliance card data.
  - `TestComplianceRedirect.py`: `/Compliance` returns 301 to `/Admin/Compliance`.
  - `TestWorkerSelfReportResilience.py` (integration; runs against live DB): records `LastHeartbeat` snapshot, asserts at least one worker's heartbeat advances in a 60s window (verifies the always-on heartbeat thread is independent of WebService).

C9. **Regression gate**: `Scripts/Smoke/ThreeOfEachBucketSmoke.py` still passes 9/9 after the refactor.
**Subsumes/adopts:** `BUG-0063` cluster (memory/KNOWN-ISSUES.md) which already drafted C1-C22 in `Features/Activity/activity-dashboard-improvements.feature.md`. This directive adopts that work and adds the operator-stated relocations + worker-self-reporting decoupling.

## Outcome (operator-stated 2026-06-23)

1. **Perfect, SOLID `/Activity` page.** Only activity-related content lives there: active transcode jobs, active VMAF, active scans, queue counts, ETA/FPS smoothing, drain-visible jobs. Everything else moves.
2. **Workers move to `/Admin/Workers`** as a new admin sub-tab. Pulls `Workers` row data, status badges, per-worker action buttons (Online/Drain/Stop). No worker UI surface remains on `/Activity`.
3. **Compliance moves to `/Admin/Compliance`** as a new admin sub-tab. Library compliance card, bucket counts, AudioVerticalHealth sub-section. No compliance card remains on `/Activity`.
4. **Workers self-report status to DB.** WebService outage MUST NOT obscure worker truth: when the WebService is down the operator can still observe worker liveness because each worker writes its own heartbeat / status row directly to PostgreSQL. The WebService is a pure consumer of these rows -- never an authority.
5. **Old documentation deleted.** Per the single-source-of-truth rule, any prose duplicated by the rewrite is pruned and replaced with a pointer.

## Acceptance Criteria

C1. **`/Activity` contents whitelist enforced.** Page renders ONLY: Active Transcode Jobs panel (with FPS smoothing + ETA countdown + drain-visible jobs per BUG-0063 C1-C7), Active Scans, QT Progress, queue-count summary. The Workers card + LibraryCompliance card + AudioVerticalHealth sub-section are REMOVED from `Templates/Activity.html`. Verifiable: `grep -E 'Worker|Compliance|AudioVerticalHealth' Templates/Activity.html` returns 0 hits.

C2. **`/Admin/Workers` exists.** New route + template. Reads `Workers` table fresh per request via existing `TeamStatusController` / `ActivityRepository.GetWorkerTiles` shape; renders the worker tiles + action buttons (Online/Drain/Stop) that previously lived on `/Activity`. Subnav at `Templates/_admin_subnav.html` gains a Workers link. Verifiable: `curl /Admin/Workers` returns 200 and the rendered HTML contains all `Workers` rows.

C3. **`/Admin/Compliance` exists as a sub-tab.** The existing `/Compliance` page becomes `/Admin/Compliance`; library-compliance card + bucket-count breakdown + AudioVerticalHealth sub-section move from `/Activity` to this page. Subnav gains a Compliance link. Verifiable: `curl /Admin/Compliance` 200; the LibraryCompliance card renders the same shape it does today.

C4. **Worker self-report telemetry decoupled from WebService.** Each `WorkerService` process writes its own row to `Workers.LastHeartbeat` + `Workers.Status` directly via DB connection -- no HTTP hop through WebService. Verifiable: kill WebService on I9; observe `Workers.LastHeartbeat` for active workers continue to update within their cadence (default 30s). Bring WebService back; `/Admin/Workers` renders accurate state immediately (data was written while it was down).

C5. **Heartbeat staleness is a derived UI concept, not a column write.** `Workers.Status` reflects operator-set state only (`Online` / `Draining` / `Stopped`). Connectivity (process reachable / unreachable) is computed at render time as `(NOW() - LastHeartbeat) vs SystemSettings.HeartbeatStaleThresholdSec` (default 300s). Implements BUG-0063 C5 + C11.

C6. **`Workers.Status` migration adds `Stopped` terminal value** (BUG-0063 C6, C8). `Scripts/SQLScripts/RenameWorkerStatusOfflineToStopped.py` runs idempotently. `_DrainAndStop` writes `Status='Stopped'` post-drain.

C7. **Data-driven status renderer** (BUG-0063 C9, C10). Single JS table maps `Workers.Status -> {Label, BadgeClass, Tooltip}`. Unknown values render with `bg-secondary` + raw string. No code change required to introduce a new Status value.

C8. **Single dashboard snapshot endpoint per page.** `/Activity` polls `/api/Activity/Snapshot` once per 5s (BUG-0063 C1; existing C3 in `activity.feature.md`); `/Admin/Workers` polls a new `/api/Admin/Workers/Snapshot` once per 5s; `/Admin/Compliance` polls `/api/Admin/Compliance/Snapshot` once per 5s. Each endpoint returns its full payload in one round-trip. No per-panel ad-hoc fetches. Verifiable: DevTools Network tab on each page shows exactly one XHR per 5s tick.

C9. **`ProgressSmoothingService` ships** (BUG-0063 C2). Rolling arithmetic mean of CurrentFPS / CurrentSpeed per `TranscodeAttemptId` over the lesser of 10 samples / 30 seconds. Stale-sample threshold `SystemSettings.StaleProgressThresholdSec` (default 15s); past threshold emits NULL. Constructor-injected `(ProgressRepository, SystemSettingsRepository, Clock)`. New unit `Features/Activity/Services/ProgressSmoothingService.py`.

C10. **`ETACountdownTimer` ships** client-side (BUG-0063 C6). Per-job timer decrements 1s/sec between polls; on each poll, `|delta| <= 5s` -> client smooth; `> 5s` -> client snaps to server. Renders `--:--:--` when smoothed FPS is unavailable.

C11. **ActiveJobs and Workers views are decoupled** (BUG-0063 C3). `ActiveJobsViewModel` rows come from `ActiveJobs WHERE TranscodeAttempts.Success IS NULL` joined to `Workers` for display name only, NEVER filtered by `Workers.Status`. A job claimed by a `Draining` worker keeps showing progress until the job actually terminates.

C12. **Per-job progress isolation** (BUG-0063 C7). `TranscodeProgress` rows keyed by `TranscodeAttemptId`; no worker-name fallback / most-recent shortcut. Two concurrent jobs on the same worker NEVER show each other's progress.

C13. **Dead UI removed** (BUG-0063 C4, C5). `Stop After This Job` button + `StopAfterJob()` JS + `POST /api/Transcode/Stop` + `SetTranscodingStopped()` helper deleted. `Resume` button deleted iff `git grep` finds no live caller.

C14. **Old documentation deleted.** Per the no-duplication rule (memory `feedback_single_source_of_truth.md`): `activity-dashboard-improvements.feature.md` content is reviewed; the SOLID-rewrite criteria that this directive fully implements get pruned and replaced with a pointer to the post-directive Activity contract. Three new doc surfaces are scaffolded:
  - `Features/Activity/activity.feature.md` -- becomes the canonical Activity page contract (refocused).
  - New `Features/Admin/Workers/admin-workers.feature.md` -- the new admin sub-tab.
  - New `Features/Admin/Compliance/admin-compliance.feature.md` -- the new admin sub-tab.
  Verifiable: every section in `activity-dashboard-improvements.feature.md` either points at one of the three new docs or is the existing-but-still-relevant prose.

C15. **`Stopped` worker still heartbeats.** Per BUG-0063 C5: a Stopped worker process can still be alive (and still writing heartbeats) -- the operator can stop the worker without killing the process. Connectivity dot shows green; status badge shows Stopped. Verifiable: set a worker to Stopped via the UI; observe LastHeartbeat still updates; observe both indicators independently.

C16. **3-of-each smoke still passes** (regression gate). The closed `filereplacement-drain-bug` directive's smoke (`Scripts/Smoke/ThreeOfEachBucketSmoke.py`) -- 3 Transcode + 3 Remux + 3 AudioFix end-to-end to IsCompliant=True -- must still pass after this directive lands. Catches any worker-telemetry change that breaks claim/dispatch.

C17. **SOLID at the touch points.** Each new responsibility lives in its own class:
  - `ProgressSmoothingService` -- rolling-window math only
  - `WorkerHeartbeatService` -- worker-side periodic writer (NEW; lives in WorkerService)
  - `AdminWorkersController` / `AdminWorkersRepository` -- new sub-tab surface
  - `AdminComplianceController` / `AdminComplianceRepository` -- new sub-tab surface
  - `DashboardSnapshotService` (existing) refactored to one method per snapshot endpoint
  Constructor DI throughout. No god-functions added to `ActivityController` / `TeamStatusController` / `WorkerService.Main`.

## Locked Decisions (2026-06-23)

- **Heartbeat cadence**: 30s write, 300s stale threshold. 10x oversampling.
- **`/Compliance` route**: 301 redirect to `/Admin/Compliance` for one release.

## SOLID Compliance Plan

Every new unit obeys SRP + constructor DI. Concrete per-class scope:

| Class | Single Responsibility | Constructor injections | Public surface |
|---|---|---|---|
| `WorkerHeartbeatService` (NEW, WorkerService side) | Periodic heartbeat write to `Workers.LastHeartbeat`; nothing else | `(Db, Clock, IntervalSec)` | `Start()`, `Stop()` |
| `WorkerStatusReporter` (NEW, WorkerService side) | Direct-DB status writes (`Online`/`Draining`/`Stopped`) | `(Db, WorkerName)` | `WriteStatus(Status)` |
| `ProgressSmoothingService` (NEW, Activity side) | Rolling-window arithmetic mean of FPS/Speed; NOT responsible for fetching progress rows | `(ProgressRepository, SystemSettingsRepository, Clock)` | `Smooth(AttemptId) -> {Fps, Speed}` |
| `AdminWorkersRepository` (NEW) | Read worker tile data only | `(Db,)` | `GetTiles()`, `GetTile(WorkerName)` |
| `AdminWorkersController` (NEW) | HTTP routing + JSON envelope | `(AdminWorkersRepository,)` | Blueprint with `/Admin/Workers` + `/api/Admin/Workers/Snapshot` |
| `AdminComplianceRepository` (NEW) | Library-compliance card SQL | `(Db,)` | `GetCard()`, `GetAudioVerticalHealth()` |
| `AdminComplianceController` (NEW) | HTTP routing + JSON envelope | `(AdminComplianceRepository,)` | Blueprint with `/Admin/Compliance` + `/api/Admin/Compliance/Snapshot` |
| `DashboardSnapshotService` (REFACTOR existing) | Activity-only payload assembly (workers/compliance moved out) | `(ActivityRepository, ProgressSmoothingService, SystemSettingsRepository)` | `BuildSnapshot()` |
| `ActivityRepository` (REFACTOR existing) | Active jobs + active scans only (workers + compliance removed) | `(Db,)` | `GetActiveJobs()`, `GetActiveScans()`, `GetQueueCounts()` |

Anti-patterns explicitly avoided:
- No `self._cached_*` in any `__init__` (R3).
- Workers + Compliance data never re-imported by `ActivityRepository` after the move (kills the "while I'm here" temptation to keep a backward-compat shim).
- `WorkerHeartbeatService.Run` is a single while-loop -- no inline orchestration logic, no embedded retry policy. Retry policy lives in DatabaseService.
- Templates split: `AdminWorkers.html` + `AdminCompliance.html` are NEW; `Activity.html` is REFACTORED (sections removed, not copy-pasted into the new templates -- they fetch from their own endpoints).

## Hook-Avoidance Pre-Flight

Plan to NOT trip the PreToolUse hook. Concrete moves per rule:

| Rule | Risk surface | Mitigation |
|---|---|---|
| R1 (Doc preread) | Editing `Templates/Activity.html` requires reading colocated docs in `Templates/`; editing `Features/Activity/*.py` requires reading every `Features/Activity/*.feature.md` + `*.flow.md`; same pattern for new `Features/Admin/Workers/` + `Features/Admin/Compliance/`. | Read every colocated doc in NEEDS_DOC_PREREAD phase BEFORE first code edit. Partial reads (`limit<=50`) per R18; use `# see <slug>.<ID>` anchors when only a section is needed. |
| R12 (Comment/docstring volume) | Every new class has a temptation for a docstring block. | Single-line class docstring at most; per-method WHY-only comments capped at one line; no module-level docstrings. |
| R13 (No new feature.md outside DELIVERING) | The 3 new feature docs (`admin-workers.feature.md`, `admin-compliance.feature.md`, refocused `activity.feature.md`) MUST land at DELIVERING phase only. | NEEDS_DOC_PREREAD reads existing docs; IMPLEMENTING writes code + tests; DELIVERING writes the 3 new feature docs + prunes `activity-dashboard-improvements.feature.md`. |
| R14 (No annotation lines on feature.md edits) | Pruning `activity-dashboard-improvements.feature.md` -- cannot add `removed YYYY-MM-DD` markers. | Delete superseded sections cleanly. Replace with one-line pointer to the post-directive doc. |
| R15 (directive anchor) | Every edit to a function/class in the ## Files list needs `# directive: activity-admin-and-worker-telemetry` directly above the `def`/`class`. | Carry the anchor pattern from prior closed directives (e.g. compliance-symmetry). |
| R16 (Slug in first 15 lines) | The 3 new feature docs (and the refocused activity.feature.md if rewritten) need `**Slug:** ...` near the top. | Template every new feature doc with the slug line at line 3. |
| R18 (Read budget) | All feature doc reads `limit<=50`. | Use offset/limit per the existing pattern. |

## Implementation Order (de-risked sequencing)

1. **Schema first**: `RenameWorkerStatusOfflineToStopped.py` + new SystemSettings rows (`HeartbeatStaleThresholdSec=300`, `StaleProgressThresholdSec=15`).
2. **Worker self-report**: `WorkerHeartbeatService` + `WorkerStatusReporter` SRP classes; wire into `WorkerService/Main.py`. **Smoke**: kill WebService on I9, observe LastHeartbeat keeps updating.
3. **Backend admin surfaces**: `AdminWorkersController` + `AdminWorkersRepository` + `AdminComplianceController` + `AdminComplianceRepository`. Register blueprints. **Smoke**: curl new endpoints.
4. **Frontend admin pages**: `AdminWorkers.html` + `AdminCompliance.html` + subnav links. **Smoke**: visit each page in browser.
5. **`/Compliance` 301 redirect**: keep old URL working for one release.
6. **ProgressSmoothingService** + `ETACountdownTimer` JS + data-driven status renderer.
7. **Refocus `/Activity`**: remove Worker + Compliance sections from `Templates/Activity.html`. Update `DashboardSnapshotService` to drop those payload keys.
8. **Remove dead UI**: StopAfterJob, Resume, related endpoints/helpers.
9. **Contract tests**: 5 new under `Tests/Contract/`.
10. **Regression gate**: re-run `Scripts/Smoke/ThreeOfEachBucketSmoke.py` to prove the worker-telemetry refactor didn't break the pipeline.
11. **VERIFYING**: collect per-criterion evidence.
12. **DELIVERING**: write the 3 new feature docs (R13 only allows at this phase) + prune `activity-dashboard-improvements.feature.md` to pointer.

## R18 overrides

(none yet)

## Files (placeholder -- finalized at NEEDS_PLAN exit; subject to NEEDS_DOC_PREREAD requirement)

| File | Role | Criterion |
|---|---|---|
| `Templates/Activity.html` | Refocus: remove Workers + Compliance + AudioVerticalHealth sections | C1, C13 |
| `Features/Admin/Workers/AdminWorkersController.py` | NEW -- /Admin/Workers route + snapshot endpoint | C2, C8 |
| `Features/Admin/Workers/AdminWorkersRepository.py` | NEW -- single-shot tile data | C2 |
| `Templates/AdminWorkers.html` | NEW -- worker tiles UI | C2, C7, C15 |
| `Features/Admin/Compliance/AdminComplianceController.py` | NEW -- /Admin/Compliance route + snapshot endpoint | C3, C8 |
| `Features/Admin/Compliance/AdminComplianceRepository.py` | NEW -- compliance card data | C3 |
| `Templates/AdminCompliance.html` | NEW -- moved compliance card | C3 |
| `Templates/_admin_subnav.html` | Add Workers + Compliance links | C2, C3 |
| `WebService/Main.py` | Register new blueprints; deprecate `/Compliance` top-level | C2, C3 |
| `WorkerService/Main.py` | Move heartbeat writer to direct-DB path; remove HTTP self-report | C4, C6 |
| `WorkerService/Services/WorkerHeartbeatService.py` | NEW -- direct-DB heartbeat writer (SRP) | C4, C17 |
| `Features/Activity/Services/ProgressSmoothingService.py` | NEW -- rolling-window FPS/Speed | C9, C17 |
| `Features/Activity/ActivityController.py` | DashboardSnapshotService refactor; remove worker + compliance routes | C8, C11 |
| `Features/Activity/ActivityRepository.py` | Remove `GetWorkerTiles` + `GetLibraryCompliance` (moved); keep ActiveJobs | C11, C12 |
| `Scripts/SQLScripts/RenameWorkerStatusOfflineToStopped.py` | NEW migration | C6 |
| `Features/Activity/activity.feature.md` | Refocused contract | C14 |
| `Features/Activity/activity-dashboard-improvements.feature.md` | Pruned -- pointer to refocused activity doc | C14 |
| `Features/Admin/Workers/admin-workers.feature.md` | NEW feature doc | C14 |
| `Features/Admin/Compliance/admin-compliance.feature.md` | NEW feature doc | C14 |
| `Tests/Contract/TestActivityContents.py` | NEW: assert /Activity has no Worker/Compliance markup | C1, C13 |
| `Tests/Contract/TestAdminWorkersEndpoint.py` | NEW: /Admin/Workers + snapshot endpoint | C2 |
| `Tests/Contract/TestAdminComplianceEndpoint.py` | NEW: /Admin/Compliance + snapshot endpoint | C3 |
| `Tests/Contract/TestWorkerSelfReport.py` | NEW: WebService-down resilience check | C4, C5 |
| `Tests/Contract/TestActivitySolidStructure.py` | NEW: grep-based SRP checks (no god-functions in ActivityController) | C17 |

## R18 overrides

(none yet)

## Status

### Progress
- [ ] NEEDS_PLAN: read existing flow + feature docs, finalize criteria + Files
- [ ] NEEDS_DOC_PREREAD: read every colocated *.feature.md / *.flow.md for files in ## Files
- [ ] IMPLEMENTING: schema migration + refactor + new controllers + new templates + tests + doc consolidation
- [ ] VERIFYING: per-criterion evidence; 3-of-each smoke re-run as regression gate
- [ ] DELIVERING: promotions table + close report

NEEDS_PLAN. Awaiting operator approval of criteria + Files list before advancing to NEEDS_DOC_PREREAD.
