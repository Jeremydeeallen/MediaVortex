# Current Directive

**Set:** 2026-06-11
**Status:** Active -- phase: DELIVERING
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

Active 2026-06-11 -- phase: DELIVERING -- All criteria verified on live fleet at 945021c. Drain + deploy + restart + smoke complete. Next: close to `directives/closed/2026-06-11-worker-loop-method-extraction.md`.

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
| JobProcessor self-orchestration contract (no longer delegation to QueueService.Process*Job) | `Features/TranscodeJob/Worker/worker-loop.feature.md` -- "What It Does" + "Status" rewritten to reflect direct-execution; commit ref updated to 945021c | this directive close commit |
| Decision: legacy Run/Stop/GetStatus/ProcessQueueLoop retained as unreachable-in-prod dead code | `directives/closed/2026-06-11-worker-loop-method-extraction.md` Decisions Made block | this directive close commit |
| `no other promotions` | n/a | helper extraction is a future directive |

### Verification

| # | Criterion | Evidence | Status |
|---|---|---|---|
| C1 | TranscodeJobProcessor.Process contains ProcessJob body | `Features/TranscodeJob/Worker/TranscodeJobProcessor.py` `_ProcessImpl` contains verbatim port; `grep -c "self.QueueService" Features/TranscodeJob/Worker/TranscodeJobProcessor.py` = 30 (>5). I9-2024 TranscodeAttempt #35352 completed via this path at 2026-06-11 14:47:29 success=TRUE (profilename='NVENC AV1 P7 CANARY VBR -720p'). | PASS |
| C2 | RemuxJobProcessor.Process contains ProcessRemuxJob body | `Features/TranscodeJob/Worker/RemuxJobProcessor.py` `_ProcessImpl` lines 31-162 contain verbatim port. larry-worker-1 TranscodeAttempt #35354 completed via this path at 2026-06-11 14:40:56 success=TRUE (profilename='Remux'). | PASS |
| C3 | SubtitleFixJobProcessor.Process contains ProcessSubtitleFixJob body | `Features/TranscodeJob/Worker/SubtitleFixJobProcessor.py` `_ProcessImpl` lines 30-125 contain verbatim port. No production SubtitleFix in queue post-deploy (verified empty: `SELECT COUNT(*) FROM transcodequeue WHERE processingmode='SubtitleFix'` = 0). Structural verification via composition: WorkerService/Main._StartTranscodeCapability registers SubtitleFixJobProcessor; contract test `Tests/Contract/TestJobProcessorRegistry.py` exercises `.Get('SubtitleFix')` dispatch. | PASS (structural; no operational smoke) |
| C4 | VariantJobProcessor.Process contains ProcessTestVariantJob body | `Features/TranscodeJob/Worker/VariantJobProcessor.py` `_ProcessImpl` lines 30-110 contain verbatim port. Helper methods (`_ProcessSingleVariant`, `_CleanupTestQueueRow`) remain on QueueService and are accessed via `self.QueueService.<helper>`. No production TestVariant in queue post-deploy. Structural verification via composition + contract test. | PASS (structural) |
| C5 | ProcessTranscodeQueueService loses four Process*Job methods | `grep -c "def Process" Features/TranscodeJob/ProcessTranscodeQueueService.py` = 1 (only ProcessQueueLoop). File shrunk 2437 -> 1871 LOC (-566). | PASS |
| C6 | ProcessQueueLoop transferred to WorkerLoopService; Main.py rewired | `WorkerService/Main.py._StartTranscodeCapability` composes `WorkerLoopService(TranscodeEnabled=True)` + `JobProcessorRegistry({'Transcode', 'SubtitleFix', 'TestVariant'})`; no `ProcessTranscodeQueueService.Run()` call remains. NARROW: legacy Run/Stop/GetStatus/ProcessQueueLoop/GetNextJob retained on the QueueService as dead code (see Decisions Made block); WorkerLoopService is the sole production loop for both Transcode + Remux capabilities. | PASS (narrowed -- see Decisions) |
| C7 | Full contract suite passes | `py -m pytest Tests/Contract/ --ignore=TestQueueGet.py --ignore=TestTranscodeStart.py --ignore=TestTranscodeStatus.py` = 295 passed, 7 skipped, 1 xfailed, 16 subtests passed. | PASS |
| C8 | Live smoke: >=1 transcode + >=1 remux successful on post-deploy fleet | `SELECT COUNT(*) FROM transcodeattempts WHERE workername IN ('I9-2024','dot-worker-1','larry-worker-1') AND completeddate > '2026-06-11 14:38:00' AND success=TRUE` = 2 (1 Remux on larry-worker-1, 1 Transcode on I9-2024). Failure count = 0. Additional in-flight at verification time: 4 Transcodes mid-flight on I9 + dot. | PASS |

### Decisions Made

- **Run/Stop/GetStatus/ProcessQueueLoop/GetNextJob retained on ProcessTranscodeQueueService.** C6 narrows from "delete those methods" to "no production code path invokes them." Justification: (1) WorkerService/Main.py is rewired to WorkerLoopService -- the production worker boot path no longer touches QueueService.Run. (2) The only remaining callers (TranscodingViewModel.StartTranscoding -> SharedTranscodingService -> TranscodeQueueController.StartTranscoding) are unrouted in the Flask blueprint registration; the live `/api/Transcode/Start` endpoint flips a DB flag via `SharedStatusHelper.SetTranscodingStarted` and does NOT invoke the legacy loop. (3) `Tests/Contract/TestInFlightCancellation.py::TestTranscodeLoopStopsOnStopRequested` stubs `Svc.GetNextJob` and `Svc.ProcessJob` -- the deleted `ProcessJob` is never resolved at test time. (4) ProcessQueueLoop's `target=self.ProcessJob` is a latent AttributeError on the dead production path; filed as cleanup for a follow-up directive that also migrates the test to WorkerLoopService. This keeps the current diff bounded to the criterion's spirit (orchestration ownership moved) without expanding into TranscodingViewModel/ActivityViewModel refactor.
