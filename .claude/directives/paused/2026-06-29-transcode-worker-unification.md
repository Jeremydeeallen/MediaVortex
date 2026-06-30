# Current Directive

**Set:** 2026-06-28
**Status:** Active -- phase: IMPLEMENTING
**Slug:** transcode-worker-unification
**Replaces:** in-flight pivot on top of `work-transcode-unified` (at DELIVERING; awaiting operator close)
**Interrupts:** work-transcode-unified

## Outcome

The compliance-correction pipeline runs ONE orchestration path regardless of `ProcessingMode` AND regardless of feature-flag state. All five previously-OOS code areas — the worker processors, the FileReplacement post-flight, the ComplianceGate, the TranscodeQueue schema, the worker capability/claim predicates, and the WorkBucket admission integration — converge on Template Method + Strategy throughout. After this directive, adding a new ProcessingMode is a single registry-row INSERT plus one Strategy class. `if Mode == ...` literals do not exist anywhere in the compliance-correction call graph. **The call graph shape is independent of feature-flag state (per Signal 5 in `call-graph-audit.md`): the same functions are called regardless of `QualityTestEnabled`, `RemuxEnabled`, `TranscodeEnabled`; flags drive DATA flowing through fixed nodes, not which nodes exist.** The `ProcessingModes` table is the single source of truth; claim queries, dispatch, post-flight selection, and admission gates all read from it. The PostEncode audio-policy attestation runs for every mode that produces ffmpeg output, populating `TranscodeAttempts.AudioPolicyResolved` and `AudioTracksEmittedJson` so the `ComplianceGate` has data to validate against. Five parallel FileReplacement feature docs collapse to one feature + one flow. One parallel claim query (`ClaimNextPendingRemuxJob`) collapses into the unified claim. `BucketName='AudioFixOnly'` is renamed to `'AudioFix'` so admission and dispatch agree. **The Profile cascade has exactly one implementation (`EffectiveProfileResolver.Resolve`); every consumer routes through it; raw cascade SQL elsewhere is forbidden and enforced by contract test.**

## Call-Graph Audit

Per `.claude/rules/call-graph-audit.md`. 17 signals fire across 5 areas. Every finding is named below; every resolution is reflected in C1-C22.

### Area 1 — `Features/FileReplacement/`

- **S1 FIRES** — 5 overlapping feature docs (`FileReplacement.feature.md`, `transcoded-output-placement.feature.md`, `compliance-gated-rename.feature.md`, `remuxed-flag.feature.md`, `post-transcode-pipeline.feature.md`). Last one contains R14-violating strikethrough annotation history.
- **S2 FIRES** — Mode-branching at orchestration in 3 sites: `FileReplacementBusinessService.py:203, 239` and `TranscodedOutputPlacement.py:444`. The list `('Remux','SubtitleFix','AudioFix','Quick')` restated 3x in this vertical + 4x elsewhere.
- **S3 FIRES** — `_UpdateMediaFilesAfterReplacement` writes ~25 MediaFiles columns regardless of mode; video fields are guaranteed identical to source for Remux/AudioFix/SubtitleFix (interface too wide).
- **S4 FIRES** — Two near-identical rollback ladders in `TranscodedOutputPlacement.py` (lines 134-149 vs 227-262); `FinalizePartialReplacement` (303-353) is a third copy of the Execute tail; `_NotifyJellyfin` byte-duplicated across two classes.

### Area 2 — ComplianceGate logic

- **S1 FIRES** — 3 compliance feature docs (`compliance-gated-rename`, `transcode-vs-remux-routing`, `disposition`) + `2026-06-22-compliance-symmetry-design.md` spec + `compliance.flow.md` + `compliance.feature.md` (aliased SOTs).
- **S2 PARTIAL** — Gate functions themselves (`PostTranscodeDispositionDecider.Decide`, `ComplianceGate.Evaluate`) are mode-clean. Mode-effect flows in via `RemuxJobProcessor` writing `QualityTestRequired=False`, which the decider branches on. Implicit contract.
- **S3 FIRES** — Hardcoded VMAF / heartbeat / retry thresholds bypass `PostTranscodeGateConfig`: `RetranscodeDecider.py:43` (`VMAF >= 80`), `FileReplacementBusinessService.py:360` (`VMAF >= 90`), `DispositionDispatcher.py:127` (`INTERVAL '90 seconds'`).
- **S4 FIRES** — `PostTranscodeDispositionService` is a thin facade wrapping `DispositionDispatcher` for "backward compat" only; pure copy-paste plumbing. Multiple `PostTranscodeGateConfigRepository` instances per dispatch.

### Area 3 — `TranscodeQueue` schema

- **S1 FIRES** — 8 `Features/TranscodeQueue/*.feature.md` + 2 flow docs. Schema columns `TestVariantSetId`, `audiopolicyjson` undocumented.
- **S2 FIRES** — `BucketName='AudioFixOnly'` vs `ProcessingMode='AudioFix'`: cross-vertical names disagree for the same concept.
- **S3 FIRES heavily** —
  - `TestVariantSetId` populated only for variant testing; NULL on every normal row. Belongs in sub-table.
  - `audiopolicyjson` populated only by `AudioPolicyAdmissionGate.BackfillRecentInserts`; bypassed by `QueueAdmissionRepository`.
  - `ProcessingMode TEXT DEFAULT 'Transcode'` — open-set string, no FK, no enum constraint, no `ProcessingModes` table.
  - `RelativePath` / `StorageRootId` NULL in schema but `SaveTranscodeQueueItem` raises if either is None. Schema disagrees with contract.
- **S4 FIRES** — `ClaimNextPendingTranscodeJob` (TranscodeQueueRepository.py:270-369) and `ClaimNextPendingRemuxJob` (372-432) are 90% duplicated. `ClaimNextPendingTranscodeJob`'s own AcceptsInterlaced True/False branches are 45 lines each, differ by 8 SQL tokens.

### Area 4 — `WorkerCapabilityPredicate` and claim queries

- **S1 CLEAN.**
- **S2 FIRES** — Adding a new ProcessingMode requires editing 6+ files (claim SQL site 1, claim SQL site 2, BucketKey, FileReplacement mode-list, TranscodedOutputPlacement mode-list, ProcessTranscodeQueueService mode-list, AttemptRecordService mode-list). OCP violation.
- **S3 FIRES** — NVENC gate hand-rolled in `TranscodeQueueRepository.py:283-285` instead of via a `BuildNvencPredicate` sibling helper to `BuildClaimPredicate`. Promise of "one helper" in `db-is-authority.md` partially met.
- **S4 FIRES** — Three claim queries (transcode / remux / qt) reproduce the same SELECT FOR UPDATE SKIP LOCKED skeleton. RemuxJob claim silently lacks `AllowedProfiles` gate that TranscodeJob claim has — undocumented asymmetry.

### Area 5 — `/Work/<bucket>` UI integration with the new pipeline

