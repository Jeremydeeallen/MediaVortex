# Directive: pre-encode-savings-gate

**Status:** Closed

**Slug:** pre-encode-savings-gate

**Supersedes:** `compliance-ceiling-per-profile` (drafted 2026-08-09, never entered IMPLEMENTING) + `partial-pipeline-completion` REOPENED-2 (drafted 2026-08-10, never entered IMPLEMENTING).

### Promotions

- Directive `## What / Why` + `## Domain Decisions` D5-D6 (AssignedProfile-anchored ceiling) → `Features/VideoEncoding/video-encoding.feature.md` C1 + S3 + Cross-Vertical Contract (commit `932fa46c`).
- Directive C7 (post-encode InsufficientSavings gate) → `Features/QualityTesting/post-transcode-disposition.feature.md` C10 + C11 vocabulary (commit `932fa46c`).
- Directive `## Code Bloat Inventory` (5-copy classifier drift) → `Core/Resolution/resolution-types.feature.md` Status amendment (adoption gap closed) (commit `932fa46c`).
- Directive C1 + C2 (threshold + GUI) → `Templates/Settings.html` Transcoding card new input row + JS LoadQueueAdmissionConfig / SaveQueueAdmissionConfig extended (commit `932fa46c`).
- Directive C6 (`TierLadderRepository.GetProfileTarget`) → `Features/Profiles/TierLadderRepository.py` new method + `Features/Profiles/profile-tier-ladder.feature.md` still current (method sits alongside `GetTier1Target` per non-compliance callers).

### Delivery Report

- DIRECTIVE: fix the Ace Ventura Jr class of false-reject failures (118 attempts) + prevent future audio-work loss via AssignedProfile-anchored per-profile ceiling + belt+suspenders post-encode savings gate. Supersedes two prior drafts that never entered IMPLEMENTING.
- STATUS: Done.
- WHAT SHIPPED:
  - `Scripts/SQLScripts/AddPreEncodeSavingsThreshold_2026_08_10.py` -- migration adds `QueueAdmissionConfig.PreEncodeSavingsThresholdPercent INTEGER DEFAULT 20 CHECK 1..99`. Idempotent.
  - `Features/Profiles/TierLadderRepository.GetProfileTarget(ProfileName, ContentClass, Resolution)` -- SSoT for per-profile target lookup.
  - `Features/VideoEncoding/VideoVertical.Evaluate` -- ceiling formula swap from `Tier1TargetKbps * Multiplier` to `AssignedProfileTargetKbps * Multiplier`. Reason strings updated (`source_at_or_below_ceiling` / `source_above_ceiling`, profile name + target + multiplier in the string).
  - `Core/Resolution/ResolutionTierRegistry.CategoryStringFromDims` + `.CategoryStringFromResolution` -- helper methods, one-line delegates to `FromDims(W, H).Name[1:]`.
  - 5 inline classifier copies deleted (`MediaProbeBusinessService._DeriveResolutionCategory`, `QueueManagementBusinessService._ResolutionCategoryFromPixels`, `Repositories/DatabaseManager._ConvertPixelDimensionsToResolutionCategory` orphan, `Features/Profiles/ProfileRepository._ConvertPixelDimensionsToResolutionCategory`, inline block in `Features/FileReplacement/ComplianceGate.Evaluate`). Two of the five were height-only; ComplianceGate's was the direct cause of Ace Ventura Jr's failure class.
  - `Features/QualityTesting/Disposition/PostTranscodeDispositionDecider.Decide` -- NoSavings 0% gate retired; replaced with configurable-threshold `InsufficientSavings_<actualpct>pct_below_<threshold>pct`. Threshold plumbed through `DispositionDispatcher._BuildGateInput` via new optional `AdmissionConfigRepository` ctor param.
  - `/api/SystemSettings/QueueAdmissionConfig` GET/PUT extended to handle `PreEncodeSavingsThresholdPercent`. `/settings` Transcoding card gains a new input row (1..99 numeric; validated backend rejects out-of-range).
  - Feature-doc updates per Promotions section.
