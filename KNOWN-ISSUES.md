# Known Issues

## Open

### [BUG-0006] Quick / AudioFix ProcessingMode rows routed to Transcode capability poller
**Date:** 2026-05-18

**What breaks:** `Repositories/DatabaseManager.ClaimNextPendingTranscodeJob` filters `(ProcessingMode IS NULL OR ProcessingMode != 'Remux')`. Anything that isn't literally `'Remux'` -- including the new `'Quick'` mode (post-2026-05-17 Remux+AudioFix collapse), the legacy `'AudioFix'`, and `'SubtitleFix'` -- gets claimed by the Transcode-side poller, which is gated on `Workers.TranscodeEnabled`. `ClaimNextPendingRemuxJob` filters `ProcessingMode = 'Remux'` (literal) and never claims any of them. Result: a Quick Fix queue row CANNOT be claimed by a worker that has `RemuxEnabled=true, TranscodeEnabled=false`. The operator must turn on TranscodeEnabled to drain the Quick queue, defeating the whole point of separating Quick from Transcode.

Operator confirmed 2026-05-18: enabled TranscodeEnabled on I9 to get a Quick row processed; until then RemuxEnabled=true alone left it sitting in Pending.

**Violates:** `Features/TranscodeQueue/media-tabs-and-loudness.feature.md` criterion 19 (Quick Fix card is claim-eligible via RemuxEnabled), and the implicit contract behind separating Quick from Transcode.

**Look first:** `Repositories/DatabaseManager.py:1682` `ClaimNextPendingTranscodeJob` filters at lines 1701 and 1718. `ClaimNextPendingRemuxJob` at 1756 (filter at line 1771). Both queries need their ProcessingMode predicate updated to keep Quick-class jobs on the Remux capability side. `TranscodeQueueModel.IsRemux` already returns True for `'Quick'/'Remux'/'AudioFix'` (commit f56d444, then 6c30c60). The DB-level claim filter is the missing piece.

**Fix with:** `/t BUG-0006`.

---

### [BUG-0005] FFmpeg muxer auto-detect fails on `.mp4.inprogress` output filename
**Date:** 2026-05-18

**What breaks:** `BuildRemuxCommand` (and `BuildSubtitleFixCommand`, and the transcode path) write to a `<basename>-mv.mp4.inprogress` filename per `worker-lifecycle.feature.md` criterion 6. FFmpeg reads the LAST extension (`.inprogress`) to pick a muxer, can't find one, exits with `AVERROR(EINVAL) = -22` and the stderr message `"Unable to choose an output format for '...'; use a standard extension for the filename or specify the format manually."`. The intermediate `.mp4` is ignored by FFmpeg's extension-based muxer detection. Confirmed 2026-05-18 against TranscodeAttempts 16550, 16551, 16552 -- three consecutive failures even after AudioComplete-aware command and clean Windows separators.

Verification: running the exact failing command with `-f mp4` added produces a successful 3.3 GB transcode in 2:43 (16.2x realtime), zero errors. Without `-f mp4`, same command fails at muxer init.

**Violates:** `Features/TranscodeQueue/remux.flow.md` Stage 7 (Command build promises a valid command that runs to completion when inputs are healthy). Also blocks `media-tabs-and-loudness.feature.md` criterion 17 verifiability.

**Look first:** `Models/CommandBuilder.py` `BuildRemuxCommand` (line 485), `BuildSubtitleFixCommand` (line 626), and `BuildCommand` (line 28 onwards for the transcode path). Each needs `'-f', 'mp4'` appended to CommandParts before the output filename. Already has `-movflags +faststart` for MP4, but `-movflags` doesn't imply muxer selection.

**Fix with:** `/t BUG-0005`.

---

### [BUG-0004] Workers.Status='Paused' does not gate capability claiming
**Date:** 2026-05-18

**What breaks:** Setting `Workers.Status='Paused'` via the Activity page UI Pause button is purely cosmetic. The worker daemon continues to claim and process jobs as long as the individual capability flags (`TranscodeEnabled`, `RemuxEnabled`, `QualityTestEnabled`, `ScanEnabled`) are TRUE. Confirmed 2026-05-18: larry-worker-8 with `Status='Paused'`, `RemuxEnabled=false`, `TranscodeEnabled=true` claimed and ran a Transcode job (`TranscodeAttempts.Id=16549`, Real Housewives S01E15 downscale to 480p). Operator had clicked Pause on the worker tile and expected NO claiming; the worker ran anyway because TranscodeEnabled stayed true.

**Violates:** `Features/TeamStatus/worker-status-model.feature.md` criterion 9 (added with this bug); also `Features/ServiceControl/capability-control-plane.feature.md` criterion 8 (Status='Online' must be a hard precondition for every capability, added 2026-05-18 amendment).

**Look first:** `WorkerService/Main.py:711` `_ApplyCapabilities` -- only checks `self.TranscodeEnabled / self.RemuxEnabled / self.QualityTestEnabled / self.ScanEnabled`; `self.WorkerStatus` is loaded from DB (line 311) but never consulted. The fix is to wrap or extend `_ApplyCapabilities` so any non-Online status short-circuits to "stop all capabilities" regardless of the individual flags. Draining state has its own rules (cf. worker-status-model.feature.md criterion 3) -- finish in-flight jobs but don't claim new ones; Paused stops immediately.

**Flow doc:** `Features/TeamStatus/worker-status-model.feature.md` describes the state model but no separate flow doc exists for capability-vs-status interplay; `/t` should either extend the existing feature doc's narrative or add a small flow doc.

**Fix with:** `/t BUG-0004`.

---

### [BUG-0003] Remux profile re-encodes audio and applies dynamics processing -- PENDING OPERATOR VERIFICATION
**Date:** 2026-05-16 (filed) / 2026-05-17 (implementation landed)

**What broke:** The `Remux` profile built an FFmpeg command that re-encoded audio to AAC and applied `acompressor=threshold=-15dB:ratio=3:attack=0.01:release=0.1:makeup=3dB` followed by `loudnorm=I=-23:LRA=7:TP=-2` on every pass. The same chain ran against 10,270 historical Remux attempts -- compounding generational loss and audibly damaging sources at the AAC quality floor (≤96 kbps WEBRip/SDTV).

**Fix landed in `Features/AudioCompletion/`** -- a per-file `MediaFiles.AudioComplete` flag drives a one-shot pass model:
- One-shot normalization on first encode (when `AudioComplete=false`); post-flight flips the flag to true.
- `-c:a copy` on every subsequent encode (when `AudioComplete=true`).
- Files at or below the channel-aware bitrate floor (`QueueAdmissionConfig.MinAudioBitrateKbps{Mono,Stereo,Surround}` = 64/96/128) are marked complete during backfill so they never run through the loudnorm chain.
- Suspect-only-on-no-audio-stream model: DTS/TrueHD/FLAC/PCM/Vorbis/Opus take the one-shot codec-convert path (BuildAudioCodecArgs lands on EAC3), not the suspect bucket.

**Implementation evidence (verified 2026-05-17):**
- Backfill: 17,973 rows AudioComplete=true / 32,999 AudioComplete=false / 2,097 Suspect (no_audio_stream) / 5,726 unprobed -- idempotent re-run reports 0 row changes.
- Command-shape live verify on row 124 (30 Rock S06E19 Bluray-480p, MP4/HEVC/AAC 124 kbps stereo):
  - AudioComplete=true -> remux command emits `-c:a copy`, no `loudnorm`.
  - After Reset (AudioComplete=false) -> remux emits `loudnorm` + `acompressor`, no `-c:a copy`.
  - After MarkComplete (AudioComplete=true) -> back to `-c:a copy`, cascade returns IsCompliant=true, RecommendedMode=NULL.
- Cascade live verify on representative rows: Suspect -> IsCompliant=NULL; sub-floor stereo -> IsCompliant=true (Transcode short-circuited by floor guard); Opus 84 kbps -> Remux (one-shot codec convert path); MKV AAC AudioComplete=true -> Remux for container fix.
- `_LoadAudioNormalizedSet` removed -- compliance cascade reads `AudioComplete` column directly.

**Pending operator smoke test (workers required, currently paused):**
1. Start workers.
2. Re-queue file Id=124 (or any AudioComplete=true MP4 file) as Remux. Watch `TranscodeAttempts.FFpmpegCommand` -- must contain `-c:a copy` and must NOT contain `loudnorm`.
3. After successful Remux, compute `ffmpeg -i <source.orig> -map 0:a -c copy -f data - | sha256sum` and the same against the remuxed output. **Hashes must match** -- the criterion-26 byte-identical contract.
4. Re-queue any AudioComplete=false file as Remux. Watch the command contains `loudnorm`. Post-flight, query the row -- `AudioComplete` must be flipped to `true`, `AudioCompletedAt` set.

**Files:** `Features/AudioCompletion/`, `Models/CommandBuilder.py`, `Features/FileReplacement/FileReplacementBusinessService.py`, `Features/TranscodeQueue/QueueManagementBusinessService.py`, `Scripts/SQLScripts/{AddAudioCompletionColumns,AddAudioBitrateFloorConfig,BackfillAudioComplete}.py`. Once the operator smoke test passes, move this entry to `memory/KNOWN-ISSUES-ARCHIVE.md`.

---

### [BUG-0002] Media files with zero audio streams persist in DB after silent-output Remux -- must be purged with full FK history
**Date:** 2026-05-16

**What breaks:** Multiple `MediaFiles` rows have a non-NULL `AudioBitrateKbps` value but the actual on-disk file has zero audio streams. The Remux pipeline successfully ran, replaced the source, and updated the DB without catching that the output was silent. The post-replacement re-probe in `_UpdateMediaFilesAfterReplacement` failed to clear or flag the missing audio — instead the pre-Remux `AudioBitrateKbps` was kept and `AudioCodec` ended up NULL. So the DB now contains "ghost audio" rows pointing at silent files.

**Confirmed silent on disk via ffprobe** (sample of 4 of the 16 NULL-codec candidates):
- `T:\Doctor Who (2005)\Specials\Doctor Who (2005) - S00E72 - Doctor Who in America SDTV-720p-mv.mp4`
- `T:\Monk\Season 7\Monk - S07E08-E09 - Mr. Monk Gets Hypnotized + Mr. Monk and the Miracle WEBDL-480p-mv.mp4`
- `T:\Shameless\Season 1\Shameless - S01E06 - Monica Comes Home (1) SDTV-720p-mv.mp4`
- `T:\Xena - Warrior Princess\Season 1\Xena - Warrior Princess - S01E05 - The Path Not Taken DVD-720p-mv.mp4`

Each has a video stream (HEVC) but no audio stream at all. The 16-file NULL-codec set is a lower bound — files where the pre-probe captured a codec name will not be caught by `AudioCodec IS NULL` alone, so the actual silent population is likely larger. Definitive identification requires `ffprobe` against every transcoded file.

**Why the DB can't be trusted as the source of truth:** `AudioBitrateKbps` was kept from the pre-Remux source instead of being NULL'd. `AudioCodec` ended up NULL only by accident on a subset of files. Any silent file whose re-probe happened to keep both fields populated is undetectable from the DB. Conclusion: the re-probe in `_UpdateMediaFilesAfterReplacement` must overwrite every audio column based strictly on what the post-replacement file actually contains — present audio populates them, absent audio NULLs them and triggers Discard. No partial updates, no defaulting to source values.

**What the user wants:** purge these rows from the DB entirely (along with the on-disk silent file) and record every removed path so they can be re-acquired from source.

**Cleanup behavior (per criterion 19 on `post-transcode-pipeline.feature.md`):**
1. ffprobe every `MediaFiles` row (or every `TranscodedByMediaVortex = true` row as a faster first pass) to identify rows whose file has zero audio streams.
2. For each silent file: delete the row and every dependent record in `TranscodeAttempts`, `TranscodeFiles`, `MediaFilesArchive`, `QualityTestResults`, `QualityTestProgress`, `TranscodeQueue`, `QualityTestingQueue`, `ActiveJobs`, `TemporaryFilePaths`, `ScanJobs` (if linked), `ProblemFiles` (if linked). One transaction per file.
3. Before the row is deleted, append its `RelativePath` (fallback `FilePath`) to a timestamped report at the repo root: `deleted-silent-files-YYYY-MM-DD.md`, grouped by show, so the operator can re-acquire.
4. Delete the silent file from disk.
5. Going forward, harden `_UpdateMediaFilesAfterReplacement` to fail loud when the re-probe finds no audio — `Discard` disposition, on-disk silent output removed, source restored if `.orig`/`.inprogress` is still recoverable.

**Violates:** `Features/FileReplacement/post-transcode-pipeline.feature.md` criterion 19 (added with this bug). Indirectly: the missing MediaProbe feature doc (no `Features/MediaProbe/*.feature.md` exists) means the re-probe contract has no owner — flag the gap, /t should create one when fixing.

**Related (not duplicate):** `### [BUG] Next Remux Batch table shows files with no audio stream that silently fail when queued` (2026-05-14, line 200) covers the *upstream* problem of queueing video-only files that error out with code 4294967274. BUG-0002 is the *downstream* problem of files that successfully completed Remux but came out silent and now sit in the DB with stale audio metadata. Different failure mode (success-with-no-audio vs explicit failure), different cleanup need (purge + report vs exclude from queue).

**Look first:**
- `Features/FileReplacement/FileReplacementBusinessService.py` — `_UpdateMediaFilesAfterReplacement` (no-audio detection gap, criterion 19 second half).
- `Features/MediaProbe/MediaProbeBusinessService.py` — the probe call that ought to surface zero-audio explicitly.
- DB foreign-key map: `TranscodeAttempts.MediaFileId`, `TranscodeFiles.MediaFileId`, `MediaFilesArchive.Id` (shared PK), `QualityTestResults.TranscodeAttemptId`, `QualityTestProgress.TranscodeAttemptId`, `TemporaryFilePaths.TranscodeAttemptId`, `ActiveJobs.QueueId` (polymorphic — see BUG-0001 criterion 16).
- Sample file paths above for `ffprobe` verification before/after.

