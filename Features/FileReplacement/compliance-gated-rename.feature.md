# Compliance-Gated Rename

**Slug:** compliance-gated-rename

## What It Does

Before promoting a transcoded `.inprogress` file to its final `-mv.<ext>` name, runs the same cascade compliance predicate that `QueueManagementBusinessService` uses to decide whether a source file needs work. If the candidate output would still be re-queued by the cascade, the rename refuses, the `.inprogress` is deleted, and the attempt's disposition is overridden to `NoReplace/ComplianceGateFailed`. Prevents `-mv-mv.<ext>` generational ghosts when an encode produces non-compliant output (wrong audio, marginal savings, non-acceptable container).

## Workflows

| #  | User action | Surface element | Handler | Backing class.method |
|----|-------------|-----------------|---------|----------------------|
| W1 | Worker finishes encode; `.inprogress` is on disk | (internal -- post-encode chain) | `_ProcessCompleteFileReplacement` calls gate | `Features/FileReplacement/TranscodedOutputPlacement.py:Execute` -> `ComplianceGate.Evaluate` |
| W2 | Operator audits a refused attempt | Activity page | `SELECT ... WHERE DispositionReason = 'ComplianceGateFailed'` | `Features/QualityTesting/PostTranscodeDispositionService.RecordComplianceGateFailure` |

## Success Criteria

C1. `ComplianceGate.Evaluate(LocalStagedPath, SourceMediaFileId, FFmpegCommand)` returns `{'Compliant': True, 'RefusalReason': None}` only when the cascade returns `IsCompliant=True AND RecommendedMode=None`. Verifiable: contract test seeds a known-compliant + a known-noncompliant candidate and asserts the gate matches.

C2. On refusal, the caller deletes the `.inprogress` and invokes `PostTranscodeDispositionService.RecordComplianceGateFailure(attemptId, cascadeReason)`, which UPDATEs `TranscodeAttempts.Disposition='NoReplace'`, `DispositionReason='ComplianceGateFailed'`, `ErrorMessage='ComplianceGateFailed: <reason>'`. Verifiable: force a gate refusal; assert the three column values + the absence of `.inprogress` on disk.

C3. The source MediaFile is untouched on refusal. Verifiable: SELECT the source row's mtime + path + size before and after a refusal; no change.

C4. The gate fails closed: any internal exception returns `{'Compliant': False, 'RefusalReason': 'gate_evaluation_error'}`. Verifiable: induce an exception inside `Evaluate` (e.g., DB unreachable); assert refusal, no rename, no source mutation.

C5. The gate uses the same predicate the cascade uses to decide compliance of existing files. There is no separate gate-only logic. Verifiable: `grep -rn "EvaluateCandidateCompliance" --include="*.py"` shows `ComplianceGate.Evaluate` calling it directly; no parallel cascade implementation exists.

C6. Loudnorm-just-ran exemption: when the FFmpeg command emitted for this attempt contains the loudnorm filter, `AudioComplete` is forced True in the candidate row before evaluation. Verifiable: contract test runs the gate on a freshly-loudnormed encode whose source has `AudioComplete=False`; asserts pass.

## Seams

| ID | Seam | Producer | Wire shape | Consumer expects | Verification |
|---|---|---|---|---|---|
| S1 | `TranscodedOutputPlacement.Execute -> ComplianceGate.Evaluate` | `_ProcessCompleteFileReplacement` (worker post-encode chain) | `(LocalStagedPath: str, SourceMediaFileId: int, FFmpegCommand: Optional[str])` | `{'Compliant': bool, 'RefusalReason': Optional[str]}` | `Tests/Contract/TestComplianceGate.py` (to be created) |
| S2 | `ComplianceGate.Evaluate -> QueueManagementBusinessService.EvaluateCandidateCompliance` | `Evaluate` synthesizes candidate row from probe + source carry-forward | dict with FilePath, Resolution, Codec, ContainerFormat, AudioCodec, AudioChannels, AssignedProfile, HasExplicitEnglishAudio, AudioLanguages, AudioComplete, AudioCorruptSuspect, SourceIntegratedLufs, SourceLoudnessRangeLU, SourceTruePeakDbtp, SourceIntegratedThresholdLufs | `{'IsCompliant': bool, 'RecommendedMode': Optional[str], 'RefusalReason': Optional[str]}` | Cascade unit test in TranscodeQueue suite |
| S3 | Refusal -> `PostTranscodeDispositionService.RecordComplianceGateFailure` | `Evaluate` returns refusal; caller invokes dispositioner | `(TranscodeAttemptId: int, CascadeReason: str)` | UPDATE TranscodeAttempts SET Disposition='NoReplace', DispositionReason='ComplianceGateFailed', ErrorMessage=... | Tests/Contract/TestPostTranscodeDisposition.py |

## Status

ACTIVE -- criteria 1-6 implemented in `Features/FileReplacement/ComplianceGate.py` (extracted from FileReplacementBusinessService during `filereplacement-decompose` directive 2026-06-02).

## Scope

```
Features/FileReplacement/ComplianceGate.py
```

## Files

| File | Role |
|------|------|
| `Features/FileReplacement/ComplianceGate.py` | The gate implementation (Evaluate method) |
| `Features/QualityTesting/PostTranscodeDispositionService.py` | `RecordComplianceGateFailure` records the override |
| `Features/TranscodeQueue/QueueManagementBusinessService.py` | `EvaluateCandidateCompliance` is the cascade predicate the gate calls |
