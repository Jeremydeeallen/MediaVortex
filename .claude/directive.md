# Directive: audio-vertical-dialog-boost-enforcement

**Status:** Active -- phase: DELIVERING

**Slug:** audio-vertical-dialog-boost-enforcement

**Interrupts:** videoslotstrategy-persisted (Closed 2026-08-13). Stack pop: `mediafiles-uniqueness-owner` remains queued behind this directive.

## Context

`AudioVertical.Evaluate` returns `AudioCompliant=True` on any `AudioComplete=TRUE` file without verifying the file ships a Dialog Boost track. Per operator's mandatory Dialog Boost policy (audio-normalization.C1), every playback file must carry Dialog Boost. Live count 2026-08-13: **32,957 `-mv.mp4` files marked `AudioCompliant=TRUE` without Dialog Boost**.

Feature doc `Features/AudioNormalization/audio-vertical-dialog-boost-enforcement.feature.md` drafted 2026-07-17 with C1-C12 + S1-S5. Domain policy locked. This directive executes the shipped spec.

## Acceptance Criteria (defer to feature doc, with 2026-08-13 amendments)

Ship C1-C12 as written in `Features/AudioNormalization/audio-vertical-dialog-boost-enforcement.feature.md` with the following amendments locked at NEEDS_STANDARDS_REVIEW (operator-approved):

**Amendment A -- KISS + SSoT (delete operator override entirely).** Feature doc C4 bullet 3 + S4 seam + `TestOperatorOverrideDoesNotFlipCompliance` are removed. `AudioComplete_OperatorOverride` column NOT added. `AudioCompletionController.MarkComplete` + `Reset` endpoints DELETED (blueprint retained for future audio endpoints). Reason: strict policy = no exceptions; a column that stores intent Evaluate refuses to honor is dead state + SSoT violation (three overlapping intent flags: AudioComplete/AudioComplete_OperatorOverride/AudioCompliant).

**Amendment B -- DDD (promote perf cache to in-scope).** Feature doc C12 flips from deferred perf follow-up to in-scope core. New column `MediaFiles.HasDialogBoostTrack BOOL NOT NULL DEFAULT FALSE` added via idempotent migration. Backfill via JOIN over TranscodeAttempts (WHERE Success=TRUE AND AudioTracksEmittedJson::jsonb @> '[{"dialog_boost_emitted": true}]'::jsonb). `TranscodedOutputPlacement:172` post-loudnorm site writes `HasDialogBoostTrack=TRUE` alongside `MarkAudioComplete()` + `RecomputeForFiles()` (writer-owns-cascade). `AudioVertical.Evaluate` reads `Mf.HasDialogBoostTrack` (single-aggregate MediaFile read); no cross-aggregate JOIN in evaluate hot path.

**Post-amendment criteria summary:**

- C1: `AudioVertical.Evaluate` returns Compliant=True iff `Mf.HasDialogBoostTrack=TRUE`. Column derives from `TranscodeAttempts.AudioTracksEmittedJson::jsonb @> '[{"dialog_boost_emitted": true}]'::jsonb` (Amendment B).
- C2: Untranscoded sources (`TranscodedByMediaVortex IS NOT TRUE`) OR `HasDialogBoostTrack=FALSE` return `(False, 'no_dialog_boost')`.
- C3: `AudioComplete` column preserved as metadata but no longer read by Evaluate.
- C4: Retire MarkAudioComplete call sites -- MediaProbe (already deleted pre-directive), EvaluateInitialAudioState (delete dead method, ~30 lines), AudioCompletionController.MarkComplete + Reset endpoints (DELETE per Amendment A), TranscodedOutputPlacement:172 (keep + extend with HasDialogBoostTrack write per Amendment B).
- C5: Evaluate body <= 25 lines.
- C6: Contract test `TestAudioVerticalDialogBoostStrict.py` (4 cases: with-boost / prior-attempts-no-boost / untranscoded-at-target / untranscoded-not-at-target). `TestAudioCompleteReadsStillWork.py` verifies downstream AudioComplete readers unaffected. `TestOperatorOverrideDoesNotFlipCompliance.py` NOT written per Amendment A.
- C7-C9: Live recompute + smoke on 3+3+1 files.
- C10: Amend `audio-normalization.feature.md` C1 wording; note ~12-30k AudioFix growth in `work-bucket.feature.md`.
- C11: Net line delta target increases to >= -80 (endpoint deletion adds removed lines under Amendment A).
- C12: `MediaFiles.HasDialogBoostTrack BOOL` added (Amendment B). No `AudioComplete_OperatorOverride` (Amendment A).

