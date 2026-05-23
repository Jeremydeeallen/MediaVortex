# Flow: Remux (audio normalize + container fix, no video re-encode)

## Entry Point

A `TranscodeQueue` row with `ProcessingMode = 'Remux'`. Workers claim
the row through the same `ClaimNextPendingTranscodeJob` path as
transcodes; the dispatcher in `ProcessJob` (`Features/TranscodeJob/ProcessTranscodeQueueService.py:351`)
inspects `Job.IsRemux` and routes to `ProcessRemuxJob`.

Until `transcode-vs-remux-routing.feature.md` step 6 ships, the only
code path that can write a `Mode='Remux'` row is `PopulateQueueForRemux`
in `QueueManagementBusinessService` -- not exposed via any API. After
step 6, every queue-entry path consults `MediaFiles.RecommendedMode`
and creates `Mode='Remux'` rows automatically when the cascade decides
the file needs only audio + container fixes.

## Promise

A remux job:
1. Copies the video stream byte-for-byte (`-c:v copy`) -- no quality loss, no encoder time.
2. Audio handling is **AudioComplete-aware** (see `Features/AudioCompletion/audio-completion.flow.md`):
   - `AudioComplete = true` -> `-c:a copy` (byte-identical to source, criterion 26)
   - `AudioComplete = false` -> one-shot pass: codec convert if needed (`BuildAudioCodecArgs` handles DTS/TrueHD/FLAC/PCM/Vorbis/Opus -> EAC3) + the loudnorm filter chain (parameter contract owned by `Features/LoudnessAnalysis/linear-loudnorm.feature.md`). Post-flight `FileReplacementBusinessService` flips `AudioComplete` to true so this never runs against the file again.
   - `AudioCorruptSuspect = true` -> the Remux is refused (logic error + flag).
3. **Renames the source to `.orig` BEFORE FFmpeg runs** so FFmpeg can write directly to the freed source path -- no intermediate filename, no suffix-strip step.
4. On FFmpeg success: FileReplacement verifies + settles the `.orig` per `KeepSource`. On any failure between rename and final verify: rollback restores the original from `.orig`.
5. Re-probes the new file and updates `MediaFiles` (Resolution, Codec, AudioCodec, ContainerFormat, IsCompliant via the recompute hook). When the just-completed FFmpeg command contained `loudnorm`, the post-flight hook also flips `AudioComplete=true, AudioCompletedAt=NOW()`.
6. Skips VMAF entirely -- video is bit-identical, no quality test makes sense.

Worker time per file: typically 5-30 seconds for a 1-hour episode when audio re-encodes (one-shot pass); near-instantaneous when `AudioComplete=true` (stream-copy both video and audio -- pure I/O).

## Safety contract -- rename-before-encode

The original file is renamed to `.orig` BEFORE FFmpeg runs. With the source path now free, FFmpeg writes directly to the final target name -- no `_remuxed` suffix, no suffix-strip step at the end. If anything fails between rename and final verification, rollback restores the source from `.orig`:

```
Original on disk:        T:\Show\episode.mp4    (the only copy of this content)

Step 1  [PREPARE]  PrepareReplacement:
                   T:\Show\episode.mp4  ->  T:\Show\episode.mp4.orig
                   Refuses to clobber a pre-existing .orig (forces operator
                   to clean up after a prior crash).

Step 2  [ENCODE]   FFmpeg reads from .orig, writes to the freed source path:
                   ffmpeg -i T:\Show\episode.mp4.orig ... T:\Show\episode.mp4
                   No path collision because the original is no longer at
                   that path -- it lives at .orig.

Step 3  [VERIFY]   FileReplacement._ProcessCompleteFileReplacement detects
                   the pre-renamed state (Step 1's .orig already exists),
                   skips its own rename step, and verifies the new file at
                   T:\Show\episode.mp4 is present and non-zero.

Step 4  [DB]       Update MediaFiles row + recompute compliance.
                   Failure here does NOT roll back -- file is on disk; future
                   probe reconciles.

Step 5  [SETTLE]   Settle the .orig backup based on KeepSource:
                   - KeepSource=true  -> rename to legacy `.old<ext>`
                   - KeepSource=false -> delete the .orig backup
```

**Rollback on any failure in steps 2-3:**
- Delete partial target file at the freed path if one landed
- Rename `.orig` back to its original path
- Return failure; original is bit-identical to its pre-call state

The 2026-05-09 incident (FFmpeg truncated source via output==input collision) cannot recur because:
1. The source is no longer at the path FFmpeg writes to (PrepareReplacement moved it).
2. `BuildRemuxCommand` refuses to build a command where output==input as a defense-in-depth check.
3. If both layers ever fail, rollback restores the `.orig`.

