# Flow: Compliance Evaluation Pipeline

**Slug:** compliance

## Entry Point

`Features/Compliance/Services/ComplianceEvaluator.Evaluate(MediaFile, EffectiveProfile, ComplianceRuleCache) -> ComplianceDecision`

Composition root: `Features/Compliance/ComplianceComposition.BuildEvaluator()` -- wires `ComplianceGateChain(Gates[])` + `ComplianceRuleEngine(Operations[])` + `ComplianceBucketResolver()` via constructor injection (DIP).

Two callers in production:

1. **Worker post-flight / probe completion** -- `MediaProbeBusinessService._ExecuteProbe` calls `QueueManagementBusinessService.RecomputeForFiles([Id])` which loops MediaFileIds -> per row builds `EffectiveProfile` (via `EffectiveProfileResolver.Resolve`) -> calls `Evaluate` -> accumulates updates -> `ComplianceWriteRepository.BulkWriteRecomputeResults` writes the materialized columns (`WorkBucket`, `OperationsNeededCsv`, `ComplianceGateBlocked`, `ComplianceEvaluatedAt`, `AssignedProfile`, `PriorityScore`, `IsCompliant`, `AdmissionDeferReason`).

2. **Pre-rename compliance gate** -- `Features/FileReplacement/ComplianceGate.Evaluate(staged_path, source_mediafile_id, ffmpeg_command)` synthesizes a `CandidateRow` dict, calls `QueueManagementBusinessService.EvaluateCandidateCompliance(CandidateRow)` which delegates to `Evaluator.Evaluate` and adapts the result to the `{IsCompliant, WorkBucket, RefusalReason}` dict shape consumed by `ComplianceGate.Evaluate`.

3. **Admin recompute** -- `POST /api/Compliance/Recompute` -> `ComplianceRecomputeService.Recompute(MediaFileIds, DryRun)` -- same per-row loop as (1), standalone path.

## Stages

| ID | Stage | Code | What it does |
|---|---|---|---|
| ST1 | Load rule cache | `BuildRuleCache()` reads 5 single-row repos | Loads `ComplianceRuleCache(Gates, TranscodeRules, RemuxRules, AudioFixRules, SubtitleFixRules)` once per batch call. Fresh DB read per `Get()` (db-is-authority); the cache is the snapshot for THIS batch only. |
| ST2 | Resolve EffectiveProfile | `EffectiveProfileResolver.Resolve(MediaFile)` | Cascade resolves the profile name (today: `MediaFile.AssignedProfile`); JOINs `Profiles` + `ProfileThresholds` for the source resolution; 3-strategy dispatch for `TargetVideoKbps`: fixed bitrate (Vk>0) -> use directly; VBR (`SourceBitratePercent>0` AND `MediaFile.VideoBitrateKbps`) -> compute `source * percent / 100`; CRF (`Quality` non-NULL) -> `CrfBitrateEstimateRepository.GetEstimatedKbps(Codec, TargetResolution, CRF)`. |
| ST3 | Apply gates | `ComplianceGateChain.Apply(Mf, Profile, Cache.Gates)` | Iterates 8 registered `IComplianceGate` impls in order: `EnglishAudio`, `AudioCorruptSuspect`, `AudioStream`, `ProbeMetadata`, `EffectiveProfile`, `ResolutionCategory`, `ProfileThresholds`, `LoudnessMeasurements`. For each: skip when disabled (`IsEnabled(Gates)` False); when enabled and `Blocks(Mf, Profile)` True, return the gate's `Name`. First failing gate wins. |
| ST4 | Short-circuit on gate | `ComplianceEvaluator.Evaluate` | If `GateChain.Apply` returns non-None, emit `ComplianceDecision(IsCompliant=None, OperationsNeeded=frozenset(), WorkBucket=None, GateBlocked=<name>, Reasons=[])` -- skip ST5-ST6. |
| ST5 | Apply operations | `ComplianceRuleEngine.Run(Mf, Profile, Cache)` | Iterates 4 registered `IComplianceOperation` impls (Transcode, Remux, AudioFix, SubtitleFix). For each: load rules via `Cache.GetForOperation(op.Name)`; call `op.Apply(Mf, Profile, Rules)` -> `OperationResult(Applies: bool, Reasons: List[dict])`. Collect all results. |
| ST6 | Resolve bucket | `ComplianceBucketResolver.Resolve(OperationsNeeded: frozenset)` | Pure function. Precedence: `Transcode` > `Remux` > `AudioFixOnly` > `SubtitleFixOnly` > None. `{AudioFix, SubtitleFix}` collapses to `AudioFixOnly` (audio takes precedence). |
| ST7 | Emit decision | `ComplianceEvaluator.Evaluate` | Build `ComplianceDecision(IsCompliant=(Bucket is None), OperationsNeeded=frozenset, WorkBucket, GateBlocked=None, Reasons=flattened-from-all-ops)`. |
| ST8 | Persist (bulk-write path only) | `ComplianceWriteRepository.BulkWriteRecomputeResults(Updates)` | Single bulk UPDATE FROM VALUES on `MediaFiles`: writes `WorkBucket`, `OperationsNeededCsv`, `ComplianceGateBlocked`, `ComplianceEvaluatedAt = NOW()`, `AssignedProfile`, `PriorityScore`, `IsCompliant`, `AdmissionDeferReason` atomically. SQL CHECK constraint `chk_compliance_consistency` (BUG-0062 / C9) refuses any row that violates the bucket-precedence invariant at the storage layer. |
| ST9 | Writeback Validation (BUG-0062, Layer 2) | `ComplianceWriteRepository.BulkWriteRecomputeResults` preamble | Before SQL construction, each tuple is validated against the C6 three-way disjunction (`IsCompliant`, `WorkBucket`, `OperationsNeededCsv`, `GateBlocked`). Valid tuples flow to ST8; invalid tuples are logged WARN with `MediaFileId` + full tuple and refused. Returns `(written, refused)` counts. Layer 1 (`ComplianceDecision.__post_init__` -- C7) and Layer 3 (SQL CHECK -- C9) are independently sufficient; this layer is the named producer-side guard. |

