# ST6 Encode Emit Layer

**Slug:** encode-emit

## What It Does

Owns the ffmpeg argv construction for every job type the worker can run. Decomposed from the legacy `Models/CommandBuilder.py` god class (857 LOC, 7 responsibilities) into single-responsibility domain primitives, codec/filter builders, external-tool adapters, and three `EncodeShape` Strategy implementations dispatched by a registry. Every shape produces a typed `CommandSpec` value object instead of an ad-hoc dict. Audio emission for every shape routes through `AudioFilterEmitter.EmitTracks` (two-track: Original + Dialog Boost); shapes MUST emit `-i` inputs before any `-map` (ffmpeg parser is order-sensitive). Structural invariants: (1) Remux output ALWAYS emits `-f mp4 -movflags +faststart` regardless of any optional ProfileSettings; (2) no shape carries an `-c:a copy` empty-Blocks fallback -- missing `Policy` or empty `Blocks` raises `AudioPolicyUnresolvedError`.

## Workflows

| #  | User action | Surface element | Handler | Backing class.method |
|----|-------------|-----------------|---------|----------------------|
| W1 | Worker claims a Transcode job | (internal -- `ProcessTranscodeQueueService.BuildTranscodeCommand`) | EncodeShapeRegistry dispatch -> TranscodeShape.Build | `Features/TranscodeJob/Emit/TranscodeShape.Build` |
| W2 | Worker claims a Remux/Quick/AudioFix job | (internal -- `ProcessTranscodeQueueService.ProcessRemuxJob`) | EncodeShapeRegistry dispatch -> RemuxShape.Build (unconditional `-f mp4 +faststart`) | `Features/TranscodeJob/Emit/RemuxShape.Build` |
| W3 | Worker claims a SubtitleFix job | (internal -- `ProcessTranscodeQueueService.ProcessSubtitleFixJob`) | EncodeShapeRegistry dispatch -> SubtitleFixShape.Build | `Features/TranscodeJob/Emit/SubtitleFixShape.Build` |
| W4 | Worker runs ffprobe pre-flight | (internal -- shape build) | MediaProbeAdapter wraps FFmpegAnalysisService.AnalyzeMediaFile | `Features/TranscodeJob/Emit/MediaProbeAdapter.RunAnalysis` |
| W5 | Worker resolves max CPU thread count | (internal -- worker init) | SystemCapabilityProbe.GetMaxCpuThreads | `Features/TranscodeJob/Emit/SystemCapabilityProbe.GetMaxCpuThreads` |

## Success Criteria

C1. **CommandSpec is a typed frozen value object.** `Features/TranscodeJob/Emit/CommandSpec.py` defines `@dataclass(frozen=True) class CommandSpec(Command: str, OutputPath: str)`. Every EncodeShape.Build that returns a non-None result returns a CommandSpec, not a dict. Verifiable: `Tests/Contract/TestCommandSpec.py` 3/3 pass.

C2. **ResolutionCalculator owns target-resolution + scale-filter math.** Pure value computation, no DB, no logging, no class state beyond the methods. `CalculateScaleFilter` is now a thin facade over `WidthAnchoredScalePolicy` (see `resolution-types.C3`): it builds a `Resolution` via `Resolution.FromAny`, resolves the target tier via `ResolutionTierRegistry.FromCategory`, and emits `Decision.AsFfmpegArg()` (or `None`). `Tests/Contract/TestResolutionCalculator.py` covers tier conversion (480p/720p/1080p/2160p), height extraction from `WxH` strings, width-from-height calculation with aspect ratio.

C3. **OutputFilenameBuilder owns filename + path normalization.** Replaces 5 methods that were duplicated between CommandBuilder and ProcessTranscodeQueueService. `-mv.mp4.inprogress` convention preserved. `-mv-mv` collapse via `CollapseMvSuffix`. Verifiable: `Tests/Contract/TestOutputFilenameBuilder.py`.

C4. **CodecParameterAssembler + AudioCodecArgsBuilder own codec arg synthesis.** Three legacy `Add*Parameter` methods + `BuildAudioCodecArgs` + `_DefaultAudioBitrateForChannels` extracted as instance methods. Verifiable: contract tests pass.

C5. **Audio emission routes through `AudioFilterEmitter.EmitTracks`.** Every shape (`TranscodeShape` / `RemuxShape` / `SubtitleFixShape`) reads Demucs premix keys from `Context` (`DemucsPremixPath`, `VocalsRmsDbfs`, `PremixMeasured*`) and forwards them to `EmitTracks`. Empty `Blocks` OR missing `Policy` raises `AudioPolicyUnresolvedError` -- no `-c:a copy` fallback, no `ProfileAudioCeiling` reencode fallback. Verifiable: `Tests/Contract/TestAudioFilterEmitter.py` + `TestRemuxShape.py`.

C6. **VideoFilterBuilder owns yadif + scale composition.** Pure value computation. yadif applied only when `IsInterlaced=True`. Verifiable: `Tests/Contract/TestVideoFilterBuilder.py`.

C7. **MediaProbeAdapter injects FFprobePath via ctor.** No live discovery in the adapter. ProcessTranscodeQueueService passes its per-worker FFprobePath at composition time. Wraps `FFmpegAnalysisService.AnalyzeMediaFile`. Verifiable: code review + `Tests/Contract/TestMediaProbeAdapter.py`.

C8. **SystemCapabilityProbe isolates OS lookups.** `GetMaxCpuThreads()` returns `os.cpu_count()` or 1; no other OS calls leak into domain code. Verifiable: `Tests/Contract/TestSystemCapabilityProbe.py`.

