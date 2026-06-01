# Flow: Linear Loudnorm (measure once, apply with fixed gain)

**Slug:** linear-loudnorm

## Entry Point

`Models.CommandBuilder.BuildAudioFilters` is the single callsite that
emits the `loudnorm` filter for every audio-re-encoding pipeline
(transcode, remux, subtitle fix). It runs for any MediaFile with
`AudioComplete=false`. This flow describes how that one callsite is
guaranteed to emit a transparent, fixed-gain command -- never a
real-time-compressing dynamic-mode command.

It is consumed by:
- `Features.TranscodeJob.ProcessTranscodeQueueService` -- assembles the
  full FFmpeg command and runs the encode.

It depends on:
- `Features.LoudnessAnalysis.LoudnessAnalysisService` -- captures the
  four ebur128 measurements per file.
- `Features.TranscodeQueue.QueueManagementBusinessService` admission
  gate -- refuses to admit a file that cannot be normalized linearly.

## Promise

For any MediaFile that runs through a MediaVortex encode:

1. The output integrated loudness measures within +/- 1 LUFS of the
   configured target (default -23 LUFS), regardless of source loudness.
   No show-to-show volume jumps.
2. The output true peak is at or below the configured target (default
   -2 dBTP). No clipping.
3. The output loudness range is preserved at or above the source LRA
   *whenever physically possible* (linear mode). For files where the
   required fixed gain would clip, dynamic mode is used instead and
   range compression is applied as little as needed to honor (2).
4. The mode used (linear vs dynamic) is recorded per file
   (`MediaFiles.AudioNormalizationMode`) and logged per encode. There
   is no silent mode choice and no silent state.
5. If loudness measurements are missing, the file is held out of the
   queue with `AdmissionDeferReason='awaiting_loudness_measurement'`
   until the measurement pipeline catches up. It is never encoded
   with a guessed or default measurement.

## Stages

```
+----------+      +-------------+      +-------------------+
| Probe    | ---> | ebur128     | ---> | MediaFiles rows   |
| complete |      | measurement |      | (4 loudness cols) |
+----------+      +-------------+      +-------------------+
                                              |
                                              v
                                       +-------------+
                                       | Admission   |
                                       | gate        |
                                       +------+------+
                                              |
                          +-------------------+----------+
                          |                              |
                  all 4 cols present              any col missing
                          |                              |
                          v                              v
                  +---------------+         +-----------------------------+
                  | Predicted-    |         | Hold out of queue.          |
                  | peak math at  |         | DeferReason=                |
                  | build time    |         |   awaiting_loudness_        |
                  +---+-------+---+         |   measurement.              |
                      |       |             | Surfaced on Activity.       |
            gain fits |       | would clip  +-----------------------------+
                      v       v
              +----------+ +-----------+
              | Build    | | Build     |
              | linear   | | dynamic   |
              | command  | | command   |
              +-----+----+ +-----+-----+
                    |            |
                    +-----+------+
                          v
                   +-------------+
                   | FFmpeg      |
                   | encode pass |
                   +-------------+
                          |
                          v
              +---------------------------+
              | Post-flight:              |
              |   MarkAudioComplete       |
              |   write AudioNormalization|
              |     Mode = linear/dynamic |
              +---------------------------+
```

## Stage detail

### Stage 1 -- ebur128 measurement (`ST1`)

Runs once per source file (re-runs on file replacement or mtime change).
Captures four numbers from the Summary block of `ffmpeg -af
ebur128=peak=true` stderr:

| Field | Persisted to | Used by loudnorm as |
|---|---|---|
| Integrated loudness (LUFS) | `MediaFiles.SourceIntegratedLufs` | `measured_I` |
| Loudness range (LU) | `MediaFiles.SourceLoudnessRangeLU` | `measured_LRA` |
| True peak (dBTP) | `MediaFiles.SourceTruePeakDbtp` | `measured_TP` |
| Relative gating threshold (LUFS) | `MediaFiles.SourceIntegratedThresholdLufs` | `measured_thresh` |