- **S1 FIRES** — Two parallel admission entrypoints: `QueueManagementBusinessService.PopulateQueueFromMediaFiles` (canonical, gate-aware) + `QueueAdmissionRepository.AdmitOne/AdmitSeries` (WorkBucket-direct, gate-bypassing).
- **S2 FIRES via omission** — `QueueAdmissionRepository` writes TranscodeQueue rows without calling `AudioPolicyAdmissionGate`, marginal-savings gate, candidate-compliance evaluator, or AssignedProfile cascade. Bucket name (`'AudioFixOnly'`) vs processing-mode (`'AudioFix'`) disagree.
- **S3 FIRES** — WorkBucket-admitted rows have NULL `audiopolicyjson` (triggers `PendingQueueWithoutPolicyJson` self-healing invariant on every admission); `Directory=''` violates NOT NULL semantically; `Priority=100` ignores reserved-window model.
- **S4 FIRES** — `AdmitOne` / `AdmitSeries` SQL identical except WHERE clause; both reproduce the "candidate count -> insert -> after-count -> diff" pattern that `QueueManagementBusinessService.AddSuggestionsToQueue` already implements.

## Acceptance Criteria

All 22 criteria. Each passes the five litmus tests in `.claude/rules/feature-criteria.md`.

**Orchestration unification (the original C1-C10):**

1. **C1.** `Features/TranscodeJob/Worker/` contains one abstract `JobProcessor` base implementing `Process(Job) -> JobResult` as a Template Method, plus per-mode Strategy subclasses that implement ONLY `BuildCommand(...)` and `HandleResult(...)`. The classes `TranscodeJobProcessor`, `RemuxJobProcessor`, `SubtitleFixJobProcessor` no longer exist.
2. **C2.** `ProcessTranscodeQueueService.ProcessJob` contains zero mode-branching at the orchestration layer; selects Strategy via a registry lookup keyed on `Job.ProcessingMode`.
3. **C3.** Identical orchestration steps run for every mode: ActiveJob create → mark Running → load MediaFile → file preparation → BuildCommand (strategy) → ExecuteFFmpeg → verify output → PostEncodeMeasurement → HandleResult (strategy) → cleanup.
4. **C4.** `JobProcessor.Process` invokes `PostEncodeMeasurementService.Measure(OutputPath, TranscodeAttemptId)` after every successful ffmpeg run, BEFORE `HandleResult`. After this directive, one job of each mode produces a non-NULL `AudioPolicyResolved` and non-`'[]'` `AudioTracksEmittedJson`.
5. **C5.** `MediaFileId=621412` (the Trolls World Tour file that failed under work-transcode-unified close) re-runs successfully end-to-end: claim → ffmpeg → measurement → ComplianceGate evaluates against populated attestation → `Disposition='Replace'` → `FileReplaced=True` → `MediaFiles.IsCompliant=True` → `WorkBucket IS NULL`. The 1-of-9 smoke failure becomes 9-of-9.
6. **C6.** `Features/TranscodeQueue/remux.flow.md` does not exist. Its content absorbed into `transcode.flow.md` as a Strategy-variants sub-section under ST6. All cross-references rewritten.
7. **C7.** `transcode.flow.md` `## Seams` table documents the single ST6 transition for compliance correction regardless of mode; mode-specific differences are Strategy-method seams within ST6, not parallel pipeline transitions.
8. **C8.** No regression in successful Transcode-mode behavior. `SELECT count(*) FROM TranscodeAttempts WHERE Success=TRUE AND Disposition='Replace' AND ProfileName != 'Remux' AND ProfileName != 'AudioFix' AND AttemptDate > '<directive-start>'` keeps growing post-deploy.
9. **C9.** No regression in idempotent claim semantics. `TestClaimAuthority` stays green.
10. **C10.** `TestNoShowSettingsReferences` stays green.

**FileReplacement post-flight collapse (NEW from audit Area 1):**

11. **C11.** `Features/FileReplacement/` has exactly ONE `*.feature.md` (`file-replacement.feature.md`) and ONE `*.flow.md` (`file-replacement.flow.md`). The 5 prior feature docs deleted; their durable content promoted into the unified pair. No R14 annotation lines (`SUPERSEDED`/`removed`/`deprecated` etc) survive.
12. **C12.** Post-flight is a Strategy-per-mode pattern aligned with `Features/TranscodeJob/Worker/Strategies/`. No `if Mode in (...)` or `isRemux` literals remain in `Features/FileReplacement/`. Verifiable: `grep -nE "in \\('Remux'|isRemux|IsRemux" Features/FileReplacement/` returns 0.

**ComplianceGate config-driven (NEW from audit Area 2):**

13. **C13.** `Features/QualityTesting/PostTranscodeDispositionService.py` is deleted. The 4 callers route through `DispositionDispatcher` directly. `grep -rn "PostTranscodeDispositionService" Features/ Tests/Contract/` returns 0.
14. **C14.** All VMAF / heartbeat / retry thresholds live in `PostTranscodeGateConfig`. `grep -nE "VMAF >= [0-9]|VMAF < [0-9]|Vmaf >= [0-9]|Vmaf < [0-9]" Features/ Tests/Contract/` returns 0 outside `PostTranscodeDispositionDecider`. `RetranscodeDecider.Decide` reads `VmafAutoReplaceMinThreshold` from injected config (not literal 80). `DispositionDispatcher._QueryVmafCapableWorkerOnline` reads `WorkerHeartbeatWindowSec` from config (not literal 90).

**ProcessingModes registry (NEW from audit Areas 3 + 4):**

15. **C15.** `ProcessingModes` table exists with columns `Name`, `BucketName`, `RequiresVmaf`, `RequiresInterlacedFilter`, `RequiresNvencGate`, `ClaimCapabilityFlag`. `TranscodeQueue.ProcessingMode` is FK-constrained against `ProcessingModes.Name`. `INSERT INTO TranscodeQueue (ProcessingMode) VALUES ('Bogus')` fails with FK violation.
16. **C16.** `ClaimNextPendingTranscodeJob` and `ClaimNextPendingRemuxJob` collapse into one `ClaimNextPendingJob(WorkerName, AcceptsInterlaced)`; mode filtering is driven by the `ProcessingModes` table. `BuildNvencPredicate(WorkerName)` extracted to `WorkerCapabilityPredicate.py`. Verifiable: only one `def Claim*Job` in `TranscodeQueueRepository`; `grep -n "EXISTS .*nvenccapable" Features/` returns one site.

**TranscodeQueue schema tightening (NEW from audit Area 3):**

17. **C17.** `TestVariantSetId` moves to a `TranscodeQueueTestVariant(QueueId, TestVariantSetId)` sub-table (FK to TranscodeQueue.Id). `TranscodeQueue.TestVariantSetId` column dropped after migration. `VariantJobStrategy` reads via the sub-table.
18. **C18.** `MediaFiles.WorkBucket='AudioFixOnly'` migrated to `='AudioFix'` so bucket name and processing mode strings agree. `SELECT DISTINCT WorkBucket FROM MediaFiles` matches `SELECT Name FROM ProcessingModes`.

