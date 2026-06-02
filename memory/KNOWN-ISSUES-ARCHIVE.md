# Known Issues Archive

Resolved entries moved from KNOWN-ISSUES.md to keep the tracker manageable. Oldest entries first.

---

### [BUG - FIXED 2026-05-13] Remux files discarded as "NoSavings" -- disposition gate ordering bug
**Date:** 2026-05-13 | **Fixed:** 2026-05-13

**What broke:** `PostTranscodeDispositionService._DecideFromInputs` checked `NewSize >= OldSize -> Discard/NoSavings` (Row 2) before `QualityTestRequired=false -> BypassReplace` (Row 3). Remux jobs set `QualityTestRequired=false` but often produce slightly larger outputs (audio re-encode). Result: 679 successful remux attempts got `Disposition='Discard'`, FileReplacement never ran. Disk state: original at `.orig`, good remuxed `.mp4` at source path, DB still pointing to old `.mkv`/`.mp4` path.

**Violates:** `Features/FileReplacement/FileReplacement.feature.md` criterion 10, `transcode-vs-remux-routing.feature.md` criterion 16.

**Fix:** Swapped Row 2 and Row 3 in `_DecideFromInputs` so `QualityTestNotRequired` fires before `NoSavings`. Remux attempts bypass the savings gate entirely. Remediation script `Scripts/SQLScripts/RemediateDiscardedRemuxFiles.py` flipped dispositions and ran `ProcessFileReplacement` for affected rows. ~380 remediated on i9; 113 blocked by stale `.orig` needing manual cleanup; 188 need script run from larry after redeploy.

---

### [BUG - FIXED 2026-05-13] Worker deploy scp copies the entire repo (venv, .git, Tests, etc.) instead of just build inputs
**Date:** 2026-05-12 | **Fixed:** 2026-05-13

**What broke:** Step 1 of `deploy/worker-deploy.flow.md` ran `scp -r /c/Code/MediaVortex/* root@10.0.0.42:/tmp/mediavortex-build/` -- a blind recursive copy that dragged `venv/`, `.git/`, `__pycache__/`, `Tests/`, smoke-test artifacts, screenshots, ad-hoc dumps, and anything else sitting in the working directory across the wire. Wasted bandwidth and time on every deploy and bloated the Docker build context for no payoff.

**Fix:** Created `.deployignore` (exclusion patterns for deploy sync -- additive by default, new files included automatically). Linux deploy: `deploy/SyncSource.py` reads `.deployignore` and uses tar-over-ssh to stream only needed files. Windows deploy: `deploy-windows-worker.py` `StepScpRepo()` now uses `shutil.copytree` with the same `.deployignore` patterns into a temp directory before scp. Flow doc step 1 updated.

**Violates:** `deploy/worker-deploy.feature.md` criterion 19.

---

### [FIXED] QueryDatabase.py sql command silently rolls back writes
**Date:** 2026-05-05 | **Fixed:** 2026-05-05
**Fix:** Added `--commit` flag. Default unchanged (rollback for safety).

### [FIXED] Yadif deinterlacing applied to progressive files
**Date:** 2026-05-05 | **Fixed:** 2026-05-05
**Fix:** Set YadifMode=NULL, YadifParity=NULL on all profiles. CommandBuilder skips yadif when NULL.

### [FIXED] StuckJobDetector breaks distributed transcoding
**Date:** 2026-05-05 | **Fixed:** 2026-05-05
**Fix:** All destructive operations scoped by WorkerName/ClaimedBy. GetActiveJobsByService includes WorkerName. SignalHandler, CrashRecoveryService, QueueManagementService all filter by worker.

### [FIXED] LocalStaging mode crashes workers without StagingDirectory configured
**Date:** 2026-05-07 | **Fixed:** 2026-05-07
**Fix:** All three job types validate `self.OutputDirectory` before entering LocalStaging mode. NULL falls back to InPlace.

### [FIXED] Post-transcode pipeline does not complete (VMAF + file replacement not firing)
**Date:** 2026-05-07 | **Fixed:** 2026-05-07
**Fix:** Removed dead ShouldTestFile(). ProcessTranscodedFile() reads QualityTestRequired from TranscodeAttempt. FileReplacementBusinessService accepts PathTranslation, translates canonical paths before filesystem ops.

### [FIXED] Thread-limiting changes degraded worker transcode performance
**Date:** 2026-05-07 | **Fixed:** 2026-05-07
**Fix:** Reverted `lp=N`, `MEDIAVORTEX_MAX_CPU_THREADS`, Docker `cpus` limit. SVT-AV1 `lp` does not reduce OS thread count; Docker CFS throttling is counterproductive with many idle threads.
**Remaining:** 4 workers at 480p preset 6 still only use ~10% of a 64-CPU system (480p frame size limits SVT-AV1 parallelism -- separate investigation).

