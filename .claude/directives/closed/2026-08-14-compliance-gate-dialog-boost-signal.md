# Directive: compliance-gate-dialog-boost-signal

**Status:** Closed

**Slug:** compliance-gate-dialog-boost-signal

**Interrupts:** audio-vertical-dialog-boost-enforcement (Closed 2026-08-13; introduced the gap this directive closes).

## Files

**Edit:**
- `Features/FileReplacement/ComplianceGate.py`
- `Features/TranscodeQueue/QueueManagementBusinessService.py` (root-cause: threaded HasDialogBoostTrack through `_RowToMediaFileForCompliance`)
- `Features/FileReplacement/TranscodedOutputPlacement.py` (mid-flight: widened cascade query to include in-flight attempt via `Success IS NULL OR Success = TRUE`)
- `Features/FileReplacement/compliance-gated-rename.feature.md` (S2 amendment)

### Promotions

- ComplianceGate CandidateRow now carries HasDialogBoostTrack read from in-flight TranscodeAttempts.AudioTracksEmittedJson (same predicate as backfill + writer-owns-cascade) -> `Features/FileReplacement/compliance-gated-rename.feature.md` S2.
- Root-cause row-mapper fix (`_RowToMediaFileForCompliance`) threads HasDialogBoostTrack through to MediaFileModel -- pattern-parallel to MediaFilesRepository._MapRowToMediaFile.
- Cascade write query in TranscodedOutputPlacement widened to include in-flight attempt (Success IS NULL OR Success = TRUE) so the current attempt's Dialog Boost signal fires the flag before RecomputeForFiles reads it.

### Delivery Report

- DIRECTIVE: fix wakko-worker-1 100% ComplianceGateFailed:no_dialog_boost failure caused by parent directive's HasDialogBoostTrack gap in the ComplianceGate row-mapper.
- STATUS: Done. Live-verified.
- WHAT SHIPPED: 3 code fixes across ComplianceGate.py + QueueManagementBusinessService.py + TranscodedOutputPlacement.py + feature-doc S2 amendment. Backfilled 480 stale HasDialogBoostTrack rows + recomputed 497 AudioCompliant.
- HOW TO USE IT: no operator action required. Reencode-path attempts now cascade correctly: ComplianceGate accepts Dialog-Boost outputs -> TranscodedOutputPlacement flips HasDialogBoostTrack=TRUE -> RecomputeForFiles flips AudioCompliant=TRUE -> WorkBucket=Compliant.
- WHAT YOU NEED TO EXECUTE: nothing. Fleet already redeployed to sha 562a4f5491.
- CRITERIA VERIFICATION:
  - C1 + C2 verified live: attempts 61758 (wakko) + 61759 (dot) post-restart, both Reencode + Dialog Boost emitted, both Success=TRUE + HasDialogBoostTrack=TRUE + AudioCompliant=TRUE + WorkBucket=Compliant.
  - C3 (no-boost outputs still refuse) not exercised in verification (no such attempts observed post-fix); behavior structurally preserved.
  - C4 wakko end-to-end Transcode pass confirmed.
  - C5 feature doc S2 amended.
- DECISIONS I MADE:
  - Two mid-flight scope expansions (Amendments A/B in-directive): QMBS row-mapper fix, TranscodedOutputPlacement cascade-query widening. Neither could be omitted without leaving the fix chain incomplete.
- KNOWN GAPS / DEFERRED:
  - Wakko Arc XPU Demucs reliability audit -- separate concern.
  - Contract test TestComplianceGate.py -- still deferred; live smoke covers.
