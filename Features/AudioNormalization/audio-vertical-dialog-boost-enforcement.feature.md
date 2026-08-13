# Audio Vertical Dialog Boost Enforcement

**Slug:** audio-vertical-dialog-boost-enforcement

## Interrupts: mediafiles-uniqueness-owner

## What It Does

Locks the audio vertical to a single, strict, verifiable criterion: **a file is audio-compliant iff it carries a Dialog Boost track produced by MediaVortex's 2-track pipeline**. Retires four legacy `AudioComplete=TRUE` marker paths whose semantics no longer match the strict policy. Compliance derives from `TranscodeAttempts.AudioTracksEmittedJson` — data we already write — via a JOIN. Zero new columns unless perf demands one.

Simplification-first: `AudioVertical.Evaluate` collapses; four legacy MarkAudioComplete call sites reviewed for retirement; the audio-normalization feature doc's C1 tightens from "encoder output ships >=2 streams" to "compliance verifies Dialog Boost track present."

## Domain policy (locked 2026-07-17)

- **Every playback file must have a Dialog Boost track.** No exceptions for at-target-loudness sources.
- **Untranscoded sources** (`TranscodedByMediaVortex=FALSE`) are NOT compliant on the audio axis regardless of their measured LUFS.
- **Ground truth** = latest successful `TranscodeAttempts.AudioTracksEmittedJson` for the MediaFileId contains a Dialog Boost track. No cutover-date constant; the data self-verifies.

## Population impact (locked estimate)

Query at directive open (2026-07-17):
- `IsCompliant=TRUE` today: **14,118**
- Of those, no Dialog Boost track: **12,637 (89.5%)**
- Truly Dialog-Boost-compliant: **1,481**
- Post-directive `IsCompliant=TRUE` estimate: **~1,481**
- ~12,637 files re-bucket to `WorkBucket='AudioFix'` (or `Transcode` if video also fails, per existing precedence)

## Success Criteria

C1. `AudioVertical.Evaluate(Mf)` returns `Compliant=True` **iff** `Mf.HasDialogBoostTrack=TRUE` (single-aggregate MediaFile read; DDD-clean). The `HasDialogBoostTrack BOOL` column is derived from `TranscodeAttempts.AudioTracksEmittedJson::jsonb @> '[{"dialog_boost_emitted": true}]'::jsonb` for the latest successful attempt, written via writer-owns-cascade at `TranscodedOutputPlacement:172` alongside `MarkAudioComplete` + `RecomputeForFiles`. Detection uses `Label='Dialog Boost'` (structural) + `dialog_boost_emitted=true` (explicit flag from `PostEncodeMeasurementService`); both coincide in emitted JSON.

C2. Untranscoded sources (`Mf.TranscodedByMediaVortex IS NOT TRUE`) return `Compliant=False, Reason='no_dialog_boost'` from the audio vertical. LUFS-at-target is no longer an escape hatch.

C3. `AudioComplete` column is preserved for metadata (LUFS-at-target signal) but is **no longer read by `AudioVertical.Evaluate`**. Grep of `AudioVertical.py` for `AudioComplete` returns 0 after the change.

C4. Retire the legacy MarkAudioComplete / AudioComplete-writing sites whose semantics are obsolete under strict policy:
- `MediaProbeBusinessService._MaybeAutoMarkAudioCompleteAtTarget` — DELETED (by `probe-loudness-remove` 2026-08-06, pre-directive).
- `AudioStateService.EvaluateInitialAudioState` — DELETED (~30 lines dead method + FloorForChannels helper + 5 unused constants; ~55 lines total).
- `AudioCompletionController` /MarkComplete + /Reset endpoints — DELETED (Amendment A -- KISS + SSoT: strict policy = no exceptions; a column storing intent Evaluate refuses to honor is dead state). Blueprint retained for future audio endpoints.
- `TranscodedOutputPlacement:172` post-transcode MarkAudioComplete — kept + EXTENDED with `HasDialogBoostTrack` write from latest attempt's AudioTracksEmittedJson (Amendment B writer-owns-cascade site).

