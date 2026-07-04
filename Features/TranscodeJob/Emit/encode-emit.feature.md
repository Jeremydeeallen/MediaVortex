# ST6 Encode Emit Layer

**Slug:** encode-emit

## What It Does

Owns the ffmpeg argv construction for every job type the worker can run. One entry point `CommandComposer.Build(MediaFile, Job, Context)` derives a `Plan{VideoOp, AudioOp, SubtitleOp, ContainerOp}` from `Job.ProcessingMode` via `PlanFactory` and composes four slot services in fixed order: `VideoSlot` (`Reencode` NVENC-VBR / QSV-ICQ / SVT-AV1 or `Copy` stream-copy + hvc1 tag), `AudioSlot` (`Reencode` 2-track Original+DialogBoost via `AudioFilterEmitter.EmitTracks`), `SubtitleSlot` (MP4 target -> `-map 0:s? -c:s mov_text`; MKV target -> `-map 0:s? -c:s copy`; image-based PGS/DVB/DVD subs targeted to MP4 -> `[]` + WARN), `ContainerSlot` (`Mp4` -> `-f mp4 -movflags +faststart`). Every composition produces a typed `CommandSpec` value object. Structural invariants: (1) Mp4 output ALWAYS emits `-f mp4 -movflags +faststart`; (2) `AudioSlot._EmitReencode` raises `AudioPolicyUnresolvedError` on missing Policy / empty Blocks -- no `-c:a copy` fallback; (3) `SubtitleSlot.Emit` fires on every Plan path -- fixes BUG-0083 (subtitle-drop across ~27127 Replace attempts).

## Workflows

| #  | User action | Surface element | Handler | Backing class.method |
|----|-------------|-----------------|---------|----------------------|
| W1 | Worker claims a Transcode job | (internal -- `ProcessTranscodeQueueService.BuildTranscodeCommand`) | CommandComposer.Build with `Plan{VideoOp=Reencode, AudioOp=Reencode, SubtitleOp=Preserve, ContainerOp=Mp4}` | `Features/TranscodeJob/Emit/CommandComposer.Build` |
| W2 | Worker claims a Remux / Quick / AudioFix job | (internal -- `WorkerLoopService`) | CommandComposer.Build with `Plan{VideoOp=Copy, AudioOp=Reencode, SubtitleOp=Preserve, ContainerOp=Mp4}` | `Features/TranscodeJob/Emit/CommandComposer.Build` |
| W3 | Worker claims a SubtitleFix job | (internal -- `WorkerLoopService`) | CommandComposer.Build with `Plan{VideoOp=Copy, AudioOp=Reencode, SubtitleOp=Preserve, ContainerOp=Mp4}` (SubtitleSlot decides codec by TargetContainer) | `Features/TranscodeJob/Emit/CommandComposer.Build` |
| W4 | Worker runs ffprobe pre-flight | (internal -- composer build) | MediaProbeAdapter wraps FFmpegAnalysisService.AnalyzeMediaFile | `Features/TranscodeJob/Emit/MediaProbeAdapter.RunAnalysis` |
| W5 | Worker resolves max CPU thread count | (internal -- worker init) | SystemCapabilityProbe.GetMaxCpuThreads | `Features/TranscodeJob/Emit/SystemCapabilityProbe.GetMaxCpuThreads` |

## Success Criteria

C1. **CommandSpec is a typed frozen value object.** `Features/TranscodeJob/Emit/CommandSpec.py` defines `@dataclass(frozen=True) class CommandSpec(Command: str, OutputPath: str)`. `CommandComposer.Build` returns `Optional[CommandSpec]` (None on refusal). Verifiable: `Tests/Contract/TestCommandSpec.py`.

C2. **ResolutionCalculator owns target-resolution + scale-filter math.** Pure value computation, no DB, no logging, no class state beyond the methods. `CalculateScaleFilter` is a thin facade over `WidthAnchoredScalePolicy` (see `resolution-types.C3`): builds a `Resolution` via `Resolution.FromAny`, resolves the target tier via `ResolutionTierRegistry.FromCategory`, emits `Decision.AsFfmpegArg()` (or `None`). Verifiable: `Tests/Contract/TestResolutionCalculator.py`.

C3. **OutputFilenameBuilder owns filename + path normalization.** `-mv.mp4.inprogress` convention preserved; `-mv-mv` collapse via `CollapseMvSuffix`. Verifiable: `Tests/Contract/TestOutputFilenameBuilder.py`.

