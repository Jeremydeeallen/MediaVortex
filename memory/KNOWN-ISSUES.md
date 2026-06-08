# Known Issues

## Active

### uncategorized

*Per-entry area subsection assignment deferred to follow-up directive `migrate-bugs-compliance-deep`. Consult `memory/BUG-INDEX.md` for per-bug area metadata and the operationally-correct active/resolved classification (several entries below still bear `RESOLVED`/`FIXED` annotations in their headers despite living under `## Active`; the INDEX classifies them correctly).*

### [BUG-0045] Directive anchor convention + hook validators are too loose for shared / hot functions
**Date:** 2026-06-08 | **Area:** standards-hook

**What breaks:** Three related gaps in how `pre-edit-standards.ps1` validates the `# directive: <slug> | # see <slug>.<ID>` anchor on a `def`/`class`. All three surface as the same operator-visible pain: shared functions touched by multiple directives end up with either lost provenance (operator "replaces" the anchor to avoid R12) or silently-wrong anchors (active directive's slug not present, see-ID typo'd against the active directive).

**Three sub-items, ship in one follow-up directive (`/n anchor-convention-comma-separated`):**

1. **R12 refusal message should TEACH the comma-separated format** when the stacked-`#`-lines pattern is two consecutive `# directive:` anchors. Today the message says "one-line max; rationale belongs in the directive doc" -- which is misleading because the right fix is NOT to delete one anchor or move rationale to the directive doc; it is to MERGE the two anchors into one line as `# directive: slug-a, slug-b | # see slug-a.C1, slug-b.C5`. The Path-Forward text should detect "both lines are directive anchors" and suggest the merge format with a worked example. Surfaced twice this session: worker-routing (replaced path-schema anchor on ClaimNextPendingTranscodeJob, losing breadcrumb) and local-staging (attempted to stack on CreateTemporaryFilePath, R12 fired with misleading guidance).

2. **R15 should validate the ACTIVE directive's slug is present in the list**, not just "any slug present." Today the hook's regex `#\s*directive:\s*[a-z0-9-]+` matches the first slug it finds. An operator could leave only a closed-directive anchor on an edited function and the hook would pass -- the active directive's provenance would be missing from the code. Fix: parse `.claude/directive.md` for the active slug, then ensure that slug is one of the comma-separated tokens on the anchor line.

3. **R15 `# see` should validate the criterion ID against the ACTIVE directive doc**. Today the regex `#\s*see\s+[a-z0-9-]+\.(S|W|C|ST)\d+` checks shape only -- a typo like `local-staging.C77` (instead of `C7`) passes regex but doesn't resolve to any real criterion. Fix: when the see anchor names the active directive's slug, parse the directive's `## Acceptance Criteria` section and confirm the cited ID exists. Closed-directive see anchors (e.g. `path.S8` for a closed `path-schema-migration` directive) are unverifiable post-close, so skip validation for those -- only enforce the live one.

**Convention to codify (in `.claude/rules/ceo-mode.md` and/or `.claude/standards/index.md` R15 row):**

```
# directive: slug-a, slug-b, slug-c | # see slug-a.C1, slug-b.C5, slug-c.C7
def SharedHotFunction(...):
```

