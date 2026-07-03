# Audio Normalization Flow

**Slug:** audio-normalization

## What It Does

Per-encode audio pipeline. Every ProcessingMode that ships audio (Transcode, Remux, AudioFix, Quick, SubtitleFix, TestVariant) runs through the SAME stages. Single source of truth: `AudioFilterEmitter.EmitTracks` for track shape; `AudioPreEncodeFacade` for Demucs orchestration.

Entry point: `Features/TranscodeJob/Worker/JobProcessor.Process` (for the five mode-driven strategies) and `Features/TranscodeJob/ProcessTranscodeQueueService._ProcessSingleVariant` (for TestVariant).

## Stages

ST1. **Claim + setup.** Worker claims the queue row. `JobProcessor.Process` resolves the local input path via `SetupFilePreparation` and creates the TranscodeAttempt row.

ST2. **Pre-encode audio (Demucs).** `AudioPreEncodeFacade.Prepare(FfmpegPath, InputPath, JobId, ProgressReporter)` runs for every ProcessingMode in `_AUDIO_EMIT_MODES = {Transcode, Remux, AudioFix, Quick, SubtitleFix}`. Steps: (a) stereo downmix WAV of source's first audio stream; (b) Demucs htdemucs vocal isolation (device: cuda / xpu / cpu auto-detected); (c) mix boosted vocals + attenuated instrumental into `dialog_boost_premix.wav`; (d) `loudnorm=print_format=json` two-pass measurement of the premix. Returns `{DemucsPremixPath, VocalsRmsDbfs, PremixMeasuredI, PremixMeasuredLra, PremixMeasuredTp, PremixMeasuredThresh, ScratchDir}`. Failure sets premix path to None so Track 1 is skipped; encode still proceeds with Track 0 only.

ST3. **Command build.** `Strategy.BuildCommand` forwards Context (containing the ST2 premix keys) wholesale to the shape via `EncodeShapeRegistry.Get(ProcessingMode).Build`. Shapes (`TranscodeShape` / `RemuxShape` / `SubtitleFixShape`) call `AudioFilterEmitter.EmitTracks(MediaFile, Policy, DemucsPremixPath=..., VocalsRmsDbfs=..., PremixMeasured...=...)`. The emitter decides Track 0 (Original) + Track 1 (Dialog Boost) shape; per-file measurements substitute at emit time. All `-i` inputs (source + premix.wav) MUST come BEFORE any `-map` args (ffmpeg parser is order-sensitive).

ST4. **Encode.** ffmpeg subprocess runs. Progress reported via `UpdateTranscodeProgress`.

ST5. **Post-encode measurement.** `PostEncodeMeasurementService.Probe(TranscodeAttemptId, FinalOutputPath)` runs ffprobe on the encoded output, measures ebur128 per audio stream, writes `TranscodeAttempts.AudioTracksEmittedJson` with per-track `AchievedIntegratedLufs / AchievedLra / AchievedTruePeakDbtp`.

ST6. **G5 persistence + C39 Demucs-failure signal.** `AudioPreEncodeFacade.PersistMeta(TranscodeAttemptId, PreAudio)` reads the ST5-written JSON, merges `vocals_rms_dbfs / vocals_fallback_dbfs / dialog_boost_emitted / demucs_failed / demucs_failure_reason` onto every track element. When ST2 caught an exception, `PreAudio` carries `DemucsFailed=true` + `DemucsFailureReason` so the persistence layer stamps `demucs_failed=true` — operator SQL can distinguish silent Demucs crash from deliberate G5 skip. If ST5 produced empty JSON, inserts a single meta-only entry with the same fields.

ST7. **Finalize + cleanup.** `Strategy.HandleResult` invokes queue service finalize (DispositionDispatcher / FileReplacement). `AudioPreEncodeFacade.Cleanup(FfmpegPath, PreAudio)` deletes the Demucs scratch dir.

## Seams

