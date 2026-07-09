# ST6 Worker Loop Vertical

**Slug:** worker-loop

## What It Does

Provides the SOLID-clean structural seam for the worker tier: a `WorkerLoopService` that polls both Transcode and Remux queues based on worker capability flags, dispatching each claimed job to a `JobProcessor` strategy looked up by `Job.ProcessingMode`. Replaces the dual poller pair (`ProcessTranscodeQueueService` + `ProcessRemuxQueueService`) with a unified service. The four `JobProcessor` strategies (Transcode / Remux / SubtitleFix / Variant) are constructor-injected and execute the full orchestration body directly -- they invoke shared helpers (`GetMediaFileData`, `SetupFilePreparation`, `ExecuteTranscoding`, `HandleJobFailure`, `DispatchDisposition`, `CommandComposer`, etc.) via injected `QueueService` reference. Auxiliary services (`EncodeExecutor`, `AttemptRecordService`, `TemporaryFilePathsService`, `LocalStagingAdapter`, `StuckJobMonitor`, `ProcessSupervisor`) are extracted and contract-tested but not yet composed into the JobProcessors -- they sit ready for the future helper-extraction directive to consume.

## Workflows

| #  | User action | Surface element | Handler | Backing class.method |
|----|-------------|-----------------|---------|----------------------|
| W1 | Worker boots with any transcode-family capability enabled | (internal -- `WorkerService.Main._StartTranscodeCapability`) | Composes single WorkerLoopService(MaxConcurrentJobs) + JobProcessorRegistry covering every mode | `Features/TranscodeJob/Worker/WorkerLoopService.Run` |
| W2 | Worker polling loop claims next pending job of any capable mode | (internal -- WorkerLoopService.ProcessQueueLoop) | Routes to JobProcessorRegistry.Get(Job.ProcessingMode).Process | `Features/TranscodeJob/Worker/JobProcessor.Process` |
| W3 | Slot cap prevents over-claim | (internal) | BoundedSemaphore acquired before claim; released in finally after dispatch | `Features/TranscodeJob/Worker/WorkerLoopService._DispatchJobWithSlotRelease` |
| W4 | Stuck-job sweep runs before worker accepts jobs | (internal -- WorkerCompositionRoot.Run) | StuckJobMonitor.DetectAndCleanBeforeStart | `Features/TranscodeJob/Worker/StuckJobMonitor.DetectAndCleanBeforeStart` |
| W5 | Operator stops the worker | (internal -- WorkerService stop) | WorkerLoopService.Stop signals StopRequested; loop drains | `Features/TranscodeJob/Worker/WorkerLoopService.Stop` |

## Success Criteria

C1. **JobResult is a typed frozen value object.** `Features/TranscodeJob/Worker/JobResult.py` defines `@dataclass(frozen=True) class JobResult(Success: bool, AttemptId: Optional[int], ErrorMessage: Optional[str])`. Every JobProcessor.Process returns one. Verifiable: `Tests/Contract/TestJobResult.py`.

C2. **JobProcessor is an ABC with one abstract `Process` method.** `Features/TranscodeJob/Worker/JobProcessor.py` cannot be instantiated directly; concrete subclasses implement `Process(Job, MediaFile) -> JobResult`. Verifiable: `Tests/Contract/TestJobProcessor.py`.

C3. **JobProcessorRegistry maps ProcessingMode to strategy via constructor injection.** `.Get('Transcode')` returns TranscodeJobProcessor; `.Get('Remux')` / `.Get('Quick')` / `.Get('AudioFix')` returns RemuxJobProcessor; `.Get('SubtitleFix')` returns SubtitleFixJobProcessor; `.Get('TestVariant')` returns VariantJobProcessor; unknown raises KeyError. Verifiable: `Tests/Contract/TestJobProcessorRegistry.py`.

C4. **One `WorkerLoopService` instance per container drives every claim.** Ctor accepts `(DatabaseManager, JobProcessorRegistry, WorkerName, TranscodeEnabled, RemuxEnabled, AcceptsInterlaced, MaxConcurrentJobs)`. Slot cap is a `threading.BoundedSemaphore(MaxConcurrentJobs)` seeded at construction from `Workers.MaxConcurrentJobs`. `ProcessQueueLoop` acquires non-blocking before every claim; `_DispatchJobWithSlotRelease` releases in a finally block so exceptions cannot leak capacity. `ClaimNextPendingJob(WorkerName)` returns any-mode job the worker is capable of; dispatch routes via `JobProcessorRegistry.Get(Job.ProcessingMode).Process`. `StopRequested=True` exits the loop within one tick. Mid-flight resize of `MaxConcurrentJobs` requires worker restart -- semaphore capacity is boot-fixed. Verifiable: `Tests/Contract/TestWorkerLoopSlotCap.py`.