## Stages

| # | Stage | Code path | What changes in DB | Failure mode |
|---|-------|-----------|--------------------|--------------|
| 1 | Claim | `DatabaseManager.ClaimNextPendingTranscodeJob` (atomic SELECT FOR UPDATE SKIP LOCKED) | `TranscodeQueue.Status='Running'`, `ClaimedBy=<worker>`, `ClaimedAt=NOW()` | Two workers can't claim same row (atomic claim) |
| 2 | Dispatch | `ProcessJob` line 351 -> `if Job.IsRemux: ProcessRemuxJob` | (none) | If `ProcessingMode` is malformed or unknown, falls through to standard transcode path -- defensive but not ideal |
| 3 | ActiveJob create | `CreateActiveJob(JobType='Remux', WorkerName, ProcessId, ThreadId)` | `ActiveJobs` row inserted | Failure aborts the job and resets the queue row to Pending |
| 4 | Source pre-flight | `os.path.exists()` after `PathResolve(StorageRootId, RelativePath)` | -- | Missing source: `MediaFiles.FFprobeFailureCount` incremented, queue row deleted, ActiveJob deleted, no TranscodeAttempt created (`TranscodeJob.feature.md` criteria 17-18) |
| 5 | TranscodeAttempt create | `CreateTranscodeAttempt(Job, ...)` | `TranscodeAttempts` row inserted with `Success=NULL` | Failure aborts; row marked failed |
| 6 | File staging | `SetupFilePreparation` resolves the worker-local source path | -- | In-place; no copy step |
| 7 | Command build | `CommandBuilder.BuildFFmpegCommand` (remux shape) | -- | Missing `FFmpegPath` raises `ValueError` -- aborts |
| 8 | Execute | `ExecuteTranscoding(Job, RemuxCommand, ...)` -- spawns `ffmpeg` via `VideoTranscodingService.TranscodeVideo` | `ActiveJobs.FFmpegPid` recorded after `Popen`; `TranscodeProgress` rows update during the run | FFmpeg non-zero exit: `HandleJobFailure` marks the attempt failed; queue row reset to Pending for retry |
| 9 | Result handling | `HandleRemuxResult` | `TranscodeAttempts.Success=true`, `QualityTestRequired=false`, `NewSizeBytes`, etc. | Continues even on size growth -- by design, remux is not aimed at disk savings |
| 10 | Quality test bypass | Disposition routes directly to FileReplacement (no VMAF) | -- | -- |
| 11 | File replacement | `FileReplacementBusinessService.ProcessFileReplacementWithVMAF` -- archive original, delete, move new file in, re-probe, update `MediaFiles` | `MediaFiles` (re-probed metadata, `TranscodedByMediaVortex=true`), `MediaFilesArchive`, `TranscodeAttempts.FileReplaced` | If `transcode-vs-remux-routing.feature.md` criterion 16 ships: post-flight gate is **skipped** for `Mode='Remux'` (audio re-encode may bump size by KB without semantic regression) |
| 12 | Compliance recompute | `priority-materialization.feature.md` post-flight hook calls `RecomputeForFiles([MediaFileId])` | `MediaFiles.IsCompliant`, `RecommendedMode`, `PriorityScore`, `AssignedProfile` updated -- expected to flip to `IsCompliant=true` | Recompute failure logged but doesn't roll back replacement (file is already swapped) |
| 13 | Cleanup | `DeleteTranscodeQueueItem(Job.Id)`, `DeleteTranscodeProgress`, `CompleteActiveJob` | TranscodeQueue row deleted, ActiveJobs marked Success=true | -- |

## Output Location

The `-mv.mp4.inprogress` file is written **next to the source**. FileReplacement renames it to drop `.inprogress`, archives the original metadata, and deletes the original source atomically. No worker-local scratch, no NFS-side staging directory.

## Audio Handling During Remux (AudioComplete-aware)

`BuildRemuxCommand` branches on `MediaFile.AudioComplete` (set by
`Features.AudioCompletion.AudioCompletionService`; see
`Features/AudioCompletion/audio-completion.flow.md`):

### Branch A -- AudioComplete = true (or AudioCorruptSuspect = true)

```
-c:v copy
-c:a copy
-tag:v hvc1           # only for HEVC sources
-movflags +faststart
```

Audio bytes pass through unchanged. Sub-second per file. Satisfies
criterion 26 (byte-identical audio) of
`transcode-vs-remux-routing.feature.md`.

