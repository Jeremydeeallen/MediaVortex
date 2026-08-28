# Directive: bug-0061-remediation

**Status:** Closed

**Slug:** bug-0061-remediation

## Outcome

Close BUG-0061 completely. All three failing contract tests pass. `TranscodeAttempts.MediaFileId` is `NOT NULL`. Orphan-attempt population is zero. ForceAdd never leaves a queue row unclaimable.

## Motivation

BUG-0061 shipped code + docs on 2026-06-13 but three gaps remain, evidenced by 3/14 failing contract tests:

1. **G1** `test_column_is_not_null_constraint` FAIL -- `information_schema.columns.is_nullable = 'YES'`. Migration `SetTranscodeAttemptsMediaFileIdNotNull.py` exists but was never executed.
2. **G2** `test_no_null_mediafileid_rows` FAIL -- 1075 orphan rows with `MediaFileId IS NULL`. Cleanup `CleanupOrphanFailedAttempts.py` exists but was never executed.
3. **G3** `test_no_pending_row_exceeds_cap` FAIL -- ForceAdd bypasses admission cap check, but claim path still applies cap => over-cap ForceAdded rows sit Pending forever, unclaimable and invisible to /FailedJobs. Design gap not covered by C1-C9.

## Design

**Path A (G1 + G2 -- migrations):** run the two idempotent scripts sequentially. CSV archive at `Reports/OrphanFailedAttempts-<stamp>.csv` for anything unrecoverable.

**Path B (G3 -- ForceAdd auto-reset):** in `QueueManagementBusinessService.AddJobToQueue`, when `ForceAdd=True` AND `HasBudgetRemaining=False`, call `FailedJobsRepository.ResetFailureBudget(mediaFile.Id, 'ForceAdd')` before proceeding to INSERT. Auto-writes audit row + bumps `MediaFiles.LastFailureResetAt`. Operator intent (ForceAdd) propagates end-to-end. When `ForceAdd=False` AND cap hit, current refusal behavior unchanged. Also apply the same discipline to the bulk force-admission paths if any.

## Acceptance Criteria

C1. `Tests/Contract/TestFailureAccounting.py` all 14 tests PASS (was 11/14).

C2. `\d TranscodeAttempts` shows `MediaFileId BIGINT NOT NULL`.

C3. `SELECT COUNT(*) FROM TranscodeAttempts WHERE MediaFileId IS NULL` returns 0.

C4. `Reports/OrphanFailedAttempts-<stamp>.csv` exists with the archived rows.

C5. When `AddJobToQueue` is called with `ForceAdd=True` on a cap-hit MediaFileId, a `FailureBudgetResets` audit row is written with `OperatorName='ForceAdd'` and `MediaFiles.LastFailureResetAt` is bumped BEFORE the queue INSERT. Log line `"ForceAdd auto-reset failure budget for ..."` present.

C6. Existing over-cap ForceAdded Pending rows (Yogurt Shop / Misfit / Naked Attraction cluster) become claimable after their MediaFileIds are retroactively reset via a one-shot backfill (`Scripts/SQLScripts/BackfillForceAddResets_2026_08_27.py`) that identifies Pending TranscodeQueue rows whose MediaFileId currently exceeds the cap and writes a FailureBudgetResets row + bumps LastFailureResetAt for each.

C7. Flow doc `failure-accounting.flow.md` `## Failure Modes` gains a row for the ForceAdd-cap-hit auto-reset behavior.

## Call-Graph Audit

- Flow doc `failure-accounting.flow.md` unique for this pipeline. No duplication.
- No orchestration-level mode-branch introduced. `ForceAdd` was already a branch; this change makes both branches converge on ResetFailureBudget when cap is hit.
- Shared output columns: `FailureBudgetResets` rows now emitted from two callers (operator UI + ForceAdd auto). Same audit shape; OperatorName distinguishes.
- OOS items below all categorized.

## Out of Scope

- (b) BUG-0095 (failure-class taxonomy) -- follow-up already filed 2026-08-27.
- (b) Bulk force paths in `QueueManagementBusinessService.PopulateQueueFromMediaFiles` -- callers pre-filter via cap predicate, so cap-hit-force is not a real path there. Not touched.
- (b) `/settings` UI for `FailureBudgetConfig.MaxEncodeFailures` -- deferred (spec-called-out follow-up).

## Files

**Create:**
- `Scripts/SQLScripts/BackfillForceAddResets_2026_08_27.py` -- one-shot: retro-reset all currently-Pending TranscodeQueue rows whose MediaFileId is cap-hit; writes FailureBudgetResets audit rows with `OperatorName='ForceAdd:backfill_2026_08_27'`.

**Edit:**
- `Features/TranscodeQueue/QueueManagementBusinessService.py` -- add ForceAdd auto-reset logic in `AddJobToQueue`.
- `Features/FailureAccounting/failure-accounting.flow.md` -- add ForceAdd auto-reset failure-mode row.

**Execute (irreversible; CSV archive):**
- `py Scripts/SQLScripts/CleanupOrphanFailedAttempts.py`
- `py Scripts/SQLScripts/SetTranscodeAttemptsMediaFileIdNotNull.py`
- `py Scripts/SQLScripts/BackfillForceAddResets_2026_08_27.py`

### Progress