**Fix with:** `/t BUG-0002`.

---

---

### [BUG] TranscodeAttempts failure rows lack ProfileName -- operator cannot tell what KIND of job failed from the row alone
**Date:** 2026-05-16

**What breaks:** When a remux or transcode job fails early (pre-flight, pre-FFmpeg), the resulting `TranscodeAttempts` row has `Success=False` and `ErrorMessage` populated (loud failure IS in the DB), but `ProfileName=NULL`. The queue row was DELETEd by the failure handler so its `ProcessingMode` context is gone. Operator looking at the row can see "this attempt failed with this error" but not "this was a Remux job" vs "this was an SVT-AV1 transcode." They must join `MediaFiles` via `MediaFileId` to recover even partial context.

Confirmed against attempts 16240-16243 on 2026-05-16: 4 remux jobs failed with `"No active StorageRootResolutions row for (StorageRootId=None, WorkerName='...')"`. All 4 rows have `ProfileName=NULL`. The triggering test-setup script inserted queue rows without `StorageRootId`/`RelativePath` (script bug, not production bug), but the observability gap is real for ANY early failure in production too.

**Note on FilePath=NULL:** That is BY DESIGN per the existing entry "FilePath used as denormalized natural key across 6+ tables" -- FilePath was removed from TranscodeAttempts INSERTs as part of the denormalization cleanup. Operators join via MediaFileId for path. ProfileName is NOT in that denormalization scope; it should be populated.

**Violates:** `Features/TranscodeJob/TranscodeJob.feature.md` criterion 30 (added with this entry). Adjacent to criterion 29 (ErrorMessage content) -- this entry owns the ProfileName slice of the same "diagnose from attempts table alone" contract.

**What "fixed" looks like:** Every `TranscodeAttempts` INSERT in the failure path sets `ProfileName` -- from the queue row's `ProcessingMode='Remux'` literal for remux jobs, from the resolved transcode profile name for transcode jobs -- regardless of how early in the pipeline the failure occurs. Verifiable: trigger a remux job that fails at the `Resolve()` call (e.g. insert a queue row with `StorageRootId=NULL`); query the resulting `TranscodeAttempts` row; observe `ProfileName='Remux'`.

**Look first:** `Features/TranscodeJob/ProcessTranscodeQueueService.py` and `Features/TranscodeJob/ProcessRemuxQueueService.py` -- the failure path in `_ProcessJob` (or equivalent) that creates the TranscodeAttempt row when an exception is caught early. The fix is to populate `ProfileName` from the queue context BEFORE the work begins, not after.

---

### [BUG] FindFuzzyFileMatch is O(N x M) -- reloads + regex-parses all RootFolder rows per new file
**Date:** 2026-05-15

**What breaks:** Every NEW file the scanner discovers triggers `FindFuzzyFileMatch`, which:
1. Calls `Repository.GetMediaFilesByRootFolderId(RootFolderId)` -- returns ALL MediaFiles rows for that RootFolder (for T:\, that is ~45,000 rows; multi-MB transfer through psycopg2).
2. Calls `ExtractShowInfo` (regex parse) on every loaded row's `FileName`.
3. For any candidate that passes the IsFuzzyMatch shape check, stats the candidate path over NFS.

The 5-thread parallel pool in `ProcessMediaFiles` means every new-file slot does this independently and concurrently -- the same 45k rows get loaded 5 times in parallel.

Confirmed against I9-2024 scan #64925 on 2026-05-15: ~22 new Graham Norton episodes were taking 3-5 seconds each. That is 22 x (45k DB load + 45k regex parses) = 990,000 ops where 22 dict lookups would suffice. For larger libraries the per-file cost grows linearly with library size -- O(N x M) where N is new files and M is RootFolder size.

Same anti-pattern family as criterion 23 (per-file work that should be precomputed once per scan) but a distinct code path: `FindMovedFile` (covered by 23) vs `FindFuzzyFileMatch` (this entry).

**Violates:** `Features/FileScanning/FileScanning.feature.md` criterion 25 (added with this entry).

**What "fixed" looks like:**
- In `PerformScan`, after `GetOrCreateRootFolder` succeeds, do a single `GetMediaFilesByRootFolderId(RootFolder.Id)` call.
- Build a `{(ShowName, Season, Episode): [DbFile, ...]}` index from that result. Skip rows where `ExtractShowInfo` returns empty parts -- they cannot be fuzzy-matched anyway.
- Pass the index through `ProcessMediaFiles -> ProcessSingleMediaFile -> FindFuzzyFileMatch` (or hold it on `self` for the duration of a single `PerformScan`).
- `FindFuzzyFileMatch` looks up `Index[(ShowName, Season, Episode)]` -- O(1) -- and runs the existing `IsFuzzyMatch` size check + `os.path.exists` candidate validation on the small candidate list.
- Index is read-only after build, safe for the parallel pool (same threading model as the filename index in `ReconcileWithDisk`).
- Verifiable: trigger a scan that introduces N new files; observe per-new-file wall-clock under 100ms instead of 3-5 seconds.

**Look first:** `Features/FileScanning/FileScanningBusinessService.py` -- `FindFuzzyFileMatch` (~line 685), called from `ProcessSingleMediaFile` new-file branch (~line 785). `PerformScan` (~line 313) is where the index should be built. The `ReconcileWithDisk` filename-index pattern (the criterion 23 fix in the same file) is the template.

---

### [BUG] ScanJobs NewFiles / UpdatedFiles / DeletedFiles counters stay at zero
**Date:** 2026-05-15

**What breaks:** A scan in progress writes `ScanJobs.NewFiles=0, UpdatedFiles=0, DeletedFiles=0` even when MediaFiles rows are being inserted, updated, or deleted. Confirmed mid-scan on 2026-05-15 against I9-2024 scan #64925: the heartbeat showed all three counters stuck at 0 while `SELECT * FROM MediaFiles WHERE LastScannedDate > NOW() - INTERVAL '3 minutes'` returned freshly-inserted rows (IDs 622023-622032 against `T:\The Graham Norton Show\Season 20`). The total-files counter (`ProcessedFiles`) climbs correctly thanks to the criterion 17 heartbeat fix, but the per-disposition breakdown the operator needs to answer "what changed?" is not produced.

**Root cause:** `FileScanResultModel` defines only `TotalFilesFound / TotalFilesProcessed / TotalFilesSkipped / TotalFilesWithErrors`. No fields exist for new / updated / deleted. `ProcessSingleMediaFile` increments `TotalFilesProcessed` uniformly for inserts and updates. `ReconcileWithDisk` (the new code that owns deletes per criterion 23) does not surface its delete count to ScanResults. `UpdateJobStatus` only writes the New/Updated/Deleted columns when a ScanResults model is passed, and even then the model has nothing meaningful in those slots.

**Violates:** `Features/FileScanning/FileScanning.feature.md` criterion 24 (added with this entry). Criterion 17 already names these columns in its contract; criterion 24 owns the per-disposition slice of that contract while criterion 17 owns the heartbeat-cadence dimension.

**What "fixed" looks like:**
- Add `NewFilesCount`, `UpdatedFilesCount`, `DeletedFilesCount` (or matching field names) to `FileScanResultModel`.
- `ProcessSingleMediaFile` insert branch increments `NewFilesCount`; update branch increments `UpdatedFilesCount`. Both protected by the existing `ProgressLock`.
- `ReconcileWithDisk` increments `DeletedFilesCount` per delete and `UpdatedFilesCount` per fuzzy-match reassignment.
- `UpdateJobStatus` writes the three new fields when ScanResults is passed.
- The heartbeat thread (criterion 17 fix) already passes ScanResults -- once the model has the fields, the heartbeat will surface them automatically with no further plumbing.
- Verifiable: trigger a scan that creates N new files, updates M files, deletes K files; observe `SELECT NewFiles, UpdatedFiles, DeletedFiles FROM ScanJobs WHERE Id=<scan>` returns (N, M, K) matching reality.

**Look first:** `Features/FileScanning/Models/FileScanResultModel.py` -- add fields. `Features/FileScanning/FileScanningBusinessService.py` -- `ProcessSingleMediaFile` (insert branch ~line 815, update branch ~line 773), `ReconcileWithDisk` (delete branch and fuzzy-match branch). The thread-safe lock pattern at `ProcessMediaFilesWithMetadata` line ~1503 is the template.

---

### [BUG] Scan triple-stats DB rows over NFS and runs the existence checks single-threaded
**Date:** 2026-05-15

**What breaks:** A continuous-scan iteration on a Windows or Linux worker does the following for every RootFolder:

1. `FileManagerService.ScanDirectory` walks the filesystem (`os.walk`) -- fast (T:\ over NFS: 45,716 files in 10 seconds).
2. `FileScanningBusinessService.DetectMovedFiles` iterates every `MediaFiles` row whose path is under this RootFolder and calls `os.path.exists(_ToLocalPath(DbFile.FilePath))` **serially, single-threaded**. For T:\ with 47,970 rows at ~25ms per NFS stat, this is ~20 minutes of wall-clock blocking before the parallel processor even starts.
3. `CleanupMissingFiles` then runs and does **the same 47,970 `os.path.exists` calls again** -- already called out by criterion 12, still present.
4. For files declared missing in step 2, `FindMovedFile` calls `os.walk` over **every one of 587 RootFolders** looking for a filename match -- exponential cost: O(missing_files x rootfolders x dir_count).
5. `ProcessMediaFiles` (5-thread parallel) then stats each file a **third time** via `FileManager.GetFileSizeMB` / `os.path.getsize` / `os.path.exists` plus a DB lookup, mostly to discover the row hasn't changed.

Worker process memory is fine (~279 MB). The bottleneck is wall-clock from sequential NFS round-trips. Observed T:\ scan #64923 on I9-2024 2026-05-15: 20+ minutes blocked in `DetectMovedFiles` with the heartbeat thread (criterion 17 fix) confirming the process is alive but the scan thread is stat-bound.

**Violates:** `Features/FileScanning/FileScanning.feature.md` criterion 23 (added with this entry). Complements criterion 12 (which owns the cap behavior); this entry owns the throughput dimension of the same `DetectMovedFiles` / `CleanupMissingFiles` / `FindMovedFile` code path.

**What "fixed" looks like:**
- Existence-check work is parallelized with the same `ThreadPoolExecutor(max_workers=5)` pattern `ProcessMediaFiles` already uses, or merged into a single `os.scandir`-driven pass that builds a `{path: stat_result}` dict for the whole RootFolder once and reuses it.
- `DetectMovedFiles` and `CleanupMissingFiles` collapse into one per-row decision so each file is stat'd at most once per scan.
- `FindMovedFile` builds a single `{filename: [paths]}` index from the `os.walk` results once per scan and looks up missing files in O(1) instead of `os.walk`-per-missing-file.
- Verifiable: re-run T:\ scan on a worker against a database whose rows match disk; observe wall-clock under 5 minutes for a no-change pass on ~50k rows.

**Look first:** `Features/FileScanning/FileScanningBusinessService.py` -- `DetectMovedFiles` (~line 1363), `CleanupMissingFiles` (call site immediately after), `FindMovedFile` (~line 1297), and the inner `os.walk` in `FindMovedFile` (~line 1318). The `ProcessMediaFiles` `ThreadPoolExecutor` pattern (~line 1486) is the template to copy. `Services/FileManagerService.py` `ScanDirectory` already produces the `os.walk` result that could feed a `{filename: [paths]}` index.

---

### [BUG] Scan progress writer is silent -- ScanJobs counters and CurrentDirectory don't advance mid-walk
**Date:** 2026-05-15

**What breaks:** A scan triggered via `ContinuousScanService` (or manual `POST /api/FileScanning/Scan/Start`) walks the filesystem but does not update `ScanJobs.ProcessedFiles`, `CurrentDirectory`, or `LastUpdated` until the scan ends. Confirmed against I9-2024 on 2026-05-15: M:\ scan #64919 ran 75s and T:\ scan #64920 ran 4+ minutes, both over NFS (89ms/dir for M:\, 18ms/dir for T:\), and both reported `ProcessedFiles=0`, `CurrentDirectory=NULL`, `LastUpdated=StartTime` for the entire run. From the operator's view, a healthy running scan and a hung scan look identical -- the only safety net is `StuckJobDetectionService` at the 15-minute threshold, which is well past the point where a real hang is impacting throughput.

**Violates:** `Features/FileScanning/FileScanning.feature.md` criterion 17 (promoted to [BUG] with this entry). The criterion text now covers two dimensions: cadence (this entry) AND phase visibility. The phase dimension was added on the same date after observing scan #64925's walk finish (`ProcessedFiles=45716`) while `Status` stayed `Running` for the entire metadata-extraction phase that followed -- `PerformScan` folds `ProbeFilesNeedingMetadata` inside its return, so the operator cannot tell "still walking files" from "files done, now FFprobing." Fix candidates: add a `ScanJobs.Phase` column, or split probe out of PerformScan so Status flips to Completed when the walk finishes and a separate row tracks probe.

**What "fixed" looks like:** During an active scan, `ScanJobs.LastUpdated` advances at least every 5 seconds even if no files changed; `CurrentDirectory` reflects the directory currently being walked; `ProcessedFiles` increments per file visited (not just per file inserted/updated). Verifiable: poll `SELECT LastUpdated, CurrentDirectory, ProcessedFiles FROM ScanJobs WHERE Id=<running-id>` every 5s and observe values advance well before `EndTime` is set.

**Look first:** `Features/FileScanning/FileScanningBusinessService.py` -- the scan-walk implementation called from `ContinuousScanService._ExecuteScan` via `StartScanning`. Find where `ProcessedFiles` increments live and confirm whether the path is taken when files are skipped vs only when files are inserted/updated. Likely fix: lift the increment to the `os.walk` yield (not the per-file work branches), and add a heartbeat write of `LastUpdated` + `CurrentDirectory` every N seconds independent of file count.

---

### [BUG] Worker status model is overcomplicated -- Draining state is broken, invisible, and unnecessary
**Date:** 2026-05-14