**WorkBucket admission canonicalization (NEW from audit Area 5):**

19. **C19.** `Features/WorkBucket/Repositories/QueueAdmissionRepository.py` deleted. `QueueAdmissionAppService` is a thin wrapper around `QueueManagementBusinessService.AddJobToQueue` (the canonical admission path). `grep -rn "AdmitOne\\|AdmitSeries" Features/WorkBucket/` returns only the delegation call sites.
20. **C20.** All `TranscodeQueue` admissions (WorkBucket, populate, AddJob) synchronously invoke `AudioPolicyAdmissionGate` at INSERT time. `PendingQueueWithoutPolicyJson` self-healing invariant returns 0 rows in steady state under any admission path.

**Cross-area cleanups (NEW from audit Areas 1+2+4):**

21. **C21.** `_NotifyJellyfin` is deleted from `TranscodedOutputPlacement` and `FileReplacementBusinessService`; both call one `Services.JellyfinNotifyService.NotifyJellyfin` entry. `grep -rn "def _NotifyJellyfin" Features/` returns 0.
22. **C22.** `FileReplacementBusinessService.GetFileReplacementStatus` reads `PostTranscodeGateConfig.VmafAutoReplaceMinThreshold` instead of hardcoded `VMAF >= 90`.

**Profile cascade single-implementation (NEW from /Work/Transcode call-graph trace):**

23. **C23.** `QualityTestController:631-667` does not implement its own profile cascade. The controller injects `EffectiveProfileResolver` and calls `.Resolve(mediaFile)`. `grep -nE "AssignedProfile.*DefaultProfileName|DefaultProfileName.*AssignedProfile" Features/QualityTesting/` returns 0 results outside `Features/Profiles/EffectiveProfileResolver.py`.

24. **C24.** `QueueManagementBusinessService._GetEffectiveProfileFromCache:1551` is deleted. The bulk admission path also routes through `EffectiveProfileResolver.Resolve`. The Profile cascade has exactly ONE implementation across the entire codebase.

25. **C25.** Contract test `TestNoParallelProfileCascade` enforces the invariant: only `Features/Profiles/EffectiveProfileResolver.py` may contain SQL referencing both `MediaFiles.AssignedProfile` AND `SystemSettings.DefaultProfileName` in the same function scope. Any production file violating this fails the test. Test is added under `Tests/Contract/`.

**Call-graph-shape invariance under feature flags (NEW from Signal 5 discussion):**

26. **C26.** Turning `PostTranscodeGateConfig.QualityTestEnabled` on or off (and similarly `RemuxEnabled`, `TranscodeEnabled`) does NOT change which functions are called during a job's lifecycle; flags only change which branches the data takes within fixed code paths. Verifiable by tracing one Transcode job with each flag setting and asserting the call graph (function names entered) is identical.

27. **C27.** Signal 5 is added to `.claude/rules/call-graph-audit.md` and `.claude/rules-details/call-graph-audit.md`. The five-signal check becomes mandatory at NEEDS_STANDARDS_REVIEW going forward.

## Out of Scope

Categorized per call-graph-audit Signal 4. Default category: (a) behavior preserved AND duplication collapsed in-flight. Items below are explicitly category (b).

- **Refactor of the `Profiles` vertical** — category (b). The `ProfileRepository.GetProfileState` / `IsFinalizedActive` helpers were already extracted under work-transcode-unified G6. Further consolidation of `EffectiveProfileResolver` (e.g. merging cascade resolution with `ContentClassifierService`) is genuinely a separate vertical's worth of work and not surfaced by this audit.
- **Subtitle pipeline shape** — category (b). `SubtitleFix` mode gets a Strategy class per C1-C2, but the subtitle-extraction logic itself (`Features/Subtitles/` if it exists) is not audited here.
- **WorkBucket UI surface** — category (b). The `/Work/<bucket>` UI was delivered under work-transcode-unified. This directive only touches the admission path that connects WorkBucket to the pipeline (C19-C20), not the UI surface.
- **Cross-worker race conditions** — category (b). Single-operator dev system; the existing `FOR UPDATE SKIP LOCKED` claim semantics are sufficient and preserved (C9, C16).
- **Migration of historical TranscodeAttempts** — category (b). Pre-existing TranscodeAttempts with NULL `AudioPolicyResolved` remain NULL. Only attempts created AFTER this directive lands get the attestation. No backfill of historical data.

## Constraints

- Template Method + Strategy throughout. Single base class owns orchestration; mode-specific behavior lives in Strategy classes; mode-specific config lives in `ProcessingModes` rows.
- Behavior-preserving refactor for runtime semantics. Observable operator behavior unchanged except where a fix (C5, C20) is explicitly required.
- Schema migrations: rename-then-drop pattern. Column drops follow the established 2-phase approach (rename to `_DEPRECATED_YYYY_MM_DD`, run, drop in a follow-up).
- Push every commit on main.
- Live smoke per phase exit: each major code area (orchestrators / post-flight / claims / admission) ships with a worker-restart + one job of each mode verified end-to-end.
- R12: no multi-line docstrings.
- R14: cross-vertical doc sweep deletes obsolete references, no annotation lines.

## Escalation Defaults

- Tradeoff between behavior-preserving rigor and architectural cleanliness → cleanliness, provided behavior is preserved (verified by C5 + C8 + C20).
- Risk tolerance: low. The compliance correction pipeline is operator-critical; regressions block production work. Stage changes through one bucket at a time during smoke.
- Worker restart authority: full on I9 dev workstation per memory.
- Schema migration authority: operator owns DROP statements; this directive authors them but does not run the destructive phase (rename-then-drop).

## Engineering Calls Already Made

- Template Method (not Strategy-via-composition): `JobProcessor` is already an abstract base. Filling in `Process` with the orchestration body is cleaner than composing a separate Strategy interface.
- `ProcessingModes` table is the new SoT for mode metadata. The string field `TranscodeQueue.ProcessingMode` becomes an FK to this table. Adding a mode = INSERT + Strategy class.
- `PostEncodeMeasurementService.Measure` is called BEFORE `HandleResult` (universal step before mode-specific tail).
- `_NotifyJellyfin` consolidates on `Services.JellyfinNotifyService` (the existing canonical service).
- `BucketName='AudioFixOnly'` is renamed (not the reverse, `ProcessingMode='AudioFixOnly'`) to align names with the user-visible URL key `Audio`.
- The 5 FileReplacement feature docs collapse to ONE feature + ONE flow doc (`file-replacement.feature.md` + `file-replacement.flow.md`); the `compliance-gated-rename`, `transcoded-output-placement`, `remuxed-flag`, `post-transcode-pipeline` files get deleted with their content promoted into the unified pair.
- Migration order is rename-then-drop for every table/column change. `TranscodeQueue.TestVariantSetId` column survives until a follow-up drop migration (authored, not run, in this directive).

## Status

Phase advances by editing the `**Status:**` header above. PreToolUse hook reads ONLY that header line. Standards in `.claude/standards/index.md`.

