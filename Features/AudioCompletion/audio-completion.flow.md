# Flow: Audio Completion (one-shot normalize, then forever stream-copy)

**Slug:** audio-completion

## Entry Point

`MediaFiles.AudioComplete` is the per-file boolean that decides whether
audio gets re-encoded on the next encode pass or stream-copied. The
field is consulted by:

- `Models.CommandBuilder.BuildCommand` (transcode path) -- chooses `-c:a copy` vs the loudnorm-aware re-encode.
- `Models.CommandBuilder.BuildRemuxCommand` -- chooses `-c:a copy` vs the loudnorm-aware re-encode.
- `Models.CommandBuilder.BuildSubtitleFixCommand` -- same.
- `Features.TranscodeQueue.QueueManagementBusinessService._EvaluateCompliance` -- the "audio-normalized" leg of the compliance cascade reads `AudioComplete` directly (replaces the legacy `NormalizedIds` set built from grepping `TranscodeAttempts.FFpmpegCommand`).

It is written by:

- `Features.AudioCompletion.AudioCompletionService.MarkAudioComplete` -- called from the FileReplacement post-flight hook when the just-completed FFmpeg command contained `loudnorm`.
- `Scripts.SQLScripts.BackfillAudioComplete` -- one-time seed pass over the existing library at feature ship time.
- `Features.TranscodeQueue.QueueManagementBusinessService.RecomputeForFiles` -- triggers a re-derivation when probe metadata changes (e.g. a re-probe finds zero audio streams where there were some before).

## Promise

For any `MediaFile`:

1. Audio is normalized **at most once** by MediaVortex. Subsequent encode passes (transcode, remux, subtitle fix) stream-copy the audio bit-for-bit.
2. Audio that is too low-bitrate to survive a re-encode (≤ 96 kbps stereo / ≤ 64 kbps mono) is **never** normalized -- it is marked `AudioComplete=true` with reason `'below_bitrate_floor'` so all future passes stream-copy.
3. Audio that is in a codec MP4 cannot stream-copy (DTS, TrueHD, FLAC, PCM, Vorbis, Opus) is routed through the **same one-shot pass** as un-normalized AAC. The pass decodes audio, applies loudnorm, and re-encodes to a MP4-compat codec (`BuildAudioCodecArgs` already lands these on EAC3 with channel-aware bitrate). Post-flight `AudioComplete=true` -- subsequent encodes stream-copy the now-MP4-compat audio. These files are **not** suspect; they are just on the codec-conversion path.
4. Audio that is missing entirely (zero audio streams on a video file) is flagged `AudioCorruptSuspect=true, AudioCorruptReason='no_audio_stream'`. Suspect is reserved for this case (and the rare undecodable exotic codec). It is intentionally a small population -- "Suspect ≠ Inconvenient."

## Stage Overview

| ID | Stage | Trigger |
|---|---|---|
| ST1 | PROBE COMPLETE -- entering the state machine | `MediaProbeBusinessService._ExecuteProbe` writes audio columns |
| ST2 | CASCADE DECIDES -- branch on audio shape (no audio / below floor / needs norm / already done) | `MarkAudioComplete` post-flight + `BackfillAudioComplete` script |
| ST3 | ONE-SHOT NORMALIZE -- run loudnorm + optional codec convert | First subsequent transcode or remux for files with `AudioComplete=false` |
| ST4 | STREAM-COPY STEADY STATE -- `-c:a copy` on every subsequent pass | Command builders consult `AudioComplete=TRUE` |

## States and transitions

