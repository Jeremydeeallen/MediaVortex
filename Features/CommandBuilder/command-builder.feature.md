# Command Builder -- One Function, One Decision Tree

## What It Does

Translates a `(MediaFile, Job)` pair into the single FFmpeg command line that
the worker will execute. **One entry point, one decision tree.** No
parallel methods for "transcode" vs "remux" vs "audio fix" vs "subtitle fix"
-- the work the file needs is derived from the file's compliance state and
the queue row's `ProcessingMode`, then a single function emits the
appropriate command shape.

## Concern

Three concerns the current sprawl created and this contract resolves:

1. **Duplicated logic across `BuildCommand` / `BuildRemuxCommand` / `BuildSubtitleFixCommand`.** Each one has its own copy of audio-branching (`AudioComplete=true → -c:a copy`), path normalization, output extension handling, and `-f mp4` flag. Three places to update on every change. BUG-0005 happened because `-f mp4` was missing in all three places; BUG-0003 happened because audio policy lived in one and not the others.

2. **Two-class layering with identical names is misleading.** `Services/CommandBuilderService.py.BuildRemuxCommand(Job, MediaFile, ...)` is a thin wrapper around `Models/CommandBuilder.py.BuildRemuxCommand(CommandData)`. Same method name, different signature, different return shape responsibilities. Callers that hit the wrapper look like they're hitting the builder. This caused real confusion during BUG-0003 debugging (we thought the new code wasn't reaching the worker; it was, just via the wrapper).

3. **Mode-specific dispatch in the worker bloats the surface.** `ProcessJob` branches on `IsRemux / IsSubtitleFix / IsTestMode` and routes to `ProcessRemuxJob / ProcessSubtitleFixJob / ProcessTestVariantJob`. Each calls a different builder. The branches exist because the builders have different signatures; if there were one builder, there'd be one dispatch path.

## Surface

Internal contract. No direct UI; affects every queued job through the
worker side of the pipeline. See `Features/TranscodeQueue/transcode.flow.md`
Stages 5-7 and `Features/TranscodeQueue/remux.flow.md` for the runtime
context this contract serves.

## Success Criteria

### A. Single entry point + decision tree

1. **One callable.** A single `CommandBuilder.BuildFFmpegCommand(MediaFile, Job, Context)` method is the only public way to obtain an FFmpeg command from inside a worker. `Context` carries the per-job operational data the builder needs but the model and job don't (FFmpegPath, OutputDirectory, InputPath after PathStorage resolution, IsLocalStaging, etc.). Verifiable: `grep -rE "def Build(Command|RemuxCommand|SubtitleFixCommand|TranscodeCommand)" Models/ Services/` returns exactly one match, the consolidated method (private helpers may exist; public methods do not).

2. **Decision tree is explicit and ordered.** Inside `BuildFFmpegCommand`, the routing is a single readable cascade:
    ```
    if NeedsTranscode(MediaFile, Job):
        return BuildTranscodeShape(...)   # video re-encode + audio + container
    if NeedsQuickFix(MediaFile, Job):
        return BuildRemuxShape(...)       # -c:v copy + audio + container
    # Compliant file -- shouldn't be here
    raise ValueError(f"MediaFile {MediaFile.Id} is compliant; no command to build")
    ```
   The three private shapes (`BuildTranscodeShape`, `BuildRemuxShape`, optionally `BuildSubtitleFixShape` if subtitles need their own branch) share a single `_CommonOutputFlags` helper for `-f mp4 -movflags +faststart -y`, a single `_BuildAudioArgs` helper for the AudioComplete branch, and a single `_NormalizePath` helper at the boundary. Verifiable: changing the output container flag (e.g. adding a new `-movflags` option) requires editing exactly one location.