Grep of `MarkAudioComplete(` in production tree returns exactly one live call (TranscodedOutputPlacement:172).

C5. `AudioVertical.Evaluate` method body ≤ 25 lines total (currently ~20 lines). No growth despite adding the Dialog Boost check.

C6. Contract test `Tests/Contract/TestAudioVerticalDialogBoostStrict.py`:
- File with Dialog Boost attempt → Compliant=True
- File with prior attempts but none with Dialog Boost → Compliant=False, Reason='no_dialog_boost'
- Untranscoded file at target LUFS → Compliant=False, Reason='no_dialog_boost'
- Untranscoded file not at target LUFS → Compliant=False, Reason unchanged (needs_normalization or codec fail per prior chain)
- Corrupt/no-audio/measurement-failed short-circuits unchanged

C7. Recompute + backfill: run `AudioVertical.RecomputeFor` across every MediaFileId. Live SQL verifies post-recompute:
- `SELECT COUNT(*) FROM MediaFiles WHERE IsCompliant=TRUE` drops from ~14,118 to ~1,481 (±5%).
- `SELECT COUNT(*) FROM MediaFiles WHERE WorkBucket='AudioFix'` grows by ~12,000.
- Zero files with Dialog Boost track show IsCompliant=FALSE on audio axis (verified via JOIN + WorkBucket).

C8. Live smoke: pick 3 currently-compliant files without Dialog Boost, run RecomputeFor, assert IsCompliant flips FALSE + WorkBucket='AudioFix'. Pick 3 currently-compliant files with Dialog Boost, run RecomputeFor, assert IsCompliant stays TRUE.

C9. Live smoke: pick 1 non-Dialog-Boost file, enqueue for AudioFix via existing pipeline, watch encode → Replace → RecomputeFor. Assert file's IsCompliant flips TRUE post-attempt (Dialog Boost now present).

C10. `audio-normalization.feature.md` C1 wording updated to reflect the strict + verified invariant: "AudioVertical.Evaluate returns Compliant=True iff the file's latest successful TranscodeAttempt emitted a Dialog Boost track." `work-bucket.feature.md` documents the ~12.6k queue growth as expected consequence of policy change.

C11. Line-count delta:
- `AudioVertical.Evaluate` rewrite: 17 lines including def signature (was ~22).
- `AudioStateService.EvaluateInitialAudioState` + `FloorForChannels` + 5 unused constants: -55 lines.
- `AudioCompletionController.MarkComplete` + `Reset` routes + raw-SQL constants + `_ResolveMediaFileIds` helper: -130 lines.
- `TranscodedOutputPlacement:172` HasDialogBoostTrack write extension: +18 lines.
- `MediaFilesRepository.py` HasDialogBoostTrack column mapping: +2 lines.
- `MediaFileModel.py` HasDialogBoostTrack field: +2 lines.
- Net: ~-168 lines in production code (target was ≥ -80 post-Amendment A).

C12. `MediaFiles.HasDialogBoostTrack BOOL NOT NULL DEFAULT FALSE` column added (Amendment B). Column is single-source-of-truth for Dialog Boost compliance; keeps AudioVertical.Evaluate MediaFile-scoped (no cross-aggregate JOIN into TranscodeAttempts). Backfilled from `TranscodeAttempts.AudioTracksEmittedJson::jsonb @> '[{"dialog_boost_emitted": true}]'::jsonb` at migration time (14,550 rows); maintained inline by TranscodedOutputPlacement writer-owns-cascade going forward.

## Seams

