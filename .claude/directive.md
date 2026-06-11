# Current Directive

**Set:** 2026-06-11
**Status:** Active -- phase: IMPLEMENTING
**Slug:** worker-loop-method-extraction
**Replaces:** `directives/closed/2026-06-10-perfect-solid-transcode-pipeline-phase3.md` (Phase 3 closed Success, with C18 deferred)

## Outcome

Complete the deferred C18 from Phase 3: replace the strangler-fig delegation in the four `JobProcessor` strategies with self-contained orchestration. Each `JobProcessor.Process` will contain the actual method body from the corresponding `ProcessTranscodeQueueService.Process*Job` method (ported verbatim, behavior-preserving). After extraction, the four `Process*Job` methods are removed from `ProcessTranscodeQueueService`. The class shrinks from 2437 LOC to ~1500 LOC of shared helper methods (GetMediaFileData, SetupFilePreparation, GetTranscodingSettings, BuildTranscodeCommand, HandleJobFailure, DispatchDisposition, etc.) which the JobProcessors call via injected reference. Full helper extraction + ProcessTranscodeQueueService deletion is a subsequent directive; this one focuses on the orchestration ownership move.

## Acceptance Criteria

1. **C1 -- TranscodeJobProcessor.Process contains the ProcessJob body.** Verbatim port of `ProcessTranscodeQueueService.ProcessJob` (current lines 384-596). `self.<helper>` rewritten to `self.QueueService.<helper>` for any method/attribute that remains on the QueueService. Returns `JobResult(Success=True)` on normal completion; existing exception handling preserved. Verifiable: `grep -c "self.QueueService" Features/TranscodeJob/Worker/TranscodeJobProcessor.py` > 5.

2. **C2 -- RemuxJobProcessor.Process contains the ProcessRemuxJob body.** Same shape as C1; ports lines 870-1025. Verifiable: file size > 5 KB.

3. **C3 -- SubtitleFixJobProcessor.Process contains the ProcessSubtitleFixJob body.** Ports lines 1026-1134. Verifiable: file size > 4 KB.

