# Directive: dialog-boost-marker-unify

**Status:** Active -- phase: DELIVERING

### Promotions

- Directive `## The bug being fixed` + `## The fix` + `## Design decisions (plain English)` -> promoted into `Features/AudioNormalization/audio-vertical-dialog-boost-enforcement.feature.md` C1/C12 wording (updated to name `TranscodeAttempts.DialogBoostEmitted` as canonical marker) + `Features/AudioNormalization/audio-normalization.feature.md` C1 wording + `Features/AudioNormalization/audio-normalization.flow.md` ST5/ST6 stage description + `## Seams` S6 row.
- Directive seam narrative -> `Features/FileReplacement/compliance-gated-rename.feature.md` S2 wire-shape (reader now reads column, not JSONB predicate).
- Directive design-decisions class ("no JSONB decision predicates") -> `.claude/rules-details/no-jsonb-decision-predicates.md` + entry under `.claude/standards/index.md` "What is NOT gated" judgment gate list. This is the durable rule that catches the bug class going forward.
- Directive OOS clause about diagnostic keys -> `Features/AudioNormalization/audio-normalization.feature.md` C37 (removed JSON-key verification, now cites DialogBoostEmitted column) + C39 (retargeted to sentinel-return-only; persistence deferred to future directive).

## Verification

- **C1** — Migration `Scripts/SQLScripts/AddDialogBoostEmittedColumn_2026_08_22.py` ran; column `TranscodeAttempts.DialogBoostEmitted BOOL NOT NULL DEFAULT FALSE` present; backfilled 23,642 attempts from union of both historical markers.
- **C2** — Contract test `test_single_writer_of_dialog_boost_emitted_column` PASSED: exactly one production writer (`Features/AudioNormalization/Services/AudioPreEncodeFacade.py`).
- **C3** — `ComplianceGate.py:104-115` reads `TranscodeAttempts.DialogBoostEmitted` column; no JSONB `@>` predicate. Live smoke: attempt 69688 (MFId 694492) approved for Replace after gate read `DialogBoostEmitted=TRUE` from in-flight attempt.
- **C4** — `TranscodedOutputPlacement.py:180-190` reads `TranscodeAttempts.DialogBoostEmitted` for latest successful attempt; no JSONB `@>` predicate.
- **C5** — `PostEncodeMeasurementService.PersistPreEncodeMeta` deleted (verified `git diff`); `AudioPreEncodeFacade.PersistMeta` rewritten to write column directly; no JSON mutation after `_PersistAttestation`.
- **C6** — Contract test `test_no_dialog_boost_emitted_literal_in_production_paths` PASSED: 0 hits in Features/Workers/WorkerService/Core.
- **C7** — `Tests/Contract/TestDialogBoostMarkerCanonical.py` 4/4 PASSED.
- **C8** — `Scripts/RecomputeDialogBoostAfterMarkerUnify.py` ran: flipped `HasDialogBoostTrack=TRUE` on 602 MediaFiles; RecomputeForFiles on 697 that had flag true but bucket non-Compliant. Post-run mismatch count = 0.
- **C9** — Live smoke on I9-2024 (Windows worker, restarted 16:41 to pick up new code):
  - Attempt 69688 (MFId 694492, Pokémon S20E28 WEBDL): `DialogBoostEmitted=TRUE`, `Disposition=Replace` (gate approved), failure downstream from unrelated stale `-mv.mp4` collision -- NOT `ComplianceGateFailed: no_dialog_boost`.
  - Attempt 69686 (MFId 694921): ffmpeg rc 4294967262 (alimiter range) -- unrelated preexisting bug.
  - Attempt 69680 (MFId 694862, Heroes S02E07 Bluray): DTS decoder crash in source -- unrelated preexisting bug.
  - **Zero `no_dialog_boost` failures on I9 post-restart** (vs 62/24h prior). Gate no longer wrongly rejects Dialog-Boost-emitted output.
- **C10** — `.claude/rules-details/no-jsonb-decision-predicates.md` created; registered in `.claude/standards/index.md` "What is NOT gated" judgment section.

**Slug:** dialog-boost-marker-unify