**What breaks:** Three related problems in the worker status/capability system:

**(1) Draining doesn't stop remux.** `_HandleStatusChange("Draining")` sets `StopRequested` on TranscodeService, stops QualityTestService, and stops ContinuousScanService -- but has no awareness of RemuxService (added later). Remux jobs keep being claimed during the entire drain window. The drain-to-Paused auto-transition eventually triggers `_StopAllCapabilities` which does know about remux, but that's a two-poll-cycle delay (~120s) during which the worker grabs new work it shouldn't.

**(2) Draining is invisible to the operator.** The Activity page UI only exposes Online and Pause buttons. `Draining` is an internal-only transient state with its own code path (`_DrainAndStop`, drain waiter thread), but the operator cannot set it from the UI and has no reason to know it exists. The operator's intent is "stop gracefully" -- that should be what Pause does.

**(3) Capability polling has unjustified constraints.** The `_ApplyConcurrencyChanges` loop still clamps concurrency to 1-5 (already removed from API validation and TeamStatus controller, but survives in the polling loop). The actual polling interval is 60s despite criterion 2 documenting "within one polling interval (default 15s)" and `SystemSettings.CapabilityPollingIntervalSec` supposedly controlling it. The 60s delay means any status or concurrency change takes up to a minute to take effect.

**Root cause:** Draining was designed before RemuxService existed and was never updated. The three-state model (Online/Draining/Paused) adds complexity for no operator benefit -- Paused should have always meant "finish in-flight, don't claim new."

**Design direction (discuss before implementing):**
- Two states only: **Online** (accepting work) and **Paused** (finish in-flight, stop claiming)
- Paused = set `StopRequested` on every capability via `_StopAllCapabilities`, let processing loops wind down naturally
- Remove `_DrainAndStop`, remove the `Draining` branch from `_HandleStatusChange`, remove the drain waiter thread
- Remove the 1-5 concurrency clamp (floor of 1, no ceiling)
- Align polling interval to the documented 15s default, verify `SystemSettings.CapabilityPollingIntervalSec` is actually wired

**Violates:** `WorkerService/WorkerService.feature.md` criteria 3, 20, 21.

**Feature doc:** `WorkerService/worker-lifecycle.feature.md` -- full design decisions and success criteria for the fix.

**Look first:** `WorkerService/Main.py` -- `_HandleStatusChange` (line ~741), `_DrainAndStop` (line ~766), `_StopAllCapabilities` (line ~783), `_ApplyConcurrencyChanges` (search for 1-5 clamp), `_CapabilityPollingLoop` (interval). `Features/FileReplacement/FileReplacementBusinessService.py` -- `PrepareReplacement` (the `.orig` rename to replace with `.inprogress` pattern). `WorkerService/WorkerService.flow.md` -- "Per-Worker Status Control" section (update to two states). `Templates/Activity.html` -- tile layout and per-machine pause.

**Fix with:** `/t`

---

### [BUG] Per-capability concurrency is not data-driven -- requires worker restart to take effect
**Date:** 2026-05-13

**What breaks:** Changing `MaxConcurrentTranscodeJobs`, `MaxConcurrentQualityTestJobs`, or `MaxConcurrentRemuxJobs` in the Workers table does not take effect until the worker process is restarted. The concurrency value is read once during `_StartXxxCapability()` and passed to `Run(MaxConcurrentJobs=N)`. The capability polling loop (60s) checks enabled/disabled flags but never re-reads the concurrency columns. This violates the "data-driven" contract: if the max is raised from 1 to 2, the worker should spin up an additional thread on its next poll without restart.

**Violates:** `WorkerService/WorkerService.feature.md` criterion 18 (added with this entry).

**Look first:** `WorkerService/Main.py` `_CapabilityPollingLoop` and `_GetPerCapabilityConcurrency()`. The queue service `Run()` method needs to support dynamic thread-pool resizing, or the capability must be stopped and restarted with the new concurrency value.

---

### [BUG] Status page "Possibly Corrupt" count has no drill-down to see which files are affected
**Date:** 2026-05-13

**What breaks:** The `/Status` page shows "Possibly Corrupt: N" (files with `FFProbeFailureCount >= 3`) as a static number with no click-through. The operator sees there ARE corrupt files but cannot see WHICH ones without navigating to `/Scanning` and opening the Corrupt Files modal. The API endpoint (`GET /api/FileScanning/MediaFiles/Corrupt`) and the detail modal (`Templates/FileScanning.html#CorruptFilesModal`) already exist -- the Status page just doesn't use them.

**Violates:** `Features/FileScanning/FileScanning.feature.md` criterion 19 (added with this entry).

**Look first:** `Templates/Status.html` line 55-61 (the `#LibCorrupt` card -- make it clickable). Reuse the existing `/api/FileScanning/MediaFiles/Corrupt` endpoint. Either inline a modal on the Status page or link to `/Scanning?openCorrupt=true` with auto-open logic.

**Fix with:** `/t`.

---

### [BUG] Next Remux Batch table shows files with no audio stream that silently fail when queued
**Date:** 2026-05-14

**What breaks:** The "Next Remux Batch" card on the ShowSettings page calls `/api/ShowSettings/SmartPopulate` with `Mode='Remux'`. The SmartPopulate query filters by `HasExplicitEnglishAudio IS NULL OR HasExplicitEnglishAudio = true`, but files that have never been probed with audio-aware code have `HasExplicitEnglishAudio = NULL` -- which passes the filter. These video-only files (e.g. Survivor S43E01, S45E02) get displayed as candidates, queued by the user, then fail with "Transcoding failed with return code 4294967274" because the remux command maps `0:a:0` which doesn't exist.

**Violates:** SmartPopulate should exclude files that are known to have zero audio streams (possibly corrupt). No feature doc exists yet for this card's population logic end-to-end.

**Look first:** `Features/TranscodeQueue/QueueManagementBusinessService.py` `SmartPopulateQueue()` WHERE clause; `Features/ShowSettings/remux-populate-card.feature.md`; the `RecommendedMode` materialization in `_EvaluateCompliance()`.

**Fix with:** `/t`.

---

### [BUG] Stale .orig files from remux re-queue loop -- 205 files affected, 14 at risk of data loss
**Date:** 2026-05-14

**Root cause:** `RecomputeForFiles` was never called from `FileReplacementBusinessService._ProcessCompleteFileReplacement`. After a successful remux, `RecommendedMode` stayed `'Remux'` and `IsCompliant` stayed `False` because the cached compliance columns were never refreshed. Queue population re-queued these already-remuxed MP4 files. Each re-queue cycle called `PrepareReplacement` (renaming `.mp4` to `.mp4.orig`), ran FFmpeg to write a new `.mp4`, and may or may not have completed. The `.orig` from the first re-queue was never cleaned up, so every subsequent attempt hit the safety guard: "Pre-existing .orig backup -- refusing to overwrite."

**What breaks:**

1. **593 wasted TranscodeAttempts** across all workers from `.orig` collision errors alone.
2. **11,068 MP4 files** still have stale `RecommendedMode = 'Remux'` in MediaFiles. Any future queue populate will re-queue them all again.
3. **137 files** have both the `.mp4` and `.mp4.orig` on disk. Of these, **123 had a prior successful remux** -- the `.mp4` is the good file and the `.orig` is safe to delete. **14 never had a successful remux** -- the first attempt's FFmpeg died mid-write, so the `.mp4` at the DB path is partial/corrupt and the `.orig` is the only intact copy.
4. **61 files** have only the `.mp4` on disk (`.orig` already cleaned up or never created). These just need `RecomputeForFiles`.
5. **7 files** have neither the `.mp4` nor `.orig` on disk -- DB points to a missing file.
6. Every file with a stale `.orig` blocks the worker indefinitely on that queue item (claims it, fails instantly, releases, re-claims on next cycle).

**Damage assessment by category:**

| Category | Count | Risk | Recovery action |
|----------|-------|------|-----------------|
| Both exist, had successful remux | 123 | Low -- `.mp4` is valid | Delete `.orig`, run `RecomputeForFiles` |
| Both exist, NEVER succeeded | 14 | **DATA LOSS** -- `.mp4` is partial | Restore `.orig` to original path, delete corrupt `.mp4`, run `RecomputeForFiles` |
| MP4 only, no `.orig` | 61 | None -- already clean | Run `RecomputeForFiles` only |
| Neither file exists | 7 | Orphan DB row | Flag for manual investigation |

**Fix (code -- already applied, not yet committed):** Wired `RecomputeForFiles([MediaFileId])` into `_ProcessCompleteFileReplacement` after the DB update succeeds. Verified: 4 files remuxed after the fix show `RecommendedMode = None`, `IsCompliant = True`. Fix prevents future re-queue loops.

**Recovery (data -- requires cleanup script):**
1. Pause all workers to stop churn.
2. For the 14 never-succeeded files: rename `.orig` back to its pre-remux path, delete the corrupt `.mp4`.
3. For the 123 safe files: delete the `.orig`.
4. Run `RecomputeForFiles` on all 11,068 stale MP4 files to clear `RecommendedMode = 'Remux'`.
5. Delete all remux queue items whose MediaFile is already MP4 and compliant after recompute.
6. Investigate the 7 neither-exists files separately.
7. Unpause workers.

**Design decision (2026-05-14): stop renaming originals.** The `.orig` rename pattern is fundamentally wrong -- it mutates the source file before the new output is confirmed good. Every crash/kill during the transcode window leaves the original in an unrecoverable state. The correct approach: write the FFmpeg output to `<filename>.inprogress` (or similar suffix) at the destination. The original file is never touched. On success, delete the original and rename `.inprogress` to the final name. On failure or crash, the `.inprogress` file is just garbage to clean up -- the original is intact. Crash recovery becomes trivial: find and delete `.inprogress` files. This eliminates the entire class of `.orig` data loss bugs.

**Look first:** `Scripts/OrigDamageAssessment.py` (assessment script already written), `Features/FileReplacement/FileReplacementBusinessService.py` (the code fix + the PrepareReplacement method that does the dangerous `.orig` rename), `Features/TranscodeQueue/QueueManagementBusinessService.py` (`RecomputeForFiles`).

---

### [BUG] Linux worker deploy flow doc incomplete -- no post-deploy verification, FFmpeg path troubleshooting, or automation parity with Windows
**Date:** 2026-05-13

**What breaks:** `deploy/worker-deploy.flow.md` ends at `docker compose up -d` with only an optional SVT-AV1 encoder check and a Workers table query. Does not document: post-deploy health checks confirming FFmpeg/FFprobe paths resolve inside the container, the full container-started-to-operational sequence, troubleshooting when FFmpeg path resolution fails, or what additional operator actions differ between first deploy vs code-only redeploy. An operator following this doc alone would not know how to diagnose "worker registered but can't find FFmpeg" without reading source code. The Windows deploy path (`deploy/windows-worker.flow.md` + `deploy-windows-worker.py`) has full post-deploy verification and single-command automation; Linux has neither.

**Violates:** `deploy/worker-deploy.feature.md` criterion 20 (added with this entry).

**Look first:** `deploy/worker-deploy.flow.md` -- compare post-deploy coverage to `deploy/windows-worker.flow.md`. The Runtime Pipeline table documents what happens inside the container (steps 8-17) but that knowledge is not surfaced as operator-actionable verification steps. Also consider whether a `deploy-linux-worker.py` (or shell script) should exist to match the Windows automation.

**Fix with:** `/t`.

---

### [BUG] Terminology inconsistency: "quality test" (what) and "VMAF" (how) used interchangeably
**Date:** 2026-05-12

**What breaks:** Code, DB columns, settings keys, log messages, and UI labels mix the policy term ("quality test" -- the decision to accept/requeue/discard a transcode) with the specific implementation term ("VMAF" -- one numeric metric). Examples: `QualityTestEnabled` (policy flag) coexists with `VMAFAutoReplaceMinThreshold` (metric-specific); `QualityTestProgress` table updated by `MonitorVMAFProgress` function; `QualityTestingBusinessService.BuildVMAFCommand`. The mixing bakes the current metric choice into surfaces that should be metric-agnostic and makes a future SSIMU2/PSNR/visual-comparison alternative awkward to add.

**Violates:** `Features/QualityTesting/QualityTesting.feature.md` criterion 11b (added with this entry).

**Look first:** `Features/QualityTesting/QualityTestingBusinessService.py` (mixed naming across method names); `Repositories/DatabaseManager.py` (column names, e.g. `QualityTestRequired` vs `VMAF`); `Templates/*.html` (operator-facing labels); `Core/Logging` strings. Fix needs a documented glossary first, then a careful rename pass; expect schema migrations for any DB columns renamed.

**Fix with:** `/t`.

---

### [BUG - PARTIAL FIX 2026-05-16] VMAF distribution becomes bimodal on held-frame content -- mean/HMean/P5 unreliable until motion-filter applied
**Date:** 2026-05-10 | **Investigated + partial fix:** 2026-05-16

**Re-classified 2026-05-16:** the original framing pinned this on MKV containers, but a controlled experiment ruled the container out. The real cause is libvmaf mis-scoring held-frame animation (animation-on-2s/3s). The fix is motion-filtered pooling, not a filter-chain change.

**Investigation summary (2026-05-16):** ran the smoke reproducer with the existing Minnie's Bow-Toons variants and five candidate fixes against the same encoded MP4s (no re-encoding -- isolates the VMAF measurement). Results in `Scripts/Smoke/VmafFilterExperiment.py`:

| Recipe | Mean | StdDev | P5 | Verdict |
|---|---|---|---|---|
| baseline (current production filter) | 74.60 | 32.58 | 0.00 | reproduces bug |
| bit10 (compare both at 10-bit, no downcast) | 74.66 | 32.60 | 0.00 | no effect |
| setparams (force range=tv:colorspace=bt709 metadata on both) | 74.60 | 32.58 | 0.00 | no effect |
| scale_range (active in_range=auto:out_range=tv conversion) | 74.60 | 32.58 | 0.00 | no effect |
| baseline against remuxed MP4 source (no re-encode) | 74.60 | 32.58 | 0.00 | **container ruled out** |
| neg_model (vmaf_v0.6.1neg) | 72.79 | 32.81 | 0.00 | marginal regression |
| mpdecimate (drop duplicate frames symmetrically before VMAF) | 73.47 | 33.01 | 0.00 | no effect (only dropped 209/4321 frames; libvmaf's motion is stricter than mpdecimate's "is duplicate" detection) |

