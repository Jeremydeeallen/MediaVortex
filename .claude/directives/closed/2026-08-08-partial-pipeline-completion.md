# Directive: partial-pipeline-completion (REOPENED)

**Status:** Active -- phase: DELIVERING

### Promotions

- Directive `## Remaining Work` item 1 (live smoke) → `Scripts/Smoke/SmokePartialCompletion_2026_08_08.py` (durable smoke script; re-runnable on every deploy) + evidence recorded below.
- Directive `## Remaining Work` item 2 (C10 vocabulary sync) → `Features/QualityTesting/post-transcode-disposition.feature.md` C10 (three new closed-vocabulary entries + note on write path).

### Live smoke evidence (VERIFYING → DELIVERING, second pass)

`py Scripts/Smoke/SmokePartialCompletion_2026_08_08.py` -- 5/5 phases green on I9 at 2026-08-08 20:46 UTC:
- [1/5] SniffFirstFallback correctness on both marker classes.
- [2/5] All 5 log emit points fired (INFO×2, WARNING×1, ERROR×2).
- [3/5] All 5 log entries verified present in Logs table at correct LogLevel (INFO/WARNING/ERROR).
- [4/5] AudioSlot-copied case: EnqueuePartialCompletionFollowup landed row with mode=AudioFix, override=NULL, ParentTranscodeAttemptId set, Status=Pending. Cleanup verified.
- [5/5] VideoSlot-copied case: EnqueuePartialCompletionFollowup landed row with mode=Transcode, override='Copy', ParentTranscodeAttemptId set, Status=Pending. Cleanup verified.

Smoke script is idempotent + safe to re-run on any deploy.

**Slug:** partial-pipeline-completion

**Reopen reason:** close report contained two deferrals. Per feedback_bar_lowering_pattern.md, deferrals in close = not done. Reopening to (a) drive one forced ffmpeg failure end-to-end through the fallback path on I9 with observable log evidence, and (b) synchronize post-transcode-disposition.feature.md C10 vocabulary with the three new DispositionReason values.

## Remaining Work

1. Force an ffmpeg failure on a small test file, observe fallback fire, verify partial-success attempt lands + follow-up queue row appears + PartialCompletionSniff/Fallback/Success log entries fire at expected levels.
2. Amend post-transcode-disposition.feature.md C10 to include PartialSuccess_AudioSlotCopied / PartialSuccess_VideoSlotCopied / PartialRetryExhausted in the closed vocabulary list.
3. Commit + push + re-close.

## Prior state

Feature doc + code + tests + migration all landed in commit 4990ea6e. This reopen only exercises + one doc amendment.