| ID | Seam | Producer | Wire shape | Consumer expects | Verification |
|----|------|----------|-----------|------------------|--------------|
| S1 | Dialog Boost track presence | `TranscodeAttempts.AudioTracksEmittedJson` | JSON array; entry with `title` matching Dialog Boost marker | `AudioVertical.Evaluate` reads via JOIN | `TestAudioVerticalDialogBoostStrict::test_join_positive_case` |
| S2 | Strict audio compliance | `AudioVertical.Evaluate(Mf)` | `(True, None)` iff Dialog Boost attempt exists; `(False, 'no_dialog_boost')` otherwise; corrupt/no-audio/failed chain unchanged | `RecomputeFor` writes `AudioCompliant + AudioCompliantReason` | `TestAudioVerticalDialogBoostStrict` full matrix |
| S3 | AudioComplete decouples from compliance | Legacy `MarkAudioComplete` callers | `AudioComplete` column stays as metadata; compliance no longer reads it | Downstream tooling (Activity dashboard, self-heal invariants) still reads `AudioComplete` for their own signals; nothing breaks | `TestAudioCompleteReadsStillWork` |
| S4 | Operator override signal (documentation) | `AudioCompletionController` | Writes `AudioComplete_OperatorOverride=TRUE` (new column) | Vertical ignores; column is human-visible signal | `TestOperatorOverrideDoesNotFlipCompliance` |
| S5 | Recompute cascade | `AudioVertical.RecomputeFor(ids)` | UPDATE MediaFiles per row; GENERATED WorkBucket re-derives | Downstream `NextTranscodeBatch` sees ~12k new AudioFix candidates | Live SQL count deltas + smoke C8/C9 |

## Scope

**In:**
- `Features/AudioNormalization/AudioVertical.py` — Evaluate rewrite (strict Dialog Boost check via JOIN)
- `Features/AudioNormalization/Services/AudioStateService.py` — trim `EvaluateInitialAudioState` complete-branches
- `Features/MediaProbe/MediaProbeBusinessService.py` — delete `_MaybeAutoMarkAudioCompleteAtTarget`
- `Features/AudioNormalization/Controllers/AudioCompletionController.py` — retarget operator override to new column (documentation only)
- Schema: `MediaFiles.AudioComplete_OperatorOverride BOOL NOT NULL DEFAULT FALSE` (idempotent migration)
- Docs: `Features/AudioNormalization/audio-normalization.feature.md` (C1 wording); `Features/WorkBucket/work-bucket.feature.md` (~12.6k backlog note); this file
- Contract tests: `Tests/Contract/TestAudioVerticalDialogBoostStrict.py`, `TestAudioCompleteReadsStillWork.py`, `TestOperatorOverrideDoesNotFlipCompliance.py`
- Live recompute run across full library

**Out (with reason):**
- **`MediaFiles.HasDialogBoostTrack BOOL` perf cache** — only add if RecomputeFor throughput becomes unacceptable. First measure, then decide (C12). Speculative optimization = YAGNI.
- **Dialog Boost track marker taxonomy overhaul** — current `title=Dialog Boost` marker is sufficient. Renaming or normalizing marker text is separate concern.
- **AudioComplete column removal** — column still carries LUFS-at-target metadata that downstream tooling reads (Activity dashboard, self-heal invariants). Decoupling from compliance is enough; removal is scope creep.
- **Retry/queue prioritization for the ~12k backlog** — existing `NextTranscodeBatch` handles pace. If overwhelming, throttle is a separate concern.
- **Deleting the ~50-line `AudioComplete` inference chain in EvaluateInitialAudioState** — trim what compliance path uses; the LUFS-metadata paths stay for their non-compliance readers.

## Status

**Phase:** COMPLETE
**Owner:** claude-opus-4-7
**Opened:** 2026-07-17
**Shipped:** 2026-08-13
**Domain policy locked:** 2026-07-17 (operator confirmed strict interpretation)

### Files

**Edit:**
- `Features/AudioNormalization/AudioVertical.py`
- `Features/AudioNormalization/Services/AudioStateService.py`
- `Features/AudioNormalization/Controllers/AudioCompletionController.py`
- `Features/FileReplacement/TranscodedOutputPlacement.py`
- `Features/MediaFiles/MediaFilesRepository.py`
- `Core/Models/MediaFileModel.py`
- `Features/AudioNormalization/audio-normalization.feature.md`
- `Features/WorkBucket/work-bucket.feature.md`

