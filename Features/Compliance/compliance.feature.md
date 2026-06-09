# Feature: Compliance Engine -- data-driven SOLID compliance evaluation

**Slug:** compliance

## What It Does

Decides, for every MediaFile, whether it is **compliant** (meets all rules under the resolved profile) and, if not, **which work bucket** ought to handle it (`Transcode` / `Remux` / `AudioFixOnly` / `SubtitleFixOnly`). Replaces the prior `_EvaluateCompliance` cascade -- a 200-line if/elif inside `QueueManagementBusinessService` -- with a data-driven SOLID class hierarchy at `Features/Compliance/`.

Five rule tables hold the operator-tunable policy (one table per operation + one for hard-block gates). Eight gate classes implement the undecidable-return paths the legacy cascade had buried inside one method. Four operation classes implement the per-operation predicates. A pure-function `ComplianceBucketResolver` maps `OperationsNeeded` to the single bucket the operator UI surfaces.

The engine is composable: adding a new operation = one new `IComplianceOperation` impl + one new rule table row. Adding a new gate = one new `IComplianceGate` impl + one new `ComplianceGates` column. Adding a new bitrate-strategy = one new branch in `EffectiveProfileResolver._ResolveTargetVideoKbps`.

## Workflows

| #  | User action | Surface element | Handler | Backing class.method |
|----|-------------|-----------------|---------|----------------------|
| W1 | Open `/settings`, expand "Compliance rules" card | GUI form | -- | `Templates/Settings.html` "Compliance rules" section |
| W2 | Edit rule + Save | per-table Save button | `PUT /api/Compliance/<table>` | `Features/Compliance/ComplianceController.Update*Rules` -> `<Table>RulesRepository.Update` |
| W3 | Click "Preview impact" | dry-run sample | `POST /api/Compliance/Preview` | `ComplianceController.PreviewRecompute` -> `ComplianceRecomputeService.Recompute(DryRun=True)` |
| W4 | Trigger admin recompute | -- | `POST /api/Compliance/Recompute` (body: MediaFileIds or All=true) | `ComplianceController.Recompute` -> `ComplianceRecomputeService.Recompute` -> per-row `ComplianceEvaluator.Evaluate` -> `ComplianceWriteRepository.BulkWriteRecomputeResults` |
| W5 | Worker probes a file (scan or reprobe) | -- | `MediaProbeBusinessService._ExecuteProbe` post-flight | `QueueManagementBusinessService.RecomputeForFiles` writes `WorkBucket` / `OperationsNeededCsv` / `ComplianceGateBlocked` / `ComplianceEvaluatedAt` + `AssignedProfile` / `PriorityScore` / `IsCompliant` / `AdmissionDeferReason` |
| W6 | Worker finishes encode, runs pre-rename compliance gate | -- | `Features/FileReplacement/ComplianceGate.Evaluate` | `QueueManagementBusinessService.EvaluateCandidateCompliance` -> `ComplianceEvaluator.Evaluate` |

## Success Criteria

C1-C26 + C5b are documented in the originating directive (`.claude/directives/closed/2026-06-09-compliance-solid-refactor.md` at directive close). Each criterion has concrete evidence in that doc's `### Verification` table.

The contract that survives directive close:

1. **`ComplianceEvaluator.Evaluate(MediaFile, EffectiveProfile, ComplianceRuleCache) -> ComplianceDecision`** is the sole public entry point. Constructor-injects `GateChain`, `RuleEngine`, `BucketResolver` (DIP). Composition root lives in `Features/Compliance/ComplianceComposition.BuildEvaluator()`.

2. **`ComplianceDecision`** is `@dataclass(frozen=True)`:
   - `IsCompliant: Optional[bool]` -- True / False / None (gate-blocked)
   - `OperationsNeeded: FrozenSet[str]` -- subset of `{'Transcode','Remux','AudioFix','SubtitleFix'}`
   - `WorkBucket: Optional[str]` -- `'Transcode'` / `'Remux'` / `'AudioFixOnly'` / `'SubtitleFixOnly'` / None
   - `GateBlocked: Optional[str]` -- gate name when IsCompliant is None
   - `Reasons: List[dict]` -- structured trace `{Rule, Operator, Actual, Threshold, Outcome}` per applied predicate

3. **Bucket precedence** (`ComplianceBucketResolver.Resolve`):
   - Empty `OperationsNeeded` -> bucket None, IsCompliant True
   - `'Transcode' in OperationsNeeded` -> bucket `'Transcode'`
   - `'Remux' in OperationsNeeded` (no Transcode) -> bucket `'Remux'`
   - `OperationsNeeded == {'AudioFix'}` (or `{'AudioFix', 'SubtitleFix'}`) -> bucket `'AudioFixOnly'`
   - `OperationsNeeded == {'SubtitleFix'}` -> bucket `'SubtitleFixOnly'`

4. **db-is-authority**: every rule-repository `Get()` reads fresh per call. No `self._cached_*` on any service or repository. Bulk recompute snapshot is a method-level `ComplianceRuleCache` parameter, never instance state.

5. **OCP**: adding a new operation requires only a new `IComplianceOperation` impl file + new rule table seed + register in `ComplianceComposition.BuildEvaluator()`. No edits to existing operations, gates, evaluator, or resolver.

## Seams

