# Partial Pipeline Completion

**Slug:** partial-pipeline-completion

## Interrupts: probe-loudness-remove

## What It Does

A transcode attempt today runs one ffmpeg process with a combined plan (video encode + audio encode). If either side raises, ffmpeg exits non-zero, the whole attempt is `Success=False`, the 20 min of work is lost, and the retry starts from scratch.

Domain rule (operator, 2026-08-08): work cannot be lost. Video-slot failure must not lose the audio-slot work; audio-slot failure must not lose the video-slot work.

Solution: on ffmpeg failure, try up to two ordered fallbacks -- each mutates the Plan to replace one Reencode slot with Copy and re-invokes ffmpeg. First fallback ordering picked from a one-line stderr sniff (`libopus|Demucs|loudnorm|audio` → audio-copy first, else video-copy first). If either fallback succeeds, the attempt lands `Success=TRUE`, the output file is placed, and a follow-up TranscodeQueue row is enqueued that retries the slot that had to be copied. Max 3 ffmpeg invocations per attempt (original + 2 fallbacks). No new pipeline stages. No intermediate files. No taxonomy classifier.

## Architecture Decisions (D1-D10)

**D1. "Slot" is the domain term (aligns with `transcode.flow.md` D2).**
Video-slot sub-op = the Reencode video slot (profile-driven encoder args). Audio-slot sub-op = the Reencode audio slot (Demucs + Dialog Boost + loudnorm + libopus emit). Container slot and subtitle slot are always Copy/Preserve today and are not partitioned. If a future third slot becomes non-trivial, it becomes a third axis under the same pattern (add one row to the sniff-hint list + one new DispositionReason value).

**D2. One ffmpeg process per successful attempt; up to two fallbacks on failure.**
Cap: 3 ffmpeg invocations per `TranscodeAttempts` row. No two-pass persistent architecture, no intermediate `.m4v` files, no mux stage. Each fallback re-reads source from disk.

**D3. Intermediate state between passes = none.**
The first pass's failed `.inprogress` is deleted before any fallback runs. Each fallback writes its own `.inprogress`. Zero new state to store.

**D4. No new `Disposition` enum value.**
Reuse `Replace`. Two new `DispositionReason` values distinguish partial-success: `'PartialSuccess_AudioSlotCopied'` (video Reencode succeeded, audio fell back to Copy) or `'PartialSuccess_VideoSlotCopied'` (audio Reencode succeeded, video fell back to Copy). Enum extension only.

**D5. One follow-up TranscodeQueue row per partial-success parent, enqueued in the same DB transaction as the parent attempt write.**
Follow-up `ProcessingMode` = `'AudioFix'` when audio was the copied slot, or `'Transcode'` + `AudioSlotOverride='Copy'` when video was the copied slot. Follow-up children cannot themselves partial-complete (see D9).

**D6. No `/Operations` UI card added.**
The two new `DispositionReason` values flow through the existing dispositions rendering surface automatically. If observability tightens later, that is a separate directive.

**D7. No new `ProcessingMode` enum.**
`AudioFix` already exists. For the video-retry follow-up, add one nullable `TranscodeQueue.AudioSlotOverride TEXT` column (values NULL or `'Copy'`). One column, zero new mode + strategy plumbing.

**D8. Fallback ordering is decided by a one-line stderr sniff, not a taxonomy classifier.**
`SlotFallbackRunner._PickFirstFallback(stderr)` returns `'AudioSlot'` if stderr contains any of `libopus | Demucs | loudnorm | audio` (case-insensitive substring match), else `'VideoSlot'`. Wrong ordering costs one extra ffmpeg run, never a wrong outcome (the second fallback catches whichever slot the sniff missed). No pattern-list to maintain, no `Ambiguous` branch, no unknown-error handling. If both fallbacks fail, attempt lands `Success=FALSE` with the original error preserved.

**D9. Infinite-retry cap.**
Follow-up TranscodeQueue rows carry `ParentTranscodeAttemptId BIGINT NULL` FK to the attempt that generated them. When a claim resolves to a row where `ParentTranscodeAttemptId IS NOT NULL`, the JobProcessor runs with `PartialCompletionDisabled=TRUE`. Any ffmpeg failure during the child lands `Success=FALSE` with `DispositionReason='PartialRetryExhausted'`. One partial-completion per parent chain, ever.

