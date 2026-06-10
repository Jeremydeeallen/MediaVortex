# Perfect SOLID Transcode Pipeline — Design Spec

**Slug:** `perfect-solid-transcode-pipeline`
**Created:** 2026-06-10
**Vertical:** ST6 TRANSCODE + ST7 DISPOSITION (per `transcode.flow.md`)

---

## Goal

Refactor the transcode pipeline (encode + disposition stages) into a SOLID-clean structure where:
- Every class has one stated responsibility (SRP — verifiable; if you need "and" to describe it, split it)
- Every behavior axis is open to extension via a new class implementing an interface (OCP)
- Every strategy interface returns a typed value object so substitution is safe (LSP)
- Every interface is focused on one method or coherent operation cluster (ISP)
- Every high-level service depends on interfaces only; concrete classes are named only in the composition root (DIP)
- Mechanical-enforcement hooks (R1, R3, R10, R11, R12, R13, R14, R15, R18, R19) **never fire during the refactor** because the design is shaped to satisfy them by construction

End state: ~25 small classes replacing 5 god classes (3832 LOC → estimated 2500-3000 LOC, the reduction coming from de-duplication).

## Scope

Five files in scope:
| File | LOC | Disposition |
|---|---|---|
| `Models/CommandBuilder.py` | 857 | DELETED at Phase 2 end |
| `Features/TranscodeJob/ProcessTranscodeQueueService.py` | 2370 | DELETED at Phase 3 end |
| `Features/TranscodeJob/ProcessRemuxQueueService.py` | 147 | DELETED at Phase 3 end |
| `Features/TranscodeJob/AdaptiveQualityService.py` | 192 | DELETED at Phase 1 end |
| `Features/QualityTesting/PostTranscodeDispositionService.py` | 266 | REFACTORED in place at Phase 1 |

Pipeline stages addressed: **ST6 TRANSCODE** + **ST7 DISPOSITION** (per `transcode.flow.md`).

## Out of Scope

