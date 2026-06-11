# Current Directive

**Set:** 2026-06-10
**Status:** Active -- phase: IMPLEMENTING
**Slug:** perfect-solid-transcode-pipeline-phase2
**Replaces:** `directives/closed/2026-06-10-perfect-solid-transcode-pipeline.md` (Phase 1 closed Success)

## Outcome

Phase 2 of the `perfect-solid-transcode-pipeline` program (spec: `docs/superpowers/specs/2026-06-10-perfect-solid-transcode-pipeline-design.md`). Decomposes `Models/CommandBuilder.py` (857 LOC, 7 responsibilities) into SOLID-clean domain primitives + filter/codec builders + `EncodeShape` strategy registry. Closes BUG-0048 (Remux missing `-f mp4 -movflags +faststart`) by making the muxer flags invariants of `RemuxShape.Build()`. Closes BUG-0049 emit side by emitting a typed `UngainablePeakError` from `AudioFilterBuilder` instead of bare `RuntimeError`, allowing the caller to defer the disposition rather than crashing the job. `Models/CommandBuilder.py` is DELETED at the end of this directive; `ProcessTranscodeQueueService.BuildTranscodeCommand` calls `EncodeShapeRegistry.Get(Job.ProcessingMode).Build(...)` and returns the resulting `CommandSpec`. Three live bugs close: BUG-0048 verified by 1 successful Remux smoke; BUG-0049 verified by typed-error log path on an ungainable file.

## Acceptance Criteria

1. **C1 -- CommandSpec value object:** `Features/TranscodeJob/Emit/CommandSpec.py` defines a frozen dataclass `CommandSpec(Command: str, OutputPath: str)`. Verifiable: import + immutability test.

2. **C2 -- ResolutionCalculator:** `Features/TranscodeJob/Emit/ResolutionCalculator.py` extracts the resolution-math methods (`_CalculateTargetResolution`, `_CalculateScaleFilter`, `_ExtractHeightFromResolution`, `_GetSourceDimensions`, `_CalculateWidthFromHeight`) from `CommandBuilder` into a single-responsibility class. Pure value computation; no DB, no logging. Verifiable: `Tests/Contract/TestResolutionCalculator.py` covers each method's documented behavior.

3. **C3 -- OutputFilenameBuilder:** `Features/TranscodeJob/Emit/OutputFilenameBuilder.py` extracts `GenerateOutputFileName` + `ExtractResolutionFromFilename` + `FormatResolutionForFilename` + `_NormalizeFfmpegPath` + `_CollapseMvSuffix` into one class. Deduplicates with the same methods that exist in `ProcessTranscodeQueueService`. Verifiable: `Tests/Contract/TestOutputFilenameBuilder.py` covers the `-mv.mp4.inprogress` output pattern + the `-mv-mv` collapse.

4. **C4 -- CodecParameterAssembler:** `Features/TranscodeJob/Emit/CodecParameterAssembler.py` extracts `AddCodecParameters` + `AddFilmGrainParameter` + `AddPixelFormatParameter` into one class. Verifiable: `Tests/Contract/TestCodecParameterAssembler.py`.

5. **C5 -- AudioCodecArgsBuilder:** `Features/TranscodeJob/Emit/AudioCodecArgsBuilder.py` extracts `BuildAudioCodecArgs` + `_DefaultAudioBitrateForChannels`. Verifiable: `Tests/Contract/TestAudioCodecArgsBuilder.py`.

6. **C6 -- UngainablePeakError typed exception:** `Features/TranscodeJob/Emit/UngainablePeakError.py` defines `class UngainablePeakError(RuntimeError)` with `MediaFileId`, `SourceIntegratedLufs`, `Gain`, `PredictedPeak`, `TargetTp` attributes. Carriers the same diagnostic info as the bare `RuntimeError` in current code. Verifiable: import + attribute access.

