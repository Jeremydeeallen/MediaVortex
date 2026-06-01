# Flow: Media Queue tabs (Transcode / Remux / Audio Fix)

**Slug:** media-tabs

## Entry Point

`GET /TranscodeQueue` renders the Media Queue page. The page restructures
the current single-mode listing into three sub-tabs, each filtered to a
distinct `TranscodeQueue.ProcessingMode` (and the underlying
`MediaFiles.RecommendedMode` that placed the row there):

| Tab | Mode | What's in it | Cost shape |
|---|---|---|---|
| **Transcode** | `'Transcode'` | Files where video re-encode is required: downscale, codec change to AV1, large estimated savings | Heavy (5-90 min per file depending on resolution and CRF) |
| **Remux** | `'Remux'` | Files where only the container needs fixing (MKV -> MP4) and audio is already complete | Light (5-30 sec per file -- I/O bound) |
| **Audio Fix** | `'AudioFix'` | Files where the audio needs the one-shot normalize pass (and possibly codec conversion), but no container or video work | Light-to-medium (audio decode + filter chain + encode; ~10-60 sec per file depending on duration) |

The tabs are operator-facing labels on top of cascade routing. The
worker still uses two FFmpeg command builders: `BuildCommand` (transcode
path) and `BuildRemuxCommand` (everything that doesn't re-encode video).
`Remux` and `AudioFix` queue rows both route to `BuildRemuxCommand` at
the worker; what differs is the operator's mental model and the
priority surface.

## Promise

Each tab is a focused queue of *like work*:

1. **Transcode** is for slow, expensive jobs. The operator schedules a few at a time, expects them to take hours.
2. **Remux** is the quick wins -- container fixes that finish in seconds. Batch through hundreds before lunch.
3. **Audio Fix** is the dialogue-and-loudness pass. Folder prioritization is first-class here -- the operator can say "do all of `Westworld` next" or "do everything on the T:\ drive."

When a file needs *both* container fix and audio normalization, it lands
on the **Remux** tab (not duplicated across tabs). `BuildRemuxCommand`
already handles both in one FFmpeg invocation -- this is the
"workers-already-opened-the-file, do both passes" efficiency. The Audio
Fix tab is reserved for files where audio is the *only* concern.

## Stages

| # | Stage | Code path | What changes |
|---|-------|-----------|---|
| 1 | Tab render | `TranscodeQueueController.GetTranscodeQueue()` accepts `?mode=Transcode|Remux|AudioFix`; returns rows filtered to that mode plus counts for the other tabs (so the tab badges show pending counts) | -- |
| 2 | Row selection | Operator clicks rows or "Select All in folder" | client-side selection state |
| 3 | Reprioritize (Audio Fix tab only) | Operator types/picks a folder name; click "Move to top" | `TranscodeQueue.Priority` updated for matching rows; SmartPopulate hint persisted to a new `AudioFixPriorityHints` table (or ShowSettings extension) so future cascade decisions for that folder land at the top |
| 4 | Queue execution | WorkerService claims `Status='Pending'` rows in `Priority DESC` order, respecting per-mode concurrency limits | TranscodeQueue.Status -> Running -> deleted on success |
| 5 | Post-flight | Standard FileReplacement + RecomputeForFiles. Re-probe + re-measure loudness so the row drops out of the tab automatically | MediaFiles.AudioComplete, SourceIntegratedLufs, IsCompliant, RecommendedMode all updated |

## Cascade -> Tab mapping

`_EvaluateCompliance` in `QueueManagementBusinessService` currently
returns `(IsCompliant, RecommendedMode)` where `RecommendedMode in
{'Transcode', 'Remux', None}`. This feature extends the set:

```
Cascade decision                                  | RecommendedMode  | Tab
--------------------------------------------------|-------------------|------------
Video re-encode needed (codec, resolution,        | 'Transcode'       | Transcode
savings >= threshold)                             |                   |
--------------------------------------------------|-------------------|------------
Container only (MKV -> MP4), audio already        | 'Remux'           | Remux
complete (-c:a copy works)                        |                   |
--------------------------------------------------|-------------------|------------
Audio not complete AND container needs fix        | 'Remux'           | Remux
  (bundled: BuildRemuxCommand handles both in     |                   |
  one FFmpeg pass)                                |                   |
--------------------------------------------------|-------------------|------------
Audio not complete AND container is fine          | 'AudioFix'        | Audio Fix
  (no MKV -> MP4 needed; just the one-shot        |                   |
  normalize + possible codec convert)             |                   |
--------------------------------------------------|-------------------|------------
Already compliant                                 | None              | (not queued)
--------------------------------------------------|-------------------|------------
Suspect / undecidable                             | None              | (not queued;
                                                  |                   |  Activity panel)
```

**Why bundle audio + container into Remux, not split:** when both are
needed, FFmpeg already does both in a single decode-encode pass. Routing
them as separate jobs would mean opening the file twice. The
single-Remux-pass keeps the worker's file-open count to one.

## Output Location

In-place: the `.inprogress` file lands next to the source, then
FileReplacement renames it and swaps the original out. No new output paths.

## State Tables Touched

```
MediaFiles               -- IsCompliant, RecommendedMode, AudioComplete,
                            SourceIntegratedLufs, SourceLoudnessRangeLU,
                            SourceTruePeakDbtp, LoudnessMeasuredAt
TranscodeQueue           -- ProcessingMode now includes 'AudioFix'
AudioFixPriorityHints    -- (NEW) folder-level priority overrides for Audio Fix tab
                           (or extension to ShowSettings)
```

## Failure Modes

| Failure | Symptom | Resolution |
|---|---|---|
| Cascade routes to 'AudioFix' for a file whose container also needs fixing (logic error) | Worker runs Remux command which container-fixes too; post-flight cascade discovers container is fine and drops out cleanly | No-op; the bundled FFmpeg call handled both anyway. Investigate the cascade discrepancy via TranscodeAttempts row. |
| Worker version doesn't know about ProcessingMode='AudioFix' (cross-version skew) | Worker falls through to the standard Remux dispatch (existing dispatcher checks `IsRemux` boolean, not exact mode string) | New code maps AudioFix -> IsRemux=True at dispatch. Old workers also see it as Remux because the row payload is identical. Graceful. |
| Reprioritize on a row that's already Running | UPDATE no-ops because the row's Priority is read at claim time, not during execution | Operator sees the prioritization apply on the next claim cycle. Loud info-log if the prioritized row was already running. |
| Folder priority hint persists after files in that folder all become compliant | Stale hint in `AudioFixPriorityHints` | Hint is read fresh per render; UI shows it next to "0 pending files" if there are no matches. Operator can clear it. |

## Out of Scope

- Per-mode worker pools (a Worker that does only AudioFix vs only Transcode). Workers stay polyvalent; per-mode concurrency limits live in `Workers.MaxConcurrentJobs` and can be tuned independently if needed.
- VMAF on Audio Fix outputs (video is bit-identical, no point).
- Multi-track audio preservation (still single English-track mapping per BUG-0003 architectural decision).

## Related Docs

- `Features/TranscodeQueue/transcode.flow.md` -- the broader pipeline; this flow restructures Stage 4's queue listing presentation, not the pipeline itself.
- `Features/TranscodeQueue/remux.flow.md` -- the worker-side Remux execution. AudioFix tab rows use this same code path.
- `Features/AudioCompletion/audio-completion.flow.md` -- the audio-completion state machine that drives the AudioFix routing decision.
- `Features/TranscodeQueue/transcode-vs-remux-routing.feature.md` -- the cascade that produces RecommendedMode (extended here to include 'AudioFix').
- `Features/MediaProbe/` -- the reprobe lifecycle feature (sibling to this one) that ensures loudness data is fresh.
