# Current Directive

**Set:** 2026-06-02
**Status:** Active -- phase: IMPLEMENTING -- criteria approved 2026-06-02.
**Slug:** bug-0032-orig-recovery
**Replaces:** (none)

## Outcome

Whatever survives from the 2026-05-14 `.orig` re-queue incident is accounted for. At-risk files where `.orig` is the only intact copy are restored to their canonical path; safe `.orig` files are deleted; stale `RecommendedMode='Remux'` rows are recomputed; orphan DB rows (no file on disk) are flagged for operator review. BUG-0032 closes.

## Acceptance Criteria

1. **Current-state assessment is on disk.** A new (or revived) audit script reports counts in the four BUG-0032 categories against today's filesystem + DB: (a) `.mp4` + `.orig` both exist, prior successful remux; (b) `.mp4` + `.orig` both exist, no successful remux (data-loss class); (c) `.mp4` only; (d) neither file exists. Verifiable: script runs to completion, produces a row-count table per category and a per-category sample list (10 paths) the operator can spot-check.
2. **Category (b) at-risk files recovered.** For every file in category (b): `.orig` renamed back to the pre-remux path, the corrupt `.mp4` deleted, `RecomputeForFiles([MediaFileId])` invoked. Verifiable: post-run query shows zero files where `.orig` exists AND no `TranscodeAttempts` row with `Success=true AND FileReplaced=true` for the parent MediaFile.
3. **Category (a) safe `.orig` files removed.** For every file in category (a): `.orig` deleted from disk. Verifiable: `find` for `*.mkv.orig` / `*.mp4.orig` post-run returns zero files under managed roots.
4. **Stale `RecommendedMode='Remux'` rows cleared.** `RecomputeForFiles` invoked on the surviving stale-Remux population. Verifiable: `SELECT COUNT(*) FROM MediaFiles WHERE RecommendedMode='Remux' AND IsCompliant=true` returns 0 (the inconsistent state).
5. **Category (d) orphan DB rows flagged.** Each row with no file on disk gets `AdmissionDeferReason='manual_review_orig_recovery_orphan'`. Verifiable: post-run query returns the category (d) count.

## Out of Scope

- Re-introducing the `.orig` rename pattern (it was correctly retired in 14c8c97).
- Recovering data for files that no longer exist on disk -- a year+ has passed; if the disk evidence is gone, the row is an orphan.

## Constraints

- Script must be dry-run-by-default. No file rename / no DB write without `--execute`.
- Recovery runs only while workers are paused (operator confirms; Claude will not start the workers).
- Idempotent: re-running on a remediated repo reports zero candidates per category.

## Escalation Defaults

- Irreversible disk operations (file delete, rename) -- Claude proposes, operator executes the `--execute` invocation OR explicitly authorizes Claude to run it.
- Risk tolerance: low.

## Engineering Calls Already Made

- Old `Scripts/OrigDamageAssessment.py` was deleted in 14c8c97; the new script will live at `Scripts/SQLScripts/AuditOrigRecovery.py` (consistent with other recovery scripts in that dir).
- `RecomputeForFiles` already runs from `_ProcessCompleteFileReplacement` (the original 2026-05-14 code fix). No further code change needed for the recurrence prevention -- this directive is data-recovery only.

## Status

Active -- phase: NEEDS_PLAN.

### Files

```
Scripts/SQLScripts/AuditOrigRecovery.py    -- CREATE: dry-run-first audit + recovery script
```

### Promotions

| Source artifact | Target file | Commit |
|---|---|---|
| no promotions | n/a | data recovery script, no contract change |

### Verification

- **Criterion 1:** TBD at VERIFYING
- **Criterion 2:** TBD at VERIFYING
- **Criterion 3:** TBD at VERIFYING
- **Criterion 4:** TBD at VERIFYING
- **Criterion 5:** TBD at VERIFYING

### Decisions Made

- TBD during execution
