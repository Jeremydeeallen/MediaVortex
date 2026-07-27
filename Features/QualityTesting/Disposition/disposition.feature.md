# ST7 Disposition

**Slug:** disposition

## What It Does

Decides what happens to a transcoded `TranscodeAttempt` after the encode completes and (optionally) VMAF lands. Replaces the legacy monolithic `PostTranscodeDispositionService` with a SOLID decomposition: one pure function for the decision, one orchestrator for the side effects, one strategy registry for adjustment math, and three small services for cleanup, compliance overrides, and retry budget. Wires into the ST6 -> ST7 seam in `transcode.flow.md`.

## Workflows

| #  | User action | Surface element | Handler | Backing class.method |
|----|-------------|-----------------|---------|----------------------|
| W1 | Worker finishes a transcode encode | (internal -- `ProcessTranscodeQueueService.DispatchDisposition`) | `DispatchDisposition` calls dispatcher | `Features/QualityTesting/Disposition/DispositionDispatcher.Dispatch` |
| W2 | VMAF result lands for a Pending attempt | (internal -- `QualityTestingBusinessService._RunVMAFTest`) | Same dispatcher fires after VMAF UPDATE | `DispositionDispatcher.Dispatch` |
| W3 | Operator skips a quality test | (internal -- `QualityTestingBusinessService.SkipQualityTest`) | Dispatcher fires after skip | `DispositionDispatcher.Dispatch` |
| W4 | Compliance gate refuses a Replace | (internal -- `FileReplacementBusinessService.ProcessFileReplacement`) | `ComplianceFailureRecorder` overrides disposition to Reject/ComplianceGateFailed | `Features/QualityTesting/Disposition/ComplianceFailureRecorder.Record` |

## Success Criteria

C1. **Disposition is a typed value object.** `Features/QualityTesting/Disposition/Disposition.py` defines a frozen dataclass `Disposition(Action: str, Reason: str, NextRegime: Optional[str], NextKnob: Optional[Any])`. Verifiable: instantiation succeeds; assignment to any field raises FrozenInstanceError.

C2. **Decision is a pure function.** `PostTranscodeDispositionDecider.Decide(Attempt: Dict, GateConfig: Dict) -> Disposition` performs zero DB access, zero logging, zero side effects. Inputs are typed dicts projected from rows by the dispatcher. Verifiable: `grep -n 'DatabaseService\|DatabaseManager\|LoggingService' Features/QualityTesting/Disposition/PostTranscodeDispositionDecider.py` returns no hits.

C3. **DB-fresh per call (db-is-authority).** `RetryBudgetService.HasBudgetRemaining(MediaFileId)` reads `PostTranscodeGateConfig.MaxRequeueAttempts` fresh on every call and counts prior `Disposition='Requeue'` outcomes. No instance cache. Verifiable: `grep -n 'self\._cached' Features/QualityTesting/Disposition/RetryBudgetService.py` returns 0 hits; `Tests/Contract/TestRetryBudgetService.py::test_reads_gate_config_fresh_per_call`.

C4. **Dispatcher composes via constructor only.** `DispositionDispatcher.__init__` parameters: Decider, GateConfigRepository, AttemptCleanupService, DatabaseService (required); RetryBudgetService, RequeueScheduler, RetainInprogressPolicy (optional). No `from X import Y` inside any method body except lazy `NextTierAdjuster` import in `_EnforceQualityCeiling`. Verifiable: ctor signature inspection.

C5. **Terminal-disposition cleanup is centralized + policy-driven.** `DispositionDispatcher._MaybeCleanupArtifacts(TranscodeAttemptId, Action, Reason)` calls `AttemptCleanupService.Cleanup` iff `Action in ('Reject', 'Requeue')` AND `RetainInprogressPolicy.ShouldRetain(Reason)` is False. `Replace` and `Pending` do NOT trigger cleanup; `Reject/TestMode` retains inprogress for A/B comparison. Verifiable: `Tests/Contract/TestDispositionDispatcher.py` + `Tests/Contract/TestRetainInprogressPolicy.py` cover each branch.