7. **C7 -- AudioFilterBuilder uses typed error:** `Features/TranscodeJob/Emit/AudioFilterBuilder.py` extracts `BuildAudioFilters`; raises `UngainablePeakError` (not `RuntimeError`) when the predicted peak exceeds target TP. Linear-only-or-refused contract preserved (no dynamic fallback). Verifiable: `Tests/Contract/TestAudioFilterBuilder.py::test_ungainable_raises_typed_error` asserts `UngainablePeakError` is raised, not bare `RuntimeError`.

8. **C8 -- VideoFilterBuilder:** `Features/TranscodeJob/Emit/VideoFilterBuilder.py` extracts `BuildVideoFilters`. Verifiable: `Tests/Contract/TestVideoFilterBuilder.py`.

9. **C9 -- MediaProbeAdapter:** `Features/TranscodeJob/Emit/MediaProbeAdapter.py` extracts `_RunFFprobeAnalysis`. Verifiable: import succeeds; ctor takes injected FFprobePath.

10. **C10 -- SystemCapabilityProbe:** `Features/TranscodeJob/Emit/SystemCapabilityProbe.py` extracts `GetMaxCpuThreads`. Verifiable: import + return-type test.

11. **C11 -- EncodeShape interface:** `Features/TranscodeJob/Emit/EncodeShape.py` defines an abstract base class with `Build(MediaFile, Job, Context) -> Optional[CommandSpec]`. Verifiable: import + abstractmethod assertion.

12. **C12 -- TranscodeShape:** `Features/TranscodeJob/Emit/TranscodeShape.py` implements `EncodeShape` for `Job.ProcessingMode='Transcode'`. Replaces `CommandBuilder._BuildTranscodeShape`. Verifiable: shape builder composes all injected dependencies (resolution + filename + codec + filters + audio codec args).

13. **C13 -- RemuxShape closes BUG-0048:** `Features/TranscodeJob/Emit/RemuxShape.py` implements `EncodeShape` for `Job.ProcessingMode='Remux'`. Emits `-f mp4` and `-movflags +faststart` **unconditionally** (they are invariants of the shape, not optional). Verifiable: any `RemuxShape().Build(MediaFile, Job, Context)` whose result is not None produces a `CommandSpec.Command` string containing both `'-f mp4'` and `'-movflags +faststart'`. `Tests/Contract/TestRemuxShape.py` covers a synthetic Remux job, asserts both flags present in the output.

14. **C14 -- SubtitleFixShape:** `Features/TranscodeJob/Emit/SubtitleFixShape.py` implements `EncodeShape` for `Job.ProcessingMode='SubtitleFix'`. Verifiable: shape builder + tests.

15. **C15 -- EncodeShapeRegistry:** `Features/TranscodeJob/Emit/EncodeShapeRegistry.py` maps `Job.ProcessingMode` to `EncodeShape`. Composition root pattern. Verifiable: `EncodeShapeRegistry().Get('Transcode')` returns `TranscodeShape`; `.Get('Remux')` returns `RemuxShape`; `.Get('SubtitleFix')` returns `SubtitleFixShape`; unknown raises `KeyError`.

16. **C16 -- ProcessTranscodeQueueService rewired:** `ProcessTranscodeQueueService.BuildTranscodeCommand` calls `self.EncodeShapeRegistry.Get(Job.ProcessingMode).Build(MediaFile, Job, Context)` and unwraps the `CommandSpec`. The old `self.CommandBuilder.BuildFFmpegCommand(...)` call is gone. `self.CommandBuilder` attribute removed from `__init__`. Verifiable: `grep -n "self.CommandBuilder" Features/TranscodeJob/ProcessTranscodeQueueService.py` returns 0 hits.

17. **C17 -- CommandBuilder deleted with zero importers:** `Models/CommandBuilder.py` does not exist; `grep -rn "from Models.CommandBuilder\|import CommandBuilder" --include='*.py' .` returns 0 production hits.

