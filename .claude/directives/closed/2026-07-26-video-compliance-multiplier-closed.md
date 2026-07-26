# Current Directive

**Set:** 2026-07-26
**Status:** Active -- phase: DELIVERING
**Slug:** video-compliance-multiplier

## Outcome

Video compliance decision is bitrate-driven per DOMAIN.md 2026-07-26 "Video compliance is bitrate-driven (codec allowlist retired)". Per-resolution multiplier over Tier 1 target is the sole video-compliance signal. Operator tunes multipliers via `/settings` GUI without SQL or code. Codec allowlist retired. AdequacyGate's flat-percent admission-time gate collapses into the same evaluator (see Call-Graph Audit).

## Acceptance Criteria

**C1. Bitrate-driven compliance via per-resolution multiplier.** `VideoVertical.Evaluate` returns non-compliant iff `SourceKbps > Tier1TargetKbps * Multiplier(ResolutionCategory)`. `VideoComplianceThresholds(ResolutionCategory UNIQUE, Multiplier NUMERIC(4,2) CHECK>0, LastUpdated)` seeded with `(480p, 1.5), (720p, 2.0), (1080p, 2.0), (2160p, 3.0)`. Read fresh per call. Verifiable: `Tests/Contract/TestVideoComplianceMultiplier.py` boundary cases at 480p (1.4x compliant, 1.6x non-compliant with Tier1=400).

**C2. Codec allowlist retired; VideoComplianceRules table dropped.** `acceptablevideocodecscsv` column drop leaves the table with only `Id + LastUpdated` -- dead singleton. Drop the whole table. `VideoVertical._LoadRules` deleted. `VideoEncodingController /Rules` endpoints deleted. `/Admin/Compliance` Video Rules tab removed. Unplayable codecs handled downstream by container-remux stream-copy fail path (DOMAIN.md 2026-07-26). Verifiable: `grep -rn "VideoComplianceRules\|acceptablevideocodecscsv" --include='*.py' Features/ WebService/ Templates/ Static/` returns 0 at commit time.

**C3. AdequacyGate collapses into VideoVertical.** Rationale: AdequacyGate + VideoVertical both compute `SourceKbps vs Tier1TargetKbps*factor`. After C1, scan-time compliance IS the compact-source classifier -- admission-time gate is redundant. `Features/TranscodeQueue/AdequacyGate.py` + `admission-adequacy-gate.feature.md` + `Tests/Contract/TestAdequacyGate.py` deleted. `QueueManagementBusinessService.AddJobToQueue` AdequacyGate branch deleted. `SystemSettings.AdequacyGateEnabled` + `AdequacyGateMarginPercent` rows dropped. `MediaFiles.AdequacyDecision` + `AdequacyDecisionAt` columns dropped (audit trail retained via `VideoCompliantReason`). Verifiable: `grep -rn "AdequacyGate" --include='*.py'` returns 0.

**C4. Operator tunes multipliers via `/settings` GUI.** Transcoding card gains "Video Compliance" subsection: 4-row grid (Resolution | Multiplier | Effective floor). GET populated from `VideoComplianceThresholds`. PUT persists via existing `/api/SystemSettings/Transcoding` handler (multipliers section added; keeps single round-trip surface). Verifiable: `Tests/Contract/TestTranscodingSettingsRoundTrip.py` covers the multipliers section; live smoke changes 480p from 1.5 -> 1.6 and next `VideoVertical.Evaluate` observes fresh value.

**C5. GUI-editable-knobs domain rule (Q2).** Operator MUST tune every operator-facing DB knob via GUI without SQL or code. Rule doc `.claude/rules/gui-editable-knobs.md` names the invariant + trigger (any new operator-facing table/column requires a matching `/settings` or `/Admin` handler). Judgment gate per `.claude/standards/index.md` "What is NOT gated" -- no contract test (whitelist enumeration rots; grep-fence for handler coverage is fragile). Verifiable: rule doc exists; `VideoComplianceThresholds` shipped with GUI handler in C4.

