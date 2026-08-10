# Directive: pre-encode-savings-gate

**Status:** Active -- phase: IMPLEMENTING

**Slug:** pre-encode-savings-gate

**Supersedes:** `compliance-ceiling-per-profile` (drafted 2026-08-09, never entered IMPLEMENTING) + `partial-pipeline-completion` REOPENED-2 (drafted 2026-08-10, never entered IMPLEMENTING).

### Promotions

- (populated at DELIVERING; hook requires non-empty section for close transition)

## What / Why

Post-encode reject class currently discards all encoder work (video + audio) when the gate refuses the output. 118 known attempts fit this pattern; Ace Ventura Jr (MediaFileId 620326) is the reference case -- ffmpeg exited clean, 2 audio tracks emitted with measured loudness normalization, ComplianceGateFailed, .inprogress deleted, work lost.

Two prior directive drafts attacked this reactively (fix ceiling formula, salvage audio from .inprogress before deletion). Operator called the correct architectural pivot: **prevention over recovery**. Compute the expected savings from `profile_target_kbps / source_kbps` BEFORE launching ffmpeg for the video slot. If savings are below threshold, skip the video transcode entirely; route work through Remux/AudioFix so the audio path runs independently and never risks pairing with a doomed video encode.

Post-encode: keep both gates (relative savings AND absolute per-profile ceiling) as belt-and-suspenders for encoder-overshoot cases. Absolute ceiling protects "output is within tier expectation" invariant; relative savings protects "we actually shrunk the file" invariant.

## Domain Decisions (operator, 2026-08-10)

D1. **Pre-encode filter.** Before enqueuing a Transcode job, compute `predicted_savings = 1 - (AssignedProfile.TargetKbps / SourceKbps)`. If `predicted_savings < 0.20`, DO NOT route to Transcode. Route to AudioFix (if audio needs work) or Remux (if only container needs work) or Compliant (if source is already fully compliant).

D2. **Threshold value.** 20% flat across all resolutions. One knob.

D3. **Post-encode gate model.** Both gates -- relative savings AND absolute per-profile ceiling. Output must clear BOTH:
- `actual_savings = 1 - (output_size / source_size) >= 0.20`
- `output_kbps <= AssignedProfile.TargetKbps * VideoComplianceThresholds.Multiplier(ResolutionCategory)`

D4. **Directive merge.** Both prior directives (`compliance-ceiling-per-profile`, `partial-pipeline-completion` REOPENED-2) are superseded by this one. No parallel work streams.

D5. **Classifier drift fix.** Absorbed into this directive because absolute ceiling still uses `ResolutionCategory` -- the 4-copy inline classifier bug is still real and blocks correctness. Unify.

D6. **AssignedProfile-anchored ceiling.** Absorbed. `Tier1 * multiplier` -> `AssignedProfile.TargetKbps * multiplier`. Every Tier 2+ profile currently fails the old formula by design; this directive fixes it.

D7. **Threshold storage.** `QueueAdmissionConfig.PreEncodeSavingsThresholdPercent INT NOT NULL DEFAULT 20 CHECK BETWEEN 1 AND 99` (single-row typed config table; sibling to existing `MinTranscodeSavingsMB`). Operator-editable via `/settings`. Per `gui-editable-knobs` rule: ships with GUI handler in same directive. `QueueAdmissionConfig` (per `marginal-savings-gate.feature.md` C9) chosen over `SystemSettings` KV table because it is typed + single-row (`SystemSettings.feature.md` C11 flags the KV table as malformed with duplicates + case-inconsistent DataType).

## Scope

