# Media Tabs and Loudness Analysis

**Slug:** media-tabs-and-loudness

## What It Does

Three changes shipped together because they reinforce each other:

1. **Loudness Analysis** (data layer): captures `SourceIntegratedLufs`, `SourceLoudnessRangeLU`, and `SourceTruePeakDbtp` per MediaFile via FFmpeg's `ebur128` filter. Measurements drive smarter `AudioComplete` decisions -- files already at -23 LUFS are marked complete without ever running through the normalize chain.
2. **Reprobe lifecycle**: a one-time full-library reprobe (re-runs `ffprobe` *and* `ebur128` on every MediaFile) plus an on-demand per-folder / per-file rescan API. Today, probe metadata is captured once on scan and never refreshed unless a file replacement triggers it; this feature makes refresh first-class.
3. **Media tabs UX**: `/TranscodeQueue` splits into three sub-tabs -- **Transcode**, **Remux**, **Audio Fix** -- each filtered to its `ProcessingMode`. The Audio Fix tab adds folder-level priority hints so the operator can say "do all of `Westworld` next." Which bucket and job label a file gets is defined in `transcode.flow.md` D2 + D4.

Together they answer two operator questions:
- *"Which files in the library will play at noticeably different volume than the rest?"* -- via `SourceIntegratedLufs` distance from -23 LUFS.
- *"Which files have wide dynamic range that the compressor will hit hard?"* -- via `SourceLoudnessRangeLU > 18`.
- *"Now that I know, how do I tell MediaVortex to prioritize fixing them?"* -- via the Audio Fix tab with folder hints.

## Concern

Operator concerns this feature resolves:

1. **No loudness measurement today.** The cascade decides "needs normalize / doesn't need normalize" using bitrate proxies (channel-aware floor) and history (loudnorm-in-past-command). Neither tells us what the audio actually *sounds* like. Bitrate and codec do not predict perceived loudness.

2. **No way to identify "remote-grab" files.** Two files both AAC stereo 192 kbps could be mastered at -23 LUFS or -14.5 LUFS and look identical in our DB. The 8.5 dB perceived difference between them is what makes the operator reach for the TV remote. We have no signal for this today.

3. **No way to identify wide-dynamic-range files at risk of audio damage.** Files with LRA > 18 LU (typical theatrical mixes) need to be flagged for the operator so the right loudnorm behavior gets applied (see `Features/AudioNormalization/audio-normalization.feature.md` C36 for the linear-mode two-pass loudnorm invariant driven by these measurements). We can't surface these for review without measurement.

4. **Probe data goes stale.** A file scanned in 2024 with FFprobe results that haven't been refreshed -- if the file was replaced out-of-band, edited, or if FFprobe was upgraded -- still carries the old metadata. There's no mechanism to refresh.

6. **Queue is presented as one undifferentiated list.** Transcode jobs (90 minutes) and Remux jobs (15 seconds) currently mix in the same view. The operator cannot easily say "let me kick off a batch of Remuxes while the Transcodes run overnight" without manually filtering. A tabbed view by job type makes the queue actionable.

## Surface

User-facing -- three GUI changes + one new admin endpoint:

1. `/TranscodeQueue` page restructured: header gains a tab bar with three tabs (Transcode / Remux / Audio Fix) each showing a pending count. Each tab body is the existing queue list filtered to its mode.
2. Audio Fix tab adds a "Prioritize folder" input + button (and a list of currently-pinned folders).
3. SmartPopulate (Card 1 on `/Scanning` or wherever it lives) gets a "Mode" column showing the cascade's decision per row, so the operator sees which tab each suggestion will land on.
4. `POST /api/MediaProbe/Reprobe` admin endpoint accepts scoped filters (`MediaFileIds[]`, `ShowFolder`, `Drive`) and runs a probe + loudness measurement pass over matching rows. No-body call returns 400 (no unbounded reprobes).

See `transcode.flow.md` D2 + D4 for which bucket and job label a file
gets. See `Features/AudioCompletion/audio-completion.flow.md`
for how `AudioComplete` is decided.

## Success Criteria

### A. Loudness Analysis -- schema