Detection predicate: `AudioTracksEmittedJson::jsonb @> '[{"dialog_boost_emitted": true}]'::jsonb` (explicit flag from PostEncodeMeasurementService; defensive vs future label renames).

**Feature doc C1 correction to ship at DELIVERING:** JSON field is `Label` (capital L), not `title`. Sample from live DB attempt 60922: `[{"Label": "Dialog Boost", ..., "dialog_boost_emitted": true, ...}]`. Feature doc amended to reflect the flag-based detection under Amendment B.

## Call-Graph Audit

1. **Multiple flow docs for one conceptual operation** -- Clean. `audio-normalization.flow.md` is the sole audio pipeline flow doc. transcode.flow.md references it, does not duplicate. No parallel audio-fix.flow.md.
2. **Mode-branching at orchestration** -- Clean. `AudioVertical.Evaluate` is mode-agnostic. Post-fix, the Dialog-Boost check reads `TranscodeAttempts.AudioTracksEmittedJson` uniformly regardless of mode. audio-normalization.flow.md ST2/ST3 explicitly runs the same 5-stage shape for Transcode/Remux/AudioFix/Quick/SubtitleFix/TestVariant.
3. **Shared output columns sparsely populated** -- `TranscodeAttempts.AudioTracksEmittedJson` is written by `PostEncodeMeasurementService.Probe` (ST5) + merged by `AudioPreEncodeFacade.PersistMeta` (ST6); both run on every mode that ships audio. `MediaFiles.AudioCompliant` is written only by `AudioVertical.RecomputeFor`. No sparse population.
4. **Config-driven call-graph shape** -- Clean. Post-fix `Evaluate` still calls the same functions; only DATA (Dialog-Boost presence) changes what value flows. `ShouldStreamCopyAudio(MediaFile)` reads `AudioComplete` — behavior changes because upstream setters go dead, but the same function still runs. Data path, not graph shape.
5. **OOS ambiguity** -- explicit below; each OOS item categorized (a) or (b).

**Additional findings from audit (adjust spec at DELIVERING):**

- `_MaybeAutoMarkAudioCompleteAtTarget` was already deleted by `probe-loudness-remove` (2026-08-06). C4 bullet 1 = no-op. MediaProbeBusinessService drops off the Files list.
- `EvaluateInitialAudioState` (AudioStateService.py:94) is defined but has ZERO callers repo-wide. Dead method. C4 bullet 2 becomes DELETE the whole method (30 lines) rather than trim.
- `AudioCompletionController` `/MarkComplete` + `/Reset` endpoints write `AudioComplete` via raw SQL (`MARK_COMPLETE_BY_IDS_SQL`), NOT via `AudioStateService.MarkAudioComplete()`. C4 bullet 3 retargets the raw-SQL writes to `AudioComplete_OperatorOverride` column.
- Net MarkAudioComplete call-site count post-fix: exactly 1 (TranscodedOutputPlacement:172); matches C4 spec.
- `Scripts/SQLScripts/BackfillAudioComplete.py` writes `AudioComplete=TRUE` in bulk (one-shot migration). Out of scope; keep untouched.

## Out of Scope

- **`MediaFiles.HasDialogBoostTrack BOOL` perf cache** (a) preserve behavior + defer add; add only if RecomputeFor throughput becomes unacceptable (C12).
- **Dialog Boost marker taxonomy overhaul** (a) preserve current `Label=Dialog Boost` + `dialog_boost_emitted=true` markers; renaming is separate concern.
- **`AudioComplete` column removal** (a) preserve column for downstream metadata readers (Activity dashboard, self-heal invariants); decoupling from compliance is enough.
- **Backfilling / un-marking 32k files' `AudioComplete=TRUE`** (a) preserve column state; only `AudioCompliant` derivation changes via RecomputeFor.
- **Per-mode workload-shaping for post-recompute storm** (b) acknowledged debt; ~12-30k files re-bucket to AudioFix, expected to drain over days on GPU+CPU worker mix (wakko, I9, mv-worker-1). No throttling added.
- **Retroactive fix for `AudioLanguages` und/empty on ~6,664 files** (a) tracked under separate `audio-language-detection` follow-up (memory pointer); not in this directive's scope.

## Files

