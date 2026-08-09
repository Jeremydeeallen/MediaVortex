# Directive: partial-pipeline-completion (REOPENED)

**Status:** Closed

**Slug:** partial-pipeline-completion

### Promotions

- Directive `## Remaining Work` item 1 (live smoke) → `Scripts/Smoke/SmokePartialCompletion_2026_08_08.py` (durable smoke script; re-runnable on every deploy).
- Directive `## Remaining Work` item 2 (C10 vocabulary sync) → `Features/QualityTesting/post-transcode-disposition.feature.md` C10 (three new closed-vocabulary entries + note on write path).

### Delivery Report

- DIRECTIVE: reopen to (a) drive one forced ffmpeg failure end-to-end through the partial-completion fallback path with observable log evidence, and (b) synchronize `post-transcode-disposition.feature.md` C10 vocabulary with the three new DispositionReason values.
- STATUS: Done.
- WHAT SHIPPED:
  - `Scripts/Smoke/SmokePartialCompletion_2026_08_08.py` -- 5/5 phase live-drive smoke against I9 (SniffFirstFallback correctness, 5 log emit points, log-table verification at correct LogLevel, AudioSlot-copied followup enqueue, VideoSlot-copied followup enqueue). Idempotent + re-runnable per deploy.
  - `Features/QualityTesting/post-transcode-disposition.feature.md` C10 -- three additions to closed-vocabulary: `PartialSuccess_AudioSlotCopied`, `PartialSuccess_VideoSlotCopied`, `PartialRetryExhausted`.
- HOW TO USE IT: `py Scripts/Smoke/SmokePartialCompletion_2026_08_08.py` on any host with DB connectivity re-verifies the partial-completion fallback + logging + follow-up-enqueue path end-to-end.
- WHAT YOU NEED TO EXECUTE: nothing outstanding.
- CRITERIA VERIFICATION:
  - Item 1 (live smoke): `py Scripts/Smoke/SmokePartialCompletion_2026_08_08.py` returned 5/5 green at 2026-08-08 20:46 UTC on I9. Log-table SELECT confirmed all 5 entries present at INFO/WARNING/ERROR as expected. Followup rows landed for both AudioSlot-copied (mode=AudioFix, override=NULL) and VideoSlot-copied (mode=Transcode, override='Copy') cases with ParentTranscodeAttemptId + Status=Pending.
  - Item 2 (C10 sync): grep of C10 section confirms the three new vocabulary entries present.
- DECISIONS I MADE: promoted the exercise script to `Scripts/Smoke/` (durable, re-runnable) rather than a one-shot ad-hoc invocation, so future deploys can re-verify the fallback path without recreating fixtures.
- KNOWN GAPS / DEFERRED: none.