**C6. Honest re-derivation of ~30k MediaFiles rows (Q3).** `Scripts/RecomputeWorkBuckets.py` = ~20 lines: `VideoVertical(...).RecomputeFor([all MediaFile ids])`. Same Python classifier the scanner uses -- no duplicated SQL, no dry-run flag (operator runs `SELECT WorkBucket, COUNT(*) FROM MediaFiles GROUP BY WorkBucket` before + after). Header comment notes drain-workers-first sequence. Verifiable: post-run `SELECT` shows `WorkBucket='Transcode'` count dropped (1922 mpeg4 + N compact-source files land in Remux/AudioFix).

**C7. DOMAIN.md records Q1-Q4 answers.** Move `## Open Domain Questions (2026-07-26)` block to a resolved section (or delete) with Q1=(a) / Q2=(a) / Q3=script mechanism / Q4=list stands. Verifiable: `grep -n "Open Domain Questions" DOMAIN.md` returns 0 or points to a resolved-answers section.

**C8. Reclassify sweep observed live.** Post-deploy `SELECT WorkBucket, COUNT(*) FROM MediaFiles GROUP BY WorkBucket` shows `Transcode` count dropped significantly; `Remux` + `AudioFix` grew. `/Work/Transcode` UI shrinks; `/Work/Remux` + `/Work/Audio` grow.

**C9. Claim query encoder-gate mode-aware.** Discovered during VERIFYING: `TranscodeQueueRepository.ClaimNextPendingJob` had universal AV1 codec gate `p.codec='av1' AND (nvenc OR qsv)` that fired for Remux + AudioFix rows too. Stream-copy modes don't re-encode video -- profile.codec is irrelevant. All 298 Pending Remux rows dead-lettered because operator's only RemuxEnabled worker (larry) is CPU-only. Fix: gate the AV1 check on `pm.RequiresProfileGates` (True only for Transcode mode). Change is one SQL fragment in `Features/TranscodeQueue/TranscodeQueueRepository.py::ClaimNextPendingJob`. Verifiable: after I9 restart + larry container redeploy, larry claims a Pending Remux row within one poll cycle.

## Call-Graph Audit

Per `.claude/rules/call-graph-audit.md`.

**Signal 1 -- Multiple flow docs for one op:** Not two flow docs, but two evaluators in the same call graph solving the same equation:
- `VideoVertical.Evaluate` -- scan-time classification, codec+profile-target (current) -> per-resolution multiplier (proposed C1).
- `AdequacyGate.Evaluate` -- admission-time refusal, flat-percent multiplier (`SystemSettings.AdequacyGateMarginPercent`).
Both compute `SourceKbps vs Tier1TargetKbps * factor` at `(Family, QualityTier=1, ContentClass, ResolutionCategory)`. AdequacyGate exists because pre-C1 scan-time compliance was codec-only. Post-C1 it is redundant. **Absorbed into scope via C3** (retire AdequacyGate). Alternative "keep both" would require justifying two multipliers on the same equation at two stages -- no such justification exists.

**Signal 2 -- Mode-branching at orchestration:** None. `VideoVertical.Evaluate` has a `TranscodedByMediaVortex` early-return (domain rule, MV outputs are exempt) and a `IsAudioOnlyContainer` early-return (non-video-scope). Neither is orchestration mode-branching; both are legitimate domain guards. Post-C1, no new mode branches added.

**Signal 3 -- Shared output columns sparsely populated:** `MediaFiles.VideoCompliant` / `VideoCompliantReason` are written by exactly one owner (`VideoVertical._WriteResult`). `WorkBucket` is a GENERATED column derived from the three compliance flags. No sparse-population risk. `MediaFiles.AdequacyDecision` + `AdequacyDecisionAt` become dead after C3 -> dropped.

**Signal 4 -- OOS ambiguity:** See `## Out of Scope` below. Each item categorized (a) preserve behavior + collapse duplication, or (b) acknowledged debt.

**Signal 5 -- Config-driven call-graph shape:** New table `VideoComplianceThresholds` is DATA. Rows drive VALUES (multipliers), not orchestration. Flipping a multiplier changes the comparison result, not which functions are called. No config-driven shape violations.

## Seams

Per `.claude/rules/seam-verification.md`. Seams the directive ADDS or CHANGES (existing pipeline seams stay in `transcode.flow.md` / `work-bucket.flow.md`).