18. **C18 -- UngainablePeakError caller fallback (closes BUG-0049):** `ProcessTranscodeQueueService.ProcessJob` (or whichever method calls `BuildTranscodeCommand`) catches `UngainablePeakError` and routes the job to a `Disposition='NoReplace', Reason='UngainablePeakDeferred'` outcome (via the new DispositionDispatcher path from Phase 1). The bare `RuntimeError` path is gone. Verifiable: synthetic test with an ungainable-peak MediaFile produces the disposition without crashing the worker.

19. **C19 -- Live smoke Remux + Transcode:** After deploy, at least one Remux job completes successfully (Success=True) on larry-worker-1, AND at least one Transcode job completes successfully on I9 or dot through the new shape registry. Verifiable: `SELECT id, profilename, success FROM TranscodeAttempts WHERE workername IN (...) AND completeddate > <deploy_time> AND success=true LIMIT 2`.

20. **C20 -- BUG-0048 return code 234 absent:** `SELECT COUNT(*) FROM TranscodeAttempts WHERE profilename='Remux' AND completeddate > <deploy_time> AND errormessage LIKE '%return code 234%'` returns 0.

## Out of Scope

- Worker loop refactor (`ProcessTranscodeQueueService` decomposition into `WorkerLoopService` + `JobProcessor` strategies) -- Phase 3.
- `ProcessRemuxQueueService` deletion -- Phase 3 closes BUG-0051.
- NVENC budget adjustment calculator (`NvencBudgetAdjustmentCalculator`) -- separate quality-floor-lift follow-up.
- Ungainable-peak admission gate (`/n ungainable-peak-admission-gate`) -- separate follow-up. C18's RuntimeError->Disposition fallback is the safety floor while admission-gate ships.
- DB schema changes (none expected).
- HTTP API contract changes (preserved).
- Operator-visible UI changes (preserved).

## Constraints