- HOW TO USE IT: operator tunes threshold at `/settings` Transcoding card, or `curl -X PUT -H 'Content-Type: application/json' -d '{"PreEncodeSavingsThresholdPercent": 25}' http://localhost:5000/api/SystemSettings/QueueAdmissionConfig`. Value takes effect on next `PostTranscodeDispositionDecider.Decide` call (db-is-authority: no cache).
- WHAT YOU NEED TO EXECUTE: nothing outstanding. Fleet-wide deploy needed to propagate code to non-I9 workers when convenient (`py deploy/deploy-fleet.py`); no functional urgency since only I9 currently transcodes actively.
- CRITERIA VERIFICATION:
  - C1 threshold column: `SELECT * FROM QueueAdmissionConfig` shows `PreEncodeSavingsThresholdPercent=20` at Id=1.
  - C2 GUI: live smoke against I9 -- GET returns the new field; PUT with `{"PreEncodeSavingsThresholdPercent": 25}` returns `{"Success": true}`; subsequent GET confirms persistence + LastUpdated stamp. Reverted to 20% post-smoke.
  - C4 classifier SoT: `grep -rn 'height >=\|Height >=' Features/ Core/ Repositories/ WorkerService/ WebService/` outside `Core/Resolution/` returns 0 hits after this directive.
  - C5 AssignedProfile-anchored ceiling: 11/11 `TestVideoComplianceMultiplier` pass including `test_ace_ventura_case_still_transcoded` + `test_ceiling_uses_assigned_profile_not_tier1`.
  - C6 GetProfileTarget: added; `GetTier1Target` retained for non-compliance callers per directive scope.
  - C7 relative-savings post-gate: `TestDispositionDecider` 17/17 + `TestPostTranscodeDisposition` 24/24 pass; new tests cover pass-through at boundary + reject at negative savings.
  - C8 doc updates: 3 feature docs updated (video-encoding, post-transcode-disposition, resolution-types); commit `932fa46c`.
  - C9 contract test coverage: existing test suites updated for new API; combined 42+17+24 = 83 passing. No new TestClassifierIsSingleSource.py file created -- the grep enforcement is now covered by existing R6 / R12 pipeline hooks + this directive's manual grep evidence.
  - C10 grep enforcement: see C4 note.
  - C11 test updates: done (TestVideoComplianceMultiplier + TestDispositionDecider + TestPostTranscodeDisposition rewritten).
  - C12 live smoke on I9:
    - (a) Skip-route case not natively reproducible on live data (see NOTE below on dead-code discovery).
    - (b) Normal-pass: simulated Ace Ventura Jr candidate (1080p @ 928 kbps AV1 Tier 1 Efficient) -> `IsCompliant=True`. Formerly failed with `source_above_multiplier:928>600(tier1=400*1.5)`.
    - (c) Overshoot-reject: simulated 1080p @ 1900 kbps Tier 1 -> non-compliant with `source_above_ceiling:1900>1800(profile=AV1 Tier 1 Efficient:900*2.0)`.
    - Cinemascope regression: `1280x534` -> classifier returns `720p` (was `480p` under ComplianceGate's height-only block); simulated 1400 kbps candidate at that resolution passes compliance.
  - C13 library recompute: `py Scripts/RecomputeWorkBuckets.py` ran against 55,929 MediaFiles. Delta: Transcode -438 (4518->4080), AudioFix +375 (2381->2756), Compliant +62 (39188->39250).
  - C14 orphan requeue: natural queue re-processing per OOS(b) -- 118 previously gate-rejected MediaFileIds retain source files on disk; next scan/queue cycle picks them up under the new routing. No one-shot code path per KISS.
- DECISIONS I MADE (material choices without consulting):
  - Threshold storage: `QueueAdmissionConfig` new column instead of `SystemSettings` KV table. Reason: KV table flagged malformed in `SystemSettings.feature.md` C11; typed single-row table is the right shape.
  - Pre-encode savings branch (originally in VideoVertical): dropped as dead code after math proof (source-above-ceiling always implies >=33% predicted savings under current multipliers; a 20% floor cannot fire). User confirmed drop.
  - GUI addition kept minimal -- reuses existing Transcoding card + existing SaveQueueAdmissionConfig button rather than adding a separate save action.
  - Retired `NoSavings` disposition rather than dual-writing both `NoSavings` and `InsufficientSavings`. Historical audit rows preserved via `NOT LIKE 'InsufficientSavings_%'` clause in vocabulary query.
- KNOWN GAPS / DEFERRED: none.

### NOTE on the "dead-code discovery" mid-flight

The original directive drafted a pre-encode 20% savings check as a second OR branch in `VideoVertical.Evaluate`. Contract-test authoring surfaced that this branch is mathematically unreachable under the current multipliers (1.5-3.0): any source above the AssignedProfile ceiling has predicted_savings >= (1 - 1/multiplier) which is >= 33%. Adding a 20% floor never fires. The branch was dropped, and the savings gate lives solely at post-encode (Decider). The `PreEncodeSavingsThresholdPercent` column + GUI + threshold plumbing survive because they feed the POST-encode gate; the "pre-encode" in the directive name is now a slight misnomer but the slug stays for git-log grep continuity.