**D10. `-c:v copy` fallback implicitly fixes container-side non-compliance.**
`ffmpeg -c:v copy -f mp4` = container remux with the source video stream. Output ends `.mp4` regardless of source container. `ContainerCompliant` flips TRUE on the resulting output. No separate branch needed.

## Scope

- `Features/TranscodeJob/Worker/JobProcessor.py` (delegate fallback loop to injected runner)
- `Features/TranscodeJob/Worker/SlotFallbackRunner.py` (NEW ~40 lines: sniff + ordered fallbacks + Plan mutation)
- `Features/TranscodeJob/Emit/CommandComposer.py` (accept `AudioSlotOverride` / `VideoSlotOverride` on the Plan)
- `Features/QualityTesting/Disposition/PostTranscodeDispositionDecider.py` (two new `DispositionReason` values + `PartialRetryExhausted`)
- `Features/TranscodeQueue/QueueManagementBusinessService.py` (follow-up enqueue helper reuses `AddJobToQueue(..., ForceAdd=True)`)
- `Scripts/SQLScripts/AddPartialCompletionColumns_2026_08_08.py` (NEW: add `TranscodeQueue.AudioSlotOverride TEXT NULL` + `TranscodeQueue.ParentTranscodeAttemptId BIGINT NULL`)
- `transcode.flow.md` (D13 + ST6 amendment paragraph)
- `Tests/Contract/TestSlotFallbackRunner.py` (NEW: sniff correctness + ordering + Plan mutation)
- `Tests/Contract/TestPartialCompletionEndToEnd.py` (NEW: forced-failure both directions + child-fail cap)

## Not In Scope

- `/Operations` card / dashboard / filter -- **(a) absorbed**: existing DispositionReason surface picks up new values automatically.
- `VideoFix` ProcessingMode enum value -- **(a) absorbed** via `AudioSlotOverride` column.
- Per-slot status columns on TranscodeAttempts -- **(a) absorbed**: DispositionReason IS the slot status.
- Two-pass persistent architecture with intermediate files -- **(a) absorbed** via single-pass with fallback re-invocation.
- Multi-fallback beyond 2 attempts -- **(b) explicit debt**: cap = 2 fallbacks; further retry requires manual operator enqueue.
- Backfill of historical `Success=FALSE` attempts -- **(b) explicit debt**: historical attempts stay `Success=FALSE`; no retroactive reclassification.

## Success Criteria

C1. **Fallback fires on ffmpeg failure with sniff-picked ordering.** When ffmpeg exits non-zero and stderr contains any of `libopus|Demucs|loudnorm|audio` (case-insensitive), the orchestrator invokes ffmpeg with the Plan mutated by `AudioSlotOverride='Copy'` (audio filter chain replaced by `-map 0:a -c:a copy`) as the FIRST fallback. When stderr contains none of those, the FIRST fallback is `VideoSlotOverride='Copy'` (video encoder args replaced by `-c:v copy`). Test: `TestSlotFallbackRunner.py` asserts sniff → ordering table.

C2. **Second fallback runs when first fails.** If the first fallback ffmpeg also exits non-zero, the orchestrator invokes the OPPOSITE Copy-override as a second fallback. If it succeeds, attempt lands `Success=TRUE` with the corresponding DispositionReason. Test: forced failure of first fallback + success of second → attempt Success=TRUE with the second-fallback's DispositionReason.

C3. **Cap at 3 ffmpeg invocations per attempt.** Both fallbacks failing lands `Success=FALSE` with the original ffmpeg stderr in `ErrorMessage` (not overwritten by fallback errors). Test: force all 3 to fail; observe `TranscodeAttempts.ErrorMessage` = original stderr, no 4th ffmpeg subprocess spawned.

C4. **Partial-success attempts land Success=TRUE with correct DispositionReason.** After a successful fallback, `TranscodeAttempts.(Success, Disposition, DispositionReason) = (TRUE, 'Replace', 'PartialSuccess_AudioSlotCopied')` when audio was copied, or `(TRUE, 'Replace', 'PartialSuccess_VideoSlotCopied')` when video was copied. `MediaFiles.TranscodedByMediaVortex=TRUE` set. Output file placed via existing FileReplacement path. Test: `SELECT Success, Disposition, DispositionReason FROM TranscodeAttempts WHERE Id=<forced>` returns expected tuple; ffprobe of output confirms which slot was copied.

