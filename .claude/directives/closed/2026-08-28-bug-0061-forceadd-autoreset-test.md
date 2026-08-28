# Directive: bug-0061-forceadd-autoreset-test

**Status:** Closed

**Slug:** bug-0061-forceadd-autoreset-test

## Outcome

Lock the BUG-0061 G3 fix (ForceAdd auto-reset in `AddJobToQueue`) with a direct contract test so future refactors cannot silently break it.

## Motivation

`bug-0061-remediation` closed with 14/14 contract tests passing, but the new `ForceAdd auto-reset` mechanism in `QueueManagementBusinessService.AddJobToQueue` is only indirectly covered by `test_no_pending_row_exceeds_cap` (invariant check). If a refactor deletes the auto-reset call, that test still passes as long as no over-cap Pending row exists at test-run time. Silent regression risk. Direct test needed.

## Acceptance Criteria

C1. `Tests/Contract/TestAddJobToQueueForceAddAutoReset.py` exists with 3 tests: (a) ForceAdd on cap-hit writes FailureBudgetResets audit + bumps LastFailureResetAt + queue admission succeeds; (b) ForceAdd when budget available does NOT write audit row; (c) non-ForceAdd on cap-hit refuses with FailureCapReached flag.

C2. All 3 new tests PASS.

C3. Test cleans up all synthetic rows in tearDown (TranscodeQueue + TranscodeAttempts + FailureBudgetResets + MediaFiles) so no leak per BUG-0092 discipline.

## Files

**Create:**
- `Tests/Contract/TestAddJobToQueueForceAddAutoReset.py`

### Progress

- [x] NEEDS_STANDARDS_REVIEW
- [x] NEEDS_PLAN
- [x] NEEDS_DOC_PREREAD: failure-accounting.feature.md + QueueManagementBusinessService (inspected this session)
- [ ] IMPLEMENTING
- [ ] VERIFYING
- [ ] DELIVERING

### Promotions

- Directive C1 -> `Tests/Contract/TestAddJobToQueueForceAddAutoReset.py` (new; locks BUG-0061 G3 ForceAdd auto-reset).

### Delivery Report

- STATUS: Done.
- WHAT SHIPPED: `Tests/Contract/TestAddJobToQueueForceAddAutoReset.py` with 3 tests. All PASS. Cleanup verified (0 leaked queue rows, 0 leaked MediaFiles).
