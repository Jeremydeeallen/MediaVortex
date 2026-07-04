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
| W5 | Queue-admission re-transcode check | (internal -- `QueueManagementBusinessService.PopulateQueueFromMediaFiles` + `AddJobToQueue`) | `RetranscodeDecider.Decide(MediaFileId)` returns `(ShouldRetranscode, PreviousAttempt)`; `AdjustmentRegistry.Get('cq').Calculate(...)` produces the next CRF | `Features/QualityTesting/Disposition/RetranscodeDecider.Decide`, `Features/TranscodeJob/Adjustments/AdjustmentRegistry.Get` |

## Success Criteria

C1. **Disposition is a typed value object.** `Features/QualityTesting/Disposition/Disposition.py` defines a frozen dataclass `Disposition(Action: str, Reason: str, NextRegime: Optional[str], NextKnob: Optional[Any])`. Verifiable: instantiation succeeds; assignment to any field raises FrozenInstanceError.

C2. **Decision is a pure function.** `PostTranscodeDispositionDecider.Decide(Attempt: Dict, GateConfig: Dict) -> Disposition` performs zero DB access, zero logging, zero side effects. Inputs are typed dicts projected from rows by the dispatcher. Verifiable: `grep -n 'DatabaseService\|DatabaseManager\|LoggingService' Features/QualityTesting/Disposition/PostTranscodeDispositionDecider.py` returns no hits.

C3. **Retranscode decision references only MediaFileId in scope.** `RetranscodeDecider.Decide(MediaFileId: int) -> Tuple[bool, Optional[Dict]]` uses `MediaFileId` for logging; no `FilePath` identifier exists in the function body. Verifiable: `grep -n 'FilePath' Features/QualityTesting/Disposition/RetranscodeDecider.py` returns 0 hits. `Tests/Contract/TestRetranscodeDecider.py::test_first_attempt_returns_should_transcode` passes.

C4. **Adjustment math is dispatched by RateControlMode.** `AdjustmentRegistry.Get(RateControlMode)` returns an `AdjustmentCalculator` strategy. `'cq' -> CrfAdjustmentCalculator`; `'vbr'` raises KeyError (slot reserved for `NvencBudgetAdjustmentCalculator`). Verifiable: `AdjustmentRegistry().Get('cq')` returns a CrfAdjustmentCalculator; `.Get('vbr')` raises KeyError.

C5. **DB-fresh per call (db-is-authority).** `RetryBudgetService.HasBudgetRemaining(MediaFileId)` reads `PostTranscodeGateConfig.MaxRequeueAttempts` and `VmafAutoReplaceMinThreshold` fresh on every call. No instance cache. Verifiable: `grep -n 'self\._cached' Features/QualityTesting/Disposition/RetryBudgetService.py` returns 0 hits; `Tests/Contract/TestRetryBudgetService.py::test_reads_gate_config_fresh_per_call`.

C6. **Dispatcher composes via constructor only.** `DispositionDispatcher.__init__` parameters: Decider, GateConfigRepository, AttemptCleanupService, DatabaseService (required); RetranscodeDecider, AdjustmentRegistry, RetryBudgetService (optional). No `from X import Y` inside any method body. Verifiable: ctor signature inspection.

C7. **Terminal-disposition cleanup is centralized + policy-driven.** `DispositionDispatcher._MaybeCleanupArtifacts(TranscodeAttemptId, Action, Reason)` calls `AttemptCleanupService.Cleanup` iff `Action in ('Reject', 'Requeue')` AND `RetainInprogressPolicy.ShouldRetain(Reason)` is False. `Replace` and `Pending` do NOT trigger cleanup; `Reject/TestMode` retains inprogress for A/B comparison. Verifiable: `Tests/Contract/TestDispositionDispatcher.py` + `Tests/Contract/TestRetainInprogressPolicy.py` cover each branch.

C8. **Compliance refusal flows through ComplianceFailureRecorder.** `FileReplacementBusinessService.ProcessFileReplacement` ComplianceGateRefused branch calls `ComplianceFailureRecorder.Record(TranscodeAttemptId, CascadeReason)`. Verifiable: code review.

## Seams