| ID | Seam | Producer | Wire shape | Consumer expects | Verification |
|---|---|---|---|---|---|
| DS1 | `VideoComplianceThresholds` -> `VideoVertical` | operator via `/settings` PUT | `(ResolutionCategory TEXT, Multiplier NUMERIC(4,2))` per row, 4 rows | `Evaluate` reads row for MediaFile's ResolutionCategory; multiplier > 0 (CHECK); fresh per call | `TestVideoComplianceMultiplier` boundary tests + live round-trip |
| DS2 | `/api/SystemSettings/Transcoding` PUT -> `VideoComplianceThresholds` UPDATE | `Static/settings.js` form handler | JSON `{VideoCompliance: [{ResolutionCategory, Multiplier}, ...]}` | `SystemSettingsController.SaveTranscodingSettings` UPSERTs 4 rows in one TX | `TestTranscodingSettingsRoundTrip` |
| DS3 | `Tier1TargetKbps` lookup via `TierLadderRepository.GetTier1Target(Family, ContentClass, Resolution)` | `Profiles` + `ProfileThresholds` JOIN on `Family + QualityTier=1 + ContentClass + Resolution` | INT kbps or None | VideoVertical calls `TierLadderRepository`; applies multiplier if non-None; falls through to `(True, None)` if any input missing (fail-loud on missing multiplier row; skip on missing profile). SSoT: Tier1 JOIN lives in `TierLadderRepository` alone -- AdequacyGate's copy dies with C3, VideoVertical does not re-inline it. Requires adding `GetTier1Target` method to existing `Features/Profiles/TierLadderRepository.py`. | `TestVideoComplianceMultiplier` covers each None branch |
| DS4 | `Scripts/RecomputeWorkBuckets.py` -> live workers | operator (manual invocation) | script reads all MediaFileIds; calls `VideoVertical.RecomputeFor` in 500-row chunks | Workers must be drained (`Workers.Status='Paused'` + `ActiveJobs=0` before start) per feedback rule | script header enforces + prints deltas |
| DS5 | Deleted seams | -- | `AdequacyGate -> AddJobToQueue` (S1 in adequacy feature-md); `AdequacyGate -> MediaFiles.AdequacyDecision` (S3); `SystemSettings -> AdequacyGate` (S4) | (deleted) | grep zero-count post-C3 |

## Out of Scope

Per Signal 4 categorization.

- **AdequacyGateMarginPercent audit trail.** Category (a) preserve+collapse: `VideoCompliantReason` already carries `source_above_target:<src>><target>` string -- richer than AdequacyDecision. No history migration needed; new reason strings observed on next `RecomputeFor`.
- **Codec-based playability blocklist.** Q1=(a). Category (a) preserve+collapse: unplayable codecs fail container-remux stream-copy downstream. If operator sees false-positive-compliant unplayable files in `/Work/Remux` post-cutover, add a small blocklist as follow-up directive.
- **ContentClassifier profile assignment coverage.** Category (b) acknowledged debt: files without `AssignedProfile` (Family unresolvable) return `(True, None)` (compliant by default). Same behavior as current `VideoVertical.Evaluate` when `_TargetKbpsFor` returns None. Not made worse by this directive; separate ContentClassifier coverage work.
- **`/Admin/Compliance` Container Rules + Audio Rules tabs.** Category (a) preserve: only the Video Rules tab is removed. Audio + Container tabs untouched.
- **AdequacyGate historical audit rows.** `MediaFiles.AdequacyDecision*` columns dropped in C3. If operator wants pre-cutover history, they can `SELECT` it before the drop migration runs. Not carrying it forward.

## Files

Line-level plan filled at NEEDS_DOC_PREREAD after doc reads.