C4. **VideoSlot owns video-track argv emission.** `Emit(Op, MediaFile, ProfileSettings, CodecParameters, ScaleFilter, MaxCpuThreads)`. `Op='Copy'` emits `-map 0:v:0 -c:v copy` plus `-tag:v hvc1` on hevc source. `Op='Reencode'` emits `-map 0:v:0 -c:v <codec>` + `-threads` + codec-specific rate-control args (NVENC VBR reads `ProfileThresholds.TargetKbps + MaxBitrateMultiplier`; NVENC CQ reads `Quality`; QSV VBR reads `TargetKbps`; QSV ICQ reads `IcqQ`; SVT-AV1 delegates to `SvtAv1EncoderArgsStrategy`) + video filter + film-grain + pix-fmt. Verifiable: `Tests/Contract/TestCommandComposer.py::test_video_slot_*`.

C5. **AudioSlot owns audio-track argv emission.** `Emit(Op, MediaFile, Context)` returns `AudioEmission(InputArgs, StreamArgs)`. `Op='Reencode'` reads `AudioPolicyResolver.GetEffectivePolicy(MediaFile)` + `AudioFilterEmitter.EmitTracks(...)` (2-track Original + DialogBoost). Missing `Policy` OR empty `Blocks` raises `AudioPolicyUnresolvedError` -- no `-c:a copy` fallback, no `ProfileAudioCeiling` reencode fallback. `Op='Copy'` emits `-map 0:a? -c:a copy`. Verifiable: `Tests/Contract/TestCommandComposer.py::test_audio_slot_*` + `Tests/Contract/TestAudioPipelineNoSilentFallback.py`.

C6. **VideoFilterBuilder owns yadif + scale composition.** Pure value computation. yadif applied only when `IsInterlaced=True`. Verifiable: `Tests/Contract/TestVideoFilterBuilder.py`.

C7. **MediaProbeAdapter injects FFprobePath via ctor.** No live discovery in the adapter. `ProcessTranscodeQueueService` passes its per-worker FFprobePath at composition time. Wraps `FFmpegAnalysisService.AnalyzeMediaFile`. Verifiable: `Tests/Contract/TestMediaProbeAdapter.py`.

C8. **SystemCapabilityProbe isolates OS lookups.** `GetMaxCpuThreads()` returns `os.cpu_count()` or 1; no other OS calls leak into domain code. Verifiable: `Tests/Contract/TestSystemCapabilityProbe.py`.

C9. **Plan tuple derived by PlanFactory from ProcessingMode.** `Features/TranscodeJob/Emit/Plan.py` defines `@dataclass(frozen=True) class Plan(VideoOp, AudioOp, SubtitleOp, ContainerOp)`. `PlanFactory.FromProcessingMode('Transcode')` -> `(Reencode, Reencode, Preserve, Mp4)`. `PlanFactory.FromProcessingMode('Remux'|'Quick'|'AudioFix'|'SubtitleFix')` -> `(Copy, Reencode, Preserve, Mp4)`. Unknown mode raises `ValueError`. Verifiable: `Tests/Contract/TestCommandComposer.py::test_plan_factory_*`.

C10. **ContainerSlot emits `-f mp4 -movflags +faststart` unconditionally on Mp4 target.** Structural invariant, not optional. Closes the BUG-0048 class: every Mp4 argv contains both flags regardless of Op. Verifiable: `Tests/Contract/TestCommandComposer.py::test_container_slot_mp4_emits_faststart`.

C11. **SubtitleSlot always fires and picks codec by target container.** `Features/TranscodeJob/Emit/Slots/SubtitleSlot.py`. MP4 target -> `-map 0:s? -c:s mov_text`; MKV target -> `-map 0:s? -c:s copy`; image-only PGS/DVB/DVD/xsub targeted to MP4 -> `[]` + WARN naming dropped codec; image+text mixed targeted to MP4 -> `-map 0:s? -c:s mov_text` + WARN. Fixes BUG-0083 (subtitle-drop across every Reencode / Remux / AudioFix / Quick / SubtitleFix path). Verifiable: `Tests/Contract/TestSubtitleSlot.py` + `Tests/Contract/TestCommandComposer.py::test_subtitle_slot_always_fires`.

C12. **CommandComposer composes 4 slots via constructor injection.** `CommandComposer.__init__` accepts `VideoSlot / AudioSlot / SubtitleSlot / ContainerSlot / ResolutionCalculator / OutputFilenameBuilder / MediaProbeAdapter / PlanFactory` (defaults to production instances). `Build(MediaFile, Job, Context)` derives Plan, resolves OutputPath + ScaleFilter, calls each slot in fixed order, returns `CommandSpec`. NVENC dispatch via `ProfileSettings.UseNvidiaHardware=1` -> `av1_nvenc`; else `ProfileSettings.Codec` (`av1_qsv` / `libsvtav1`). Verifiable: `Tests/Contract/TestCommandComposer.py`.

## Seams