```
                     +-----------------+
                     | (not yet probed)|
                     |  AudioComplete  |
                     |     = NULL      |
                     +--------+--------+
                              |
                  MediaProbe completes
                              |
                              v
                     +--------+--------+
                     |  Cascade decides|
                     +--------+--------+
                              |
        +-------+-------------+--------------+-------+
        |                     |              |       |
        v                     v              v       v
  no audio               below floor    needs norm   already done
  stream                                or DTS/etc   (loudnorm in
                                                     TranscodeAttempts
                                                     history)
        |                     |              |       |
        v                     v              v       v
 Suspect=true        Complete=true  Complete=false  Complete=true
 Reason=             Reason=        Reason=NULL     Reason=NULL
 'no_audio_stream'   'below_                        (back-filled from
                      bitrate_                       legacy detection)
                      floor'
                                          |
                                          v
                              First subsequent
                              transcode OR remux
                              runs BuildAudioCodecArgs
                              (codec convert if needed)
                              + loudnorm filter (per
                              linear-loudnorm.feature.md).
                              On successful replace,
                              MarkAudioComplete sets
                              AudioComplete=true,
                              AudioCompletedAt=NOW().
                                          |
                                          v
        +-------------------------+-------+
        |                         |
        |                         v
        |              All future encodes stream-copy
        |              audio (-c:a copy).
        v
  Hard-blocked from queue. Operator surfaces via
  KNOWN-ISSUES / SELECT and decides remediation
  (re-import, audio-track repair, manual MarkComplete).
```

## Seams

| ID | Transition | Producer (writer) | Wire shape | Consumer (reader) expects | Verification |
|---|---|---|---|---|---|
| S1 | `ST1 -> ST2` (probe -> cascade) | `MediaProbeBusinessService._ExecuteProbe` | `MediaFiles.(AudioCodec TEXT, AudioBitrateKbps INT, AudioChannelCount INT, AudioLanguages TEXT)` populated | `QueueManagementBusinessService._EvaluateCompliance` reads these to decide eligible/below-floor/etc | Post-probe SQL: `SELECT AudioCodec, AudioBitrateKbps, AudioChannelCount FROM MediaFiles WHERE Id=<id>` -- all three non-NULL for any non-error probe |
| S2 | `ST2 -> ST3` (cascade -> normalize) | Cascade decision (no DB row written -- decision lives in `BuildAudioCodecArgs` + command builder) | `MediaFiles.AudioComplete=FALSE` (or NULL) + audio not in MP4-compat set OR loudness mismatch | `Models.CommandBuilder.BuildCommand` / `BuildRemuxCommand` emit `loudnorm` filter chain | Inspect `TranscodeAttempts.FFpmpegCommand ILIKE '%loudnorm%'` for the next attempt of the file |
| S3 | `ST3 -> ST4` (normalize -> steady-state) | `FileReplacementBusinessService` post-flight calls `AudioCompletionService.MarkAudioComplete` | `MediaFiles.AudioComplete=TRUE, AudioCompletedAt=NOW()` | All future command-builder invocations see `AudioComplete=TRUE` and emit `-c:a copy` | `SELECT AudioComplete, AudioCompletedAt FROM MediaFiles WHERE Id=<id>` -- TRUE + non-NULL timestamp after the next successful replacement carrying a loudnorm command |
| S4 | `ST4 -> done` (steady-state -> no further normalize) | Command builders read `AudioComplete=TRUE` | `ffmpeg ... -c:a copy ...` (bit-identical audio passthrough) | Operator manual override via `POST /api/AudioCompletion/Reset` flips back to FALSE for a deliberate re-run | `SELECT COUNT(*) FROM TranscodeAttempts WHERE MediaFileId=<id> AND FFpmpegCommand ILIKE '%loudnorm%' AND CompletedDate > AudioCompletedAt` -> 0 |

## Failure modes

