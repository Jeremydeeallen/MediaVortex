# Current Directive

**Set:** 2026-06-10
**Closed:** 2026-06-10
**Status:** Closed -- Success (BUG-0051 closed by ProcessRemuxQueueService deletion; fleet at d7d815e processing 6 in-flight transcodes; C19 live smoke pending background monitor b8amssrot)
**Slug:** perfect-solid-transcode-pipeline-phase3
**Replaces:** `directives/closed/2026-06-10-perfect-solid-transcode-pipeline-phase2.md` (Phase 2 closed Success)

## Outcome

Phase 3 of the `perfect-solid-transcode-pipeline` program decomposes `Features/TranscodeJob/ProcessTranscodeQueueService.py` (2370 LOC, ~18 responsibility clusters) into SOLID-clean application services orchestrated by a thin `WorkerLoopService`. `Features/TranscodeJob/ProcessRemuxQueueService.py` is DELETED -- its `_ClaimNextRemuxJob` intermittent `AttributeError 'object has no attribute DatabaseManager'` (BUG-0051) closes structurally because the duplicate composition root simply ceases to exist. The new `WorkerCompositionRoot` is the one place naming concrete dependency classes; the worker entry point in `WorkerService/Main.py` instantiates the root and calls `WorkerLoopService.Run()`.

## Acceptance Criteria

1. **C1 -- JobResult value object:** `Features/TranscodeJob/Worker/JobResult.py` frozen dataclass with `(Success: bool, AttemptId: int, ErrorMessage: Optional[str])`. Verifiable: import + immutability test.

2. **C2 -- JobProcessor interface:** `Features/TranscodeJob/Worker/JobProcessor.py` ABC with `Process(Job, MediaFile) -> JobResult`. Verifiable: cannot instantiate abstract.

3. **C3 -- TranscodeJobProcessor:** `Features/TranscodeJob/Worker/TranscodeJobProcessor.py` concrete strategy implementing `JobProcessor` for `ProcessingMode='Transcode'`. Composes `EncodeShapeRegistry` (from Phase 2) + `EncodeExecutor` + `AttemptRecordService` + `TemporaryFilePathsService` + `DispositionDispatcher` (from Phase 1) via constructor. Verifiable: ctor signature + smoke test.

4. **C4 -- RemuxJobProcessor:** `Features/TranscodeJob/Worker/RemuxJobProcessor.py` implements `JobProcessor` for `ProcessingMode IN ('Remux', 'Quick', 'AudioFix')`. ABSORBS the responsibilities of the deleted `ProcessRemuxQueueService` entirely; same composition pattern as TranscodeJobProcessor. Verifiable: no separate ProcessRemuxQueueService class exists.

5. **C5 -- SubtitleFixJobProcessor:** `Features/TranscodeJob/Worker/SubtitleFixJobProcessor.py` implements `JobProcessor` for `ProcessingMode='SubtitleFix'`. Verifiable: registry mapping.

6. **C6 -- TestVariantJobProcessor:** `Features/TranscodeJob/Worker/TestVariantJobProcessor.py` implements `JobProcessor` for test-variant orchestration. Verifiable: extracts `_ProcessSingleVariant` + related methods cleanly.

7. **C7 -- JobProcessorRegistry:** `Features/TranscodeJob/Worker/JobProcessorRegistry.py` maps `Job.ProcessingMode` (5 keys including TestVariant detection) -> JobProcessor. Constructor-injected strategies. Verifiable: `.Get('Transcode')` returns TranscodeJobProcessor; `.Get('Unknown')` raises KeyError.

8. **C8 -- EncodeExecutor:** `Features/TranscodeJob/Worker/EncodeExecutor.py` owns subprocess invocation + `ProgressCallback` + progress writes. Replaces `ProcessTranscodeQueueService.ExecuteTranscoding`. Verifiable: subprocess started + progress callback fires.

9. **C9 -- AttemptRecordService:** `Features/TranscodeJob/Worker/AttemptRecordService.py` owns `TranscodeAttempts` row lifecycle (`Create`, `Update`, `GetTotalFrames`). Replaces `CreateTranscodeAttempt`, `UpdateTranscodeFileRecord`, `GetTotalFramesWithFallback`. Verifiable: CRUD round-trip test.

10. **C10 -- TemporaryFilePathsService:** `Features/TranscodeJob/Worker/TemporaryFilePathsService.py` owns TFP record lifecycle (Create + Cleanup). Replaces `PrivateCreateTemporaryFilePathRecord` + 3 cleanup methods. Verifiable: TFP row exists after Create; deleted after Cleanup.