- **ST1-ST5** (scan, probe, assign, recompute, queue admission) — separate verticals; admission gate for ungainable peak (BUG-0049 C6) is a tiny follow-up directive after Phase 1.
- **ST8 VMAF** (`Features/QualityTesting/*` beyond PostTranscodeDispositionService) — own vertical; was just refactored.
- **ST9 ACTION** (`Features/FileReplacement/*`) — refactored 2026-06-02 (`filereplacement-decompose`).
- **DB schema changes** — additive only via idempotent migrations; no renames or drops in this directive.
- **HTTP API contract changes** — preserved.
- **Operator-visible UI behavior changes** — preserved.
- **FFmpeg argv byte preservation** — explicitly not preserved; equivalence is "output media functionally identical for VMAF / size / playback", not byte-identical command strings (BUG-0048's faststart fix is a byte change).
- **BUG-0052 PathStorage shim** — prerequisite hotfix; runs as a small standalone directive **before** Phase 1 (workers can't even bootstrap on fresh containers without it).
- **BUG-0053 TestMediaProbeUsesPath SELECT** — same; one-line hotfix directive before Phase 1.

## Current state — SOLID violations enumerated

### `Models/CommandBuilder.py` (857 LOC, 1 class, 7 responsibility clusters)

| Cluster | Methods | Violations |
|---|---|---|
| Shape orchestration | `BuildFFmpegCommand`, `_BuildTranscodeShape`, `_BuildRemuxShape`, `_BuildSubtitleFixShape` | **OCP** (dispatcher branches on `Job.ProcessingMode`); **SRP** (orchestration is its own job) |
| Audio filter | `BuildAudioFilters` | **DIP** (creates `DatabaseManager()` mid-method); **SRP** (audio concerns ≠ shape building) |
| Video filter | `BuildVideoFilters` | **SRP** |
| Codec assembly | `AddCodecParameters`, `AddFilmGrainParameter`, `AddPixelFormatParameter`, `BuildAudioCodecArgs`, `_DefaultAudioBitrateForChannels` | **SRP** |
| Resolution math | `_CalculateTargetResolution`, `_CalculateScaleFilter`, `_ExtractHeightFromResolution`, `_GetSourceDimensions`, `_CalculateWidthFromHeight` | **SRP** (pure value computation belongs in own module) |
| Filename concerns | `GenerateOutputFileName`, `ExtractResolutionFromFilename`, `FormatResolutionForFilename`, `_NormalizeFfmpegPath`, `_CollapseMvSuffix` | **SRP** + **DRY** (duplicated in ProcessTranscodeQueueService) |
| External-tool wrappers | `_RunFFprobeAnalysis`, `GetMaxCpuThreads` | **SRP** + boundary leak (adapter masquerading as domain method) |

### `Features/TranscodeJob/ProcessTranscodeQueueService.py` (2370 LOC, 1 class, ~18 responsibility clusters)

Three parallel job-type dispatchers (`ProcessJob` / `ProcessRemuxJob` / `ProcessSubtitleFixJob` / `ProcessTestVariantJob`) share ~80% of flow but are written as parallel methods — classic **OCP** smell.

Additional responsibilities tangled in: lifecycle (`Run`/`Stop`/`GetStatus`), queue polling, file prep, settings, command-build dispatch, attempt-record management, subprocess execution, three result handlers, disposition dispatch, four kinds of cleanup, path computations, record updates, supervision, local-staging integration, stuck-job monitoring, source-missing handling.

**DRY violation:** `_GenerateOutputFileName`, `_ExtractResolutionFromFilename`, `_FormatResolutionForFilename` exist here AND in CommandBuilder — same logic, two copies.

### `Features/TranscodeJob/ProcessRemuxQueueService.py` (147 LOC)

**DIP** violation: lazy-imports and instantiates `ProcessTranscodeQueueService` to do the actual remux work via `_GetExecutor()`. BUG-0051's intermittent `'ProcessRemuxQueueService' object has no attribute 'DatabaseManager'` AttributeError is almost certainly state leakage at this composition seam. Eliminating the duplicate composition root closes BUG-0051 structurally — there will be no second service to drift.

### `Features/TranscodeJob/AdaptiveQualityService.py` (192 LOC)

**SRP** violation: DB read (`GetLatestTranscodeAttemptWithVMAF`) + CRF math (`CalculateAdjustedCRF`) + validation (`ValidateCRFAdjustment`) + decision (`ShouldRetranscode`).

**Hardcoded thresholds:** VMAF 80 cutoff (line 81, 179), min CRF 15 (line 94, 116) — should be config-driven per `db-is-authority` rule.

**BUG-0050 root cause:** lines 160, 167, 174, 180, 185 reference bare `FilePath` (not in scope — function takes `MediaFileId`). Splitting decision from logging fixes this by construction (decision becomes a pure function over typed inputs; logging happens at the call site with the correct identifiers).

### `Features/QualityTesting/PostTranscodeDispositionService.py` (266 LOC, 6 methods)

Smallest violation set. SRP-borderline: `DecidePostTranscodeDisposition` orchestrates DB read + decision + commit + cleanup. `_DecideFromInputs` is already a pure function (good — preserve this shape). The cleanup (`CleanupTemporaryFilePaths`) and compliance recording (`RecordComplianceGateFailure`) belong as separate services.

---

## Target architecture

### ST6 TRANSCODE — Encode emit layer

**Domain primitives** (pure value computation, no dependencies, single-line docstrings):

| Class | Responsibility | Replaces |
|---|---|---|
| `ResolutionCalculator` | Target resolution + scale filter + height/width math | CommandBuilder resolution-math methods |
| `OutputFilenameBuilder` | Output filename + extension + resolution-token | CommandBuilder + ProcessTranscodeQueueService filename methods (de-duped) |
| `CommandSpec` (value object) | Typed `(Command: str, OutputPath: str)` — replaces ad-hoc dict | All `Dict[str, str]` returns |
| `CodecParameterAssembler` | Codec arg assembly (incl. film grain, pixel format) | CommandBuilder `Add*Parameter*` methods |
| `AudioFilterBuilder` | Linear-loudnorm filter string (one mode only per `linear-loudnorm.feature.md`) | CommandBuilder `BuildAudioFilters` |
| `VideoFilterBuilder` | yadif + scale composition | CommandBuilder `BuildVideoFilters` |
| `AudioCodecArgsBuilder` | `-c:a` + `-b:a` selection | CommandBuilder `BuildAudioCodecArgs` |

**Strategy layer** (OCP via interface + concrete implementations):

```
EncodeShape (interface)
    def Build(MediaFile, Job, Context) -> CommandSpec | None: ...
        │
        ├─ TranscodeShape   (CRF / VBR / NVENC unified per Profile.RateControlMode)
        ├─ RemuxShape       (-c:v copy + audio decision branch; emits -f mp4 -movflags +faststart unconditionally)
        └─ SubtitleFixShape (mov_text subtitle remux)

EncodeShapeRegistry
    def Get(ProcessingMode: str) -> EncodeShape: ...
```

Adding a new shape = new class implementing `EncodeShape` + registry entry. Zero dispatcher edits. **OCP win.**

**Interface adapter:**

| Class | Responsibility |
|---|---|
| `MediaProbeAdapter` | Wraps ffprobe invocation (injected into shapes); replaces CommandBuilder `_RunFFprobeAnalysis` |
| `SystemCapabilityProbe` | Wraps `GetMaxCpuThreads` and similar OS probes |

### ST6 TRANSCODE — Worker loop layer

**Application services:**

| Class | Responsibility | Replaces |
|---|---|---|
| `WorkerLoopService` | `Run`/`Stop`/`GetStatus` + `ProcessQueueLoop`; delegates per-job to `JobProcessor` | ProcessTranscodeQueueService lifecycle + ProcessRemuxQueueService entirely |
| `JobProcessor` (interface) | `Process(Job) -> JobResult` | Replaces the 3 parallel `Process*Job` methods |
| `TranscodeJobProcessor` | Concrete: file prep → shape build → execute → result handle for transcode jobs | ProcessTranscodeQueueService `ProcessJob` |
| `RemuxJobProcessor` | Same flow for remux jobs | `ProcessRemuxJob` + ProcessRemuxQueueService entirely |
| `SubtitleFixJobProcessor` | Same flow for subtitle-fix jobs | `ProcessSubtitleFixJob` |
| `TestVariantJobProcessor` | Test-variant orchestration | `ProcessTestVariantJob` + `_ProcessSingleVariant` etc. |
| `EncodeExecutor` | Subprocess invocation + `ProgressCallback` + progress writes | `ExecuteTranscoding` + nested callback |
| `AttemptRecordService` | `TranscodeAttempts` lifecycle (`Create`, `Update`, `GetTotalFrames`) | `CreateTranscodeAttempt`, `UpdateTranscodeFileRecord`, `GetTotalFramesWithFallback` |
| `TemporaryFilePathsService` | TFP record lifecycle (create + cleanup) | `PrivateCreateTemporaryFilePathRecord`, `_CleanupFailedAttemptFiles`, `_CleanupLocalScratchForAttempt` |
| `LocalStagingAdapter` | Wraps existing `LocalStagingService`; presents a stable interface to JobProcessors | `_ResolveTfpPathParts`, `_GetLocalStagingPathsIfActive`, `_CopyBackStagedOutput` |
| `StuckJobMonitor` | `DetectAndCleanStuckJobsBeforeStart` + `StartStuckJobMonitoring` loop | All four stuck-job methods |
| `ProcessSupervisor` | `StopAllActiveTranscodingProcesses` + `CancelActiveTranscodeJob` | Same |

Each JobProcessor composes the same five steps via its constructor-injected dependencies:
1. `FilePrep.Prepare(Job) -> EffectiveInputPath`
2. `ShapeRegistry.Get(Job.ProcessingMode).Build(MediaFile, Job, Context) -> CommandSpec`
3. `AttemptRecordService.Create(Job, CommandSpec) -> AttemptId`
4. `EncodeExecutor.Execute(CommandSpec, AttemptId) -> ExecutionResult`
5. `ResultHandler.Handle(Job, ExecutionResult, AttemptId) -> Disposition` (then queue ST7)

**OCP win:** new job types = new `JobProcessor` class + registration. No edits to `WorkerLoopService`.

### ST7 DISPOSITION layer

**Domain primitives:**

| Class | Responsibility | Replaces |
|---|---|---|
| `PostTranscodeDispositionDecider` | Pure function `(Attempt, GateConfig) -> Disposition` | `PostTranscodeDispositionService._DecideFromInputs` (already a pure function — preserve shape) |
| `Disposition` (value object) | Typed `(Action, Reason, NextRegime?, NextKnob?)` | Replaces string disposition + reason pair |

**Strategy layer:**

```
AdjustmentCalculator (interface)
    def CalculateNextKnobs(PreviousAttempt, ProfileSettings, GateThreshold) -> KnobOverrides | None: ...
        │
        ├─ CrfAdjustmentCalculator      (SVT-AV1 / x264 — CRF-down per VMAF gap)
        └─ NvencBudgetAdjustmentCalculator (NVENC VBR — bitrate-up per VMAF gap)

AdjustmentRegistry
    def Get(RateControlMode: str) -> AdjustmentCalculator: ...
```

Selected by `Profile.RateControlMode` (not by codec name or profile string). **DIP** + **OCP** wins.

**Application services:**

| Class | Responsibility | Replaces |
|---|---|---|
| `RetryBudgetService` | Counts prior failed attempts; decides Discard-into-Review vs Requeue per `PostTranscodeGateConfig.MaxRequeueAttempts` | Currently spread across PostTranscodeDispositionService + AdaptiveQualityService |
| `DispositionDispatcher` | Orchestrates: read attempt → decide → calculate adjustments → write next-queue-row OR ProblemFiles | `DecidePostTranscodeDisposition` + `_CommitDisposition` |
| `RetranscodeDecider` | "Should this MediaFile be re-queued at all?" — pure function over prior attempts | `AdaptiveQualityService.ShouldRetranscode` (without the FilePath NameError because inputs are typed) |
| `ComplianceFailureRecorder` | Records cascade reasons | `PostTranscodeDispositionService.RecordComplianceGateFailure` (extracted) |
| `AttemptCleanupService` | Removes TFP rows for completed dispositions | `PostTranscodeDispositionService.CleanupTemporaryFilePaths` (extracted) |

### Composition root

| Class | Responsibility |
|---|---|
| `WorkerCompositionRoot` | Single class that names every concrete dependency; assembled at worker startup; passed to `WorkerLoopService` constructor |

Pattern:

```python
class WorkerCompositionRoot:
    """Single home for concrete class names; wires the worker graph."""

    def __init__(self, WorkerName: str):
        Db = DatabaseManager()
        Probe = MediaProbeAdapter()
        Resolution = ResolutionCalculator()
        Filename = OutputFilenameBuilder()
        Codec = CodecParameterAssembler()
        Audio = AudioFilterBuilder(Db)
        Video = VideoFilterBuilder()
        AudioCodec = AudioCodecArgsBuilder()
        Registry = EncodeShapeRegistry({
            'Transcode': TranscodeShape(Probe, Resolution, Filename, Codec, Audio, Video, AudioCodec),
            'Remux': RemuxShape(Probe, Filename, Audio),
            'SubtitleFix': SubtitleFixShape(Probe, Filename),
        })
        AdjustReg = AdjustmentRegistry({
            'cq': CrfAdjustmentCalculator(),
            'vbr': NvencBudgetAdjustmentCalculator(),
        })
        Decider = PostTranscodeDispositionDecider()
        Retry = RetryBudgetService(Db)
        DispDispatch = DispositionDispatcher(Decider, AdjustReg, Retry, Db)
        # ... all the others
        self.WorkerLoop = WorkerLoopService(
            JobRegistry=JobProcessorRegistry({
                'Transcode': TranscodeJobProcessor(...),
                'Remux': RemuxJobProcessor(...),
                'SubtitleFix': SubtitleFixJobProcessor(...),
                'TestVariant': TestVariantJobProcessor(...),
            }),
            StuckMonitor=StuckJobMonitor(Db),
            Supervisor=ProcessSupervisor(),
        )

    def Run(self): self.WorkerLoop.Run()
```

This is the **ONLY** place that names concrete classes. Everything else depends on injected interfaces. **DIP achieved by construction.**

### Hook-compliance design choices (preventing rejections)

| Hook | How design satisfies it |
|---|---|
| **R1** colocated `*.feature.md` preread | New classes land with colocated `*.feature.md` from day 1 (in directive's `### Files` list). Phase 4 promotes content. |
| **R3** no DB cache | `Db` injected fresh per-call sites; only `Workers` row is read once at composition (capability flags — does not change mid-flight per design) |
| **R10** `BuildClaimPredicate` | All claim queries stay in `TranscodeQueueRepository`; no new claim paths created |
| **R11** idempotent migrations | Phase 1 may add `PostTranscodeGateConfig.MaxRequeueAttempts INTEGER NOT NULL DEFAULT 3` via `ADD COLUMN IF NOT EXISTS` |
| **R12** edit-region trap | All NEW files born with one-line docstrings only. Edits to existing files (`PostTranscodeDispositionService.py`) stay outside preexisting multi-line docstring regions. |
| **R13** `*.feature.md` only at DELIVERING | Phase 4 promotes; phases 1-3 carry content in the directive doc. EXCEPTION: a new `Features/TranscodeJob/encode-emit.feature.md` may be needed at Phase 2 start to anchor the new vertical — file as Phase 2 first commit if so. |
| **R14** no annotation lines | Replaced sections deleted, not annotated. Feature/flow doc updates are in-place rewrites. |
| **R15** code anchors | Every new + edited def/class gets `# directive: perfect-solid-transcode-pipeline \| # see perfect-solid-transcode-pipeline.C<N>` |
| **R18** doc read budget | Directive's own `*.feature.md` (if created) sized so a section read fits `limit=50` |
| **R19** TranscodeQueueRepository owns claim queries | All claim work routes through it; new `JobProcessor` strategies call into the repo, never duplicate claim SQL |

---

## SOLID violations → Resolutions mapping

| Violation | Phase | Resolution mechanism |
|---|---|---|
| CommandBuilder god class (7 responsibilities) | 2 | Split into 7 domain primitives + 3 shape classes |
| CommandBuilder dispatcher branches (OCP) | 2 | `EncodeShapeRegistry` lookup |
| `BuildAudioFilters` creates `DatabaseManager` mid-method (DIP) | 2 | `AudioFilterBuilder(Db)` — Db injected via ctor |
| ProcessTranscodeQueueService 2370 LOC (SRP × 18) | 3 | Split into 11 application services + 4 JobProcessors |
| 3 parallel `Process*Job` methods (OCP) | 3 | `JobProcessor` interface + 4 concrete strategies |
| `ProcessRemuxQueueService` lazy-imports ProcessTranscodeQueueService (DIP) | 3 | Both services deleted; `RemuxJobProcessor` is its own first-class strategy |
| Filename method duplication CommandBuilder ↔ ProcessTranscodeQueueService (DRY) | 2 | Single `OutputFilenameBuilder`; both old copies deleted |
| AdaptiveQualityService 4 responsibilities (SRP) | 1 | Split into `RetranscodeDecider` + `CrfAdjustmentCalculator` + `RetryBudgetService` + drop validation (use type system) |
| AdaptiveQualityService hardcoded thresholds (DIP / db-is-authority) | 1 | Read from `PostTranscodeGateConfig` per call |
| PostTranscodeDispositionService orchestration tangled with decision | 1 | `DispositionDispatcher` (orchestration) + `PostTranscodeDispositionDecider` (pure decision) |
| `dict` returns + string-typed dispositions (LSP / type safety) | All | `CommandSpec`, `Disposition`, `KnobOverrides`, `JobResult` value objects |

---

## Live bugs closed (by phase)

| Bug | Phase | How |
|---|---|---|
| **BUG-0050** AdaptiveQualityService NameError | 1 | `RetranscodeDecider.Decide(PreviousAttempt: Attempt) -> Decision` is a pure function with typed inputs. No `FilePath` reference, no swallowed NameError. Old file deleted in same commit. |
| **BUG-0048** Remux missing -f mp4 -movflags +faststart | 2 | `RemuxShape.Build()` emits these unconditionally (they're invariants of the shape, not optional flags). Old `_BuildRemuxShape` deleted. |
| **BUG-0049** emit-side contract | 2 | `AudioFilterBuilder` ALWAYS emits linear-mode loudnorm when given gainable inputs; raises typed `UngainablePeakError` (not bare `RuntimeError`) when inputs are ungainable. Caller (`TranscodeJobProcessor`) catches typed error and routes job to deferral. Admission gate (deferred C6 of legacy-audio-damage-accounting) is a separate small follow-up directive after Phase 1. |
| **BUG-0051** ProcessRemuxQueueService AttributeError | 3 | Class deleted entirely. `RemuxJobProcessor` is built by composition root with `self.DatabaseManager = injected_db` and never composes a second service. No surface for the AttributeError to exist on. |

**Prerequisite hotfixes (NOT in this directive):**
- BUG-0052 PathStorage shim → 1 small directive, BEFORE Phase 1
- BUG-0053 TestMediaProbeUsesPath SELECT → 1 line, same directive as BUG-0052

---

## Delivery phases

### Phase 1 — ST7 Disposition vertical (closes BUG-0050)

**Builds:**
- `Features/QualityTesting/Disposition/PostTranscodeDispositionDecider.py` (pure function class)
- `Features/QualityTesting/Disposition/Disposition.py` (value object)
- `Features/QualityTesting/Disposition/DispositionDispatcher.py`
- `Features/QualityTesting/Disposition/RetryBudgetService.py`
- `Features/QualityTesting/Disposition/RetranscodeDecider.py`
- `Features/QualityTesting/Disposition/ComplianceFailureRecorder.py`
- `Features/QualityTesting/Disposition/AttemptCleanupService.py`
- `Features/TranscodeJob/Adjustments/AdjustmentCalculator.py` (interface)
- `Features/TranscodeJob/Adjustments/CrfAdjustmentCalculator.py`
- `Features/TranscodeJob/Adjustments/AdjustmentRegistry.py`
- `Tests/Contract/TestDispositionDecider.py` (pure-function tests)
- `Tests/Contract/TestRetranscodeDecider.py`
- `Tests/Contract/TestRetryBudgetService.py`

**Modifies:**
- `Features/QualityTesting/PostTranscodeDispositionService.py` — slimmed to thin coordinator OR fully replaced (decide during implementation)
- `Features/TranscodeJob/ProcessTranscodeQueueService.py` — `DispatchDisposition` rewired to call new dispatcher
- `Scripts/SQLScripts/AddRetryBudgetColumn.py` (NEW, R11-idempotent if MaxRequeueAttempts not present)

**Deletes:**
- `Features/TranscodeJob/AdaptiveQualityService.py`

**Verification:**
- Pure-function tests pass for all decision logic
- Integration: a completed transcode attempt routes through new dispatcher and produces the same Disposition outcome as before for ≥10 representative attempt rows (golden-master test)
- BUG-0050 NameError no longer appears in Logs after deployment

### Phase 2 — ST6 Emit primitives + shape layer (closes BUG-0048, BUG-0049 emit)

**Builds:**
- `Features/TranscodeJob/Emit/CommandSpec.py` (value object)
- `Features/TranscodeJob/Emit/ResolutionCalculator.py`
- `Features/TranscodeJob/Emit/OutputFilenameBuilder.py`
- `Features/TranscodeJob/Emit/CodecParameterAssembler.py`
- `Features/TranscodeJob/Emit/AudioFilterBuilder.py`
- `Features/TranscodeJob/Emit/VideoFilterBuilder.py`
- `Features/TranscodeJob/Emit/AudioCodecArgsBuilder.py`
- `Features/TranscodeJob/Emit/UngainablePeakError.py` (typed exception)
- `Features/TranscodeJob/Emit/MediaProbeAdapter.py`
- `Features/TranscodeJob/Emit/SystemCapabilityProbe.py`
- `Features/TranscodeJob/Emit/EncodeShape.py` (interface)
- `Features/TranscodeJob/Emit/TranscodeShape.py`
- `Features/TranscodeJob/Emit/RemuxShape.py`
- `Features/TranscodeJob/Emit/SubtitleFixShape.py`
- `Features/TranscodeJob/Emit/EncodeShapeRegistry.py`
- `Features/TranscodeJob/encode-emit.feature.md` (R13 — created at DELIVERING of Phase 2; until then content in directive)
- Contract tests: per primitive + per shape

**Modifies:**
- `Features/TranscodeJob/ProcessTranscodeQueueService.BuildTranscodeCommand` — rewires to call `ShapeRegistry.Get(Job.ProcessingMode).Build(...)`. Thin adapter; survives until Phase 3.

**Deletes:**
- `Models/CommandBuilder.py`
- The 3 duplicated filename methods in ProcessTranscodeQueueService

**Verification:**
- Per-primitive unit tests pass
- Shape tests: each `*.Build()` call produces a `CommandSpec` that, executed via ffmpeg, produces output media equivalent to the pre-refactor command (golden-master byte-tolerant)
- BUG-0048: synthetic Remux job produces command containing `-f mp4 -movflags +faststart`
- BUG-0049 (emit-side): synthetic gainable file produces linear-mode loudnorm; synthetic ungainable raises `UngainablePeakError` (not bare RuntimeError)
- 1 successful Remux completes end-to-end through the new shape

### Phase 3 — ST6 Worker loop cutover (closes BUG-0051)

**Builds:**
- `Features/TranscodeJob/Worker/WorkerLoopService.py`
- `Features/TranscodeJob/Worker/JobProcessor.py` (interface)
- `Features/TranscodeJob/Worker/TranscodeJobProcessor.py`
- `Features/TranscodeJob/Worker/RemuxJobProcessor.py`
- `Features/TranscodeJob/Worker/SubtitleFixJobProcessor.py`
- `Features/TranscodeJob/Worker/TestVariantJobProcessor.py`
- `Features/TranscodeJob/Worker/JobProcessorRegistry.py`
- `Features/TranscodeJob/Worker/EncodeExecutor.py`
- `Features/TranscodeJob/Worker/AttemptRecordService.py`
- `Features/TranscodeJob/Worker/TemporaryFilePathsService.py`
- `Features/TranscodeJob/Worker/LocalStagingAdapter.py`
- `Features/TranscodeJob/Worker/StuckJobMonitor.py`
- `Features/TranscodeJob/Worker/ProcessSupervisor.py`
- `Features/TranscodeJob/Worker/JobResult.py` (value object)
- `Composition/WorkerCompositionRoot.py`
- `Features/TranscodeJob/worker-loop.feature.md` (R13)
- Contract tests per service

**Modifies:**
- `WorkerService/Main.py` — instantiates `WorkerCompositionRoot` instead of `ProcessTranscodeQueueService` + `ProcessRemuxQueueService` pair

**Deletes:**
- `Features/TranscodeJob/ProcessTranscodeQueueService.py`
- `Features/TranscodeJob/ProcessRemuxQueueService.py`

**Verification:**
- Worker shard runs end-to-end on `larry LXC 218` (NVENC + Remux + SubtitleFix smoke)
- `SELECT COUNT(*) FROM Logs WHERE ClassName='ProcessRemuxQueueService' AND CreatedAt > <cutover_time>` returns 0 (class is gone)
- BUG-0051 AttributeError signature does not appear in Logs post-cutover (1-week window)
- Live workers process at least 1 Transcode, 1 Remux, 1 SubtitleFix successfully

### Phase 4 — Cleanup + promotion

**Modifies:**
- Promote criteria sections from directive doc → `encode-emit.feature.md`, `worker-loop.feature.md`, `disposition.feature.md` (R13)
- Update `transcode.flow.md` ST6/ST7 stage detail + seam table to point at new class names
- Replace stale prose in `command-builder.feature.md` (or delete the file if fully superseded)
- Final R15 anchors on all edited def/class

**Deletes:**
- Phase 2's thin adapter in (now-gone) ProcessTranscodeQueueService.BuildTranscodeCommand — already deleted in Phase 3
- `command-builder.feature.md` if superseded

**Verification:**
- `grep -r "from Models.CommandBuilder" .` returns 0 hits
- `grep -r "ProcessTranscodeQueueService\|ProcessRemuxQueueService\|AdaptiveQualityService" --include='*.py' .` returns 0 production hits (test references may remain)
- Directive doc final size ≤ 110% of IMPLEMENTING-snapshot (R14 size guard)
- Every new file has an R15 anchor + colocated feature/flow ref

---

## Verification strategy

**Per phase:**
1. **Unit tests** for every domain primitive (pure functions; trivially testable)
2. **Contract tests** under `Tests/Contract/` for every interface; assert producer → consumer round-trip
3. **Golden-master tests** comparing pre-refactor vs post-refactor outputs:
   - CommandSpec.Command byte-diff allowed only on the lines that BUG-0048 fixes
   - Disposition decisions byte-identical for ≥10 representative attempts
4. **Live smoke** on `larry LXC 218`: one shard runs each job type successfully through the new code
5. **Log scan** after cutover: previously-firing exception signatures (BUG-0048-0051) no longer appear

**Cross-phase invariants:**
- Hooks never fire during the directive lifetime (R1, R12, R13, R14, R15 specifically — these are the ones a code-shape mistake would trip)
- `py -m pytest Tests/Contract/TestClaimAuthority.py` passes after every commit
- DB schema delta is additive only (`\d` before/after shows new columns only, no drops)

---

## Risk + rollback

**Phase 1 risk:** disposition logic regression on a live attempt mid-flight. **Mitigation:** golden-master test pre-cutover; commits are atomic per file replacement; revert = `git revert <phase1 commits>` and old `AdaptiveQualityService.py` is restored.

**Phase 2 risk:** new shape emits an FFmpeg argv that fails. **Mitigation:** thin adapter retains the OLD `_BuildTranscodeShape` / `_BuildRemuxShape` paths until Phase 3 — Phase 2 can be reverted by toggling the adapter to use old paths (1-line config or env var). **Cleanup:** adapter removed in Phase 3.

**Phase 3 risk:** worker loop cutover breaks all transcoding. **Mitigation:** cutover happens on ONE worker shard first (larry's `mediavortex-worker-1-1`); other 7 shards stay on old code by running a previous container image until smoke clears. **Rollback:** rebuild old image; restart shards.

**Phase 4 risk:** none beyond doc-staleness; reversible.

---

## Operator inputs needed before Phase 1 starts

1. **Prerequisite hotfixes (DECIDED — confirm or override):** Ship BUG-0052 (PathStorage) + BUG-0053 (TestMediaProbeUsesPath SELECT) as a small `pre-perfect-solid-fixups` directive BEFORE Phase 1. Rationale: folding hotfixes into Phase 1's first commit pollutes the SOLID-refactor scope; standalone pre-fix keeps the SOLID directive's commit history clean and gets workers bootable on fresh containers immediately.
2. **80 ungainable rows currently queued (DECIDED — confirm or override):** Leave them. They'll fail through Phase 2 producing 80 typed `UngainablePeakError` log entries — that's useful debugging signal for the deferred admission-gate follow-up directive (lets us see WHICH files slipped past). Zero audio damage either way (the RuntimeError / typed error never reaches output). SQL purge is reversible if you change your mind.
3. **Single-shard canary host at Phase 3 (OPERATOR DECISION):** Need you to pick which worker shard on larry LXC 218 is safe to cut over first. I don't have visibility into which shard's current workload is least critical.

---

## Open questions

None at design level. Implementation-time decisions:

- **Phase 1**: Whether to keep `PostTranscodeDispositionService` as a thin facade vs delete it entirely (TBD by code shape post-extraction)
- **Phase 2**: Whether `RemuxShape` and `SubtitleFixShape` need their own filter builders or can share `AudioFilterBuilder` (TBD by how many audio decisions branch per shape)
- **Phase 3**: Whether `TestVariantJobProcessor` is its own strategy or composes `TranscodeJobProcessor` (TBD by how much variant orchestration overlaps the base transcode flow)

---

## Definition of done

The directive is COMPLETE when:
1. Every box in the target architecture diagram exists as a file in the repo
2. The five listed deletions are done (`Models/CommandBuilder.py`, `ProcessTranscodeQueueService.py`, `ProcessRemuxQueueService.py`, `AdaptiveQualityService.py`, plus PostTranscodeDispositionService refactor)
3. Every class has a one-line stated responsibility; no class needs "and" to describe it
4. `WorkerCompositionRoot` is the only file naming concrete dependency classes (verifiable via grep)
5. All four live bugs (BUG-0048, 0049 emit, 0050, 0051) verified closed via log scan + smoke
6. Contract tests for every interface exist under `Tests/Contract/`
7. No hook rejection appears in `.claude/.refusal-state.json` for any commit landed under this directive's slug
8. `transcode.flow.md` ST6 + ST7 sections + seam table reflect the new class names and seams
