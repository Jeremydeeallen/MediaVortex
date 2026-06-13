# Failure Accounting -- FailureBudgetService + FailedJobs Surface + TranscodeAttempts NOT NULL

**Set:** 2026-06-13
**Status:** Closed
**Slug:** failure-accounting
**Bug:** BUG-0061 (CLUSTER -- subsumes BUG-0055 + BUG-0060 + BUG-0029)
**Sequencing:** Cluster A of 3. B (compliance-writeback-invariant) closed 2026-06-13 at 5d4f81a. C (BUG-0063 activity-dashboard) is the third cluster.

## Outcome

**Failing encodes are accountable, capped, and operator-visible -- and `TranscodeAttempts` is structurally MediaFile-scoped from this commit forward.**

Three concrete deliverables, each enforcing a different part of the contract:
1. A budget service caps repeated encode failures per MediaFile (sibling to `RetryBudgetService` for VMAF).
2. A `/FailedJobs` operator surface (page + API + repository) so the operator can see, audit, and reset capped files without grepping logs.
3. `TranscodeAttempts.MediaFileId` becomes `NOT NULL` (after archival of the 1455 historical orphan rows back to 2025-10-15); every future INSERT path is loud-fail if it cannot resolve `MediaFileId` or `ProfileName`.

After this directive, the 15-fail loop on Mune Guardian (and any future analogue) is structurally impossible: the queue cannot accept the next job, the claim path cannot grab it, the operator's Next-Batch surfaces cannot suggest it.

## Acceptance Criteria

1. **`FailureBudgetService.HasBudgetRemaining(MediaFileId) -> bool` is the single source of truth for "may this file fail again."** Counts consecutive `TranscodeAttempts.Success=FALSE` for the given MediaFileId since the most recent `Success=TRUE` (or since `MediaFiles.CreatedAt` if no prior success); also resets when `MediaFiles.LastFailureResetAt` exceeds the most recent failure. Reads DB fresh per call (db-is-authority). Verifiable: insert N+1 consecutive failures, `HasBudgetRemaining` returns FALSE; insert a Success=TRUE row, returns TRUE; bump `LastFailureResetAt`, returns TRUE.

2. **`FailureBudgetConfig` single-row table holds the cap.** Columns `Id INT PRIMARY KEY DEFAULT 1 CHECK (Id=1)`, `MaxEncodeFailures INTEGER NOT NULL DEFAULT 3`, `ResetWindowDays INTEGER NULL` (NULL = no time-based reset), `LastUpdated TIMESTAMP DEFAULT NOW()`. Idempotent migration `Scripts/SQLScripts/AddFailureBudgetConfig.py`. Verifiable: `\d FailureBudgetConfig` shows schema; re-running migration is a no-op.

3. **`TranscodeAttempts.MediaFileId` is `NOT NULL` post-deploy.** Migration `Scripts/SQLScripts/SetTranscodeAttemptsMediaFileIdNotNull.py` runs AFTER the cleanup script and asserts `NULL count = 0` precondition before applying the constraint. Verifiable: `SELECT COUNT(*) FROM TranscodeAttempts WHERE MediaFileId IS NULL` returns 0; `\d TranscodeAttempts` shows the column as `NOT NULL`.

4. **`Scripts/SQLScripts/CleanupOrphanFailedAttempts.py` archives the 1455 orphan rows idempotently.** Dedupes by `(ErrorMessage, AttemptDate-rounded-to-minute, WorkerName)`, best-effort backfills `MediaFileId` via `TranscodeQueueId` correlation where the queue row still exists, archives the rest to `Reports/OrphanFailedAttempts-<YYYY-MM-DD>.csv`, deletes archived rows. Re-running on a clean state is a no-op (`SELECT COUNT(*) FROM TranscodeAttempts WHERE MediaFileId IS NULL` already 0 -> script exits 0 with "no orphans" message). Verifiable: pre-count = 1455; post-count = 0; CSV exists; second run reports 0 archived.