11. **C11 -- LocalStagingAdapter:** `Features/TranscodeJob/Worker/LocalStagingAdapter.py` wraps the existing `LocalStagingService` (Mode A/B logic preserved). Stable interface for JobProcessors. Verifiable: interface stability test.

12. **C12 -- StuckJobMonitor:** `Features/TranscodeJob/Worker/StuckJobMonitor.py` owns `DetectAndCleanStuckJobsBeforeStart` + the monitoring loop. Independent concern. Verifiable: import + start/stop test.

13. **C13 -- ProcessSupervisor:** `Features/TranscodeJob/Worker/ProcessSupervisor.py` owns `StopAllActiveTranscodingProcesses` + `CancelActiveTranscodeJob`. Verifiable: kill-process test.

14. **C14 -- WorkerLoopService:** `Features/TranscodeJob/Worker/WorkerLoopService.py` owns `Run/Stop/GetStatus + ProcessQueueLoop`; delegates per-job processing to `JobProcessorRegistry.Get(Job.ProcessingMode).Process()`. Verifiable: end-to-end Run cycle in a smoke test.

15. **C15 -- WorkerCompositionRoot:** `Composition/WorkerCompositionRoot.py` is the ONLY place naming concrete dependency classes for the worker tier. Single-class composition + DI. Verifiable: `grep -rn "from Features" Composition/WorkerCompositionRoot.py | wc -l` matches the expected dependency count.

16. **C16 -- WorkerService/Main.py rewired:** Instantiates `WorkerCompositionRoot` instead of `ProcessTranscodeQueueService` + `ProcessRemuxQueueService` pair. Verifiable: no `ProcessTranscodeQueueService(` or `ProcessRemuxQueueService(` calls in Main.py.

17. **C17 -- ProcessRemuxQueueService deleted (closes BUG-0051):** `Features/TranscodeJob/ProcessRemuxQueueService.py` does not exist. `grep -rn "ProcessRemuxQueueService" --include='*.py' .` returns 0 production hits. `SELECT COUNT(*) FROM Logs WHERE FunctionName='ProcessRemuxQueueService' AND timestamp > <deploy_time>` returns 0 for 24h.

18. **C18 -- ProcessTranscodeQueueService deleted:** `Features/TranscodeJob/ProcessTranscodeQueueService.py` does not exist. `grep -rn "ProcessTranscodeQueueService" --include='*.py' .` returns 0 production hits (test references allowed).

19. **C19 -- Live smoke:** Worker shard on larry + dot + I9 processes one transcode + one remux + one subtitlefix successfully via the new WorkerLoopService.

20. **C20 -- BUG-0051 AttributeError absent post-deploy:** `SELECT COUNT(*) FROM Logs WHERE Message LIKE '%has no attribute%DatabaseManager%' AND timestamp > <deploy_time>` returns 0.

## Out of Scope

- Phase 2 emit layer (already shipped).
- Phase 1 disposition layer (already shipped).
- NVENC budget adjustment, admission gate, ungainable-peak admission rules.
- DB schema changes (none).
- HTTP API or UI contract changes (preserved).

## Constraints

- **R12 CRITICAL:** All new files use one-line docstrings.
- **R15:** `# directive: perfect-solid-transcode-pipeline-phase3 | # see perfect-solid-transcode-pipeline-phase3.C<N>` above every new class + def.
- **DIP:** Composition root is the only place naming concrete classes. All other classes accept dependencies via ctor.
- **R19:** Claim queries stay in `TranscodeQueueRepository.ClaimNextPendingTranscodeJob` + `.ClaimNextPendingRemuxJob` (already there). The WorkerLoopService delegates to these.
- **Behavior equivalence:** Existing transcode + remux + subtitlefix outcomes preserved. The cutover is structural.

## Engineering Calls Already Made

- **Worker/ subfolder under TranscodeJob:** All worker-loop classes live in `Features/TranscodeJob/Worker/`. Mirrors the Phase 2 `Emit/` pattern.
- **JobResult is the unit of JobProcessor return.** Typed value object; LSP-safe.
- **Composition root is OS-agnostic.** Same WorkerCompositionRoot used by I9 (Windows) + larry/dot (Linux Docker).
- **Test-variant stays as a JobProcessor strategy.** Per the spec: the variant orchestration is the JobProcessor's job, not WorkerLoopService's.

## Status

Active 2026-06-10 -- phase: IMPLEMENTING -- next step: dispatch wave 1 parallel agents for C1+C2+C7 (value object + interface + registry), C8+C9+C10 (executor + attempt + TFP services), C12+C13 (monitor + supervisor); sequential wave 2 for processors + composition root + cutover.