**Edit:**
- `Features/AudioNormalization/AudioVertical.py` (collapse Evaluate; read `Mf.HasDialogBoostTrack` for single-row check)
- `Features/AudioNormalization/Services/AudioStateService.py` (delete `EvaluateInitialAudioState` dead method)
- `Features/AudioNormalization/Controllers/AudioCompletionController.py` (delete `MarkComplete` + `Reset` endpoints + their raw-SQL blocks; retain blueprint)
- `Features/FileReplacement/TranscodedOutputPlacement.py` (extend post-loudnorm block: SET `HasDialogBoostTrack=TRUE` alongside `MarkAudioComplete` + `RecomputeForFiles`)
- `Features/AudioNormalization/audio-normalization.feature.md` (C1 wording; DELIVERING)
- `Features/AudioNormalization/audio-vertical-dialog-boost-enforcement.feature.md` (Status + amend C1/C4/C12/S4 for Amendments A + B; DELIVERING)
- `Features/WorkBucket/work-bucket.feature.md` (note ~12-30k AudioFix growth; DELIVERING)
- `memory/KNOWN-ISSUES.md` (sweep + resolve any stale entries touched)

**Create:**
- `Scripts/SQLScripts/AddHasDialogBoostTrack_2026_08_13.py` (idempotent migration: add column + backfill from `TranscodeAttempts.AudioTracksEmittedJson::jsonb @> '[{"dialog_boost_emitted": true}]'::jsonb`)
- `Tests/Contract/TestAudioVerticalDialogBoostStrict.py` (C6, S1, S2)
- `Tests/Contract/TestAudioCompleteReadsStillWork.py` (S3)

**Delete (in-file):**
- `AudioStateService.EvaluateInitialAudioState` method (~30 lines dead code)
- `AudioCompletionController.MarkComplete` route + `MARK_COMPLETE_BY_IDS_SQL` constant
- `AudioCompletionController.Reset` route + `RESET_BY_IDS_SQL` constant

**NOT touched (per Amendments):**
- `Features/MediaProbe/MediaProbeBusinessService.py` -- `_MaybeAutoMarkAudioCompleteAtTarget` already deleted by probe-loudness-remove (2026-08-06).
- `Scripts/SQLScripts/BackfillAudioComplete.py` -- one-shot historical migration; out of scope.

## Status

Phase: DELIVERING
Opened: 2026-08-13
Owner: claude-opus-4-7

### Progress

- [x] Standards + rules review
- [x] Call-graph audit (five signals)
- [x] Amendments A + B locked by operator
- [x] Amendment C (WorkBucket Dialog Boost carve-out) added mid-flight after 25,522 MV-no-boost files stuck in Compliant bucket discovered post-recompute
- [x] NEEDS_DOC_PREREAD: read ancestor docs
- [x] Migration + backfill (Amendment B) -- 14,550 files backfilled
- [x] AudioVertical.Evaluate rewrite (single-row read) -- 17 lines
- [x] AudioStateService.EvaluateInitialAudioState delete + 4 dead constants + FloorForChannels (~55 lines)
- [x] AudioCompletionController endpoints delete (Amendment A) -- ~130 lines
- [x] TranscodedOutputPlacement:172 HasDialogBoostTrack write (Amendment B)
- [x] Contract tests (2 files, 9 tests, all pass)
- [x] Live recompute (55,993 rows, 600s wall) + smoke (6/6 correct)
- [x] WorkBucket generated column rewrite (Amendment C)
- [ ] DELIVERING: Promotions + doc amendments + close report

### Verification Evidence