`LoudnessMeasuredAt` is stamped on success; `MeasurementFailureReason`
holds a stable short code on failure (see
`LoudnessAnalysisService.MeasureLoudness` docstring).

### Stage 2 -- Admission gate (`ST2`)

When `_EvaluateCompliance` sees a file with `AudioComplete=false`,
it requires only:

1. `LoudnessMeasuredAt IS NOT NULL`
2. All four loudness columns IS NOT NULL

If either fails, the file does not get a queue row. A structured
`AdmissionDeferReason='awaiting_loudness_measurement'` is recorded so
the operator can see why each file is held. The probe co-trigger
(stage 1, run on every probe completion) catches the file up on the
next pass.

The admission gate does **not** check the predicted-peak math. That
check is deferred to command-build time, where it selects between
linear and dynamic mode (stage 3). The reason is that an ungainable
file is still a file we want to normalize -- holding it out of the
queue just relocates the show-to-show loudness jump that the whole
feature exists to prevent.

### Stage 3 -- Command-build (linear or dynamic) (`ST3`)

At build time, `BuildAudioFilters` computes:

```
predicted_peak = SourceTruePeakDbtp + (TargetLoudness - SourceIntegratedLufs)
```

If `predicted_peak <= TargetTruePeak`, emit linear-mode loudnorm:

```
loudnorm=I={TargetLoudness}:LRA={TargetLra}:TP={TargetTp}
        :measured_I={...}:measured_LRA={...}
        :measured_TP={...}:measured_thresh={...}
        :linear=true
```

Otherwise emit dynamic-mode loudnorm (same params, no `linear=true`):

```
loudnorm=I={TargetLoudness}:LRA={TargetLra}:TP={TargetTp}
        :measured_I={...}:measured_LRA={...}
        :measured_TP={...}:measured_thresh={...}
```

In either case:
- `TargetLoudness`, `TargetTp` come from SystemSettings (defaults
  -23, -2).
- `TargetLra = max(SourceLoudnessRangeLU, MinimumLoudnessRangeLU)`. The
  minimum floor is a SystemSettings row (default 11). For linear mode,
  this guarantees `measured_LRA <= TargetLra` so FFmpeg cannot
  silently switch modes mid-stream. For dynamic mode, this is the
  range envelope the limiter targets.
- No `acompressor`. The chain is one filter regardless of mode.

The mode chosen is logged per encode and stored on `MediaFiles.
AudioNormalizationMode` (`'linear'` or `'dynamic'`) by the post-flight
hook. Activity surfaces both counts. Dynamic mode is the explicit
correct tool for ungainable files, not a hidden fallback.

### Stage 4 -- FFmpeg encode pass (`ST4`)

FFmpeg applies a fixed gain of `(TargetLoudness - measured_I)` to every
sample of the decoded audio stream, re-encodes via `BuildAudioCodecArgs`,
and writes the output. No real-time loudness measurement, no compressor,
no limiter (the TP ceiling is enforced by the pre-encode gate, not by a
runtime limiter).

### Stage 5 -- Post-flight (`ST5`)

## Seams