1. Add `SystemSettings.PreEncodeSavingsThresholdPercent` column + `/settings` GUI handler.
2. Add pre-encode savings predicate to WorkBucket routing: files where predicted savings < threshold NEVER enter Transcode bucket.
3. Unify resolution-category classifier: extract `Core/Resolution/ResolutionTierRegistry`-backed helper (already exists per `resolution-types.feature.md` C1/C9); delete 4 inline copies (`MediaProbeBusinessService._DeriveResolutionCategory`, `DatabaseManager._DeriveResolutionCategory`, `QueueManagementBusinessService._ResolutionCategoryFromPixels`, inline block in `ComplianceGate.Evaluate`).
4. Swap post-encode absolute ceiling formula in `VideoVertical.Evaluate` from Tier1-anchored to AssignedProfile-anchored (`AssignedProfile.TargetKbps * multiplier`).
5. Add post-encode relative-savings gate: reject if `actual_savings < 0.20`. Coexists with existing `NoSavings` gate (which is `<= 0%`) -- new gate supersedes, `NoSavings` retired.
6. Library-wide `QueueManagementBusinessService.RecomputeForFiles` after code lands -- thousands of MediaFiles will churn Transcode -> Remux/AudioFix/Compliant as pre-encode filter and new ceiling take effect.
7. Contract test asserts (a) inline height/width category derivations = 0 outside `Core/Resolution/`, (b) pre-encode filter predicate is invoked at WorkBucket derivation, (c) both post-encode gates fire correctly.
8. Update `Features/VideoEncoding/video-encoding.feature.md`, `Features/WorkBucket/work-bucket.feature.md`, `Features/QualityTesting/Disposition/disposition.feature.md`, `transcode.flow.md`. Retire references to `NoSavings` disposition; add references to the new pre-encode + post-encode savings gates.
9. Live smoke on I9: (a) file predicted to save < 20% -> observe routed to AudioFix/Remux, never Transcode. (b) file predicted to save > 20% but encoder overshoots -> observe post-encode reject on absolute ceiling. (c) file predicted to save > 20% and encoder hits target -> observe both gates pass + FileReplaced=TRUE.
10. Requeue the 118 orphan attempts (source files intact; natural queue re-processes them under the new routing).

## Out of Scope

(a) Salvaging audio work from `.inprogress` on post-encode reject -- category (b) tolerated: prevention model reduces reject class dramatically, remaining overshoot cases lose audio work (rare enough per D3 belt+suspenders design). If evidence post-ship shows this class is materially larger than expected, open a follow-up directive.

(b) Encoder rate-control tuning to reduce overshoot -- category (c) unrelated concern. This directive fixes routing + gates, not encoder settings.

(c) Migrating `MediaFiles.ResolutionCategory` from string to typed `ResolutionTier` throughout the tree -- category (a) tolerated debt: large mechanical change; not required for routing correctness.

(d) Retroactive audio-only pass on the 118 orphan source files (skip transcode, produce audio-processed output directly) -- category (b) tolerated: natural queue reprocess suffices under new routing; no separate one-shot code path.

## Call-Graph Audit

- **Multiple flow docs for one conceptual operation.** `transcode.flow.md` remains SoT. No new flow doc. WorkBucket routing predicate change documented as amendment to existing stages.
- **Orchestration-level mode-branching.** No new mode branch. Pre-encode filter is a DATA predicate on WorkBucket derivation (same code path evaluates it for every file). Post-encode dual gate is two sequential checks in the same reject path, not mode-branched orchestration.
- **Mode-sparse output columns.** `MediaFiles.VideoCompliant` continues to be written for every classified row. New column `MediaFiles.PredictedSavingsPercent` (or similar; NEEDS_PLAN decides whether to persist) written uniformly. No new sparsity.
- **OOS clause ambiguity.** OOS (a)/(b)/(c)/(d) each explicitly typed. No silent debt.
- **Config-driven call-graph shape.** `SystemSettings.PreEncodeSavingsThresholdPercent` is a VALUE, not a routing switch. Same functions called regardless. Data flows differently based on the number; call graph unchanged. OCP compliant.

## Acceptance Criteria

