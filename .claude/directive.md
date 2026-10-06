# Current Directive

**Set:** 2026-10-06
**Status:** Active -- phase: IMPLEMENTING
**Slug:** label-decides-command
**Replaces:** `directives/closed/2026-10-06-tv-video-rule-tier1.md` (closed Success)

## Outcome

A job's label alone decides what ffmpeg does, and each stage is checked for the one thing it did. Transcode re-encodes video and copies audio. Remux copies both into mp4. AudioFix copies video and adds Dialog Boost. A finished transcode is kept even though it has no Dialog Boost yet; the file then sits in the Audio bucket. A failed attempt never replaces a file. The keep-the-good-half fallback, the pre-replace compliance check, and the unused Quick / SubtitleFix labels are gone. Directive 1 of 3 (then `auto-handoff`, `pipeline-doc-single-source`); approved plan `~/.claude/plans/we-have-to-simplify-refactored-hearth.md`.

## Acceptance Criteria

1. Every Transcode job's command re-encodes video and copies audio; every Remux job's copies both; every AudioFix job's copies video and re-encodes audio. Verify: over attempts after ship, `SELECT ProcessingMode, COUNT(*) FROM TranscodeAttempts` grouped by command shape shows exactly one shape per label.
2. A transcode whose output has no Dialog Boost track is kept: the file is replaced and lands in the Audio bucket. Verify: one live TV transcode -> `FileReplaced=TRUE`, `WorkBucket='AudioFix'`.
3. No attempt replaces a file unless it is recorded successful. Verify: `SELECT COUNT(*) FROM TranscodeAttempts WHERE Success IS FALSE AND FileReplaced IS TRUE AND AttemptDate > <ship>` = 0.
4. An AudioFix job that adds no Dialog Boost track fails and leaves the file untouched. Verify: contract test; `SELECT COUNT(*) ... WHERE ProcessingMode='AudioFix' AND FileReplaced IS TRUE AND DialogBoostEmitted IS NOT TRUE AND AttemptDate > <ship>` = 0.
5. A job that copies video proves it: video stream checksum of output equals source, else the job fails. Verify: contract test.
6. Audio the mp4 container cannot carry is converted to a plain compatible codec by the copy stages instead of failing the job. Verify: contract test on a `wmav2` source.
7. Only three job labels exist. Verify: `SELECT Name FROM ProcessingModes` returns Transcode, Remux, AudioFix.
8. Writing an attempt field the system does not know fails loudly. Verify: contract test.
9. After a file is placed, its Dialog Boost flag reflects the attempt that placed it. Verify: live AudioFix -> `HasDialogBoostTrack` equals that attempt's `DialogBoostEmitted`.

## Call-Graph Audit

- **Flow docs:** `transcode.flow.md` (D2, D3, D6, D13, ST6, ST9), `Features/AudioNormalization/audio-normalization.flow.md` (restates command-build shape + D13 routing), `Features/TranscodeQueue/media-tabs.flow.md` (stale `RecommendedMode` version of the same classification -> queue pipeline). The last two overlap the first; both are resolved in `pipeline-doc-single-source` (pointer / delete).
- **Orchestration mode branches found:** `JobProcessor.Process` pre-encode-failure branch and `_TryPartialFallback` (D13) -- deleted here. `FileReplacementBusinessService` `isRemux` / `RequiresProfileGates` branch (size guard + gate by label) -- gate half deleted here; size guard stays keyed on label, now truthful because label = command. `Strategy.HandleResult` (Transcode vs Remux handler) stays: it is the strategy hook.
- **Signal 5:** today compliance flags (data) choose which slot functions run and which verification runs is chosen by label -- two sources. After: label only.
- **Shared output columns sparse by mode:** `VideoSlotStrategy` empty for AudioFix / Remux attempts (strategies drop it); `DialogBoostEmitted` written only when pre-encode ran; `Disposition='Replace'` with `Success=FALSE`. First and third fixed here; second is correct by design after this change (only AudioFix runs pre-encode).
- **OOS categories:** below.