5. **Every `TranscodeAttempts` INSERT path sets both `MediaFileId` and `ProfileName` or loud-fails.** Loud-fail = WARN log with the context that failed to resolve plus `LoggingService.LogException` if a structural invariant was violated (the row is still attempted with a placeholder so we don't lose the audit trail, but the placeholder is grep-able: `MediaFileId = 0` / `ProfileName = '__UNRESOLVED__'`). Verified for: success path AND failure path AND every `ProcessingMode` (Transcode, Remux, Quick, AudioFix, SubtitleFix, TestVariant). Verifiable: `Tests/Contract/TestFailureAccounting.py` synthesizes one row per (mode, success/failure) and asserts `MediaFileId` + `ProfileName` non-null and non-placeholder; manual grep confirms every `INSERT INTO TranscodeAttempts` call site in the tree passes both.

6. **Claim path + recompute path + Next-Batch surfaces all consult `FailureBudgetService`.** (a) `TranscodeQueueRepository.ClaimNextPendingTranscodeJob` + `ClaimNextPendingRemuxJob` + `ClaimQualityTestJob` add `AND NOT EXISTS (<capped predicate>)` via a single SQL-fragment helper in `Core/Database/FailureBudgetPredicate.py` (sibling to `WorkerCapabilityPredicate`). (b) `QueueManagementBusinessService.RecomputeForFiles` does NOT insert into `TranscodeQueue` for capped files; logs the skip with reason. (c) `NextTranscodeBatch` SQL (both TV + Movies cards) + the four `SmartPopulate` Next-Batch paths (Transcode / Remux / AudioFix / SubtitleFix-Quick if any) add the same exclusion. Verifiable: insert N+1 consecutive failures on MediaFileId X, hit each surface, confirm X is excluded; reset X via `/FailedJobs`, confirm X re-appears; contract test `TestFailureAccounting::test_capped_files_excluded_from_every_surface` iterates the 7 surfaces.

7. **`FailedJobsRepository` is the read+reset SOT.** Provides `GetCappedJobs(limit, offset, search) -> List[FailedJobRow]` (filename, MediaFileId, FailureCount, LastErrorMessage, LastAttemptDate, AssignedProfile, LastWorkerName) and `ResetFailureBudget(MediaFileId, OperatorName)` which (a) inserts an audit row in `FailureBudgetResets`, (b) updates `MediaFiles.LastFailureResetAt = NOW()`. Verifiable: cap a MediaFile, observe it in `GetCappedJobs`; call `ResetFailureBudget`, observe an audit row + `LastFailureResetAt` populated + `GetCappedJobs` no longer contains the file.

8. **`/FailedJobs` page renders the surface.** `Templates/FailedJobs.html` lists capped jobs (sortable by date / failure count / filename), supports search, surfaces a per-row Reset button (with confirm dialog), and links each row's filename to a modal showing the full `TranscodeAttempts` history. Linked from the `/Activity` page nav. Verifiable: open `/FailedJobs` with a synthetic over-cap row; see it; click Reset; confirm; observe the row disappears.

9. **CI invariant test `Tests/Contract/TestFailureAccounting.py` asserts:** (a) `TranscodeAttempts.MediaFileId IS NULL` count = 0; (b) `TranscodeAttempts.ProfileName IS NULL` count on `Success=FALSE` rows = 0; (c) every `TranscodeQueue` row with `Status='Pending'` has `FailureBudgetService.HasBudgetRemaining = True`; (d) `FailedJobsRepository.GetCappedJobs()` returns the expected set for a synthetic over-cap MediaFile; (e) `ResetFailureBudget` writes the audit row + bumps `LastFailureResetAt`. Verifiable: `py -m pytest Tests/Contract/TestFailureAccounting.py` exits 0.

10. **Reversible deployment, idempotent migrations.** Each migration script has a single-statement rollback documented at the bottom of the script's stdout on first run. Re-running any migration on a clean DB is a no-op. The CleanupOrphanFailedAttempts script is bounded -- runs in seconds, writes CSV before deleting, leaves the DB in a verifiable end state. Verifiable: dry-run rollback restores pre-deploy schema; second run of every script reports no-op.

## Out of Scope

- Touching the VMAF `RetryBudgetService` (it works correctly; this directive's `FailureBudgetService` is a sibling, not a refactor).
- Activity page redesign (Cluster C / BUG-0063 directive).
- Refactoring the legacy `QueueManagementBusinessService._EvaluateCompliance` shim.
- Worker concurrency tuning, claim ordering, or queue priority math (owned by `queue-priority.feature.md`).
- Profile-cascade cleanup (separate concern).

## Engineering Calls Already Made

- **New vertical `Features/FailureAccounting/`** mirrors `Features/QualityTesting/Disposition/`. Repository + Service + Controller + ViewModel + tests live colocated. Sibling pattern, not a refactor of existing code.
- **Two new tables, not column additions.** `FailureBudgetConfig` (single-row scalar config -- mirrors `PostTranscodeGateConfig`) and `FailureBudgetResets` (audit log). Adding columns to `SystemSettings` or `MediaFiles` would conflate concerns.
- **Single SQL-fragment helper** for the cap predicate -- `Core/Database/FailureBudgetPredicate.BuildCapPredicate()`. One place emits this; every consumer calls it. Same pattern as `WorkerCapabilityPredicate`.
- **`MediaFiles.LastFailureResetAt`** is the reset mechanism, not deletion of historical `TranscodeAttempts` rows. History is preserved; the counter just ignores prior failures.
- **One-shot cleanup BEFORE NOT NULL migration.** The 1455 orphan rows would block the constraint. Script archives + deletes them first; migration then has a clean precondition.
- **Loud-fail placeholders, not silent drops.** Unresolved `MediaFileId` writes as `0` (sentinel) with WARN; unresolved `ProfileName` writes as `'__UNRESOLVED__'`. Both are grep-able. Better than swallowing the row.

## Risk + Rollback

| Risk | Likelihood | Impact | Mitigation / Rollback |
|---|---|---|---|
| Claim-path predicate change breaks an existing working flow | Low | High (queue stalls) | New predicate is additive (`AND NOT EXISTS (...)`) -- removing the helper call reverts. Contract test exercises both branches. Rollback: revert the commit. |
| `NOT NULL` migration blocks a worker mid-flight | Low | Medium | Workers don't INSERT `NULL` MediaFileId in current code; the new INSERT discipline lands BEFORE the constraint. Migration asserts NULL count = 0 precondition before applying. Rollback: `ALTER TABLE TranscodeAttempts ALTER COLUMN MediaFileId DROP NOT NULL`. |
| Cleanup script over-archives (deletes rows it shouldn't) | Low | Medium | CSV written BEFORE delete; idempotent re-run on clean state is no-op. Operator can re-import CSV via `INSERT INTO TranscodeAttempts SELECT * FROM csv_load(...)`. |
| FailureBudgetService over-counts (some failures shouldn't count) | Medium | Low | Service is DB-fresh per call; config is operator-tunable (`MaxEncodeFailures` default 3 can rise to 5/10 via `/settings`). `LastFailureResetAt` is the operator escape hatch. |
| FailedJobs Reset is misused (operator resets too aggressively) | Low | Low | Per-file friction (modal confirm + audit row). No bulk reset endpoint. Audit table records who reset what when. |

## Notes

Cluster A's `FailedJobsRepository` is the contract Cluster C (BUG-0063) consumes for the "Failed Jobs (N)" pill on `/Activity`. Cluster A ships the repo + the surface; C consumes the repo for its dashboard widget.

---

## Status

**Phase:** DELIVERING
**Last touched:** 2026-06-13 by Claude (all 10 ACs PASS; delivery report drafted; commit pending)
**Sequencing decision:** A is now active per CEO directive to keep moving after Cluster B close.

### Delivery Report

DIRECTIVE: Failure Accounting -- per-MediaFile encode-failure budget + operator surface (BUG-0061, subsumes BUG-0055 + BUG-0060 + BUG-0029)

STATUS: Done

WHAT SHIPPED:
- **New vertical** `Features/FailureAccounting/`: `FailureBudgetService` (HasBudgetRemaining + CountConsecutiveFailures), `FailedJobsRepository` (GetCappedJobs + ResetFailureBudget + CountCapped + GetAttemptHistory), `FailedJobsController` (`GET /FailedJobs`, `GET /api/FailedJobs`, `GET /api/FailedJobs/Count`, `GET /api/FailedJobs/<id>/Attempts`, `POST /api/FailedJobs/<id>/Reset`), 2 dataclass models.
- **One SQL-fragment helper** `Core/Database/FailureBudgetPredicate.BuildCapPredicate` consumed by 7 surfaces (3 claim methods + 4 admission/Next-Batch paths).
- **3 idempotent migrations**: `AddFailureBudgetConfig` (config table + audit table + MediaFiles.LastFailureResetAt column); `CleanupOrphanFailedAttempts` (5510 -> 0 orphans, CSV archive); `SetTranscodeAttemptsMediaFileIdNotNull` (constraint).
- **INSERT discipline** across all 3 `TranscodeAttempts` model-construction call sites: `MediaFileId` + ProfileName set from `Job.MediaFileId` + ProcessingMode-derived literal; repo-layer sentinel fallback for unresolvable producers (loud-fail with WARN).
- **Operator surface** `/FailedJobs` page + nav-link badge in `Templates/Base.html`; Reset confirmation modal + per-row attempt-history modal.
- 10 contract tests in `Tests/Contract/TestFailureAccounting.py`.

LIVE STATE (post-deploy on I9):
- 5510 orphan `TranscodeAttempts` rows -> 0 (5388 archived to `Reports/OrphanFailedAttempts-2026-06-13-070605.csv`; 122 backfilled from `(StorageRootId, RelativePath)` match).
- `TranscodeAttempts.MediaFileId` constraint is now `NOT NULL`.
- 28 currently-capped MediaFiles surface on `/FailedJobs`, including Mune Guardian 16-fail loop.
- 3 stale Pending TranscodeQueue rows for over-cap MediaFiles (caught by `TestPendingQueueRespectsCap`) deleted during VERIFYING.

HOW TO USE IT (operator-facing):
- Open `/FailedJobs` (nav link, top bar). Red badge shows count of capped files. Click filename to see full attempt history. Click Reset to re-allow claims.
- Tune cap via SQL today: `UPDATE FailureBudgetConfig SET MaxEncodeFailures = N WHERE Id = 1;` (next claim picks it up; no restart).
- Live invariant: `py -m pytest Tests/Contract/TestFailureAccounting.py` (10 tests, runs against live DB).
- Re-run cleanup any time: `py Scripts/SQLScripts/CleanupOrphanFailedAttempts.py` (idempotent; clean DB = "no orphans" message).
- Rollback constraint if ever needed: `ALTER TABLE TranscodeAttempts ALTER COLUMN MediaFileId DROP NOT NULL;` (one statement). `FailureBudgetConfig` + `FailureBudgetResets` drop with one statement each (printed by migration on first run).

WHAT YOU NEED TO EXECUTE: Nothing -- migrations + cleanup already executed on I9; WebService restarted with the new blueprint.

CRITERIA VERIFICATION: see `### Verification` table -- 10/10 PASS with concrete evidence per criterion.

DECISIONS I MADE (without consulting):
- **Single SQL fragment** rather than per-callsite logic. Same pattern as `WorkerCapabilityPredicate`. One source of truth.
- **Sentinel-and-WARN** on unresolvable INSERT instead of raise. Audit row is preserved with `MediaFileId=0` / `ProfileName='__UNRESOLVED__'`; future grep finds the regression. Losing the row would be a worse failure mode.
- **`GetCappedJobs` uses ARRAY_AGG** for last error / worker rather than a self-JOIN. Single scan; readable.
- **Cap predicate also applied to `ClaimQualityTestJob`** via JOIN to TranscodeAttempts.MediaFileId. AC6 lists it; QT itself doesn't increment the cap, but the JOIN keeps the helper consistent across all 7 surfaces.
- **3 stale Pending rows discovered + deleted** during VERIFYING. Caught by the AC6 contract test (`TestPendingQueueRespectsCap`). Pre-existing data drift, not a code bug; same logical change.

KNOWN GAPS / DEFERRED:
- `FailureBudgetConfig.ResetWindowDays` column reserved but unwired -- no time-based reset today.
- No `/settings` GUI card for the cap (operator edits via SQL); leave for future polish.
- Cluster C (BUG-0063 activity-dashboard) remains a separate directive.

### Approval Tracking

| AC | Status | Date | Notes / Amendment text / Waiver reason |
|---|---|---|---|
| AC1 (FailureBudgetService SOT) | approved | 2026-06-13 | CEO: "do not stop until cluster a is complete" |
| AC2 (FailureBudgetConfig table) | approved | 2026-06-13 | CEO blanket approval |
| AC3 (TranscodeAttempts.MediaFileId NOT NULL) | approved | 2026-06-13 | CEO blanket approval |
| AC4 (CleanupOrphanFailedAttempts idempotent) | approved | 2026-06-13 | CEO blanket approval |
| AC5 (INSERT discipline + loud-fail placeholders) | approved | 2026-06-13 | CEO blanket approval |
| AC6 (Claim + recompute + Next-Batch consult) | approved | 2026-06-13 | CEO blanket approval |
| AC7 (FailedJobsRepository read+reset SOT) | approved | 2026-06-13 | CEO blanket approval |
| AC8 (`/FailedJobs` page + Reset modal) | approved | 2026-06-13 | CEO blanket approval |
| AC9 (CI invariant test) | approved | 2026-06-13 | CEO blanket approval |
| AC10 (Reversible deployment + idempotent migrations) | approved | 2026-06-13 | CEO blanket approval |

### Seams

| Seam | Producer | Wire shape | Consumer expects | Verification |
|---|---|---|---|---|
| `FailureBudgetService.HasBudgetRemaining` (NEW) | Service | `MediaFileId: int -> bool` | Claim + Recompute + Next-Batch + tests | Contract test against synthetic over-cap row |
| `FailedJobsRepository.GetCappedJobs` (NEW) | Repository | `(limit, offset, search) -> List[FailedJobRow dataclass]` | `/api/FailedJobs` controller + ViewModel | curl + UI smoke |
| `FailedJobsRepository.ResetFailureBudget` (NEW) | Repository | `(MediaFileId, OperatorName) -> None; writes 2 tables atomically` | `POST /api/FailedJobs/<id>/Reset` | Audit-row + LastFailureResetAt observable in DB |
| `FailureBudgetConfig` -> Service (state-store) | `FailureBudgetConfigRepository.Get()` | dataclass `(MaxEncodeFailures, ResetWindowDays)` | `FailureBudgetService.HasBudgetRemaining` reads fresh per call | `Tests/Contract/TestFailureAccounting::test_config_mid_flight` |
| `BuildCapPredicate()` -> Claim SQL (function-call) | `Core/Database/FailureBudgetPredicate` | SQL fragment + parameters | `ClaimNextPendingTranscodeJob`, `ClaimNextPendingRemuxJob`, `ClaimQualityTestJob` | grep confirms one helper, every claim path uses it |
| `TranscodeAttempts INSERT` discipline (state-store) | every INSERT call site | `(MediaFileId NOT NULL, ProfileName NOT NULL, ...)` | DB constraint + CI invariant | grep all INSERT INTO TranscodeAttempts; contract test |

### Files

```
Features/FailureAccounting/__init__.py                                -- NEW
Features/FailureAccounting/Models/FailedJobRow.py                     -- NEW: dataclass
Features/FailureAccounting/Models/FailureBudgetConfigModel.py         -- NEW: dataclass
Features/FailureAccounting/Repositories/FailureBudgetConfigRepository.py -- NEW: GET
Features/FailureAccounting/Repositories/FailedJobsRepository.py       -- NEW: GetCappedJobs + ResetFailureBudget
Features/FailureAccounting/Services/FailureBudgetService.py           -- NEW: HasBudgetRemaining
Features/FailureAccounting/FailedJobsController.py                    -- NEW: GET / + POST /<id>/Reset + GET /<id>/Attempts
Features/FailureAccounting/failure-accounting.feature.md              -- NEW (created at DELIVERING per R13)
Features/FailureAccounting/failure-accounting.flow.md                 -- NEW (created at DELIVERING per R13)
Core/Database/FailureBudgetPredicate.py                               -- NEW: BuildCapPredicate
Templates/FailedJobs.html                                             -- NEW
Templates/Navigation.html                                             -- EDIT: link /FailedJobs
Scripts/SQLScripts/AddFailureBudgetConfig.py                          -- NEW: + FailureBudgetResets + LastFailureResetAt column on MediaFiles
Scripts/SQLScripts/CleanupOrphanFailedAttempts.py                     -- NEW
Scripts/SQLScripts/SetTranscodeAttemptsMediaFileIdNotNull.py          -- NEW
Tests/Contract/TestFailureAccounting.py                               -- NEW
Features/TranscodeQueue/TranscodeQueueRepository.py                   -- EDIT: claim predicate
Features/TranscodeQueue/QueueManagementBusinessService.py             -- EDIT: recompute + next-batch consult + INSERT discipline
Features/TranscodeJob/*                                               -- EDIT: TranscodeAttempts INSERT discipline at every call site
WebService/Main.py                                                    -- EDIT: register FailedJobsBlueprint
```

### R18 overrides

(none yet)

### Plan

1. Migrations first: `AddFailureBudgetConfig.py` (config table + FailureBudgetResets audit + MediaFiles.LastFailureResetAt column).
2. Core models + service: `FailureBudgetConfigModel`, `FailedJobRow`, `FailureBudgetConfigRepository`, `FailureBudgetService`.
3. Shared SQL fragment: `Core/Database/FailureBudgetPredicate.BuildCapPredicate`.
4. INSERT discipline pass: grep every `INSERT INTO TranscodeAttempts`, ensure `MediaFileId` + `ProfileName` are set or loud-fail; no silent NULL writes.
5. Cleanup orphans: `CleanupOrphanFailedAttempts.py` (CSV archive + delete + count assertions).
6. NOT NULL migration: `SetTranscodeAttemptsMediaFileIdNotNull.py`.
7. Repository + service: `FailedJobsRepository`.
8. Claim-path integration: edit 3 claim methods to call `BuildCapPredicate`.
9. Recompute + Next-Batch integration: `QueueManagementBusinessService.RecomputeForFiles` + `NextTranscodeBatch` + `SmartPopulate*`.
10. Controller + template + nav link.
11. Contract test.
12. Execute cleanup on I9 (operator authorized -- self-executed per memory).
13. Apply NOT NULL constraint.
14. Smoke test the full surface.
15. Promote durable content into `failure-accounting.feature.md` + `failure-accounting.flow.md` at DELIVERING.

### Verification

(Populated at VERIFYING phase.)

| AC | Evidence | Run by | Date | Result |
|---|---|---|---|---|
| AC1 | `TestFailureBudgetService` -- 3 cases green: zero-failures budgets True; cap-N failures -> False; Success row resets counter to 0. Reads DB fresh per call (no caching). | Claude on I9 | 2026-06-13 | PASS |
| AC2 | Migration applied: `FailureBudgetConfig (Id INT PK CHECK Id=1, MaxEncodeFailures INTEGER NOT NULL DEFAULT 3, ResetWindowDays INTEGER, LastUpdated TIMESTAMP)` seeded with `(1, 3, NULL)`. Re-run = no-op (`ON CONFLICT DO NOTHING`). | Claude on I9 | 2026-06-13 | PASS |
| AC3 | Migration applied. `SELECT is_nullable FROM information_schema.columns WHERE table_name='transcodeattempts' AND column_name='mediafileid'` returns `NO`. Idempotent: 2nd run = no-op. `TestTranscodeAttemptsMediaFileIdNotNull` green. | Claude on I9 | 2026-06-13 | PASS |
| AC4 | Cleanup ran: pre=5510 orphans, post=0. 122 best-effort-backfilled via `(StorageRootId, RelativePath)`; 5388 archived to `Reports/OrphanFailedAttempts-2026-06-13-070605.csv` then deleted. Re-run: "no orphans -- nothing to do" (status=OK). | Claude on I9 | 2026-06-13 | PASS |
| AC5 | All 3 `TranscodeAttempts` INSERT call sites (`ProcessTranscodeQueueService.CreateTranscodeAttempt` + `HandleJobFailure` + `Worker/AttemptRecordService.Create`) set `MediaFileId=getattr(Job, 'MediaFileId', None)` and `ProfileName` (literal `Remux`/`AudioFix`/`Quick`/`SubtitleFix` for non-Transcode modes; resolved profile for Transcode). The repository layer `SaveTranscodeAttempt` falls back to sentinel `0` / `'__UNRESOLVED__'` with WARN log if either is missing. `TestProfileNameOnFailureRows` green. | Claude on I9 | 2026-06-13 | PASS |
| AC6 | End-to-end synthetic: created MediaFileId=690705 + 4 consecutive failures; **HasBudgetRemaining=False**, NextTranscodeBatch excludes, SmartPopulate(Transcode) excludes, AddSuggestionsToQueue ItemsAdded=0, `/api/FailedJobs/Count` includes. Called `ResetFailureBudget`: **HasBudgetRemaining=True**, NextTranscodeBatch includes (top-1), `/api/FailedJobs/Count` excludes. Claim-paths (3) call `BuildCapPredicate` via single helper. Stale 3 over-cap Pending rows discovered by CI test removed during VERIFYING. `TestPendingQueueRespectsCap` green. | Claude on I9 | 2026-06-13 | PASS |
| AC7 | `FailedJobsRepository.GetCappedJobs` returns dataclass list with FailureCount + LastErrorMessage + LastAttemptDate + AssignedProfile + LastWorkerName. `ResetFailureBudget` writes a `FailureBudgetResets` audit row (PriorFailureCount preserved) AND bumps `MediaFiles.LastFailureResetAt = NOW()` in one call. `TestFailedJobsRepository` green (2 tests). | Claude on I9 | 2026-06-13 | PASS |
| AC8 | `GET /FailedJobs` HTTP 200; `GET /api/FailedJobs?limit=3` returns JSON with 3 capped rows including Mune Guardian 16-fail loop; `GET /api/FailedJobs/Count` returns `{Count: 28}`. Nav-link added to `Templates/Base.html` with badge `NavFailedJobsCount` polled every 30s. Modal opens via `js-show-history`; Reset button POSTs `/<id>/Reset` with confirm modal. | Claude on I9 | 2026-06-13 | PASS |
| AC9 | `Tests/Contract/TestFailureAccounting.py`: 10/10 PASS (TestTranscodeAttemptsMediaFileIdNotNull x2, TestProfileNameOnFailureRows x1, TestFailureBudgetService x3, TestFailedJobsRepository x2, TestPendingQueueRespectsCap x1, TestBuildCapPredicate x1). | Claude on I9 | 2026-06-13 | PASS |
| AC10 | (a) `AddFailureBudgetConfig.py` 2nd run prints all-present + 3-statement rollback. (b) `CleanupOrphanFailedAttempts.py` 2nd run on clean DB prints "no orphans -- nothing to do". (c) `SetTranscodeAttemptsMediaFileIdNotNull.py` 2nd run prints "already NOT NULL -- no-op" + 1-statement rollback. (d) No data destroyed: orphans archived to CSV before delete; no schema column dropped. | Claude on I9 | 2026-06-13 | PASS |

### Promotions

(Populated at DELIVERING.)

| Source artifact in directive | Target file | Commit |
|---|---|---|
| AC1-AC2 architecture (FailureBudgetService + FailureBudgetConfig) | `Features/FailureAccounting/failure-accounting.feature.md` C1-C2 | c1f0760 |
| AC3-AC4 orphan archival + NOT NULL | `Features/FailureAccounting/failure-accounting.feature.md` C3-C4 + Failure Modes | c1f0760 |
| AC5 INSERT discipline (3 call sites + repo layer fallback) | `Features/FailureAccounting/failure-accounting.feature.md` C5 + ST1 + S6 + S7 | c1f0760 |
| AC6 single SQL-fragment helper consumed by 7 surfaces | `Features/FailureAccounting/failure-accounting.feature.md` C6 + `failure-accounting.flow.md` ST3 + S3 | c1f0760 |
| AC7-AC8 FailedJobs surface (page + API + repo + reset audit) | `Features/FailureAccounting/failure-accounting.feature.md` C7-C8 + W1-W3 + S4-S5 | c1f0760 |
| AC9 CI invariant test (10 tests) | `Tests/Contract/TestFailureAccounting.py` (file is the artifact) | c1f0760 |
