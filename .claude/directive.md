# Directive: dialog-boost-marker-unify

**Status:** Closed

**Slug:** dialog-boost-marker-unify

**Interrupts:** mediafiles-uniqueness-owner (paused).

## Files

**Create:**
- `Scripts/SQLScripts/AddDialogBoostEmittedColumn_2026_08_22.py`
- `Scripts/RecomputeDialogBoostAfterMarkerUnify.py`
- `Tests/Contract/TestDialogBoostMarkerCanonical.py`
- `.claude/rules-details/no-jsonb-decision-predicates.md`

**Edit:**
- `Features/AudioNormalization/Services/PostEncodeMeasurementService.py`
- `Features/AudioNormalization/Services/AudioPreEncodeFacade.py`
- `Features/FileReplacement/ComplianceGate.py`
- `Features/FileReplacement/TranscodedOutputPlacement.py`
- `Features/AudioNormalization/audio-vertical-dialog-boost-enforcement.feature.md`
- `Features/AudioNormalization/audio-normalization.feature.md`
- `Features/AudioNormalization/audio-normalization.flow.md`
- `Features/FileReplacement/compliance-gated-rename.feature.md`
- `Tests/Contract/TestDemucsFailureSentinel.py`
- `.claude/standards/index.md`

### Promotions

- Directive bug + fix + design-decision narrative -> `Features/AudioNormalization/audio-vertical-dialog-boost-enforcement.feature.md` C1/C12 + `Features/AudioNormalization/audio-normalization.feature.md` C1 + `Features/AudioNormalization/audio-normalization.flow.md` ST5/ST6 + S6.
- Directive seam narrative -> `Features/FileReplacement/compliance-gated-rename.feature.md` S2.
- Directive design-decisions class -> `.claude/rules-details/no-jsonb-decision-predicates.md` + `.claude/standards/index.md` "What is NOT gated".
- Directive OOS clause about diagnostic keys -> `Features/AudioNormalization/audio-normalization.feature.md` C37 + C39.

### Delivery Report

- DIRECTIVE: unify Dialog Boost marker into a single typed column so the two-writer-one-blob failure that stuck 6,505 files in a Transcode-and-fail loop cannot recur.
- STATUS: Done. Verified end-to-end on I9 sha `fbf64d22`.
- WHAT SHIPPED:
  - `TranscodeAttempts.DialogBoostEmitted BOOL NOT NULL DEFAULT FALSE` column + idempotent migration + backfill from union of both historical markers (23,642 attempts).
  - Single writer: `AudioPreEncodeFacade.PersistMeta` -> `UPDATE TranscodeAttempts SET DialogBoostEmitted=<bool>`.
  - Two readers unified: `ComplianceGate.Evaluate` (in-flight attempt) + `TranscodedOutputPlacement.Execute` (latest successful attempt). Both `SELECT DialogBoostEmitted FROM TranscodeAttempts`. No JSONB predicates in production.
  - `PostEncodeMeasurementService.PersistPreEncodeMeta` deleted. `AudioTracksEmittedJson` reverts to single-writer / no-mutation.
  - One-shot recompute: flipped `MediaFiles.HasDialogBoostTrack=TRUE` on 602 stuck files; recomputed WorkBucket on 697.
  - Contract test greps the pattern that caused the bug (4/4 pass).
  - New judgment rule `.claude/rules-details/no-jsonb-decision-predicates.md` registered in standards index.
- HOW TO USE IT: no operator action. Next continuous scan naturally re-buckets remaining stuck files; new Transcode attempts approve/refuse correctly via the column.
- WHAT YOU NEED TO EXECUTE: `py deploy/deploy-fleet.py` to roll new code to dot/wakko/larry fleet (I9 already restarted for smoke). Fleet redeploy is deferred; recompute sweeps reconcile in the interim.
- CRITERIA VERIFICATION:
  - C1: migration ran; 23,642 attempts backfilled TRUE from union `dialog_boost_emitted:true` OR `Label:'Dialog Boost'`.
  - C2: contract test single-writer grep PASSED (`AudioPreEncodeFacade.py` only).
  - C3: gate reads column at `ComplianceGate.py:104-115`. Smoke: attempt 69688 `DialogBoostEmitted=TRUE` -> `Disposition=Replace` (gate approved).
  - C4: placement reads column at `TranscodedOutputPlacement.py:180-190`.
  - C5: `PersistPreEncodeMeta` deleted; JSON blob single-writer.
  - C6: production grep = 0.
  - C7: `Tests/Contract/TestDialogBoostMarkerCanonical.py` 4/4 pass.
  - C8: recompute flipped 602 files; post-run mismatch = 0.
  - C9: 12h post-restart -- **0 `no_dialog_boost` failures** (vs 62/24h prior). Overall success 95.2% across 227 attempts.
  - C10: rule + index entry in place.
- DECISIONS I MADE:
  - Deleted pre-encode diagnostic keys (`vocals_rms_dbfs`, `demucs_failed`, etc.) entirely instead of "folding into per-track record" (my initial C5 wording). No consumer once decision moves to column; keeping them was speculative. If operator diagnostics need SQL surface later, separate directive adds typed columns.
  - Rule landed in `.claude/rules-details/` not `.claude/rules/` (cache discipline: new rules graduate to always-loaded only when proven invariant).
  - Historical migration `AddHasDialogBoostTrack_2026_08_13.py` left with stale JSONB predicate as documented dead-code debt (already ran; not re-run).
  - Retargeted `audio-normalization.feature.md` C39 from "persisted failure signal" to "sentinel return" -- pipeline behavior preserved, JSON breadcrumb persistence deferred.
- KNOWN GAPS / DEFERRED:
  - Fleet redeploy pending (dot/wakko/larry still on old code). Recompute + I9 processing cover the population in the meantime.
  - Unrelated preexisting bugs surfaced during smoke (worth separate directives): stuck-detect ffmpeg-died class (6/12h), alimiter rc-34 (1), DTS decoder crash on source Bluray (1), stale `-mv.mp4` collision blocking rename (1).
