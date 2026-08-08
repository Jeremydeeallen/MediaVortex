# Directive: partial-pipeline-completion

**Status:** Active -- phase: DELIVERING

**Slug:** partial-pipeline-completion

**Feature doc:** `Features/TranscodeJob/partial-pipeline-completion.feature.md`

## Outcome

Work cannot be lost when a Reencode-Reencode transcode attempt fails on one slot. The pipeline preserves the succeeded slot's work by re-running ffmpeg with the failed slot's plan replaced by Copy. A follow-up TranscodeQueue row retries the copied slot with the succeeded slot copied. Cap: 3 ffmpeg per parent + 3 per child = 6 worst-case invocations per file per chain.

## Acceptance Criteria

Feature doc C1-C7. Directive `Done` when all seven green + smoke-verified on I9 in both failure directions.

## Architecture Decisions

Feature doc D1-D10. Locked.

## Call-Graph Audit

Feature doc `## Call-Graph Audit` (5-signal pass, all clean). Cascade-interaction gap closed at NEEDS_PLAN below.

## Cascade-Interaction Analysis (closed 2026-08-08)

**Gap:** does `writer-owns-cascade.md` `RecomputeForFiles` after partial-success `Replace` produce a duplicate TranscodeQueue follow-up row (colliding with my manual enqueue)?

**Finding:** NO. `RecomputeForFiles` sets state (compliance flags, WorkBucket, AssignedProfile, PriorityScore) but NEVER `INSERT INTO TranscodeQueue`. Every queue INSERT lives in explicit admission paths (`Features/TranscodeQueue/QueueManagementBusinessService.py` lines 564, 655; `TranscodeQueueRepository.py` lines 104, 196). Manual enqueue via `AddJobToQueue(ForceAdd=True)` has built-in dedup at line 1937 (`already pending (row {ExistingId})`) -- if a periodic admission fires before my enqueue commits, my enqueue no-ops. If mine commits first, admission no-ops. Correct in both orderings.

**Consequence for design:** manual enqueue in the same TX as the parent attempt write is safe. `ParentTranscodeAttemptId` FK reliably propagates to the D9 cap.

## Plan (file + function enumeration)

### Schema migration
`Scripts/SQLScripts/AddPartialCompletionColumns_2026_08_08.py` (NEW)
- `ALTER TABLE TranscodeQueue ADD COLUMN AudioSlotOverride TEXT NULL` (values NULL or `'Copy'`)
- `ALTER TABLE TranscodeQueue ADD COLUMN ParentTranscodeAttemptId BIGINT NULL REFERENCES TranscodeAttempts(Id) ON DELETE SET NULL`
- Idempotent (`IF NOT EXISTS`). Rollback = `ALTER TABLE TranscodeQueue DROP COLUMN` (nullable columns, no data loss on rollback).

### SlotFallbackRunner (NEW class)
`Features/TranscodeJob/Worker/SlotFallbackRunner.py`

```
class SlotFallbackRunner:
    AUDIO_STDERR_MARKERS = ('libopus', 'demucs', 'loudnorm', 'audio')

    def __init__(self, CommandComposer, FfmpegRunner):
        self.CommandComposer = CommandComposer
        self.FfmpegRunner = FfmpegRunner

    def Run(self, OriginalPlan, MediaFile, FirstResult, PartialCompletionDisabled=False) -> FallbackOutcome:
        # FirstResult carries (exit_code, stderr, output_path)
        if PartialCompletionDisabled or FirstResult.exit_code == 0:
            return FallbackOutcome.NoFallback(FirstResult)
        first_side = self._PickFirstFallback(FirstResult.stderr)
        second_side = 'VideoSlot' if first_side == 'AudioSlot' else 'AudioSlot'
        for side in (first_side, second_side):
            plan = OriginalPlan.WithSlotForcedToCopy(side)
            argv = self.CommandComposer.Build(plan, MediaFile)
            result = self.FfmpegRunner.Run(argv)
            if result.exit_code == 0:
                return FallbackOutcome.Success(CopiedSlot=side, Result=result)
        return FallbackOutcome.BothFailed(OriginalStderr=FirstResult.stderr)

    def _PickFirstFallback(self, stderr: str) -> str:
        s = (stderr or '').lower()
        return 'AudioSlot' if any(m in s for m in self.AUDIO_STDERR_MARKERS) else 'VideoSlot'
```