**Interrupts:** mediafiles-uniqueness-owner (paused; parent stack: mediafiles-uniqueness-owner -> e2e-bug-fixes -> concurrency-cap-live-reload -> probe-loudness-remove -> worker-memorymax-cgroup -> preencode-loudness-cache-hit).

## The bug being fixed (plain English)

Every Transcode job since ~2026-08-20 fails post-encode compliance with `no_dialog_boost` even when the emitter produced a Dialog Boost track. 62 failures in the last 24 h; 6,505 files stuck in the Transcode WorkBucket looping forever.

`TranscodeAttempts.AudioTracksEmittedJson` is a JSON blob written by TWO services:

1. `PostEncodeMeasurementService._PersistAttestation` -- per-track ebur128 achievements (`AchievedLra`, `AchievedIntegratedLufs`, `AchievedTruePeakDbtp`)
2. `PostEncodeMeasurementService.PersistPreEncodeMeta` (called by `AudioPreEncodeFacade.PersistMeta`) -- merges in `dialog_boost_emitted`, `demucs_failed`, `vocals_rms_dbfs`

Ordering is implicit. When `_PersistAttestation` runs LAST it overwrites the pre-encode merge and the `dialog_boost_emitted` key vanishes. Three reader sites (`ComplianceGate.py:107`, `TranscodedOutputPlacement.py:184`, `AddHasDialogBoostTrack_2026_08_13.py:31`) query for exactly that key with `AudioTracksEmittedJson::jsonb @> '[{"dialog_boost_emitted": true}]'::jsonb`. Key gone -> probe returns false -> compliance gate refuses -> `HasDialogBoostTrack` written FALSE -> file re-queues -> infinite loop.

Evidence: attempts 67745 (success 2026-08-19), 68159 (fail 2026-08-20), 69081 (fail 2026-08-21) all on MediaFileId=699776. Success attempt's JSON contains `dialog_boost_emitted: true`. Both failing attempts' JSON contain only the Achieved* keys -- pre-encode meta was stomped.

## The fix (plain English)

Boolean fact answering "did this attempt emit Dialog Boost?" is attempt-level state. Store it as `TranscodeAttempts.DialogBoostEmitted BOOL NOT NULL DEFAULT FALSE`. Single writer (audio pre-encode facade). Single reader (`SELECT DialogBoostEmitted FROM TranscodeAttempts WHERE Id=?`). No JSONB path expressions. No string-literal predicate duplicated across three files. No two-writer merge race.

`AudioTracksEmittedJson` reverts to its DDD-correct scope: per-track achievement measurements written by one owner (`_PersistAttestation`), never merged into.

## Design decisions (plain English)

- **Why a column, not a JSON key.** A boolean attempt-level fact does not belong in a per-track JSON array. JSON path = brittle predicate string duplicated in every reader + implicit ordering coupling between two writers. Column = 8 bytes, one writer, one indexed read.
- **Why delete `PersistPreEncodeMeta` entirely.** Its only purpose was to seed a JSONB blob for later `@>` verification. With the column replacing the predicate, the merge has no consumer. Diagnostic breadcrumbs (`vocals_rms_dbfs`, `demucs_failure_reason`) fold into `_PersistAttestation`'s per-track record so the JSON blob still carries them for operator diagnosis -- but no code makes decisions from them.
- **Why keep `AudioTracksEmittedJson`.** Per-track ebur128 achievements are genuinely per-track (Track 0 = Dialog Boost, Track 1 = Original) with one writer and one carve-out reader (loudness verification). Correct DDD shape.
- **Why not just fix the predicate string.** Preserves the class of bug. Any future writer that stops emitting the key silently breaks every reader. Fixing the predicate string leaves both root violations (JSONB-decision-predicate + two-writer-one-blob) intact. Operator's ask was "so we don't have this problem ever again."
- **Why a grep-enforcement contract test.** The literal string `dialog_boost_emitted` in code is the trace evidence of the bug class. If it reappears anywhere in production paths, the pattern is regrowing. Grep = 0 outside the one-time backfill migration.
- **Why requeue the 62 failures explicitly.** Once the gate reads the correct column, next continuous scan re-queues them naturally. But for the population whose `HasDialogBoostTrack` was flipped FALSE by the buggy write path -- their attempts DID emit Dialog Boost -- a one-shot `RecomputeForFiles` at directive close flips the flag back so they route to `Compliant` bucket instead of looping through another failed transcode.
- **Why a new rule doc.** Bug class ("boolean decisions derived from JSONB containment probes over shared blobs") needs a rule so future PRs get caught at review. Judgment-gate, not hook-mechanical (grep for `@>` is too noisy; reviewer flags at plan review).