**Refusal case:** if `AudioComplete = true` but `AudioCodec` is not in
the MP4-compat set (`aac`, `ac3`, `eac3`, `mp3`), `BuildRemuxCommand`
flips `AudioCorruptSuspect = true,
AudioCorruptReason = 'incompatible_codec_unsupported'` and returns
None. This is a logic-error guard -- it shouldn't reach here, but if a
data inconsistency does push it through, we refuse rather than fail at
the muxer.

### Branch B -- AudioComplete = false (one-shot pass)

```
-c:v copy
-c:a aac -b:a 128k                            # or eac3 for incompat sources -- see BuildAudioCodecArgs
-af loudnorm=...                              # parameters owned by linear-loudnorm.feature.md
-tag:v hvc1                                   # HEVC only
-movflags +faststart
```

The loudnorm filter runs exactly once per file in its lifetime.
Post-flight `MarkAudioComplete` flips the column to true so this branch
is never re-entered for this file. For DTS/TrueHD/FLAC/PCM sources,
`BuildAudioCodecArgs` selects EAC3 with channel-aware bitrate, so the
same one-shot pass handles codec conversion in addition to
normalization. See `Features/LoudnessAnalysis/linear-loudnorm.feature.md`
for the loudnorm parameter contract (linear-or-dynamic mode selection,
target loudness, LRA floor, measurement requirements).

Filters are reused from `BuildAudioFilters` -- same chain that fires on
the transcode path, so loudness consistency is uniform across pipelines.

## State Tables Touched

```
TranscodeQueue       -- Status: Pending -> Running -> (deleted on success)
ActiveJobs           -- one row per claim, with FFmpegPid recorded after Popen
TranscodeAttempts    -- one row, Success=NULL during run, true on completion
TranscodeProgress    -- live progress updates during ExecuteTranscoding
TemporaryFilePaths   -- canonical paths for cross-host coordination
MediaFiles           -- updated by re-probe + RecomputeForFiles on completion
MediaFilesArchive    -- snapshot of original metadata (taken by FileReplacement)
```

## Failure Modes

| Failure | Symptom | Resolution |
|---|---|---|
| Worker can't reach source via PathTranslation | Pre-flight `os.path.exists()` returns False | `MediaFiles.FFprobeFailureCount += 1`, queue row deleted, no TranscodeAttempt created. Existing scan-time guard skips the file on next populate. |
| Source has no audio stream (video-only file) | `BuildRemuxCommand` detects `HasAudio=False` via FFprobe analysis | Command is built with video-only mapping (`-map 0:v:0`, no `-map 0:a:*`, no audio codec/filter args). The file is remuxed to MP4 container with video copy only. No error -- this is a supported path. |
| FFmpeg fails (codec quirks, audio decode error) | TranscodeAttempt marked failed | Queue row reset to Pending; will be retried next claim cycle. Persistent failures: investigate via `TranscodeAttempts.ErrorMessage`. |
| File replacement fails | Original kept, `.inprogress` orphaned next to source | `TranscodeAttempts.FileReplaced=false`. Investigate; may need manual cleanup or `Scripts/FixStuckPostReplacementFiles.py`. |
| Re-probe reports `IsCompliant=false` after replacement | RecomputeForFiles flags the file again | Operator-visible warning. Indicates the remux didn't fully fix the file -- e.g. audio normalization filter didn't apply correctly. Inspect `TranscodeAttempts.FFpmpegCommand` for the actual command. |
| Recompute hook fails (DB unreachable) | `MediaFiles.IsCompliant` not flipped | Replacement still succeeded; rerun the admin recompute endpoint or wait for the next probe to fire the hook. Loud warning logged. |

## Out of Scope

- VMAF is **never** run on remux outputs -- video is bit-identical to source, so VMAF would always score ~100. Skipping it saves CPU.
- Remux is not aimed at disk savings. The post-flight "no savings" gate (transcode-vs-remux-routing.feature.md criterion 16) is **skipped** for `Mode='Remux'`.
- Subtitle handling on remux is currently passthrough (no `-c:s` mapping). If the source has embedded subtitles in formats MP4 doesn't accept, they may be stripped. Distinct `Mode='SubtitleFix'` exists for that case.

## Related Docs

- `transcode.flow.md` -- Stages 1-7 of the broader transcode pipeline; this flow is a Mode-divergent branch within Stage 5 (TRANSCODE) and uses the same Stages 6 (skipped) and 7 (REPLACE).
- `Docs/AudioStrategy.md` -- audio normalization rules and decision matrix.
- `Features/TranscodeQueue/transcode-vs-remux-routing.feature.md` -- the cascade that decides which files get routed here.
- `Features/TranscodeQueue/queue-priority.feature.md` -- workers claim by `Priority DESC`; remux items are not specially prioritized today.
