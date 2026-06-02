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


### --- swept from KNOWN-ISSUES.md (RESOLVED-misfiled-under-Active) 2026-06-02 ---
### [BUG-0023 - RESOLVED 2026-05-31] Legacy ProfileManagementModal silently corrupted NVENC profiles' Codec column
**Date:** 2026-05-31 | **Area:** ui / profiles | **Closed by:** `directives/closed/2026-05-31-unify-profile-editor.md`

**The footgun:** Opening an NVENC profile (Codec='av1_nvenc') in the legacy `ProfileManagementModal` Edit dialog silently coerced the Codec dropdown to `libsvtav1`. The dropdown's `<select>` options were `libsvtav1 / libx265 / libx264 / libvpx-vp9` -- no `av1_nvenc` option existed -- so `$('#ProfileCodec').val('av1_nvenc')` silently failed and the dropdown defaulted to the first available option (`libsvtav1`). The operator saw "AV1 (libsvtav1)" in the dropdown without realizing it was wrong. On Save, the PUT `/api/profiles/<id>` endpoint posted `Codec='libsvtav1'`, overwriting the DB column. The NVENC profile then routed to `libsvtav1` encoding instead of NVENC -- breaking the queue's worker-capability filter (`Workers.nvenccapable`) and the CommandBuilder NVENC branch.

**Caught:** during `unify-profile-editor` close-out discussion (operator asked "is the NVENC codec set in the DB but just not exposed in the GUI?"). The legacy modal's Codec dropdown HTML (`Templates/Settings.html:560-565` before retirement) had only `libsvtav1` as the enabled option, with three other codecs marked `disabled` as "Not Implemented Yet" placeholders -- but `av1_nvenc` was never in the list at all even after the NVENC adoption shipped.

**Resolution:** Legacy `ProfileManagementModal` removed entirely; the cogs/knob modal is now the canonical Profile + ProfileThresholds editor. Codec dropdown in the unified editor includes `av1_nvenc` + `libsvtav1`. PATCH `/api/profiles/<id>/knobs` allowlists every editable column. Verified: opening `NVENC AV1 P7 CANARY VBR -720p` in the new editor shows Codec=`av1_nvenc` correctly; saving any unrelated field leaves Codec='av1_nvenc' unchanged.

**Historical data:** if any NVENC profile in the wild had its Codec silently overwritten to `libsvtav1` before this fix, audit via `SELECT ProfileName, Codec, UseNvidiaHardware FROM Profiles WHERE UseNvidiaHardware = 1 AND Codec != 'av1_nvenc';` -- any rows returned are corruption survivors that need manual `UPDATE Profiles SET Codec='av1_nvenc'`.

---

### [BUG-0022 - RESOLVED 2026-05-29] VMAF not working properly; transcoding using NVIDIA (NVENC) enhancements
**Date:** 2026-05-28 | **Area:** quality-testing / nvenc-evaluation

**Resolution 2026-05-29 (VMAF measurement arm):** Three production-VMAF fixes in `Features/QualityTesting/QualityTestingBusinessService.BuildVMAFCommand`:

1. **Input order corrected.** Production had `-i original -i transcoded` with the filter mapping `[0:v]->[dist]` and `[1:v]->[ref]`. libvmaf reads positionally as (distorted, reference), so production was treating the ORIGINAL as the distorted input and the TRANSCODED as the reference -- backwards. VMAF model is asymmetric; the wrong direction produces content-dependent inverted scores. This bug pre-dated the chain rewrite and is the most likely root cause of historically inconsistent VMAF readings. Found during the 2026-05-29 canary on Cheers S03E03 where the corrected chain initially produced VMAF=67.40 (wrong direction). Fixed by swapping the ffmpeg input order; the filter pad labels stay the same.

2. **Chain modernized** to match the production-decision shootout: PTS reset on both inputs (kills container timestamp drift causing frame-alignment slippage), unified scale-to-target with lanczos + `in_range=auto:out_range=tv` color-range pinning (NVENC outputs limited range -- mismatches collapsed scores), 10-bit precision (`yuv420p10le`), libvmaf with explicit `log_fmt=xml` + `n_threads=4`.

3. **`n_subsample=10` removed.** Old chain scored only every 10th frame, which made the held-frame motion-filter unreliable (integer_motion between non-consecutive frames is meaningless) and lost tail-of-distribution detail that the percentile metrics (P1/P5/P10/P25) depend on.

**Historical impact:** `TranscodeAttempts.VMAF` values from before 2026-05-29 are inverted-direction measurements. They remain valid for relative comparisons within the same content/profile pair (the bug was systematic) but the absolute number is not what libvmaf normally reports. Auto-replace thresholds (`VMAFAutoReplaceMinThreshold=88`) were calibrated against inverted readings and may need re-tuning -- track that as a separate follow-up once enough new (correct-direction) scores accumulate.

Motion-filter threshold recalibration (the `integer_motion < 0.5` cutoff over-triggers on plain low-motion live action -- 2026-05-28 shootout data shows 32-60% MotionZeroFraction across sitcom + drama, not just held-frame animation as the 15% trigger was tuned for) deferred to a separate follow-up; needs per-frame XML data captured under the new chain to calibrate, and the three fixes above already address the user-reported "wildly inconsistent" VMAF symptom independently.

**Resolution 2026-05-28 (NVENC adoption arm):** NVENC AV1 evaluation complete. Shootout matrix tested SVT-AV1 P6 FG8 CRF26 (production-dominant) vs 7 NVENC variants across 4 content types (anime held-frame, anime action, sitcom, drama). Winner: NVENC av1_nvenc p7 tune=uhq multipass=fullres rc=vbr+cq aq-strength=15 rc-lookahead=32 bf=7 (`nv_cq32_sink` in matrix). Median: -14% size vs SVT reference at -0.47 VMAF Mean, ~1.6x faster wall encode. Within the operator's "closish quality at sameish size" criterion on every source.