## Out of Scope

- (b) Automatic hand-off to the next stage; stuck-detection grace -> `auto-handoff`.
- (b) Deleting / rewriting the 53 conflicting doc files -> `pipeline-doc-single-source`. This directive edits only docs its code anchors point at.
- (b) Collapsing the three remaining strategy classes; `Success` still written by result handler + failure handler.
- (b) Repair of data left by the old bugs (unflagged `-mv` files, own outputs in Transcode bucket) -> `.claude/directives/backlog/_bucket-rules-phase-2.md`.
- (b) `AudioSlotOverride` / `ParentTranscodeAttemptId` columns remain in the DB, unread.

## Constraints

- Workers drained before deploy. No column drops.
- `ProcessingModes` row deletion only after confirming 0 queue rows carry those labels.

## Escalation Defaults

- Keep a stage's output vs re-check everything -> keep; each stage checks only its own product.
- Risk tolerance: medium.

## Engineering Calls Already Made

- Operator 2026-10-06: Transcode -> Audio; Remux -> Audio; Audio. Each stage keeps its result. Old file deleted when a stage's output is placed. Remux is container only. Uncopyable audio converted plainly. "Do not overengineer."
- Plan source is the existing `ProcessingModeMetadata` per-label plan fields.
- Uncopyable-audio test reuses `AudioComplianceRules.AcceptableAudioCodecsCsv`; decided per file, not per stream (16 affected files).
- `-mv` means "MediaVortex wrote this file"; naming unchanged.

## Status

### Files

```
Features/TranscodeJob/Emit/Plan.py                                   -- EDIT: plan from label
Features/TranscodeJob/ProcessingModeMetadata.py                      -- EDIT: Transcode/Remux audio Copy; drop Quick, SubtitleFix
Features/TranscodeJob/Emit/CommandComposer.py                        -- EDIT: plan from Job.ProcessingMode; no override
Features/TranscodeJob/Emit/Slots/AudioSlot.py                        -- EDIT: Copy converts uncopyable codec
Features/TranscodeJob/Worker/JobProcessor.py                         -- EDIT: delete D13 + pre-encode fallback
Features/TranscodeJob/Worker/PartialCompletion.py                    -- DELETE
Features/TranscodeJob/Worker/Strategies/TranscodeJobStrategy.py      -- EDIT: forward context
Features/TranscodeJob/Worker/Strategies/QuickJobStrategy.py          -- DELETE
Features/TranscodeJob/Worker/Strategies/SubtitleFixJobStrategy.py    -- DELETE
Features/TranscodeJob/ProcessTranscodeQueueService.py                -- EDIT: HandleRemuxResult fails on bad verify
Features/TranscodeJob/TranscodeJobRepository.py                      -- EDIT: unknown field raises
Features/TranscodeQueue/QueueManagementBusinessService.py            -- EDIT: delete candidate check + follow-up enqueue
Features/TranscodeQueue/TranscodeQueueRepository.py                  -- EDIT: stop mapping override columns
Features/TranscodeQueue/Models/TranscodeQueueModel.py                -- EDIT: drop override fields
Features/FileReplacement/ComplianceGate.py                           -- DELETE
Features/FileReplacement/FileReplacementBusinessService.py           -- EDIT: no gate plumbing
Features/FileReplacement/TranscodedOutputPlacement.py                -- EDIT: no gate; boost flag from this attempt
Features/FileReplacement/PostFlightProcessors/PostFlightRegistry.py  -- EDIT: three labels
Features/FileReplacement/PostFlightProcessors/SubtitleFixPostFlight.py -- DELETE
Features/QualityTesting/Disposition/ComplianceFailureRecorder.py     -- DELETE
Features/AudioNormalization/AudioNormalizationController.py          -- EDIT: stale gate reference
Composition/WorkerCompositionRoot.py, WorkerService/Main.py          -- EDIT: registry wiring
Scripts/SQLScripts/RetireQuickSubtitleFixModes_2026_10_06.py         -- CREATE
Scripts/Smoke/SmokePartialCompletion_2026_08_08.py, Scripts/Smoke/SmokePreEncodeFailureRoutesToD13_2026_09_01.py -- DELETE
Tests/Contract/TestLabelDecidesCommand.py                            -- CREATE
Tests/Contract/TestCommandComposer.py                                -- EDIT
Tests/Contract/TestComplianceGatePassFailOnly.py, TestComplianceGateLanguageOverride.py, TestPartialCompletion.py, TestPartialCompletionEndToEnd.py, TestPreEncodeFailureRoutesToD13.py, TestJobProcessorPreEncodeFailure.py, TestPlanFactoryFromComplianceState.py -- DELETE
Tests/Contract/failloud_baseline.json                                -- EDIT: drop deleted files
transcode.flow.md                                                    -- EDIT at DELIVERING: D2, D3, D6, D13
```