**Create:**
- `Scripts/SQLScripts/AddHasDialogBoostTrack_2026_08_13.py`
- `Scripts/SQLScripts/RewriteWorkBucketGeneratedColumn_2026_08_13.py`
- `Tests/Contract/TestAudioVerticalDialogBoostStrict.py`
- `Tests/Contract/TestAudioCompleteReadsStillWork.py`

**Delete:**
- `MediaProbeBusinessService._MaybeAutoMarkAudioCompleteAtTarget` method (~50 lines inside the file)

## Pre-flight

Same drain pattern as `mediafiles-uniqueness-owner`:

1. Verify zero in-flight attempts: `SELECT COUNT(*) FROM TranscodeAttempts WHERE Success IS NULL` = 0.
2. Pause fleet: `UPDATE Workers SET Status='Paused' WHERE WorkerName LIKE '%worker%'`.
3. Wait for `ActiveJobs` empty.
4. Stop I9 services + remote containers.
5. `pg_dump` snapshot.
6. Apply schema migration.
7. Deploy code (I9 source-tree, remote redeploy).
8. Restart services.
9. Run recompute + smoke tests.

## Smoke tests

### Compliance-flip verification

**C1. Three currently-compliant Dialog-Boost files.** Query: `SELECT mf.Id FROM MediaFiles mf JOIN TranscodeAttempts ta ON ta.MediaFileId=mf.Id WHERE mf.IsCompliant=TRUE AND ta.Success=TRUE AND ta.AudioTracksEmittedJson::text ILIKE '%Dialog Boost%' LIMIT 3`. Run RecomputeFor on those Ids. Assert `IsCompliant` stays TRUE.

**C2. Three currently-compliant NON-Dialog-Boost files.** Query: `SELECT mf.Id FROM MediaFiles mf WHERE mf.IsCompliant=TRUE AND NOT EXISTS (SELECT 1 FROM TranscodeAttempts ta WHERE ta.MediaFileId=mf.Id AND ta.Success=TRUE AND ta.AudioTracksEmittedJson::text ILIKE '%Dialog Boost%') LIMIT 3`. Run RecomputeFor. Assert `IsCompliant=FALSE`, `WorkBucket='AudioFix'`.

**C3. One live end-to-end.** Pick 1 file from C2's set. Enqueue. Watch full pipeline: encode → Dialog Boost track emitted → Replace → RecomputeFor. Assert final `IsCompliant=TRUE`, WorkBucket=None.

### Population sanity

**P1.** Post-recompute SQL: `SELECT COUNT(*) FROM MediaFiles WHERE IsCompliant=TRUE` returns ~1,481 (±5%). `WorkBucket='AudioFix'` count grows by ~12,000.

**P2.** Grep: `AudioVertical.py` mentions `AudioComplete` zero times (decoupling verified).

**P3.** Log tail 15 min post-restart: zero exceptions from `AudioVertical.Evaluate` or its callers.

## Rollback

`git revert <landing-commit>` on main; push; restart. Schema migration additive (`AudioComplete_OperatorOverride` column); leave in place OR `ALTER TABLE ... DROP COLUMN IF EXISTS`.

Trickier: post-recompute the library-wide compliance flags will have flipped for 12k files. Rollback restores the code but the flag state won't auto-revert. Two options at rollback time:
- Restore from `pg_dump` snapshot (full state revert).
- Run `AudioVertical.RecomputeFor` on the full library against reverted code (recomputes back to lenient state).

Atomic-commit discipline: land the whole directive as one commit so revert is one action.

## Cross-references

- `Features/AudioNormalization/audio-normalization.feature.md` — vertical criteria + Dialog Boost contract (C1 updated here)
- `Features/WorkBucket/work-bucket.feature.md` — WorkBucket derivation
- `.claude/directives/closed/2026-07-03-audio-dialog-boost-real.md` — Dialog Boost machinery landed
- `.claude/directives/closed/2026-06-22-compliance-symmetry.md` — three-vertical compliance shape
- `.claude/rules/db-is-authority.md` — DB owns compliance state
- `.claude/rules/fail-loud.md`
- `.claude/rules/feature-criteria.md` — five litmus tests