C1. `QueueAdmissionConfig.PreEncodeSavingsThresholdPercent INTEGER NOT NULL DEFAULT 20 CHECK BETWEEN 1 AND 99` added as a new column to the existing single-row `QueueAdmissionConfig` table (per `marginal-savings-gate.feature.md` C9). Idempotent migration (`ALTER TABLE ... ADD COLUMN IF NOT EXISTS`). Read fresh per `VideoVertical.Evaluate` call via `QueueAdmissionConfigRepository` (no `__init__` cache per `db-is-authority`). Fail-loud if row missing.

C2. `/settings` Transcoding card exposes the threshold. GET returns current value; PUT persists via existing `SystemSettingsRepository.UpsertAll` pattern. Ships in the same directive per `gui-editable-knobs`.

C3. `VideoVertical.Evaluate` returns `VideoCompliant=TRUE` when `source_kbps <= AssignedProfile.TargetKbps * Multiplier(ResolutionCategory)`, else `VideoCompliant=FALSE`. The pre-encode 20% savings branch was designed then dropped as dead code (proof at NEEDS_PLAN discovery): any source above the AssignedProfile ceiling has predicted_savings >= (1 - 1/multiplier) which is >= 33% for the smallest current multiplier (1.5). Adding a 20% floor as an OR branch never fires. The savings gate lives solely at post-encode (C7). WorkBucket routing falls out naturally from the flag: VideoCompliant=TRUE + AudioCompliant=FALSE -> AudioFix; + ContainerCompliant=FALSE -> Remux; all TRUE -> Compliant. No new routing branch.

C4. `Core/Resolution/ResolutionTierRegistry.FromDims(W, H)` (existing) is the SOLE derivation of resolution category from pixel dims in the production tree. Contract test greps for inline `Height >= N` / `Width >= N` patterns outside `Core/Resolution/`, count == 0. The 4 inline copies named in Scope #3 are deleted; callers delegate to the registry.

C5. `VideoVertical.Evaluate` uses `AssignedProfile.TargetKbps * Multiplier(ResolutionCategory)` as the ceiling. Two outcomes:
- Compliant: `source_at_or_below_ceiling:{Src}<={Ceiling}(profile={ProfileName}:{Target}*{Mult})`
- Non-compliant: `source_above_ceiling:{Src}>{Ceiling}(profile={ProfileName}:{Target}*{Mult})`
Fail-loud on missing inputs (AssignedProfile / Target / Multiplier / ResolutionCategory / VideoBitrateKbps).

C6. `TierLadderRepository.GetProfileTarget(ProfileName, ContentClass, Resolution) -> Optional[int]` exists and returns `ProfileThresholds.TargetKbps` for the exact triple. `GetTier1Target` remains for non-compliance callers (`NextTierAdjustmentCalculator` for tier-escalation math) but is no longer called by `VideoVertical.Evaluate`.

C7. Post-encode relative-savings gate: after `VideoVertical.Evaluate` passes absolute ceiling, `ComplianceGate.Evaluate` computes `actual_savings = 1 - (output_size / source_size)` and rejects if `actual_savings < SystemSettings.PreEncodeSavingsThresholdPercent / 100`. Reason: `output_savings_below_threshold:{ActualPct}%<{Threshold}%`. Existing `NoSavings` disposition retired (superseded by this gate at the tighter threshold).

C8. `Features/VideoEncoding/video-encoding.feature.md` updated: C1 reflects AssignedProfile-anchored ceiling; new criterion for pre-encode filter; new criterion for post-encode dual gate. `Features/WorkBucket/work-bucket.feature.md` updated for pre-encode routing predicate. `Features/QualityTesting/Disposition/disposition.feature.md` updated for new reason strings + retired `NoSavings`. `transcode.flow.md` updated for the new routing decision point.

C9. `Tests/Contract/TestPreEncodeSavingsGate.py` (NEW) covers: (a) source at profile_target * 5 with 20% threshold -> routes to Transcode (predicted 80% savings). (b) source at profile_target * 1.1 with 20% threshold -> routes to AudioFix/Compliant (predicted 9% savings). (c) threshold change from 20 -> 30 in SystemSettings -> next WorkBucket recompute reflects new threshold (db-is-authority). (d) missing SystemSettings row -> fail-loud RuntimeError.