Production wiring shipped: `Features/Profiles/nvenc-profiles.feature.md`. Two new Profiles in DB (`NVENC AV1 P7 UHQ CQ32 -480p`, `NVENC AV1 P7 UHQ CQ32 -720p`); CommandBuilder NVENC branch updated to emit the full quality knob set + p010le pix_fmt; `Workers.nvenccapable` column added with I9-2024 marked capable; queue claim filter routes NVENC jobs to capable workers only.

**Still open (VMAF measurement arm):** The "VMAF not working properly" framing remains a latent concern -- the shootout used the production-equivalent motion-filter pooling and saw motion-filter trigger on live-action sitcom and drama (not just held-frame animation, where it was designed to). The 15% motion-zero threshold may be miscalibrated for non-anime content. Track that as a separate VMAF measurement bug if it surfaces in production VMAF scores diverging from operator perception. Not gating NVENC rollout -- the shootout's relative comparison is valid even if absolute VMAF numbers are content-quirky.

**Original report below.**



**Reported as (verbatim):** "vmaf not working properly and transcoding using nvidia enhancements."

**Context not yet investigated.** Captured at record time; do not infer beyond this until `/t BUG-0022`.

**Repro:** TBD -- operator to narrow during `/t`. Two distinct concerns conflated in the report:
1. VMAF measurement / scoring is producing wrong or unexpected results in some scenario (encoder choice? hardware path? content type? threshold gate?).
2. Transcoding is using or should use NVIDIA hardware enhancements (NVENC encoder, CUDA scaling, NPP filters, hardware decode). MediaVortex's documented encoder is `libsvtav1` (CPU). It is unclear whether (a) NVENC was switched in somewhere and is producing the VMAF issue, (b) NVENC is being evaluated as an upgrade path and the comparison harness is producing the VMAF issue, or (c) the two are independent and should be split into separate bugs.

**Evidence:**
- Untracked PowerShell harnesses live under `Scripts/CodecAnalysis/`: `NvidiaVariableRunsAddScale.ps1` (on disk 2026-05-28); git status also shows `NvidiaVariableRuns.ps1` and `Nvidia full quality vs MV.ps1` as untracked (not present on disk at record time -- may have been deleted, renamed, or live elsewhere). These suggest an in-flight NVENC vs MediaVortex (libsvtav1) comparison effort.
- Existing related (NOT this bug, do not auto-merge):
  - BUG (line 668, PARTIAL FIX 2026-05-16): held-frame content bimodal VMAF -- motion-filtered pooling shipped, residual threshold-gate gap.
  - BUG (line 725): MonitorVMAFProgress stops emitting updates ~25% before FFmpeg exits -- cosmetic, score integrity OK.
  - BUG (line 832, RESOLVED 2026-05-16): QualityTestEnabled flip mid-run missed by transcode producer.

**Look first:**
- `Scripts/CodecAnalysis/NvidiaVariableRunsAddScale.ps1` -- recent harness, likely the source of the "not working properly" observation.
- `Features/QualityTesting/QualityTestingBusinessService.py` `BuildVMAFCommand` / `ParseVMAFMetrics` -- VMAF filter chain and metric pooling. Confirm the chain matches reference parameters when source vs encoded differ in pixel format / color range / scale (NVENC commonly emits limited-range NV12; libvmaf wants matched ranges or the score collapses).
- `Features/CommandBuilder/CommandBuilderService.py` -- confirm whether any NVENC path exists; if not, the "nvidia enhancements" arm is an open question, not a current code path.
- `Models/CommandBuilder.py` BuildAudioFilters / BuildVideoFilters -- scale/format insertion that NVENC vs CPU paths would differ on.

**Violates:** `Features/QualityTesting/QualityTesting.feature.md` criterion 2 (VMAF produces a meaningful 0-100 score) and `Features/TranscodeJob/TranscodeJob.feature.md` (encoder selection contract). [BUG-0022] criterion added to both.

**Flow doc:** Affected pipeline is the post-transcode quality test path in `Features/QualityTesting/QualityTesting.feature.md` -- no dedicated `*.flow.md` exists for the VMAF dispatch + scoring pipeline. `/t` should create it before fixing.

**Fix with:** `/t BUG-0022` -- first action is to ask the operator to split (a) the VMAF measurement failure and (b) the NVENC evaluation/adoption into separate bugs if they are independent, then proceed.

**Update 2026-05-28 (NVENC arm):** Test harness built and ready to run on I9. See `Scripts/Smoke/EncoderShootout.feature.md`. Matrix: 6 sources (Black Butler S01E05, One Piece S14E03, New Girl S01E03 + S07E01, Curb Your Enthusiasm S04E08, Cheers S01E07) x 4 variants (SVT-AV1 P6 FG8 CRF26 production-reference + NVENC av1_nvenc p7 hq fullres at CQ 28/32/36), all encoded at 854x480 to match the production-dominant >480p downscale path. Run: `py Scripts/Smoke/EncoderShootout.py --matrix Scripts/Smoke/NvencVsSvtAv1.matrix.json`. VMAF chain uses the production motion-filter pooling (held-frame fix), 10-bit precision, PTS+color-range alignment. Operator decision rule: NVENC wins if any CQ rung lands within 2.0 VMAF Mean points of SVT AND within 15% of SVT size, OR if speed savings outweigh a larger gap. Result sidecar will be `Scripts/Smoke/NvencVsSvtAv1-1080pTo480p-2026-05-28.shootout.json`.

---

### [BUG-0021 - RESOLVED 2026-05-27] Codec/AudioCodec/AudioComplete stale on MediaFiles row after seemingly successful replacement
**Date:** 2026-05-27 | **Area:** file-replacement / mediafile-persistence

**Resolution 2026-05-27:** Closed by `.claude/directive.md` (clean-happy-path-transcode) criterion 2, verified live on canary 3 (MediaFile 6490, Steven Universe S01E37). The criterion requires every probe-populated MediaFiles column to match a fresh re-probe of the new file on disk -- including `Codec`, `AudioCodec`, `AudioComplete`, `AudioNormalizationMode`. Verified end-to-end: all columns refreshed, no orphan state.

