# Audio Normalization Flow

**Slug:** audio-normalization

## What It Does

Per-encode audio pipeline. Every ProcessingMode that ships audio (Transcode, Remux, AudioFix, Quick, SubtitleFix, TestVariant) runs through the SAME stages. Single source of truth: `AudioFilterEmitter.EmitTracks` for track shape; `AudioPreEncodeFacade` for Demucs orchestration.

Entry point: `Features/TranscodeJob/Worker/JobProcessor.Process` (for the five mode-driven strategies) and `Features/TranscodeJob/ProcessTranscodeQueueService._ProcessSingleVariant` (for TestVariant).

## Stages

ST1. **Claim + setup.** Worker claims the queue row. `JobProcessor.Process` resolves the local input path via `SetupFilePreparation` and creates the TranscodeAttempt row.

ST2. **Pre-encode audio (Demucs).** `AudioPreEncodeFacade.Prepare(FfmpegPath, InputPath, JobId, ProgressReporter)` runs when `MediaFile.AudioCompliant IS NOT TRUE` (compliance-driven gate; audiocompliant files stream-copy audio and skip Demucs entirely). Substeps + progress emit per `PreEncodeAudioPipeline.Run`: (a) `SourceMeasure` 0->100 via streaming ffmpeg loudnorm on source; (b) `Downmix` 0->100 stereo WAV extract; (c) `Demucs` 0->100 vocal isolation, per-tqdm-tick percent from daemon stderr (>= 1 Hz on real workloads); (d) `Premix` 0->100 boosted-vocals + attenuated-instrumental mix; (e) `LoudnormMeasure` 0->100 via streaming ffmpeg loudnorm on premix. Each substep invokes `ProgressReporter(Phase, Percent, Info)`, which writes a `TranscodeProgress` row with `CurrentPhase=<Phase>` + `ProgressPercent=<pct>` -- `/Activity` reads these to render Phase + Progress cells during pre-encode. Returns `{DemucsPremixPath, VocalsRmsDbfs, PremixMeasuredI, PremixMeasuredLra, PremixMeasuredTp, PremixMeasuredThresh, ScratchDir}`. Failure sets premix path to None so Track 1 is skipped; encode still proceeds with Track 0 only.

ST3. **Command build.** `Strategy.BuildCommand` forwards Context (containing the ST2 premix keys) wholesale to `CommandComposer.Build(MediaFile, Job, Context)`. The composer derives a `Plan` via `PlanFactory.FromComplianceState(MediaFile)` (per transcode.flow.md D2). When `AudioCompliant=FALSE` the AudioOp is `Reencode` and `AudioSlot.Emit('Reencode', MediaFile, Context)` calls `AudioFilterEmitter.EmitTracks(MediaFile, Policy, DemucsPremixPath=..., VocalsRmsDbfs=..., PremixMeasured...=...)`; the emitter decides Track 0 (Original) + Track 1 (Dialog Boost) shape and per-file measurements substitute at emit time. When `AudioCompliant=TRUE` the AudioOp is `Copy` and `AudioSlot.Emit('Copy', ...)` emits `-map 0:a? -c:a copy` with no Demucs input. The composer emits all `-i` inputs (source + `AudioEmission.InputArgs` premix) BEFORE any `-map` args (ffmpeg parser is order-sensitive).

ST4. **Encode.** ffmpeg subprocess runs. Progress reported via `UpdateTranscodeProgress`.

ST5. **Post-encode measurement.** `PostEncodeMeasurementService.Probe(TranscodeAttemptId, FinalOutputPath)` runs ffprobe on the encoded output, measures ebur128 per audio stream, writes `TranscodeAttempts.AudioTracksEmittedJson` with per-track `AchievedIntegratedLufs / AchievedLra / AchievedTruePeakDbtp`. Single writer; JSON is never mutated after this write.

ST6. **Dialog Boost flag persistence.** `AudioPreEncodeFacade.PersistMeta(TranscodeAttemptId, PreAudio)` writes `TranscodeAttempts.DialogBoostEmitted BOOL` from the ST2 Demucs premix outcome (TRUE iff premix path present AND vocals RMS above fallback floor). Single boolean column; no JSON merge. Read by `ComplianceGate.Evaluate` (in-flight attempt) and `TranscodedOutputPlacement.Execute` (latest successful attempt) to derive `MediaFiles.HasDialogBoostTrack`.

ST7. **Finalize + cleanup.** `Strategy.HandleResult` invokes queue service finalize (DispositionDispatcher / FileReplacement). `AudioPreEncodeFacade.Cleanup(FfmpegPath, PreAudio)` deletes the Demucs scratch dir.

## Seams