C6. **Compliance refusal flows through ComplianceFailureRecorder.** `FileReplacementBusinessService.ProcessFileReplacement` ComplianceGateRefused branch calls `ComplianceFailureRecorder.Record(TranscodeAttemptId, CascadeReason)`. Verifiable: code review.

## Seams

| ID | Seam | Producer | Wire shape | Consumer expects | Verification |
|---|---|---|---|---|---|
| S1 | `ProcessTranscodeQueueService.DispatchDisposition -> DispositionDispatcher.Dispatch` | `ProcessTranscodeQueueService` (or `QualityTestingBusinessService._RunVMAFTest`/`SkipQualityTest`) | `(TranscodeAttemptId: int)` | `Dispatch -> DispositionResult` (legacy return-shape at boundary) | `Tests/Contract/TestDispositionDispatcher.py` |
| S2 | `DispositionDispatcher -> PostTranscodeDispositionDecider.Decide` | Dispatcher projects row + gate config | `(Attempt: Dict, GateConfig: Dict)` | `Decider.Decide -> Disposition` VO | `Tests/Contract/TestDispositionDecider.py` |
| S3 | `Dispatcher._CommitDisposition -> DB UPDATE` | Dispatcher | `UPDATE TranscodeAttempts SET Disposition, DispositionReason, DispositionDecidedAt WHERE Id=...` | Idempotent on re-dispatch (cached check at S1) | Log entry: `Disposition for TranscodeAttempt <id>: <Action> (Reason=<Reason>) inputs={...}` |
| S4 | `Terminal disposition -> AttemptCleanupService.Cleanup` | Dispatcher | `(TranscodeAttemptId: int)` for Action in (Reject, Requeue) unless `RetainInprogressPolicy.ShouldRetain(Reason)` | `DELETE FROM TemporaryFilePaths WHERE TranscodeAttemptId = ...` | `SELECT COUNT(*) FROM TemporaryFilePaths tfp JOIN TranscodeAttempts ta ON ta.Id = tfp.TranscodeAttemptId WHERE ta.Disposition IN ('Reject','Requeue') AND ta.DispositionReason NOT IN ('TestMode')` -> 0 |
| S5 | `Requeue -> NextTierAdjuster` | Dispatcher `_EnforceQualityCeiling` on Requeue outcomes | `(CurrentProfileName)` | `NextTierProfile` or None (ceiling); Ceiling folds Requeue -> Reject/QualityCeilingReached | `TestNextTierAdjuster.py` |

## Status

ACTIVE. Escalation on Requeue is tier-ladder-driven via `NextTierAdjuster`.

## Files

| File | Role |
|------|------|
| `Features/QualityTesting/Disposition/Disposition.py` | C1 value object |
| `Features/QualityTesting/Disposition/PostTranscodeDispositionDecider.py` | C2 pure-function decider |
| `Features/QualityTesting/Disposition/RetryBudgetService.py` | C3 DB-fresh retry budget (counts Disposition='Requeue') |
| `Features/QualityTesting/Disposition/ComplianceFailureRecorder.py` | C6 extracted recorder |
| `Features/QualityTesting/Disposition/AttemptCleanupService.py` | C5 TFP cleanup chokepoint |
| `Features/QualityTesting/Disposition/DispositionDispatcher.py` | C4 orchestrator |
| `Features/TranscodeJob/Adjustments/NextTierAdjustmentCalculator.py` | S5 tier-ladder escalation |
| `Features/QualityTesting/PostTranscodeDispositionService.py` | facade preserving backward compat |
| `Tests/Contract/TestDisposition.py` | C1 |
| `Tests/Contract/TestDispositionDecider.py` | C2 |
| `Tests/Contract/TestRetryBudgetService.py` | C3 |
| `Tests/Contract/TestDispositionDispatcher.py` | C4, C5 |
| `Tests/Contract/TestNextTierAdjuster.py` | S5 |