C5. **Follow-up TranscodeQueue row auto-enqueued in the same TX as the parent attempt write.** For `PartialSuccess_AudioSlotCopied`, the follow-up row is `(MediaFileId=<same>, ProcessingMode='AudioFix', ParentTranscodeAttemptId=<parent.Id>, AudioSlotOverride=NULL)`. For `PartialSuccess_VideoSlotCopied`, follow-up is `(MediaFileId, ProcessingMode='Transcode', ParentTranscodeAttemptId=<parent.Id>, AudioSlotOverride='Copy')`. A parent attempt without its follow-up is impossible. Test: `SELECT COUNT(*) FROM TranscodeQueue WHERE ParentTranscodeAttemptId=<parent.Id>` returns 1 within the transaction commit.

C6. **Follow-up child cannot itself partial-complete (D9 cap).** When a queue row is claimed with `ParentTranscodeAttemptId IS NOT NULL`, the JobProcessor runs with `PartialCompletionDisabled=TRUE`. Any ffmpeg failure lands `Success=FALSE, DispositionReason='PartialRetryExhausted'`. No further follow-up enqueued. Test: force child failure; observe expected DispositionReason and zero grandchildren.

C8. **Every partial-completion event is logged with sufficient context to troubleshoot design flaws.** Sniff decisions log `PartialCompletionSniff` at INFO with matched markers list + first-fallback side + 200-char stderr head. Every fallback attempt logs `PartialCompletionFallback` at INFO with attempt number + copied slot. Fallback success logs `PartialCompletionSuccess` at WARNING (not INFO -- partial-success is a degraded outcome operator MUST see in normal log scanning) with copied slot + DispositionReason. Both fallbacks failing logs `PartialCompletionExhausted` at ERROR with all three stderrs (original + fallback1 + fallback2). Child (`PartialCompletionDisabled=True`) failure logs `PartialRetryExhausted` at ERROR with parent attempt id + child stderr. No silent try/except anywhere in `_TryPartialFallback`. Contract test asserts each log call fires at the expected level with the expected payload keys via `unittest.mock.patch('Features.TranscodeJob.Worker.PartialCompletion.LoggingService')`. Test: after a forced both-fail run, `SELECT COUNT(*) FROM Logs WHERE Message LIKE 'PartialCompletionExhausted%' AND Timestamp > <run_time>` returns 1.

C7. **Domain decision D13 lands in `transcode.flow.md`.** New paragraph under `## Domain Decisions`: `**D13. Slot-independence fallback.** On ffmpeg failure inside a Reencode-Reencode attempt, up to two fallback ffmpeg invocations run with one Reencode slot replaced by Copy each time (order picked by a one-line stderr sniff for audio-side markers). Successful fallback lands Success=TRUE, DispositionReason='PartialSuccess_{Audio,Video}SlotCopied', and enqueues one follow-up TranscodeQueue row that retries the copied slot. Follow-up children cannot themselves partial-complete; child failure lands DispositionReason='PartialRetryExhausted'. Cap = 3 ffmpeg per parent + 3 per child = 6 invocations worst-case per file per chain.` Test: `grep -n '\*\*D13\*\*' transcode.flow.md` returns one hit; paragraph matches.

## Workflows

| # | Operator perceives | Surface | Handler | Backing code |
|---|---|---|---|---|
| W1 | File queued for transcode; audio-slot fails; file lands with source audio; AudioFix follow-up visible in queue | `/Work` → `Queue` | claim + JobProcessor + SlotFallbackRunner + follow-up enqueue | `Features/TranscodeJob/Worker/JobProcessor.py` |
| W2 | See partial-success attempts on existing dispositions table | `/Operations` → attempts | `GET /api/Operations/Snapshot` | `Features/Activity/ActivityController.py` |
| W3 | Follow-up AudioFix runs against video-copied output; audio re-encoded; file replaced again with full audio | (automatic) | claim loop | `Features/TranscodeJob/Worker/WorkerLoopService.py` |

## Seams

