# Target Policy Program Plan

> **For agentic workers:** execute one phase per session. Each phase is one directive opened with `/n <slug>`, ends with the Phase Exit Checklist, a commit, a push, a handoff update in memory `project_handoff_target_policy.md`, and a `/clear`. The spec is `Docs/superpowers/specs/2026-11-27-target-policy-architecture-design.md`; read it fully before any phase. Evidence: `Docs/superpowers/audits/2026-11-26-knob-inventory.md`, `Docs/superpowers/audits/2026-11-26-branching-audit.md`.

**Goal:** the spec's section 1. Facts stored, policy in one home each, target resolved by one view, pipeline shape fixed, no stored derived state, review as a state. After Phase 8 a new library, codec, fps class, encoder or tier is an INSERT.

**Operating rules for every phase**
- Read only: `.claude/rules/*.md` (auto), the spec, this file, the phase's named docs. Nothing else until a step needs it.
- Golden tests are the safety net: `Tests/Contract/TestGoldenTvCommands.py` (one TV fixture's Transcode + AudioFix argv) and the compliance-count snapshot (`Tests/Contract/TestComplianceCountsUnchanged.py`, TV + Movies counts per dimension written at Phase 1 and asserted after every migration). A phase that moves either does not ship; the cause is fixed, never the test.
- Every migration script is idempotent, regenerates `.claude/schema/snapshot.json`, and is applied live in the same phase (`db-is-authority`; a column that exists in code but not in the DB is a failed phase).
- Hygiene is part of every phase: delete what the phase makes dead in the same commit; `grep -rn <Name> --include=*.py` before every deletion.
- Smoke tests run on fleet workers (dot NVENC, wakko QSV), never I9, always on COPIES, per `/mediavortex-smoke-transcode`.

**Resume protocol (start of every session)**
1. Read memory `project_handoff_target_policy.md` (RESUME HERE in `MEMORY.md`).
2. Open this plan at the phase the handoff names, first unticked step.
3. Operator trigger phrase: "continue target policy". Nothing else is needed.

**Phase Exit Checklist (mandatory, every phase)**
1. Criteria: every criterion the phase owns is verified live (farm server + a fleet worker where a worker is involved) and its evidence is in the directive and the owning feature doc.
2. Golden tests + compliance-count snapshot pass; command and result recorded.
3. Decisions single-sourced: every decision lives in `ARCHITECTURE.md` or `transcode.flow.md` Domain Decisions or the vertical's `*.feature.md`, once; the spec is not cited from code or docs as an authority after Phase 0.
4. Stale text deleted, not annotated (R14); grep the phase's old terms.
5. Dead code deleted: zero callers = delete in the same commit.
6. Contract tests for touched verticals pass; `TestFailLoud` baseline for the touched files does not grow.
7. Commit + push; `git status --short` clean except operator-owned files.
8. Handoff memory: dated "Phase N done" paragraph (shipped, operator-visible, decisions, "nothing deferred"), "Next" line set.
9. Print verbatim: "Phase N complete and pushed. Clear now (`/clear`). To resume: say "continue target policy". Next session starts Phase N+1 step 1: <one line>."

Only after step 9 is printed does the session end. If 1 to 8 cannot complete, the phase is not done: say which item and why; do not print step 9.

---

## Phase 0: Reconcile and write the architecture  (docs only)

1. `/n target-policy-architecture`. Docs-first directive (R13 override rows for the new `Features/Policy/policy.feature.md`).
2. Copy the two audit reports to `Docs/superpowers/audits/` (done 2026-11-27 if present; verify).
3. Close directive `xxx-video-tier` as `Closed -- Partial (superseded by target-policy program)`: its code (reassign for any tiered library, overrides checkbox) is shipped and harmless and is deleted in Phase 2; criteria 4-7 are met by Phase 6 instead. Operator confirms the close in-session before the status edit.
4. `ARCHITECTURE.md`: Vertical Roster `Profile` row -> `Policy` (owns the tables of spec 4.1-4.5, the view, `TargetResolver`, `EncoderSelector`, genre sync); remove `ContentClassifier`; Cross-Cutting Concerns add `MediaFileTargets` view + `Target`; Data Flow drops the "ContentClassifier assigns Profile" line; Database Invariants add "policy tables read only by `Features/Policy/`" and "no stored derived target"; `## Gap to Target` lists Phases 1-7 with their slugs.
5. `transcode.flow.md`: D2 "Copy untouched" reads the policy's default track; D4 dimension table becomes one video row (tier path) and the audio row becomes "tracks match policy"; D6 "tracks per policy"; D7 "our output whose tracks matched policy"; new D13 "target is resolved by `MediaFileTargets`, never stored"; ST3 marked deleted (ID retained); ST7 decision table from spec section 6 (adds `Hold`). `ingest.flow.md`: ST5 Classify deleted, genre sync named under Policy.
6. `GLOSSARY.md`: `Target`, `LadderCell`, `FrameRateClass`, `TargetOverride`, `Hold`; deprecate `AssignedProfile`, `profile assignment`, `classifier`.
7. Create `Features/Policy/policy.feature.md` (Slug `policy`) with W/C/S IDs for: resolve target, override tier, edit ladder, edit encoder settings, edit tier acceptance; criteria from spec section 9.
8. Deliver, close, commit, push, handoff memory, `/clear`.

## Phase 1: Policy vertical, view, resolver, consumers switched  (no deletions yet)

1. `/n target-policy-resolver`. Criteria: spec 9.2 for the new tables; golden + count tests exist and pass before any consumer switch.
2. Golden + snapshot tests written first against current code (TV fixture Transcode and AudioFix argv; TV + Movies compliance counts).
3. Migration `AddTargetPolicyTables_2026_11_27.py`: `TargetOverrides`, `FrameRateClasses`, `EncoderSettings`, `LadderCells` (populated from `ProfileThresholds` standard + high x1.5), `Profiles` acceptance columns (from `PostTranscodeGateConfig`), `StorageRoots.ReviewBeforeReplace`, `StorageRoots` NOT NULL tier/class (xxx set to 3 / live_action / review TRUE as data in this migration, operator-confirmed in session), the VIEW `MediaFileTargets`. Data migration of `SeriesProfiles` and operator/manual `AssignedProfile` into `TargetOverrides`. Snapshot regenerated.
4. `Features/Policy/`: `Target` dataclass, `TargetResolver` (one SELECT on the view), `EncoderSelector`, repositories for the five tables, `MovieGenreSyncService` moved here. Rename `Features/Profiles` -> `Features/Policy` (git mv; update imports in one commit).
5. Consumers take `Target`: `VideoVertical.Evaluate(Facts, Target)`, `AudioVertical.Evaluate(Facts, Target)` (admission-gate side effects moved to `AddJobToQueue`), `ContainerVertical.Evaluate(Facts, Target)`; `RecomputeForFiles` resolves once per file and passes it; admission (`EvaluateQueueAdmission`) and `CommandComposer.Build` take `Target` + `EncoderSettings`; `DispositionDispatcher` builds the decider input from `Target`. Old `AssignedProfile` column still exists but nothing reads it for decisions.
6. GUI: ladder grid gains the frame-rate tab; encoder settings grid; tier acceptance table; override controls on `/Work` write `TargetOverrides`; library table gains review-before-replace.
7. Golden + snapshot pass; deploy server + fleet; one TV Transcode and one TV AudioFix on a fleet worker byte-identical to the golden argv.
8. Deliver, close, commit, push, handoff memory, `/clear`.

## Phase 2: Delete the stored target and the classifier

1. `/n target-policy-delete-stored`. Criteria: spec 9.1, 9.9 for `ReassignTierProfiles`, `ContentClassificationRules`, `SeriesProfiles`, `WorkerEncoderResolver`, `ProcessingModeMetadata`.
2. Migration drops `MediaFiles.AssignedProfile/AssignedProfileSource/KeepSource`, `SeriesProfiles`, `ContentClassificationRules`, `ProfileThresholds` (replaced by `LadderCells`), the dropped `Profiles` columns (spec 4.3), `TranscodeFiles.SuccessfullyTranscoded`, `TranscodeQueue.AudioSlotOverride`, the four STREAMING profiles, dead `SystemSettings` keys (inventory list), `DefaultProfileName`, `CRFOverride_*`.
3. Code deletions: `Features/ContentClassifier/` (whole vertical), `ProfileAssignmentService`, `SeriesProfileService`, `EffectiveProfileResolver`, `EncoderKnobRepository`, `WorkerEncoderResolver`, `HwAccelResolver` worker reads, `ProcessingModeMetadata`, `AddJobToQueue` ProfileId/QualityTier/QualityLabel parameters and the three profile write paths, `/settings` classifier-rules card and the `/Optimization` profile dropdown, `TestMoviesVideoRule` reassign tests (replaced by Policy tests).
4. `TestTargetAuthority`, `TestKnobInventory`, `TestPipelineShape` added; `TestFailLoud` baseline for the decision layer set to 0.
5. Golden + snapshot pass; deploy; live: change one TV series override on `/Work`, observe recompute with no reassign step (spec 9.6).
6. Deliver, close, commit, push, handoff memory, `/clear`.

## Phase 3: Audio authority  (spec 4.6; absorbs xxx Unit 3)

Order inside the phase is the TV safeguard. Do not reorder.

1. `/n target-policy-audio`. Criteria: TV golden AudioFix argv unchanged; TV and Movies `AudioCompliant` counts unchanged; one xxx copy through AudioFix yields one aac stream at -26 within tolerance, no Demucs step; `grep no_dialog_boost` = 0.
2. Migration: `AudioPolicyTracks` seeded from live `AudioComplianceRules` values for the global policy; library policy row for xxx (ScopeKey 3) with one `Original` aac 128 -26 default; drop `EmitTracks`, `TargetLra`, `PreVerticalReNormalizePolicy`; drop the eight track columns from `AudioComplianceRules`. Snapshot.
3. Emitter iterates `AudioPolicyTracks`; `PreEncodeAudioPipeline` runs Demucs only when a `Dialog Boost` track exists; `AudioStrategyClassifier` reads track targets (no `-23/-2/3` defaults); Copy path reads the policy default track for conversion.
4. `AudioVertical`: tracks-match-policy + loudness within tolerance; no side effects; `no_dialog_boost` deleted.
5. GUI: `/AudioNormalization` tracks sub-table; `/Admin/Compliance` loses the eight knobs.
6. Golden + snapshot pass; deploy; live TV AudioFix on a fleet worker byte-identical; live xxx COPY through AudioFix per criteria.
7. Deliver, close, commit, push, handoff memory, `/clear`.

## Phase 4: Verification and Hold  (spec 4.9, 6)

1. `/n target-policy-verification`. Criteria: decision table of spec section 6 implemented as a pure function with a table-driven contract test; `Hold` retains `.ip` and appears on `/QualityTesting` with Replace/Reject; larger output rejected in the decider; `grep SmartConfidence|RetryBudgetService|GetKeepSourceSetting` = 0.
2. Migration: `PostTranscodeGateConfig` -> `VerificationConfig` (keep `MaxRequeueAttempts`, add `MinOutputSavingsPercent`); drop the listed columns; `ProcessingModes` dead columns dropped. Snapshot.
3. `PostTranscodeDispositionDecider.Decide(AttemptFacts, Target)` pure; `DispositionDispatcher` no longer swallows exceptions to `Pending`; `Hold` path in ST9; Requeue = `LadderCells(Tier+1)`; `FailureBudgetService` is the one budget.
4. `/QualityTesting` Hold list (stills, percentiles, buttons); Override API accepts `Hold` rows.
5. Deploy; live: one fleet smoke on a COPY lands in `Hold`, resolved to Reject by the operator, `.ip` cleaned; one TV job replaces as before.
6. Deliver, close, commit, push, handoff memory, `/clear`.

## Phase 5: Container and command hygiene  (spec 4.5, 4.7)

1. `/n target-policy-command`. Criteria: `ContainerSlot`/`OutputFilenameBuilder` read `OutputContainer`; `VideoSlot` reads only `EncoderSettings` + `Target`; golden argv unchanged; one `ResolutionCategory` derivation (`ResolutionTierRegistry`); `JobProcessor` output path from `OutputFilenameBuilder`.
2. Delete the four container homes, `ResolutionCalculator` dims table and `TranscodedOutputPlacement` width table (both read the registry), `DetectNormalizationInCommand` (reads `DialogBoostEmitted`), `Remux`/`AudioFix` duplicate strategy classes (one `CopyVideoJobStrategy` parameterised by label), the mid-job `RecomputeForFiles` calls (`AudioPreEncodeFacade:85`, `JobProcessor:83`; loudness persists without cascade until ST9 recompute).
3. Golden + snapshot pass; deploy + fleet; one Remux and one Transcode on fleet workers byte-identical.
4. Deliver, close, commit, push, handoff memory, `/clear`.

## Phase 6: xxx as data  (absorbs xxx Units 2-3 operator steps)

1. `/n xxx-target-data`. Criteria: `SELECT COUNT(*) FROM MediaFileTargets WHERE StorageRootId=3 AND Tier<>3` = 0; 2160p ceiling as the operator set it; one xxx 4K `high` and one `standard` file encode from COPIES on dot and wakko, land in `Hold`, VMAF and stills visible, operator resolves; TV and Movies counts unchanged.
2. Operator on `/settings`: confirm xxx tier 3 / live_action (set by Phase 1 migration), decide 2160p multiplier, decide `high` ladder kbps for 2160p after seeing the two smokes, decide `ReviewBeforeReplace` flip to FALSE.
3. Smoke per `/mediavortex-smoke-transcode` (copies, fleet only).
4. Deliver, close, commit, push, handoff memory, `/clear`.

## Phase 7: Close-out  (verification only)

1. Re-run spec section 9 criteria 1-9 end to end; `ARCHITECTURE.md` `## Gap to Target` empty; `TestKnobInventory` dead list empty; `TestFailLoud` decision-layer baseline 0.
2. `git status --short` clean; `git log origin/main..HEAD` empty.
3. Program summary paragraph in memory; state plainly: no deferred work, no known gaps. Then `xxx-cull` (spec 2026-10-28 Unit 4) resumes as its own program.
