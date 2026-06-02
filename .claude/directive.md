# Current Directive

**Set:** 2026-06-02
**Status:** Active -- phase: IMPLEMENTING -- end-to-end worker ownership.
**Slug:** bug-0020-worker-ownership
**Replaces:** (none -- continuation of BUG-0020 after Slice 1 compliance-gate landed in d26f77e)

## Outcome

A worker process owns the terminal state of every `.inprogress` it creates and every TFP/MediaFile row that belongs to one of its attempts. No sibling service (OrphanCleanupService, scan adoption, manual scripts) deletes a `.inprogress` for a live worker; no sibling sweeps a TFP row for an attempt whose owning worker is alive. Crash recovery on worker startup is the only safety net, and it operates only on rows owned by the restarting worker. The five operator-run cleanup scripts find zero candidates on a fresh fleet pass.

## Acceptance Criteria

1. Every worker entry point (`ProcessTranscodeQueueService.ProcessJob`, `ProcessRemuxQueueService.ProcessJob`, and any other ProcessJob equivalents) wraps the encode + post-flight chain in `try/finally`. On any exception or early return, the `finally` block deletes the `.inprogress` file produced by this attempt (if any) and emits a non-success disposition with an audit trail. Verifiable: induce a forced failure mid-encode and observe no `.inprogress` file remains on disk after `ProcessJob` returns.
2. `OrphanCleanupService._SweepInProgressFiles` (if it exists) refuses to delete a `.inprogress` whose parent attempt has `WorkerName` matching an `ActiveJobs` row -- live owner means the worker still owns the file. Verifiable: insert a synthetic `.inprogress` plus a fresh `ActiveJobs` row, run the sweep, observe the file untouched.
3. Worker-side TFP cleanup happens before the worker returns control. `ProcessJob` deletes the TFP row for the attempt in its `finally` (after disposition is committed). `OrphanCleanupService._SweepTemporaryFilePaths` runs only as a safety net and skips rows whose parent attempt's `WorkerName` still has an `ActiveJobs` row. Verifiable: run a full encode, observe the TFP row deleted by the time `ProcessJob` returns.
4. Crash recovery (`WorkerService/Main.py` startup) operates only on attempts where `TranscodeAttempts.WorkerName = self.WorkerName`. No worker touches another worker's in-flight rows. Verifiable: synthetic attempts owned by worker A are not touched when worker B starts.
5. After the fix, running each of `CleanupSourceFileOrphans.py`, `CleanupStaleInProgressFiles.py`, `CleanupGenerationalGhostRows.py`, `CleanupOrphanMvPairs.py`, `CleanupTemporaryFilePathsOrphans.py` (whichever exist) on a fresh fleet pass reports zero candidates. Verifiable: each script's dry-run output shows zero candidates.

## Out of Scope

- Re-introducing the `.orig` rename pattern (correctly retired).
- Restructuring `OrphanCleanupService` away from its sweep architecture -- keep it as the safety net, just gate its writes on liveness.
- Changing the `ActiveJobs` polymorphic schema (BUG-0001 covered the polymorphic FK question; we use it as-is).

## Constraints

- Sweep services keep running -- they become safety nets, not primary cleanup paths.
- All cleanup gates query `ActiveJobs` for liveness; no in-memory worker registry.
- One commit per criterion slice; do not bundle all changes into one mega-commit.

## Escalation Defaults

- Risk tolerance: medium (touches the worker hot path).

## Engineering Calls Already Made

- Slice 1 (compliance-gated rename, BUG-0020 C3) shipped in d26f77e + ca19ad3.
- BUG-0001 chokepoint pattern (`_CommitDisposition` deletes TFP on non-Replace dispositions) is the foundation for criterion 3; this directive completes the success-path side.

## Status

Active -- phase: IMPLEMENTING.

### Files

```
Features/TranscodeJob/ProcessTranscodeQueueService.py    -- EDIT: try/finally + .inprogress cleanup (C1)
Features/TranscodeJob/ProcessRemuxQueueService.py        -- EDIT: try/finally + .inprogress cleanup (C1)
Features/ServiceControl/OrphanCleanupService.py          -- EDIT: liveness gate before delete (C2, C3)
Features/QualityTesting/PostTranscodeDispositionService.py -- EDIT: success-path TFP cleanup (C3)
Features/FileReplacement/FileReplacementBusinessService.py -- EDIT: TFP cleanup chokepoint (C3)
WorkerService/Main.py                                    -- EDIT: crash recovery scoped to self.WorkerName (C4)
WorkerService/worker-lifecycle.feature.md                -- EDIT: update C8-C13 to reflect ownership rules
```

### Promotions

| Source artifact | Target file | Commit |
|---|---|---|
| Ownership rules (worker owns .inprogress + TFP terminal state) | `WorkerService/worker-lifecycle.feature.md` | TBD |
| Liveness-gated sweep predicate | `Features/ServiceControl/orphan-cleanup.flow.md` | TBD |

### Verification

- **Criterion 1:** TBD at VERIFYING
- **Criterion 2:** TBD at VERIFYING
- **Criterion 3:** TBD at VERIFYING
- **Criterion 4:** TBD at VERIFYING
- **Criterion 5:** TBD at VERIFYING

### Decisions Made

- TBD during execution