| ID | Transition | Producer | Wire shape | Consumer expects | Verification |
|---|---|---|---|---|---|
| S1 | ST1 -> ST2 | `JobProcessor.Process` | `(FfmpegPath: str, InputPath: str, JobId: int, ProgressReporter: callable)` | `AudioPreEncodeFacade.Prepare` returns dict with DemucsPremixPath + VocalsRmsDbfs + PremixMeasured* + ScratchDir on success, OR `{DemucsFailed: True, DemucsFailureReason: <ExcType>: <msg>, DemucsPremixPath: None, VocalsRmsDbfs: None}` on Demucs exception (C39); None only when Mode not in `_AUDIO_EMIT_MODES` or InputPath empty | `Tests/Contract/TestAudioPreEncodeFacade.py` (round-trip Prepare + Cleanup + failure-sentinel round-trip) |
| S2 | ST2 -> ST3 | `AudioPreEncodeFacade.EnrichContext` (called inline by `_RunPreEncodeAudio` or `_ProcessSingleVariant`) | dict keys `DemucsPremixPath, VocalsRmsDbfs, PremixMeasuredI, PremixMeasuredLra, PremixMeasuredTp, PremixMeasuredThresh` merged into Context / TranscodingSettings | Every shape (`TranscodeShape.Build`, `RemuxShape.Build`, `SubtitleFixShape.Build`) reads these six keys from Context; forwards to `AudioFilterEmitter.EmitTracks` | grep across shapes: each shape must call EmitTracks with all six kwargs; `-c:a copy` no-Blocks fallback is FORBIDDEN (starvation vector) |
| S3 | ST3 emit-order invariant | Shapes | `ffmpeg <FFmpegPath> -i "<src>" -i "<premix>" -map 0:v:0 -c:v <copy|codec> -map 0:a:0 ... -map 1:a:0 ...` | ffmpeg parser requires all `-i` inputs BEFORE any `-map`; interleaved args produce EINVAL (exit 4294967274 on Windows) | Manual replay of any failing 2-track cmd + audit of shape build order |
| S4 | ST3 -> ST4 | `AudioFilterEmitter.EmitTracks` | Returns `List[TrackBlock]` (Track 0 always; Track 1 iff DemucsPremixPath truthy AND VocalsRmsDbfs > Track1VocalsRmsFallbackDbfs) | Shape iterates blocks and emits `-map / -c:a:N / -b:a:N / -filter:a:N / -metadata / -disposition` per block; empty Blocks raises `AudioPolicyUnresolvedError` (starvation vector) | `Tests/Contract/TestAudioFilterEmitter.py` |
| S5 | ST4 -> ST5 | ffmpeg subprocess | `.mp4.inprogress` file on disk with N audio streams | `PostEncodeMeasurementService.Probe` runs ffprobe + ebur128 per stream; writes `TranscodeAttempts.AudioTracksEmittedJson` as JSON array | manual ffprobe replay + SQL |
| S6 | ST5 -> ST6 | `PostEncodeMeasurementService.Probe` | `AudioTracksEmittedJson` = list of `{TrackIndex, Label, Language, Strategy, AchievedIntegratedLufs, AchievedLra, AchievedTruePeakDbtp}` | `AudioPreEncodeFacade.PersistMeta` reads existing JSON, merges vocals meta onto every element, writes back | SQL: `SELECT audiotracksemittedjson->0->>'vocals_rms_dbfs' FROM transcodeattempts WHERE id=<N>` returns numeric |
| S7 | ST6 -> ST7 | Cleanup call | `ScratchDir` path from PreAudio dict | `AudioPreEncodeFacade.Cleanup(FfmpegPath, PreAudio)` shutil.rmtree the scratch dir; safe when None | `Tests/Contract/TestAudioPreEncodeFacade.py` idempotent Cleanup |

## Starvation guards (kbps/ch floor)

Track 0 per-channel bitrate has three defense layers per audio-normalization.C38:

1. **DB write barrier** (`AudioNormalizationController.update_audio_rules`): refuses PUT bodies where `Track0BitratePerChannelKbps < 48` or `Track0MinPerChannelKbps < 48`. Operator cannot save a starving config via the GUI.
2. **Emit barrier** (`AudioFilterEmitter.MIN_TRANSPARENT_KBPS_PER_CH = 48`): `max(MIN_TRANSPARENT_KBPS_PER_CH, target, min) * Channels`. Even if the DB is somehow starved, the emitter clamps to 48 kbps/ch.
3. **Fallback deletion** (all shapes): `-c:a copy` no-Blocks fallbacks deleted from `RemuxShape` / `SubtitleFixShape`; `ProfileAudioCeiling` reencode fallback deleted from `TranscodeShape`. Empty `Blocks` or missing `Policy` raises `AudioPolicyUnresolvedError` (routes MediaFile to operator review, not to a starved encode).

Together the three layers close: BUG-0072 (21 kbps/ch 5.1 starvation), the operator-knob GUI-drop-to-zero vector, and the source-bitrate-inherit `-c:a copy` silo.

## Mode coverage matrix

| ProcessingMode | Strategy | Shape | Runs PreEncodeAudio | 2-track emit |
|---|---|---|---|---|
| Transcode | TranscodeJobStrategy | TranscodeShape | via `JobProcessor._RunPreEncodeAudio` | yes |
| Remux | RemuxJobStrategy | RemuxShape | via `JobProcessor._RunPreEncodeAudio` | yes |
| AudioFix | AudioFixJobStrategy | RemuxShape | via `JobProcessor._RunPreEncodeAudio` | yes |
| Quick | QuickJobStrategy | RemuxShape | via `JobProcessor._RunPreEncodeAudio` | yes |
| SubtitleFix | SubtitleFixJobStrategy | SubtitleFixShape | via `JobProcessor._RunPreEncodeAudio` | yes |
| TestVariant | VariantJobProcessor | TranscodeShape (per variant) | via `ProcessTranscodeQueueService._ProcessSingleVariant` -> `AudioPreEncodeFacade.Prepare` | yes |