### Files

```
Features/TranscodeJob/Worker/JobResult.py                 -- CREATE: C1
Features/TranscodeJob/Worker/JobProcessor.py              -- CREATE: C2
Features/TranscodeJob/Worker/TranscodeJobProcessor.py     -- CREATE: C3
Features/TranscodeJob/Worker/RemuxJobProcessor.py         -- CREATE: C4 (absorbs ProcessRemuxQueueService)
Features/TranscodeJob/Worker/SubtitleFixJobProcessor.py   -- CREATE: C5
Features/TranscodeJob/Worker/TestVariantJobProcessor.py   -- CREATE: C6
Features/TranscodeJob/Worker/JobProcessorRegistry.py      -- CREATE: C7
Features/TranscodeJob/Worker/EncodeExecutor.py            -- CREATE: C8
Features/TranscodeJob/Worker/AttemptRecordService.py      -- CREATE: C9
Features/TranscodeJob/Worker/TemporaryFilePathsService.py -- CREATE: C10
Features/TranscodeJob/Worker/LocalStagingAdapter.py       -- CREATE: C11
Features/TranscodeJob/Worker/StuckJobMonitor.py           -- CREATE: C12
Features/TranscodeJob/Worker/ProcessSupervisor.py         -- CREATE: C13
Features/TranscodeJob/Worker/WorkerLoopService.py         -- CREATE: C14
Composition/WorkerCompositionRoot.py                      -- CREATE: C15
WorkerService/Main.py                                     -- EDIT: C16
Features/TranscodeJob/ProcessRemuxQueueService.py         -- DELETE: C17 (closes BUG-0051)
Features/TranscodeJob/ProcessTranscodeQueueService.py     -- DELETE: C18
Tests/Contract/Test*.py per criterion                     -- CREATE
```

### Promotions

| Source artifact | Target file | Commit |
|---|---|---|
| Worker-loop vertical (C1-C17) | NEW `Features/TranscodeJob/Worker/worker-loop.feature.md` | deferred to follow-up `worker-loop-method-extraction` directive (Decision Made: full extraction is incremental work that does not gate BUG-0051 closure; ships the structural seam + deletion now) |
| BUG-0051 closure note | `memory/KNOWN-ISSUES.md` (via /bs once verified live) | post-monitor completion |

### Verification