| ID | Seam | Producer | Wire shape | Consumer expects | Verification |
|---|---|---|---|---|---|
| S1 | `Strategy.BuildCommand -> CommandComposer.Build` | 5 Strategies (Transcode/Remux/Quick/AudioFix/SubtitleFix) | `(MediaFile, Job, Context: Dict)` | `Optional[CommandSpec]` (None on refusal) | `Tests/Contract/TestCommandComposer.py` |
| S2 | `CommandComposer.Build -> PlanFactory.FromProcessingMode` | CommandComposer | `Job.ProcessingMode: str` | `Plan(VideoOp, AudioOp, SubtitleOp, ContainerOp)`; unknown mode raises `ValueError` | `Tests/Contract/TestCommandComposer.py::test_plan_factory_*` |
| S3 | `CommandComposer -> 4 slots (fixed order)` | CommandComposer | Plan tuple | VideoSlot + AudioSlot + SubtitleSlot + ContainerSlot each emit their argv fragment | `Tests/Contract/TestCommandComposer.py::test_slot_ordering` |
| S4 | `ContainerSlot('Mp4') -> argv invariants` | ContainerSlot | Op string | `['-f', 'mp4', '-movflags', '+faststart']` | `Tests/Contract/TestCommandComposer.py::test_container_slot_mp4_emits_faststart` |
| S5 | `AudioFilterEmitter.EmitTracks -> raise on empty` | AudioFilterEmitter | `(MediaFile, Policy, AudioStreams, DemucsPremixPath, ...)` | `List[TrackBlock]` (Track 0 always; Track 1 iff premix present + vocals RMS > fallback); empty raises `AudioPolicyUnresolvedError` | `Tests/Contract/TestAudioFilterEmitter.py` |
| S6 | `MediaProbeAdapter.RunAnalysis -> FFmpegAnalysisService` | MediaProbeAdapter | `(InputPath: str)` | `Optional[Analysis]` (None on subprocess failure -- never propagates) | `Tests/Contract/TestMediaProbeAdapter.py` |
| S7 | `SubtitleSlot.Emit -> argv` | SubtitleSlot | `(TargetContainer, SubtitleFormats)` | MP4 -> `['-map', '0:s?', '-c:s', 'mov_text']`; MKV -> `['-map', '0:s?', '-c:s', 'copy']`; image-only-to-MP4 -> `[]` + WARN | `Tests/Contract/TestSubtitleSlot.py` |

## Status

ACTIVE. Single `CommandComposer.Build(MediaFile, Job, Context)` owns every ffmpeg argv construction. Four Slot services (`VideoSlot`, `AudioSlot`, `SubtitleSlot`, `ContainerSlot`) compose in fixed order keyed on `Plan{VideoOp, AudioOp, SubtitleOp, ContainerOp}` derived from `Job.ProcessingMode` via `PlanFactory`. Landed under `transcode-flow-canonical` C17.

## Files

| File | Role |
|------|------|
| `Features/TranscodeJob/Emit/CommandSpec.py` | C1 value object |
| `Features/TranscodeJob/Emit/ResolutionCalculator.py` | C2 |
| `Features/TranscodeJob/Emit/OutputFilenameBuilder.py` | C3 |
| `Features/TranscodeJob/Emit/VideoFilterBuilder.py` | C6 |
| `Features/TranscodeJob/Emit/MediaProbeAdapter.py` | C7 |
| `Features/TranscodeJob/Emit/SystemCapabilityProbe.py` | C8 |
| `Features/TranscodeJob/Emit/Plan.py` | C9 (Plan + PlanFactory) |
| `Features/TranscodeJob/Emit/CommandComposer.py` | C12 |
| `Features/TranscodeJob/Emit/Slots/VideoSlot.py` | C4 |
| `Features/TranscodeJob/Emit/Slots/AudioSlot.py` | C5 |
| `Features/TranscodeJob/Emit/Slots/SubtitleSlot.py` | C11 |
| `Features/TranscodeJob/Emit/Slots/ContainerSlot.py` | C10 |
| `Features/TranscodeJob/Emit/EncoderArgsStrategies/IEncoderArgsStrategy.py` | C4 ABC (VideoSlot delegates SVT-AV1) |
| `Features/TranscodeJob/Emit/EncoderArgsStrategies/SvtAv1EncoderArgsStrategy.py` | C4 SVT-AV1 fallback |
| `Tests/Contract/TestCommandSpec.py` | C1 |
| `Tests/Contract/TestResolutionCalculator.py` | C2 |
| `Tests/Contract/TestOutputFilenameBuilder.py` | C3 |
| `Tests/Contract/TestVideoFilterBuilder.py` | C6 |
| `Tests/Contract/TestMediaProbeAdapter.py` | C7 |
| `Tests/Contract/TestSystemCapabilityProbe.py` | C8 |
| `Tests/Contract/TestSubtitleSlot.py` | C11 |
| `Tests/Contract/TestCommandComposer.py` | C4/C5/C9/C10/C12 |
| `Tests/Contract/TestNoLegacyResidue.py` | grep-fence retired symbols to 0 in production tree |
| `Tests/Contract/TestAudioPipelineNoSilentFallback.py` | C5 no-fallback invariant on AudioSlot |
