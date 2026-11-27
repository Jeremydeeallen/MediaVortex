# Target Policy Program Plan

> **For agentic workers:** execute one phase per session. Each phase is one directive opened with `/n <slug>`, ends with the Phase Exit Checklist, a commit, a push, a handoff update in memory `project_handoff_target_policy.md`, and a `/clear`. The spec is `Docs/superpowers/specs/2026-11-27-target-policy-architecture-design.md`; read it fully before any phase. Evidence: `Docs/superpowers/audits/2026-11-26-knob-inventory.md`, `Docs/superpowers/audits/2026-11-26-branching-audit.md`.

**Goal:** the spec's section 1. Facts stored, policy in one home each, target resolved by one view, pipeline shape fixed, no stored derived state, review as a state. After Phase 8 a new library, codec, fps class, encoder or tier is an INSERT.

**Operating rules for every phase**
- Read only: `.claude/rules/*.md` (auto), the spec, this file, the phase's named docs. Nothing else until a step needs it.
- Golden tests are the safety net: `Tests/Contract/TestGoldenTvCommands.py` (one TV fixture's Transcode + AudioFix argv) and the compliance-count snapshot (`Tests/Contract/TestComplianceCountsUnchanged.py`, TV + Movies counts per dimension written at Phase 1 and asserted after every migration). A phase that moves either does not ship; the cause is fixed, never the test.
- Every migration script is idempotent, regenerates `.claude/schema/snapshot.json` (`py Scripts/Migration/GenerateSchemaSnapshot.py`; `TestSchemaSnapshot` green), and is applied live in the same phase (`db-is-authority`; a column that exists in code but not in the DB is a failed phase).
- Destructive migrations (any DROP, rename, NOT NULL tightening, CHECK) follow one order, every phase: (1) additive migration applied live; (2) server + fleet deployed on the new code (deploy drains in-flight work); (3) `pg_dump --data-only --table=<t>` of every table or column set about to be dropped into `Docs/superpowers/audits/dropped/<date>-<table>.sql` (committed); (4) destructive migration applied live, with the operator's explicit go in-session (irreversible); (5) snapshot regenerated. Old worker code never runs against a schema missing its columns.
- Golden argv fixture shape: a frozen `MediaFile` row + frozen ffprobe JSON (the audio emitter probes live) in `Tests/Contract/Golden/`, driven through the public entry (`CommandComposer.Build`) with the DB stubbed at the repository seam. Expected argv lives in `tv-transcode.argv` and `tv-audiofix.argv`; a phase swaps the stub, never the files.
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

## Phase 0: Reconcile and write the architecture  (docs only) -- done 2026-11-27 (`target-policy-architecture`)

1. `/n target-policy-architecture`. Docs-first directive (R13 override rows for the new `Features/Policy/policy.feature.md`).
2. Copy the two audit reports to `Docs/superpowers/audits/` (done 2026-11-27 if present; verify).
3. Close directive `xxx-video-tier` as `Closed -- Partial (superseded by target-policy program)`: its code (reassign for any tiered library, overrides checkbox) is shipped and harmless and is deleted in Phase 2; criteria 4-7 are met by Phase 6 instead. Operator confirms the close in-session before the status edit.
4. `ARCHITECTURE.md`: Vertical Roster `Profile` row -> `Policy`; Database Invariants also name the `WorkBucket` expression as the one home of D7 (spec 3) (owns the tables of spec 4.1-4.5, the view, `TargetResolver`, `EncoderSelector`, genre sync); remove `ContentClassifier`; Cross-Cutting Concerns add `MediaFileTargets` view + `Target`; Data Flow drops the "ContentClassifier assigns Profile" line; Database Invariants add "policy tables read only by `Features/Policy/`" and "no stored derived target"; `## Gap to Target` lists Phases 1-7 with their slugs.
5. `transcode.flow.md`: D2 "Copy untouched" reads the policy's default track; D4 dimension table becomes one video row (tier path) and the audio row becomes "tracks match policy"; D6 "tracks per policy"; D7 "our output whose tracks matched policy"; new D13 "target is resolved by `MediaFileTargets`, never stored"; ST3 marked deleted (ID retained); ST7 decision table from spec section 6 (adds `Hold`). `ingest.flow.md`: ST5 Classify deleted, genre sync named under Policy.
6. `GLOSSARY.md`: `Target`, `LadderCell`, `FrameRateClass`, `TargetOverride`, `Hold`; deprecate `AssignedProfile`, `profile assignment`, `classifier`.
7. Create `Features/Profiles/policy.feature.md` (Slug `policy`; colocated with the code Phase 1a renames to `Features/Policy/`, the `git mv` carries it) with W/C/S IDs for: resolve target, override tier, edit ladder, edit encoder settings, edit tier acceptance, edit library/genre/frame-rate policy; criteria from spec section 9.
8. Deliver, close, commit, push, handoff memory, `/clear`.

## Phase 1: Policy vertical, view, resolver, consumers switched

Four sub-phases, one session each, same slug prefix. Deletions in Phase 1 are limited to code whose only caller the sub-phase replaced; the mass deletion is Phase 2. Every sub-phase ends with golden + snapshot green and a deploy where a worker is touched.

### 1a: safety net + tables + view  (`/n target-policy-1a-tables`)

1. Golden + snapshot tests written first against current code (TV fixture Transcode and AudioFix argv per the Operating rules fixture shape; TV + Movies compliance counts per dimension committed as `Tests/Contract/Golden/compliance-counts.json`). Both green before anything else.
2. Inventory `CodecFlags` + `CodecParameters` (columns, readers, live rows); result recorded in `2026-11-26-knob-inventory.md` under a dated addendum; fold rule decided (spec 4.5).
3. Migration `AddTargetPolicyTables_2026_11_27.py` (additive only): `TargetOverrides`, `FrameRateClasses`, `EncoderSettings` (seeded from `WorkerEncoderResolver` dicts + `ProfileThresholds` Qsv* + libsvtav1 rows from step 2), `LadderCells` (from `ProfileThresholds` standard + high x1.5), `Profiles` acceptance columns (from `PostTranscodeGateConfig`; held-frame thresholds NULL until Phase 4), `StorageRoots.ReviewBeforeReplace`, `ContainerComplianceRules.OutputContainer`, the VIEW `MediaFileTargets` (DROP VIEW IF EXISTS + CREATE VIEW). Data migration of `SeriesProfiles` and operator/manual `AssignedProfile` into `TargetOverrides` (tier profiles only; assignments in a library with no default tier are not migrated). xxx keeps `DefaultQualityTier NULL` (resolves `Undecided('Tier')`) until `Hold` exists: setting it earlier would queue and replace xxx files unreviewed. The `StorageRoots` NOT NULL tightening is destructive-order and follows Phase 6. Snapshot regenerated.
4. `Features/Policy/`: `Target` dataclass, `TargetResolver` (`Resolve(Id)` + `ResolveMany(Ids)`, one SELECT each on the view), `EncoderSelector`, repositories for the five tables, `MovieGenreSyncService` moved here. Rename `Features/Profiles` -> `Features/Policy` (git mv; update imports in one commit). Nothing consumes `Target` yet. `TestTargetAuthority` added (copy the tree-walk shape of `TestWorkerRuntimeStateAuthorship.py`).
5. `deploy-baremetal-worker.py` runs the two capability-probe scripts after restart (spec 4.5); fleet deploy; `Workers.nvenccapable/qsvcapable` non-NULL on every Enabled worker.
6. Deliver, close, commit, push, handoff memory, `/clear`.

### 1b: compliance consumers  (`/n target-policy-1b-verticals`)

1. `VideoVertical.Evaluate(Facts, Target)`, `AudioVertical.Evaluate(Facts, Target)` (admission-gate side effects moved to `AddJobToQueue`), `ContainerVertical.Evaluate(Facts, Target)`; `Undecided` -> NULL + reason (spec 5). `RecomputeForFiles` calls `ResolveMany` once per batch, passes `Target`; `_EncodeTargets` priority estimate reads `Target` (spec 6 ST4). `WorkBucket` generated column rewritten to the spec 3 expression (audio clause stays until Phase 3). `TestWorkBucketGeneratedColumn` asserts the whole expression.
2. Compliance-count snapshot identical; one TV recompute batch (500 files) timed before/after and recorded.
3. Deliver, close, commit, push, handoff memory, `/clear`.

### 1c: admission, composer, claim, disposition  (`/n target-policy-1c-pipeline`)

1. Admission (`EvaluateQueueAdmission`, `AddJobToQueue`) takes `Target`; `CommandComposer.Build(Facts, Target, EncoderSettings, Label)`; `VideoSlot` reads an `EncoderSettings` row; `DispositionDispatcher` builds the decider input from `Target`. `ClaimNextPendingJob` loses the `Profiles` join and gates (spec 4.5); `WorkerCapabilityPredicate` NVENC/QSV predicates deleted; `TestClaimAuthority` updated; `claim-authority.md` cited in the commit. Old `AssignedProfile` column still exists but nothing reads it for decisions or claims.
2. Golden argv byte-identical; deploy server + fleet; one TV Transcode and one TV AudioFix on a fleet worker byte-identical to the golden argv (command text from `TranscodeAttempts`).
3. Deliver, close, commit, push, handoff memory, `/clear`.

### 1d: GUI  (`/n target-policy-1d-gui`)

1. Ladder grid gains the frame-rate tab; encoder settings grid; tier acceptance table; override controls on `/Work` and `/Optimization` write `TargetOverrides` and show the resolved tier; library table gains review-before-replace. `TestKnobInventory` added (every policy column has a reader and a control).
2. Live on the farm server: each control round-trips (spec 9.6 ladder edit changes a `VideoCompliantReason`).
3. Deliver, close, commit, push, handoff memory, `/clear`.

## Phase 2: Delete the stored target and the classifier

1. `/n target-policy-delete-stored`. Criteria: spec 9.1, 9.9 for `ReassignTierProfiles`, `ContentClassificationRules`, `SeriesProfiles`, `WorkerEncoderResolver`, `ProcessingModeMetadata`.
2. Code first, then the drop (Operating rules order). Code deletions: `Features/ContentClassifier/` (whole vertical), `ProfileAssignmentService`, `SeriesProfileService`, `EffectiveProfileResolver`, `EncoderKnobRepository`, `WorkerEncoderResolver`, `HwAccelResolver` worker reads, `ProcessingModeMetadata`, `CodecFlags`/`CodecParameters` readers, `AddJobToQueue` ProfileId/QualityTier/QualityLabel parameters and the three profile write paths (`AddSuggestionsToQueue:569`, `AddJobToQueue:1818`, `RecomputeForFiles:1711`), `MediaFilesRepository.SaveMediaFile` + `MediaFileModel` profile fields, `FileScanningRepository.SaveMediaFileArchive` profile/KeepSource columns, `Services/FileManagerService` `'Default'` profile metadata, `/settings` classifier-rules card and default-profile editor, the `/Optimization` and `/Work` profile dropdowns, `TestMoviesVideoRule` reassign tests (replaced by Policy tests). Every DISP reader in the knob inventory switched to `MediaFileTargets` or deleted, by table: `DashboardSnapshotService`, `ComplianceSummaryController`, `WorkBucketController /api/Profiles/Active`, `ActivityRepository`, `TranscodeAttemptModel` labels, `FailedJobsRepository` sort keys, `SQLQueriesController`, `FailedJobs.html`, `Operations.html`, `SQLQueries.html`, `WorkBucket.html`. Live scripts migrated or deleted: `RecomputeLibraryCompliance.py`, `RemapXxxToTier1.py`, `FixDefaultProfileIssue.py`, `MergeZDriveDuplicateMediaFiles.py`, `TimeAddSuggestionsToQueue.py`, `SnapshotQueueE2E.py`, `SmokeTestScan.py`, `SmokeTestQueuePopulate.py`, `Smoke/ThreeOfEachBucketSmoke.py`, `*.sql` analyses. Deploy server + fleet.
3. Migration (after the deploy, with pg_dump + operator go) drops `MediaFiles.AssignedProfile/AssignedProfileSource/KeepSource` and the same three from `MediaFilesArchive`, `SeriesProfiles`, `ContentClassificationRules`, `ProfileThresholds` (replaced by `LadderCells`), `CodecFlags`, `CodecParameters`, the dropped `Profiles` columns (spec 4.3), `ProcessingModes.RequiresProfileGates`, `TranscodeFiles.SuccessfullyTranscoded`, `TranscodeQueue.AudioSlotOverride`, the four STREAMING profiles (`VmafConfidenceStats` rows cascade; intended, the table goes in Phase 4), dead `SystemSettings` keys (inventory list), `DefaultProfileName`, `CRFOverride_*`. Snapshot regenerated.
4. `TestTargetAuthority`, `TestKnobInventory`, `TestPipelineShape` added; `TestFailLoud` baseline for the decision layer set to 0.
5. Golden + snapshot pass; deploy; live: change one TV series override on `/Work`, observe recompute with no reassign step (spec 9.6).
6. Deliver, close, commit, push, handoff memory, `/clear`.

## Phase 3: Audio authority  (spec 4.6; absorbs xxx Unit 3)

Order inside the phase is the TV safeguard. Do not reorder.

1. `/n target-policy-audio`. Criteria: TV golden AudioFix argv unchanged; TV and Movies `AudioCompliant` counts unchanged; one xxx copy through AudioFix yields one aac stream at -26 within tolerance, no Demucs step; `grep no_dialog_boost` = 0.
2. Migration (additive part first, drops after the deploy per Operating rules): `AudioPolicyTracks` seeded from live `AudioComplianceRules` values for the global policy; library policy row for xxx (ScopeKey 3) with one `Original` aac 128 -26 default; `folder` scope rows checked (0 today -> scope dropped from the CHECK and the view; else the view gains the canonical-prefix predicate); drop `EmitTracks`, `TargetLra`, `PreVerticalReNormalizePolicy`; drop the eight track columns from `AudioComplianceRules`; `WorkBucket` generated column loses the `HasDialogBoostTrack` clause (spec 4.8). `TranscodeQueue.AudioPolicyJson` changes shape; in-flight rows are drained by the deploy, so no compatibility code. Snapshot.
3. Emitter iterates `AudioPolicyTracks`; `PreEncodeAudioPipeline` runs Demucs only when a `Dialog Boost` track exists; `AudioStrategyClassifier` reads track targets (no `-23/-2/3` defaults); Copy path reads the policy default track for conversion.
4. `AudioVertical`: tracks-match-policy + loudness within tolerance; no side effects; `no_dialog_boost` deleted.
5. GUI: `/AudioNormalization` tracks sub-table; `/Admin/Compliance` loses the eight knobs.
6. Golden + snapshot pass; deploy; live TV AudioFix on a fleet worker byte-identical; live xxx COPY through AudioFix per criteria.
7. Deliver, close, commit, push, handoff memory, `/clear`.

## Phase 4: Verification and Hold  (spec 4.9, 6)

1. `/n target-policy-verification`. Criteria: decision table of spec section 6 implemented as a pure function with a table-driven contract test; `Hold` retains `.ip` and appears on `/QualityTesting` with Replace/Reject; larger output rejected in the decider; `grep SmartConfidence|RetryBudgetService|GetKeepSourceSetting` = 0.
2. Migration (Operating rules order): `PostTranscodeGateConfig` -> `VerificationConfig` (keep `MaxRequeueAttempts`, add `MinOutputSavingsPercent`); drop the listed columns; `ProcessingModes` dead columns dropped; `VmafConfidenceStats` and `SystemSettings.BitratePerPixelBoundaries` dropped. Snapshot.
3. `PostTranscodeDispositionDecider.Decide(AttemptFacts, Target)` pure, table-driven contract test covers every row of spec 6 including Tier 5 -> `QualityCeilingReached`; `DispositionDispatcher` no longer swallows exceptions to `Pending`; `Hold` path in ST9; Requeue upserts the file override `Tier+1` (spec 4.2) then re-adds the job; `FailureBudgetService` is the one budget. `Hold` exempt from cleanup: `RetainInprogressPolicy.RETAIN_REASONS` gains `Hold`, `CrashRecoveryService` and `OrphanCleanupService` skip `Disposition='Hold'` attempts (spec 4.9); contract test per sweeper.
4. `/QualityTesting` Hold list (stills, percentiles, buttons); Override API accepts `Hold` rows; `/settings` verification-config card (`MaxRequeueAttempts`, `MinOutputSavingsPercent`) per `gui-editable-knobs.md`.
5. Deploy; live: one fleet smoke on a COPY lands in `Hold`, resolved to Reject by the operator, `.ip` cleaned; one TV job replaces as before.
6. Deliver, close, commit, push, handoff memory, `/clear`.

## Phase 5: Container and command hygiene  (spec 4.5, 4.7)

1. `/n target-policy-command`. Criteria: `ContainerSlot`/`OutputFilenameBuilder` read `OutputContainer`; `VideoSlot` reads only `EncoderSettings` + `Target`; golden argv unchanged; one `ResolutionCategory` derivation (`ResolutionTierRegistry`); `JobProcessor` output path from `OutputFilenameBuilder`.
2. Delete the four container homes, `ResolutionCalculator` dims table and `TranscodedOutputPlacement` width table (both read the registry), `DetectNormalizationInCommand` (reads `DialogBoostEmitted`), `Remux`/`AudioFix` duplicate strategy classes (one `CopyVideoJobStrategy` parameterised by label). The mid-job `RecomputeForFiles` calls (`AudioPreEncodeFacade:85`, `JobProcessor:83`) stay: `writer-owns-cascade.md` requires them, and after Phase 2 they can no longer rewrite a stored target.
3. Golden + snapshot pass; deploy + fleet; one Remux and one Transcode on fleet workers byte-identical.
4. Deliver, close, commit, push, handoff memory, `/clear`.

## Phase 6: xxx as data  (absorbs xxx Units 2-3 operator steps)

1. `/n xxx-target-data`. Criteria: `SELECT COUNT(*) FROM MediaFileTargets WHERE StorageRootId=3 AND Tier<>3` = 0; 2160p ceiling as the operator set it; one xxx 4K `high` and one `standard` file encode from COPIES on dot and wakko, land in `Hold`, VMAF and stills visible, operator resolves; TV and Movies counts unchanged.
2. Operator on `/settings`, with `Hold` live (Phase 4): set xxx `ReviewBeforeReplace` TRUE first, then tier 3 / live_action (deferred from Phase 1a so no xxx file could be replaced unreviewed), decide 2160p multiplier, decide `high` ladder kbps for 2160p after seeing the two smokes, decide `ReviewBeforeReplace` flip to FALSE. Then the `StorageRoots.DefaultQualityTier` / `DefaultContentClass` NOT NULL tightening (Operating rules order).
3. Smoke per `/mediavortex-smoke-transcode` (copies, fleet only).
4. Deliver, close, commit, push, handoff memory, `/clear`.

## Phase 7: Close-out  (verification only)

1. Re-run spec section 9 criteria 1-9 end to end; `ARCHITECTURE.md` `## Gap to Target` empty; `TestKnobInventory` dead list empty; `TestFailLoud` decision-layer baseline 0.
2. `git status --short` clean; `git log origin/main..HEAD` empty.
3. Program summary paragraph in memory; state plainly: no deferred work, no known gaps. Then `xxx-cull` (spec 2026-10-28 Unit 4) resumes as its own program.