| Failure | Symptom | Resolution |
|---|---|---|
| Audio bitrate column is NULL on a file we'd otherwise mark `below_floor` | Cascade treats it as eligible-for-normalize (false). Conservative -- worst case is one (well-bounded) re-encode pass. | Re-probe restores `AudioBitrateKbps`. Backfill re-runs idempotent. |
| FFmpeg loudnorm pass fails | TranscodeAttempt fails, queue row reset to Pending, `AudioComplete` not flipped. | Standard retry. If FFmpeg keeps failing, ProblemFiles tracking surfaces the file. |
| Post-flight `MarkAudioComplete` raises | Replacement already succeeded (file on disk is the normalized version) but DB still says `AudioComplete=false`. | Loud warning. Next admin recompute will re-evaluate from the most-recent `TranscodeAttempts.FFpmpegCommand` substring match and flip the bit. |
| Re-probe of a replaced file shows zero audio streams (silent output) | `RecomputeForFiles` flips the file to `AudioCorruptSuspect=true, AudioCorruptReason='no_audio_stream'` | Catches BUG-0002 class regressions. The file is held out of the queue until the operator clears it. |
| Operator wants to force a re-normalize after a settings change | `AudioComplete=true` blocks the encode-path normalization entirely. | Admin endpoint `POST /api/AudioCompletion/Reset` accepts `MediaFileId[]` (or scope filter) and sets the rows back to `AudioComplete=false`. Next encode runs the loudnorm chain. |
| Operator wants to skip the one-shot pass for a carefully-mastered source (Blu-ray rip, etc.) | `AudioComplete=false` by default means a normalize pass will run on next encode. | Admin endpoint `POST /api/AudioCompletion/MarkComplete` flips the row to `AudioComplete=true, AudioCompletedAt=NOW()` without running any pass. All future encodes stream-copy. |

## Bitrate floor

| Channels | Floor (≤ skipped) |
|---|---|
| 1 (mono) | 64 kbps |
| 2 (stereo) | 96 kbps |
| 3+ (surround) | 128 kbps |

Stored in `QueueAdmissionConfig` columns `MinAudioBitrateKbpsMono`,
`MinAudioBitrateKbpsStereo`, `MinAudioBitrateKbpsSurround`. Single-row
config; no caching per the repo-wide rule against cached DB settings.

Files **at or below** the floor are marked `AudioComplete=true` so the
encode path stream-copies. Files **above** the floor are normalized on
their first encode pass and then stream-copied forever.

## MP4-compatible audio codec set

```
('aac', 'ac3', 'eac3', 'mp3')
```

Stored in `CodecCompatibility` under `Kind='AudioCodecMp4'`. Files
outside this set are **never** stream-copied into MP4. They are routed
through the one-shot pass (`AudioComplete=false`) where
`BuildAudioCodecArgs` converts the codec (lossless / unknown sources
land on EAC3 with channel-aware bitrate) in the same FFmpeg invocation
that applies loudnorm. Post-flight they become `AudioComplete=true` and
join the stream-copy population.

Suspect is reserved for the cases where conversion itself is not safe:
no audio stream at all, or a rare codec the encoder cannot decode.

## Loudnorm detection

The same substring match used today by `_LoadAudioNormalizedSet`:

```
TranscodeAttempts.FFpmpegCommand ILIKE '%loudnorm%'
```

For the most-recent **successful** attempt per `MediaFileId`. Validated
2026-05-09 against live data (2,385 normalized vs 230 not). The same
detector is used by `MarkAudioComplete` (post-flight, current attempt's
command) and `BackfillAudioComplete` (historical attempts).

## Output Location

`MediaFiles.AudioComplete`, `MediaFiles.AudioCompletedAt`,
`MediaFiles.AudioCorruptSuspect`, `MediaFiles.AudioCorruptReason`.

No new tables. No write to `MediaFilesArchive` for this state -- archive
is for source-file metadata snapshots, not for derived flags.

## Related Docs

- `Features/TranscodeQueue/remux.flow.md` -- consumes `AudioComplete` in the command builder.
- `Features/TranscodeQueue/transcode.flow.md` (the top-level flow) -- Stage 5 (TRANSCODE) command construction consumes `AudioComplete`.
- `Features/TranscodeQueue/transcode-vs-remux-routing.feature.md` -- compliance cascade now reads `AudioComplete` instead of grep-derived `NormalizedIds`.