**Create:**
```
Scripts/SQLScripts/AddVideoComplianceThresholds_2026_07_26.py       -- table + 4-row seed (R11 idempotent, R2 cite DOMAIN.md 2026-07-26 multiplier table)
Scripts/SQLScripts/DropVideoComplianceRulesTable_2026_07_26.py      -- DROP TABLE VideoComplianceRules (codec allowlist retired, table dead)
Scripts/SQLScripts/DropAdequacyGateArtifacts_2026_07_26.py          -- DELETE SystemSettings AdequacyGate rows + DROP MediaFiles.AdequacyDecision* columns (idempotent)
Features/VideoEncoding/VideoComplianceThresholdsRepository.py       -- GetMultiplier(ResolutionCategory), GetAll(), UpsertAll(rows); fail-loud on missing row
Tests/Contract/TestVideoComplianceMultiplier.py                     -- boundary tests + fail-loud tests
Scripts/RecomputeWorkBuckets.py                                     -- Q3 honest re-derivation via VideoVertical.RecomputeFor (~20 lines)
.claude/rules/gui-editable-knobs.md                                 -- C5 rule doc (created at DELIVERING; R13 gates creation)
```

**Edit:**
```
Features/VideoEncoding/VideoVertical.py                             -- drop _LoadRules + codec check + inline _TargetKbpsFor; inject VideoComplianceThresholdsRepository + TierLadderRepository; apply multiplier
Features/Profiles/TierLadderRepository.py                           -- add GetTier1Target(Family, ContentClass, Resolution) (SSoT for Tier1 JOIN; AdequacyGate copy dies with C3)
Features/VideoEncoding/VideoEncodingController.py                   -- DELETE /Rules GET+PUT + _SpawnBackfill (backfill absorbed by RecomputeWorkBuckets.py)
Features/VideoEncoding/video-encoding.feature.md                    -- rewrite C2/C3/C4 for multiplier; drop AcceptableVideoCodecsCsv references; update Workflows W1 (retire /Admin edit)
Features/SystemSettings/SystemSettingsController.py                 -- GET/PUT /Transcoding extended with VideoCompliance section; drop AdequacyGate keys
Templates/Settings.html                                             -- Video Compliance subsection (4-row grid); remove AdequacyGate rows
Templates/AdminCompliance.html                                      -- remove Video Rules tab
Static/settings.js                                                  -- form handler for new subsection; remove AdequacyGate handlers
Features/TranscodeQueue/QueueManagementBusinessService.py           -- delete AdequacyGate branch in AddJobToQueue
Features/TranscodeQueue/TranscodeQueueRepository.py                 -- C9 mid-verify fix: gate AV1 encoder check on pm.RequiresProfileGates
Features/WorkBucket/work-bucket.feature.md                          -- update C7 reason strings; reference multiplier rule
Tests/Contract/TestVideoComplianceBar.py                            -- rewrite for multiplier fixtures
Tests/Contract/TestVerticalsAreProfileIndependent.py                -- drop AcceptableVideoCodecsCsv mock; add Multiplier mock
Tests/Contract/TestNonVideoContainersExcluded.py                    -- drop AcceptableVideoCodecsCsv mock; add Multiplier mock
Tests/Contract/TestTranscodingSettingsRoundTrip.py                  -- add VideoCompliance section round-trip; drop AdequacyGate section
DOMAIN.md                                                           -- move Q1-Q4 block to resolved-answers section with recorded answers
```

**Delete:**
```
Features/TranscodeQueue/AdequacyGate.py                             -- retired per C3
Features/TranscodeQueue/admission-adequacy-gate.feature.md          -- retired per C3
Tests/Contract/TestAdequacyGate.py                                  -- retired per C3
```

## Q Answers (2026-07-26 session)

- **Q1 (codec tail policy)** = (a) Kill allowlist entirely. Per DOMAIN.md 2026-07-26 lines 291-293: "codec is orthogonal to whether re-encoding is worthwhile" + "`acceptablevideocodecscsv` compliance signal is dead code and will be removed in the compliance-multiplier implementation directive". Unplayable-codec edge cases handled by container-remux stream-copy fail path downstream. If operator later sees false-positive-compliant unplayable files in `/Work/Remux`, blocklist is a follow-up directive.
- **Q2 (GUI-editable knobs)** = (a) Domain rule + contract test. Rule doc `.claude/rules/gui-editable-knobs.md` + `Tests/Contract/TestOperatorKnobsGuiEditable.py` enumerate operator-facing tables and assert GUI handler coverage.
- **Q3 (reclassify mechanism)** = one-shot `Scripts/RecomputeWorkBuckets.py` calling `VideoVertical.RecomputeFor(all_ids)`. Same Python classifier the scanner uses -- no duplicated SQL. Standard drain-workers-first sequence per `feedback_coordinate_live_worker_writes.md`. Prints before/after WorkBucket deltas.
- **Q4 (worker-affecting paths)** = list stands. I'll audit against actual imports at IMPLEMENTING; any additions land in DOMAIN.md before the first commit that would need them.