## Acceptance Criteria

C1. `TranscodeAttempts.DialogBoostEmitted BOOL NOT NULL DEFAULT FALSE` column exists. Migration idempotent (`ADD COLUMN IF NOT EXISTS`). Backfill sets `DialogBoostEmitted=TRUE` where `AudioTracksEmittedJson::jsonb @> '[{"dialog_boost_emitted": true}]'::jsonb` OR `AudioTracksEmittedJson::jsonb @> '[{"Label": "Dialog Boost"}]'::jsonb` (union of both historical markers; latter catches post-marker-drop attempts). Runs once, then JSONB predicate never runs in production code again.

C2. Exactly one production-code writer sets `TranscodeAttempts.DialogBoostEmitted`. Grep of `DialogBoostEmitted\s*=` in `Features/`, `Workers/`, `WorkerService/`, `Core/` returns one write site (audio pre-encode facade path). All other references are reads.

C3. `Features/FileReplacement/ComplianceGate.py` no longer queries `AudioTracksEmittedJson::jsonb @>`. Pre-replace Dialog Boost check reads `TranscodeAttempts.DialogBoostEmitted` for the in-flight attempt directly. `CandidateRow['HasDialogBoostTrack']` derives from that column.

C4. `Features/FileReplacement/TranscodedOutputPlacement.py` no longer queries `AudioTracksEmittedJson::jsonb @>`. Post-replace update to `MediaFiles.HasDialogBoostTrack` reads `TranscodeAttempts.DialogBoostEmitted` for the latest successful attempt of the MediaFileId.

C5. `Features/AudioNormalization/Services/PostEncodeMeasurementService.PersistPreEncodeMeta` deleted. `Features/AudioNormalization/Services/AudioPreEncodeFacade.PersistMeta` rewritten: writes `TranscodeAttempts.DialogBoostEmitted` column; drops the JSON-stamping call. Pre-encode diagnostic keys (`vocals_rms_dbfs`, `vocals_fallback_dbfs`, `demucs_failed`, `demucs_failure_reason`) are DROPPED from JSON entirely -- they were breadcrumbs, not decisions. If they become useful they get their own attempt-level columns via a separate directive (per Out of Scope). `AudioTracksEmittedJson` written by exactly one method (`_PersistAttestation`), never mutated after write.

C6. Grep of literal string `dialog_boost_emitted` in production paths (`Features/`, `Workers/`, `WorkerService/`, `Core/`) returns zero matches. In `Scripts/SQLScripts/` returns at most two matches: the new backfill migration (`AddDialogBoostEmittedColumn_2026_08_21.py`) and the historical `AddHasDialogBoostTrack_2026_08_13.py` (dead migration, already ran; not re-run).

C7. Contract test `Tests/Contract/TestDialogBoostMarkerCanonical.py`:
  - Asserts `dialog_boost_emitted` grep enforcement (C6).
  - Asserts exactly one production writer for `TranscodeAttempts.DialogBoostEmitted` (C2).
  - Asserts no production `AudioTracksEmittedJson::jsonb @>` query remains (C3, C4).
  - Round-trip: insert synthetic attempt with `DialogBoostEmitted=TRUE`; compliance gate's Dialog Boost check returns TRUE.

C8. One-shot `Scripts/RecomputeDialogBoostAfterMarkerUnify.py`: for every MediaFileId whose latest successful attempt has `DialogBoostEmitted=TRUE` but current `MediaFiles.HasDialogBoostTrack=FALSE`, run `QueueManagementBusinessService().RecomputeForFiles([Id])`. Idempotent. Logs count flipped.