3. **Decision tree predicates are derived, not duplicated.** `NeedsTranscode` reads `MediaFile.NeedsTranscode` (materialized by the cascade at recompute time). `NeedsQuickFix` reads `MediaFile.NeedsQuick`. The builder does not re-evaluate the cascade -- it trusts the materialized flags. If both are true, Transcode wins (heaviest mode subsumes the others). Verifiable: with `NeedsTranscode=true AND NeedsQuick=true`, `BuildFFmpegCommand` returns the Transcode shape, not the Remux shape.

4. **`ProcessingMode` selects the dispatch, the builder is the same.** The worker's `ProcessJob` continues to branch on `Job.IsRemux / IsTestMode` for code paths it needs around the actual FFmpeg execution (FileReplacement post-flight gate differs by mode, etc.). But ALL of those code paths call the same `BuildFFmpegCommand`. Verifiable: only one `CommandBuilder.BuildFFmpegCommand` call site per worker dispatch method (Process{Transcode,Remux,SubtitleFix,TestVariant}Job).

### B. Output shape (all branches)

5. **Output filename always ends `<basename>-mv.mp4.inprogress`** (per `worker-lifecycle.feature.md` criterion 6). The basename derivation may vary by branch (transcode bakes target resolution into the name when downscaling; remux keeps the source basename) but the suffix is uniform. Verifiable: every command emitted by the builder ends with a quoted path matching that pattern.

6. **`-f mp4` is always present** (BUG-0005). FFmpeg's extension-based muxer detection reads the LAST extension (`.inprogress`) and fails without an explicit format. Verifiable: every command emitted includes the literal token sequence `-f mp4` between the codec args and the output filename. Removing `-f mp4` from any code path is a test failure.

7. **`-movflags +faststart` is always present** for MP4 outputs. Standard web-streaming-friendly placement. Verifiable: same shape as criterion 6.

