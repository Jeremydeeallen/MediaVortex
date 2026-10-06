# Audio Strategy

Which job touches audio, and how, is decided in one place: `transcode.flow.md` `## Domain Decisions` D2 (the job label decides the command) and D6 (what the Audio stage emits). This page is an overview and points there; it does not restate the rules.

## Rules

### 1. Which job re-encodes audio

Only the Audio stage (`AudioFix` job label) re-encodes audio. `Transcode` and `Remux` jobs copy audio untouched -- see `transcode.flow.md` D2 for the exact meaning of "copy untouched" (stream copy when the source codec is acceptable, otherwise a plain aac conversion with no loudness work).

### 2. Language: English Preferred

When the Audio stage picks the stream that feeds Dialog Boost and the file contains multiple audio streams, the English track is preferred.

- Streams tagged `eng` or `en` are preferred
- When no English track exists, the first audio stream is used as a fallback

**Implementation:** `Features/AudioNormalization/Services/PreEncodeAudioPipeline._SelectPreferredAudioIndex`.

### 3. Normalization: Industry-Standard Loudness

The Audio stage ships two tracks per kept language: Dialog Boost (Demucs vocal isolation + tight loudnorm) and Original (linear-mode loudnorm, source dynamics preserved). The parameter contract, measurement requirements, and operator-tunable knobs are owned by `Features/AudioNormalization/audio-normalization.feature.md` (see C36 for the linear-mode two-pass invariant, C37 for the single emit path, C38 for the transparent kbps/ch floor).

## Key Files

- `Features/TranscodeJob/Emit/Slots/AudioSlot.py` -- `Copy` (Transcode / Remux) and `Reencode` (AudioFix) audio argv
- `Features/AudioNormalization/AudioFilterEmitter.py` -- `EmitTracks`, the single producer of the two-track filter chain
- `Features/AudioNormalization/Services/AudioPreEncodeFacade.py` -- Demucs pre-encode orchestration