C9. **EncodeShape strategy dispatch via registry.** `EncodeShapeRegistry.__init__` takes a `Dict[str, EncodeShape]`; `.Get(ProcessingMode)` returns the strategy; unknown raises KeyError. Five keys registered by `ProcessTranscodeQueueService._BuildDefaultEncodeShapeRegistry`: `'Transcode'`, `'Remux'`, `'Quick'`, `'AudioFix'`, `'SubtitleFix'`. Verifiable: `Tests/Contract/TestEncodeShapeRegistry.py`.

C10. **RemuxShape emits `-f mp4` + `-movflags +faststart` unconditionally.** These flags are invariants of the shape, not optional ProfileSettings. Closes the BUG-0048 class: every Remux ffmpeg argv contains both flags. Verifiable: `Tests/Contract/TestRemuxShape.py::test_emits_f_mp4_unconditionally` + `test_emits_movflags_faststart_unconditionally`.

C11. **SubtitleFixShape emits the same invariants + `-c:s mov_text`.** ASS/SSA -> mov_text conversion is the SubtitleFix shape's defining transform; container/faststart invariants match Remux. Verifiable: `Tests/Contract/TestSubtitleFixShape.py`.

C12. **TranscodeShape composes 5 collaborators via constructor.** ResolutionCalculator + OutputFilenameBuilder + CodecParameterAssembler + VideoFilterBuilder + MediaProbeAdapter, plus injectable audio seams (Resolver, Emitter, StreamProbe) that default to production instances. Audio emission runs through `AudioFilterEmitter.EmitTracks` (which reads `AudioComplianceRules` per encode). NVENC dispatch via `ProfileSettings.UseNvidiaHardware=1`; SVT-AV1 fallback otherwise. Verifiable: `Tests/Contract/TestTranscodeShape.py`.

## Seams

| ID | Seam | Producer | Wire shape | Consumer expects | Verification |
|---|---|---|---|---|---|
| S1 | `ProcessTranscodeQueueService.BuildTranscodeCommand -> EncodeShapeRegistry.Get` | ProcessTranscodeQueueService | `(ProcessingMode: str)` | `Get` returns `EncodeShape` (raises KeyError on unknown) | `Tests/Contract/TestEncodeShapeRegistry.py` |
| S2 | `EncodeShape.Build -> CommandSpec` | TranscodeShape / RemuxShape / SubtitleFixShape | `(MediaFile, Job, Context: Dict)` | `Optional[CommandSpec]` (None on refusal) | Per-shape contract tests |
| S3 | `RemuxShape.Build -> ffmpeg argv invariants` | RemuxShape | argv string | substring `'-f mp4'` AND substring `'-movflags +faststart'` AND substring `'-c:v copy'` | `Tests/Contract/TestRemuxShape.py` |
| S4 | `AudioFilterEmitter.EmitTracks -> raise on empty` | AudioFilterEmitter | `(MediaFile, Policy, AudioStreams, DemucsPremixPath, ...)` | `List[TrackBlock]` (Track 0 always; Track 1 iff premix present + vocals RMS > fallback); empty raises `AudioPolicyUnresolvedError` | `Tests/Contract/TestAudioFilterEmitter.py` |
| S5 | `MediaProbeAdapter.RunAnalysis -> FFmpegAnalysisService` | MediaProbeAdapter | `(InputPath: str)` | `Optional[Analysis]` (None on subprocess failure -- never propagates) | `Tests/Contract/TestMediaProbeAdapter.py` |

## Status

ACTIVE -- Phase 2 of `perfect-solid-transcode-pipeline` shipped. CommandBuilder god class deleted (857 LOC). 15 new classes + 1 typed error. ~50 contract tests passing. Live in production at commit `d7d815e`.

## Files

| File | Role |
|------|------|
| `Features/TranscodeJob/Emit/CommandSpec.py` | C1 value object |
| `Features/TranscodeJob/Emit/ResolutionCalculator.py` | C2 |
| `Features/TranscodeJob/Emit/OutputFilenameBuilder.py` | C3 |
| `Features/TranscodeJob/Emit/CodecParameterAssembler.py` | C4 |
| `Features/TranscodeJob/Emit/AudioCodecArgsBuilder.py` | C4 (legacy; unused post-two-track) |
| `Features/TranscodeJob/Emit/VideoFilterBuilder.py` | C6 |
| `Features/TranscodeJob/Emit/MediaProbeAdapter.py` | C7 |
| `Features/TranscodeJob/Emit/SystemCapabilityProbe.py` | C8 |
| `Features/TranscodeJob/Emit/EncodeShape.py` | C9 interface |
| `Features/TranscodeJob/Emit/EncodeShapeRegistry.py` | C9 |
| `Features/TranscodeJob/Emit/TranscodeShape.py` | C12 |
| `Features/TranscodeJob/Emit/RemuxShape.py` | C10 |
| `Features/TranscodeJob/Emit/SubtitleFixShape.py` | C11 |
| `Tests/Contract/TestCommandSpec.py` | C1 |
| `Tests/Contract/TestResolutionCalculator.py` | C2 |
| `Tests/Contract/TestOutputFilenameBuilder.py` | C3 |
| `Tests/Contract/TestCodecParameterAssembler.py` | C4 |
| `Tests/Contract/TestVideoFilterBuilder.py` | C6 |
| `Tests/Contract/TestMediaProbeAdapter.py` | C7 |
| `Tests/Contract/TestSystemCapabilityProbe.py` | C8 |
| `Tests/Contract/TestEncodeShape.py` | C9 |
| `Tests/Contract/TestEncodeShapeRegistry.py` | C9 |
| `Tests/Contract/TestTranscodeShape.py` | C12 |
| `Tests/Contract/TestRemuxShape.py` | C10 |
| `Tests/Contract/TestSubtitleFixShape.py` | C11 |