The originally-cited evidence file (MediaFile 683466) was the residue of a 2026-05-22 attempt (TranscodeAttempt 22587 on dot-worker-4, before any of this directive's fixes shipped). Its stale row is historical, not from a current code defect. Today's code (commits d93c485 + 464d9f7 + supporting) does not reproduce the failure on healthy transcodes.

The originally-feared "re-probe miss + FileReplaced=true commits anyway" failure path was not observed and is exotic by nature -- on a just-finished FFmpeg encode that emitted a valid output, FFprobe failure requires either path-translation bug, filesystem-mount transient (more likely on Linux NFS clients), or codec/container Jellyfin can't read (basically never for AV1/HEVC/H264 in mp4/mkv). If it surfaces, file a new bug with the worker's `_UpdateMediaFilesAfterReplacement` warning line as evidence.

**What was originally reported (incorrect diagnosis -- preserved for context):** `Features/FileReplacement/FileReplacementBusinessService._UpdateMediaFilesAfterReplacement` assigns `Codec`, `AudioCodec`, and `AudioComplete` on the MediaFile model from the post-replacement FFprobe pass and calls `SaveMediaFile`. `Repositories/DatabaseManager.SaveMediaFile` does NOT include these three columns in its UPDATE statement, so they are silently dropped. (Audit on 2026-05-27 showed Codec and AudioCodec ARE in both UPDATE branches; the original diagnosis was wrong on those two columns. Only AudioNormalizationMode was missing -- separately resolved as BUG-0019.) Operator-visible Library Compliance tallies (e.g. AudioFix routing decisions, codec-distribution counts) misreport the affected files as still being the source codec until the next probe pass refreshes them.

**Same shape as BUG-0017** (resolved 2026-05-25 by adding 6 columns: FileSize, LastModifiedDate, ResolutionCategory, IsInterlaced, AudioLanguages, HasExplicitEnglishAudio). The pattern is: hand-maintained UPDATE column list in SaveMediaFile drifts out of sync with model attributes assigned by callers; any column not in the list is silently dropped. The BUG-0017 fix patched 6 columns but did not address the architectural cause -- so the next column class (Codec/AudioCodec/AudioComplete) repeats the failure.

**Repro:** Queue any `-mv.mp4` HEVC source for re-encode through the compliance-gated-rename slice (commit d26f77e or later). After successful encode + replacement (FileReplaced=true, file visibly AV1 on disk):
```sql
SELECT Id, FilePath, Codec, AudioCodec, AudioComplete, LastScannedDate FROM MediaFiles WHERE Id=<id>;
```
Codec returns the pre-replacement value (e.g. `'hevc'` for an AV1 file on disk); AudioCodec returns the pre-replacement value; AudioComplete returns NULL.

**Evidence:** Canary 3 of compliance-gated-rename slice on 2026-05-27. MediaFile 683466 (So I'm a Spider S01E16): pre-encode HEVC/AAC, post-encode visually verified 720p AV1 with normalized audio, FileReplaced=true, but DB row shows Codec='hevc', AudioCodec='aac', AudioComplete=NULL, LastScannedDate from 2026-05-23.

**Workaround:** Trigger a library-wide reprobe via `UPDATE MediaFiles SET NeedsReprobe=TRUE` then run the probe pass. Resets all stale columns from on-disk FFprobe.

**Look first:** `Repositories/DatabaseManager.SaveMediaFile` UPDATE SET clause. Confirm Codec/AudioCodec/AudioComplete absent. Immediate patch: add the three columns (matching the BUG-0017 pattern -- use COALESCE on the UPDATE so legacy SELECT paths that don't load these columns can't blank existing values). Then audit every other column on MediaFiles model against the UPDATE list -- there may be more dropped columns lurking that nobody has hit yet.

**Real fix is architectural:** new feature `mediafile-persistence-no-drift` -- replace the hand-maintained UPDATE column list with one of: (1) generate UPDATE from model fields (`dataclasses.fields()` or pydantic), (2) single canonical `MEDIAFILE_PERSISTENT_COLUMNS` constant referenced by model + repository + migration, (3) runtime drift check at startup that ERRORs when model attributes don't match UPDATE list. Pick one and prevent the recurring class.

**Violates:** `Features/FileReplacement/FileReplacement.feature.md` criterion 3 ("After replacement, the new file is re-probed and all MediaFiles columns are updated with fresh metadata") and criterion 14 (added with this bug).

**Fix with:** `/t BUG-0021` for the immediate patch (3 columns). Architectural fix lives in the new `mediafile-persistence-no-drift` feature.

---

### [BUG-0019 - RESOLVED 2026-05-27] MediaFiles.AudioNormalizationMode stays NULL after encode that ran loudnorm
**Date:** 2026-05-25 | **Area:** linear-loudnorm / file-replacement

**Resolution 2026-05-27:** Two-gap fix.
1. `Repositories/DatabaseManager.SaveMediaFile` did not list `AudioNormalizationMode` in either UPDATE statement (duplicate-path or by-Id) or in the INSERT. Added in all three with COALESCE protection on the UPDATEs so partial-load callers cannot blank an existing mode.
2. `Features/FileReplacement/FileReplacementBusinessService._UpdateMediaFilesAfterReplacement` did not derive the mode from the just-run FFmpeg command. Now accepts an optional `FFmpegCommand` parameter and calls `AudioCompletionService.DetectNormalizationMode` (new helper) to set `media_file.AudioNormalizationMode` before `SaveMediaFile`. `'linear'` if the command contains `linear=true`, `'dynamic'` if it contains `loudnorm` without `linear=true`, `None` otherwise. `_ProcessCompleteFileReplacement` passes its own `FFmpegCommand` through. `FinalizePartialReplacement` (crash-recovery path) leaves `FFmpegCommand=None`; the column stays untouched since crash-recovery doesn't know which mode ran.

Round-trip and COALESCE protection verified via `Tests/Contract/TestMediaFilePersistence.py` (covers directive `.claude/directive.md` criterion 2). Next live transcode populates the column.

**Original report below.**

**What breaks:** Per `linear-loudnorm.feature.md` criterion 14 the column should record `'linear' | 'dynamic' | NULL` based on the mode that BuildAudioFilters selected. Doctor Who S06E04 canary v5 ran with predicted_peak=+2.8 dBTP (forcing dynamic mode) and the emitted ffmpeg command confirms the dynamic-mode loudnorm+alimiter chain ran. Post-replacement `MediaFiles.AudioNormalizationMode = NULL`. Pipeline impact: none -- the column is only read by the Library Compliance tally SQL (linear/dynamic counts) for operator visibility. Files transcode, replace, and serve correctly.

**Repro:** queue any dynamic-mode-eligible source (`SourceIntegratedLufs <= -28 AND SourceTruePeakDbtp >= -3`) through the Transcode path; after FileReplacement, `SELECT AudioNormalizationMode FROM MediaFiles WHERE Id = ...` returns NULL despite the TranscodeAttempts.FfpmpegCommand showing the loudnorm filter ran.

**Look first:** `Models/CommandBuilder.BuildAudioFilters` returns the filter string but does not write the mode anywhere. Either (a) BuildAudioFilters needs to write `AudioNormalizationMode` directly when it picks linear vs dynamic, or (b) FileReplacement / disposition needs to parse the recorded FfpmpegCommand and derive the mode at replacement time. Owner contract per linear-loudnorm.feature.md C14.

**Violates:** `Features/LoudnessAnalysis/linear-loudnorm.feature.md` criterion 14 (mode tally column populated for every encode that ran loudnorm).

---

### [BUG-0017 - RESOLVED 2026-05-25] MediaFiles.FileSize NULL on most rows despite recent transcodes that should populate it
**Date:** 2026-05-24 | **Area:** file-replacement

**Resolution 2026-05-25:** Root cause confirmed -- `Repositories/DatabaseManager.SaveMediaFile` UPDATE and INSERT both omitted `FileSize` from their column lists. Same omission silently dropped 5 sibling columns assigned by `FileReplacementBusinessService._UpdateMediaFilesAfterReplacement`: `LastModifiedDate`, `ResolutionCategory`, `IsInterlaced`, `AudioLanguages`, `HasExplicitEnglishAudio`. Fix adds all 6 columns to both UPDATE branches and the INSERT. UPDATEs use `COALESCE(%s, ColumnName)` so callers that fetched a model via legacy SELECT paths (which still don't load these columns) cannot blank existing DB values. INSERT is direct since new rows have no prior state. Round-trip verified on Id=7323.

**Original report below.**

**What breaks:** `FileReplacementBusinessService._UpdateMediaFilesAfterReplacement` sets `media_file.FileSize = os.path.getsize(LocalNewFilePath)` and then calls `SaveMediaFile`. Per `Repositories/DatabaseManager.SaveMediaFile`, the column SHOULD be persisted. In practice many MediaFiles rows have `FileSize IS NULL` even when their corresponding TranscodeAttempts shows a successful post-flight replacement. The downstream impact: queue inserts that read `MediaFiles.FileSize` and propagate it to `TranscodeQueue.SizeBytes` and then `TranscodeAttempts.OldSizeBytes` end up with 0 -- the post-transcode defense-in-depth check at `FileReplacementBusinessService.py:196-208` then refuses with `NewSize >= OldSize=0`, even though a successful encode just happened.

**Repro:**
1. `SELECT Id, FilePath, FileSize, SizeMB FROM MediaFiles WHERE Id = 26621` -- observe `FileSize=None` despite SizeMB being populated and a successful TranscodeAttempts row existing for this file with recent FileReplacedDate.
2. Broader: `SELECT COUNT(*) FROM MediaFiles WHERE FileSize IS NULL` -- expect a large fraction of the library.

**Evidence:**
- Direct observation via pipeline-test-harness step 10 against MediaFile 26621: SaveMediaFile called with FileSize set, post-call DB row still shows NULL.
- Triggered the defense-in-depth refusal in the second harness test case, blocking the Transcode step.

**Look first:** `Repositories/DatabaseManager.SaveMediaFile` UPDATE SET clause -- is `FileSize` actually in the column list, or is it being silently dropped? Compare to the INSERT path. If the column is in both paths, check whether some caller is overwriting with None on a later UPDATE.

---

### [BUG-0014 - RESOLVED 2026-05-26] Linear-loudnorm overshoots TargetTruePeak in dynamic-mode fallback
**Date:** 2026-05-24 | **Area:** linear-loudnorm

**Resolution 2026-05-26 (v2, verified on real-world content):** `Models/CommandBuilder.BuildAudioFilters` appends `,alimiter=limit=<linear>:attack=1:level=0` after `loudnorm=...` ONLY when dynamic mode fires (linear mode untouched -- it hits TP precisely on its own). The alimiter ceiling is set **2 dB under** `TargetTruePeak` (default -2 -> alimiter at -4 dBFS sample-peak, linear amplitude 0.6310) and `attack=1` (1ms, down from the 5ms default) so transient peaks get clamped before they leak through the attack window. `level=0` disables alimiter's auto-leveling so loudnorm's integrated loudness target survives unchanged. The chain is transparent on quiet content (no clamping below the ceiling).

**v1 (-3 dBFS / default 5ms attack) failed in production:** Doctor Who S06E04 canary 2026-05-25 18:42 measured **-1.6 dBTP** post-encode -- alimiter clamped sample peaks but the 5ms attack let individual transients ride 1.4 dB above the threshold into the inter-sample-peak region. v2 tightens both limit and attack.

**v2 verification (2026-05-26 04:13):** Doctor Who S03E10 (Blink) Bluray-720p, source measured I=-28.0 LUFS, TP=-0.8 dBTP, predicted_peak=+4.2 dBTP -> dynamic mode fires. Post-encode ebur128: I=-22.3 LUFS, **Peak=-2.6 dBFS**. Criterion 26 passes with 0.6 dB margin. Audio path command captured in TranscodeAttempts.FfpmpegCommand: `loudnorm=I=-23:LRA=...:TP=-2:measured_I=-28.00:...,alimiter=limit=0.6310:attack=1:level=0`.

**Original report below.**

**What breaks:** Per `linear-loudnorm.feature.md` criterion 12 the loudnorm filter is supposed to honor `TargetTruePeak` (default -2 dBTP) in both linear and dynamic modes. In practice, dynamic-mode fallback (triggered when predicted_peak > TP at gate time -- criterion 10) produces output that exceeds the TP target by 1-3 dBTP. FFmpeg loudnorm's internal limiter is not enforcing TP=-2 reliably; output peak can ride well above 0 dBTP, causing audible clipping on downstream playback.

**Repro:**
1. Pick a source file with `SourceTruePeakDbtp >= -3` AND `SourceIntegratedLufs <= -28` (hot peaks + quiet integrated -- forces dynamic mode at the gate per criterion 10).
2. Run Quick Fix via the pipeline-test-harness or by re-queueing.
3. `ffmpeg -i <output> -af ebur128=peak=true -f null -` -- inspect the Summary `Peak:` line. Expected: <= -2 dBTP. Actual: ~+1 to +2 dBTP.

**Evidence:**
- Pipeline-test-harness step 10 against MediaFile 683333 (HIMYM S06E08, source was a `-mv.mp4` with hot peaks): post-Quick-Fix output measured **+1.70 dBTP**, far above the -2 dBTP ceiling.

**Look first:**
1. The `loudnorm` command emitted by `Models/CommandBuilder.BuildAudioFilters` for the dynamic-mode branch -- does it omit `linear=true` correctly? Capture from a recent TranscodeAttempts.FFpmpegCommand.
2. FFmpeg/libavfilter version behavior -- loudnorm's dynamic-mode limiter has had bugs in older builds. Verify `ffmpeg -version` matches a known-good build.
3. The `TP` parameter passed to loudnorm: confirm it's `-2` (not `-2.0` rejected) and that nothing later in the filter chain (no `acompressor` post-removal, but check) is raising the level.

**Possible fix paths:**
- Append a downstream true-peak limiter (`alimiter=limit=-2dB`) when dynamic mode fires
- Tighten the gate predicate to refuse the encode rather than fall back to dynamic when overshoot is likely > N dBTP
- Use a lower `TargetLoudness` for ungainable files (compute the max integrated that keeps peak <= -2)

**Violates:** `Features/LoudnessAnalysis/linear-loudnorm.feature.md` criterion 26 (output TP at or below TargetTruePeak).

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

### [BUG - FIXED 2026-05-21] Bare-metal Linux host bootstrap not codified -- manual SSH steps required before deploy-linux-worker.py
**Date:** 2026-05-16 (opened); 2026-05-21 (closed)

**Resolution:** `infrastructure/terraform/mediavortex-bare-metal-bootstrap.py` lands the canonical bootstrap. Reads `fstab_mounts` from `infrastructure/terraform/inventory.toml` (new field on `vm_type = "bare-metal"` entries), idempotently installs `nfs-common` + Docker CE, applies a managed block in `/etc/fstab`, creates `/opt/mediavortex` + every mountpoint, runs `mount -a`. New bare-metal bringup: `py infrastructure/terraform/mediavortex-bare-metal-bootstrap.py --host <friendly>` then `py deploy/deploy-linux-worker.py <friendly>`. Verifiable: re-running the bootstrap on a clean host is a no-op (managed-block sed delete + re-append yields identical fstab; package + dir checks short-circuit). See `infrastructure/docs/features/linux-worker-deploy.md` criterion 10 (also marked resolved 2026-05-21) for the host-side acceptance test. This entry should be moved to the Resolved section with a `BUG-NNNN` ID on the next housekeeping pass.

**What breaks:** Adding a new bare-metal Linux worker host today requires manual SSH steps before `deploy/deploy-linux-worker.py` will pass its pre-flight check: install Docker CE, install nfs-common, append three NFS entries to `/etc/fstab` (Brain media_tv, Synology movies, Synology xxx), `mount -a`, and `mkdir /opt/mediavortex`. LXC has the equivalent codified at `infrastructure/terraform/mediavortex-workers/setup.sh`. Bare-metal has nothing.

Done manually for dot on 2026-05-16 -- worked in ~5 minutes -- but the manual steps undermine the "one command from fresh" experience that the worker-deploy feature promises for already-provisioned hosts. The exact commands run on dot are visible in the conversation transcript and on dot itself via `/etc/fstab` + apt history.

**Violates:** `infrastructure/docs/features/linux-worker-deploy.md` criterion 10 (added with this entry). Does NOT violate `deploy/worker-deploy.feature.md` -- that feature's scope explicitly excludes host provisioning; criterion 5 (fail-fast pre-flight) is satisfied today because the script correctly reports the missing prereqs.

**What "fixed" looks like:** A script at `infrastructure/terraform/mediavortex-bare-metal-bootstrap.sh` (or similar) that takes a target hostname/IP from `inventory.toml`, idempotently installs Docker CE + nfs-common, configures fstab from a canonical mount template, runs `mount -a`, and creates the required directories. After it runs, `deploy/bringup.md` bare-metal prerequisites collapse from a checklist to "run the bootstrap script first." Verifiable: on a host with only base Ubuntu + SSH, running the bootstrap script followed by `deploy-linux-worker.py <friendly>` brings the host to `Workers.Status='Online'` with zero manual steps in between.

**Look first:** `infrastructure/terraform/mediavortex-workers/setup.sh` (LXC equivalent, ~lines 1-100 -- the AppArmor purge is LXC-specific and should NOT carry over to bare-metal); `deploy/bringup.md` (current manual prereq section for bare-metal Linux); `infrastructure/terraform/inventory.toml` (canonical source for friendly name -> IP and ssh_user lookup); the NFS fstab entries that worked on dot 2026-05-16 are the same three lines used on Wakko (Brain `10.0.0.40:/mnt/pve/Media/_tv` nfs4, Synology `10.0.0.61:/volume1/_video` nfs vers=3, Synology `10.0.0.61:/volume2/XXX` nfs vers=3, all with `_netdev,nofail`).

**Fix with:** `/t`.

---


### --- swept from KNOWN-ISSUES.md (BUG-0016 close) 2026-06-02 ---

### [BUG-0016 - RESOLVED 2026-06-02] Orphan MediaFiles rows for `-mv.mp4` paths cause idx_mediafiles_filepath_unique violations on subsequent encodes

**Resolution 2026-05-25:** `Scripts/SQLScripts/CleanupOrphanMvPairs.py` resolved 1,425 of 1,506 detected coexistence pairs. The audit gate (TranscodeAttempts with Success=true AND FileReplaced=true AND command references the -mv.mp4 output) classified 1,423 as RETIRE-eligible. RETIRE preserves the audit trail by re-parenting `TranscodeAttempts` (and downstream `MediaFilesArchive` + `TemporaryFilePaths`) from the source row to the surviving -mv.mp4 row before deleting the source MediaFiles row. **No disk files were deleted** -- spot-checks revealed many -mv.mp4 outputs from BUG-0013-era runs have wrong audio (Pokemon S04E20 at -18.2 LUFS + clipping; Office S07E05 at -32.5 LUFS), so the .mkv source remains as the safe master pending a future LUFS-verified retire script. The remaining 81 KEEP_BOTH pairs (no audit trail proving the -mv.mp4 came from a clean pipeline run) were parked with `AdmissionDeferReason='manual_review_pair_conflict'`, `RecommendedMode=NULL`, `NeedsQuick/NeedsTranscode=FALSE` to keep them out of the queue until operator triage. Find them via `SELECT Id, FilePath FROM MediaFiles WHERE AdmissionDeferReason='manual_review_pair_conflict'`.

**Below:** original entry preserved for context.

---

**Date:** 2026-05-24 | **Area:** file-replacement

**What breaks:** Some MediaFiles rows reference paths like `T:\Show\ep-mv.mp4` while a separate MediaFiles row for the original `T:\Show\ep.mkv` also exists. When the pipeline runs a Quick Fix on the `.mkv` row, FileReplacement produces `ep-mv.mp4` and calls `SaveMediaFile` with the new path -- which violates `idx_mediafiles_filepath_unique` because the orphan row already claims that path. Result: rename succeeded on disk, DB update failed, the file is in an inconsistent state.

**Repro:**
```sql
SELECT m1.Id AS source_id, m1.FilePath AS source_path,
       m2.Id AS orphan_id, m2.FilePath AS orphan_path
FROM MediaFiles m1
JOIN MediaFiles m2 ON LOWER(m2.FilePath) = LOWER(REPLACE(m1.FilePath, '.mkv', '-mv.mp4'))
WHERE m1.FilePath ILIKE '%.mkv' LIMIT 10;
```
Returns matched pairs. Pipeline runs on any source_id will hit the constraint.

**Evidence:**
- Pipeline-test-harness step 10 against MediaFile 18045 (Ren & Stimpy S03E03): orphan row 683391 pointed at the `-mv.mp4` path, FileReplacement failed with `UniqueViolation: duplicate key value violates unique constraint "idx_mediafiles_filepath_unique"`.

**Look first:** Where does the orphan get created? Suspect either (a) a manual Quick Fix that succeeded enough to create a new MediaFiles row but didn't archive/delete the original, or (b) the SmartPopulate / Scan path discovering both files as separate MediaFiles. Run the repro SQL to count -- if large, a cleanup migration is the first move.

**Fix with:** `/t BUG-0016`.

---


### --- BUG-0018 rolled into BUG-0020 (close) 2026-06-02 ---

### [BUG-0018 - RESOLVED 2026-06-02 ROLLED INTO BUG-0020] OrphanCleanupService._SweepTemporaryFilePaths races FileReplacement during the VMAF window
**Date:** 2026-05-25 | **Area:** orphan-cleanup / file-replacement

**Status:** **Mitigated, not fixed.** Sweep is disabled (`return 0`) in `Features/ServiceControl/OrphanCleanupService.py` pending the redesign below. Operator-cleanable TFP accumulation is the accepted trade until the proper fix ships.

**Related: [BUG-0015]** is the disk-side companion to this DB-side hole. Both are symptoms of the same architectural gap: nothing reconciles disk `.inprogress` / `-mv.mp4` orphans against `TemporaryFilePaths` + `TranscodeAttempts` state. Fix them together as a single "TFP/disk lifecycle" feature pass, otherwise the disk-orphan sweep and DB-orphan sweep will keep racing each other and the live pipeline.

**Reproduced twice on Doctor Who S06E04:**
- *Canary v2* (legacy predicate `Success IS NOT NULL`): encode 16:32-16:48 -> VMAF -> Disposition=Replace+VmafPassed, FileReplaced=FALSE, `.inprogress` (297 MB) stranded.
- *Canary v3* (tightened predicate `Success=FALSE OR FileReplaced=TRUE OR Disposition IN ('Discard','NoReplace','Requeue')`): same outcome. OrphanCleanup logged `removed 1 TemporaryFilePaths rows` at 23:15:26 UTC while attempt 25927 was `Success=TRUE, Disposition=Pending` -- a state that should NOT match the tightened predicate. Predicate-tightening is the wrong gate either way; investigation halted at the user's request to avoid further token spend.

**What breaks:** Encode finishes -> `Success=TRUE` committed -> file sits in QualityTestingQueue for 5-15 min while VMAF runs -> OrphanCleanup sweeps every ~120s on each of 4 worker containers. The TFP row gets deleted somewhere in that window. When VMAF lands and disposition flips to Replace, `FileReplacementBusinessService.ProcessFileReplacement` reads SourceStorageRootId/SourceRelativePath from TFP, finds nothing, bails silently. `.inprogress` stays on disk, MediaFiles row never updates, no audit trail beyond `_AutoCaptureStillsIfPolicyFires` warnings logged after VMAF score lands.

**Why predicate-tightening is the wrong approach:** "Orphan" is being inferred from columns on the parent attempt (Success/Disposition/FileReplaced). The actual orphan signal is *no live owner has work in progress* -- and during the VMAF window the live owner is the QualityTesting worker, whose presence is recorded in `QualityTestingQueue` + `ActiveJobs`, not in `TranscodeAttempts`. The sweep can't see liveness from the columns it's checking.

**Success criteria for the real fix:**
1. `_SweepTemporaryFilePaths` deletes a TFP row only when **all three** are true: (a) no `QualityTestingQueue` row exists for the parent TranscodeAttemptId; (b) no `ActiveJobs` row exists for that attempt (across both `Transcode` and `QualityTest` ServiceNames); (c) the parent attempt's terminal state is recorded (`Success=FALSE` OR `FileReplaced=TRUE` OR `Disposition IN ('Discard','NoReplace','Requeue')`).
2. After re-enabling, a 4-file Transcode+VMAF canary across larry-worker-1..4 must produce zero `.inprogress` files stranded; every attempt either reaches FileReplaced=TRUE or records a non-Replace disposition with TFP cleaned by the disposition owner.
3. The sweep logs the attempt IDs it touches on each non-zero run (`OrphanCleanup deleted TFP for TranscodeAttemptIds=[...]`) so any future race is diagnosable from logs alone, not from inference.

**Violates:** `transcode.flow.md` Stage 7 (FileReplacement must complete for any Disposition in {Replace, BypassReplace}).

---

### --- BUG-0015 rolled into BUG-0020 (close) 2026-06-02 ---

### [BUG-0015 - RESOLVED 2026-06-02 ROLLED INTO BUG-0020] Orphan `-mv.mp4` files on disk without corresponding MediaFiles row
**Date:** 2026-05-24 | **Area:** file-replacement

**Related: [BUG-0018]** is the DB-side companion to this disk-side hole. Both are symptoms of the same architectural gap: nothing reconciles disk `.inprogress` / `-mv.mp4` orphans against `TemporaryFilePaths` + `TranscodeAttempts` state. Fix them together as a single "TFP/disk lifecycle" feature pass -- piecemeal fixes will keep racing each other and the live pipeline.

**What breaks:** Filesystem directories accumulate `-mv.mp4` (and `-mv.mp4.inprogress`) files with no DB row pointing at them. When the pipeline runs a Quick Fix on a sibling source, `_ProcessCompleteFileReplacement` at line 425 refuses with `"Refusing to overwrite existing file at target"`. Encode aborts before any state change.

**Repro:**
1. Pick any directory with a recently-attempted Quick Fix.
2. `ls *-mv*` -- common to see one or more `.mp4` files that match no MediaFiles row.
3. Run Quick Fix again on the source `.mkv` -- pipeline refuses.

**Evidence:**
- Bluey Minisodes S01E09 dir had `-mv.mp4`, `-mv-mv.mp4`, `-mv-mv-thumb.jpg`, `-mv.mp4.inprogress` siblings of the original `.mkv` source, none referenced by any MediaFiles row -- left behind by interrupted Quick Fix runs (likely the BUG-0013 generational-stacking cycle plus crashed attempts).
- Ren & Stimpy S03E03 dir same pattern.
- Pipeline-test-harness step 10 surfaced both via the "Refusing to overwrite" path.

**Look first:** Crash-recovery in `FileReplacementBusinessService`. The `.inprogress` rename is the worker-lifecycle.feature.md atomic pattern, but on worker crash mid-encode the orphan survives until the next OrphanCleanup sweep. For `-mv.mp4` finals: probably from FileReplacement's "rename succeeded but DB update failed" path (e.g. BUG-0016) which logs a warning, returns Success=True, but leaves the file at the target name without the corresponding DB transition.

**Fix with:** `/t BUG-0015`.

---

### --- BUG-0010 rolled into BUG-0020 (close) 2026-06-02 ---

### [BUG-0010 - RESOLVED 2026-06-02 ROLLED INTO BUG-0020] TemporaryFilePaths cleanup runs only on FileReplacement success, leaks on all other return paths
**Date:** 2026-05-22 | **Area:** file-replacement

**What breaks:** `FileReplacementBusinessService.ProcessFileReplacement` only calls `_CleanupTemporaryFilePaths` inside the `if replacement_result.get('Success', False):` branch at line 217-225. Every other terminal return -- transcode_attempt None (165-166), transcoded file missing on disk (185-189), defense-in-depth size guard (196-208), archive failure (210), and the `else` branch where `_ProcessCompleteFileReplacement` returns Success=false -- exits without removing the TFP row. Because `TranscodeAttempts.Success` is already set by then, the OrphanCleanup safety-net sweep removes them ~every 2 minutes and emits a WARNING.

This is the structural sibling of BUG-0009. BUG-0009 is "why are replacements failing in the first place"; BUG-0010 is "even if replacements never failed, future failure modes will leak again until cleanup is moved off the success-only branch."

**Repro:** Force any non-success branch (e.g. delete the transcoded file from `LocalOutputPath` between transcode-finish and replacement-start) and observe the TFP row remains until the next OrphanCleanup sweep.

**Evidence:** Code inspection at `FileReplacementBusinessService.py:160-232`. The chokepoint comment in `PostTranscodeDispositionService._CommitDisposition` (line 295-298) explicitly states FileReplacement owns its own TFP cleanup on success; nothing claims it on failure.

**Violates:** `Features/FileReplacement/FileReplacement.feature.md` criterion 12 (added with this bug).

**Look first:** Two viable fixes -- (a) put `_CleanupTemporaryFilePaths` in a `finally` block scoped to the function so every terminal return cleans up, OR (b) route any failure return through `PostTranscodeDispositionService._CommitDisposition` with a non-success Disposition (Requeue/Discard) so the existing chokepoint owns cleanup for both success and failure paths. (b) is cleaner architecturally because it keeps cleanup centralized in `_CommitDisposition`, but (a) is a smaller surgical change.

**Fix with:** `/t BUG-0010`.

---

### --- BUG-0009 rolled into BUG-0020 (close) 2026-06-02 ---

### [BUG-0009 - RESOLVED 2026-06-02 ROLLED INTO BUG-0020] FileReplacement returns Success=false for some attempts, leaving orphaned TemporaryFilePaths rows
**Date:** 2026-05-22 | **Area:** file-replacement

**What breaks:** `OrphanCleanup` logs `OrphanCleanup removed N TemporaryFilePaths rows for finished TranscodeAttempts -- a terminal-state cleanup path is leaking, investigate.` at small but recurring counts (1-3 per sweep, ~every 2 minutes). The trigger is `TranscodeAttempts.Success=true` (transcode succeeded) AND a `TemporaryFilePaths` row still exists for that attempt -- which means `FileReplacementBusinessService.ProcessFileReplacement` reached the attempt but bailed out of the success branch at `FileReplacementBusinessService.py:217`. The actual failure reason is not visible in the OrphanCleanup warning -- only the count.

**Repro:** Watch WorkerService logs over a 10-minute window. The OrphanCleanup TFP-orphan WARN fires repeatedly with non-zero counts. Cross-reference TranscodeAttempts where `Success=true AND Disposition IN ('Replace','BypassReplace')` and look for ones with no corresponding `FileReplaced=true`.

**Evidence:** Confirmed 2026-05-22 from live worker logs -- four consecutive OrphanCleanup sweeps removed 2, 2, 3, 1 TFP rows respectively. OrphanCleanupService.\_SweepTemporaryFilePaths is doing its safety-net job; the upstream `FileReplacement` chokepoint is the actual leak source.

**Violates:** `Features/FileReplacement/FileReplacement.feature.md` criterion 11 (added with this bug).

**Look first:** `Features/FileReplacement/FileReplacementBusinessService.py:160-225`. Every return path that does NOT reach `_CleanupTemporaryFilePaths` (line 225) is a candidate:
- line 165-166: `GetTranscodeAttemptById` returned None
- line 185-189: `ValidateFileExists(LocalTranscodedPath)` false (transcoded output missing on local mount)
- line 196-208: defense-in-depth size guard (`NewSize >= OldSize` for non-Remux)
- line 217 `else`: `_ProcessCompleteFileReplacement` returned Success=false
- archive failure inside `_ArchiveOriginalFileDetails` (line 210)

To diagnose: grep WorkerService log for `FileReplacementBusinessService` ERROR/WARNING lines immediately preceding each OrphanCleanup TFP warning. The function already logs its specific error -- pull those lines into a count by reason. Most likely candidates given recent operational state: missing-output-file (post-2026-05-22 SMB cutover staging path drift) or size-guard (non-Remux profiles producing larger output on certain content).

**Fix with:** `/t BUG-0009`.

---


### --- BUG-0011 close 2026-06-02 (verified solid in production over multiple days) ---

### [BUG-0011 - RESOLVED 2026-06-02] JellyfinNotify gets HTTP 500 from Jellyfin, WARNING does not log the offending payload | resolved: 2026-06-02
**Date:** 2026-05-22 | **Area:** jellyfin-notify

**What breaks:** `WARNING: JellyfinNotify: non-2xx status=500 for 2 update(s); body='Error processing request.'` fires from `Services/JellyfinNotifyService.py:169-173`. Jellyfin's 500 body is a generic ASP.NET error string -- no path, no library name, no plugin trace. The WARNING logs only count + body slice, so neither MediaVortex nor the operator can tell which translated path Jellyfin choked on. Likely causes (per the `reference_jellyfin_notify_api` memory and prior post-mortems): a path that doesn't resolve to any configured Jellyfin library root, a separator/case mismatch between MediaVortex-translated and Jellyfin-configured library paths, or a plugin-side bug that wraps a downstream exception as 500 instead of 4xx.

**Repro:** Run any file-mutation choke point (file replace, scan-detected new file, etc.) and wait for the WARNING to fire. There is no way today to map the warning back to a path without code change.

**Evidence:** Live worker log 2026-05-22 -- "non-2xx status=500 for 2 update(s); body='Error processing request.'". Same notification path produces 204 for the vast majority of mutations, so this isn't a global config failure -- it's path-specific.

**Violates:** `jellyfin-push-notify.feature.md` criterion 10 (added with this bug).

**Look first:** `Services/JellyfinNotifyService.py:154-180`. Add `Translated` (or at minimum the first entry's `Path` + `UpdateType`) to the non-2xx WARNING. While debugging the eventual fix, also check Jellyfin's own log (`/var/log/jellyfin/` on the Jellyfin host) at the timestamps -- ASP.NET 500 usually corresponds to a stack trace in the server log that names the offending library/plugin.

**Fix with:** `/t BUG-0011`.

---


### --- BUG-0004 close 2026-06-02 (fixed in 908a148; reinforced by ffe1b84 shared claim helper + 5483e58 sync StopRequested) ---

### [BUG-0004 - RESOLVED 2026-06-02] Workers.Status='Paused' does not gate capability claiming | resolved: 2026-06-02
**Date:** 2026-05-18

**What breaks:** Setting `Workers.Status='Paused'` via the Activity page UI Pause button is purely cosmetic. The worker daemon continues to claim and process jobs as long as the individual capability flags (`TranscodeEnabled`, `RemuxEnabled`, `QualityTestEnabled`, `ScanEnabled`) are TRUE. Confirmed 2026-05-18: larry-worker-8 with `Status='Paused'`, `RemuxEnabled=false`, `TranscodeEnabled=true` claimed and ran a Transcode job (`TranscodeAttempts.Id=16549`, Real Housewives S01E15 downscale to 480p). Operator had clicked Pause on the worker tile and expected NO claiming; the worker ran anyway because TranscodeEnabled stayed true.

**Violates:** `Features/TeamStatus/worker-status-model.feature.md` criterion 9 (added with this bug); also `Features/ServiceControl/capability-control-plane.feature.md` criterion 8 (Status='Online' must be a hard precondition for every capability, added 2026-05-18 amendment).

**Look first:** `WorkerService/Main.py:711` `_ApplyCapabilities` -- only checks `self.TranscodeEnabled / self.RemuxEnabled / self.QualityTestEnabled / self.ScanEnabled`; `self.WorkerStatus` is loaded from DB (line 311) but never consulted. The fix is to wrap or extend `_ApplyCapabilities` so any non-Online status short-circuits to "stop all capabilities" regardless of the individual flags. Draining state has its own rules (cf. worker-status-model.feature.md criterion 3) -- finish in-flight jobs but don't claim new ones; Paused stops immediately.

**Flow doc:** `Features/TeamStatus/worker-status-model.feature.md` describes the state model but no separate flow doc exists for capability-vs-status interplay; `/t` should either extend the existing feature doc's narrative or add a small flow doc.

**Fix with:** `/t BUG-0004`.

---