| ID | Transition | Producer (writer) | Wire shape | Consumer (reader) expects | Verification |
|---|---|---|---|---|---|
| S1 | `ST1 -> ST2` (measure -> admission) | `LoudnessAnalysisService.MeasureAndPersist` (called from `filescanning.flow.md::ST4` probe co-trigger) | `MediaFiles.(SourceIntegratedLufs, SourceLoudnessRangeLU, SourceTruePeakDbtp, SourceIntegratedThresholdLufs, LoudnessMeasuredAt)` all NOT NULL on success; `LoudnessMeasurementFailureReason TEXT` on failure | `QueueManagementBusinessService._EvaluateCompliance` requires `LoudnessMeasuredAt IS NOT NULL` + all four columns non-NULL | `SELECT COUNT(*) FROM MediaFiles WHERE AudioComplete=FALSE AND LoudnessMeasuredAt IS NULL` -> bucket size of held files |
| S2 | `ST2 -> queue or defer` | `_EvaluateCompliance` writes deferral signal | `MediaFiles.AdmissionDeferReason='awaiting_loudness_measurement'` (or absent if admitted) | Queue admission path skips deferred rows | `SELECT COUNT(*) FROM MediaFiles WHERE AdmissionDeferReason='awaiting_loudness_measurement'` |
| S3 | `ST3 -> ST4` (command -> ffmpeg) | `Models.CommandBuilder.BuildAudioFilters` | `loudnorm=I=...:LRA=...:TP=...:measured_I=...:measured_LRA=...:measured_TP=...:measured_thresh=...[:linear=true]` filter string embedded in `TranscodeAttempts.FFpmpegCommand` | FFmpeg subprocess executes the filter graph | `SELECT FFpmpegCommand FROM TranscodeAttempts WHERE Id=<attempt>` contains the literal `loudnorm=I=` substring |
| S4 | `ST5 -> downstream` (post-flight -> steady-state) | `FileReplacementBusinessService` post-flight | `MediaFiles.(AudioComplete=TRUE, AudioCompletedAt=NOW(), AudioNormalizationMode IN ('linear','dynamic'))` | `audio-completion.flow.md::ST4` stream-copy steady state observed | `SELECT AudioNormalizationMode, COUNT(*) FROM MediaFiles WHERE AudioComplete=TRUE GROUP BY 1` -- non-empty linear + dynamic buckets |

On successful replacement, `MarkAudioComplete` flips
`MediaFiles.AudioComplete=true`. All future encodes for this file
stream-copy audio. See `Features/AudioCompletion/audio-completion.flow.md`.

## Failure modes

| Failure | Symptom | Resolution |
|---|---|---|
| ebur128 stderr Summary block is missing a field (e.g. silent stream) | `LoudnessAnalysisService.PersistLoudness` does not write -- `LoudnessMeasuredAt` stays NULL | File stuck in `awaiting_loudness_measurement` bucket. Operator inspects: re-probe, or mark AudioComplete manually if source is acceptable as-is. |
| Source loudness is so low that the fixed gain would breach TP | Build-time math selects dynamic mode for this file. Logged + recorded on `AudioNormalizationMode='dynamic'`. | None needed -- this is the explicit correct path. Operator can audit the dynamic-mode population via the Activity count; if a specific file's compressed output is unacceptable, re-source it or `MarkAudioComplete` it to bypass normalization entirely. |
| Encoder command is built without measurements (logic error: should have been gated) | `BuildAudioFilters` raises `RuntimeError`. Transcode fails. Queue row reset to Pending. | Loud failure. Fix the upstream gate; do not silently degrade. |
| Operator changes target loudness in SystemSettings | New encodes pick up the new target. Existing AudioComplete=true files are unaffected (they stream-copy). | Operator runs `POST /api/AudioCompletion/Reset` for any subset they want re-normalized to the new target. |

## Loudness math reference

Linear-mode gain: `gain_dB = TargetLoudness - measured_I`.
Examples (TargetLoudness = -23):

| measured_I | gain | new peak (if measured_TP = -1) | mode |
|---|---|---|---|
| -23.0 | 0 dB | -1.0 dBTP | linear (gain is a no-op) |
| -18.0 (loud broadcast) | -5 dB | -6.0 dBTP | linear |
| -28.0 (typical film) | +5 dB | +4.0 dBTP | dynamic (would clip) |
| -33.0 (very quiet) | +10 dB | +9.0 dBTP | dynamic (would clip) |

The build-time check selects the mode. Linear is preferred when the
math permits; dynamic is the correct tool when it does not. Both
modes target the same integrated loudness; dynamic compresses range
to honor the TP ceiling, linear leaves range untouched.

## Related Docs

- `Features/AudioCompletion/audio-completion.feature.md` -- per-file
  state machine that decides whether loudnorm runs at all. Owns
  `AudioComplete`, suspect/eligible reasons, and the post-flight hook.
- `Features/TranscodeQueue/media-tabs-and-loudness.feature.md` --
  ebur128 measurement capture (this flow consumes the columns it
  populates).
- `Features/LoudnessAnalysis/linear-loudnorm.feature.md` -- contract
  for the policy described in this flow.