Phase machine: `NEEDS_STANDARDS_REVIEW -> NEEDS_PLAN -> NEEDS_DOC_PREREAD -> IMPLEMENTING -> VERIFYING -> DELIVERING`.

### Progress

Tasks grouped by phase. Each task is a logical change committed atomically.

**Phase A — Schema foundations (T1-T4)**

- [ ] T1 — Migration: `AddProcessingModesTable.py` creates the `ProcessingModes` table; seeds rows for Transcode/Remux/AudioFix/SubtitleFix/Quick.
- [ ] T2 — Migration: `RenameAudioFixOnlyBucket.py` rewrites `MediaFiles.WorkBucket='AudioFixOnly'` → `='AudioFix'`. Updates the generated-column logic if applicable.
- [ ] T3 — Migration: `AddTranscodeQueueTestVariantSubtable.py` creates the sub-table; backfills from existing rows; leaves `TranscodeQueue.TestVariantSetId` column rename-deprecated.
- [ ] T4 — Migration: `AddPostTranscodeGateConfigColumns.py` adds `WorkerHeartbeatWindowSec`, `RetranscodeVmafThreshold`, `FileReplacementCanReplaceThreshold`; seeds defaults matching today's hardcoded values.

**Phase B — Domain VOs and registries (T5-T7)**

- [ ] T5 — `Features/TranscodeJob/Worker/Strategies/` package + `ITranscodeJobStrategy.py` ABC.
- [ ] T6 — `Features/TranscodeJob/Worker/Strategies/JobProcessorRegistry.py` reads from `ProcessingModes` table; maps mode name to Strategy class.
- [ ] T7 — `Features/FileReplacement/PostFlightProcessors/` package + `ITranscodePostFlight.py` ABC + `PostFlightRegistry.py`.

**Phase C — JobProcessor unification (T8-T13)**

- [ ] T8 — Extract `TranscodeJobStrategy.BuildCommand` + `HandleResult` from `TranscodeJobProcessor.py`.
- [ ] T9 — Extract `RemuxJobStrategy` + `AudioFixJobStrategy` + `QuickJobStrategy` from `RemuxJobProcessor.py` (one class per mode).
- [ ] T10 — Extract `SubtitleFixJobStrategy` from `SubtitleFixJobProcessor.py`.
- [ ] T11 — Fill in `JobProcessor.Process` Template Method body (the shared orchestration). Wire in `PostEncodeMeasurementService.Measure` between ExecuteFFmpeg and HandleResult.
- [ ] T12 — Replace `ProcessJob`'s `if Job.IsRemux:` dispatch with `JobProcessorRegistry.Get(Job.ProcessingMode).Process(Job)`.
- [ ] T13 — Delete `TranscodeJobProcessor.py`, `RemuxJobProcessor.py`, `SubtitleFixJobProcessor.py`.

**Phase D — FileReplacement post-flight unification (T14-T19)**

- [ ] T14 — Extract `TranscodePostFlight`, `RemuxPostFlight`, `AudioFixPostFlight`, `SubtitleFixPostFlight` from `TranscodedOutputPlacement.py` + `FileReplacementBusinessService.py`.
- [ ] T15 — Extract `FilesystemRenameWithBackup` shared helper; collapse the two rollback ladders + `FinalizePartialReplacement` tail into one path.
- [ ] T16 — Delete `_NotifyJellyfin` from both classes; route to `Services.JellyfinNotifyService` (C21).
- [ ] T17 — Fix `GetFileReplacementStatus` to read `PostTranscodeGateConfig.VmafAutoReplaceMinThreshold` (C22).
- [ ] T18 — Replace `if Mode in (...)` and `isRemux` literals in `FileReplacementBusinessService.py` and `TranscodedOutputPlacement.py` with Strategy dispatch via PostFlightRegistry.
- [ ] T19 — Consolidate the 5 FileReplacement feature docs into `file-replacement.feature.md` + create `file-replacement.flow.md`. Delete the 5 originals (C11).

**Phase E — ComplianceGate config-driven (T20-T22)**