## Seams

| ID | Transition | Producer (writer) | Wire shape | Consumer (reader) expects | Verification |
|---|---|---|---|---|---|
| S1 | `ST1 -> ST2` (cache ready, per-row begin) | `BuildRuleCache()` builds the immutable snapshot | `ComplianceRuleCache` (frozen dataclass; 5 sub-dataclasses) | `EffectiveProfileResolver.Resolve` is called per MediaFile; doesn't consume the cache directly but the engine passes it forward to ST3-ST5 | `Tests/Contract/TestComplianceEngine.TestMidFlightConfigChange` |
| S2 | `ST2 -> ST3` (profile resolved) | `EffectiveProfileResolver.Resolve` | `EffectiveProfile(ProfileName, TargetVideoKbps: Optional[int], TargetAudioKbps: Optional[int], TargetResolutionCategory)` -- None when no profile/threshold; 0 valid for "no fixed bitrate" (CRF/VBR profiles with computed targets) | Gates + operations consume Profile; `ProfileThresholdsGate.Blocks` fires only on `is None`, not 0 (post-CRF-regression hotfix) | `Tests/Contract/TestComplianceEngine.TestCrfProfileRegression` |
| S3 | `ST3 -> ST4` (gate verdict) | `ComplianceGateChain.Apply` returns `Optional[str]` (gate Name or None) | gate name string from a fixed vocabulary (8 values) | When non-None, evaluator short-circuits and persists `ComplianceGateBlocked = <name>` | `Tests/Contract/TestComplianceEngine.TestGates` (10 cases) |
| S4 | `ST5` per-operation result | each `IComplianceOperation.Apply` | `OperationResult(OperationName, Applies, Reasons: List[{Rule, Operator, Actual, Threshold, Outcome}])` | Engine aggregates `OperationsNeeded` from `{r.OperationName for r in results if r.Applies}`; aggregates `Reasons` list from all results' traces | `Tests/Contract/TestComplianceEngine.TestOperations` (8 cases) |
| S5 | `ST6 -> ST7` (bucket resolved) | `ComplianceBucketResolver.Resolve` | `Optional[str]` from `{None, 'Transcode', 'Remux', 'AudioFixOnly', 'SubtitleFixOnly'}` | `ComplianceDecision.WorkBucket` carries it; downstream UI readers `WHERE WorkBucket = '...'` | `Tests/Contract/TestComplianceEngine.TestBucketResolverPrecedence` (6 cases) |
| S6 | `ST8` write-back | `ComplianceWriteRepository.BulkWriteRecomputeResults` | Single bulk UPDATE FROM VALUES; row tuple shape: `(Id, AssignedProfile, PriorityScore, IsCompliant, DeferReason, WorkBucket, OperationsNeededCsv, ComplianceGateBlocked)` | All MediaFiles columns updated atomically; `ComplianceEvaluatedAt = NOW()` set in the same statement | Worker probe completion triggers it; `SELECT ComplianceEvaluatedAt FROM MediaFiles WHERE Id=<id>` advances on each recompute |
| S7 | `ST7 -> ST9 -> ST8` writeback invariant (BUG-0062) | `ComplianceEvaluator.Evaluate` (tuple producer) + `ComplianceBucketResolver.Resolve` (co-mutator of `IsCompliant + WorkBucket`) + `ComplianceWriteRepository.BulkWriteRecomputeResults` (validator) | Tuple `(Id, AssignedProfile, PriorityScore, IsCompliant: Optional[bool], DeferReason, WorkBucket: Optional[str], OperationsNeededCsv: Optional[str], GateBlocked: Optional[str])` satisfying the three-way disjunction `(IsCompliant=TRUE AND WorkBucket IS NULL AND OperationsNeededCsv empty) OR (IsCompliant=FALSE AND WorkBucket non-null AND OperationsNeededCsv non-empty) OR (IsCompliant IS NULL AND GateBlocked non-null)` | `MediaFiles` row passes SQL `chk_compliance_consistency`; downstream `IsCompliant`-gated UI / queue logic never sees a contradictory row | `Tests/Contract/TestComplianceWriteConsistency.py` -- asserts (a) DB-wide count of contradictory rows = 0, (b) each layer (constructor / repository validator / SQL CHECK) refuses a synthetic contradiction in isolation |