8. **Paths are normalized at the boundary** (BUG fix 2026-05-18, `_NormalizeFfmpegPath`). InputPath and OutputPath both pass through `os.path.normpath(path.strip().strip('"'))` before being quoted into the command. Result: uniform native separators on the active platform; no mixed `\` and `/` shapes. Verifiable: regex search the emitted command for `\\.*?/` (forward slash AFTER a backslash within the same quoted path) returns no matches on Windows.

### C. Audio policy (BUG-0003 contract)

9. **Audio is always `-c:a copy` when `MediaFile.AudioComplete=true`** -- byte-identical pass-through, no decode, no loudnorm. Identical behavior in Transcode and Remux branches. Verifiable: build a command for a file with `AudioComplete=true`; resulting command contains `-c:a copy` and does NOT contain `loudnorm` or `acompressor`.

10. **Audio runs through `BuildAudioCodecArgs + BuildAudioFilters` (the one-shot normalize chain) when `MediaFile.AudioComplete=false`.** Codec is selected by `BuildAudioCodecArgs` from the MP4-compat table (DTS/TrueHD/FLAC/PCM → EAC3 with channel-aware bitrate). Filters apply `acompressor + loudnorm` per the system-setting defaults. Identical behavior in Transcode and Remux branches. Verifiable: build a command for `AudioComplete=false`; command contains `loudnorm=I=-23` and a non-`copy` `-c:a` selection.

11. **Suspect short-circuit refusal.** If `MediaFile.AudioCorruptSuspect=true`, OR if `AudioComplete=true` AND `AudioCodec` is not in the MP4-compat set (logic-error state), `BuildFFmpegCommand` returns `None` and logs an error. The audio-suspect path also marks the row in `MediaFiles.AudioCorruptReason` for operator visibility. Verifiable: build a command for a synthetic suspect row; result is `None`; row gains `AudioCorruptReason`.

### D. Class consolidation

12. **One CommandBuilder class.** The `Services/CommandBuilderService.py` wrapper is removed. Callers that previously hit the wrapper construct the `Context` dict themselves and call `Models/CommandBuilder.BuildFFmpegCommand` directly. The pre-FFprobe stream detection that `CommandBuilderService.BuildRemuxCommand` ran (via `FFmpegAnalysisService.AnalyzeMediaFile`) is either (a) moved into the builder or (b) replaced by reading the already-probed `MediaFile.AudioCodec` / `MediaFile.AudioChannels` columns -- the file has been probed by the time it reaches the queue (per `FileScanning.feature.md` criterion 28). Verifiable: `find . -name CommandBuilderService.py` returns no files; all callers compile and tests pass.

### E. Migration safety

13. **In-flight legacy queue rows continue to work.** Any `TranscodeQueue` rows with `ProcessingMode IN ('Remux','AudioFix','SubtitleFix')` predating the consolidation must still dispatch correctly through the new single builder. The decision tree reads `MediaFile.NeedsQuick / NeedsTranscode` (the source of truth) rather than the legacy `ProcessingMode` string, so legacy rows route the same way new ones do. Verifiable: insert a synthetic queue row with each of the legacy modes, claim it via the appropriate poller, build the command, observe the same shape a `Quick`/`Transcode` row would produce.

## Status

**IMPLEMENTED 2026-05-18** (pending live smoke test).

### Progress

- [x] Audit current state -- 3 builders (BuildCommand, BuildRemuxCommand, BuildSubtitleFixCommand) + 1 wrapper layer (Services/CommandBuilderService)
- [x] Define decision tree (criteria 1-4)
- [x] Define output shape contract (criteria 5-8)
- [x] Define audio policy (criteria 9-11)
- [x] Operator approves criteria 1-13
- [x] Implement: add `BuildFFmpegCommand` as single public entry; rename shapes to `_BuildTranscodeShape` / `_BuildRemuxShape` / `_BuildSubtitleFixShape`; absorb FFprobe + scale-filter helpers from wrapper; drop dead `BuildVideoCodecParameters` and `ValidateCommandData`
- [x] Remove `Services/CommandBuilderService.py` wrapper
- [x] Update callers in `Features/TranscodeJob/ProcessTranscodeQueueService.py` (import, type, default, 3 call sites)
- [x] Compile verification: `Models/CommandBuilder.py`, `Features/TranscodeJob/ProcessTranscodeQueueService.py`, `WorkerService/Main.py` all parse and import cleanly
- [ ] Live smoke test: Transcode row, Quick row, SubtitleFix row each produce expected command shapes

## Scope

```
Models/CommandBuilder.py                         -- becomes single source of FFmpeg command generation
Services/CommandBuilderService.py                -- (REMOVED) -- wrapper layer no longer needed
Features/TranscodeJob/ProcessTranscodeQueueService.py -- callers updated to use single builder API
Features/TranscodeQueue/remux.flow.md            -- Stage 7 wording updated to reference single builder
Features/TranscodeQueue/transcode.flow.md        -- Stage 5 wording updated to reference single builder
```

## Files

| File | Role |
|------|------|
| Feature doc (this file) | Contract |
| `Models/CommandBuilder.py` | The one and only command builder, with private `_NormalizeFfmpegPath`, `_BuildAudioArgs`, `_CommonOutputFlags`, `_BuildTranscodeShape`, `_BuildRemuxShape` helpers and the single public `BuildFFmpegCommand` |
| `Models/MediaFileModel.py` | Source of `NeedsQuick`, `NeedsTranscode`, `AudioComplete`, `AudioCorruptSuspect` (already populated by cascade per media-tabs-and-loudness criteria 15-16) |
| `Features/TranscodeJob/ProcessTranscodeQueueService.py` | Single call site per dispatch method; constructs `Context` dict; reads return value |

## Deviation from conventions

CommandBuilder isn't a per-feature vertical (it serves Transcode, Remux,
SubtitleFix, and TestVariant dispatch paths). Placing the doc under
`Features/CommandBuilder/` rather than per-feature is the same shape as
`Features/AudioCompletion/` and `Features/LoudnessAnalysis/` -- shared
services that own a cross-cutting concern get their own feature dir.