1. `MediaFiles.SourceIntegratedLufs FLOAT` column exists, nullable. Represents EBU R128 integrated loudness of the source audio in LUFS. Migration `Scripts/SQLScripts/AddSourceLoudnessColumns.py` is idempotent. Verifiable: `\d MediaFiles` shows the column.

2. `MediaFiles.SourceLoudnessRangeLU FLOAT` column exists, nullable. Represents EBU R128 loudness range in LU. Higher = wider dynamic range. Verifiable: same migration.

3. `MediaFiles.SourceTruePeakDbtp FLOAT` column exists, nullable. Represents EBU R128 true-peak in dBTP. Anything > 0 will clip on some DACs. Verifiable: same migration.

4. `MediaFiles.LoudnessMeasuredAt TIMESTAMP` column exists, nullable. Set to NOW() whenever the three measurements are written. Used to detect stale measurements (e.g. when a file was replaced post-measure). Verifiable: same migration.

### B. Loudness Analysis -- service

5. `Features/LoudnessAnalysis/LoudnessAnalysisService.py` exists with at least these methods:
   - `MeasureLoudness(FilePath: str, AudioStreamIndex: int = 0) -> Optional[LoudnessResult]` -- runs `ffmpeg -af ebur128=peak=true` against the file's selected audio stream, parses the summary block from stderr, returns `(IntegratedLufs, LoudnessRangeLU, TruePeakDbtp)` or None on parse failure / FFmpeg error.
   - `PersistLoudness(MediaFileId: int, Result: LoudnessResult) -> bool` -- writes the four columns in one UPDATE; sets `LoudnessMeasuredAt = NOW()`.
   - `IsMeasurementStale(MediaFile) -> bool` -- returns true if `LoudnessMeasuredAt IS NULL` or earlier than the file's most-recent `TranscodeAttempts.FileReplacedDate`.
6. `MeasureLoudness` is the only place that invokes FFmpeg for measurement (single seam). Caller passes a pre-resolved local path; PathTranslation happens upstream. Verifiable: grep confirms no other call site invokes `ebur128`.

### C. Loudness Analysis -- integration

7. MediaProbe pipeline (`Features/MediaProbe/MediaProbeBusinessService.py`) is extended: after a successful FFprobe, the service also invokes `LoudnessAnalysisService.MeasureLoudness` against the same file and persists. Failure of the loudness step does NOT roll back the probe -- loudness is best-effort; the columns stay NULL on failure and the next reprobe retries. Verifiable: insert a fresh MediaFile, run probe, observe both probe metadata and loudness columns populated.

8. `Scripts/SQLScripts/BackfillSourceLoudness.py` measures every `MediaFiles` row where `SourceIntegratedLufs IS NULL`. Idempotent (resumable). Expected runtime: ~30k files at ~1.5 sec/file = ~12-14 hours single-threaded; can be parallelized across worker capability. Reports progress every 100 rows.

### D. Loudness Analysis -- cascade integration

9. `AudioCompletionService.EvaluateInitialAudioState` is extended: when `SourceIntegratedLufs IS NOT NULL` and within ±1 LU of -23 LUFS (so [-24, -22]), the file is marked `AudioComplete=true` regardless of other signals. Reason: `'already_at_target_loudness'`. The reasoning: there's no useful work for loudnorm to do; running the chain would only introduce artifacts. Verifiable: insert a row with `SourceIntegratedLufs = -23.2`, run `EvaluateInitialAudioState`, observe AudioComplete=true.

10. `BackfillAudioComplete.py` (existing script) gains a Pass 5: after the existing four passes, files where `SourceIntegratedLufs` is in [-24, -22] are flipped to `AudioComplete=true, AudioCorruptReason='already_at_target_loudness'`. Run after `BackfillSourceLoudness.py` completes. Idempotent.

### E. Reprobe lifecycle

11. `Features/MediaProbe/MediaProbeController.py` exposes `POST /api/MediaProbe/Reprobe` with JSON body accepting `MediaFileIds: List[int]`, `ShowFolder: str`, or `Drive: str`. At least one filter required (refuses unbounded calls). Returns `{Success, Queued}` where `Queued` is the number of files added to the reprobe queue.