Every filter-chain mitigation produced byte-identical or near-identical results. ffprobe confirmed Minnie's source MKV and encoded MP4 have IDENTICAL color metadata (`color_range=tv`, `color_space=bt709`, `color_transfer=bt709`, `color_primaries=bt709`); only pix_fmt differs (8-bit source, 10-bit encoded). The bug doc's color-metadata-mismatch hypothesis applies to Black Butler's `color_range=unknown` case but is NOT the cause on Minnie's, yet Minnie's bimodal'd just as hard.

**Actual cause:** libvmaf's `integer_motion` elementary feature is the temporal absolute difference between consecutive reference frames. Cross-tabulating motion vs VMAF on Minnie's: 41.3% of source frames have motion=0 (1783 of 4321), and 281 of those score VMAF<10. VMAF model 0.6.1 was trained on continuous-motion live-action and produces wildly wrong scores on motion=0 frames even when the encoded picture is visually identical to the source. PNG stills extracted at the VMAF=0 frames confirm: encoder is fine, libvmaf is mis-measuring.

**The trigger is byte-identical consecutive frames, not "animation."** Production-DB cross-check 2026-05-16 against shows with VMAF data:

| Show | Type | Mean | P5 | StdDev |
|---|---|---|---|---|
| Pokémon S20E10 | Hand-drawn anime | 71.5 | 0.0 | 35.1 |
| Real Housewives S03E22 | Reality TV | 76.6 | 9.2 | 29.8 |
| Steven Universe S05E14 | 2D Western animation | 76.8 | 18.9 | 22.7 |
| Bunk'd S02E11 | Disney sitcom | 78.3 | 22.7 | 24.7 |
| The Bear S03E10 | Live-action drama | 79.4 | 10.8 | 27.8 |
| **Garfield Show S01E19** | **Modern CGI** | **97.7** | **95.7** | **1.5** |
| Outlander | Live action | 96.7 | -- | 2.0 |

Counter-intuitively, modern CGI is NOT a reliable predictor of the bug -- Garfield's render pipeline likely uses per-frame motion blur or sub-pixel dither that breaks byte-identity. The shows that DO bimodal are the ones with truly identical held frames: hand-drawn anime animated-on-2s, 2D Western animation with the same technique, reality TV with photo montages and title cards, sitcoms shot multicam on static stages, and dramas with title-card / chapter-card interludes. The Office S00E05 from the original report fits this pattern (S00 specials/extras with lots of static title content).

A secondary contributor: even among motion>0 frames, ~114 frames score VMAF<10 due to low VIF/ADM values on low-spatial-information regions (flat color areas common in animation). VMAF's features fall outside their training distribution on stylized content. This residual can't be cleanly filtered without false positives, so even after motion filtering the metric remains less reliable on animation than on live action.

**Fix shipped (partial):** `Features/QualityTesting/QualityTestingBusinessService.py::ParseVMAFMetrics` now parses `integer_motion` per frame in addition to the VMAF score. When more than 15% of source frames have motion<0.5 (held-frame animation detected), Mean/StdDev/HarmonicMean/percentiles are pooled over only the motion>=0.5 frames -- the duplicate frames are excluded from the metric. Live action sits at <2% motion=0 so the filter is a no-op. Two new fields surface for observability: `MotionZeroFraction` and `MotionFilterApplied`. Smoke harness `Scripts/Smoke/EncodeAndVmaf.py::ParseMetricsFromXml` mirrors the same logic so harness reports stay consistent with production.

Minnie's metrics with the fix:

| Metric | Raw (broken) | Motion-filtered | Clean 4K MP4 reference |
|---|---|---|---|
| Mean | 74.60 | **84.43** | 95.77 |
| HarmonicMean | 11.20 | **24.64** | 95.75 |
| StdDev | 32.58 | **26.75** | 1.18 |
| P5 | 0.00 | **12.08** | 94.30 |
| P25 | 54.12 | **94.39** | -- |

**Residual limitation:** filtered Mean=84 is still below `VmafAutoReplaceMinThreshold=88` even though the encode is visually clean -- so the auto-replace gate will still Requeue this attempt today. P25 of 94 over the filtered pool tells the real story (75% of unique frames score 94+), but the gate doesn't look at P25. Possible follow-ups (not in this fix): (a) lower the threshold when `MotionFilterApplied=True`, (b) gate on filtered P25 instead of filtered Mean for animation, (c) skip the VMAF gate entirely for animation and rely on visual slider review. These are operator-policy decisions, separate from the measurement fix.

**Violates:** `Features/QualityTesting/QualityTesting.feature.md` criterion 2b (re-scoped 2026-05-16 to reflect the actual cause).

**Investigation artifacts:** `Scripts/Smoke/VmafFilterExperiment.py` (committed -- per-recipe harness for re-running the experiment matrix) and `Scripts/Smoke/MinnieBowToons-S04E07-Animation8Mbps.results.json` (committed -- known-bimodal reference, baseline numbers in the file). The remuxed-source MP4 and per-frame PNG extracts are gitignored (regeneratable: `ffmpeg -i <mkv> -map 0:v:0 -map 0:a:0? -c copy <mp4>` to remux; `ffmpeg -i <file> -vf "select=eq(n\,61)" -vframes 1 <png>` to extract frame 61).

---

### [BUG] `MonitorVMAFProgress` stops emitting updates ~25% before FFmpeg exits
**Date:** 2026-05-10

**What breaks:** On attempt 4396 (Steven Universe S05E14, 16,080 frames), the progress log went silent at frame 12,000 (74.6%) and then `Process completed return code: 0` appeared ~25 seconds later. No exception was thrown; no error in the Logs table for that window. Same monitor failure leaves `QualityTestProgress.Status` stuck at `'Processing'` (or `'Started'` with pre-`RETURNING Id` worker code) and `ProgressPercentage` stuck wherever the last successful poll landed -- so the Activity UI shows a phantom "running" row forever even though the VMAF actually finished.

**Data integrity NOT affected:** the FFmpeg process itself completes normally. `vmaf_output.xml` is well-formed (verified: 1,609 frame elements covering frames 0-16080), `QualityTestResults.VMAFScore` is parsed correctly from the XML, and the disposition function reads the right value. The bug is purely on the operator-visibility side.

**Isolated to the Python wrapper (2026-05-10):** ran the EXACT same FFmpeg command directly in a terminal (no `MonitorVMAFProgress` wrapping). FFmpeg emitted clean progress lines every ~100 frames all the way to frame 16,037 (99.7%) and produced the final `frame=16083` line, with VMAF score 79.603343 -- identical to the worker run. So FFmpeg is not the problem. The defect is entirely in our stderr-consumer thread.

**Violates:** `Features/QualityTesting/QualityTesting.feature.md` criterion 7 ("Quality test progress is reported in real time"). [BUG] criterion 7b added with this entry.

**Look first:** `Features/QualityTesting/QualityTestingBusinessService.py:722` (`MonitorVMAFProgress`) and `ParseFFmpegProgressLine` (~line 803). Most likely: the FFmpeg stderr read loop terminates on a short/empty read that gets interpreted as EOF before FFmpeg has actually written its final stderr buffer. Or: a poll-timeout in the monitor loop is shorter than FFmpeg's final-flush interval. The thread that runs `MonitorVMAFProgress` should keep reading until FFmpeg's `wait()` returns, and should emit a final `UpdateProgressRecord(..., Status='Completed', ProgressPercentage=100)` regardless of whether stderr produced a tail progress line.

**Fix with:** `/t`. Same monitor handles two visible symptoms (no late-stage progress lines, `Status` never advancing to `Completed`); fix once.

---

### [BUG] env-driven config in singleton `__new__` never fires; operator-controllable knobs scattered across env / KV / fossilized rows
**Date:** 2026-05-10

**Today's specific instance (fixed in commit `e291ca4`):** `Core/Logging/LoggingService.py` read its verbosity flags inside `__new__`, but every callsite in the codebase uses the `@classmethod` form (`LoggingService.LogInfo(...)`) without instantiating -- so `__new__` never executed and `_InfoEnabled` stayed `False` regardless of the `MEDIAVORTEX_LOG_INFO` env var. WorkerService produced zero INFO logs anywhere (terminal or DB) for the entire post-disposition feature work. Discovered during the i9 smoke test when no QT-loop diagnostics were visible. The fix moved env reads to class-attribute initialization (runs at import) and split `LogInfo` so the DB audit write is unconditional while only the terminal print stays gated.

**Broader concern (still open):** operator-controllable knobs are spread across three surfaces today -- env vars (`MEDIAVORTEX_LOG_INFO`, `MEDIAVORTEX_DEBUG`, `MEDIAVORTEX_SHARE_MAPPINGS`, `MEDIAVORTEX_DB_*`), legacy `SystemSettings` KV rows (mostly retired by the post-transcode-disposition feature 2026-05-10), and fossilized state rows (`ServiceStatus.QualityTestService`, fixed in commit `afdca4a`). No doc owns the rule "which kind of knob lives where". Future config bugs will keep slipping through this gap. The path-storage entry below retires the share-mapping env-vars; the typed `PostTranscodeGateConfig` retired a slice of legacy KV; what's left needs an explicit policy.

**Look first:** `grep -rn "os.getenv" --include="*.py"` outside DB connection strings and process-local startup constants. Each match is a candidate for the same trap or worse: an env-driven knob the operator can't change without restarting workers, with no audit, no UI, no per-worker visibility, no hot-reload.

**Fix with:** `/n config-plane.feature.md` -- when scoped, define a typed config table for operator knobs and the explicit rule "env vars only for genuinely process-local startup constants". Also audit other singletons (e.g. `WorkerContext`, `FFmpegService` cached path) for the `__new__`-runs-once-on-instantiation trap. Not in scope today; the immediate observability bug is patched.

**Related (also fixed 2026-05-10):** `ServiceStatus.<X>Service.Status` was being read as a live gate inside `ProcessQualityTestQueueService.ProcessQueueLoop` and `ProcessTranscodeQueueService.ProcessQueueLoop` -- the same fossilized-row anti-pattern as the disposition function. Retired in `Features/ServiceControl/capability-control-plane.feature.md`. The single gate for "should this worker run capability X right now?" is now `Workers.<X>Enabled + Workers.Status='Online' + fresh heartbeat`, full stop.

---

### [BUG - CRITICAL - WORKAROUND IN PLACE] Canonical path storage is OS-coupled
**Date:** 2026-05-10
**Single source of truth for this issue.** Every other doc that touches path translation, share mappings, drive letters, or platform-specific path handling MUST link to this entry rather than re-describing the problem. If you find a duplicate description in any feature/flow doc, replace it with a link to here.

**Affects:** every path column in the database. Concretely: `MediaFiles.FilePath`, `TranscodeQueue.FilePath`, `RootFolders.RootFolder`, `ShowSettings.ShowFolder`, `TranscodeAttempts` path columns, `MediaFilesArchive.FilePath`, and any future column shaped like a path. Also: `Services/PathTranslationService.py`, `Core/WorkerContext.py`, `Repositories/DatabaseManager.py:RegisterWorkerShareMappings`, the `WorkerShareMappings` table, and the `MEDIAVORTEX_SHARE_MAPPINGS` env var.

**Diagnosis:** the canonical form of every path stored in the DB is Windows-shaped -- drive letter + backslashes (`T:\Show\Season 1\file.mkv`). The schema decided, at the row level, that one specific OS shape is the source of truth. Linux workers cannot use the canonical value directly; every read/write has to translate `T:\…` to `/mnt/media_tv/…` via a runtime layer. The translation layer works, but it is a workaround for a schema decision, not a feature.

**Symptoms (all observable in DB Logs):**
- 271+ "Path does not exist, cannot normalize" WARNINGs (`PrivateNormalizePathToFilesystemCase`).
- 80+ "FFprobe failed for ..." ERRORs with no captured stderr.
- 439 "FFmpeg path from settings not found" ERRORs across three distinct path shapes.
- 3 "/bin/sh: 1: C:CodeAutomationMediaVortex..." Linux failures (Windows backslashes shell-stripped).
- The full existence of `PathTranslationService`, `WorkerContext.PathTranslation`, and `WorkerShareMappings` -- all of these are workaround scaffolding.

**Current workaround (in production, working, do NOT touch without a feature):**
- `Services/PathTranslationService.py` translates `T:\…` to per-worker mount on every read/write.
- `WorkerShareMappings` table holds per-worker drive-letter -> local-mount rows (12 rows today: 4 workers x 3 letters M/T/Z).
- `MEDIAVORTEX_SHARE_MAPPINGS` env var on each container seeds those rows at registration time.
- `WorkerContext.Current().PathTranslation` is the runtime entry point all services call.
- `Core/WorkerContext.feature.md` and `deploy/worker-deploy.feature.md` document the workaround surfaces.

**Violates:** `path-storage.feature.md` (repo root) -- success criteria 1, 2, 4. Criterion 1 is the [BUG] criterion: no row in any DB table contains a drive letter or backslash in a path field.

**The right shape (deferred -- scoped in `path-storage.feature.md`):**
- Path columns become `(RootId BIGINT REFERENCES RootFolders(Id), RelativePath TEXT)`. Forward slashes, no drive letter, no leading slash.
- New table `RootFolderResolutions` replaces `WorkerShareMappings`: one row per `(RootId, WorkerName)` with the worker's absolute path for that root.
- Absolute paths are computed at I/O boundaries (FFmpeg invocation, `open()`, `os.path.exists`) by joining root resolution + relative path. Never stored.
- `PathTranslationService` reduces to a join lookup (< 50 LOC, no regex, no drive-letter parsing).

