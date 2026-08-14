# Directive: compliance-gate-dialog-boost-signal

**Status:** Active -- phase: IMPLEMENTING

**Slug:** compliance-gate-dialog-boost-signal

**Interrupts:** audio-vertical-dialog-boost-enforcement (Closed 2026-08-13; introduced the gap this directive closes).

## Context

`AudioVertical.Evaluate` (post the previous directive) requires `Mf.HasDialogBoostTrack`. `ComplianceGate.Evaluate` builds a synthetic `CandidateRow` from ffprobe of the staged file and passes it to `EvaluateCandidateCompliance`. That CandidateRow never sets `HasDialogBoostTrack`, so every fresh Transcode/Reencode that legitimately emits Dialog Boost still fails the gate as `no_dialog_boost`. Wakko-worker-1: 100% failure rate across all Transcode attempts today. I9 + mv-w would hit the same the moment their Remux queue drains and they claim any Reencode work.

## Acceptance Criteria

- C1: `ComplianceGate.Evaluate` populates `CandidateRow['HasDialogBoostTrack']` from the in-flight `TranscodeAttempts.AudioTracksEmittedJson::jsonb @> '[{"dialog_boost_emitted": true}]'::jsonb` for `SourceMediaFileId`. Same predicate as `Scripts/SQLScripts/AddHasDialogBoostTrack_2026_08_13.py` backfill + `TranscodedOutputPlacement:172` writer-owns-cascade.
- C2: When encoder emits Dialog Boost, ComplianceGate returns `{'Compliant': True}` and rename proceeds.
- C3: When encoder does NOT emit Dialog Boost, ComplianceGate returns `{'Compliant': False, 'RefusalReason': 'non_compliant_AudioFix'}` (or equivalent from cascade). Behavior unchanged for that class.
- C4: Live smoke on wakko-worker-1: next Transcode attempt with Dialog Boost emitted completes the rename (no ComplianceGateFailed).
- C5: `compliance-gated-rename.feature.md` S2 wire shape updated to include `HasDialogBoostTrack` in the CandidateRow dict enumeration.

## Call-Graph Audit

1. Multiple flow docs -- clean. ComplianceGate participates in transcode.flow.md; no parallel gate flow.
2. Mode-branching at orchestration -- clean. Gate runs uniformly across all ProcessingModes.
3. Shared output columns sparsely populated -- root cause of THIS directive: `HasDialogBoostTrack` is sparsely populated on the synthetic CandidateRow (never set). Fix closes it.
4. Config-driven call-graph -- clean. No flag changes what functions run.
5. OOS explicit below.

## Out of Scope

- (a) Passing `TranscodeAttemptId` through the gate signature. Not needed -- `Success IS NULL AND MediaFileId=?` uniquely identifies the in-flight attempt per `claim-authority.md` invariant.
- (a) Contract test `TestComplianceGate.py` -- already flagged as TBD in feature doc; not owning that here. Live smoke covers C4.
- (b) Wakko Arc XPU Demucs reliability audit -- separate concern; if wakko's Demucs is inconsistent, that's a different failure class than THIS bug (which affects all workers).

## Files

**Edit:**
- `Features/FileReplacement/ComplianceGate.py` (add HasDialogBoostTrack read from in-flight attempt)
- `Features/FileReplacement/compliance-gated-rename.feature.md` (S2 wire shape amendment; DELIVERING)

## Status

Phase: NEEDS_STANDARDS_REVIEW
Opened: 2026-08-13
Owner: claude-opus-4-7