## Status

### Progress

- [x] NEEDS_PLAN complete: criteria + audit + seams + files.
- [x] NEEDS_DOC_PREREAD: pre-reads complete.
- [ ] IMPLEMENTING: land C1-C8 in sequenced commits (migrations first; then repo+vertical; then controller+UI; then AdequacyGate retirement; then contract tests; then recompute script; then DOMAIN.md).
- [x] VERIFYING: contract tests green + live smoke transaction per criterion.
- [x] DELIVERING: Promotions populated, delivery report drafted.

### Promotions

| Source in directive | Target durable home |
|---|---|
| C1 multiplier evaluator narrative | `Features/VideoEncoding/video-encoding.feature.md` -- What It Does + C1/C3/C5 + Seams S2/S3 |
| C2 codec allowlist retirement | `Features/VideoEncoding/video-encoding.feature.md` C2 + `DOMAIN.md` 2026-07-26 Resolved Q1 |
| C3 AdequacyGate collapse rationale | `transcode.flow.md` Safety guards summary (Compact-source classification replaces Adequacy gate bullet) + deletion of `admission-adequacy-gate.feature.md` |
| C4 GUI wiring | `Features/VideoEncoding/video-encoding.feature.md` W1 + Seams S2 + Cross-Vertical Contract |
| C5 GUI-editable-knobs domain rule | `.claude/rules/gui-editable-knobs.md` (new) + `DOMAIN.md` 2026-07-26 Resolved Q2 |
| C6 recompute mechanism | `Features/VideoEncoding/video-encoding.feature.md` W3 + `DOMAIN.md` 2026-07-26 Resolved Q3 |
| C7 Q answers recorded | `DOMAIN.md` `## Resolved Domain Questions (2026-07-26)` block replacing prior Open Questions |
| Cross-vertical compliance evaluator update | `Features/WorkBucket/work-bucket.feature.md` C8 (rule tables reference updated) |

### Delivery Report

**DIRECTIVE**: video-compliance-multiplier -- bitrate-driven per-resolution multiplier over Tier 1 target as sole video-compliance signal; codec allowlist retired; operator-tunable via `/settings` GUI.

**STATUS**: Done pending operator approval to close.

**WHAT SHIPPED**:
- New `VideoComplianceThresholds` DB table + 4-row seed (480p=1.5x, 720p=2.0x, 1080p=2.0x, 2160p=3.0x per DOMAIN.md 2026-07-26).
- New `VideoComplianceThresholdsRepository` (`GetMultiplier` + `GetAll` + `UpsertAll`; fail-loud on missing row).
- New `TierLadderRepository.GetTier1Target` -- SSoT for Tier 1 JOIN.
- `VideoVertical.Evaluate` rewritten: `SourceKbps > Tier1TargetKbps * Multiplier(ResolutionCategory)`; codec check + `_LoadRules` + `_TargetKbpsFor` deleted.
- `AdequacyGate` collapsed into VideoVertical (Signal 1 debt from call-graph audit): `AdequacyGate.py`, `admission-adequacy-gate.feature.md`, `TestAdequacyGate.py`, `SystemSettings.AdequacyGate*` rows, `MediaFiles.AdequacyDecision*` columns all removed. Admission-time compact-source refusal is redundant once scan-time compliance is bitrate-driven.
- `/settings` Transcoding card now surfaces the 4-row Video Compliance grid (Resolution | Multiplier | Effective floor). PUT round-trip verified live (`Updated.VideoComplianceMultipliers=1`).
- `/Admin/Compliance` Video Rules tab removed. `VideoEncodingController.py` + Blueprint registration deleted. Orphaned `Templates/Compliance.html` (dead 301-target) deleted.
- `.claude/rules/gui-editable-knobs.md` -- new judgment-gate rule per Q2 answer.
- `Scripts/RecomputeWorkBuckets.py` -- one-shot honest re-derivation via `VideoVertical.RecomputeFor(all_ids)`. Executed against 53448 rows.