**Look first:** `Services/PathTranslationService.py`, `Core/WorkerContext.py`, `Repositories/DatabaseManager.py:RegisterWorkerShareMappings`, schema of `RootFolders` and `WorkerShareMappings`, and any code site that splits or constructs a path with a drive letter (grep for `[A-Za-z]:\\\\` and `os.sep`).

**Fix with:** `/n` against `path-storage.feature.md`. This is a real project (~8-12 Progress steps when planned). Migration is the bulk of the work; the rule is precise. Do NOT attempt incrementally -- the contract has to flip atomically (schema migration + code cutover + backfill in one operator window).

**Note for future bug records:** symptoms of OS-coupled storage (Windows-flavored paths on Linux, drive-letter assumptions, mount-prefix mismatches) append context HERE rather than open a new entry. This issue is the umbrella.

---

### [BUG - CRITICAL] Profile-less savings estimate uses misleading `SizeMB * 0.5` proxy
**Date:** 2026-05-10
**Affects:** `Features/TranscodeQueue/QueueManagementBusinessService.py:CalculatePriority` (size*0.5 fallback at line 1032), `_EvaluateCompliance` (returns undecidable when profile missing), `EstimateTargetSizeMB` (returns None when profile missing).

When a `MediaFile` has no `AssignedProfile` (and the profile cascade doesn't resolve), every estimate-of-savings path either falls back to `SizeMB * 0.5` (priority calc) or returns "undecidable" (compliance / admission). Result: profile-less files all rank by file size, regardless of compression headroom -- a 5 GB already-AV1 source ranks the same as a 5 GB h264 source. The operator looking at the library to decide which titles to assign profiles to next is sorted by the wrong signal.

**The probed metadata is already there** -- `MediaFiles.Codec`, `OverallBitrate`, `VideoBitrateKbps`, `AudioBitrateKbps`, `DurationMinutes`, `ResolutionCategory` -- nothing reads them for a profile-agnostic compression-potential estimate.

**Why critical:** profile assignment is operator-driven; the operator needs a ranked "next candidates to look at" view that works WITHOUT a profile already being set. Otherwise the assignment-then-queue loop has a chicken-and-egg.

**Violates:** `queue-priority.feature.md` Success Criterion 15 (added with this bug).

**Look first:** `QueueManagementBusinessService.CalculatePriority` (the size*0.5 fallback path) and the `EstimateTargetSizeMB` helper introduced by `marginal-savings-gate.feature.md`. The fix is a profile-agnostic estimator that reads `Codec` + `OverallBitrate` + `ResolutionCategory` and looks up an expected-output-bitrate table (could extend `CrfBitrateEstimates` or add a sibling table -- design choice for the `/t` session).

**Fix with:** `/t`

---

### [BUG] QueueManagementBusinessService.py Cursor-era cleanup backlog
**Date:** 2026-05-10
**Affects:** `Features/TranscodeQueue/QueueManagementBusinessService.py` (2,064 LOC, 35 methods)

Pre-claude-rails (Cursor-written) patterns that the marginal-savings-gate feature explicitly DID NOT clean up to keep its scope tight. Recorded here so they're not lost:

1. **Class is too big.** 2,064 LOC across 7 distinct concerns: queue population, priority calculation, compliance evaluation, recompute, job add/remove, statistics, subtitle-fix population. Fold into smaller services, one per concern.
2. **Silent except blocks** at lines 548-549, 567-568, 1485-1493 (and others). Pattern: `except Exception: pass` with a comment justifying defensiveness. Violates the Phase 2a loud-failure rule. Sweep to `LogException` + re-raise or `LogWarning` with explicit reason.
3. **`LogFunctionEntry(...)` boilerplate** at almost every public method's first line. Useful in early dev, log-spam at scale. Remove or gate on `LOG_LEVEL=DEBUG`.
4. **Boilerplate docstrings** that restate the function name (e.g. line 32 docstring "Populate transcoding queue from MediaFiles..." on `PopulateQueueFromMediaFiles`). CLAUDE.md says "default to writing no comments." Sweep to remove redundant docstrings; keep only ones with WHY content.
5. **Conditional imports inside try blocks** (e.g. line 546). Defensive against modules that always exist. Move to top-level imports.
6. **Legacy `self.DatabaseManager` use** -- 30 call sites of `Repositories/DatabaseManager.py` instead of the feature-local `TranscodeQueueRepository`. The marginal-savings gate replaces this only inside its own touched paths (~5 call sites); remaining 25+ are legacy code paths that need migration to the vertical-slice repo per `KNOWN-ISSUES.md:146`.

**Look first:** `Features/TranscodeQueue/QueueManagementBusinessService.py` -- start with the function-list scan to plan the split, then attack one concern at a time.

**Fix with:** `/n` (this is a refactor, not a single bug -- needs its own feature doc + criteria, especially around the class split which has API-surface implications)

---

### [BUG - RESOLVED 2026-05-16] QualityTestEnabled flip mid-run does not reach the transcode producer; in-flight job replaces file with no VMAF
**Date:** 2026-05-09 | **Resolved:** 2026-05-16
**Affects:** WorkerService.feature.md (criterion 2, criterion 15), `Features/TranscodeJob/ProcessTranscodeQueueService.py:100-101, 885-900, 1329`, `Features/QualityTesting/ShouldQualityTestService.py:34-57`

**Resolution:** The producer-side cache was already removed during the post-transcode disposition rewrite (see `ProcessTranscodeQueueService.py:101` comment "Per-worker QualityTestEnabled is no longer cached on this service instance"). The disposition function (`PostTranscodeDispositionService._DecideFromInputs`) now reads gate state fresh per call. The remaining operator pain -- no global UI lever to bypass VMAF for everything -- is addressed by `post-transcode-disposition.feature.md` criterion 26 (2026-05-16): new `PostTranscodeGateConfig.QualityTestEnabled` column + checkbox on `/settings` Post-Transcode card. When OFF, every successful transcode emits `Disposition='BypassReplace', DispositionReason='QualityTestingGloballyDisabled'` and goes straight to FileReplacement. Mid-flight toggle is safe (no caching).

---

### [BUG - HISTORICAL] QualityTestEnabled flip mid-run does not reach the transcode producer; in-flight job replaces file with no VMAF (original report)
**Date:** 2026-05-09
**Affects:** WorkerService.feature.md (criterion 2, criterion 15), `Features/TranscodeJob/ProcessTranscodeQueueService.py:100-101, 885-900, 1329`, `Features/QualityTesting/ShouldQualityTestService.py:34-57`

`ProcessTranscodeQueueService` caches `WorkerQualityTestEnabled` from the `WorkerConfig` dict at construction time. `WorkerConfig` is loaded once in `WorkerService._RegisterAndLoadWorkerConfig` at process startup and never refreshed, so toggling `Workers.QualityTestEnabled` mid-run does not change `IsQualityTestEnabled()` for the producer side. The capability poller does flip the *consumer* (start/stop QualityTestService), but the producer keeps writing `TranscodeAttempts.QualityTestRequired=False`. `ShouldQualityTestService` reads that False and calls `_ReplaceFileDirectly` (BypassVMAFCheck=True) -- original deleted, transcoded moved in, next job starts. Observed today on i9: VMAF was added mid-job, the in-flight transcode finished, file got replaced without VMAF, and the worker picked up the next job. Repro by starting a worker with `QualityTestEnabled=False`, queuing a job, flipping the flag (or the global) while the job runs, watching the post-success path skip the quality queue.

Secondary trap at line 100-101: `Config.get('QualityTestEnabled') or Config.get('qualitytestenabled')` silently treats a stored `False` the same as an explicit override (cached as False, shadows global), but a missing key collapses to None and falls through to global. The two paths should not behave differently.

**Violates:** WorkerService.feature.md criterion 2 ("Changing a capability flag in the Workers table takes effect within 60 seconds without restarting the process") -- the contract holds for the capability lifecycle but not for the transcode producer's QualityTestEnabled gate.

**Look first:** `Features/TranscodeJob/ProcessTranscodeQueueService.py:885-900` (`IsQualityTestEnabled` -- read live from DB instead of cached snapshot), lines 100-101 (tri-state load, drop the `or` collapse), line 1329 (the call site that stamps `QualityTestRequired` onto the success row), and `WorkerService/Main.py:88-145` (`_RegisterAndLoadWorkerConfig` is the cached snapshot source -- decide whether to refresh it on the capability poll or bypass it for read-mostly settings). Principle going forward: do not cache DB-backed settings on long-lived service instances; read fresh.

**Fix with:** `/t`

---

### [TECH DEBT] Activity page conflates worker liveness and operational state
**Date:** 2026-05-08
**Affects:** Templates/Activity.html (worker tag display), API endpoints that return worker status

The Activity page shows a single "Online/Offline" badge per worker. It appears to be driven by `Workers.LastHeartbeat` freshness (process-is-alive signal). But the `Workers.Status` column is a separate axis -- it carries the operational state set by the Drain/Offline buttons (`Online` / `Draining` / `Offline`). When the user clicked Offline, the DB column flipped correctly to `Offline`, but the UI badge stayed green because the worker process is still alive and heartbeating (alive AND stopped is a valid combination today).

The four real states from the combination:
- Status=Online + heartbeat fresh -- alive AND working (the green "Online" users expect)
- Status=Online + heartbeat stale -- should be working but process is dead (broken, needs investigation)
- Status=Offline + heartbeat fresh -- alive but stopped (process running, not picking up jobs)
- Status=Offline + heartbeat stale -- clean shutdown

**Fix:** show two separate visuals per worker row in the Activity table.
1. Connectivity indicator (dot or pill, color from heartbeat age: green <60s, yellow 60s-5m, red >5m)
2. Operational state pill (text + color from `Workers.Status`: Online green, Draining amber, Offline gray)

The connectivity indicator answers "can I reach this worker?". The operational state pill answers "should this worker be picking up jobs?". These are independent and both useful.

**Look first:** Templates/Activity.html worker-tag rendering, the API endpoint that feeds it (likely under `Features/TeamStatus/` or `Features/ServiceControl/`), and `Workers` schema (Status + LastHeartbeat already exist, no schema change needed).

**Fix with:** `/n` (template + API change, ~30 min)

---

### [TECH DEBT - PARTIALLY RESOLVED] Loud-failure sweep -- Phase 2
**Date:** 2026-05-08 | **Phase 2a applied:** 2026-05-08
**Affects:** Models/CommandBuilder.py, WebService/Main.py, WorkerService/Main.py, Repositories/DatabaseManager.py, Features/Profiles/, Features/FileScanning/, Features/TranscodeQueue/, Services/FFmpegAnalysisService.py, Features/MediaProbe/, Features/FileReplacement/

Phase 1 (commit 6bf51b2) addressed the four highest-risk silent swallows that hid today's Windows-worker FFmpegPath bug. Three parallel agent audits (silent-failure code patterns, recent DB Logs over 48h, FFmpeg path resolution chain) surfaced ~30 more sites and several systemic blind spots that need a follow-up pass. Documented here so the next session can pick it up cleanly.

**Phase 2a applied (this session):**
- [x] WebService/Main.py: 10 `except: print(...)` blocks converted to LoggingService.LogException (lines 154, 341, 354, 363, 390, 421, 434, 447, 455, 464). When WebService is launched detached by StartMediaVortex.py, errors now land in the DB Logs table instead of vanishing to a closed stdout.
- [x] Models/CommandBuilder.py: 4 codec/audio swallows (`AddCodecParameters`, `AddFilmGrainParameter`, `AddPixelFormatParameter`, `BuildAudioFilters`) now LogException with explicit "transcode will run with partial settings" wording so wrong-quality output is traceable.
- [x] Features/FileReplacement/FileReplacementBusinessService.py: stripped the `Failed to update MediaFiles table: Failed to extract metadata: ...` double-wrap. Original FFprobe error surfaces verbatim via LogError with both local + canonical paths; outer call site logs an explicit "MediaFiles update skipped after successful replacement" warning so the cause/consequence are linkable in DB Logs.
- [x] Services/FFmpegService.py ExecuteFFprobe: subprocess timeout and generic exceptions now use LogException (was LogError, no traceback). Non-zero return code log includes truncated stderr + stdout + command in a multi-line block.
- [x] Services/FFmpegAnalysisService.AnalyzeMediaFile: removed redundant double-log of FFprobe failure (ExecuteFFprobe already logs). JSONDecodeError now LogException with output-snippet for diagnosis.
- [x] WorkerService/Main.py SignalHandler: 3 silent `except: pass` blocks (FFmpeg-kill outer, mark-Offline, pool-close) now LogException with stderr fallback if logger itself fails (defensive for shutdown teardown).
- [x] Repositories/DatabaseManager.py: DeleteProfile, DeleteRootFolder, RecordProblemFile getsize -- all 3 now LogException.
- [x] Scripts/FlagMissingMediaFiles.py created. One-shot to bump FFprobeFailureCount=3 on rows whose source path is missing on disk, so queue-population's existing safety guard skips them. Run with --dry-run first.

**Phase 2b remaining (lower priority, capture for future session):**

**Remaining silent-swallow sites (lower-risk, code path):**
- `Models/CommandBuilder.py:284-285` -- `ExtractResolutionFromFilename` returns None silently. Affects output naming.
- `Features/FileScanning/FileScanningRepository.py:80-81` and `Features/Profiles/ProfileRepository.py:121-122` -- duplicates of `DeleteProfile` / `DeleteRootFolder` in vertical-slice copies (Phase 2a covered the DatabaseManager versions).
- `Features/TranscodeQueue/QueueManagementBusinessService.py:478-479` -- silent skip of show-override lookup; file gets wrong target resolution.
- `Features/MediaProbe/MediaProbeBusinessService.py:134-135` -- `_DeriveResolutionCategory` returns None silently; NULL `ResolutionCategory` leaks into queue logic.
- `Features/TranscodeJob/VideoTranscodingService.py:406-408` -- progress parser swallow, "not critical" comment.
- `Features/TranscodeJob/ProcessTranscodeQueueService.py:1660-1661` -- `_ExtractResolutionFromFilename` swallow.
- `WorkerService/Main.py:251-252` -- scan interval setting parse error silent (falls back to 60min).
- `WorkerService/Main.py:488-489` -- drain mode silently swallows QualityTestService.Stop() failure; drain may never actually stop.
- `TranscodeService/config.py:110` -- same `except:print` pattern (TranscodeService is being deprecated -- delete with the dir per the other tech-debt entry above).

**Systemic blind spots from the DB-log audit (48h window):**
- **439 hits** of `GetFFmpegPathFromSettings: "FFmpeg path from settings not found"` -- ERROR-level, no `ExceptionType`. Three distinct paths recur (`/opt/mediavortex/FFmpeg`, `/opt/mediavortex/MediaVortex/...`, `C:\Code\MediaVortex\...`). The function probes/falls back without surfacing the failure. Caller is silently degraded.
- **271+ hits** of `DatabaseManager: "Path does not exist, cannot normalize"` -- WARNING. Likely the dead-file pattern from `PrivateNormalizePathToFilesystemCase` running on stale MediaFiles rows. Phase 1's pre-flight check stops new occurrences from creating attempt rows but doesn't sweep the existing stale rows. Need a one-shot script that flags `MediaFiles` where the path doesn't exist on disk for any worker that can reach it.
- **121 hits** of `_ProcessCompleteFileReplacement: "Failed to update MediaFiles table: Failed to extract metadata"` -- WARNING. Two layers of "Failed to" with no underlying cause. The `ntpath.dirname` fix (commit f5021d2) addresses new occurrences but the wrapper still strips the original exception. Strip the wrapper, log the original.
- **80+ hits** of `AnalyzeMediaFile: "FFprobe failed for ..."` -- ERROR with no `ExceptionType` and no `StackTrace`. Caller logs only the path, not the FFprobe stderr. Capture stderr into ExceptionMessage so we can see *why* FFprobe failed.
- **3 occurrences** of `/bin/sh: 1: C:CodeAutomationMediaVortexFFm...` -- Linux Larry workers tried to execute a Windows-flavored path with backslashes shell-stripped. The path purge in commit 87aaf58 removed the source string, but find the call site that constructed it; some code is still concatenating Windows paths on Linux callers.

**Recommended order when picking this up:**
1. Sweep `WebService/Main.py` `except: print(...)` -> `LogException`. Mechanical, low-risk, big visibility win.
2. Fix the 4 `CommandBuilder.AddCodecParameters/BuildAudioFilters` silent swallows -- highest-risk because they corrupt transcode quality.
3. Strip the "Failed to update MediaFiles table:" wrapper in `_ProcessCompleteFileReplacement` so the original exception surfaces.
4. Capture FFprobe stderr in `AnalyzeMediaFile` exception-path log.
5. One-shot `Scripts/FlagMissingMediaFiles.py` to mark all existing MediaFiles where the path is unreadable from any registered worker.
6. Then the lifecycle / DB-delete swallows.

**Fix with:** `/n` (multi-feature sweep, ~2-3 hours)

---

### [BUG] Worker capability flags not editable from the UI
**Date:** 2026-05-08
**Affects:** WorkerService.feature.md (criterion 14), Activity page, Settings page, `Features/TeamStatus/TeamStatusController.py`

`Workers.TranscodeEnabled`, `Workers.QualityTestEnabled`, `Workers.ScanEnabled` are read by the worker's 60s capability poller, but no UI control writes them -- the operator has to run `UPDATE Workers SET ScanEnabled=true WHERE WorkerName=...` directly via SQL. Same gap as the per-worker Status (Online/Draining/Offline) controls -- but those at least have buttons on the Activity page; capability flags have nothing.

**Look first:** `Features/TeamStatus/TeamStatusController.py` already has `POST /api/TeamStatus/Workers/<name>/Status` for status changes -- mirror that pattern for capability flags. `Templates/Activity.html` worker-row rendering already iterates `/api/TeamStatus/Workers` JSON which includes `TranscodeEnabled`/`QualityTestEnabled`/`ScanEnabled` -- add three toggle controls to each row alongside the existing status buttons.

**Flow doc gap:** `WorkerService.flow.md` covers the read-path (capability polling) but not the write-path. `/t` should extend it with a stage describing the API endpoint contract before the fix.

**Fix with:** `/t` (one new POST endpoint + Activity template change + JS handler; estimate 30-45 min)

---

### [BUG] SystemSettings not normalized; /settings page does not show every row
**Date:** 2026-05-08
**Affects:** SystemSettings.feature.md (criteria 11, 12), `Features/SystemSettings/SystemSettingsRepository.py`, `Templates/Settings.html`

DB state: no UNIQUE on `SettingKey` (duplicates exist: ContinuousScanEnabled x2, ContinuousScanIntervalMinutes x2, ExcludedDirectories x4). `DataType` mixes BOOLEAN/boolean/string/INTEGER/integer/text. List-shaped values stored as CSV (`AllowedExtensions`, `ExcludedDirectories`). Per-file CRF overrides use `CRFOverride_<long_path>` keys instead of a typed override table. Until tonight's UI patch the /settings page only rendered hardcoded known keys (FFmpegPath, MaxCpuThreads, etc.) -- new keys like `DisplayTimezone` were invisible despite existing in the DB. Tonight's commit 505fac2 added a generic "All System Settings" advanced table; criterion 12 is now achievable but the normalization gaps in criterion 11 remain.

**Look first:** `Scripts/SQLScripts/` -- needs a migration that dedupes by `SettingKey` (keep most-recently `LastModified`), adds `UNIQUE(SettingKey)`, and a CHECK constraint on `DataType`. Then move `AllowedExtensions` / `ExcludedDirectories` to child tables and `CRFOverride_*` to a `MediaFileTranscodeOverrides` table keyed on `MediaFileId`. Frontend code that splits CSV in `Settings.html` (search for `.split(',')` near AllowedExtensions/ExcludedDirectories) needs to follow.

**Flow doc gap:** No general flow doc exists for the SystemSettings pipeline (DB row -> Repository -> Controller -> Settings.html UI -> POST round-trip). `/t` should create one before the fix so the dedupe migration and frontend follow-up have a documented contract.

**Fix with:** `/t` (multi-step migration + UI follow-up; estimate 1-2 hours)

---

### [BUG] Workers attempt jobs for MediaFiles entries whose source file no longer exists on disk
**Date:** 2026-05-08
**Affects:** TranscodeJob feature (ProcessTranscodeQueueService, FFprobe build step), TranscodeQueue feature (queue population)
**Criterion violated:** Worker should refuse to claim a job whose source path is unreadable. The pipeline must distinguish "file gone -- mark MediaFile missing, drop from queue, do not retry" from "file unreadable transiently -- retry."

Observed: Bachelor in Paradise S10E01 was successfully transcoded earlier today, but file replacement lost both the original (`T:\Bachelor in Paradise\Season 10\Bachelor in Paradise - S10E01 - Week 1 HDTV-720p.mkv`) and the new file. MediaFiles row 41437 still has the original FilePath, hevc codec, and TranscodedByMediaVortex=NULL. Queue items for it keep being created (Id 76218 most recent). Worker claims the queue item, calls FFprobe to build the command, FFprobe fails with "No such file or directory", attempt fails, and the queue item is removed -- but a new one will appear on the next queue population because the MediaFiles row is unchanged. No pre-flight check verifies the source file exists before claiming/probing/building.

**Look first:**
- `Features/TranscodeJob/ProcessTranscodeQueueService.py` -- ProcessJob entry, where to add `os.path.exists(LocalSourcePath)` check after `SetupFilePreparation` returns the InPlace path. Failing here should set MediaFiles.LastFFprobeError = "Source file missing" + LastFFprobeAttemptDate, optionally bump FFprobeFailureCount, and DELETE the queue item without creating a TranscodeAttempt row.
- Queue-population caller (likely `Features/TranscodeQueue/QueueManagementBusinessService.py`) -- should skip MediaFiles where FFprobeFailureCount >= 3 (existing safety guard per CLAUDE.md). Verify it actually does for the "missing file" case.
- `Features/FileReplacement/FileReplacementBusinessService.py` -- the move-then-update sequence that lost Bachelor S10E01 in the first place. Need atomic semantics so a failed re-probe does not leave the original deleted and the new file in an unknown state.

**Fix with:** `/t` -- single-feature work, scope is clear

---

### [BUG] Second concurrent job shows first job's progress
**Date:** 2026-05-05
**Affects:** TranscodeJob feature -- concurrent job progress tracking
**Criterion violated:** TranscodeJob.feature.md -- each running job must report independent progress

When MaxConcurrentJobs > 1 and a second job starts while the first is still running, the second job displays the same progress percentage and ETA as the first (e.g., both show 20.5% / ETA 01:41:41). Only one FFmpeg process is actually running.

**Look first:** `Features/TranscodeJob/ProcessTranscodeQueueService.py:169` (`GetStatus` returns single `currentProgress`), `GetCurrentTranscodeProgress()` in DatabaseManager (likely returns one row, not per-job), and `VideoTranscodingService.TranscodeVideo` (process spawning).

**Fix with:** `/t`

---

### [BUG] DatabaseManager.py monolith -- dual database access paths
**Date:** 2026-05-07
**Affects:** All features that still import from Repositories/DatabaseManager.py instead of their own Repository
**Criterion violated:** Feature vertical isolation -- each feature should access the database exclusively through its own Repository

`Repositories/DatabaseManager.py` (630+ lines) is the legacy data access layer. Features are supposed to use `Features/<Name>/<Name>Repository.py`, but some still call DatabaseManager directly. This creates two paths to the database: the feature Repository and the legacy monolith. Unclear where new queries should go, and changing a query may need updates in two places.

**Look first:** `Repositories/DatabaseManager.py` -- audit which features import from it. Cross-reference with each `Features/<Name>/<Name>Repository.py` to find overlap.

**Fix with:** `/n` (this is a migration, not a quick fix -- needs audit of all callers first)

---

### [BUG] Feature vertical boundaries do not match governed code
**Date:** 2026-05-07
**Affects:** TranscodeJob.feature.md, FileReplacement.feature.md, Services/CommandBuilderService.py, Services/FFmpegAnalysisService.py, Core/Services/PathTranslationService.py
**Criterion violated:** TranscodeJob.feature.md scope/criteria mismatch; FileReplacement.feature.md cross-feature dependency

TranscodeJob.feature.md declares scope `Features/TranscodeJob/**` + `WorkerService/Main.py`, but its criteria govern behavior in CommandBuilderService (conditional yadif, output mode), FFmpegAnalysisService (per-worker FFprobe), PathTranslationService (multi-prefix translation), and ProcessTranscodeQueueService (VMAF toggle, worker config loading). Separately, FileReplacement depends on MediaProbe for re-probing with no explicit contract.

**Look first:** TranscodeJob.feature.md criteria list -- each criterion that references a file outside the declared scope. `Features/FileReplacement/FileReplacementBusinessService.py` for the MediaProbe call.

**Fix with:** `/n` (architectural boundary redesign -- either expand TranscodeJob scope or extract worker/command-building into separate feature verticals)

---

### [BUG] FilePath used as denormalized natural key across 6+ tables
**Date:** 2026-05-05
**Affects:** Schema-wide -- MediaFiles, TranscodeAttempts, TranscodeFiles, TranscodeQueue, CompliantFiles, ProblemFiles
**Criterion violated:** Data normalization -- same filepath (with platform-specific drive letter prefix) stored redundantly across tables instead of referencing MediaFiles.Id as a foreign key.

Full Windows paths (e.g., `T:\Shows\file.mkv`) are stored as natural keys in at least 6 tables. This causes:
1. Case inconsistencies already present in production data (`T:\` vs `t:\`, `Z:\` vs `z:\`)
2. Platform coupling -- every table embeds Windows drive letters, making cross-platform workers depend on prefix translation at query boundaries
3. No referential integrity -- deleting/renaming a file in MediaFiles does not cascade to dependent tables
4. Path changes (drive letter remapping, share migration) require updating every table

**Scale:** ~67k rows in MediaFiles, ~3.8k in TranscodeFiles, ~2.9k in TranscodeAttempts, ~1.4k in CompliantFiles.

**Migration in progress (Phase 3 of architecture redesign):**
- [x] MediaFileId BIGINT columns + indexes added to 5 child tables (AddMediaFileIdColumns.py)
- [x] Backfill completed: 1,952 rows linked, 6,867 orphans (old history with deleted files)
- [x] All JOINs and INSERTs updated in code to use MediaFileId
- [x] FK constraints added (AddMediaFileForeignKeys.py) -- TranscodeFiles/TranscodeAttempts ON DELETE SET NULL, TranscodeQueue/CompliantFiles/ProblemFiles ON DELETE CASCADE
- [x] All WHERE/JOIN reads switched from FilePath to MediaFileId (Phase 3b Step 1)
- [x] FilePath removed from INSERT/UPDATE statements for TranscodeAttempts, TranscodeFiles, ProblemFiles (Phase 3b Step 2)
- [x] NOT NULL constraint dropped from FilePath on TranscodeAttempts, TranscodeFiles, ProblemFiles (was blocking INSERTs)
- [x] Deploy verification -- workers Online and heartbeating (root cause: CrashRecoveryService killed itself because Python is PID 1 in Docker and the recorded ProcessId from a prior crash matched the new container's own PID; also bumped postgres max_connections 30->200 and added pool closeall() before os._exit() to stop connection-leak death spiral)
- [ ] Run RenameFilePathColumns.py to soft-rename columns (Phase 3b Step 4)
- [ ] Drop FilePath_Deprecated columns (Phase 4 -- point of no return)

---

### [BUG] Workers in broken canonical state silently fail scanning; no multi-drive scanning workflow
**Date:** 2026-05-13

**What breaks:** Two related gaps in the scanning pipeline:

(1) **Unknown worker state.** A worker with `ScanEnabled=true` but broken path resolution (missing `WorkerShareMappings` rows, unmapped drives, `PathTranslationService` returning untranslated Windows paths on Linux) silently begins a scan pass. `ContinuousScanService` calls `StartScanning` for each RootFolder without validating that `_ToLocalPath(RootFolderPath)` resolves to an accessible local directory. The result is `os.walk` errors, wrong paths inserted into MediaFiles, or scans that appear to complete with 0 files found. No pre-scan health check, no operator-visible signal that a worker's path state is broken.

(2) **Multi-drive scanning.** RootFolders are seeded under specific drive prefixes (T:\\, M:\\, Z:\\). Adding a new drive to scan requires: manually inserting RootFolders rows, adding `WorkerShareMappings` rows for every worker that can reach the new drive, and restarting workers. There is no UI workflow to register a new drive/share, associate it with workers, and begin scanning. The operator cannot scan from all workers across all drives without manual SQL and restarts.

**Violates:** `Features/FileScanning/FileScanning.feature.md` criteria 20, 21 (added with this entry). `WorkerService/WorkerService.feature.md` criterion 19 (added with this entry).

**Look first:** `Features/FileScanning/ContinuousScanService.py` `_ExecuteScan` -- where pre-scan path validation should fire. `Features/FileScanning/FileScanningBusinessService.py` `_ToLocalPath` -- the translation call that should be validated. `Services/PathTranslationService.py` -- the translation layer. `Templates/Settings.html` or `Templates/FileScanning.html` -- where a "add drive" UI would live. `Repositories/DatabaseManager.py:RegisterWorkerShareMappings` -- the current seeding path for share mappings. Related: `KNOWN-ISSUES.md` canonical path storage entry (the root cause); `path-storage.feature.md` (the long-term fix).

---

### [BUG] QueryDatabase.py truncates long text columns at 60 chars -- error messages unreadable
**Date:** 2026-05-13

**What breaks:** `Scripts/SQLScripts/QueryDatabase.py` hardcodes `max_col_width=60` in `print_table()` with no CLI override. Long values -- `errormessage`, `ffpmpegcommand`, `filepath` -- are silently cut to 57 chars + `...`. The operator cannot read error messages from `TranscodeAttempts` without dropping into raw Python to query the DB directly. Discovered when diagnosing a remux failure: the `PrepareReplacement failed: Pre-existing .orig backup at /...` message was truncated, hiding the actual file path needed to resolve it.

**Violates:** `Features/SQLQueries/SQLQueries.feature.md` criterion 6 (added with this entry).

**Look first:** `Scripts/SQLScripts/QueryDatabase.py` lines 47-74 (`print_table` and `truncate`). Add a `--width N` CLI flag (default unlimited or large); pass through to `max_col_width`.

---

### [BUG - FIXED 2026-05-21] Bare-metal Linux host bootstrap not codified -- manual SSH steps required before deploy-linux-worker.py
**Date:** 2026-05-16 (opened); 2026-05-21 (closed)

**Resolution:** `infrastructure/terraform/mediavortex-bare-metal-bootstrap.py` lands the canonical bootstrap. Reads `fstab_mounts` from `infrastructure/terraform/inventory.toml` (new field on `vm_type = "bare-metal"` entries), idempotently installs `nfs-common` + Docker CE, applies a managed block in `/etc/fstab`, creates `/staging` + `/opt/mediavortex` + every mountpoint, runs `mount -a`. New bare-metal bringup: `py infrastructure/terraform/mediavortex-bare-metal-bootstrap.py --host <friendly>` then `py deploy/deploy-linux-worker.py <friendly>`. Verifiable: re-running the bootstrap on a clean host is a no-op (managed-block sed delete + re-append yields identical fstab; package + dir checks short-circuit). See `infrastructure/docs/features/linux-worker-deploy.md` criterion 10 (also marked resolved 2026-05-21) for the host-side acceptance test. This entry should be moved to the Resolved section with a `BUG-NNNN` ID on the next housekeeping pass.

**What breaks:** Adding a new bare-metal Linux worker host today requires manual SSH steps before `deploy/deploy-linux-worker.py` will pass its pre-flight check: install Docker CE, install nfs-common, append three NFS entries to `/etc/fstab` (Brain media_tv, Synology movies, Synology xxx), `mount -a`, and `mkdir /staging /opt/mediavortex`. LXC has the equivalent codified at `infrastructure/terraform/mediavortex-workers/setup.sh`. Bare-metal has nothing.

Done manually for dot on 2026-05-16 -- worked in ~5 minutes -- but the manual steps undermine the "one command from fresh" experience that the worker-deploy feature promises for already-provisioned hosts. The exact commands run on dot are visible in the conversation transcript and on dot itself via `/etc/fstab` + apt history.

**Violates:** `infrastructure/docs/features/linux-worker-deploy.md` criterion 10 (added with this entry). Does NOT violate `deploy/worker-deploy.feature.md` -- that feature's scope explicitly excludes host provisioning; criterion 5 (fail-fast pre-flight) is satisfied today because the script correctly reports the missing prereqs.

**What "fixed" looks like:** A script at `infrastructure/terraform/mediavortex-bare-metal-bootstrap.sh` (or similar) that takes a target hostname/IP from `inventory.toml`, idempotently installs Docker CE + nfs-common, configures fstab from a canonical mount template, runs `mount -a`, and creates the required directories. After it runs, `deploy/bringup.md` bare-metal prerequisites collapse from a checklist to "run the bootstrap script first." Verifiable: on a host with only base Ubuntu + SSH, running the bootstrap script followed by `deploy-linux-worker.py <friendly>` brings the host to `Workers.Status='Online'` with zero manual steps in between.

**Look first:** `infrastructure/terraform/mediavortex-workers/setup.sh` (LXC equivalent, ~lines 1-100 -- the AppArmor purge is LXC-specific and should NOT carry over to bare-metal); `deploy/bringup.md` (current manual prereq section for bare-metal Linux); `infrastructure/terraform/inventory.toml` (canonical source for friendly name -> IP and ssh_user lookup); the NFS fstab entries that worked on dot 2026-05-16 are the same three lines used on Wakko (Brain `10.0.0.40:/mnt/pve/Media/_tv` nfs4, Synology `10.0.0.61:/volume1/_video` nfs vers=3, Synology `10.0.0.61:/volume2/XXX` nfs vers=3, all with `_netdev,nofail`).

**Fix with:** `/t`.

---

## Resolved

### [BUG-0001 - FIXED 2026-05-17] Stuck-item cleanup gaps -- operational rows leak past their job's terminal state
**Date:** 2026-05-16 | **Fixed:** 2026-05-17 | resolved: 2026-05-17

**What broke:** Four distinct paths let operational rows linger past terminal state. Observed on I9-2024 with 17 workers Paused: 9 stale `ActiveJobs` (no parent queue row), 1 `QualityTestingQueue` row in flight 5+ hours after its attempt succeeded, 18 `TranscodeProgress` orphans + duplicates (no UNIQUE), **551 `TemporaryFilePaths` rows** for finished attempts (`_CleanupTemporaryFilePaths` only ran inside `ProcessFileReplacement`'s success branch -- every other terminal state leaked).

**Fix (shipped 2026-05-17):** Four-part bundle, verified live.

1. **TFP chokepoint at disposition (criterion 15).** `Features/QualityTesting/PostTranscodeDispositionService._CommitDisposition` now deletes the TFP row inline when `Disposition IN ('Discard','NoReplace','Requeue')` (`Replace`/`BypassReplace` defer to FileReplacement's existing success-branch cleanup because they still need the canonical paths). `Features/QualityTesting/QualityTestingBusinessService._CleanupTemporaryFilePathsForVmafFailure` covers the VMAF-failure path. FFmpeg/FFprobe-verify failures were already covered by `HandleJobFailure` in `ProcessTranscodeQueueService`.

2. **ActiveJobs root-cause + sweep (criterion 16).** A direct FK on the polymorphic `ActiveJobs.QueueId` is impossible (it references either `TranscodeQueue` or `QualityTestingQueue` depending on `ServiceName`), and a DB trigger would hide the leaking caller. Root-cause fix: `QueueManagementBusinessService.RemoveJobFromQueue` now deletes the matching `ActiveJobs` row even on the non-Running path (previously only `_CancelRunningJob` cleaned it for Running rows). Safety net: the new orphan sweep emits one WARN log per removal naming the gone `ServiceName`/`QueueId`/`WorkerName`, so any future regression surfaces immediately.

3. **Recurring orphan sweep (criteria 16, 17, 18).** New `Features/ServiceControl/OrphanCleanupService.SweepOrphans` runs every `StuckJobDetectionIntervalSec` (default 120s) as a sibling daemon to `_StuckJobDetectionLoop`. Five sweep steps: TFP orphans, ActiveJobs(TranscodeService), ActiveJobs(QualityTestingService), stale QualityTestingQueue, orphaned TranscodeProgress. One INFO summary per cycle; WARN per removal. Flow doc: `Features/ServiceControl/orphan-cleanup.flow.md`.

4. **TranscodeProgress UNIQUE (criterion 18).** `Scripts/SQLScripts/AddOrphanCleanupAndUniqueProgress.py` -- idempotent migration that dedupes existing rows (keep latest per `TranscodeAttemptId`) then adds `UNIQUE (TranscodeAttemptId)`.

**Verified:** 2026-05-16 manual sweep cleared the 550 TFP backlog in one cycle (WARN log fired). 2026-05-17 live worker logged two consecutive `OrphanCleanup swept: TFP=0 ActiveJobs(Transcode)=0 ActiveJobs(QualityTest)=0 QTQueue=0 Progress=0` lines 120s apart -- steady state holds. All 18 feature criteria pass.

**Files:** `Features/QualityTesting/PostTranscodeDispositionService.py:263`, `Features/QualityTesting/QualityTestingBusinessService.py:26-41` (new helper), `Features/TranscodeQueue/QueueManagementBusinessService.py:2077` (ActiveJobs cleanup), `Features/ServiceControl/OrphanCleanupService.py` (new), `Features/ServiceControl/orphan-cleanup.flow.md` (new), `Scripts/SQLScripts/AddOrphanCleanupAndUniqueProgress.py` (new migration), `WorkerService/Main.py:617` (loop startup) + `:801-846` (loop body), `Features/FileReplacement/post-transcode-pipeline.feature.md` criteria 15-18, `transcode.flow.md` Stage 6 tables-written.

---

### [BUG - FIXED 2026-05-16 - CRITICAL] Worker with broken NFS mount silently destroys queue -- marks all files as source-missing
**Date:** 2026-05-14 | **Fixed:** 2026-05-15 (validation gate) + 2026-05-16 (UI surfacing, data remediation) | resolved: 2026-05-16

**What broke:** wakko-worker-1 was set to Online after a redeploy with `/mnt/media_tv` pointing at the local NVMe (908G) instead of the NAS NFS share. For ~4.5 hours it claimed queue items, found "source file missing" per-file (correct -- the share wasn't mounted), bumped `FFprobeFailureCount`, marked the row source-missing, and deleted the queue item. 154 MediaFiles were corrupted this way (the original "~6" estimate was the first 2 minutes only). Files were fine on the NAS -- wakko just couldn't see them.

**Root cause:** No mount validation gated the Online transition. The per-file "source missing" check was correct behavior for genuinely missing files but catastrophically wrong when the entire mount was broken -- it treated a mount failure as thousands of individual file failures.

**Fix (shipped 2026-05-15, surfaced 2026-05-16):**
- `WorkerService/Main.py::_ValidateStorageMounts()` queries `StorageRootResolutions` for the worker and checks each `AbsolutePath` is a directory, readable, AND non-empty. Empty = local FS showing through where a share should be mounted.
- `WorkerService/Main.py::_ApplyMountValidationResult()` writes `Workers.MountValidationError`, forces `Status='Paused'`, and gates capability startup. Re-runs on every Paused -> Online transition via `_HandleStatusChange()`.
- `Scripts/SQLScripts/AddMountValidationErrorColumn.py` adds the new column.
- `Features/TeamStatus/TeamStatusController.py::GetWorkers` returns `MountValidationError`; `Templates/Activity.html` renders a red alert on the worker tile when set, so the operator sees the failure reason without reading logs.

**Data remediation:** `Scripts/ResetWakkoMountFailureCounts.py` -- one-shot, idempotent, dry-run-by-default. Found 154 false-positive flags from the wakko window (2026-05-14), confirmed each file exists on disk now, reset `FFprobeFailureCount=0` and cleared `LastFFprobeError`. Verified post-fix count in window = 0.

**Verifies:** `WorkerService/worker-lifecycle.feature.md` criteria 20, 21. All 17 enabled workers return `MountValidationError=NULL` on live fleet (healthy baseline).

**Files:** `WorkerService/Main.py:495 _ValidateStorageMounts`, `WorkerService/Main.py:538 _ApplyMountValidationResult`, `WorkerService/Main.py:586` (startup gate) + `:859` (resume gate), `Scripts/SQLScripts/AddMountValidationErrorColumn.py`, `Scripts/ResetWakkoMountFailureCounts.py`, `Features/TeamStatus/TeamStatusController.py:297-300, 329`, `Templates/Activity.html:455-463`, `WorkerService/WorkerService.flow.md` step 7a.

---

### [BUG - FIXED 2026-05-16] MediaFiles had 45,420 duplicate `(StorageRootId, RelativePath)` rows from backslash-escape variants
**Date:** 2026-05-16 | **Fixed:** 2026-05-16 | resolved: 2026-05-16

**What broke:** Same physical file had multiple `MediaFiles` rows because `FilePath` strings differed in escaping (`T:\Show\f.mkv` vs `T:\\Show\f.mkv`). The existing `idx_mediafiles_filepath_unique` keyed on raw `LOWER(FilePath)` so string-distinct variants coexisted; no unique index on `(StorageRootId, RelativePath)`. 45,420 duplicate groups (90,840 rows out of ~102k) -- exactly two rows per group with the high-Id row carrying a doubled leading backslash. ~9k loser rows had FK refs split across `TranscodeAttempts`, `TranscodeFiles`, `MediaFilesArchive`, and `ProblemFiles`.

**Root cause:** the historical FileName/FilePath escaping bug (commit `706f2bc`, Linux `os.path.basename` returning the whole canonical path) produced variant-escaped FilePath strings; `SaveMediaFile`'s existence check used `LOWER(FilePath) = LOWER(%s)` -- string-exact, so variants passed as "new file" and were inserted. The unique index used the same key, so it didn't catch them either. The `(StorageRootId, RelativePath)` tuple is identical between variants (RelativePath uses forward slashes) but had no unique constraint, so coexistence was permitted at every layer.

**Violates:** `Features/FileScanning/FileScanning.feature.md` criterion 27.

**Fix:**
- `Scripts/SQLScripts/DedupeMediaFilesByRelativePath.py`: per-group keeper selection (cleanest FilePath -- fewest doubled backslashes -- tiebreaker highest Id), FK migration on `TranscodeAttempts.MediaFileId`, `TranscodeQueue.MediaFileId`, `TranscodeFiles.MediaFileId`, `ProblemFiles.MediaFileId`, and `MediaFilesArchive.Id` correlation, then DELETE losers. Per-group transactions for resumability. Idempotent + `--dry-run`. Ran clean against prod: 45,420 groups committed, 0 remaining.
- `Scripts/SQLScripts/AddMediaFilesStorageRootRelativePathUnique.py`: creates `idx_mediafiles_storageroot_relpath_unique ON MediaFiles (StorageRootId, LOWER(RelativePath)) WHERE StorageRootId IS NOT NULL AND RelativePath IS NOT NULL`. Pre-checks dup count is zero.
- `Features/FileScanning/FileScanningRepository.py::SaveMediaFile`: existence check now keys on `(StorageRootId, LOWER(RelativePath))` when both are set; falls back to `LOWER(FilePath)` for legacy rows lacking storage-root data so the path-storage transition stays smooth.
- `idx_mediafiles_filepath_unique` left in place (still a useful guard against FilePath-only inserts during transition).

**Backend verification:** dup-group count 45,351 -> 0 confirmed against prod. UNIQUE constraint rejects test duplicate insert with `psycopg2.errors.UniqueViolation` as expected. MediaFiles row count 102,576 -> 56,698 (matches losers removed + earlier overlapping FilePath dedup).

**Files:** see `Scripts/SQLScripts/DedupeMediaFilesByRelativePath.py`, `Scripts/SQLScripts/AddMediaFilesStorageRootRelativePathUnique.py`, `Features/FileScanning/FileScanningRepository.py::SaveMediaFile`, `Features/FileScanning/FileScanning.feature.md` criterion 27.

---

### [BUG - FIXED 2026-05-16] Card 1.5 sort parity + header parity with Card 1
**Date:** 2026-05-16 | **Fixed:** 2026-05-16

**What broke:**
1. **Count-badge format diverged.** Card 1 ("Next Batch") rendered `BatchItems.length` (next-batch size). Card 1.5 ("Next Remux Batch") rendered `RemuxTotalCandidates` (total pool remaining). Operator could not eyeball "what gets queued vs what's left" from the badges.
2. **Sort did not consider size meaningfully on Card 1.5.** Both cards used `ORDER BY PriorityScore DESC NULLS LAST, SizeMB DESC`. PriorityScore is materialized for 100% of rows in both modes (verified live DB), but for a `RecommendedMode='Remux'` row the score models *transcode savings* -- meaningless for a remux operation that does not re-encode video. Card 1.5's top row was a 217 MB MP4 at PriorityScore 85, while a 1,956 MB Ghostbusters MKV (a genuinely larger remux candidate) sat at row 2.
3. **Card 1.5 header had two extraneous captions.** "Audio normalize + container fix (no video re-encode)" subtitle and "no profile needed" italic caption — operator wanted them gone; the title alone is sufficient.

**Violates:** `Features/ShowSettings/remux-populate-card.feature.md` criterion 21.

**Fix:**
- `Features/TranscodeQueue/QueueManagementBusinessService.py::SmartPopulateQueue` ORDER BY changed to `SizeMB DESC NULLS LAST, PriorityScore DESC NULLS LAST` for both modes. Size is the meaningful primary key; priority is the tiebreaker. Card 1 ordering changes minimally (size correlates with priority for transcode); Card 1.5 leads with the largest remux candidates (verified: 2,666 MB JFK MKV at top vs prior 217 MB MP4).
- `Templates/ShowSettings.html`: both count badges render `<batch>/<total>` (e.g. `100/17,045` and `250/7,439`); badge text now set inside `RenderBatch` / `RenderRemuxBatch` so it always reflects the displayed batch length and total candidates together. Removed Card 1.5 subtitle and "no profile needed" caption.
- `Features/ShowSettings/smart-populate.feature.md` criterion 2 and `Features/ShowSettings/smart-populate.flow.md` updated to document the new sort key.

**Performance note:** new ORDER BY EXPLAIN ANALYZE is top-N heapsort on Seq Scan at 97 ms -- well under the 250 ms p95 threshold per `smart-populate.feature.md` criterion 19. The existing partial index `idx_mediafiles_smartpopulate` is now keyed for the prior sort and unused by SmartPopulate; can be replaced with `(SizeMB DESC NULLS LAST, PriorityScore DESC NULLS LAST)` in a follow-up if p95 ever trends up.

---

### [BUG - FIXED 2026-05-16] HasFileChanged returns True for every file when a different worker scans them
**Date:** 2026-05-16 | **Fixed:** 2026-05-16 | resolved: 2026-05-16

**What broke:** Two workers in different system timezones produced different `FileModificationTime` values for the same physical file. I9-2024 (MST) wrote one value; larry-worker-1 (UTC container) computed a value 25,200 seconds (7 hours) different for the same POSIX mtime. `HasFileChanged`'s 1s tolerance was nowhere close to forgiving the gap, so every cross-worker scan flipped every file as "updated."

**Root cause:** `GetFileModificationTime` called `datetime.fromtimestamp(ts)` without a `tz=` parameter, returning a naive datetime in the worker's local timezone. The DB column `MediaFiles.FileModificationTime` is `timestamp without time zone` so the offset was silently lost. Same anti-pattern at `IsSameFile`.

**Fix (commit 5f1f6f8):** Both `GetFileModificationTime` and `IsSameFile` now compute mtime as naive UTC via `datetime.fromtimestamp(ts, tz=timezone.utc).replace(tzinfo=None)`. Worker-independent. DB column type unchanged. Verified locally: cross-tz delta drops from 25,200s to 0s.

**Backend verification:** Larry post-fix M:\ scan #64932 produced `UpdatedFiles=0` (clean incremental skip). T:\ #64933 and Z:\ #64934 first post-fix passes performed the documented one-time correction storm successfully (T:\ corrected 15,458 / 45,716 rows that earlier-aborted #64931 hadn't reached; Z:\ corrected the full ~7,913 I9-MST-only population). After the storm, the column is uniform UTC and stable.

**Pending verification (not blocking closure):** Cross-worker end-to-end proof with I9 still to come -- I9 WorkerService is currently down per operator's call. When restarted with the new code (5f1f6f8 is already in `C:\Code\MediaVortex` working tree), I9's first scan should report `UpdatedFiles=0` for files Larry just normalized to UTC. That confirms ping-pong is gone for good.

**Files:** `Features/FileScanning/FileScanningBusinessService.py::GetFileModificationTime` (line ~1179), `IsSameFile` (line ~1225); `Features/FileScanning/FileScanning.feature.md` criterion 26; `Features/FileScanning/FileScanning.flow.md` Failure Modes table.

---

### [BUG - FIXED 2026-05-15] Optimization page Jellyfin sync form fails with "paramiko is not installed"
**Date:** 2026-05-15 | **Fixed:** 2026-05-15 | resolved: 2026-05-15

**What broke:** Submitting the Jellyfin sync form on http://10.0.0.7:5000/Optimization returned `{"Success": false, "ErrorMessage": "paramiko is not installed"}`. `paramiko>=3.0.0` was declared in `requirements.txt` line 21, so the dependency was meant to be present.

**Root cause:** The running WebService process launches from `C:\Code\MediaVortex\WebService\venv\` (a service-local venv) rather than the root `venv/` that `CLAUDE.md` documents. `WebService/venv/` was missing paramiko despite the declaration. `JellyfinService.py` wraps `import paramiko` in try/except and falls through to a hard-coded error string at line 39, which surfaced as the user-visible message.

**Fix:** Ran `pip install -r requirements.txt` into `WebService/venv/`. paramiko-5.0.0 installed. No code changes -- the envelope behavior at `Features/Optimization/JellyfinService.py:6-10` was already correct.

**Closes:** `Features/Optimization/Optimization.feature.md` criterion 8. New flow doc: `Features/Optimization/Optimization.flow.md` covers the Jellyfin SSH sync pipeline and explicitly lists the "paramiko not installed in runtime venv" failure mode and the two-venv gotcha.

**Action remaining for operator:** restart WebService -- the running process imported paramiko at startup and cached `PARAMIKO_AVAILABLE = False`.

---

### [TECH DEBT - FIXED 2026-05-15] Card 1.5 Add Batch -- legacy bookkeeping, redundant payload, arbitrary size cap
**Date:** 2026-05-15 | **Fixed:** 2026-05-15

**What was wrong:** Card 1.5 "Add Batch" payload duplicated MediaFiles data (~52KB at 250 items, scaling linearly); server did three round-trips (existing-paths SELECT, MediaFiles SELECT, bulk INSERT); 1-500 size cap was arbitrary; no "queue all matching" affordance; size selector reset on every page load; dead code (per-row `Item.get('Mode')` fallback, dead `Priority` assignment in QueueByFolder, never-fired per-item-insert fallback).

**Fix:**
- `AddSuggestionsToQueue` now accepts `MediaFileIds` (slim) or legacy `Items`; rewritten as a single `INSERT INTO TranscodeQueue ... SELECT FROM MediaFiles WHERE Id = ANY(%s) AND NOT EXISTS (...)` with priority computed inline as `COALESCE(PriorityScore, size-based fallback)`. No Python per-item loop; no per-item DB lookup; bulk-insert-fallback removed (verified zero hits historically).
- New `/api/ShowSettings/QueueAllMatching` endpoint + `QueueAllMatching` service method: one `INSERT...SELECT` against the cascade-filtered set with optional `Search`/`Drive` filters.
- `Templates/ShowSettings.html`: both Add Batch buttons send `{Mode, ProfileId, MediaFileIds:[...]}` only; new "Queue All" button on Card 1.5; `localStorage`-backed sticky size for both selectors; `max="500"` → `max="1000"`; collapsed duplicate `PAGE_SIZE`/`REMUX_PAGE_SIZE` vars into the BATCH_SIZE values.
- `SmartPopulateQueue` Limit ceiling 500 → 1000.
- `QueueByFolder` slimmed to pass `MediaFileIds` only; dead `Priority` line dropped.
- `smart-populate.flow.md` stages 7-8 updated to describe the single-statement INSERT path and the new "queue all matching" entry point.

**Violates:** `Features/ShowSettings/remux-populate-card.feature.md` criterion 20.

---

### [BUG - FIXED 2026-05-15] Next Remux Batch "Add Batch" button takes 3-10 seconds
**Date:** 2026-05-15 | **Fixed:** 2026-05-15

**What broke:** On `/ShowSettings`, clicking the "Add Batch" button on the Next Remux Batch card (Card 1.5) took 3-10 seconds.

**Root cause:** `AddSuggestionsToQueue` called `GetProfileSettingsForTargetResolution` per item to feed `CalculatePriority`. Each call did 2 SELECTs plus 2-3 synchronous `LogInfo` INSERTs (~45ms on the network DB). For a 250-item batch that serialized to ~11 seconds. The profile-target bitrate estimate is meaningless for Mode='Remux' (no video re-encode), so the call was both expensive and useless on this path.

**Fix:** In `Features/TranscodeQueue/QueueManagementBusinessService.py`, gate the per-item `GetProfileSettingsForTargetResolution` call on `ItemMode != 'Remux'`. CalculatePriority's SizeMB-based fallback applies for Remux items. `SuppressFallbackWarning=True` was already set so no log spam.

**Violates:** `Features/ShowSettings/remux-populate-card.feature.md` criterion 19.

---

### [BUG - FIXED 2026-05-14] Remux jobs instantly fail with opaque "Failed to setup file preparation" -- 482 wasted attempts
**Date:** 2026-05-14 | **Fixed:** 2026-05-14

**What broke:** Workers claimed remux queue items, created a TranscodeAttempt row, then immediately failed at `SetupFilePreparation` with the generic message "Failed to setup file preparation for remux". 482 failed TranscodeAttempts across 6 larry workers. Source files didn't exist on disk (queue populated from stale MediaFiles rows). Error message was opaque -- actual exception logged to Logs table but not propagated to TranscodeAttempts.ErrorMessage.

**Fix:** (1) Added source-file existence pre-flight check to `ProcessRemuxJob`, mirroring the existing check in `ProcessJob`. Missing source: marks `MediaFiles.FFprobeFailureCount++`, deletes queue item and ActiveJob, no TranscodeAttempt row created. (2) Added `_LastSetupError` propagation from `SetupFilePreparation` to all callers so TranscodeAttempts.ErrorMessage includes the actual exception detail.

**Violates:** `Features/TranscodeJob/TranscodeJob.feature.md` criteria 17-18.

---

### [FEATURE - DONE 2026-05-14] Disable/enable workers -- hide retired workers from UI

**Problem:** Retired workers (e.g. Remington) remain visible in the Activity page worker cards forever. No way to hide them without deleting the row (which loses historical config).

**Solution:** Added `Workers.Enabled` column (BOOLEAN, default TRUE). The `/api/TeamStatus/Workers` endpoint filters to `Enabled=TRUE` by default. A `?IncludeDisabled=true` query param shows all. Activity page has a "Show Disabled" toggle and Disable/Enable buttons on each worker card. Disabled workers render dimmed with a dark "Disabled" badge.

**Files:** `TeamStatusController.py` (endpoints), `Activity.html` (UI), `AddWorkerEnabledColumn.py` (migration).

---

*Older resolved entries archived to `memory/KNOWN-ISSUES-ARCHIVE.md`.*