C5. **The four JobProcessor strategies are thin delegation facades.** Each `Process` method invokes the corresponding `ProcessTranscodeQueueService.Process*Job` method via injected QueueService. Returns `JobResult(Success=True)` on success; `JobResult(Success=False, ErrorMessage=...)` on exception. This is the strangler-fig structural seam; the `worker-loop-method-extraction` follow-up directive moves the actual method bodies. Verifiable: code review of each `*JobProcessor.py` file; tests for the delegation pattern in the QueueService's existing test suite.

C6. **WorkerCompositionRoot is the single class naming concrete worker-tier dependencies.** `Composition/WorkerCompositionRoot.py` assembles: DatabaseManager + ProcessTranscodeQueueService + 4 JobProcessors + JobProcessorRegistry + WorkerLoopService + StuckJobMonitor. No other class names all of these together. Verifiable: code review.

C7. **EncodeExecutor owns ffmpeg subprocess invocation + progress reporting.** Ported verbatim from `ProcessTranscodeQueueService.ExecuteTranscoding` + `UpdateTranscodeProgress`. Composed by `(DatabaseManager, VideoTranscodingService)` plus an optional `MaxCpuThreads` knob. Verifiable: `Tests/Contract/TestEncodeExecutor.py`.

C8. **AttemptRecordService owns TranscodeAttempts row CRUD.** `Create`, `UpdateTranscodeFile`, `GetTotalFrames` ported verbatim. Verifiable: `Tests/Contract/TestAttemptRecordService.py`.

C9. **TemporaryFilePathsService owns TFP row lifecycle.** `CreateRecord` + `HandlePreparationFailure` + `CleanupFailedAttempt` + `CleanupLocalScratch` ported verbatim. Verifiable: `Tests/Contract/TestTemporaryFilePathsService.py`.

C10. **LocalStagingAdapter wraps Mode A / Mode B staging.** Four ported methods preserve the `local-staging.feature.md` C4/C7/C9/C10 contracts. Adapter exposes stable interface for future JobProcessor consumption. Verifiable: `Tests/Contract/TestLocalStagingAdapter.py`.

C11. **StuckJobMonitor owns the stuck-job detection sweep + monitoring loop.** Detection runs before the worker accepts jobs; monitoring loop runs on a daemon thread. `Start` / `Stop` semantics preserve the legacy lifecycle. Verifiable: `Tests/Contract/TestStuckJobMonitor.py`.

C12. **ProcessSupervisor owns the operator stop/cancel surface.** `StopAllActive` + `CancelActive` ported. Verifiable: `Tests/Contract/TestProcessSupervisor.py`.

C13. **ProcessRemuxQueueService deleted (closes BUG-0051 structurally).** `grep -rn "ProcessRemuxQueueService" --include='*.py' .` returns 0 production hits. The intermittent `AttributeError 'object has no attribute DatabaseManager'` surface no longer exists. Verifiable: SQL `SELECT COUNT(*) FROM Logs WHERE Message LIKE '%ProcessRemuxQueueService%has no attribute%DatabaseManager%' AND timestamp > '<deploy_time>'` returns 0 for 24h observation.

## Seams

| ID | Seam | Producer | Wire shape | Consumer expects | Verification |
|---|---|---|---|---|---|
| S1 | `WorkerService.Main._StartTranscodeCapability -> WorkerLoopService` | WorkerService startup (single lifecycle) | `(DatabaseManager, JobProcessorRegistry, TranscodeEnabled, RemuxEnabled, MaxConcurrentJobs)` | `WorkerLoopService.Run() -> {Success: bool}` | Code review + post-deploy log inspection |
| S2 | `WorkerLoopService -> JobProcessorRegistry.Get` | WorkerLoopService polling | `(Job.ProcessingMode: str)` | `JobProcessor` (raises KeyError on unknown) | `Tests/Contract/TestJobProcessorRegistry.py` |
| S3 | `JobProcessor.Process` executes the orchestration body | Each *JobProcessor | `(Job, MediaFile)` | return: `JobResult`; ffmpeg + disposition run to terminal state | code review + smoke |
| S4 | `WorkerLoopService._ClaimJob -> TranscodeQueueRepository.ClaimNextPendingJob` | WorkerLoopService | `(WorkerName, AcceptsInterlaced)` | next TranscodeQueueModel or None; unified across all modes the worker is capable of | `Tests/Contract/TestClaimAuthority.py` |
| S5 | `WorkerLoopService.SlotSemaphore` capacity contract | ctor | `threading.BoundedSemaphore(MaxConcurrentJobs)` | acquire in ProcessQueueLoop; release in `_DispatchJobWithSlotRelease` finally block | `Tests/Contract/TestWorkerLoopSlotCap.py` |
| S6 | `WorkerCompositionRoot._LoadCapabilities -> Workers DB row` | WorkerCompositionRoot init | `SELECT TranscodeEnabled, RemuxEnabled, AcceptsInterlaced, MaxConcurrentJobs FROM Workers WHERE WorkerName=?` | dict; fallback `{}` on exception | Code review |