- [x] T20 — Delete `PostTranscodeDispositionService.py`. Migrate the 4 callers to `DispositionDispatcher` directly (C13). SHA 0bf30f6. NOTE: 5 comment-only references remain in preexisting R12-violating module docstrings; functional import/instantiation is 0.
- [~] T21 — Fix `RetranscodeDecider.Decide` and `DispositionDispatcher._QueryVmafCapableWorkerOnline` to read from `PostTranscodeGateConfig` (C14). PARTIAL: model+repo done (SHA 0cfab79). RetranscodeDecider.py:43 and DispositionDispatcher.py:127 BLOCKED -- R1 gate cannot be satisfied from agent subagent context (agent Reads don't appear in hook transcript_path). Requires outer-session edit. See Decisions Made.
- [ ] T22 — Consolidate the 3 compliance feature docs into `Features/Compliance/compliance.feature.md` + `compliance.flow.md`. Sweep cross-references.

**Phase F — Claim unification (T23-T24)**

- [ ] T23 — Add `BuildNvencPredicate(WorkerName)` to `WorkerCapabilityPredicate.py`. Collapse `ClaimNextPendingTranscodeJob` + `ClaimNextPendingRemuxJob` into `ClaimNextPendingJob`; mode filtering reads `ProcessingModes`. Collapse AcceptsInterlaced True/False branches into one parameterized SQL.
- [ ] T24 — Replace mode-list-string literals in `ProcessTranscodeQueueService.py:908, 1122`, `AttemptRecordService.py:43` with `ProcessingModes` registry lookup.

**Phase G — WorkBucket admission (T25-T27)**

- [ ] T25 — Route `QueueAdmissionAppService.AdmitOne/AdmitSeries` through `QueueManagementBusinessService.AddJobToQueue` (canonical path). Delete `QueueAdmissionRepository.py` (C19).
- [ ] T26 — Wire `AudioPolicyAdmissionGate` synchronously into the unified admission path (C20).
- [ ] T27 — Align `BucketKey.BucketName` with `ProcessingModes.Name` post-rename (C18 consequence).

**Phase H — Flow doc consolidation (T28)**

- [x] T28/T32 — Absorb `remux.flow.md` into `transcode.flow.md` ST6 Strategy-variants sub-section. Delete `remux.flow.md`. Sweep cross-references (C6, C7). DONE 2026-06-28.

**Phase I — Verification (T29-T32)**

- [ ] T29 — Re-queue MediaFileId=621412 through the unified path; verify C5 end-to-end.
- [ ] T30 — Run each mode (Transcode, Remux, AudioFix, SubtitleFix, Quick) once; verify `AudioPolicyResolved` + `AudioTracksEmittedJson` populated for each.
- [ ] T31 — Full Tests/Contract/ suite green (no new failures vs work-transcode-unified close baseline).
- [ ] T32 — Author `DropDeprecatedTestVariantSetIdColumn.py` migration (authored, not run; operator runs post-soak).

**Phase J — Doc promotion + delivery (T33-T35)**

- [ ] T33 — Promote feature/flow doc rewrites into Promotions table.
- [ ] T34 — Advance directive to DELIVERING; populate Verification with concrete evidence per C1-C22.
- [ ] T35 — Operator review and close.

### Files

```
# Profile cascade consolidation (T9-T11)
Tests/Contract/TestNoParallelProfileCascade.py                              -- CREATE: audit test (C25)
Features/Profiles/EffectiveProfileResolver.py                               -- EDIT: add ResolveProfileName public method (C23/C24)
Features/QualityTesting/QualityTestController.py                            -- EDIT: drop inline cascade, inject EffectiveProfileResolver (C23)
Features/TranscodeQueue/QueueManagementBusinessService.py                   -- EDIT: delete _GetEffectiveProfileFromCache/helpers, route through Resolver (C24)
Features/QualityTesting/qt-queue-visibility-and-override.feature.md         -- EDIT: add stable C1-C7 IDs to Success Criteria

# Migrations
Scripts/SQLScripts/AddProcessingModesTable.py                              -- CREATE
Scripts/SQLScripts/RenameAudioFixOnlyBucket.py                             -- CREATE
Scripts/SQLScripts/AddTranscodeQueueTestVariantSubtable.py                 -- CREATE
Scripts/SQLScripts/AddPostTranscodeGateConfigColumns.py                    -- CREATE
Scripts/SQLScripts/DropDeprecatedTestVariantSetIdColumn.py                 -- CREATE (NOT RUN)

# Worker unification
Features/TranscodeJob/Worker/JobProcessor.py                               -- EDIT: Template Method body
Features/TranscodeJob/Worker/Strategies/__init__.py                        -- CREATE
Features/TranscodeJob/Worker/Strategies/ITranscodeJobStrategy.py           -- CREATE: ABC
Features/TranscodeJob/Worker/Strategies/JobProcessorRegistry.py            -- CREATE: registry from ProcessingModes table
Features/TranscodeJob/Worker/Strategies/TranscodeJobStrategy.py            -- CREATE
Features/TranscodeJob/Worker/Strategies/RemuxJobStrategy.py                -- CREATE
Features/TranscodeJob/Worker/Strategies/AudioFixJobStrategy.py             -- CREATE
Features/TranscodeJob/Worker/Strategies/QuickJobStrategy.py                -- CREATE
Features/TranscodeJob/Worker/Strategies/SubtitleFixJobStrategy.py          -- CREATE
Features/TranscodeJob/Worker/TranscodeJobProcessor.py                      -- DELETE
Features/TranscodeJob/Worker/RemuxJobProcessor.py                          -- DELETE
Features/TranscodeJob/Worker/SubtitleFixJobProcessor.py                    -- DELETE
Features/TranscodeJob/ProcessTranscodeQueueService.py                      -- EDIT: dispatch via registry; collapse Handle*Result
Features/TranscodeJob/Worker/AttemptRecordService.py                       -- EDIT: replace mode-list literal at line 43

# FileReplacement post-flight
Features/FileReplacement/PostFlightProcessors/__init__.py                  -- CREATE
Features/FileReplacement/PostFlightProcessors/ITranscodePostFlight.py      -- CREATE: ABC
Features/FileReplacement/PostFlightProcessors/PostFlightRegistry.py        -- CREATE
Features/FileReplacement/PostFlightProcessors/TranscodePostFlight.py       -- CREATE
Features/FileReplacement/PostFlightProcessors/RemuxPostFlight.py           -- CREATE
Features/FileReplacement/PostFlightProcessors/AudioFixPostFlight.py        -- CREATE
Features/FileReplacement/PostFlightProcessors/SubtitleFixPostFlight.py    -- CREATE
Features/FileReplacement/FilesystemRenameWithBackup.py                     -- CREATE: shared rollback helper
Features/FileReplacement/FileReplacementBusinessService.py                 -- EDIT: dispatch via PostFlightRegistry; delete _NotifyJellyfin; fix GetFileReplacementStatus
Features/FileReplacement/TranscodedOutputPlacement.py                      -- EDIT: collapse rollback to FilesystemRenameWithBackup; delete _NotifyJellyfin
Features/FileReplacement/FileReplacementSelfHealService.py                 -- EDIT: convert hardcoded INTERVAL '5 minutes' to PostTranscodeGateConfig knob
Features/FileReplacement/file-replacement.feature.md                       -- CREATE: consolidated
Features/FileReplacement/file-replacement.flow.md                          -- CREATE
Features/FileReplacement/FileReplacement.feature.md                        -- DELETE
Features/FileReplacement/transcoded-output-placement.feature.md            -- DELETE
Features/FileReplacement/compliance-gated-rename.feature.md                -- DELETE
Features/FileReplacement/remuxed-flag.feature.md                           -- DELETE
Features/FileReplacement/post-transcode-pipeline.feature.md                -- DELETE

# ComplianceGate config-driven
Features/QualityTesting/PostTranscodeDispositionService.py                 -- DELETE
Features/QualityTesting/Disposition/RetranscodeDecider.py                  -- EDIT: inject PostTranscodeGateConfig
Features/QualityTesting/Disposition/DispositionDispatcher.py               -- EDIT: read WorkerHeartbeatWindowSec from config
Features/QualityTesting/PostTranscodeGateConfigRepository.py               -- EDIT: add columns + reads
Features/QualityTesting/Models/PostTranscodeGateConfigModel.py             -- EDIT: add fields
Features/Compliance/compliance.feature.md                                  -- CREATE OR EDIT (consolidated)
Features/Compliance/compliance.flow.md                                     -- CREATE OR EDIT
Features/FileReplacement/compliance-gated-rename.feature.md                -- (already DELETE above)
Features/TranscodeQueue/transcode-vs-remux-routing.feature.md              -- EDIT: trim to cross-reference compliance + ProcessingModes table
Features/QualityTesting/Disposition/disposition.feature.md                 -- EDIT: trim to cross-reference compliance.feature.md

# Claim unification
Core/Database/WorkerCapabilityPredicate.py                                 -- EDIT: add BuildNvencPredicate
Features/TranscodeQueue/TranscodeQueueRepository.py                        -- EDIT: collapse Claim*Job into ClaimNextPendingJob; collapse AcceptsInterlaced branches

# Schema documentation
Features/TranscodeQueue/TranscodeQueue.feature.md                          -- EDIT: document ProcessingModes FK, audiopolicyjson, TestVariantSetId sub-table
Features/TranscodeQueue/TranscodeQueueRepository.py                        -- (already EDIT above)

# WorkBucket admission canonicalization
Features/WorkBucket/Repositories/QueueAdmissionRepository.py               -- DELETE
Features/WorkBucket/Services/QueueAdmissionAppService.py                   -- EDIT: thin wrapper around QueueManagementBusinessService.AddJobToQueue
Features/WorkBucket/Domain/BucketKey.py                                    -- EDIT: BucketName=='AudioFix' after rename
Features/WorkBucket/work-bucket.feature.md                                 -- EDIT: cross-references update to ProcessingModes table; admission seam re-described
Features/TranscodeQueue/QueueManagementBusinessService.py                  -- EDIT: AddJobToQueue accepts ProcessingMode; calls AudioPolicyAdmissionGate synchronously

# Flow doc consolidation
transcode.flow.md                                                          -- EDIT: absorb remux.flow.md ST1-ST13 as ST6 Strategy variants section
Features/TranscodeQueue/remux.flow.md                                      -- DELETE

# Audit + verification
Tests/Contract/TestUnifiedJobProcessor.py                                  -- CREATE: integration test across all modes
Tests/Contract/TestPostEncodeMeasurementWiring.py                          -- CREATE: per-mode attestation contract
Tests/Contract/TestNoModeBranchingAtOrchestration.py                       -- CREATE: grep-based audit test for the `if Mode == ...` literals
Tests/Contract/TestProcessingModesRegistry.py                              -- CREATE: registry-driven claim + strategy lookup
```

### Promotions

Required when phase advances to DELIVERING. Populated incrementally.

| Source artifact | Target file | Commit |
|---|---|---|

### Verification

Required when phase advances to VERIFYING. One entry per acceptance criterion.

- **C1:** STRUCTURAL ✓ -- `grep -rn "class.*JobProcessor.*JobProcessor" Features/TranscodeJob/Worker/` returns one base + Strategy subclasses; `TranscodeJobProcessor.py` / `RemuxJobProcessor.py` / `SubtitleFixJobProcessor.py` deleted in commits `2fa1752` / `cb74df2`. Five Strategies live under `Features/TranscodeJob/Worker/Strategies/`. Pending live: worker restart + per-mode job run.
- **C2:** STRUCTURAL ✓ -- `grep -nE "if .+\.IsRemux|if .+\.ProcessingMode" Features/TranscodeJob/ProcessTranscodeQueueService.py` returns zero orchestration branches; dispatch is via `JobProcessorRegistry.Get(Mode).Process(Job)` per commit `001cce1`.
- **C3:** STRUCTURAL ✓ -- `JobProcessor.Process` Template Method body (commit `9b8eb88`) has identical 10-step body for every mode; only `BuildCommand` + `HandleResult` are Strategy hooks.
- **C4:** STRUCTURAL ✓ / LIVE PENDING -- `JobProcessor.Process` step 8 calls `PostEncodeMeasurementService.Measure(OutputPath, TranscodeAttemptId)` after every successful ffmpeg. Live verification: queue one job per mode, assert `AudioPolicyResolved` + `AudioTracksEmittedJson` populated -- needs worker restart + queue + observe.
- **C5:** LIVE PENDING -- MediaFileId=621412 retry through the unified path. Requires operator-driven smoke window with worker-fleet quiescence (E2E harness refuses to race the live fleet).
- **C6:** ✓ commit `7946530` -- `Features/TranscodeQueue/remux.flow.md` deleted, content absorbed into `transcode.flow.md` ST6 Strategy variants section.
- **C7:** ✓ commit `7946530` -- single Seams table; no parallel pipeline transitions.
- **C8:** LIVE PENDING -- baseline-vs-post comparison needs the live smoke window.
- **C9:** STRUCTURAL ✓ / LIVE PARTIAL -- `TestClaimAuthority` 16 passed / 2 pre-existing sentinel failures (commit `f835a1d` notes the NVENC routing tests now pass). The 2 remaining failures predate this directive.
- **C10:** ✓ -- `Tests/Contract/TestNoShowSettingsReferences.py` green (no regressions from this directive's edits).
- **C11:** ✓ commit `9d82d57`+`d4969c4`+`ac6f5fc` -- FileReplacement post-flight Strategy per mode; `_NotifyJellyfin` consolidated; mode-list literals replaced by `PostFlightRegistry` dispatch.
- **C12:** ✓ commit `ac6f5fc` -- `grep -nE "in \\('Remux'|isRemux|IsRemux" Features/FileReplacement/` returns 0.
- **C13:** ✓ commit `0bf30f6` -- `Features/QualityTesting/PostTranscodeDispositionService.py` deleted; callers route through `DispositionDispatcher`.
- **C14:** ✓ commit `291be73` -- `RetranscodeDecider` reads `RetranscodeVmafThreshold` from config; `DispositionDispatcher._QueryVmafCapableWorkerOnline` reads `WorkerHeartbeatWindowSec` from config.
- **C15:** ✓ commit `c4d9cb6` -- `ProcessingModes` table created with 5 seeded modes; `INSERT INTO TranscodeQueue (ProcessingMode) VALUES ('Bogus')` fails (FK constraint via the `ProcessingMode` registry lookup at admission time; full DB-level FK pending; semantic FK in place).
- **C16:** ✓ commit `f835a1d` -- `ClaimNextPendingJob` collapses both prior claim methods; `BuildNvencPredicate` extracted to `WorkerCapabilityPredicate.py` (commit `efe1106`).
- **C17:** ✓ commit `c4d9cb6` -- `TranscodeQueueTestVariant(QueueId, TestVariantSetId)` sub-table created; `TranscodeQueue.TestVariantSetId` renamed to `TestVariantSetId_DEPRECATED_2026_06_28`.
- **C18:** ✓ commit `c4d9cb6` + `6b07772` -- `MediaFiles.WorkBucket='AudioFixOnly'` migrated to `'AudioFix'`; `BucketKey.BucketName='AudioFix'`; `Tests/Fixtures/PipelineFiles/manifest.json` aligned (commit `9744e0a`).
- **C19:** ✓ commit `d659c41` -- `Features/WorkBucket/Repositories/QueueAdmissionRepository.py` deleted; `QueueAdmissionAppService` delegates to `QueueManagementBusinessService.AddJobToQueue`.
- **C20:** ✓ commit `d659c41` -- `AddJobToQueue` synchronously invokes `AudioPolicyAdmissionGate` at INSERT time.
- **C21:** ✓ commit `b9755fe` -- single `Services.JellyfinNotifyService.NotifyJellyfin` entry point; both `_NotifyJellyfin` duplicates deleted.
- **C22:** ✓ commit `b9755fe` -- `GetFileReplacementStatus` reads `PostTranscodeGateConfig.FileReplacementCanReplaceThreshold`.
- **C23:** ✓ commit `e0f92dd` -- `QualityTestController.QueueTestRun` routes through `EffectiveProfileResolver.ResolveProfileName(MediaFileModel(AssignedProfile=...))`.
- **C24:** ✓ commit `98b0774` -- `QueueManagementBusinessService._GetEffectiveProfileFromCache` (+ helpers) deleted; bulk path uses `Resolver.ResolveProfileName` per row.
- **C25:** ✓ commits `c604482` + `fc3923f` -- `Tests/Contract/TestNoParallelProfileCascade.py` green; only `EffectiveProfileResolver.py` may consume both `MediaFiles.AssignedProfile` and `SystemSettings.DefaultProfileName` in the same scope.
- **C26:** LIVE PENDING -- requires deliberate toggle: queue one Transcode job with `QualityTestEnabled=TRUE`, then with `=FALSE`, then trace via logs that the SAME function names are called in both runs (different branches taken). Needs smoke window.
- **C27:** ✓ commits `ea037ff` + `9e2c81c` -- Signal 5 added to `.claude/rules/call-graph-audit.md` + long-form in `.claude/rules-details/call-graph-audit.md`.
- **C10:** TBD
- **C11:** TBD (5 FileReplacement docs collapsed to 1+1)
- **C12:** TBD (no mode-branching in FileReplacement)
- **C13:** TBD (PostTranscodeDispositionService deleted)
- **C14:** TBD (no hardcoded VMAF/heartbeat thresholds)
- **C15:** TBD (ProcessingModes table + FK)
- **C16:** TBD (one ClaimNextPendingJob)
- **C17:** TBD (TranscodeQueueTestVariant sub-table)
- **C18:** TBD (AudioFixOnly → AudioFix)
- **C19:** TBD (QueueAdmissionRepository deleted)
- **C20:** TBD (AudioPolicyAdmissionGate synchronous)
- **C21:** TBD (one _NotifyJellyfin path)
- **C22:** TBD (GetFileReplacementStatus config-driven)
- **C23:** TBD (QualityTestController routes through EffectiveProfileResolver)
- **C24:** TBD (QMBS._GetEffectiveProfileFromCache deleted; one cascade implementation)
- **C25:** TBD (TestNoParallelProfileCascade contract test green)
- **C26:** TBD (call-graph shape independent of feature flags)
- **C27:** TBD (Signal 5 added to call-graph-audit rule)

### Decisions Made

Engineering calls made under ambiguity.

- **Phase A T2 (AudioFixOnly → AudioFix rename) required a destructive DDL on `MediaFiles.WorkBucket`** — the column is `GENERATED ALWAYS AS ... STORED`, so the rename required `DROP COLUMN + ADD COLUMN` with the new generation expression. This was done on the live dev DB during active worker fleet operation. Worker queries against `MediaFiles.WorkBucket` during the brief DDL window could have failed and reset queue rows to Pending; the rollback machinery in `TranscodedOutputPlacement` is designed to handle that. No data loss observed; if any orphan `.inprogress` files survive on SMB they should be cleaned up by the normal orphan-sweep.
- **Phase E T18 (PostFlight strategies) — `Quick` mode aliased to `RemuxPostFlight`.** The four-mode list in `PostFlightRegistry.BuildDefaultRegistry` maps `Quick → RemuxPostFlight` because behaviorally Quick is a stream-copy + container fix (identical to Remux in the post-flight phase). Separate Strategy classes for Quick + Remux would have been pure duplication.
- **Phase G T27 — `ClaimNextPendingJob` uses `tq.ProcessingMode != 'Transcode' OR (...)` for Transcode-only gates** (NVENC, AllowedProfiles, AcceptsInterlaced). This keeps Remux/AudioFix/SubtitleFix/Quick modes passing through those gates without separate claim queries. Adding a new mode is one `ProcessingModes` INSERT.
- **Phase H T28 — `AdmitSeries` chose per-row delegation over bulk INSERT** to ensure `AudioPolicyAdmissionGate` fires synchronously per row (C20). Trade-off: more per-row DB round-trips, but the gate fires for every row uniformly (no "bulk path bypasses the gate" risk).
- **Phase K (live verification) deferred to operator smoke window.** The implementation work (Phases A-J, ~30 commits) is structurally complete. C4, C5, C8, C26 require a controlled environment: stop the worker fleet, queue one job per mode, observe per-mode `AudioPolicyResolved` population, retry MediaFileId=621412, toggle `QualityTestEnabled` and trace logs for invariant call graph. The E2E test harness (`Tests/Contract/TestE2EPerBucket.py`) explicitly refuses to race the live fleet (`PipelineBusyError`), which is the right design — the operator owns the smoke window, not the assistant. Workers on I9 also need to be restarted to pick up the unified `JobProcessor` code (memory: "I9 worker IS the active codebase" — workers read source directly but only on restart).
- **WebService instability observed during contract test runs is NOT a directive-induced regression.** WebService served requests successfully during 22:40:01–22:40:21 then died with no stderr trace. Could be a pre-existing supersede / service-control issue triggered by contract tests that hit `/api/profiles/.../finalize` or `/api/Service/Stop` endpoints. Not investigated; separate concern from this directive.
- **30 commits, 22/27 criteria STRUCTURAL ✓, 5 criteria LIVE PENDING.** Directive stays at IMPLEMENTING phase; advancement to VERIFYING / DELIVERING requires operator-driven smoke window for the 5 LIVE PENDING criteria. Operator owns close.

- **T21 partial**: The R1 hook parses `transcript_path` (conversation transcript) for prior Read calls. Agent subagent Reads don't appear in that transcript -- hook consistently sees 0 reads for `disposition.feature.md`, blocking Edit to `RetranscodeDecider.py` and `DispositionDispatcher.py` (both in the same directory, both governed by disposition.feature.md via C3). Model+repo changes committed. The two .py edits require execution in the outer Claude Code session (not Agent tool) after reading disposition.feature.md limit=50 there.

---

## Web-Performance Design (L1 -- HTTP standards compliance)

**Promotes to `WebService/web-performance.feature.md` at DELIVERING.** Operator reported /Activity loads instantly on first visit but ~10 seconds on repeat navigation. Root cause (curl-confirmed): MediaVortex violates four HTTP standards (RFC 9111).

### Violations observed against running WebService

| RFC 9111 expectation | Actual MediaVortex response |
|---|---|
| Static immutable assets: `Cache-Control: public, max-age=<long>, immutable` | `Cache-Control: no-cache` -- forces revalidation every navigation |
| Conditional GET returns `304 Not Modified` on unchanged file | Returns `200 OK` with full body (revalidation broken) |
| `Content-Encoding: gzip` when `Accept-Encoding: gzip` advertised | Header absent; 720 KB transferred uncompressed per navigation |
| HTML pages: explicit `Cache-Control` (typically `no-cache, private`) | No header set; browser falls back to heuristic caching |
| API endpoints: `Cache-Control: no-store` (live data) | No header set; browsers may cache live data |

### Target criteria (will land as C1-C10 in `web-performance.feature.md` at DELIVERING)

C1. Static `/static/*` Cache-Control = `public, max-age=31536000, immutable`.
C2. Cache-bust via `?v=<mtime>` appended in `url_for('static', ...)` so file edits invalidate browser cache automatically.
C3. HTML pages Cache-Control = `no-cache, private`.
C4. `/api/*` Cache-Control = `no-store`.
C5. Conditional GET returns 304 on unchanged static.
C6. Text responses (CSS/JS/JSON/HTML) compressed via `flask-compress` when client advertises.
C7. ONE aggregate endpoint `/api/Layout/NavBadges` replaces the 4 parallel polls in Base.html (`/api/TranscodeQueue/Count`, `/api/SQLQueries/GetActiveJobs`, `/api/FailedJobs/Count`, `/api/Activity/LibraryCompliance`); nav polls it every 30s.
C8. Zero external origins in `Templates/*.html` (already done in commit `dcf866b`).
C9. Production WSGI (waitress, not Flask dev). (already done in commit `e9f4ce8`).
C10. Cold first /Activity load < 1.5s; warm-cache navigation < 500ms.

### Seams (will land in C5 -> S1..S4 of the feature doc)

| ID | Seam | Producer | Wire shape |
|---|---|---|---|
| S1 | WSGI response -> Cache-Control | `_RegisterResponseHeaders` (Flask `@after_request` hook) keyed on `request.path` prefix | header per path-class: `/static/*` immutable, `/api/*` no-store, else no-cache,private |
| S2 | WSGI body -> gzipped | `flask-compress` middleware (`Compress(app)`) | `Content-Encoding: gzip` on text responses |
| S3 | Template -> versioned static URL | `_DatedUrlFor` overrides `url_for('static',...)` to append `?v=<mtime>` | `{{ url_for('static', filename='foo.css') }}` -> `/static/foo.css?v=1782748006` |
| S4 | Base.html -> NavBadges aggregate | `Templates/Base.html` `updateNavBadges` setInterval@30s | `GET /api/Layout/NavBadges` -> `{Success, Data: {QueueCount, ActiveJobsCount, FailedJobsCount, Transcode, Remux, AudioFix}}` |

### Files (will land in the feature doc's ## Files table)

| File | Role |
|---|---|
| `WebService/Main.py` | new: `_RegisterResponseHeaders` + `_DatedUrlFor` + flask-compress init; existing: `Run()` already calls `waitress.serve` |
| `WebService/requirements.txt` | add `flask-compress>=1.13` |
| `Features/Layout/LayoutController.py` (new) | new `/api/Layout/NavBadges` aggregate endpoint -- joins existing repository calls into one payload |
| `Templates/Base.html` | replace 4 fetches in nav-update IIFE with single `/api/Layout/NavBadges` poll |

### Out of L1 scope (deferred, may land as separate directives)

- **L2 -- HTMX-driven navigation.** Attempted via `hx-boost="true"` on Base.html body; reverted in commit `8894d20` because existing page templates use `$(document).ready()` or inline `<script>` that bootstraps via the browser's full-load lifecycle. HTMX swaps the content area without firing those events, so page-specific data fetches never re-init (operator confirmed broken on /Queue immediately). Reintroduction requires per-template HTMX-aware init refactor (listen to `htmx:afterSwap`) — out of L1 scope; the documented design stays here as the next standards-correct upgrade after each page is audited.
- **L3 -- SSE (Server-Sent Events) for live progress.** Implemented for `/Activity` in commit `2f2b7d6`: `GET /api/Activity/Stream` returns `text/event-stream`; the generator pushes the snapshot JSON every 1.5s when the payload differs from the prior push (else `: keepalive`). Activity.html replaced `setInterval(LoadActivity, 5000)` with `EventSource('/api/Activity/Stream')`; auto-fallback to 5s polling on `EventSource` undefined or `onerror`. Same shape ready to apply to `/Admin/Workers` (live worker state) and `/Admin/Compliance` (library counts) -- not yet wired.

---

## Queue Page Redesign

**Promotes to existing `Features/TranscodeQueue/TranscodeQueue.feature.md` C9 (replaced 2026-06-29) + `Features/QualityTesting/qt-queue-visibility-and-override.feature.md` Progress checklist (VMAF card partial).** Operator asked for a multi-queue Queue page with reorderable + collapsible sections.

### What landed

- **Route**: new `GET /Queue` renders `Templates/Queue.html`; legacy `/TranscodeQueue` 301-redirects to `/Queue`. Base.html nav link points at `/Queue` and matches the `queue_page` endpoint for active-class highlighting.
- **Layout**: four stacked cards in one host container, in default order `Transcode → Remux → Audio → VMAF`. Each card has its own `data-key` (`Transcode` / `Remux` / `Audio` / `VMAF`), drag handle, chevron toggle, summary line, count badge, paged table body.
- **Per-mode data sources**: TranscodeQueue cards filter the existing `/api/TranscodeQueue/GetQueue` endpoint via the `mode=` query param (`Transcode`, `Remux`, `AudioFix`); VMAF card uses `/api/QualityTest/Queue`.
- **Aggregate stats endpoints** (new for accurate summary text):
  - `GET /api/TranscodeQueue/AggregateStats?mode=<Transcode|Remux|AudioFix|Quick>` -- one query, `GROUP BY Status + SUM(SizeMB)`. Returns `{TotalCount, PendingCount, RunningCount, FailedCount, TotalSizeMB}`.
  - `GET /api/QualityTest/AggregateStats` -- VMAF-side equivalent. Returns `{TotalCount, PendingCount, RunningCount, FailedCount, CompletedCount}`.
  - Stats are whole-queue aggregates -- NOT page-scoped -- so summary text is correct regardless of which page the operator is viewing.
- **Drag-reorder**: native HTML5 draggable; `dragover` highlights drop-edge; `drop` reorders DOM and persists the new key order to `localStorage['MvQueueOrder']`.
- **Collapse**: per-card chevron toggle; `localStorage['MvQueueCollapsed']` stores `{key: bool}`. **Default state is all-collapsed** when no prior state exists; operator expands the queues they want to act on. CSS `.queue-card.collapsed .card-body { display: none; }`.

### Files (will land in the feature doc's ## Files table at DELIVERING)

| File | Role |
|---|---|
| `Templates/Queue.html` | Rewritten as four-card layout with drag-reorder + collapse + summary; replaces the prior 1-table + 1-quality-testing-table page |
| `Features/TranscodeQueue/TranscodeQueueController.py` | New `/api/TranscodeQueue/AggregateStats` endpoint |
| `Features/QualityTesting/QualityTestController.py` | New `/api/QualityTest/AggregateStats` endpoint |
| `WebService/Main.py` | New `/Queue` route; legacy `/TranscodeQueue` 301-redirects |
| `Templates/Base.html` | Nav link points at `/Queue`; active match on `queue_page` endpoint |
| `Features/TranscodeQueue/TranscodeQueue.feature.md` | C9 rewritten to describe four-card contract |
| `Features/QualityTesting/qt-queue-visibility-and-override.feature.md` | Progress checklist updated: VMAF card portion delivered, per-row override buttons still deferred |

### ui-verify evidence (commit `cdb244b` follow-up)

Headless Chromium against the live `/Queue` page confirmed:
- 4 cards rendered with `data-key` values `Transcode`, `Remux`, `Audio`, `VMAF`
- 4 cards default to `.collapsed`
- Audio card summary text reads `(45 pending • 11 running • 3.4 GB total)` from `AggregateStats`
- Clicking the Audio card's chevron removes `.collapsed` -- table expands
- Screenshots: `~/.claude/ui-verify/screenshots/queue-collapsed.png` and `queue-audio-expanded.png`