- One line per function (R12 OK).
- Slugs accumulate in chronological order (oldest -> newest left to right).
- When a directive closes, its slug stays as a historical breadcrumb (preserves "this function was touched by directive X" for future archaeology).
- Active directive (rightmost typically) gates the current edit (R15 enforced via #2 above).
- `# see` carries one ID per slug, comma-separated in matching order.

**Look first:** `.claude/hooks/pre-edit-standards.ps1` -- `Test-R12-CommentVolume` (for sub-item 1: add a "is this a stacked-directive-anchors block?" detector + a path-forward message variant), `Test-R15-DirectiveAnchor` (for sub-items 2 + 3: parse active directive doc for slug + criterion IDs and validate against the anchor line). `.claude/rules/ceo-mode.md` -- add the comma-separated convention example. `.claude/standards/index.md` R15 row -- update description.

**Fix with:** `/n anchor-convention-comma-separated` -- single directive, ~3 hook functions touched, one rule doc updated, one standards row updated. Out of scope: retroactively converting every existing single-anchor function in the codebase (do that opportunistically when each is touched next).

---

### [BUG-0044] CpuAffinityService loses its SystemSettingsRepository wiring on every worker startup -- config knobs silently ignored
**Date:** 2026-06-06 | **Area:** worker-lifecycle

**What breaks:** On every WorkerService startup, `CpuAffinityService._LoadConfig()` raises `AttributeError: 'CpuAffinityService' object has no attribute 'SystemSettingsRepository'`. The exception is caught -- the service then logs `INFO CpuAffinityService initialized` 4 ms later and proceeds to pin P-cores correctly using hardcoded defaults. But the SystemSettings-driven knobs covered by `Features/SystemSettings/SystemSettings.feature.md` criterion 3 (temperature threshold, monitoring interval, cooling wait) never actually take effect on the worker. Whatever is configured in the SystemSettings table is silently overridden.

**Repro:** Restart WorkerService on any host (observed on I9-2024). Within ~15 s of `Worker is Online`:
```sql
SELECT TimeStamp, Message FROM logs
WHERE FunctionName='CpuAffinityService' AND LogLevel='ERROR'
ORDER BY TimeStamp DESC LIMIT 1;
```
returns the AttributeError. Observed timestamps this session: `2026-06-06 22:01:31.540373` on PID 21252.

**Evidence:** Adjacent commit `d0d48b3 fix(worker-init-ordering): move repo field assignments before _RegisterAndLoadWorkerConfig() call` (2026-06-06) fixed the same shape of bug on a different service. The CpuAffinityService init path apparently expects `self.SystemSettingsRepository` to be assigned before `_LoadConfig()` runs, and that assignment is either missing or happening in the wrong order. After the AttributeError, the service still emits `Hybrid=True, Detection=GetSystemCpuSetInformation, P-cores=[0..15], E-cores=[16..31]` and successfully pins both concurrent transcode jobs (30344, 30345) -- so the regression is observability-only at runtime, not functional. The hidden cost is that operator-configured thermal knobs do nothing.

**Violates:** `Features/SystemSettings/SystemSettings.feature.md` criterion 13 (added with this bug). Indirect impact on criterion 3 (configured values are not actually controlling behavior).

**Same shape, sibling case — broaden the fix to cover both:** `StuckJobDetectionService` raises `'StuckJobDetectionService' object has no attribute 'ActiveJobRepository'` on every sweep cycle (observed 26 occurrences in a 35-minute window 2026-06-06 21:10:17 - 21:45:48). Each stuck-job check for a candidate job ID raises and is caught, so the sweep silently no-ops on every candidate. Same root cause class: a repo attribute the service expects is not assigned before the method that reads it runs. Fix scope for `/t BUG-0044` should be "audit every WorkerService-owned service `__init__` for missing repo attributes that `_LoadConfig` / sweep methods rely on," not just CpuAffinityService.

**Look first:**
1. `Services/CpuAffinityService.py` -- `__init__` and `_LoadConfig`. Look for the line that references `self.SystemSettingsRepository`; trace where the attribute is supposed to be assigned and confirm the call ordering matches the d0d48b3 fix pattern.
2. `Services/StuckJobDetectionService.py` -- same audit: `self.ActiveJobRepository` is referenced but never assigned in `__init__` (or assigned after the method that uses it).
3. `WorkerService/Main.py` -- service wiring during worker boot; compare to the sibling fix in d0d48b3 to see which repos are now assigned pre-config-load and which were missed.
4. `Repositories/SystemSettingsRepository.py` + `Repositories/ActiveJobRepository.py` -- confirm the expected interfaces both services are trying to call.

**Flow doc:** `WorkerService/WorkerService.flow.md` covers worker startup including service init -- `/t` should verify the init-ordering contract is captured there before fixing.

**Fix with:** `/t BUG-0044`.

---

### [BUG-0020] Workers must own their processes end-to-end, and `-mv` must only be appended when the output is actually compliant
**Date:** 2026-05-26 | **Area:** worker-lifecycle / file-replacement

**What breaks (two coupled gaps):**

1. **End-to-end ownership.** Workers do not own the lifecycle of the processes they spawn. When a worker's encode finishes but a downstream step (FileReplacement, VMAF dispatch, TFP cleanup) fails or races a sibling sweep (see BUG-0018), the partial artifact survives as a disk and/or DB orphan. The worker that created the artifact is in the best position to clean it up -- it knows its own attempt ID, its own `.inprogress` path, and whether FileReplacement returned success. Today that responsibility is split across multiple services (OrphanCleanupService, scan adoption, manual scripts), creating the BUG-0015 + BUG-0018 lifecycle holes we are currently mitigating by hand.

2. **Premature `-mv` naming.** A file is renamed to `<basename>-mv.mp4` once FFmpeg returns 0 and the FFprobe sanity check passes (`worker-lifecycle.feature.md` criterion 8). But "FFmpeg produced a valid MP4" is not the same as "the output is compliant" -- the rename can land on a file that still has wrong audio, missed loudnorm, oversized output (no-savings refusal), or any other downstream-detectable defect. The next scan / cascade recompute then sees a `-mv.mp4` path and assumes work is done, when in fact the file would still get picked up by a remux / audio / transcode job if it were re-evaluated.

   Stronger rule: `-mv` should only be appended when the output passes the same compliance gate that the cascade uses to decide whether a file needs work. If the output would still get re-queued, the rename is misleading at best, an infinite-loop risk at worst (re-encode produces same non-compliant output, `-mv-mv.mp4` grows another generation each cycle -- see Doctor Who / Love Death Robots ghost-row pattern this session).

**Success criteria for the real fix:**
1. A worker process that produces a `.inprogress` file is responsible for that file's terminal state. On any non-success exit (encode failure, FFprobe failure, FileReplacement failure, kill/crash mid-flow), the same worker deletes the `.inprogress` before releasing the active-job slot. No other service is permitted to delete `.inprogress` files belonging to a live worker.
2. A worker that completes an encode AND succeeds at FileReplacement is responsible for the post-replacement state (TFP cleanup, MediaFile row update). No other service may touch TFP rows for an attempt whose owning worker is alive.
3. The `-mv.mp4` rename happens only after compliance is verified against the same predicate the cascade uses (`NeedsQuick`, `NeedsTranscode`, audio criteria, savings gate). If the candidate output would still be re-queued by the cascade, the worker must not rename and must instead emit a non-Replace disposition with the audit trail naming which compliance check failed.
4. Crash recovery on worker startup (`worker-lifecycle.feature.md` C11-C13) remains the safety net for the case where the worker died before reaching its own cleanup. Crash recovery operates only on rows OWNED by the restarting worker.
5. After the fix, the operator-run scripts (`CleanupSourceFileOrphans.py`, `CleanupStaleInProgressFiles.py`, `CleanupGenerationalGhostRows.py`, `CleanupOrphanMvPairs.py`) should report zero candidates on a fresh fleet pass -- if they find candidates, that is a worker bug, not an expected sweep target.

**Violates:**
- `WorkerService/worker-lifecycle.feature.md` criteria 8-13 (rename / cleanup ownership)
- `Features/FileReplacement/FileReplacement.feature.md` (transition contract)
- The compliance contract enforced by the cascade in `Features/TranscodeQueue/QueueManagementBusinessService._EvaluateCompliance`

**Related:** BUG-0015 (disk orphans), BUG-0016 (DB ghost-row pairs), BUG-0018 (TFP sweep race). All three are downstream symptoms of the ownership gap this bug names. Fix them together as a single "worker process ownership + compliance-gated rename" feature pass.

---

### [BUG-0007] Worker capability toggle does not refresh UI until modal is closed and reopened
**Date:** 2026-05-22 | **Area:** activity-page

**What breaks:** Clicking a capability switch on a worker tile / modal on the `/Activity` page (TranscodeEnabled / QualityTestEnabled / ScanEnabled / RemuxEnabled) hits `POST /api/TeamStatus/Workers/<name>/<Capability>` and the DB row updates correctly, but the on-screen toggle stays in its pre-click position until the operator closes the modal and reopens it (or reloads the page). The handler appears to fire-and-forget without re-rendering from the fresh server payload.

**Repro:** Open `/Activity`. Click a worker to open its modal (or expand its tile). Toggle any capability switch. Without closing the modal, observe the switch position. Query `SELECT TranscodeEnabled FROM Workers WHERE WorkerName=<name>` -- the DB value has flipped, but the UI still shows the old value. Close the modal and reopen it; UI now matches the DB.

**Evidence:** The capability poller is doing its job (`Features/ServiceControl/capability-control-plane.feature.md` criteria 2-4 still hold -- the backend loop starts/stops within 60-90s of the flip). The bug is strictly UI: the post-toggle handler does not call the same render function that initial-load uses, so the modal's component state drifts from server state until next open.

**Violates:** `Features/Activity/activity-dashboard-improvements.feature.md` criterion 18 (added with this bug).

**Look first:** `Templates/Activity.html` -- `ActivityPage.ToggleWorkerCapability` (around the `/api/TeamStatus/Workers/<name>/<Capability>` fetch call). The success branch returns without re-fetching `/api/TeamStatus/Workers` or re-rendering the modal contents. Compare with how the modal is initially populated and pull the same render path into the success handler. Related: `CapabilityRow(...)` builder used in worker tile rendering.

**Fix with:** `/t BUG-0007`.

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

### [BUG-0029] TranscodeAttempts failure rows lack ProfileName -- operator cannot tell what KIND of job failed from the row alone
**Date:** 2026-05-16

**What breaks:** When a remux or transcode job fails early (pre-flight, pre-FFmpeg), the resulting `TranscodeAttempts` row has `Success=False` and `ErrorMessage` populated (loud failure IS in the DB), but `ProfileName=NULL`. The queue row was DELETEd by the failure handler so its `ProcessingMode` context is gone. Operator looking at the row can see "this attempt failed with this error" but not "this was a Remux job" vs "this was an SVT-AV1 transcode." They must join `MediaFiles` via `MediaFileId` to recover even partial context.

Confirmed against attempts 16240-16243 on 2026-05-16: 4 remux jobs failed with `"No active StorageRootResolutions row for (StorageRootId=None, WorkerName='...')"`. All 4 rows have `ProfileName=NULL`. The triggering test-setup script inserted queue rows without `StorageRootId`/`RelativePath` (script bug, not production bug), but the observability gap is real for ANY early failure in production too.

**Note on FilePath=NULL:** That is BY DESIGN per the existing entry "FilePath used as denormalized natural key across 6+ tables" -- FilePath was removed from TranscodeAttempts INSERTs as part of the denormalization cleanup. Operators join via MediaFileId for path. ProfileName is NOT in that denormalization scope; it should be populated.

**Violates:** `Features/TranscodeJob/TranscodeJob.feature.md` criterion 30 (added with this entry). Adjacent to criterion 29 (ErrorMessage content) -- this entry owns the ProfileName slice of the same "diagnose from attempts table alone" contract.

**What "fixed" looks like:** Every `TranscodeAttempts` INSERT in the failure path sets `ProfileName` -- from the queue row's `ProcessingMode='Remux'` literal for remux jobs, from the resolved transcode profile name for transcode jobs -- regardless of how early in the pipeline the failure occurs. Verifiable: trigger a remux job that fails at the `Resolve()` call (e.g. insert a queue row with `StorageRootId=NULL`); query the resulting `TranscodeAttempts` row; observe `ProfileName='Remux'`.

**Look first:** `Features/TranscodeJob/ProcessTranscodeQueueService.py` and `Features/TranscodeJob/ProcessRemuxQueueService.py` -- the failure path in `_ProcessJob` (or equivalent) that creates the TranscodeAttempt row when an exception is caught early. The fix is to populate `ProfileName` from the queue context BEFORE the work begins, not after.

---

### [BUG-0024] FindFuzzyFileMatch is O(N x M) -- reloads + regex-parses all RootFolder rows per new file
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

### [BUG-0024] ScanJobs NewFiles / UpdatedFiles / DeletedFiles counters stay at zero
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

### [BUG-0024] Scan triple-stats DB rows over NFS and runs the existence checks single-threaded
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

### [BUG-0024] Scan progress writer is silent -- ScanJobs counters and CurrentDirectory don't advance mid-walk
**Date:** 2026-05-15

**What breaks:** A scan triggered via `ContinuousScanService` (or manual `POST /api/FileScanning/Scan/Start`) walks the filesystem but does not update `ScanJobs.ProcessedFiles`, `CurrentDirectory`, or `LastUpdated` until the scan ends. Confirmed against I9-2024 on 2026-05-15: M:\ scan #64919 ran 75s and T:\ scan #64920 ran 4+ minutes, both over NFS (89ms/dir for M:\, 18ms/dir for T:\), and both reported `ProcessedFiles=0`, `CurrentDirectory=NULL`, `LastUpdated=StartTime` for the entire run. From the operator's view, a healthy running scan and a hung scan look identical -- the only safety net is `StuckJobDetectionService` at the 15-minute threshold, which is well past the point where a real hang is impacting throughput.

**Violates:** `Features/FileScanning/FileScanning.feature.md` criterion 17 (promoted to [BUG] with this entry). The criterion text now covers two dimensions: cadence (this entry) AND phase visibility. The phase dimension was added on the same date after observing scan #64925's walk finish (`ProcessedFiles=45716`) while `Status` stayed `Running` for the entire metadata-extraction phase that followed -- `PerformScan` folds `ProbeFilesNeedingMetadata` inside its return, so the operator cannot tell "still walking files" from "files done, now FFprobing." Fix candidates: add a `ScanJobs.Phase` column, or split probe out of PerformScan so Status flips to Completed when the walk finishes and a separate row tracks probe.

**What "fixed" looks like:** During an active scan, `ScanJobs.LastUpdated` advances at least every 5 seconds even if no files changed; `CurrentDirectory` reflects the directory currently being walked; `ProcessedFiles` increments per file visited (not just per file inserted/updated). Verifiable: poll `SELECT LastUpdated, CurrentDirectory, ProcessedFiles FROM ScanJobs WHERE Id=<running-id>` every 5s and observe values advance well before `EndTime` is set.

**Look first:** `Features/FileScanning/FileScanningBusinessService.py` -- the scan-walk implementation called from `ContinuousScanService._ExecuteScan` via `StartScanning`. Find where `ProcessedFiles` increments live and confirm whether the path is taken when files are skipped vs only when files are inserted/updated. Likely fix: lift the increment to the `os.walk` yield (not the per-file work branches), and add a heartbeat write of `LastUpdated` + `CurrentDirectory` every N seconds independent of file count.

---

### [BUG-0025] Worker status model is overcomplicated -- Draining state is broken, invisible, and unnecessary
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

### [BUG-0025] Per-capability concurrency is not data-driven -- requires worker restart to take effect
**Date:** 2026-05-13

**What breaks:** Changing `MaxConcurrentTranscodeJobs`, `MaxConcurrentQualityTestJobs`, or `MaxConcurrentRemuxJobs` in the Workers table does not take effect until the worker process is restarted. The concurrency value is read once during `_StartXxxCapability()` and passed to `Run(MaxConcurrentJobs=N)`. The capability polling loop (60s) checks enabled/disabled flags but never re-reads the concurrency columns. This violates the "data-driven" contract: if the max is raised from 1 to 2, the worker should spin up an additional thread on its next poll without restart.

**Violates:** `WorkerService/WorkerService.feature.md` criterion 18 (added with this entry).

**Look first:** `WorkerService/Main.py` `_CapabilityPollingLoop` and `_GetPerCapabilityConcurrency()`. The queue service `Run()` method needs to support dynamic thread-pool resizing, or the capability must be stopped and restarted with the new concurrency value.

---

### [BUG-0030] Status page "Possibly Corrupt" count has no drill-down to see which files are affected
**Date:** 2026-05-13

**What breaks:** The `/Status` page shows "Possibly Corrupt: N" (files with `FFProbeFailureCount >= 3`) as a static number with no click-through. The operator sees there ARE corrupt files but cannot see WHICH ones without navigating to `/Scanning` and opening the Corrupt Files modal. The API endpoint (`GET /api/FileScanning/MediaFiles/Corrupt`) and the detail modal (`Templates/FileScanning.html#CorruptFilesModal`) already exist -- the Status page just doesn't use them.

**Violates:** `Features/FileScanning/FileScanning.feature.md` criterion 19 (added with this entry).

**Look first:** `Templates/Status.html` line 55-61 (the `#LibCorrupt` card -- make it clickable). Reuse the existing `/api/FileScanning/MediaFiles/Corrupt` endpoint. Either inline a modal on the Status page or link to `/Scanning?openCorrupt=true` with auto-open logic.

**Fix with:** `/t`.

---

### [BUG-0031] Next Remux Batch table shows files with no audio stream that silently fail when queued
**Date:** 2026-05-14

**What breaks:** The "Next Remux Batch" card on the ShowSettings page calls `/api/ShowSettings/SmartPopulate` with `Mode='Remux'`. The SmartPopulate query filters by `HasExplicitEnglishAudio IS NULL OR HasExplicitEnglishAudio = true`, but files that have never been probed with audio-aware code have `HasExplicitEnglishAudio = NULL` -- which passes the filter. These video-only files (e.g. Survivor S43E01, S45E02) get displayed as candidates, queued by the user, then fail with "Transcoding failed with return code 4294967274" because the remux command maps `0:a:0` which doesn't exist.

**Violates:** SmartPopulate should exclude files that are known to have zero audio streams (possibly corrupt). No feature doc exists yet for this card's population logic end-to-end.

**Look first:** `Features/TranscodeQueue/QueueManagementBusinessService.py` `SmartPopulateQueue()` WHERE clause; `Features/ShowSettings/remux-populate-card.feature.md`; the `RecommendedMode` materialization in `_EvaluateCompliance()`.

**Fix with:** `/t`.

---

### [BUG-0033] Linux worker deploy flow doc incomplete -- no post-deploy verification, FFmpeg path troubleshooting, or automation parity with Windows
**Date:** 2026-05-13

**What breaks:** `deploy/worker-deploy.flow.md` ends at `docker compose up -d` with only an optional SVT-AV1 encoder check and a Workers table query. Does not document: post-deploy health checks confirming FFmpeg/FFprobe paths resolve inside the container, the full container-started-to-operational sequence, troubleshooting when FFmpeg path resolution fails, or what additional operator actions differ between first deploy vs code-only redeploy. An operator following this doc alone would not know how to diagnose "worker registered but can't find FFmpeg" without reading source code. The Windows deploy path (`deploy/windows-worker.flow.md` + `deploy-windows-worker.py`) has full post-deploy verification and single-command automation; Linux has neither.

**Violates:** `deploy/worker-deploy.feature.md` criterion 20 (added with this entry).

**Look first:** `deploy/worker-deploy.flow.md` -- compare post-deploy coverage to `deploy/windows-worker.flow.md`. The Runtime Pipeline table documents what happens inside the container (steps 8-17) but that knowledge is not surfaced as operator-actionable verification steps. Also consider whether a `deploy-linux-worker.py` (or shell script) should exist to match the Windows automation.

**Fix with:** `/t`.

---

### [BUG-0034] Terminology inconsistency: "quality test" (what) and "VMAF" (how) used interchangeably
**Date:** 2026-05-12

**What breaks:** Code, DB columns, settings keys, log messages, and UI labels mix the policy term ("quality test" -- the decision to accept/requeue/discard a transcode) with the specific implementation term ("VMAF" -- one numeric metric). Examples: `QualityTestEnabled` (policy flag) coexists with `VMAFAutoReplaceMinThreshold` (metric-specific); `QualityTestProgress` table updated by `MonitorVMAFProgress` function; `QualityTestingBusinessService.BuildVMAFCommand`. The mixing bakes the current metric choice into surfaces that should be metric-agnostic and makes a future SSIMU2/PSNR/visual-comparison alternative awkward to add.

**Violates:** `Features/QualityTesting/QualityTesting.feature.md` criterion 11b (added with this entry).

**Look first:** `Features/QualityTesting/QualityTestingBusinessService.py` (mixed naming across method names); `Repositories/DatabaseManager.py` (column names, e.g. `QualityTestRequired` vs `VMAF`); `Templates/*.html` (operator-facing labels); `Core/Logging` strings. Fix needs a documented glossary first, then a careful rename pass; expect schema migrations for any DB columns renamed.

**Fix with:** `/t`.

---

### [BUG-0026 - PARTIAL FIX 2026-05-16] VMAF distribution becomes bimodal on held-frame content -- mean/HMean/P5 unreliable until motion-filter applied
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

### [BUG-0026] `MonitorVMAFProgress` stops emitting updates ~25% before FFmpeg exits
**Date:** 2026-05-10

**What breaks:** On attempt 4396 (Steven Universe S05E14, 16,080 frames), the progress log went silent at frame 12,000 (74.6%) and then `Process completed return code: 0` appeared ~25 seconds later. No exception was thrown; no error in the Logs table for that window. Same monitor failure leaves `QualityTestProgress.Status` stuck at `'Processing'` (or `'Started'` with pre-`RETURNING Id` worker code) and `ProgressPercentage` stuck wherever the last successful poll landed -- so the Activity UI shows a phantom "running" row forever even though the VMAF actually finished.

**Data integrity NOT affected:** the FFmpeg process itself completes normally. `vmaf_output.xml` is well-formed (verified: 1,609 frame elements covering frames 0-16080), `QualityTestResults.VMAFScore` is parsed correctly from the XML, and the disposition function reads the right value. The bug is purely on the operator-visibility side.

**Isolated to the Python wrapper (2026-05-10):** ran the EXACT same FFmpeg command directly in a terminal (no `MonitorVMAFProgress` wrapping). FFmpeg emitted clean progress lines every ~100 frames all the way to frame 16,037 (99.7%) and produced the final `frame=16083` line, with VMAF score 79.603343 -- identical to the worker run. So FFmpeg is not the problem. The defect is entirely in our stderr-consumer thread.

**Violates:** `Features/QualityTesting/QualityTesting.feature.md` criterion 7 ("Quality test progress is reported in real time"). [BUG] criterion 7b added with this entry.

**Look first:** `Features/QualityTesting/QualityTestingBusinessService.py:722` (`MonitorVMAFProgress`) and `ParseFFmpegProgressLine` (~line 803). Most likely: the FFmpeg stderr read loop terminates on a short/empty read that gets interpreted as EOF before FFmpeg has actually written its final stderr buffer. Or: a poll-timeout in the monitor loop is shorter than FFmpeg's final-flush interval. The thread that runs `MonitorVMAFProgress` should keep reading until FFmpeg's `wait()` returns, and should emit a final `UpdateProgressRecord(..., Status='Completed', ProgressPercentage=100)` regardless of whether stderr produced a tail progress line.

**Fix with:** `/t`. Same monitor handles two visible symptoms (no late-stage progress lines, `Status` never advancing to `Completed`); fix once.

---

### [BUG-0035] env-driven config in singleton `__new__` never fires; operator-controllable knobs scattered across env / KV / fossilized rows
**Date:** 2026-05-10

**Today's specific instance (fixed in commit `e291ca4`):** `Core/Logging/LoggingService.py` read its verbosity flags inside `__new__`, but every callsite in the codebase uses the `@classmethod` form (`LoggingService.LogInfo(...)`) without instantiating -- so `__new__` never executed and `_InfoEnabled` stayed `False` regardless of the `MEDIAVORTEX_LOG_INFO` env var. WorkerService produced zero INFO logs anywhere (terminal or DB) for the entire post-disposition feature work. Discovered during the i9 smoke test when no QT-loop diagnostics were visible. The fix moved env reads to class-attribute initialization (runs at import) and split `LogInfo` so the DB audit write is unconditional while only the terminal print stays gated.

**Broader concern (still open):** operator-controllable knobs are spread across three surfaces today -- env vars (`MEDIAVORTEX_LOG_INFO`, `MEDIAVORTEX_DEBUG`, `MEDIAVORTEX_SHARE_MAPPINGS`, `MEDIAVORTEX_DB_*`), legacy `SystemSettings` KV rows (mostly retired by the post-transcode-disposition feature 2026-05-10), and fossilized state rows (`ServiceStatus.QualityTestService`, fixed in commit `afdca4a`). No doc owns the rule "which kind of knob lives where". Future config bugs will keep slipping through this gap. The path-storage entry below retires the share-mapping env-vars; the typed `PostTranscodeGateConfig` retired a slice of legacy KV; what's left needs an explicit policy.

**Look first:** `grep -rn "os.getenv" --include="*.py"` outside DB connection strings and process-local startup constants. Each match is a candidate for the same trap or worse: an env-driven knob the operator can't change without restarting workers, with no audit, no UI, no per-worker visibility, no hot-reload.

**Fix with:** `/n config-plane.feature.md` -- when scoped, define a typed config table for operator knobs and the explicit rule "env vars only for genuinely process-local startup constants". Also audit other singletons (e.g. `WorkerContext`, `FFmpegService` cached path) for the `__new__`-runs-once-on-instantiation trap. Not in scope today; the immediate observability bug is patched.

**Related (also fixed 2026-05-10):** `ServiceStatus.<X>Service.Status` was being read as a live gate inside `ProcessQualityTestQueueService.ProcessQueueLoop` and `ProcessTranscodeQueueService.ProcessQueueLoop` -- the same fossilized-row anti-pattern as the disposition function. Retired in `Features/ServiceControl/capability-control-plane.feature.md`. The single gate for "should this worker run capability X right now?" is now `Workers.<X>Enabled + Workers.Status='Online' + fresh heartbeat`, full stop.

---

### [BUG-0027 - CRITICAL - WORKAROUND IN PLACE] Canonical path storage is OS-coupled
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

### [BUG-0036 - CRITICAL] Profile-less savings estimate uses misleading `SizeMB * 0.5` proxy
**Date:** 2026-05-10
**Affects:** `Features/TranscodeQueue/QueueManagementBusinessService.py:CalculatePriority` (size*0.5 fallback at line 1032), `_EvaluateCompliance` (returns undecidable when profile missing), `EstimateTargetSizeMB` (returns None when profile missing).

When a `MediaFile` has no `AssignedProfile` (and the profile cascade doesn't resolve), every estimate-of-savings path either falls back to `SizeMB * 0.5` (priority calc) or returns "undecidable" (compliance / admission). Result: profile-less files all rank by file size, regardless of compression headroom -- a 5 GB already-AV1 source ranks the same as a 5 GB h264 source. The operator looking at the library to decide which titles to assign profiles to next is sorted by the wrong signal.

**The probed metadata is already there** -- `MediaFiles.Codec`, `OverallBitrate`, `VideoBitrateKbps`, `AudioBitrateKbps`, `DurationMinutes`, `ResolutionCategory` -- nothing reads them for a profile-agnostic compression-potential estimate.

**Why critical:** profile assignment is operator-driven; the operator needs a ranked "next candidates to look at" view that works WITHOUT a profile already being set. Otherwise the assignment-then-queue loop has a chicken-and-egg.

**Violates:** `queue-priority.feature.md` Success Criterion 15 (added with this bug).

**Look first:** `QueueManagementBusinessService.CalculatePriority` (the size*0.5 fallback path) and the `EstimateTargetSizeMB` helper introduced by `marginal-savings-gate.feature.md`. The fix is a profile-agnostic estimator that reads `Codec` + `OverallBitrate` + `ResolutionCategory` and looks up an expected-output-bitrate table (could extend `CrfBitrateEstimates` or add a sibling table -- design choice for the `/t` session).

**Fix with:** `/t`

---

### [BUG-0028] QueueManagementBusinessService.py Cursor-era cleanup backlog
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

### [TECH DEBT BUG-0037] Activity page conflates worker liveness and operational state
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

### [BUG-0025] Worker capability flags not editable from the UI
**Date:** 2026-05-08
**Affects:** WorkerService.feature.md (criterion 14), Activity page, Settings page, `Features/TeamStatus/TeamStatusController.py`

`Workers.TranscodeEnabled`, `Workers.QualityTestEnabled`, `Workers.ScanEnabled` are read by the worker's 60s capability poller, but no UI control writes them -- the operator has to run `UPDATE Workers SET ScanEnabled=true WHERE WorkerName=...` directly via SQL. Same gap as the per-worker Status (Online/Draining/Offline) controls -- but those at least have buttons on the Activity page; capability flags have nothing.

**Look first:** `Features/TeamStatus/TeamStatusController.py` already has `POST /api/TeamStatus/Workers/<name>/Status` for status changes -- mirror that pattern for capability flags. `Templates/Activity.html` worker-row rendering already iterates `/api/TeamStatus/Workers` JSON which includes `TranscodeEnabled`/`QualityTestEnabled`/`ScanEnabled` -- add three toggle controls to each row alongside the existing status buttons.

**Flow doc gap:** `WorkerService.flow.md` covers the read-path (capability polling) but not the write-path. `/t` should extend it with a stage describing the API endpoint contract before the fix.

**Fix with:** `/t` (one new POST endpoint + Activity template change + JS handler; estimate 30-45 min)

---

### [BUG-0038] SystemSettings not normalized; /settings page does not show every row
**Date:** 2026-05-08
**Affects:** SystemSettings.feature.md (criteria 11, 12), `Features/SystemSettings/SystemSettingsRepository.py`, `Templates/Settings.html`

DB state: no UNIQUE on `SettingKey` (duplicates exist: ContinuousScanEnabled x2, ContinuousScanIntervalMinutes x2, ExcludedDirectories x4). `DataType` mixes BOOLEAN/boolean/string/INTEGER/integer/text. List-shaped values stored as CSV (`AllowedExtensions`, `ExcludedDirectories`). Per-file CRF overrides use `CRFOverride_<long_path>` keys instead of a typed override table. Until tonight's UI patch the /settings page only rendered hardcoded known keys (FFmpegPath, MaxCpuThreads, etc.) -- new keys like `DisplayTimezone` were invisible despite existing in the DB. Tonight's commit 505fac2 added a generic "All System Settings" advanced table; criterion 12 is now achievable but the normalization gaps in criterion 11 remain.

**Look first:** `Scripts/SQLScripts/` -- needs a migration that dedupes by `SettingKey` (keep most-recently `LastModified`), adds `UNIQUE(SettingKey)`, and a CHECK constraint on `DataType`. Then move `AllowedExtensions` / `ExcludedDirectories` to child tables and `CRFOverride_*` to a `MediaFileTranscodeOverrides` table keyed on `MediaFileId`. Frontend code that splits CSV in `Settings.html` (search for `.split(',')` near AllowedExtensions/ExcludedDirectories) needs to follow.

**Flow doc gap:** No general flow doc exists for the SystemSettings pipeline (DB row -> Repository -> Controller -> Settings.html UI -> POST round-trip). `/t` should create one before the fix so the dedupe migration and frontend follow-up have a documented contract.

**Fix with:** `/t` (multi-step migration + UI follow-up; estimate 1-2 hours)

---

### [BUG-0040] Second concurrent job shows first job's progress
**Date:** 2026-05-05
**Affects:** TranscodeJob feature -- concurrent job progress tracking
**Criterion violated:** TranscodeJob.feature.md -- each running job must report independent progress

When MaxConcurrentJobs > 1 and a second job starts while the first is still running, the second job displays the same progress percentage and ETA as the first (e.g., both show 20.5% / ETA 01:41:41). Only one FFmpeg process is actually running.

**Look first:** `Features/TranscodeJob/ProcessTranscodeQueueService.py:169` (`GetStatus` returns single `currentProgress`), `GetCurrentTranscodeProgress()` in DatabaseManager (likely returns one row, not per-job), and `VideoTranscodingService.TranscodeVideo` (process spawning).

**Fix with:** `/t`

---

### [BUG-0028] DatabaseManager.py monolith -- dual database access paths
**Date:** 2026-05-07
**Affects:** All features that still import from Repositories/DatabaseManager.py instead of their own Repository
**Criterion violated:** Feature vertical isolation -- each feature should access the database exclusively through its own Repository

`Repositories/DatabaseManager.py` (630+ lines) is the legacy data access layer. Features are supposed to use `Features/<Name>/<Name>Repository.py`, but some still call DatabaseManager directly. This creates two paths to the database: the feature Repository and the legacy monolith. Unclear where new queries should go, and changing a query may need updates in two places.

**Look first:** `Repositories/DatabaseManager.py` -- audit which features import from it. Cross-reference with each `Features/<Name>/<Name>Repository.py` to find overlap.

**Fix with:** `/n` (this is a migration, not a quick fix -- needs audit of all callers first)

---

### [BUG-0028] Feature vertical boundaries do not match governed code
**Date:** 2026-05-07
**Affects:** TranscodeJob.feature.md, FileReplacement.feature.md, Services/CommandBuilderService.py, Services/FFmpegAnalysisService.py, Core/Services/PathTranslationService.py
**Criterion violated:** TranscodeJob.feature.md scope/criteria mismatch; FileReplacement.feature.md cross-feature dependency

TranscodeJob.feature.md declares scope `Features/TranscodeJob/**` + `WorkerService/Main.py`, but its criteria govern behavior in CommandBuilderService (conditional yadif, output mode), FFmpegAnalysisService (per-worker FFprobe), PathTranslationService (multi-prefix translation), and ProcessTranscodeQueueService (VMAF toggle, worker config loading). Separately, FileReplacement depends on MediaProbe for re-probing with no explicit contract.

**Look first:** TranscodeJob.feature.md criteria list -- each criterion that references a file outside the declared scope. `Features/FileReplacement/FileReplacementBusinessService.py` for the MediaProbe call.

**Fix with:** `/n` (architectural boundary redesign -- either expand TranscodeJob scope or extract worker/command-building into separate feature verticals)

---

### [BUG-0027] FilePath used as denormalized natural key across 6+ tables
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

### [BUG-0027] Workers in broken canonical state silently fail scanning; no multi-drive scanning workflow
**Date:** 2026-05-13

**What breaks:** Two related gaps in the scanning pipeline:

(1) **Unknown worker state.** A worker with `ScanEnabled=true` but broken path resolution (missing `WorkerShareMappings` rows, unmapped drives, `PathTranslationService` returning untranslated Windows paths on Linux) silently begins a scan pass. `ContinuousScanService` calls `StartScanning` for each RootFolder without validating that `_ToLocalPath(RootFolderPath)` resolves to an accessible local directory. The result is `os.walk` errors, wrong paths inserted into MediaFiles, or scans that appear to complete with 0 files found. No pre-scan health check, no operator-visible signal that a worker's path state is broken.

(2) **Multi-drive scanning.** RootFolders are seeded under specific drive prefixes (T:\\, M:\\, Z:\\). Adding a new drive to scan requires: manually inserting RootFolders rows, adding `WorkerShareMappings` rows for every worker that can reach the new drive, and restarting workers. There is no UI workflow to register a new drive/share, associate it with workers, and begin scanning. The operator cannot scan from all workers across all drives without manual SQL and restarts.

**Violates:** `Features/FileScanning/FileScanning.feature.md` criteria 20, 21 (added with this entry). `WorkerService/WorkerService.feature.md` criterion 19 (added with this entry).

**Look first:** `Features/FileScanning/ContinuousScanService.py` `_ExecuteScan` -- where pre-scan path validation should fire. `Features/FileScanning/FileScanningBusinessService.py` `_ToLocalPath` -- the translation call that should be validated. `Services/PathTranslationService.py` -- the translation layer. `Templates/Settings.html` or `Templates/FileScanning.html` -- where a "add drive" UI would live. `Repositories/DatabaseManager.py:RegisterWorkerShareMappings` -- the current seeding path for share mappings. Related: `KNOWN-ISSUES.md` canonical path storage entry (the root cause); `path-storage.feature.md` (the long-term fix).

---

## Resolved

### [BUG-0042] Active Jobs list view omits VMAF runs while header badge counts them -- operator misreads as "stuck", kills workers, orphans claimed rows
**Date:** 2026-06-03 -> 2026-06-03 | **Area:** activity-page

**Resolution:** `GetRunningQualityTestProgress` rewritten to drive from `ActiveJobs WHERE ServiceName='QualityTestService'` LEFT JOIN `QualityTestProgress`/`QualityTestingQueue`/`TranscodeAttempts`, returning one row per claim (with NULL progress fields when no `QualityTestProgress` row exists). `Templates/Activity.html` `RenderActiveJobs` renders NULL-progress rows with a yellow stale-claim badge + human-readable claim age via a new `FormatClaimAge` helper. Method migrated from `Repositories/DatabaseManager.py` to `Features/QualityTesting/QualityTestRepository.py` (per `database-manager-aggregates.json`); `QualityTestController.GetQualityTestProgress` now routes through the repository. Live canary against 12 orphan QualityTestService claims: `/api/QualityTesting/Progress` returned `Jobs.Count=12` matching `/api/SQLQueries/GetActiveJobs` `QualityTestService=12`.

**Out of scope (still active):** worker-side claim release on graceful shutdown/SIGTERM, and any orphan-cleanup sweep that automatically releases stale `ActiveJobs` rows. This fix is the display layer only; producer-side gaps are tracked separately.

---