### Plan

Commit units (each: code + every caller + its tests in one commit):

1. **Plan from label.** `ProcessingModeMetadata` audio ops; `PlanFactory.FromProcessingMode`; `CommandComposer` uses it; `TranscodeJobStrategy` forwards context; `AudioSlot` Copy converts uncopyable codec; `JobProcessor` runs Demucs iff label's audio op is Reencode. Delete `FromComplianceState`, `TestPlanFactoryFromComplianceState`; update `TestCommandComposer`; add `TestLabelDecidesCommand` shape tests.
2. **Delete D13.** `JobProcessor` fallback branch + four helpers; `PartialCompletion.py`; `EnqueuePartialCompletionFollowup`; override fields in queue model + repository; `WithSlotForcedToCopy`; `PlanOverride`; D13 tests + smoke scripts.
3. **Delete the pre-replace check.** `ComplianceGate.py`, `EvaluateCandidateCompliance`, `_RowToMediaFileForCompliance`, `ComplianceFailureRecorder`, gate plumbing in `FileReplacementBusinessService` + `TranscodedOutputPlacement`; gate tests.
4. **Stage verification.** `HandleRemuxResult` fails on checksum mismatch or (AudioFix) missing boost, and stops swallowing; `HasDialogBoostTrack` from the placing attempt; `UpdateTranscodeAttempt` raises on unknown field.
5. **Three labels.** Delete Quick / SubtitleFix strategies, post-flight, wiring, metadata rows; `RetireQuickSubtitleFixModes` script.

Order 1 -> 3 -> 2 -> 4 -> 5 is forced: after unit 1 a transcode has no boost, so the gate (unit 3) must go before any deploy. Units 1-5 deploy together.

Seams changed (others referenced by existing `transcode.S*`):

| Seam | Producer | Wire shape | Consumer expects | Verification |
|---|---|---|---|---|
| Label -> plan | queue row `ProcessingMode TEXT` | one of Transcode / Remux / AudioFix | `PlanFactory.FromProcessingMode` -> `Plan(VideoOp, AudioOp, SubtitleOp, ContainerOp)`; unknown label raises | `TestLabelDecidesCommand` |
| Stage verify -> dispatch | `HandleRemuxResult` | checksum equal AND (label != AudioFix OR `DialogBoostEmitted`) | dispatch only when true; else `HandleJobFailure` | `TestLabelDecidesCommand` |
| Placement -> boost flag | `TranscodedOutputPlacement.Execute` | `TranscodeAttempts.DialogBoostEmitted BOOL` of the placing attempt | `MediaFiles.HasDialogBoostTrack` | live AudioFix |
| Attempt update | any caller | dict of column -> value | every key is a known column, else `ValueError` | `TestLabelDecidesCommand` |

### Promotions

### Verification

### Decisions Made