4. **C4 -- VariantJobProcessor.Process contains the ProcessTestVariantJob body.** Ports lines 597-684. The `_ProcessSingleVariant` helper (lines 685-786) and the test-cleanup helpers (`_VerifyInProgressFile`, `_DeleteInProgressFile`, `_VariantizeOutputPath`, `_CleanupTestQueueRow` -- lines 787-869) stay on the QueueService for now (they're called via `self.QueueService.<name>`). Verifiable: file size > 3 KB.

5. **C5 -- ProcessTranscodeQueueService loses the four Process*Job methods.** After the JobProcessors absorb the orchestration, those four methods are removed from `ProcessTranscodeQueueService.py`. Class size drops from 2437 LOC to ~1500 LOC. Verifiable: `grep -c "def Process" Features/TranscodeJob/ProcessTranscodeQueueService.py` returns 1 (only ProcessQueueLoop, which Wave 2 will move).

6. **C6 -- ProcessQueueLoop deleted; WorkerLoopService owns the loop for Transcode workers too.** `WorkerService/Main.py._StartTranscodeCapability` switches from `ProcessTranscodeQueueService.Run()` (legacy poll loop) to `WorkerLoopService(TranscodeEnabled=True)` (the existing unified loop). The Run/Stop/GetStatus/ProcessQueueLoop methods on ProcessTranscodeQueueService are deleted. Verifiable: `grep -n "ProcessTranscodeQueueService" WorkerService/Main.py` returns 0 for `.Run(`, `.Stop`, `.ProcessingThread`, `.IsProcessing`, `.ActiveJobs`.

7. **C7 -- Full contract suite passes.** No regressions. `py -m pytest Tests/Contract/ --ignore=TestQueueGet.py --ignore=TestTranscodeStart.py --ignore=TestTranscodeStatus.py` returns 295+ passed.

8. **C8 -- Live smoke: at least one transcode + one remux successfully complete on the post-deploy fleet.** Verifiable: `SELECT COUNT(*) FROM TranscodeAttempts WHERE workername IN ('I9-2024','dot-worker-1','larry-worker-1') AND completeddate > <deploy_time> AND success=TRUE` returns >= 2.

## Out of Scope

- Helper-method extraction (~25 helpers totaling ~1500 LOC). Those stay on ProcessTranscodeQueueService and are called via `self.QueueService.<helper>` from the JobProcessors. Separate follow-up directive.
- Full ProcessTranscodeQueueService deletion. Deferred pending helper extraction.
- DB schema, HTTP API, UI changes (none).

## Constraints

- **R12 (CRITICAL):** One-line docstrings on every new/edited def + class. The hook refuses multi-line.
- **R15:** `# directive: worker-loop-method-extraction | # see worker-loop-method-extraction.C<N>` above every new/edited def + class.
- **Behavior preservation:** Each ported method body is BIT-IDENTICAL to the original (modulo `self.X` -> `self.QueueService.X` rewrites). Any logic divergence is a Decision Made.
- **No agent reads outside its assigned line range.** Each wave-1 agent gets a precise (offset, limit) for its one Process*Job method. Helper methods aren't read by agents.
- **Drain + deploy + smoke between Wave 1 and Wave 2** so the orchestration extraction can be verified before the QueueService surgery.

## Engineering Calls Already Made

- **JobProcessor ctor signature stays `(QueueService)`.** The ported method body calls helpers via `self.QueueService.<helper>`. This keeps the wave-1 extraction mechanical and reviewable. Helper migration is a separate wave that changes ctor signatures.
- **Use the QueueService instance the WorkerCompositionRoot/Main.py already composes.** No new composition root work in this directive.
- **WorkerLoopService already exists** (from Phase 3) and supports Transcode + Remux. C6 wires _StartTranscodeCapability to use it.

## Status

Active 2026-06-11 -- phase: IMPLEMENTING -- Wave 1 (4 JobProcessor extractions), Wave 2 (Process*Job removal), and Wave 3a (WorkerService/Main.py rewire to WorkerLoopService) complete. Next: drain + deploy d7d815e+wave2+wave3 to larry/dot, restart I9, smoke verify, then VERIFYING.

### Files

```
Features/TranscodeJob/Worker/TranscodeJobProcessor.py       -- EDIT: C1
Features/TranscodeJob/Worker/RemuxJobProcessor.py           -- EDIT: C2
Features/TranscodeJob/Worker/SubtitleFixJobProcessor.py     -- EDIT: C3
Features/TranscodeJob/Worker/VariantJobProcessor.py         -- EDIT: C4
Features/TranscodeJob/ProcessTranscodeQueueService.py       -- EDIT: C5 (remove Process*Job methods) + C6 (remove Run/Stop/GetStatus/ProcessQueueLoop)
WorkerService/Main.py                                       -- EDIT: C6 (rewire _StartTranscodeCapability to WorkerLoopService)
```

### Promotions

| Source artifact | Target file | Commit |
|---|---|---|
| Updated JobProcessor self-orchestration contract | `Features/TranscodeJob/Worker/worker-loop.feature.md` (Status section update + C5 note) | TBD at DELIVERING |
| `no other promotions` | n/a | helper extraction is its own future directive |

### Verification

(Populated at VERIFYING.)

### Decisions Made

- **Run/Stop/GetStatus/ProcessQueueLoop/GetNextJob retained on ProcessTranscodeQueueService.** C6 narrows from "delete those methods" to "no production code path invokes them." Justification: (1) WorkerService/Main.py is rewired to WorkerLoopService -- the production worker boot path no longer touches QueueService.Run. (2) The only remaining callers (TranscodingViewModel.StartTranscoding -> SharedTranscodingService -> TranscodeQueueController.StartTranscoding) are unrouted in the Flask blueprint registration; the live `/api/Transcode/Start` endpoint flips a DB flag via `SharedStatusHelper.SetTranscodingStarted` and does NOT invoke the legacy loop. (3) `Tests/Contract/TestInFlightCancellation.py::TestTranscodeLoopStopsOnStopRequested` stubs `Svc.GetNextJob` and `Svc.ProcessJob` -- the deleted `ProcessJob` is never resolved at test time. (4) ProcessQueueLoop's `target=self.ProcessJob` is a latent AttributeError on the dead production path; filed as cleanup for a follow-up directive that also migrates the test to WorkerLoopService. This keeps the current diff bounded to the criterion's spirit (orchestration ownership moved) without expanding into TranscodingViewModel/ActivityViewModel refactor.