| ID | Transition | Producer | Wire shape | Consumer expects | Verification |
|---|---|---|---|---|---|
| S1 | ST1 -> ST2 | `JobProcessor.Process` | `(FfmpegPath: str, InputPath: str, JobId: int, ProgressReporter: callable)` | `AudioPreEncodeFacade.Prepare` returns dict with DemucsPremixPath + VocalsRmsDbfs + PremixMeasured* + ScratchDir on success, OR `{DemucsFailed: True, DemucsFailureReason: <ExcType>: <msg>, DemucsPremixPath: None, VocalsRmsDbfs: None}` on Demucs exception (C39); None only when Mode not in `_AUDIO_EMIT_MODES` or InputPath empty | `Tests/Contract/TestAudioPreEncodeFacade.py` (round-trip Prepare + Cleanup + failure-sentinel round-trip) |
| S2 | ST2 -> ST3 | `AudioPreEncodeFacade.EnrichContext` (called inline by `_RunPreEncodeAudio` or `_ProcessSingleVariant`) | dict keys `DemucsPremixPath, VocalsRmsDbfs, PremixMeasuredI, PremixMeasuredLra, PremixMeasuredTp, PremixMeasuredThresh` merged into Context / TranscodingSettings | `AudioSlot._EmitReencode(MediaFile, Context)` reads these six keys and forwards to `AudioFilterEmitter.EmitTracks` | grep `AudioSlot._EmitReencode` must call EmitTracks with all six kwargs; `-c:a copy` no-Blocks fallback is FORBIDDEN (starvation vector) |
| S3 | ST3 emit-order invariant | CommandComposer | `ffmpeg <FFmpegPath> -i "<src>" -i "<premix>" -map 0:v:0 -c:v <copy\|codec> -map 0:a:0 ... -map 1:a:0 ...` | ffmpeg parser requires all `-i` inputs BEFORE any `-map`; `CommandComposer.Build` appends `AudioEmission.InputArgs` right after the source `-i` and before VideoSlot; interleaved args produce EINVAL (exit 4294967274 on Windows) | Manual replay of any failing 2-track cmd + audit of composer build order |
| S4 | ST3 -> ST4 | `AudioFilterEmitter.EmitTracks` | Returns `List[TrackBlock]` (Track 0 always; Track 1 iff DemucsPremixPath truthy AND VocalsRmsDbfs > Track1VocalsRmsFallbackDbfs) | `AudioSlot._EmitReencode` iterates blocks and emits `-map / -c:a:N / -b:a:N / -filter:a:N / -metadata / -disposition` per block; empty Blocks raises `AudioPolicyUnresolvedError` (starvation vector) | `Tests/Contract/TestAudioFilterEmitter.py` |
| S5 | ST4 -> ST5 | ffmpeg subprocess | `.mp4.inprogress` file on disk with N audio streams | `PostEncodeMeasurementService.Probe` runs ffprobe + ebur128 per stream; writes `TranscodeAttempts.AudioTracksEmittedJson` as JSON array | manual ffprobe replay + SQL |
| S6 | ST5 -> ST6 | `AudioPreEncodeFacade.PersistMeta` | `UPDATE TranscodeAttempts SET DialogBoostEmitted = <bool> WHERE Id = <N>` | `ComplianceGate.Evaluate` + `TranscodedOutputPlacement.Execute` read the column via `SELECT DialogBoostEmitted FROM TranscodeAttempts` -- no JSONB path expressions | `Tests/Contract/TestDialogBoostMarkerCanonical.py` (grep + round-trip) |
| S7 | ST6 -> ST7 | Cleanup call | `ScratchDir` path from PreAudio dict | `AudioPreEncodeFacade.Cleanup(FfmpegPath, PreAudio)` shutil.rmtree the scratch dir; safe when None | `Tests/Contract/TestAudioPreEncodeFacade.py` idempotent Cleanup |

## Starvation guards (kbps/ch floor)

Track 0 per-channel bitrate has three defense layers per audio-normalization.C38:

1. **DB write barrier** (`AudioNormalizationController.update_audio_rules`): refuses PUT bodies where `Track0BitratePerChannelKbps < 48` or `Track0MinPerChannelKbps < 48`. Operator cannot save a starving config via the GUI.
2. **Emit barrier** (`AudioFilterEmitter.MIN_TRANSPARENT_KBPS_PER_CH = 48`): `max(MIN_TRANSPARENT_KBPS_PER_CH, target, min) * Channels`. Even if the DB is somehow starved, the emitter clamps to 48 kbps/ch.
3. **Fallback deletion** (`Features/TranscodeJob/Emit/Slots/AudioSlot._EmitReencode`): `-c:a copy` no-Blocks fallback + `ProfileAudioCeiling` reencode fallback both gone. Empty `Blocks` or missing `Policy` raises `AudioPolicyUnresolvedError` (routes MediaFile to operator review, not to a starved encode).

Together the three layers close: BUG-0072 (21 kbps/ch 5.1 starvation), the operator-knob GUI-drop-to-zero vector, and the source-bitrate-inherit `-c:a copy` silo.

## Compliance coverage matrix

Plan is derived per-file from `(VideoCompliant, AudioCompliant, ContainerCompliant)` via `PlanFactory.FromComplianceState(MediaFile)`; `SubtitleOp=Preserve` always; `ProcessingMode` is a reporting tag only (transcode.flow.md D3).

| (V,A,C) | Plan (Video, Audio, Subtitle, Container) | Runs PreEncodeAudio | 2-track emit |
|---|---|---|---|
| (F,F,F) | (Reencode, Reencode, Preserve, Mp4) | yes | yes |
| (F,F,T) | (Reencode, Reencode, Preserve, Preserve) | yes | yes |
| (F,T,F) | (Reencode, Copy, Preserve, Mp4) | no | no (`-c:a copy`) |
| (F,T,T) | (Reencode, Copy, Preserve, Preserve) | no | no (`-c:a copy`) |
| (T,F,F) | (Copy, Reencode, Preserve, Mp4) | yes | yes |
| (T,F,T) | (Copy, Reencode, Preserve, Preserve) | yes | yes |
| (T,T,F) | (Copy, Copy, Preserve, Mp4) | no | no (`-c:a copy`) |
| (T,T,T) | (Copy, Copy, Preserve, Preserve) -- would not admit (WorkBucket=Compliant) | -- | -- |

Diagnostic path: `VariantJobProcessor` -> `ProcessTranscodeQueueService._ProcessSingleVariant` -> `AudioPreEncodeFacade.Prepare` unconditionally (variant test intentionally exercises Demucs regardless of compliance).