C10. `Tests/Contract/TestClassifierIsSingleSource.py` (NEW) greps production tree for inline height/width category derivations; count == 0 outside `Core/Resolution/`.

C11. `Tests/Contract/TestVideoComplianceMultiplier.py` updated for AssignedProfile-anchored ceiling. All prior fail-loud cases still fail loud.

C12. Live smoke on I9 (mandatory per `ceo-mode.md#smoke-gate-verifying---delivering`):
- (a) One file per resolution (480p/720p/1080p/2160p) where source is barely above compliance ceiling but predicted savings < 20%. Observe: routed to AudioFix or Compliant, NOT Transcode.
- (b) One file where predicted savings >= 20%, encoder hits target. Observe: both post-encode gates pass, FileReplaced=TRUE.
- (c) One file where predicted savings >= 20%, encoder overshoots and lands above absolute ceiling. Observe: post-encode reject fires. If no natural reproducer exists on live data, construct a fixture -- ship blocked without demonstrated reject-path evidence (no narrowing).

C13. After code deployed, `Scripts/RecomputeWorkBuckets.py` invoked against every `MediaFiles.Id WHERE AssignedProfile IS NOT NULL`. Post-recompute SQL: `SELECT WorkBucket, COUNT(*) FROM MediaFiles GROUP BY WorkBucket` shows material Transcode -> AudioFix/Compliant shift under the new predicate.

C14. The 118 previously gate-rejected MediaFileIds are naturally re-processed via the new routing (source files intact; recompute lands them in the correct bucket). Verifiable: `SELECT COUNT(*) FROM TranscodeQueue WHERE MediaFileId IN (<the 118>)` == number of files whose new WorkBucket is Transcode; the remainder now sit in AudioFix / Compliant / Remux with no queue entry needed.

## Principle Analysis

**KISS.** Two prior directives (11+9 criteria) collapse into one (14 criteria) with a simpler mental model: predict shrinkage, act on prediction, verify actuals. Fewer moving parts than salvage-machinery + ceiling-formula-rewrite done separately.

**DDD.** Pre-encode filter is a `Features/WorkBucket/` routing concern -- lives where routing decisions live. Absolute ceiling stays in `Features/VideoEncoding/VideoVertical`. Relative-savings gate in `Features/FileReplacement/ComplianceGate`. Classifier in `Core/Resolution/`. Each concern lands in its own bounded context; no cross-contamination.

**DRY.** Four resolution-classifier copies -> one (`ResolutionTierRegistry.FromDims`). Two disposition reasons for "not enough savings" (`NoSavings` + new relative-gate reason) -> one (new gate; `NoSavings` retired). One threshold value (`SystemSettings.PreEncodeSavingsThresholdPercent`) drives both pre- and post-encode gates -- no parallel constant.

**SOLID.**
- SRP: pre-encode routing decision lives in the classifier / WorkBucket derivation, not tangled with encode execution. Post-encode gate stays post-encode. Salvage-and-recover machinery deleted (or never added).
- OCP: adding a new gate dimension = new predicate in the classifier, no orchestration change. Adding a new tier = one `ResolutionTiers` DB row (per existing `resolution-types` C8).
- LSP: n/a.
- ISP: repositories expose narrow contracts (`GetProfileTarget`, `GetMultiplier`, `GetSavingsThreshold`).
- DIP: `VideoVertical`, `ComplianceGate`, `QueueManagementBusinessService` depend on repository interfaces, not concrete SQL. Preserved.

**SSoT.**
- `SystemSettings.PreEncodeSavingsThresholdPercent` = SoT for the 20% knob.
- `ProfileThresholds.TargetKbps` = SoT for per-profile bitrate target (already; unchanged).
- `VideoComplianceThresholds.Multiplier` = SoT for per-resolution tolerance (already; unchanged).
- `ResolutionTiers` DB table + `ResolutionTierRegistry` = SoT for resolution classification (adoption gap paid).