| ID | Seam | Producer | Wire shape | Consumer expects | Verification |
|---|---|---|---|---|---|
| S1 | `MediaProbeBusinessService` -> `RecomputeForFiles` | Probe completion in `_ExecuteProbe` | `MediaFileId: int` | `RecomputeForFiles([id])` evaluates + writes `WorkBucket` / `OperationsNeededCsv` / `ComplianceGateBlocked` / `ComplianceEvaluatedAt` + `AssignedProfile` / `PriorityScore` / `IsCompliant` / `AdmissionDeferReason` on `MediaFiles` | Post-probe `SELECT ComplianceEvaluatedAt FROM MediaFiles WHERE Id=<id>` is fresh |
| S2 | `EvaluateCandidateCompliance` -> `ComplianceEvaluator.Evaluate` | `Features/FileReplacement/ComplianceGate.Evaluate` (worker pre-rename) | `CandidateRow: dict` shaped like `MediaFiles` row | `EvaluateCandidateCompliance` returns `{IsCompliant, WorkBucket, RefusalReason}` dict shape via delegation | `Tests/Contract/TestComplianceEngine.TestGates` |
| S3 | `RecomputeForFiles` write | Per-row UPDATE via `ComplianceWriteRepository.BulkWriteRecomputeResults` | `MediaFiles.(WorkBucket TEXT, OperationsNeededCsv TEXT, ComplianceGateBlocked TEXT, ComplianceEvaluatedAt TIMESTAMP, ...)` | Queue UI readers (`NextTranscodeBatch`, `SmartPopulateQueue`) + Activity widget (`ActivityRepository.GetWorkBucketBreakdown`) | `SELECT WorkBucket, COUNT(*) FROM MediaFiles GROUP BY WorkBucket` reflects the bucketed distribution |
| S4 | Rule config -> engine | Each `*RulesRepository.Get()` reads its single-row table | dataclass per rule table | `ComplianceRuleCache` aggregates all 5; `ComplianceEvaluator.Evaluate` calls `Cache.GetForOperation(op_name)` | `Tests/Contract/TestComplianceEngine.TestMidFlightConfigChange` -- mid-flight UPDATE reflects in next Get |
| S5 | Profile resolution | `EffectiveProfileResolver.Resolve(MediaFile)` reads `Profiles` + `ProfileThresholds` + optional `CrfBitrateEstimates` | `EffectiveProfile(ProfileName, TargetVideoKbps, TargetAudioKbps, TargetResolutionCategory)` | `TranscodeOperation.Apply` consumes Profile for upscale / savings rules | Smoke per CRF/VBR/fixed strategy |
| S6 | GUI -> rules | `Templates/Settings.html` PUTs each rule table via fetch | JSON body matching the dataclass column names | `ComplianceController.Update*Rules` -> `*RulesRepository.Update` (partial update of non-None fields) | Round-trip via curl + reload |
| S7 | Bucket counts widget | `GET /api/Compliance/Buckets` | `{Buckets: {bucket: N}, GateBlocked: {gate: N}}` | GUI `RefreshBucketCounts()` JS renders live counts | curl |

## Status

ACTIVE -- post-directive close. Engine + GUI + readers all live in production.

## Files

| File | Role |
|------|------|
| `ComplianceController.py` | Flask blueprint at `/api/Compliance/*` -- 10 routes (GET/PUT per rule table + Buckets + Preview + Recompute) |
| `ComplianceComposition.py` | DIP composition root -- `BuildEvaluator()` + `BuildRuleCache()` factories |
| `Models/ComplianceDecision.py` | Immutable decision dataclass (5 fields) |
| `Models/OperationResult.py` | One operation's verdict (Applies + Reasons trace) |
| `Models/EffectiveProfile.py` | Resolved profile + bitrate trio for compliance |
| `Models/ComplianceRuleCache.py` | Snapshot of all 5 rule tables; built once per bulk recompute |
| `Models/{Transcode,Remux,AudioFix,SubtitleFix}RulesModel.py` + `ComplianceGatesModel.py` | One dataclass per rule table |
| `Repositories/{Transcode,Remux,AudioFix,SubtitleFix}RulesRepository.py` + `ComplianceGatesRepository.py` | One read/Update repo per rule table; no caching |
| `Repositories/ComplianceWriteRepository.py` | Bulk UPDATE that persists per-row recompute results |
| `Services/ComplianceEvaluator.py` | Sole public entry; gates -> operations -> bucket orchestration |
| `Services/ComplianceGateChain.py` | Registered gates in order; first failing gate short-circuits |
| `Services/ComplianceRuleEngine.py` | Runs each registered operation; collects results |
| `Services/ComplianceBucketResolver.py` | Pure function: OperationsNeeded -> WorkBucket |
| `Services/ComplianceRecomputeService.py` | Admin recompute path -- evaluates + writes per row |
| `Services/EffectiveProfileResolver.py` | 3-strategy bitrate dispatch (fixed / VBR / CRF) |
| `Operations/IComplianceOperation.py` + `{Transcode,Remux,AudioFix,SubtitleFix}Operation.py` | Abstract + 4 LSP-interchangeable impls |
| `Gates/IComplianceGate.py` + `{EnglishAudio,AudioCorruptSuspect,AudioStream,LoudnessMeasurements,ProbeMetadata,EffectiveProfile,ResolutionCategory,ProfileThresholds}Gate.py` | Abstract + 8 LSP-interchangeable impls |

## See also

- `compliance.flow.md` -- pipeline detail (load rules -> apply gates -> apply operations -> resolve bucket -> emit decision)
- `Features/TranscodeQueue/transcode-vs-remux-routing.feature.md` -- legacy doc with pointer to here
- `transcode.flow.md` Stage 3.5 -- pipeline integration with pointer to here
- `Features/TranscodeQueue/marginal-savings-gate.feature.md` -- the `CrfBitrateEstimates` table consumed by `EffectiveProfileResolver`
- `Features/TranscodeQueue/queue-priority.feature.md` -- claim ORDER BY contract (unchanged by this feature)