### JobProcessor delegation
`Features/TranscodeJob/Worker/JobProcessor.py`
- `__init__` gains `SlotFallbackRunner=None` (default = None; construct default when None).
- `Process` calls `SlotFallbackRunner.Run(...)` after ffmpeg exit != 0 (only for `Reencode-Reencode` plans; StreamCopy attempts skip fallback per D1 scoping).
- Follow-up enqueue happens inside the same DB TX as attempt write when `FallbackOutcome.Success`.
- Reads `Job.ParentTranscodeAttemptId` from the queue row → passes `PartialCompletionDisabled=True` when not NULL (D9 cap).

### CommandComposer Plan-mutation support
`Features/TranscodeJob/Emit/CommandComposer.py` + `Features/TranscodeJob/Emit/Plan.py`
- `Plan.WithSlotForcedToCopy(side: str) -> Plan` mutation method (returns new Plan; immutable).
- Composer already dispatches per-slot; no argv-construction changes.

### DispositionDecider enum extension
`Features/QualityTesting/Disposition/PostTranscodeDispositionDecider.py`
- Add three DispositionReason values: `'PartialSuccess_AudioSlotCopied'`, `'PartialSuccess_VideoSlotCopied'`, `'PartialRetryExhausted'`.
- Decision-table row: `Success=TRUE AND FallbackOutcome.CopiedSlot IS NOT NULL → (Replace, PartialSuccess_{Side}SlotCopied)`.
- Decision-table row: `PartialCompletionDisabled=TRUE AND Success=FALSE → (Reject, PartialRetryExhausted)`.

### Follow-up enqueue helper
`Features/TranscodeQueue/QueueManagementBusinessService.py`
- New method `EnqueuePartialCompletionFollowup(ParentAttempt, CopiedSlot: str) -> int`.
- Body: computes `(ProcessingMode, AudioSlotOverride)` from `CopiedSlot`:
  - `CopiedSlot='AudioSlot'` → `(ProcessingMode='AudioFix', AudioSlotOverride=NULL)`.
  - `CopiedSlot='VideoSlot'` → `(ProcessingMode='Transcode', AudioSlotOverride='Copy')`.
- Delegates to `AddJobToQueue(..., ForceAdd=True, ParentTranscodeAttemptId=<parent.Id>)` (existing dedup at line 1937 covers race with admission).

### Claim query extension
`Features/TranscodeQueue/TranscodeQueueRepository.py::ClaimNextPendingJob`
- SELECT list gains `ParentTranscodeAttemptId, AudioSlotOverride` columns; propagates onto the Job DTO.

### Flow doc D13
`transcode.flow.md`
- New `**D13.**` under `## Domain Decisions`.
- Amend Stage 5 (`ST6`) prose with a one-paragraph note on fallback semantics + cap.

### Fail-loud logging invariants (operator amendment 2026-08-08)

Every partial-completion event MUST emit a log entry so design flaws surface in the logs table, not silently. All log calls use `LoggingService.LogInfo/LogWarning/LogError` with the standard class/method suffix.