**Code Bloat Inventory (deletion list, ~137 LOC net removed):**

| File | Symbol | Reason | Lines |
|---|---|---|---|
| `Features/MediaProbe/MediaProbeBusinessService.py` | `_DeriveResolutionCategory` | Duplicate of registry | ~25 |
| `Repositories/DatabaseManager.py` | `_DeriveResolutionCategory` + docstring | Duplicate; comment already flagged | ~40 |
| `Features/TranscodeQueue/QueueManagementBusinessService.py` | `_ResolutionCategoryFromPixels` | Duplicate | ~20 |
| `Features/FileReplacement/ComplianceGate.py` | inline height-only block (lines 61-77) | Duplicate + the bug | ~17 |
| `Features/VideoEncoding/VideoVertical.py` | `_ResolveFamily` + Tier1 lookup path | Family-based Tier1 lookup replaced by direct AssignedProfile lookup | ~15 |
| `Features/QualityTesting/Disposition/` | `NoSavings` disposition handler + closed-vocabulary entry | Retired; superseded by new relative-savings gate | ~20 |

## Files (draft; NEEDS_PLAN finalizes)

- `Scripts/SQLScripts/AddPreEncodeSavingsThreshold_2026_08_10.py` (NEW: ADD COLUMN on `QueueAdmissionConfig`)
- `Features/TranscodeQueue/QueueAdmissionConfigRepository.py` (add getter for threshold; fresh per call)
- `Features/SystemSettings/SystemSettingsController.py` (GET/PUT handler for threshold; UI lives under Transcoding card)
- `Templates/Settings.html` (Transcoding card: threshold input)
- `Features/VideoEncoding/VideoVertical.py` (AssignedProfile-anchored ceiling + predicted_savings second-branch OR; drop Tier1 lookup)
- `Features/Profiles/TierLadderRepository.py` (add `GetProfileTarget`)
- `Features/FileReplacement/ComplianceGate.py` (delete inline classifier block; add relative-savings gate)
- `Features/MediaProbe/MediaProbeBusinessService.py` (delete `_DeriveResolutionCategory`; delegate to registry)
- `Repositories/DatabaseManager.py` (delete `_DeriveResolutionCategory`; delegate to registry)
- `Features/TranscodeQueue/QueueManagementBusinessService.py` (delete `_ResolutionCategoryFromPixels`; delegate to registry; add pre-encode filter call)
- `Features/QualityTesting/Disposition/` (retire `NoSavings` handler + vocabulary; new gate reason strings)
- `Features/VideoEncoding/video-encoding.feature.md` (criteria updates)
- `Features/WorkBucket/work-bucket.feature.md` (pre-encode filter documented)
- `Features/QualityTesting/Disposition/disposition.feature.md` (vocabulary changes)
- `transcode.flow.md` (new routing decision + gate stages)
- `Core/Resolution/resolution-types.feature.md` (SOLE-classifier enforcement noted)
- `Tests/Contract/TestPreEncodeSavingsGate.py` (NEW)
- `Tests/Contract/TestClassifierIsSingleSource.py` (NEW)
- `Tests/Contract/TestVideoComplianceMultiplier.py` (updates)
- `Scripts/RecomputeWorkBuckets.py` (invoke post-deploy)
- `Scripts/Smoke/SmokePreEncodeSavingsGate_2026_08_10.py` (NEW, C12)

## Progress

- [ ] NEEDS_STANDARDS_REVIEW: rules + standards index re-read (already loaded).
- [ ] NEEDS_PLAN: finalize file list, decide WorkBucket predicate insertion point (generated column vs business service), decide new disposition-reason vocabulary strings.
- [ ] NEEDS_DOC_PREREAD: Read affected `*.flow.md` / `*.feature.md` ancestors.
- [ ] IMPLEMENTING: code + contract tests + migration + GUI.
- [ ] VERIFYING: per-criterion evidence + live smoke per C12 (all three scenarios demonstrated).
- [ ] DELIVERING: Promotions, feature-doc updates, delivery report.