12. Reprobe queue mechanism: rather than blocking on FFmpeg synchronously, the endpoint inserts rows into a new `ReprobeQueue` table (or extends an existing scan/probe queue) with `Status='Pending'`, `Priority`, `MediaFileId`. The MediaProbe worker capability claims these in `Priority DESC` order. Verifiable: POST with one MediaFileId, observe `ReprobeQueue` row inserted with Status=Pending.

13. One-time full-library reprobe migration: `Scripts/SQLScripts/QueueFullLibraryReprobe.py` inserts every `MediaFiles.Id` into `ReprobeQueue` at low priority. Designed to run once after this feature lands so existing files get loudness measurements + fresh FFprobe data. Idempotent (skips rows already pending or in-progress). Reports total queued.

14. After successful reprobe of a file, the MediaProbe worker calls `LoudnessAnalysisService.MeasureLoudness` in the same pass (criterion 7) and then `RecomputeForFiles([MediaFileId])` so the cascade picks up fresh state. Verifiable: queue a reprobe for a file with stale loudness, observe LoudnessMeasuredAt updated post-run.

### F. Job labels

Which job label a file is queued under, and what that label's command does to the file, is defined once in `transcode.flow.md` D2 (labels) + D4 (buckets). Not restated here.

17b. **[BUG-0005]** Every command builder writing to a `.inprogress` output filename MUST include the FFmpeg `-f mp4` flag (or the appropriate muxer name when not MP4). FFmpeg's auto-detection reads only the LAST filename extension, sees `.inprogress`, fails to find a muxer, and exits with `AVERROR(EINVAL) = -22`. Verifiable: build a Remux command for any MediaFile, observe `-f mp4` appears between the codec args and the output path; running the command end-to-end completes without the "Unable to choose an output format" error.

17c. **[BUG-0006]** `Remux` and `AudioFix` queue rows are claimed under `Workers.RemuxEnabled`, NOT under `TranscodeEnabled` (see `Features/ServiceControl/capability-control-plane.feature.md` criterion 6). Verifiable: with `Workers.RemuxEnabled=true, TranscodeEnabled=false` on a worker, queue a row with `ProcessingMode='Remux'`; observe the worker claims it within the capability-poll interval. Symmetric: with `RemuxEnabled=false, TranscodeEnabled=true`, that same row is NOT claimed by that worker.

### G. Media tabs UI

21. The Audio Fix tab gains a "Prioritize folder" control: input box accepting a folder name (autocomplete from `ShowFolders`), plus a list of currently-pinned folders with remove buttons. Pinning persists to `AudioFixPriorityHints` table. Verifiable: pin `Westworld`, observe `AudioFixPriorityHints` row inserted; Audio Fix tab list re-orders so Westworld files surface at the top.

22. When a file is queued as `AudioFix` and a folder pin matches its show folder, the `TranscodeQueue.Priority` is set higher (or a "BoostedPriority" column reflects the pin). Verifiable: pin a folder, run RecomputeForFiles, observe pinned-folder rows have higher Priority than unpinned ones of the same mode.

### H. Operator visibility

23. The Activity page's Library Compliance panel is added in this feature. It shows counts by:
    - Compliance: total / IsCompliant=true / IsCompliant=false / IsCompliant=NULL
    - Work bucket breakdown (Transcode / Remux / AudioFix / none)
    - Audio sub-section: AudioComplete=true / false / NULL / AudioCorruptSuspect=true (by reason)
    - **NEW** Loudness sub-section: distribution by integrated LUFS band (on target ±1, close ±3, off 3-6 LU, way off 6+ LU), unmeasured count, LRA > 18 count
   Verifiable: visual inspection plus SQL reconciliation against MediaFiles GROUP BY.

24. `/api/MediaProbe/ReprobeQueueStatus` endpoint returns `{Pending: N, Running: M, CompletedLast24h: K}` for the reprobe queue. Used by the Reprobe button in `/Work/<bucket>` to show in-flight status. Verifiable: queue 100 reprobes, observe Pending=100 in the response.

## Status