| ID | Seam | Producer | Wire shape | Consumer expects | Verification |
|---|---|---|---|---|---|
| S1 | JobProcessor → SlotFallbackRunner | JobProcessor on ffmpeg exit != 0 | (Plan, ffmpeg stderr TEXT last 4KB, `PartialCompletionDisabled: bool`) | `SlotFallbackRunner.Run(...) -> AttemptOutcome{Success, DispositionReason, FallbackSlot?}` | `TestSlotFallbackRunner.py` |
| S2 | SlotFallbackRunner → CommandComposer | Mutated Plan with one slot forced to Copy | `Plan(VideoSlot=Copy|Reencode, AudioSlot=Copy|Reencode, ...)` | `CommandComposer.Build(plan)` returns ffmpeg argv | `TestPartialCompletionEndToEnd.py` |
| S3 | JobProcessor → TranscodeAttempts + TranscodeQueue (one TX) | orchestrator on partial-success | attempts row (Success=TRUE, DispositionReason set) + queue row (ParentTranscodeAttemptId, AudioSlotOverride) | `WorkerLoopService.ClaimNext` picks up follow-up | `SELECT ... WHERE ParentTranscodeAttemptId=?` returns 1 |
| S4 | Follow-up claim → JobProcessor with partial-disabled | claim query on row where `ParentTranscodeAttemptId IS NOT NULL` | `PartialCompletionDisabled=TRUE` flag | any failure lands `Success=FALSE, DispositionReason='PartialRetryExhausted'` | `TestPartialCompletionEndToEnd.py` child-fail case |
| S5 | Follow-up completion → MediaFiles compliance recompute | AudioFix follow-up success | `MediaFiles.AudioCompliant=TRUE` after audio re-encoded | existing `RecomputeForFiles([MediaFileId])` cascade (writer-owns-cascade rule) | `TestPartialCompletionEndToEnd.py` end state assertion |

## Call-Graph Audit

Per `.claude/rules/call-graph-audit.md`. Required to advance NEEDS_STANDARDS_REVIEW → NEEDS_PLAN.

**Signal 1 — Multiple flow docs for one conceptual op:** NO. Feature stays within `transcode.flow.md`. AudioFix follow-up is already covered by ST5. No new flow doc created; no existing flow doc split.

**Signal 2 — Orchestration-level mode-branching:** NO. The fallback loop is a **runtime conditional on exit-code data** (`if ffmpeg_rc != 0: try fallback`), not an enum-mode branch. Same JobProcessor → same CommandComposer → same ffmpeg subprocess call graph regardless of first-pass outcome. Only Plan **values** differ across invocations; call graph **shape** is stable.

**Signal 3 — Shared output columns sparsely populated:** `TranscodeQueue.ParentTranscodeAttemptId` and `TranscodeQueue.AudioSlotOverride` are both NULL on ~all rows -- only populated for partial-completion follow-ups. Intentional. Contract: NULL semantics = "not a partial-completion chain; use default JobProcessor behavior." No existing consumer misinterprets NULL (verified by grepping the tree at NEEDS_PLAN and confirming no `COALESCE(ParentTranscodeAttemptId, ...)` or `AudioSlotOverride = ''` compares exist).

**Signal 4 — OOS ambiguity:** every `## Not In Scope` item categorized (a) absorbed or (b) explicit debt. Two (b) items acknowledged: cap = 2 fallbacks (further retry manual), no historical backfill.

**Signal 5 — Config-driven call-graph shape:** NO. No config toggle changes call graph. Fallback fires from ffmpeg exit code (data), not settings. Turning off partial-completion would require deleting the whole `SlotFallbackRunner.Run` call, not flipping a flag.

**Recurring-failure guard:** does this directive land cleanly atop a divergent pipeline? Checked: the transcode pipeline is unified under `JobProcessor.Process` per `transcode-worker-unification` (2026-06-28). No parallel processor classes, no `remux.flow.md`. Safe.

## Status

Active -- phase: NEEDS_STANDARDS_REVIEW (Call-Graph Audit complete above; ready to advance to NEEDS_PLAN on criteria approval)

### Progress

- [x] NEEDS_STANDARDS_REVIEW: call-graph audit landed; KISS/DDD/DRY/SOLID/SSoT pass documented above
- [ ] NEEDS_PLAN: files-touched enumeration; SlotFallbackRunner class sketch; migration + rollback plan for the two nullable columns
- [ ] NEEDS_DOC_PREREAD: colocated feature/flow doc list per file touched
- [ ] IMPLEMENTING: migration → CommandComposer flag → SlotFallbackRunner → JobProcessor delegation → Decider enum values → follow-up enqueue helper → transcode.flow.md D13 → contract tests
- [ ] VERIFYING: forced-failure smoke on I9 (both directions + child-fail cap); classifier test suite green; DB audit confirms parent/child chain shape
- [ ] DELIVERING: promotions of D13 into flow doc; close report

## Files

Populated at NEEDS_PLAN. Preview matches `## Scope` above.