- [x] NEEDS_STANDARDS_REVIEW: rules loaded; standards index Read this session
- [x] NEEDS_PLAN: criteria + Files above
- [x] NEEDS_DOC_PREREAD: failure-accounting.feature.md + .flow.md Read this session; QueueManagementBusinessService.py inspected; FailedJobsRepository.py inspected
- [ ] IMPLEMENTING: code + backfill + docs
- [ ] VERIFYING: contract tests 14/14 + live smoke on one existing over-cap ForceAdded row
- [ ] DELIVERING: promote to feature doc + flow doc + BUG-INDEX

### Promotions

- Directive Design (ForceAdd auto-reset) -> `Features/FailureAccounting/failure-accounting.flow.md` `## Failure Modes` (new row documenting the auto-reset).
- BUG-0061 status flip -> `memory/BUG-INDEX.md` (active -> resolved) + `memory/KNOWN-ISSUES.md` BUG-0061 header updated with resolution stanza.

### Delivery Report

- DIRECTIVE: Close BUG-0061 by shipping the three remaining gaps -- MediaFileId NOT NULL migration, orphan cleanup, ForceAdd auto-reset -- so 14/14 contract tests pass.
- STATUS: Done.
- WHAT SHIPPED:
  - `Scripts/SQLScripts/CleanupOrphanFailedAttempts.py` executed: 1075 orphans -> backfilled 8 via (StorageRootId, RelativePath), archived 1067 to `Reports/OrphanFailedAttempts-2026-08-27-074314.csv`, deleted archived rows. Post-count 0.
  - `Scripts/SQLScripts/SetTranscodeAttemptsMediaFileIdNotNull.py` executed: `TranscodeAttempts.MediaFileId BIGINT NOT NULL`.
  - `Features/TranscodeQueue/QueueManagementBusinessService.AddJobToQueue` (line ~1941): unified the ForceAdd branch and the cap-check branch. When `ForceAdd=True` AND `HasBudgetRemaining=False`, calls `FailedJobsRepository().ResetFailureBudget(mediaFile.Id, 'ForceAdd')` before INSERT + logs auto-reset. When `ForceAdd=False` AND cap hit, unchanged refusal.
  - `Scripts/SQLScripts/BackfillForceAddResets_2026_08_27.py` created + executed: 29 over-cap Pending MediaFileIds retro-reset (audit rows written with `OperatorName='ForceAdd:backfill_2026_08_27'`, LastFailureResetAt bumped). Idempotent pre-check.
  - `Features/FailureAccounting/failure-accounting.flow.md` `## Failure Modes` row added for ForceAdd auto-reset.
  - `Tests/Contract/TestFailureAccounting.py` now 14/14 PASS (was 11/14). No test file changes -- the three failing tests were correct, the implementation caught up.
- HOW TO USE IT: no operator action needed. `/FailedJobs` surface + retry cap now fully enforced. Operator ForceAdd on a cap-hit file is auto-recorded as a ForceAdd reset in `FailureBudgetResets`.
- WHAT YOU NEED TO EXECUTE: fleet redeploy (`py deploy/deploy-fleet.py`) so remote workers pick up the new `AddJobToQueue` behavior. I9 = source-tree-live (already picked up after WebService restart, if needed).
- CRITERIA VERIFICATION:
  - C1: `py -m pytest Tests/Contract/TestFailureAccounting.py -q` -> `14 passed in 120.85s`.
  - C2: `information_schema.columns.is_nullable` = `NO` for TranscodeAttempts.MediaFileId.
  - C3: `SELECT COUNT(*) FROM TranscodeAttempts WHERE MediaFileId IS NULL` = 0.
  - C4: `Reports/OrphanFailedAttempts-2026-08-27-074314.csv` exists (1067 rows).
  - C5: code inspection at `QueueManagementBusinessService.py:1941` shows the auto-reset branch + log; log-line grep will match on next ForceAdd of an over-cap file.
  - C6: Yogurt Shop 211831 (was fails_since_reset=3, unclaimable) now fails_since_reset=0, cap=3, predicate `0<3=TRUE`, claim eligible. Backfill audit has 33 rows total (29 distinct MediaFileIds from this run + prior audit rows counted).
  - C7: flow doc row added.
- DECISIONS I MADE:
  - Broader retro-reset than "only ForceAdded": the backfill script resets ANY currently-Pending over-cap row, not only rows whose Pending status came via ForceAdd. Reason: the contract test invariant is `no Pending row exceeds cap`; leaving legacy leak-through rows unreset would fail the test. All 29 rows unblock claim; if any turn out to be permanently-broken sources (e.g. DTS-corrupt Heroes S02E01), they'll re-fail 3x and hit cap again -- this time surfaced correctly via /FailedJobs.
  - `# allow: R11` override on the audit INSERT: FailureBudgetResets has no unique constraint by design (audit rows are append-only). Pre-check SELECT above the INSERT guarantees per-(MediaFileId, OperatorName) idempotency. The R11 rule text explicitly sanctions override in the no-unique-constraint case.
- KNOWN GAPS / DEFERRED:
  - BUG-0095 (failure-class taxonomy) -- follow-up filed 2026-08-27, waits on BUG-0061 close.
  - `/settings` UI for `FailureBudgetConfig.MaxEncodeFailures` -- deferred per original spec OOS.