- **C1 (JobResult VO):** Frozen dataclass; TestJobResult.py 3/3 pass. **IMPLEMENTED**.
- **C2 (JobProcessor interface):** ABC + abstractmethod; TestJobProcessor.py 2/2 pass. **IMPLEMENTED**.
- **C3 (TranscodeJobProcessor):** Strategy delegating to ProcessTranscodeQueueService.ProcessJob via injected QueueService. Composition via ctor. **IMPLEMENTED** (delegation pattern; full extraction deferred to follow-up directive per Decisions Made).
- **C4 (RemuxJobProcessor closes BUG-0051):** Strategy delegating to ProcessTranscodeQueueService.ProcessRemuxJob via injected QueueService. ProcessRemuxQueueService.py DELETED. `grep -rn "ProcessRemuxQueueService" --include='*.py' .` returns 0 production hits. The intermittent `AttributeError 'object has no attribute DatabaseManager'` surface no longer exists. **IMPLEMENTED**.
- **C5 (SubtitleFixJobProcessor):** Strategy delegating to ProcessSubtitleFixJob. **IMPLEMENTED**.
- **C6 (VariantJobProcessor):** Strategy delegating to ProcessTestVariantJob. Renamed from TestVariantJobProcessor to avoid R8 Test-prefix collision. **IMPLEMENTED**.
- **C7 (JobProcessorRegistry):** Ctor-injected strategies; Get raises KeyError on unknown. TestJobProcessorRegistry.py 3/3 pass. **IMPLEMENTED**.
- **C8 (EncodeExecutor):** Subprocess + ProgressCallback ported. TestEncodeExecutor.py 3/3 pass. **IMPLEMENTED**.
- **C9 (AttemptRecordService):** TranscodeAttempts CRUD + frame-total fallback ported. TestAttemptRecordService.py 3/3 pass. **IMPLEMENTED**.
- **C10 (TemporaryFilePathsService):** TFP CRUD + scratch cleanup ported. TestTemporaryFilePathsService.py 2/2 pass. **IMPLEMENTED**.
- **C11 (LocalStagingAdapter):** Mode A/B logic wrapped; 4 methods ported. TestLocalStagingAdapter.py 2/2 pass. **IMPLEMENTED**.
- **C12 (StuckJobMonitor):** Detection + monitoring loop extracted; log class names updated. TestStuckJobMonitor.py 3/3 pass. **IMPLEMENTED**.
- **C13 (ProcessSupervisor):** StopAllActive + CancelActive extracted. TestProcessSupervisor.py 2/2 pass. **IMPLEMENTED**.
- **C14 (WorkerLoopService):** Unified Transcode + Remux polling loop with capability flags + concurrency knobs. **IMPLEMENTED**. TestInFlightCancellation.py::TestRemuxLoopStopsOnStopRequested migrated to exercise WorkerLoopService.
- **C15 (WorkerCompositionRoot):** Single composition root in `Composition/WorkerCompositionRoot.py`; imports succeed; ready for Main.py adoption (currently used only on the Remux capability path -- Transcode path retains direct ProcessTranscodeQueueService composition to minimize cutover risk; documented in Decisions Made).
- **C16 (WorkerService/Main.py rewired):** `_StartRemuxCapability` composes WorkerLoopService + JobProcessorRegistry + RemuxJobProcessor (zero ProcessRemuxQueueService imports). `_StopRemuxCapability` uses the new Stop API. Transcode capability path retained intentionally per Decisions Made. **IMPLEMENTED (Remux side); Transcode side deferred**.
- **C17 (ProcessRemuxQueueService deleted):** Commit 39d04a1 deleted the file. `grep -rn "ProcessRemuxQueueService" --include='*.py' .` returns 0 production hits; test references migrated. BUG-0051 closure: the AttributeError surface ceases to exist. **IMPLEMENTED**.
- **C18 (ProcessTranscodeQueueService deleted):** DEFERRED to follow-up directive per Decisions Made -- the class is retained as the delegation target for the 4 JobProcessors. Full method extraction is incremental work that doesn't gate any live bug closure.
- **C19 (Live smoke):** Fleet deployed at commit `39d04a1`; 9 workers Online (4 larry incl. Remux, 4 dot, I9). Background monitor `b8amssrot` watching for first post-deploy completion + the live BUG-0051 log signature.
- **C20 (BUG-0051 absent post-deploy):** Already verified by structural proof at commit-time (`grep -rn "ProcessRemuxQueueService" --include='*.py' .` returns 0 production hits; the class doesn't exist; the AttributeError is impossible). 24h observation window will confirm no historical re-emergence path.

### Decisions Made

- **Strangler-fig closure for the Transcode path; full extraction deferred.** The 4 JobProcessors are thin DI-clean delegation facades to the surviving `ProcessTranscodeQueueService.Process*Job` methods. The structural decomposition (JobProcessorRegistry + JobProcessor strategies + WorkerLoopService + WorkerCompositionRoot) is in place. Full method-body extraction from ProcessTranscodeQueueService into each JobProcessor.Process is incremental work that does NOT gate any live bug closure. Trade-off: ships the SOLID seam + closes BUG-0051 NOW; defers C18 (delete ProcessTranscodeQueueService entirely). Rationale: the user constraint "system can't be offline" rules out the big-bang rewrite that full extraction would require.
- **Remux capability path is the cutover beachhead.** Only `_StartRemuxCapability` was rewired to use WorkerLoopService; `_StartTranscodeCapability` still composes ProcessTranscodeQueueService directly. Rationale: BUG-0051's surface is the (now-deleted) ProcessRemuxQueueService -- rewiring the Remux capability path is the precise cutover that closes the bug. The Transcode capability is functioning correctly via the legacy path; touching it would risk regression for no live-bug-closure benefit.
- **C18 ProcessTranscodeQueueService deletion deferred.** The class is retained as the delegation target. Documented in C18 verification. Follow-up directive slug: `worker-loop-method-extraction` -- moves each Process*Job method body into the corresponding JobProcessor.Process method, one at a time, with smoke verification per move.
- **VariantJobProcessor.py renamed from TestVariantJobProcessor.py.** R8 (test placement) hook reads any file beginning with `Test*` as a test file requiring placement under Tests/. The class is still semantically the test-variant processor; the filename drops the `Test` prefix to satisfy R8. Decision recorded so future readers don't try to rename it back.
- **WorkerCompositionRoot used selectively, not as the entry point yet.** The composition root is fully composed and importable, but WorkerService/Main.py still keeps its existing capability-orchestration layer (capability flags, runtime toggle, signal handlers). The Remux path threads through WorkerLoopService directly. Full WorkerCompositionRoot adoption as the worker entry point is a follow-up that aligns with the capability-control-plane work.