## Failure Modes

| Failure | Symptom | Resolution |
|---|---|---|
| Rule table missing (migration not run) | `*RulesRepository.Get()` returns dataclass defaults + WARNING log | Operator runs `Scripts/SQLScripts/AddComplianceRuleTables.py` |
| Profile resolution fails (no AssignedProfile or no ProfileThresholds row) | Decision has `GateBlocked='EffectiveProfile'` or `'ProfileThresholds'`; row stays out of every queue | Operator assigns a profile (Media tab profile selector) or sets `SystemSettings.DefaultProfileName` |
| CRF profile -> no `CrfBitrateEstimates` row | `EffectiveProfileResolver` returns `TargetVideoKbps=None`; `TranscodeOperation` skips savings rule (codec/resolution checks still fire); savings predicate doesn't trigger | Operator seeds the table via `/settings` "Queue admission" card OR file is correctly bucketed via codec/resolution checks alone |
| Loudness measurement absent | `LoudnessMeasurementsGate` fires (when enabled); `ComplianceGateBlocked='LoudnessMeasurements'` | Operator triggers reprobe via `POST /api/MediaProbe/Reprobe`; worker runs `LoudnessAnalysisService.MeasureAndPersist` |
| Worker reads stale code mid-flight (pre-redeploy in-flight encode) | Pre-rename gate may use old cascade; one transcode produces `Disposition=NoReplace, DispositionReason=ComplianceGateFailed` and self-cleans the .inprogress | Operator's natural cascade re-queues the file once the worker is on the new code |

## Out of Scope

- **Claim ordering** -- owned by `Features/TranscodeQueue/queue-priority.feature.md`. Compliance writes `WorkBucket`; the claim path doesn't read it.
- **Queue admission filtering** -- the admission gate (`Features/TranscodeQueue/marginal-savings-gate.feature.md`) reads compliance results (`IsCompliant IS NOT TRUE`) but lives independently; this flow doesn't change admission logic.
- **VMAF / quality-floor feedback** -- separate paused directive `quality-floor-lift`. Compliance evaluation runs at probe + post-flight; VMAF runs after a Transcode replaces a file.
- **Per-show rule overrides** -- today rules are library-wide. Future: an `EffectiveProfileResolver` extension can layer per-show overrides on top of the library defaults without touching the engine.

## Code anchors

| Code | Anchor |
|---|---|
| `Features/Compliance/Services/ComplianceEvaluator.py:Evaluate` | `# see compliance.ST3` through `ST7` |
| `Features/Compliance/Services/ComplianceGateChain.py:Apply` | `# see compliance.ST3` |
| `Features/Compliance/Services/ComplianceRuleEngine.py:Run` | `# see compliance.ST5` |
| `Features/Compliance/Services/ComplianceBucketResolver.py:Resolve` | `# see compliance.ST6` |
| `Features/Compliance/Services/EffectiveProfileResolver.py:Resolve` | `# see compliance.ST2` |
| `Features/Compliance/Repositories/ComplianceWriteRepository.py:BulkWriteRecomputeResults` | `# see compliance.ST8` (+ `# see compliance.ST9` for the validation preamble) |
| `Features/Compliance/Models/ComplianceDecision.py:__post_init__` | `# see compliance.S7` (constructor self-validation) |