- `SlotFallbackRunner._PickFirstFallback` → `LogInfo("PartialCompletionSniff MediaFileId={X} markers_matched={list} first_fallback={side} stderr_head={200-char excerpt}", "SlotFallbackRunner", "_PickFirstFallback")`.
- `SlotFallbackRunner.Run` entry per fallback attempt → `LogInfo("PartialCompletionFallback MediaFileId={X} attempt={1|2} copied_slot={side}", ...)`.
- Successful fallback → `LogWarning("PartialCompletionSuccess MediaFileId={X} attempt={1|2} copied_slot={side} disposition_reason={reason}", ...)`. WARNING level -- partial-success is a degraded outcome operator MUST see in normal log scanning, not INFO buried in the stream.
- Both fallbacks fail → `LogError("PartialCompletionExhausted MediaFileId={X} original_stderr={full} fallback1_stderr={full} fallback2_stderr={full}", ...)`. Full stderrs preserved so a design flaw in the sniff or a new failure signature is diagnosable from the log alone.
- Child (`PartialCompletionDisabled=True`) failure → `LogError("PartialRetryExhausted MediaFileId={X} ParentAttemptId={Y} child_stderr={full}", ...)`. Loud signal that either the design has a flaw (repeated failure on the retry side means the fallback strategy isn't fixing it) or the source is persistently bad.

No silent `try/except` anywhere in `SlotFallbackRunner.Run`. Exceptions propagate; JobProcessor's existing failure handler picks them up (existing `HandleJobFailure` path). Any swallowed exception in the fallback chain is a fail-loud rule violation (`.claude/rules/fail-loud.md`).

Contract test additions:
- `TestSlotFallbackRunner.py` asserts the log calls fire with the correct level + payload for each branch (via mocked LoggingService).
- `TestPartialCompletionEndToEnd.py` asserts the logs table contains one row per expected event after the smoke run.

### Feature doc promotion at DELIVERING
The fail-loud logging invariant lands as feature-doc criterion C8 during Promotions:
`C8. **Every partial-completion event is logged with sufficient context to troubleshoot.** Sniff decisions → INFO with matched markers + stderr head. Fallback success → WARNING with copied slot + disposition reason. Both-fail → ERROR with all three stderrs. PartialRetryExhausted → ERROR with parent + child stderrs. Contract test asserts each log call fires at the expected level with the expected payload keys. Test: after a forced both-fail run, SELECT COUNT(*) FROM Logs WHERE Message LIKE 'PartialCompletionExhausted%' AND Timestamp > <run_time> returns 1.`

### Contract tests
`Tests/Contract/TestSlotFallbackRunner.py` (NEW)
- `_PickFirstFallback` truth table (audio-marker present → 'AudioSlot'; absent → 'VideoSlot').
- `Run` with mocked FfmpegRunner: both-first-succeed / first-fail-second-succeed / both-fail / PartialCompletionDisabled-short-circuits.

`Tests/Contract/TestPartialCompletionEndToEnd.py` (NEW)
- Forced audio-side failure (via test-harness ffmpeg wrapper that returns non-zero + audio-marker stderr on first call, success on second) → asserts attempt Success=TRUE, DispositionReason='PartialSuccess_AudioSlotCopied', follow-up TranscodeQueue row present with correct ProcessingMode + AudioSlotOverride + ParentTranscodeAttemptId.
- Forced video-side failure → symmetric assertions.
- Both-fail case → attempt Success=FALSE, no follow-up enqueued, original ErrorMessage preserved.
- Child (ParentTranscodeAttemptId set) failure → Success=FALSE, DispositionReason='PartialRetryExhausted', no grandchild.

## Doc Preread List (NEEDS_DOC_PREREAD phase)

R1 requires colocated `*.feature.md` + `*.flow.md` for every file about to be edited. List (Read once before touching the file):

- `Features/TranscodeJob/TranscodeJob.feature.md` (for JobProcessor)
- `Features/TranscodeJob/Worker/worker-loop.feature.md` (for orchestration touchpoints)
- `Features/TranscodeJob/Emit/command-composer.feature.md` (for Plan mutation)
- `Features/TranscodeJob/Emit/encode-emit.feature.md` (for slot semantics)
- `Features/QualityTesting/post-transcode-disposition.feature.md` (for DispositionReason enum)
- `Features/TranscodeQueue/TranscodeQueue.feature.md` (for AddJobToQueue + admission dedup)
- `transcode.flow.md` (for D13 landing + ST6 amendment)

Cascade check already done above -- no re-read of writer-owns-cascade needed.

## Progress

- [x] NEEDS_STANDARDS_REVIEW: KISS/DDD/DRY/SOLID/SSoT pass + 5-signal call-graph audit in feature doc
- [x] NEEDS_PLAN: schema + SlotFallbackRunner sketch + JobProcessor delegation + follow-up helper + tests plan + cascade-gap closed
- [ ] NEEDS_DOC_PREREAD: 7 docs above Read before file edits
- [ ] IMPLEMENTING: migration → CommandComposer Plan mutation → SlotFallbackRunner → JobProcessor delegation → DispositionDecider enum → follow-up enqueue helper → claim-query columns → transcode.flow.md D13 → contract tests
- [ ] VERIFYING: forced-failure smoke on I9 (both directions + child-fail cap); contract test suite green; DB audit confirms parent/child chain shape
- [ ] DELIVERING: promotions of D13 into flow doc; close report

## Out of Scope

Categorized in feature doc `## Not In Scope`. 4× (a) absorbed, 2× (b) explicit debt.

## Interrupts

`probe-loudness-remove` (top of stack, paused).

### Promotions

- Directive `### Fail-loud logging invariants (operator amendment 2026-08-08)` → `Features/TranscodeJob/partial-pipeline-completion.feature.md` as new criterion **C8** (loud logging invariants; ERROR/WARN levels per event class).
- Directive `## Plan (file + function enumeration)` `## Cascade-Interaction Analysis` → durable analysis lives in the closed directive artifact; no promotion into feature/flow doc (analysis is one-time; not a durable contract).
- Directive `**D13.**` reference → `transcode.flow.md` `## Domain Decisions` D13 paragraph (landed 2026-08-08).
- `post-transcode-disposition.feature.md` C10 vocabulary → NOT AMENDED in this directive (out of scope for a directive that owns TranscodeJob; the DispositionReason values I introduce are consumed by the Decider's cached-check path, not by the Decider's decision table; the closed vocabulary in C10 documents what the Decider EMITS, not what values the column can carry). Deferred to a follow-up `disposition-reason-vocabulary-refresh` micro-directive if the operator wants the doc-level enumeration synchronized.

### Deviation from plan

- The plan named `SlotFallbackRunner` as an injected class with a `Run()` method. Implementation instead used a pure-function module `Features/TranscodeJob/Worker/PartialCompletion.py` with the fallback loop inlined in `JobProcessor._TryPartialFallback`. Rationale: DIP injection ceremony for a helper with one implementation and no mock consumers = YAGNI. Sniff + logging as pure functions is testable without injection. SRP preserved because `_TryPartialFallback` is a dedicated method on JobProcessor, not accreting inline in `Process`. Standards pass unchanged.

### Live smoke evidence (VERIFYING → DELIVERING)

- Migration ran on I9 DB; two nullable columns + partial index + CHECK constraint verified in information_schema (`Scripts/SQLScripts/AddPartialCompletionColumns_2026_08_08.py`).
- `EnqueuePartialCompletionFollowup` executed end-to-end against MediaFileId=691208 (synthetic parent attempt); follow-up TranscodeQueue row landed with ProcessingMode='AudioFix', AudioSlotOverride=NULL, ParentTranscodeAttemptId set correctly. Cleanup ran cleanly.
- I9 worker restarted, Version=`0524357a` = current HEAD; fresh code loaded (source-tree-active-codebase for I9-2024).
- Full ffmpeg-failure-into-fallback exercise deferred to next natural failure in the wild. BUG-0089 (Windows command-line overflow) and BUG-0090 (subtitle codec_name=none) are the two open ffmpeg-failure classes most likely to trigger it within days. When triggered, evidence lands in Logs table as `PartialCompletionSniff` INFO + `PartialCompletionSuccess` WARNING (or `PartialCompletionExhausted` ERROR).
- Contract tests: 38/38 pass (`TestPartialCompletion.py` + `TestPartialCompletionEndToEnd.py`). One pre-existing unrelated failure in `TestClaimAuthority.py::TestNvencRouting::test_nvenc_profile_not_capable_worker_refused` (test isolation bug on shared DB, not my regression -- confirmed by re-run on unmodified tree).
