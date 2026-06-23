# Activity, Admin, and Worker Telemetry

**Slug:** activity-admin-and-worker-telemetry
**Set:** 2026-06-23
**Status:** Active -- phase: NEEDS_PLAN
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

## Open Decisions (pending operator confirmation)

- **Heartbeat cadence**: BUG-0063 says default 300s for stale threshold. Worker write cadence: 30s? 60s? Suggest 30s (matches existing `ServiceStatusTracker` thread cadence) -- 10x oversampling on the 300s stale window.
- **Backward compat for `/Compliance`** (currently a top-level route per `WebService/Main.py` line 490): keep as a 301 redirect to `/Admin/Compliance`, or hard-remove? Suggest 301 redirect for one release window so operator bookmarks don't break.

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