### [FIXED] FFmpegService.py cpu_affinity overrides Docker cpuset pinning
**Date:** 2026-05-07 | **Fixed:** 2026-05-07
**Fix:** FFmpegService.py and VideoTranscodingService.py skip affinity calls when `/.dockerenv` exists. Docker cpuset is the sole CPU isolation mechanism in containers.

### [FIXED] Services resolve tool paths from SystemSettings instead of per-worker config
**Date:** 2026-05-08 | **Fixed:** 2026-05-08
**Fix:** WorkerContext singleton. FFmpegService resolves: explicit arg > WorkerContext > cached > SystemSettings. FileReplacementBusinessService auto-reads PathTranslation from WorkerContext.

### [FIXED] Concurrent job progress invisible in UI
**Date:** 2026-05-08 | **Fixed:** 2026-05-08
**Fix:** Removed `INNER JOIN TranscodeQueue` from progress queries. Progress now uses `TranscodeProgress + TranscodeAttempts WHERE Success IS NULL`.
**Note:** Queue rows for concurrent jobs still disappear (cause unknown). Audit trigger `trg_transcodequeue_delete` is in place.

### [BUG - FIXED 2026-05-09] Worker claim path orders by SizeMB, ignoring Priority entirely
**Date:** 2026-05-09
**Fix:** all four claim/peek queries changed to `ORDER BY Priority DESC, DateAdded ASC`. `transcode.flow.md` Stage 2.2 updated to match.

### [BUG - FIXED 2026-05-09] BuildRemuxCommand path-collision destroyed source file
**Date:** 2026-05-09 | **Fixed:** 2026-05-09
**Fix:** `BuildRemuxCommand` ALWAYS uses side-by-side suffix (`_remuxed.mp4`). `_ProcessCompleteFileReplacement` rewritten to rename-then-replace pattern with rollback.

### [BUG - FIXED 2026-05-09] File scanner runs on whichever worker has ScanEnabled, not the one with fastest storage access
**Date:** 2026-05-09 | **Fixed:** 2026-05-09
**Fix:** Added `RootFolders.PreferredWorkerName`, `ScanJobs.WorkerName`, and `SystemSettings('MoveDetectionMaxFiles')`. `ContinuousScanService._ExecuteScan` drops rootfolders pinned to other workers.

### --- swept from KNOWN-ISSUES.md 2026-06-02 ---

### [BUG-0013 - FIXED 2026-05-23] AudioComplete not flipped to true after successful loudnorm pass -- files re-queue forever
**Date:** 2026-05-23 | **Fixed:** 2026-05-23 | resolved: 2026-05-23

**What broke:** `FileReplacementBusinessService._ProcessCompleteFileReplacement` is supposed to call `AudioCompletionService.MarkAudioComplete(MediaFileId)` after a successful replacement whose FFmpeg command contained `loudnorm`. The call was wrapped in try/except + a `DetectNormalizationInCommand(FFmpegCommand)` guard. In practice MarkAudioComplete almost never fired: of 2,234 post-Quick `-mv.mp4` rows with measured loudness, only 9 had AudioComplete=true. Files with off-target LUFS got pulled back into the queue, ran another loudnorm pass, stacked `-mv-mv-mv...` suffixes.

**Root cause:** Typo on `FileReplacementBusinessService.py:214`. The dataclass attribute on `TranscodeAttemptModel` is `FfpmpegCommand` (lowercase `f` second character -- mirrors the misspelled `transcodeattempts.ffpmpegcommand` DB column). The post-flight call used `getattr(transcode_attempt, 'FFpmpegCommand', None)` (uppercase second `F`). `getattr` returned the default `None`, `DetectNormalizationInCommand(None)` returned `False`, and `MarkAudioComplete` was never invoked. The other two "Look first" hypotheses (DELETE+INSERT changing Id; UPDATE rowcount=0) were ruled out by reading the code.

**Fix (shipped 2026-05-23, commit 2560fe9 + pre-rebase rework in commits dac42ba and beyond):** Single-character correction: `'FFpmpegCommand'` -> `'FfpmpegCommand'`. Live-verified via direct `getattr` on a synthetic `TranscodeAttemptModel` -- correct attribute returns the command string, wrong attribute returns None. After the fix, every new post-loudnorm replacement triggers `MarkAudioComplete` and flips the column.

**Recovery for historical broken rows:** Forward-only. The ~2,200 already-broken rows remain `AudioComplete IS NOT TRUE`; operator decision whether to backfill via `AudioCompletionService.MarkAudioComplete` keyed off a query for files with loudnorm history and successful FileReplaced. Tracked via the criterion 25 query that should return 0 for new replacements.

**Verifiable:** `Features/AudioCompletion/audio-completion.feature.md` criterion 25 -- for any successful Remux/Transcode whose FFmpeg command contains `loudnorm` AND was successfully replaced AFTER 2026-05-23, `MediaFiles.AudioComplete=true`.