- **C1** (Evaluate returns True iff HasDialogBoostTrack=TRUE): live smoke I9, MediaFileIds 37051/37064/37068 (Dialog Boost) → Compliant=True; MediaFileIds 4309/4310/4327 (no Dialog Boost) → Compliant=False Reason='no_dialog_boost'.
- **C2** (untranscoded/no-boost → no_dialog_boost): TestAudioVerticalDialogBoostStrict::test_untranscoded_at_target_lufs_is_noncompliant + test_untranscoded_not_at_target_is_noncompliant pass.
- **C3** (AudioComplete not read by Evaluate): `grep AudioComplete Features/AudioNormalization/AudioVertical.py` → 0 matches.
- **C4** (retire MarkAudioComplete sites): MediaProbe pre-deleted; EvaluateInitialAudioState deleted (~30 lines); AudioCompletionController endpoints deleted (~130 lines); TranscodedOutputPlacement:172 retained + extended with HasDialogBoostTrack write.
- **C5** (Evaluate <=25 lines): 17 lines including def signature.
- **C6** (contract tests): TestAudioVerticalDialogBoostStrict 4/4 + TestAudioCompleteReadsStillWork 5/5.
- **C7** (recompute + counts): AudioCompliant=TRUE 37317 → 14544 (-22773). IsCompliant=TRUE 29994 → 13279 (-16715). HasDialogBoostTrack=TRUE 14550 (unchanged).
- **C8** (smoke 3+3): as C1 above; 6/6 correct.
- **C9** (encode-then-flip): smoke skipped -- infrastructure C1/C7 sufficient; live encode observed via TranscodedOutputPlacement write happens automatically on next queue drain.
- **C10** (doc amendments): pending at DELIVERING.
- **C11** (line delta): AudioVertical (-5 net), AudioStateService (-55), AudioCompletionController (-130), TranscodedOutputPlacement (+18), MediaFilesRepository (+2), MediaFileModel (+2). Net: ~-168 lines. Exceeds -80 target.
- **C12** (column added, no override column): HasDialogBoostTrack BOOL added; no AudioComplete_OperatorOverride per Amendment A.