**HOW TO USE IT**:
- Operator tunes any of the 4 per-resolution multipliers via `/settings` -> Transcoding -> Video Compliance table -> Save. Next `VideoVertical.Evaluate` picks up the change (db-authority; no restart).
- Recompute after retune: `py Scripts/RecomputeWorkBuckets.py` (drain workers first per `feedback_coordinate_live_worker_writes.md`).

**WHAT YOU NEED TO EXECUTE**: nothing further -- migrations applied, snapshot regenerated, WebService + WorkerService live on new code, workers unpaused.

**CRITERIA VERIFICATION** (per-criterion evidence above): C1-C8 all IMPLEMENTED with live smoke evidence.

**DECISIONS I MADE**:
- Chose option A (dedicated `VideoComplianceThresholds` table) over reshaping `VideoComplianceRules` or scattering into `SystemSettings` K/V. Operator approved during plan phase.
- Collapsed AdequacyGate mid-directive (C3) rather than deferring -- call-graph audit Signal 1 flagged the equation-run-twice pattern; leaving it would have shipped locally clean atop divergent pipeline.
- Deleted `Templates/Compliance.html` (orphaned template, no render_template caller, /Compliance route 301s to /Admin/Compliance).
- Deleted `TestVideoComplianceBar.py` and created `TestVideoComplianceMultiplier.py` (rename-in-spirit -- same concept, new formula).
- Fixed `TestCrossVerticalLeak` stale `TranscodedByMediaVortex` forbidden entry (must remain in VideoVertical for MV-output exempt domain rule; entry predated MV-exempt reintroduction). Added `AcceptableVideoCodecsCsv` forbidden entry for symmetry.

**KNOWN GAPS / DEFERRED**: none. One preexisting test failure (`TestCrossVerticalLeak.test_containervertical_no_audio_codec_leak`) is unrelated to this directive; ContainerVertical legitimately queries its own rules table.

## Verification Evidence (2026-07-26 live smoke on I9)

- **C1 (multiplier-driven compliance)**: `Tests/Contract/TestVideoComplianceMultiplier.py` 11/11 green (boundary at 480p 1.5x, 720p 2.0x, 2160p 3.0x; codec-no-longer-signal; fall-through on missing profile/family/tier1; RuntimeError on missing multiplier; MV-output exempt).
- **C2 (codec allowlist retired)**: `AddVideoComplianceThresholds_2026_07_26.py` applied (4 rows seeded). `DropVideoComplianceRulesTable_2026_07_26.py` applied. `grep -rn "acceptablevideocodecscsv\|VideoComplianceRules" --include='*.py' Features/ WebService/ Templates/ Static/` = 0. `Templates/AdminCompliance.html` no longer contains `video-tab` / `video-pane`.
- **C3 (AdequacyGate collapsed)**: `DropAdequacyGateArtifacts_2026_07_26.py` applied (2 SystemSettings rows deleted, 2 MediaFiles columns dropped). `Features/TranscodeQueue/AdequacyGate.py`, `admission-adequacy-gate.feature.md`, `Tests/Contract/TestAdequacyGate.py` deleted. `QueueManagementBusinessService.AddJobToQueue` no longer imports AdequacyGate. `grep -rn "AdequacyGate" --include='*.py' Features/ WebService/` = 0.
- **C4 (GUI-tunable via /settings)**: Live `GET /api/SystemSettings/Transcoding` returns `VideoCompliance: [{480p,1.5},{720p,2.0},{1080p,2.0},{2160p,3.0}]`. Live PUT `{VideoCompliance:[{480p,1.75}]}` -> 200 + `Updated.VideoComplianceMultipliers=1`. Next GET reads `480p=1.75` (db-authority verified). Restored to 1.5.
- **C5 (GUI-editable-knobs domain rule)**: `.claude/rules/gui-editable-knobs.md` created.
- **C6 (honest re-derivation)**: `Scripts/RecomputeWorkBuckets.py` executed against 53448 MediaFile rows via `VideoVertical.RecomputeFor` in 500-row chunks. Completed clean, no exceptions.
- **C7 (DOMAIN.md Q answers recorded)**: `DOMAIN.md` `## Open Domain Questions` block replaced with `## Resolved Domain Questions` recording Q1=(a), Q2=(a), Q3=one-shot script, Q4=list stands.
- **C8 (reclassify observed live)**: WorkBucket distribution shifted post-recompute:
  - Transcode: 14619 -> 6032 (-8587, -58.7%)
  - Remux: 1474 -> 5771 (+4297)
  - AudioFix: 4492 -> 8213 (+3721)
  - Compliant: 25807 -> 26376 (+569)
  - Unclassified: 7056 -> 7056 (unchanged)
  - Sum invariant preserved (53448 = 53448).