**Files:** `Features/FileReplacement/FileReplacementBusinessService.py:214`. Commit 2560fe9 (and follow-ups in the same session).

---

### [BUG-0008 - FIXED 2026-05-22] I9 intermittent write failures to NFS mount -- ffmpeg output-open returns EINVAL
**Date:** 2026-05-22 | **Fixed:** 2026-05-22 | resolved: 2026-05-22

**What broke:** On I9-2024, ffmpeg jobs (transcode + Quick/Remux) failed intermittently with exit code 4294967274 (= -22 = `EINVAL`) at the output-file `open()` step, before any encode work. Hit both audio-reencode and stream-copy commands. Linux containers (larry, wakko, dot) writing to the SAME porky NFS export had zero failures across the same load. Defect was host-local to I9.

**Investigation log:** `deploy/BUG-0008-i9-nfs-einval.troubleshooting.md` -- captures every ruled-out hypothesis with evidence (soft-mount, concurrency, multi-NIC routing, drive-letter session unbinding, AV filter drivers, shell=True wrapper, NFSv4 negotiation). All client-side workarounds failed; UNC paths failed the same way as drive-letter paths, proving the Microsoft NFS client itself was the unstable layer.

**Root cause:** The Microsoft NFS client (Windows 11 built-in) returns intermittent `ERROR_INVALID_PARAMETER` on `CreateFile()` against a Linux kernel nfsd. The bug is in the client implementation; Linux NFS clients against the same exports are stable. The infrastructure repo's `brain-porky-media-migration.md` originally planned for Windows workers to remain on SMB (SMB-to-brain -> SMB-to-porky), but the SMB-on-porky setup was never stood up and I9 was inadvertently moved to NFS. This was the first time the MS-NFS-client + Linux-nfsd combination had been exercised in this homelab; the fragility was latent until then.

**Fix (shipped 2026-05-22, commit b02a34b):** Cutover Windows access from NFS to SMB. Stood up Samba on porky for the TV share with a `mediavortex` user; used Synology native SMB for Movies + XXX (the cleaner option since Synology's SMB stack is its primary protocol). Updated `StorageRootResolutions` for I9-2024 to SMB UNCs. The worker bypasses the Microsoft NFS client entirely. Linux workers stayed on NFS unchanged.

**Architecture changes alongside the cutover:**
- Worker became a strict reader on `StorageRootResolutions` / `WorkerShareMappings`. `RegisterStorageRootResolutionsFromCanonical` and the `MEDIAVORTEX_SHARE_MAPPINGS` env-var branch deleted; missing SRR rows hard-fail with a remediation pointer.
- Atomic claim queries (`ClaimNextPendingTranscodeJob`, `ClaimNextPendingRemuxJob`) gate on `Workers.Status='Online' AND <Cap>Enabled=TRUE` via an EXISTS subquery -- Pause and capability flips take effect on the very next claim attempt, no polling-cache lag.
- `PrivateNormalizePathToFilesystemCase` translates canonical -> local via `PathTranslationService` before filesystem probes, eliminating the "Path does not exist, cannot normalize: T:\..." warnings.
- `_VerifyRequiredPaths` reads `StorageRootResolutions.AbsolutePath` (works uniformly for POSIX, drive letter, or UNC) instead of `LEFT(FilePath,2)` drive-letter scan.
- `QueryDatabase.py` print_table no longer truncates output.

**Verified:** 329-for-329 success on I9-2024 since cutover, zero `4294967274` EINVAL failures. The original verification criterion (100 consecutive without EINVAL) was overshot by 3.3x.

**New artifacts:**
- `Scripts/SQLScripts/SetWindowsWorkerUncPaths.py` -- sole writer for SRR / WSM; `UNC_PREFIXES` dict is the only place share literals live in code.
- `WorkerService/windows-unc-path-translation.feature.md` -- feature spec for the cutover.
- `deploy/BUG-0008-i9-nfs-einval.troubleshooting.md` -- full investigation log.

**Vault entries created:** `homelab/porky/cifs/mediavortex`, `homelab/synology/cifs/jallen11` (per `skills/infra-vault/SKILL.md` naming convention).

**Files:** `Repositories/DatabaseManager.py`, `WorkerService/Main.py`, `Core/Services/PathTranslationService.py`, `StartWorker.py`, `Scripts/SQLScripts/SetWindowsWorkerUncPaths.py`, `Scripts/SQLScripts/QueryDatabase.py`, `WorkerService/windows-unc-path-translation.feature.md`, `deploy/BUG-0008-i9-nfs-einval.troubleshooting.md`, `deploy/worker-deploy.feature.md` criterion 13, `deploy/worker-deploy-windows.flow.md`. Commit b02a34b.

---

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