| ID | Seam | Producer | Wire shape | Consumer expects | Verification |
|---|---|---|---|---|---|
| S1 | `ProcessTranscodeQueueService.DispatchDisposition -> DispositionDispatcher.Dispatch` | `ProcessTranscodeQueueService` (or `QualityTestingBusinessService._RunVMAFTest`/`SkipQualityTest`) | `(TranscodeAttemptId: int)` | `Dispatch -> DispositionResult` (legacy return-shape at boundary) | `Tests/Contract/TestDispositionDispatcher.py` |
| S2 | `DispositionDispatcher -> PostTranscodeDispositionDecider.Decide` | Dispatcher projects row + gate config | `(Attempt: Dict, GateConfig: Dict)` | `Decider.Decide -> Disposition` VO | `Tests/Contract/TestDispositionDecider.py` |
| S3 | `Dispatcher._CommitDisposition -> DB UPDATE` | Dispatcher | `UPDATE TranscodeAttempts SET Disposition, DispositionReason, DispositionDecidedAt WHERE Id=...` | Idempotent on re-dispatch (cached check at S1) | Log entry: `Disposition for TranscodeAttempt <id>: <Action> (Reason=<Reason>) inputs={...}` |
| S4 | `Terminal disposition -> AttemptCleanupService.Cleanup` | Dispatcher | `(TranscodeAttemptId: int)` for Action in (Reject, Requeue) unless `RetainInprogressPolicy.ShouldRetain(Reason)` | `DELETE FROM TemporaryFilePaths WHERE TranscodeAttemptId = ...` | `SELECT COUNT(*) FROM TemporaryFilePaths tfp JOIN TranscodeAttempts ta ON ta.Id = tfp.TranscodeAttemptId WHERE ta.Disposition IN ('Reject','Requeue') AND ta.DispositionReason NOT IN ('TestMode')` -> 0 |
| S5 | `QueueManagementBusinessService -> RetranscodeDecider.Decide` | QueueManagement admission paths | `(MediaFileId: int)` | `(ShouldRetranscode: bool, PreviousAttempt: Optional[Dict])` | `Tests/Contract/TestRetranscodeDecider.py` |
| S6 | `Caller -> AdjustmentRegistry -> CrfAdjustmentCalculator` | QueueManagement (post-decide) | `AdjustmentRegistry().Get('cq').Calculate(PreviousAttempt: Dict, ProfileSettings: Dict, GateThreshold: float) -> KnobOverrides` | `KnobOverrides(CRF: Optional[int], BitrateKbps: Optional[int], MaxrateKbps: Optional[int])` | `Tests/Contract/TestCrfAdjustmentCalculator.py` |

## Status

ACTIVE -- Phase 1 of `perfect-solid-transcode-pipeline` shipped. NVENC `'vbr'` AdjustmentCalculator slot reserved for Phase 2. Admission-gate-ungainable-peak follow-up directive slug: `ungainable-peak-admission-gate`.

## Files

| File | Role |
|------|------|
| `Features/QualityTesting/Disposition/Disposition.py` | C1 value object |
| `Features/TranscodeJob/Adjustments/KnobOverrides.py` | value object used by AdjustmentCalculator |
| `Features/QualityTesting/Disposition/PostTranscodeDispositionDecider.py` | C2 pure-function decider |
| `Features/QualityTesting/Disposition/RetranscodeDecider.py` | C3 |
| `Features/QualityTesting/Disposition/RetryBudgetService.py` | C5 DB-fresh retry budget |
| `Features/QualityTesting/Disposition/ComplianceFailureRecorder.py` | C8 extracted recorder |
| `Features/QualityTesting/Disposition/AttemptCleanupService.py` | C7 TFP cleanup chokepoint |
| `Features/QualityTesting/Disposition/DispositionDispatcher.py` | C6 orchestrator |
| `Features/TranscodeJob/Adjustments/AdjustmentCalculator.py` | C4 strategy interface |
| `Features/TranscodeJob/Adjustments/CrfAdjustmentCalculator.py` | C4 CRF impl |
| `Features/TranscodeJob/Adjustments/AdjustmentRegistry.py` | C4 strategy registry |
| `Features/QualityTesting/PostTranscodeDispositionService.py` | 64-LOC facade preserving backward compat for legacy tests/smoke |
| `Tests/Contract/TestDisposition.py` | C1 |
| `Tests/Contract/TestKnobOverrides.py` | (value object) |
| `Tests/Contract/TestDispositionDecider.py` | C2 |
| `Tests/Contract/TestRetranscodeDecider.py` | C3 |
| `Tests/Contract/TestRetryBudgetService.py` | C5 |
| `Tests/Contract/TestDispositionDispatcher.py` | C6, C7 |
| `Tests/Contract/TestCrfAdjustmentCalculator.py` | C4 |
| `Tests/Contract/TestAdjustmentRegistry.py` | C4 |