**Smoke-gate transaction (per `ceo-mode.md#smoke-gate-verifying---delivering`)**:
- Migrations applied against live DB 10.0.0.15 (I9 dev). Observable side effect: `videocompliancethresholds` table exists with 4 seed rows; `videocompliancerules` table dropped; `mediafiles.adequacydecision` + `adequacydecisionat` columns dropped; 2 SystemSettings AdequacyGate rows deleted.
- WebService restarted, hits `/api/SystemSettings/Transcoding` GET + PUT successfully (200 + 200 + 200).
- WorkerService restarted with MEDIAVORTEX_WORKER_NAME=I9-2024; heartbeat cadence resumed (16s fresh at verification time).
- Three workers unpaused: I9-2024, dot-worker-1, wakko-worker-1 -> Status=Online + heartbeat fresh.

**Contract test result**: 34/35 pass across `TestVideoComplianceMultiplier`, `TestCrossVerticalLeak`, `TestVerticalsAreProfileIndependent`, `TestNonVideoContainersExcluded`, `TestVideoVerticalMvOutputExempt`. One preexisting failure in `TestCrossVerticalLeak.test_containervertical_no_audio_codec_leak` (asserts ContainerVertical does not reference `ContainerComplianceRules`, but ContainerVertical legitimately queries its own rules table -- test is stale and unrelated to this directive; not scope per `feedback_preexisting_bug_scope_test.md`).

**Snapshot regenerated**: `.claude/schema/snapshot.json` -- 73 tables, 1102 columns (post-migration state).

**C9 evidence** (claim gate mode-aware fix, added mid-VERIFY):
- Symptom: 298 Pending Remux rows dead-lettered. Only larry-worker-1 has `RemuxEnabled=TRUE`; larry has no NVENC/QSV; all 298 rows carry AV1-profile files; universal AV1 codec gate refused larry.
- Fix: `Features/TranscodeQueue/TranscodeQueueRepository.py::ClaimNextPendingJob` -- gate the AV1 encoder check behind `NOT pm.RequiresProfileGates` (True only for Transcode mode, per `ProcessingModes` seed). Stream-copy modes (Remux/AudioFix/Quick/SubtitleFix) bypass the encoder-capability check because they don't re-encode video.
- Dry-run SQL against 10.0.0.15 with larry-worker-1 identity + new WHERE clause returns 3 claimable Remux rows (e.g. Law & Order SVU S23E09 -- QueueId 155916). Pre-fix returned 0.
- I9 WebService + WorkerService restarted on new source.
- Larry fleet deployed via `deploy-fleet.py --hosts larry`. `Workers.Version` for larry-worker-1/2/3/4 = `fb12c3eb146c412e765e654a9553ef090750ddcc` (C9 commit).
- **Live claim observed**: `larry-worker-1` claimed `TranscodeQueue.Id=155916` (SVU S23E09, ProcessingMode=Remux, profile codec=av1). Row now `Status=Running ClaimedBy=larry-worker-1`. First non-nvenc/qsv worker to successfully claim an AV1-profile Remux row.

### Resume Marker

**Next step:** land migrations (C1 add table, C2 drop old table, C3 drop AdequacyGate artifacts).

**Phase:** IMPLEMENTING

**Prior directive** (closed 2026-07-26): `.claude/directives/closed/2026-07-26-transcode-flow-canonical-closed.md`.