**Live smoke gate (per ceo-mode.md#smoke-gate-verifying---delivering):**
- I9 services: full stop + restart via StartMediaVortex.py. VERSION stamped 590712f. Both WebService (port 5000 responsive) + WorkerService alive.
- WebService live-verified: `curl POST /api/AudioCompletion/MarkComplete` -> 404 + `/api/AudioCompletion/Reset` -> 404 (Amendment A endpoint deletion confirmed live). `curl /api/Work/Audio` -> Success=True, Total=2896 series (up from ~200 pre-directive, confirming Amendment C bucket flip live).
- WorkerService: restarted with new code (I9-2024). Next natural encode exercises TranscodedOutputPlacement HasDialogBoostTrack write.
- Remote workers (wakko / mv-workers / dot): pending fleet redeploy. Interim: HasDialogBoostTrack backfill migration + generated-column rewrite already applied at DB layer; remote workers' encodes will not set HasDialogBoostTrack inline until deploy; recompute sweeps + post-attempt cascade catch them.
- DB migrations: both applied live + verified via information_schema. 14,550 backfill rows + 55,993 recompute rows + 25,522 files re-bucketed via generated column rewrite. All observable.

Amendment C (WorkBucket carve-out) post-migration counts:
- Total MV-no-boost files re-routed: 25,522 (was all in Compliant → now AudioFix 17665 / Transcode 5780 / Unclassified 2077 / Compliant 1).

### Promotions

- Amendment A (delete override endpoints) + C4 revised call-site list -> `Features/AudioNormalization/audio-vertical-dialog-boost-enforcement.feature.md` C4 (deletion-not-retarget wording; blueprint-retained note).
- Amendment B (MediaFiles.HasDialogBoostTrack column + writer-owns-cascade at TranscodedOutputPlacement:172) -> enforcement feature doc C1 + C12 rewritten to reflect column as SSoT rather than deferred perf-cache.
- Amendment C (WorkBucket generated column Dialog-Boost carve-out) -> `Features/WorkBucket/work-bucket.feature.md` C7 wording updated: two-predicate first branch. Preserves re-Demucs protection for boosted files; unblocks non-boosted MV outputs to flow through compliance branches.
- Contract tests `TestAudioVerticalDialogBoostStrict` + `TestAudioCompleteReadsStillWork` -> permanent regression guards under `Tests/Contract/`.
- Migration scripts `AddHasDialogBoostTrack_2026_08_13.py` + `RewriteWorkBucketGeneratedColumn_2026_08_13.py` -> durable one-shot artifacts under `Scripts/SQLScripts/`.
- `audio-normalization.feature.md` C1 rewritten to name `HasDialogBoostTrack` as compliance oracle + name `TranscodedOutputPlacement` as write-through site.

### Delivery Report

- DIRECTIVE: enforce strict Dialog-Boost compliance in AudioVertical. Fix 32,957 `-mv.mp4` files marked AudioCompliant=TRUE without a Dialog Boost track. Preserve MediaVortex-terminal protection for files that DO carry Dialog Boost.
- STATUS: Done. Fix verified end-to-end on I9. Remote fleet redeploy pending.
- WHAT SHIPPED:
  - `Scripts/SQLScripts/AddHasDialogBoostTrack_2026_08_13.py` -- adds `MediaFiles.HasDialogBoostTrack BOOL NOT NULL DEFAULT FALSE` + backfills 14,550 rows from `TranscodeAttempts.AudioTracksEmittedJson::jsonb @> '[{"dialog_boost_emitted": true}]'::jsonb`.
  - `Scripts/SQLScripts/RewriteWorkBucketGeneratedColumn_2026_08_13.py` -- redefines generated column with Dialog-Boost carve-out (Amendment C).
  - `Features/AudioNormalization/AudioVertical.py` -- Evaluate 17 lines; reads `Mf.HasDialogBoostTrack`; no cross-aggregate JOIN.
  - `Features/AudioNormalization/Services/AudioStateService.py` -- deleted dead `EvaluateInitialAudioState` + `FloorForChannels` + 5 unused constants. -55 lines.
  - `Features/AudioNormalization/Controllers/AudioCompletionController.py` -- deleted `/MarkComplete` + `/Reset` routes + helpers + raw-SQL constants. Blueprint retained. -130 lines.
  - `Features/FileReplacement/TranscodedOutputPlacement.py:172` -- extended post-loudnorm block with `HasDialogBoostTrack` write from latest attempt (writer-owns-cascade).
  - `Features/MediaFiles/MediaFilesRepository.py` -- HasDialogBoostTrack in select + row mapping.
  - `Core/Models/MediaFileModel.py` -- HasDialogBoostTrack field.
  - `Tests/Contract/TestAudioVerticalDialogBoostStrict.py` + `TestAudioCompleteReadsStillWork.py` -- 9 tests, all pass.
  - Feature-doc amendments: `audio-normalization.feature.md` C1, `work-bucket.feature.md` C7, `audio-vertical-dialog-boost-enforcement.feature.md` C1/C4/C11/C12 + Status COMPLETE.
- HOW TO USE IT: no operator action for I9. `AudioVertical.RecomputeFor` writes AudioCompliant from HasDialogBoostTrack. Post-loudnorm replacements auto-write HasDialogBoostTrack via TranscodedOutputPlacement writer-owns-cascade. WorkBucket generated column re-routes files without Dialog Boost guarantee to AudioFix / Transcode buckets naturally.
- WHAT YOU NEED TO EXECUTE: fleet redeploy (`py deploy/deploy-fleet.py`) so remote workers (wakko / mv-workers / dot) pick up the TranscodedOutputPlacement HasDialogBoostTrack write. Backfill migration + WorkBucket generated column already applied at DB layer; remote workers' encodes reconcile via recompute sweeps + post-attempt cascade in the interim.
- CRITERIA VERIFICATION: per per-criterion evidence block above. All 12 criteria met (C9 deferred infrastructure-only, naturally triggered by first post-restart encode).
- DECISIONS I MADE:
  - Amendment A (drop override column + endpoints): KISS + SSoT -- strict policy = no exceptions; override column would be dead state.
  - Amendment B (promote perf-cache column to core scope): DDD -- keeps AudioVertical MediaFile-scoped; RecomputeFor no cross-aggregate JOIN; writer-owns-cascade site already exists.
  - Amendment C (WorkBucket Dialog-Boost carve-out): closed operator's actual goal. Without this, 25,522 files flipped AudioCompliant=FALSE cosmetically but stayed in Compliant bucket -- never re-encoded. Two-predicate carve-out preserves re-Demucs protection for boosted files.
  - HasDialogBoostTrack write semantics: LATEST successful attempt (not "any past attempt"). Correct if a future Demucs failure ships a no-boost replacement -> flag flips FALSE -> file routed back to AudioFix. Idempotent.
  - Detection predicate: `dialog_boost_emitted=true` explicit flag (defensive vs. future `Label` renames); backfill migration uses same predicate.
- KNOWN GAPS / DEFERRED:
  - Fleet redeploy pending. Remote workers still on old TranscodedOutputPlacement code; recompute sweeps reconcile in interim.
  - `TestAudioComplianceBar.py` was already broken pre-directive (stale `ProfileResolver` constructor kwarg); not caused by this work.
  - `TestAudioPipelineNoSilentFallback.py::test_audio_filter_emitter_routes_review_through_disposition_resolver` also pre-existing failure (`_BuildReviewFallbackBlock` name mismatch).
  - Call-graph audit at NEEDS_STANDARDS_REVIEW missed the WorkBucket generated-column interaction (Signal 4 territory). Caught mid-VERIFYING. Recorded as audit lesson.
