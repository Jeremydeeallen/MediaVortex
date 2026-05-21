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