COMPLETE 2026-05-17 -- all 22 criteria implemented and committed. One operational task ongoing: the loudness backfill is running in the background (4 parallel shards across larry-workers, ~3-7 days expected). System is usable today with whatever portion has been measured; remaining files trickle in as the backfill grinds.

## Phase 1 -- Surgical data capture (kick off while we build the rest)

The full feature is large. To parallelize, Phase 1 ships only the schema + a standalone backfill script that an operator runs manually on any paused worker. The measurement pass runs unattended for ~20 hours; Phase 2 work proceeds during that window.

**Phase 1 surface (criteria 1-4 + change-detection + index + backfill):**
- 6 columns added to MediaFiles: `SourceIntegratedLufs`, `SourceLoudnessRangeLU`, `SourceTruePeakDbtp`, `LoudnessMeasuredAt`, `LastProbedFileSize`, `LastProbedFileMtime`
- 1 partial index: `idx_mediafiles_loudness_unmeasured`
- 1 idempotent migration: `Scripts/SQLScripts/AddSourceLoudnessAndChangeDetection.py`
- 1 standalone backfill script: `Scripts/SQLScripts/BackfillProbeAndLoudness.py`
  - `--worker-name <name>` arg: resolves `Workers.FFmpegPath` + `WorkerShareMappings` MountMap from DB
  - Reads `MediaFiles WHERE SourceIntegratedLufs IS NULL AND AudioCorruptSuspect = FALSE ORDER BY PriorityScore DESC NULLS LAST`
  - For each: `os.stat()` → check mtime+size short-circuit → `ffmpeg -af ebur128=peak=true` → parse stderr summary → persist
  - Resumable, idempotent, progress every 100 rows
  - Failures: stamp `LoudnessMeasuredAt=NOW()` with NULL measurements (so we don't retry forever; criterion 8 semantics)
  - Runs on any paused worker; no daemon involvement; no claim of TranscodeQueue rows
- Smoke test: `--limit 5` on the operator's chosen worker to confirm parsing + path translation work before full run
- Coordination: operator launches the script in their preferred terminal; can interrupt + resume freely

**Phase 1 NOT in scope** (Phase 2 covers):
- `Features/LoudnessAnalysis/LoudnessAnalysisService.py` (the proper Python module -- Phase 1 backfill is throwaway code that gets superseded)
- MediaProbe loudness integration (criterion 7)
- Reprobe endpoint + queue (E11-E14)
- Cascade `AudioComplete` bump on target-loudness files (D9-D10)
- `AudioFix` job label (F)
- Media tabs UI (G21-G22)
- Activity panel + visibility queries (H23-H24)
- Cross-feature doc updates

### Progress

- [x] Feature doc (this file) drafted
- [x] Decision: ONE feature (kept) -- shipped as a single composite with clean criteria boundaries
- [x] Decision: AudioFixPriorityHints standalone table (kept) -- transient operator state, not durable per-show config
- [x] Decision: NeedsReprobe column on MediaFiles (replaced "ReprobeQueue table") -- lighter; existing GetFilesNeedingProbe loop picks up flagged rows
- [x] Step 1: Loudness schema (A1-A4) + change-detection columns (LastProbedFileSize/Mtime) + partial index -- commit `440fa6d`
- [x] Step 2: LoudnessAnalysisService (B5-B6) -- commit `440fa6d`
- [x] Step 3: BackfillProbeAndLoudness.py (Phase 1) -- ongoing; setsid-launched, 4-shard, persistent across disconnects
- [x] Step 4: MediaProbe loudness integration (C7) -- commit `440fa6d`
- [x] Step 5: Cascade target-loudness short-circuit (D9-D10) -- commit `440fa6d`; Pass 5 in BackfillAudioComplete.py upgrades on-target files
- [x] Step 6: ProcessingMode trichotomy in cascade (F15-F17) -- commit `440fa6d`; TranscodeQueueModel.IsRemux includes 'AudioFix'
- [x] Step 7: Reprobe endpoints (E11-E14) -- commit `440fa6d`; uses NeedsReprobe column
- [x] Step 8: One-time full-library reprobe script (E13) -- `QueueFullLibraryReprobe.py`; idempotent
- [x] Step 9: Media tabs UI (G18-G20) -- commit `4573b36`; Queue.html three sub-tabs, ?mode=, ModeCounts in response
- [x] Step 10: Audio Fix folder pins (G21-G22) -- commit `f56d444`; AudioFixPriorityHints table + cascade integration + UI widget
- [x] Step 11: Activity panel (H23-H24) -- commit `519d44d`; /api/Activity/LibraryCompliance + 2x2 grid
- [ ] Step 12: Cross-feature doc updates -- IN PROGRESS (this update)
- [ ] Step 13: Live operator smoke test -- pending workers + WebService start

### Operational handoff

WebService restart picks up these new blueprints:
- `AudioCompletionBlueprint`   (/api/AudioCompletion/{Reset, MarkComplete})
- `ActivityBlueprint`          (/api/Activity/LibraryCompliance)
- `AudioFixPriorityHintsBlueprint` (/api/AudioFixPriorityHints/{List, Add, Remove, ApplyAll})
- MediaProbe endpoints extended: /api/MediaProbe/Reprobe (POST + DELETE), /api/MediaProbe/ReprobeQueueStatus
- /api/TranscodeQueue/GetQueue gains ?mode= query parameter

Backfill monitoring (any time):
```
ssh root@larry "pct exec 218 -- sh /tmp/_status_shards.sh"
```

## Open design questions

The criteria above bake in specific designs. Items below are intentionally
called out where I made a judgment call -- speak up if you'd rather take a
different route:

1. **Reprobe queue separate table vs reuse FileScanQueue?** I sketched a new `ReprobeQueue` for clarity but extending the existing scan queue with a `Kind='Reprobe'` discriminator is cheaper. I lean toward the new table because reprobe priorities, retry semantics, and triggers diverge from scan over time.
2. **Folder pins separate table (resolved).** `AudioFixPriorityHints` standalone table. Pins are operator-actionable transient state, not durable per-show config -- they get cleared as the work completes.
3. **"AudioFix" name or something better?** The user prompted "(or a better name)". Alternatives: "Audio Pass", "Loudness Fix", "Sound Fix". I went with `'AudioFix'` because it's the verbiage the cascade already uses internally; happy to rename.
4. **Loudness measurement runs on file open or batched?** I chose: at MediaProbe time + a reprobe pass. Alternative: measure-on-demand during cascade evaluation (lazy). I rejected lazy because it would block the cascade for ~1.5 sec/file and the cascade is called in tight loops (RecomputeForFiles).
5. **Should the existing "Remux" tab be renamed to "Container Fix"?** The user's mental model is "1-Transcode 2-Remux 3-Audio fix". "Remux" is technically accurate but operator-mysterious. "Container Fix" is more honest about what it does. Worth a rename? I left it as Remux for now to minimize disruption to existing operator habits.

## Scope

```
Features/TranscodeQueue/media-tabs-and-loudness.feature.md  -- (THIS FILE)
Features/LoudnessAnalysis/LoudnessAnalysisService.py        -- (NEW) ebur128 invoker + parser + persister
Features/LoudnessAnalysis/__init__.py                       -- (NEW)
Features/MediaProbe/MediaProbeBusinessService.py            -- chain loudness measurement after probe
Features/MediaProbe/MediaProbeController.py                 -- POST /api/MediaProbe/Reprobe endpoint
Features/MediaProbe/MediaProbeWorker.py (or equivalent)     -- claim ReprobeQueue rows + measure + recompute
Features/AudioCompletion/AudioCompletionService.py          -- extend EvaluateInitialAudioState with loudness clause
Features/TranscodeQueue/QueueManagementBusinessService.py   -- queue admission for the AudioFix label; folder-pin boost
Features/TranscodeQueue/TranscodeQueueController.py         -- tab filtering, mode counts, folder-pin endpoint
Features/TranscodeQueue/TranscodeQueueViewModel.py          -- mode counts, audio-fix-pin queries
Features/Activity/...                                        -- Library Compliance panel + loudness sub-section
Templates/TranscodeQueue.html                                -- tab bar + per-tab body + folder-pin controls
Templates/SmartPopulate (Card 1)                             -- Mode column
Scripts/SQLScripts/AddSourceLoudnessColumns.py              -- (NEW)
Scripts/SQLScripts/AddReprobeQueue.py                       -- (NEW) or extend FileScanQueue
Scripts/SQLScripts/AddAudioFixPriorityHints.py              -- (NEW) standalone AudioFixPriorityHints table
Scripts/SQLScripts/BackfillSourceLoudness.py                -- (NEW) one-time measurement pass
Scripts/SQLScripts/QueueFullLibraryReprobe.py               -- (NEW) one-time reprobe seed
Scripts/SQLScripts/BackfillAudioComplete.py                 -- extend with Pass 5 (target-loudness)
Features/AudioCompletion/audio-completion.feature.md          -- amend C9 (cascade reads SourceIntegratedLufs)
transcode.flow.md                                              -- Stage 4 (queue) tab structure noted
```

## Files

| File | Role |
|------|------|
| Feature doc (this file) | Contract |
| `Scripts/SQLScripts/AddSourceLoudnessColumns.py` | Idempotent ADD COLUMN SourceIntegratedLufs / SourceLoudnessRangeLU / SourceTruePeakDbtp / LoudnessMeasuredAt |
| `Scripts/SQLScripts/AddReprobeQueue.py` | NEW table or FileScanQueue extension (TBD) |
| `Scripts/SQLScripts/AddAudioFixPriorityHints.py` | NEW standalone `AudioFixPriorityHints` table |
| `Scripts/SQLScripts/BackfillSourceLoudness.py` | One-time measurement pass over the ~30k AudioComplete=false library |
| `Scripts/SQLScripts/QueueFullLibraryReprobe.py` | One-time reprobe seed for all 56,698 MediaFiles rows |
| `Features/LoudnessAnalysis/LoudnessAnalysisService.py` | MeasureLoudness (ebur128 invoke + parse), PersistLoudness, IsMeasurementStale |
| `Features/MediaProbe/MediaProbeBusinessService.py` | Chain LoudnessAnalysisService after FFprobe; expose reprobe |
| `Features/MediaProbe/MediaProbeController.py` | POST /api/MediaProbe/Reprobe + GET /api/MediaProbe/ReprobeQueueStatus |
| `Features/AudioCompletion/AudioCompletionService.py` | EvaluateInitialAudioState gets a target-loudness clause |
| `Features/TranscodeQueue/QueueManagementBusinessService.py` | Queue admission for the `AudioFix` label; folder-pin boost |
| `Features/TranscodeQueue/TranscodeQueueController.py` | Tab counts endpoint; folder-pin POST endpoint |
| `Features/TranscodeQueue/TranscodeQueueViewModel.py` | Per-mode count queries; AudioFixPriorityHints query |
| `Templates/TranscodeQueue.html` | Tab bar + per-tab body + folder-pin controls |
| `Templates/SmartPopulate row template` | `Mode` badge column |
| `Features/Activity/...` | Library Compliance panel (deferred from prior feature) + Loudness sub-section |

## Deviation from conventions

**Multi-concern feature.** This feature spans loudness analysis (data), reprobe lifecycle (probe pipeline), and queue UX (UI). Each is large enough to be its own feature, and traditional convention is one-concern-per-feature. Bundling is intentional: the three concerns reinforce each other. Shipping them piecemeal would leave each in a half-useful state.

Implementation may still split into sibling features for clean code review (e.g. `loudness-analysis.feature.md` covering criteria A-D, `reprobe-lifecycle.feature.md` covering E, `media-tabs.feature.md` covering F-G-H). The decision is deferred to the operator at review time. The runbook order above keeps them in dependency order regardless of doc split.
## Interrupts

This feature was filed as a `/n` PIVOT while the parent `audio-completion` work was awaiting operator smoke test. `audio-completion` is **code complete and committed** (commit `48555ba`, 2026-05-17) -- it is not paused, just awaiting the FFmpeg byte-identical hash verification once workers come up. This feature builds on top of it: the loudness data added here will refine the `AudioComplete` decisions audio-completion already makes.

Stack order at filing time:
```
version-on-deploy            (parent, unmodified)
media-tabs-and-loudness      (this feature)
```