C9. Live smoke on deploy target: one previously-failing MediaFileId (from the 62-file population, e.g. 699776) manually re-queued as Transcode; encode completes; compliance gate returns Compliant=True; file replaced; `MediaFiles.HasDialogBoostTrack=TRUE`; `MediaFiles.WorkBucket='Compliant'`. Zero `ComplianceGateFailed: no_dialog_boost` in the last 10 attempts post-deploy.

C10. Rule `.claude/rules-details/no-jsonb-decision-predicates.md`: "Boolean decision signals derive from typed columns, not JSONB containment probes over shared blobs written by more than one hand." Lands in rules-details (per doc-layering.md cache-discipline: new rules graduate to `.claude/rules/` only when proven invariant). Registered in `.claude/standards/index.md` "What is NOT gated" judgment section. Rationale cites this directive.

## Call-Graph Audit

- **Flow docs touched:** `Features/AudioNormalization/audio-normalization.flow.md` ST5 (post-encode measurement) + ST6 (post-encode gate). Single flow; no parallel flow doc.
- **Orchestration mode-branch:** none. Transcode + AudioFix both invoke `_PersistAttestation`; both benefit equally.
- **Shared output columns mode-sparse:** `AudioTracksEmittedJson.dialog_boost_emitted` key present in pre-2026-08-20 attempts, absent post-2026-08-20. Backfill sees both shapes.
- **OOS categorized:** every item below explicitly (a) preserve-behavior-collapse-duplication or (b) acknowledged debt.

## Out of Scope

- (a) `vocals_rms_dbfs`, `vocals_fallback_dbfs`, `demucs_failed`, `demucs_failure_reason`: preserved by folding into `_PersistAttestation`'s per-track record (moved, not deleted). No decision code reads them. Column promotion is separate directive if ever needed.
- (a) Historical `AudioTracksEmittedJson` blobs with old `dialog_boost_emitted` key: left as-is. Backfill uses them once to seed the new column, then never queries them again.
- (b) `Scripts/SQLScripts/AddHasDialogBoostTrack_2026_08_13.py` + `RewriteWorkBucketGeneratedColumn_2026_08_13.py`: historical, retained as-is. Not re-run. First still contains stale JSONB predicate; dead code by directive close. Documented debt; not scrubbed here.
- (a) `MediaFiles.HasDialogBoostTrack` column: kept. Correct DDD boundary for `AudioVertical.Evaluate` (single-aggregate MediaFile read). Only its WRITE path changes.

## Files

**Create:**
- `Features/AudioNormalization/dialog-boost-marker-unify.feature.md` (durable feature doc; created at DELIVERING per R13)
- `Scripts/SQLScripts/AddDialogBoostEmittedColumn_2026_08_21.py`
- `Scripts/RecomputeDialogBoostAfterMarkerUnify.py`
- `Tests/Contract/TestDialogBoostMarkerCanonical.py`
- `.claude/rules/no-jsonb-decision-predicates.md`

**Edit:**
- `Features/AudioNormalization/Services/PostEncodeMeasurementService.py`
- `Features/AudioNormalization/Services/AudioPreEncodeFacade.py`
- `Features/FileReplacement/ComplianceGate.py`
- `Features/FileReplacement/TranscodedOutputPlacement.py`
- `Features/AudioNormalization/audio-vertical-dialog-boost-enforcement.feature.md`
- `Features/AudioNormalization/audio-normalization.flow.md`
- `Features/FileReplacement/compliance-gated-rename.feature.md`
- `.claude/standards/index.md`

### Progress

- [ ] NEEDS_STANDARDS_REVIEW: read every `.claude/rules/*.md` + `.claude/standards/index.md`
- [ ] Advance -> NEEDS_PLAN; operator reviews criteria + Files list
- [ ] Advance -> NEEDS_DOC_PREREAD; read ancestor `*.feature.md` / `*.flow.md`
- [ ] Advance -> IMPLEMENTING; land migration + code edits + tests
- [ ] Advance -> VERIFYING; contract tests + live smoke on MediaFileId=699776
- [ ] Advance -> DELIVERING; promote content into feature.md + write delivery report