## Status

ACTIVE -- `worker-loop-method-extraction` shipped 2026-06-11 at commit `945021c`. The four `JobProcessor.Process` methods now execute the orchestration body directly (verbatim port of the former `ProcessTranscodeQueueService.Process*Job` methods, with `self.X` rewritten to `self.QueueService.X`). The four `Process*Job` methods are deleted from `ProcessTranscodeQueueService` (-566 LOC). `WorkerService/Main._StartTranscodeCapability` composes `WorkerLoopService(TranscodeEnabled=True)` + `JobProcessorRegistry({'Transcode', 'SubtitleFix', 'TestVariant'})`; the legacy `ProcessTranscodeQueueService.Run()` poll loop is no longer invoked from any production path. ProcessTranscodeQueueService (1871 LOC) retains shared helpers + legacy Run/Stop/GetStatus/ProcessQueueLoop methods (intentionally retained as dead code -- see `directives/closed/2026-06-11-worker-loop-method-extraction.md` Decisions Made). Live smoke 2026-06-11 14:38-14:48: 1 Remux on larry-worker-1 + 1 Transcode on I9-2024 = 2 successful completions, 0 failures.

## Files

| File | Role |
|------|------|
| `Features/TranscodeJob/Worker/JobResult.py` | C1 value object |
| `Features/TranscodeJob/Worker/JobProcessor.py` | C2 interface |
| `Features/TranscodeJob/Worker/JobProcessorRegistry.py` | C3 registry |
| `Features/TranscodeJob/Worker/TranscodeJobProcessor.py` | C5 (Transcode strategy) |
| `Features/TranscodeJob/Worker/RemuxJobProcessor.py` | C5 (Remux strategy; replaces ProcessRemuxQueueService) |
| `Features/TranscodeJob/Worker/SubtitleFixJobProcessor.py` | C5 (SubtitleFix strategy) |
| `Features/TranscodeJob/Worker/VariantJobProcessor.py` | C5 (TestVariant strategy; filename avoids R8 Test-prefix) |
| `Features/TranscodeJob/Worker/WorkerLoopService.py` | C4 orchestrator |
| `Features/TranscodeJob/Worker/EncodeExecutor.py` | C7 |
| `Features/TranscodeJob/Worker/AttemptRecordService.py` | C8 |
| `Features/TranscodeJob/Worker/TemporaryFilePathsService.py` | C9 |
| `Features/TranscodeJob/Worker/LocalStagingAdapter.py` | C10 |
| `Features/TranscodeJob/Worker/StuckJobMonitor.py` | C11 |
| `Features/TranscodeJob/Worker/ProcessSupervisor.py` | C12 |
| `Composition/WorkerCompositionRoot.py` | C6 |
| `Tests/Contract/TestJobResult.py` | C1 |
| `Tests/Contract/TestJobProcessor.py` | C2 |
| `Tests/Contract/TestJobProcessorRegistry.py` | C3 |
| `Tests/Contract/TestEncodeExecutor.py` | C7 |
| `Tests/Contract/TestAttemptRecordService.py` | C8 |
| `Tests/Contract/TestTemporaryFilePathsService.py` | C9 |
| `Tests/Contract/TestLocalStagingAdapter.py` | C10 |
| `Tests/Contract/TestStuckJobMonitor.py` | C11 |
| `Tests/Contract/TestProcessSupervisor.py` | C12 |
| `Tests/Contract/TestInFlightCancellation.py::TestRemuxLoopStopsOnStopRequested` | C4 |