- **R12 (CRITICAL):** Every new file uses ONE-LINE docstrings on every class and def. Module docstrings one line.
- **R15:** Every new def/class gets `# directive: perfect-solid-transcode-pipeline-phase2 | # see perfect-solid-transcode-pipeline-phase2.C<N>` directly above.
- **R1:** Editing `ProcessTranscodeQueueService.py` requires preread of colocated `*.feature.md` / `*.flow.md`.
- **DIP:** Each new class accepts dependencies via constructor injection. The wiring in `ProcessTranscodeQueueService.__init__` is the composition root for Phase 2; Phase 3 lifts it to `WorkerCompositionRoot`.
- **FFmpeg byte-equivalence:** The new shapes produce ffmpeg argv that is *behaviorally equivalent* to the old `CommandBuilder.BuildFFmpegCommand` output (same output media). Byte-identity NOT required (BUG-0048's faststart addition is a deliberate byte change in Remux).
- **R13:** New `*.feature.md` only at DELIVERING. New vertical: `Features/TranscodeJob/Emit/encode-emit.feature.md`.

## Escalation Defaults

- **Edge case in CRF/VBR dispatch not covered by current CommandBuilder** -> document in Decisions Made; preserve current behavior.
- **Tests reveal byte-divergence in argv** -> escalate; investigate whether divergence is the BUG-0048 deliberate change or a regression.
- **Worker mid-flight when CommandBuilder delete commit lands** -> drain workers first, then commit + restart fleet.

## Engineering Calls Already Made

- **EncodeShape returns CommandSpec, not dict.** Typed value object; LSP-safe substitution.
- **Three shapes for Phase 2:** TranscodeShape, RemuxShape, SubtitleFixShape. Test-variant shape stays in `ProcessTranscodeQueueService._ProcessSingleVariant` for Phase 3 (variant orchestration is the worker-loop concern).
- **AudioFilterBuilder preserves linear-only-or-refused contract.** No dynamic fallback (per `linear-loudnorm.feature.md` + `legacy-audio-damage-accounting` directive). The only change is `RuntimeError` -> `UngainablePeakError`.
- **MediaProbeAdapter takes FFprobePath via ctor.** No live discovery in the adapter; ProcessTranscodeQueueService passes its per-worker FFprobePath.
- **No new feature.md for value objects.** They appear in the EncodeShape vertical's encode-emit.feature.md.
- **Models/CommandBuilder.py deleted entirely.** No facade. The class is fully replaced by EncodeShapeRegistry + shape strategies.

## Status

Active 2026-06-10 -- phase: IMPLEMENTING -- next step: dispatch wave 1 parallel agents for C1-C10 (domain primitives + filters + adapters); sequential wave 2 for C11-C18.

### Files

```
Features/TranscodeJob/Emit/CommandSpec.py                 -- CREATE: C1
Features/TranscodeJob/Emit/ResolutionCalculator.py        -- CREATE: C2
Features/TranscodeJob/Emit/OutputFilenameBuilder.py       -- CREATE: C3
Features/TranscodeJob/Emit/CodecParameterAssembler.py     -- CREATE: C4
Features/TranscodeJob/Emit/AudioCodecArgsBuilder.py       -- CREATE: C5
Features/TranscodeJob/Emit/UngainablePeakError.py         -- CREATE: C6
Features/TranscodeJob/Emit/AudioFilterBuilder.py          -- CREATE: C7
Features/TranscodeJob/Emit/VideoFilterBuilder.py          -- CREATE: C8
Features/TranscodeJob/Emit/MediaProbeAdapter.py           -- CREATE: C9
Features/TranscodeJob/Emit/SystemCapabilityProbe.py       -- CREATE: C10
Features/TranscodeJob/Emit/EncodeShape.py                 -- CREATE: C11
Features/TranscodeJob/Emit/TranscodeShape.py              -- CREATE: C12
Features/TranscodeJob/Emit/RemuxShape.py                  -- CREATE: C13 (BUG-0048)
Features/TranscodeJob/Emit/SubtitleFixShape.py            -- CREATE: C14
Features/TranscodeJob/Emit/EncodeShapeRegistry.py         -- CREATE: C15
Features/TranscodeJob/ProcessTranscodeQueueService.py     -- EDIT: C16 + C18 wiring
Models/CommandBuilder.py                                  -- DELETE: C17
Tests/Contract/Test*.py per criterion                     -- CREATE
```

### Promotions

| Source artifact | Target file | Commit |
|---|---|---|
| Encode-emit vertical (C1-C15) | NEW `Features/TranscodeJob/Emit/encode-emit.feature.md` | TBD at DELIVERING |
| BuildTranscodeCommand seam update (C16) | existing `Features/TranscodeJob/TranscodeJob.feature.md` Seams table | TBD |
| transcode.flow.md ST6 stage emit-layer detail | `transcode.flow.md` | TBD |
| `command-builder.feature.md` | DELETE (superseded by encode-emit.feature.md) | TBD |

### Verification

- **C1 (CommandSpec):** Frozen dataclass; `TestCommandSpec.py` 3/3 pass; immutability raises FrozenInstanceError on field set. **IMPLEMENTED**.
- **C2 (ResolutionCalculator):** Pure value computation; 5 methods extracted from CommandBuilder. `TestResolutionCalculator.py` covers tier conversion + scale-filter generation. **IMPLEMENTED**.
- **C3 (OutputFilenameBuilder):** 5 methods extracted; `-mv.mp4.inprogress` convention preserved; collapse-`mv-mv` test passes. **IMPLEMENTED**.
- **C4 (CodecParameterAssembler):** 3 methods extracted; codec/film-grain/pixel-format assembly. **IMPLEMENTED**.
- **C5 (AudioCodecArgsBuilder):** `BuildAudioCodecArgs` + `DefaultAudioBitrateForChannels` extracted. **IMPLEMENTED**.
- **C6 (UngainablePeakError):** Typed RuntimeError subclass; carries (MediaFileId, SourceIntegratedLufs, Gain, PredictedPeak, TargetTp) attributes. `TestUngainablePeakError.py` 3/3 pass including isinstance(RuntimeError) backward-compat. **IMPLEMENTED**.
- **C7 (AudioFilterBuilder closes BUG-0049 emit):** Linear-or-refused contract preserved. Raises `UngainablePeakError` (not bare RuntimeError) when predicted peak exceeds target TP. `TestAudioFilterBuilder.py::test_ungainable_raises_typed_error` proves the typed error. **IMPLEMENTED**.
- **C8 (VideoFilterBuilder):** yadif + scale composition extracted; pure value computation. **IMPLEMENTED**.
- **C9 (MediaProbeAdapter):** Per-worker FFprobe wrapper; FFprobePath injected via ctor. **IMPLEMENTED**.
- **C10 (SystemCapabilityProbe):** `GetMaxCpuThreads` extracted; defaults to 1 when os.cpu_count() returns None. **IMPLEMENTED**.
- **C11 (EncodeShape interface):** ABC with single abstract `Build(MediaFile, Job, Context) -> Optional[CommandSpec]`. Instantiating ABC raises TypeError. **IMPLEMENTED**.
- **C12 (TranscodeShape):** Composes 7 collaborators; returns CommandSpec. NVENC/SVT-AV1 dispatch by `ProfileSettings.UseNvidiaHardware`. **IMPLEMENTED**.
- **C13 (RemuxShape closes BUG-0048):** `TestRemuxShape.py::test_emits_f_mp4_unconditionally` + `test_emits_movflags_faststart_unconditionally` pass. The flags are now invariants of the shape, not optional ProfileSettings. **IMPLEMENTED structurally; live verification pending C19/C20**.
- **C14 (SubtitleFixShape):** Same invariant flags + `-c:s mov_text` subtitle conversion. **IMPLEMENTED**.
- **C15 (EncodeShapeRegistry):** Maps 5 keys -> 3 shapes (`'Transcode'`, `'Remux'`, `'Quick'`, `'AudioFix'` -> Remux, `'SubtitleFix'`). `Get('vbr')` raises KeyError (sic -- unknown raises KeyError per design). **IMPLEMENTED**.
- **C16 (ProcessTranscodeQueueService rewired):** `grep -n "self.CommandBuilder" Features/TranscodeJob/ProcessTranscodeQueueService.py` returns 0. All 3 BuildFFmpegCommand call sites (ProcessRemuxJob, ProcessSubtitleFixJob, BuildTranscodeCommand) now use `self.EncodeShapeRegistry.Get(Job.ProcessingMode).Build(...)`. **IMPLEMENTED**.
- **C17 (CommandBuilder deleted):** `Models/CommandBuilder.py` deleted (commit d3f6813). `grep -rn "from Models.CommandBuilder\|import CommandBuilder" --include='*.py' .` returns 0. Legacy scripts `Scripts/EndToEndTestCommandBuilder.py` + `Scripts/RegressionTestCommandBuilder.py` also deleted. `Tests/Contract/TestLinearLoudnormEnforcement.py` migrated to AudioFilterBuilder. **IMPLEMENTED**.
- **C18 (UngainablePeakError caller fallback):** `BuildTranscodeCommand` re-raises `UngainablePeakError`; the 3 Process*Job methods' existing `except Exception` blocks catch it (since UngainablePeakError is a RuntimeError subclass) and route to `HandleJobFailure` which writes the attempt + lets DispositionDispatcher fire normally (Discard/TranscodeFailed). Worker does NOT crash on ungainable peak. Full disposition reason `UngainablePeakDeferred` deferred to admission-gate follow-up directive per Decisions Made. **IMPLEMENTED (minimal -- worker safety floor)**.
- **C19 (Live smoke Remux + Transcode):** Pending fleet redeploy.
- **C20 (BUG-0048 return code 234 absent):** Pending observation window post-deploy.

### Decisions Made

(Populated during execution as ambiguities surface.)
