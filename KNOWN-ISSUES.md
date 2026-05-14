# Known Issues

## Open

### [FEATURE - DONE 2026-05-14] Disable/enable workers -- hide retired workers from UI

**Problem:** Retired workers (e.g. Remington) remain visible in the Activity page worker cards forever. No way to hide them without deleting the row (which loses historical config).

**Solution:** Added `Workers.Enabled` column (BOOLEAN, default TRUE). The `/api/TeamStatus/Workers` endpoint filters to `Enabled=TRUE` by default. A `?IncludeDisabled=true` query param shows all. Activity page has a "Show Disabled" toggle and Disable/Enable buttons on each worker card. Disabled workers render dimmed with a dark "Disabled" badge.

**Files:** `TeamStatusController.py` (endpoints), `Activity.html` (UI), `AddWorkerEnabledColumn.py` (migration).

### [FEATURE - DONE 2026-05-14] Remove hardcoded concurrency ceiling -- let DB drive limits

**Problem:** `MaxConcurrentJobs` was capped at 5 in 6 places (API validation, worker clamp). Operator had to redeploy to raise the limit. Not data-driven.

**Solution:** Removed upper bound from all validation/clamp sites. Only floor of 1 enforced. The operator sets whatever value fits their hardware via the Workers table.

**Files:** `TeamStatusController.py`, `ProcessRemuxQueueService.py`, `ProcessTranscodeQueueService.py`, `ProcessQualityTestQueueService.py`, `TranscodeJobController.py`, `WorkerService/Main.py`.

### [BUG - FIXED 2026-05-13] Remux files discarded as "NoSavings" -- disposition gate ordering bug
**Date:** 2026-05-13 | **Fixed:** 2026-05-13

**What broke:** `PostTranscodeDispositionService._DecideFromInputs` checked `NewSize >= OldSize -> Discard/NoSavings` (Row 2) before `QualityTestRequired=false -> BypassReplace` (Row 3). Remux jobs set `QualityTestRequired=false` but often produce slightly larger outputs (audio re-encode). Result: 679 successful remux attempts got `Disposition='Discard'`, FileReplacement never ran. Disk state: original at `.orig`, good remuxed `.mp4` at source path, DB still pointing to old `.mkv`/`.mp4` path.

**Violates:** `Features/FileReplacement/FileReplacement.feature.md` criterion 10, `transcode-vs-remux-routing.feature.md` criterion 16.

**Fix:** Swapped Row 2 and Row 3 in `_DecideFromInputs` so `QualityTestNotRequired` fires before `NoSavings`. Remux attempts bypass the savings gate entirely. Remediation script `Scripts/SQLScripts/RemediateDiscardedRemuxFiles.py` flipped dispositions and ran `ProcessFileReplacement` for affected rows. ~380 remediated on i9; 113 blocked by stale `.orig` needing manual cleanup; 188 need script run from larry after redeploy.

---

### [BUG] Per-capability concurrency is not data-driven -- requires worker restart to take effect
**Date:** 2026-05-13

**What breaks:** Changing `MaxConcurrentTranscodeJobs`, `MaxConcurrentQualityTestJobs`, or `MaxConcurrentRemuxJobs` in the Workers table does not take effect until the worker process is restarted. The concurrency value is read once during `_StartXxxCapability()` and passed to `Run(MaxConcurrentJobs=N)`. The capability polling loop (60s) checks enabled/disabled flags but never re-reads the concurrency columns. This violates the "data-driven" contract: if the max is raised from 1 to 2, the worker should spin up an additional thread on its next poll without restart.

**Violates:** `WorkerService/WorkerService.feature.md` criterion 18 (added with this entry).

**Look first:** `WorkerService/Main.py` `_CapabilityPollingLoop` and `_GetPerCapabilityConcurrency()`. The queue service `Run()` method needs to support dynamic thread-pool resizing, or the capability must be stopped and restarted with the new concurrency value.

---

### [BUG - FIXED 2026-05-13] MaxConcurrentJobs from Workers table is ignored -- workers always run 1 concurrent job
**Date:** 2026-05-13 | **Fixed:** 2026-05-13

**What breaks:** `WorkerService/Main.py` loads `MaxConcurrentJobs` from the Workers table into `self.WorkerConfig` at startup, but `_StartTranscodeCapability()` (line 207) and `_StartQualityTestCapability()` (line 245) both hardcode `Run(MaxConcurrentJobs=1)`. Setting `Workers.MaxConcurrentJobs=2` in the DB has no effect -- the worker still processes one queue item at a time.

**Violates:** `WorkerService/WorkerService.feature.md` criterion 16.

**Fix:** Replaced the single `MaxConcurrentJobs` column with per-capability columns: `MaxConcurrentTranscodeJobs` (default 1, CPU-bound), `MaxConcurrentQualityTestJobs` (default 2, I/O-bound), `MaxConcurrentRemuxJobs` (default 2, I/O-bound). Each capability now reads its own column via `_GetPerCapabilityConcurrency()`. Additionally, remux is now a separate capability (`ProcessRemuxQueueService`) with its own queue loop and claim query, so remux concurrency is independent of transcode. Schema migration: `Scripts/SQLScripts/AddPerCapabilityConcurrency.py`.

---

### [BUG] Status page "Possibly Corrupt" count has no drill-down to see which files are affected
**Date:** 2026-05-13

**What breaks:** The `/Status` page shows "Possibly Corrupt: N" (files with `FFProbeFailureCount >= 3`) as a static number with no click-through. The operator sees there ARE corrupt files but cannot see WHICH ones without navigating to `/Scanning` and opening the Corrupt Files modal. The API endpoint (`GET /api/FileScanning/MediaFiles/Corrupt`) and the detail modal (`Templates/FileScanning.html#CorruptFilesModal`) already exist -- the Status page just doesn't use them.

**Violates:** `Features/FileScanning/FileScanning.feature.md` criterion 19 (added with this entry).

**Look first:** `Templates/Status.html` line 55-61 (the `#LibCorrupt` card -- make it clickable). Reuse the existing `/api/FileScanning/MediaFiles/Corrupt` endpoint. Either inline a modal on the Status page or link to `/Scanning?openCorrupt=true` with auto-open logic.

**Fix with:** `/t`.

---

### [BUG - FIXED 2026-05-13] Worker deploy scp copies the entire repo (venv, .git, Tests, etc.) instead of just build inputs
**Date:** 2026-05-12 | **Fixed:** 2026-05-13

**What broke:** Step 1 of `deploy/worker-deploy.flow.md` ran `scp -r /c/Code/MediaVortex/* root@10.0.0.42:/tmp/mediavortex-build/` -- a blind recursive copy that dragged `venv/`, `.git/`, `__pycache__/`, `Tests/`, smoke-test artifacts, screenshots, ad-hoc dumps, and anything else sitting in the working directory across the wire. Wasted bandwidth and time on every deploy and bloated the Docker build context for no payoff.

**Fix:** Created `.deployignore` (exclusion patterns for deploy sync -- additive by default, new files included automatically). Linux deploy: `deploy/SyncSource.py` reads `.deployignore` and uses tar-over-ssh to stream only needed files. Windows deploy: `deploy-windows-worker.py` `StepScpRepo()` now uses `shutil.copytree` with the same `.deployignore` patterns into a temp directory before scp. Flow doc step 1 updated.

**Violates:** `deploy/worker-deploy.feature.md` criterion 19.

---

### [BUG] Next Remux Batch table shows files with no audio stream that silently fail when queued
**Date:** 2026-05-14

**What breaks:** The "Next Remux Batch" card on the ShowSettings page calls `/api/ShowSettings/SmartPopulate` with `Mode='Remux'`. The SmartPopulate query filters by `HasExplicitEnglishAudio IS NULL OR HasExplicitEnglishAudio = true`, but files that have never been probed with audio-aware code have `HasExplicitEnglishAudio = NULL` -- which passes the filter. These video-only files (e.g. Survivor S43E01, S45E02) get displayed as candidates, queued by the user, then fail with "Transcoding failed with return code 4294967274" because the remux command maps `0:a:0` which doesn't exist.

**Violates:** SmartPopulate should exclude files that are known to have zero audio streams (possibly corrupt). No feature doc exists yet for this card's population logic end-to-end.

**Look first:** `Features/TranscodeQueue/QueueManagementBusinessService.py` `SmartPopulateQueue()` WHERE clause; `Features/ShowSettings/remux-populate-card.feature.md`; the `RecommendedMode` materialization in `_EvaluateCompliance()`.

**Fix with:** `/t`.

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

### [BUG - CRITICAL] VMAF distribution becomes bimodal on MKV-source transcodes -- mean/HMean/P5 unreliable for trending
**Date:** 2026-05-10

**What breaks:** Same encoder recipe (libsvtav1 preset 4, FG 0, CRF sweep, lanczos scale, compare at 1280:720) produces wildly different VMAF distribution shapes depending on source container. Reference data point from the FourK test: 4K MP4 source -> Mean 95.77, HMean 95.75, StdDev 1.18, P5 94.30 across 1080p/720p/480p output variants. Unimodal, tight, exactly what we expect from a clean source. The three MKV sources tested today (Minnie's Bow-Toons S04E07 8.6 Mbps WEBDL-1080p, Black Butler S02 Extras 13 Mbps 10-bit anime, The Office S00E05 7.1 Mbps WEBDL-1080p) all returned bimodal distributions: roughly 56% of frames score VMAF 90+, but ~7% score near zero with a continuous bad-frame gradient in between. Concrete numbers for Minnie's 1080p CRF32 variant: Mean 74.60, HMean 11.20, StdDev 32.58, P5 0.00, P10 14.06, P25 54.12.

**The metric is wrong, not the encoder:** extracted source-vs-encoded PNG stills at one of the "VMAF=0" frames (Minnie's frame 150 at 0:06.26). The images are visually indistinguishable. So the encoder is producing the correct picture; libvmaf is assigning a near-zero score to a frame that looks identical to the reference. The user-visible slider remains useful (it shows you the actual frames); the per-attempt numeric VMAF score does not currently reflect perceptual quality on MKV-source transcodes.

**Ruled out:** frame desync (`ffprobe -count_frames` returned 2181 frames on source and on each of the three Minnie's encoded variants -- identical counts, identical r_frame_rate 24000/1001, identical duration 90.97s). VMAF subsampling drift (re-ran with `n_subsample=10` removed entirely; distribution stayed bimodal, P5 went from 0.29 to 0.00, StdDev got slightly worse). FPS mismatch (rates match across variants).

**Most likely cause:** color metadata mismatch confusing libvmaf's per-frame scoring on dark or transitional frames. ffprobe on Minnie's source reports `pix_fmt=yuv420p` 8-bit `color_range=tv color_space=bt709`; encoded reports `pix_fmt=yuv420p10le` 10-bit `color_range=tv color_space=unknown`. Black Butler source: `pix_fmt=yuv420p10le` `color_range=unknown color_space=unknown`; encoded: `pix_fmt=yuv420p10le color_range=tv color_space=unknown`. The `format=yuv420p` step in our VMAF filter chain downconverts the encoded stream to 8-bit but does NOT enforce a matching color_range -- so for "unknown"-tagged source frames libvmaf may interpret pixel values in one range while the encoded stream is interpreted in another, producing huge synthetic differences on dark pixels (where the limited-vs-full range gap is largest).

**Why critical:** tier-threshold calibration (the entire point of the source-quality work) cannot proceed while Mean/HMean/P5 from MKV-source attempts are not comparable to MP4-source numbers. The auto-replace gate (`VmafAutoReplaceMinThreshold=88` in `PostTranscodeGateConfig`) is currently making decisions on a metric that measures different things depending on source container. The 80/78-VMAF "ceiling" we have been attributing to source bitrate may be partly a measurement artifact when source is MKV. Operator-facing implication: do not trust per-attempt VMAF numbers for MKV-source transcodes until this is resolved; visual slider inspection remains valid.

**Violates:** `Features/QualityTesting/QualityTesting.feature.md` criterion 2 ("VMAF scoring compares the transcoded file against the original and produces a numeric score (0-100)") -- the score is being produced but does not correspond to perceptual quality on MKV inputs. [BUG] criterion 2b added with this entry.

**Candidate mitigation suggested by operator:** remux MKV sources to MP4 before transcoding. Remux is bytewise-identical to the source video stream (no quality loss) and would normalize container-level timing and pixel-format metadata. Risk: pre-transcode remux adds a stage to the pipeline (storage, time, failure mode); the metadata change may not be the actual cause and the fix won't work. Validate the hypothesis on ONE source first: remux Minnie's to MP4, re-run the same harness, compare VMAF distribution shape. If clean unimodal scores result, remux-before-transcode is the answer; if still bimodal, color metadata is not the cause and the investigation goes deeper.

**Other candidate mitigations to try in order of cost:** (a) add `setparams=range=tv:colorspace=bt709` to both filter streams (metadata-only, no pixel conversion -- might tell libvmaf to interpret both consistently); (b) add explicit `scale=...:in_range=auto:out_range=tv` to source stream (active range conversion); (c) use `zscale` filter for color management if available in the FFmpeg build; (d) compare both as 10-bit (`format=yuv420p10le` for both) to keep encoded native; (e) remux source MKV->MP4 before VMAF only (not before transcode), see if the VMAF measurement alone normalizes; (f) the operator's mitigation: remux before transcode entirely.

**Look first:** `Features/QualityTesting/QualityTestingBusinessService.py:BuildVMAFCommand` for the production VMAF filter chain. `Scripts/Smoke/EncodeAndVmaf.py:Vmaf` for the smoke-test harness filter chain (identical shape). The relevant FFmpeg subprocess invocation and lavfi string are the only surface for this bug. Reproducer: run `py Scripts/Smoke/EncodeAndVmaf.py --vmaf-only Scripts/Smoke/MinnieBowToons-S04E07-Animation8Mbps.results.json` and observe Mean ~74 / P5 0.

**Fix with:** `/t`. Try mitigation (a) first; iterate down the list. Track which fix changed the distribution shape so we know which metadata mismatch was actually responsible.

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

### [BUG - FIXED 2026-05-10] Post-transcode pipeline had 5 split decision sites, 5+ scattered config sources, no audit trail
**Date:** 2026-05-10
**Affects:** `Features/QualityTesting/ShouldQualityTestService.py`, `Features/QualityTesting/QualityTestingBusinessService.py` (`UpdateQualityTestResults`, `CheckAndTriggerAutoReplace`), `Features/FileReplacement/FileReplacementBusinessService.py` (`ProcessFileReplacement`/`ProcessFileReplacementWithVMAF` with `BypassVMAFCheck` parameter), `Features/TranscodeJob/ProcessTranscodeQueueService.py` (`IsQualityTestEnabled`), `SystemSettings` rows for `VMAFAutoReplaceMinThreshold` / `MaxThreshold` / `QualityTestEnabled`.

After a transcode completes, the decision "do we run VMAF, replace, requeue, or discard?" is split across five files. Inputs come from five different storage shapes (per-worker capability, global SystemSettings KV, ServiceStatus, per-attempt flag, ProfileThresholds). No place captures the final decision and the reason for it. Today (2026-05-10) Sister Wives S04E05 transcode succeeded but `ServiceStatus.QualityTestService='Paused'` silently routed to bypass-replace which then silently failed -- the 720p output was deleted by failure cleanup, no detail logs, no queryable reason for why it didn't replace. The opaque "Quality test processing failed for TranscodeAttempt X: File replaced automatically because Quality testing service is paused" log claims success while `FileReplaced=false`.

**Violates:** `Features/QualityTesting/post-transcode-disposition.feature.md` (drafted 2026-05-10, all 17 criteria).

**Fix:** unified `DecidePostTranscodeDisposition` function + `PostTranscodeGateConfig` typed-column table + `Disposition`/`DispositionReason`/`DispositionDecidedAt` columns on `TranscodeAttempts`. Legacy ShouldQualityTestService / BypassVMAFCheck / ProcessFileReplacementWithVMAF / CheckAndTriggerAutoReplace deleted.

**Follow-up bugs caught during sight-test before redeploy (also fixed 2026-05-10):**
- **Wrong dict key:** `QualityTestingBusinessService.py:271` read `JobDetails.get('transcode_attempt_id')` (snake_case) when the dict uses `'TranscodeAttemptId'` (PascalCase). Effect: `DecidePostTranscodeDisposition` was never re-called after VMAF score landed; `Disposition` stayed `Pending` forever; FileReplacement never triggered. The decision-table conformance test missed it (pure unit test, didn't exercise wiring).
- **Fossilized gate input:** the disposition function read `ServiceStatus.QualityTestService.Status` as a live gate. Every live writer of that row is in `archive_QualityTestService/Main.py`; the new unified WorkerService never updates it. The row had been frozen at `Status='Paused', UpdatedAt='2026-01-26'` for 3.5 months. Effect: every transcode hit decision-table row 8 (`NoReplace, VmafServicePaused`) regardless of actual worker capability. **Fix:** replaced the gate with a computed query against `Workers` (`QualityTestEnabled=TRUE AND Status='Online' AND fresh heartbeat`). Reason names retained for audit-history compatibility.
- **Honest Requeue dispatch:** `Disposition='Requeue'` was a no-op (audit-only). `_HandleRequeueDisposition` now deletes the staged file and writes a ProblemFiles row. NOT auto-creating a new TranscodeQueue at adjusted CRF -- TranscodeQueue has no CRF column, so a new row would re-run the same profile at the same CRF. Real auto-requeue requires a schema change (tracked separately).

**Fix with:** `/n` -- doc-first feature, shipped 2026-05-10. Two latent wiring bugs and one no-op branch caught and fixed before the larry redeploy.

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

### [BUG - FIXED 2026-05-10] ShowSettings global-default `*` overrides explicit profile assignment (target resolution)
**Date:** 2026-05-10 | **Fixed:** 2026-05-10 (cascade + global-default row entirely removed)
**Affects:** `Features/ShowSettings/ShowSettingsRepository.py`, `Features/ShowSettings/ShowSettingsController.py`, `Features/TranscodeJob/ProcessTranscodeQueueService.py`, `Features/TranscodeQueue/QueueManagementBusinessService.py`, `ShowSettings.feature.md`.

Sister Wives S04E05 was queued under `AV1 P4 FG6 >720p` (1080p source, profile says target=720p) but the FFmpeg command emitted `scale=852:480` because `ShowSettings.ShowFolder='*' / TargetResolution='480p'` clobbered the profile. `GetTargetResolutionForFile` cascaded specific match -> `*` default and the worker unconditionally overrode `ProfileSettings['TargetResolution']`.

**Fix:** removed the cascade entirely.
- `GetDefaultTargetResolution()` deleted from repository.
- `GetTargetResolutionForFile()` now returns the per-show row only (or None); no fallback to `*`.
- The `ShowFolder='*'` row was deleted from the live DB.
- `GET /api/ShowSettings/Default` and `POST /api/ShowSettings/Default` endpoints deleted; `GET /Shows` no longer returns `DefaultTargetResolution`.
- Profile.TranscodeDownTo is now the sole source of default target behavior; ShowSettings carries explicit per-show overrides only.

**Violates / closed:** `ShowSettings.feature.md` Success Criterion 1.

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

### [BUG - FIXED 2026-05-09] File scanner runs on whichever worker has ScanEnabled, not the one with fastest storage access
**Date:** 2026-05-09 | **Fixed:** 2026-05-09 (host-affinity column + per-rootfolder claim guard + cap as SystemSetting)
**Affects:** `Features/FileScanning/FileScanningBusinessService.py` (`DetectMovedFiles`, `CleanupMissingFiles`, `ProcessMediaFilesWithMetadata`), `Features/FileScanning/ContinuousScanService.py`, `FileScanning.feature.md` criteria 11 and 12, `FileScanning.flow.md` "Continuous Mode Specifics"

Two related deficiencies surfaced together:

1. **No host-affinity for scan work.** `ContinuousScanService` runs on every worker with `Workers.ScanEnabled=true` and iterates every `RootFolders` row independently. There is no claim/lease coordination, so two ScanEnabled workers can both walk the same rootfolder at the same time. Worse, the worker with the slowest storage path (e.g. WebService over SMB to brain) wins by default if it ticks first, while a backplane-attached worker like larry-worker-1 sits idle. Operator already flipped `larry-worker-1.ScanEnabled=true` for a fast-path TV scan but cannot guarantee the work lands there.

2. **Move detection silently disabled for libraries >10k files.** `DetectMovedFiles` skips at `MaxFiles=10000` (`FileScanningBusinessService.py:1488`). Library has 48,035 rows -> always skipped. The next-step `CleanupMissingFiles` walks the same row set with the same `os.path.exists` checks and is not capped, so the supposed "save" is zero. Net effect: file moves/renames outside MediaVortex become delete+create, dropping AssignedProfile / IsCompliant / RecommendedMode / TranscodedByMediaVortex / probe metadata.

**Violates:** `FileScanning.feature.md` criteria 11 and 12 (added with this bug).

**Look first:**
- `Features/FileScanning/ContinuousScanService.py` -- the per-worker tick that needs claim/lease semantics.
- `Features/FileScanning/FileScanningBusinessService.py:1487-1497` -- the 10k cap.
- `Features/FileScanning/FileScanningBusinessService.py:1374-1410` -- `CleanupMissingFiles` (uncapped, walks same rows).
- `RootFolders` schema -- candidate for a `PreferredWorkerName` column for affinity, or move to a separate `ScanAffinity` table.
- `ScanJobs` -- already exists; could carry a claim semantic similar to `TranscodeQueue.ClaimedBy`.

**Flow doc gap:** `FileScanning.flow.md` lines 46-51 ("Continuous Mode Specifics") describes the unscoped per-worker iteration as the current behavior. It is not yet updated for distributed claim semantics; `/t` should rewrite that section before the fix.

**Fix:** `Scripts/SQLScripts/AddScanAffinityColumns.py` adds `RootFolders.PreferredWorkerName`, `ScanJobs.WorkerName`, and seeds `SystemSettings('MoveDetectionMaxFiles', '100000')`. `RootFolderModel`/`FileScanningRepository` carry the new column. `FileScanningBusinessService.IsScanRunningForRootFolder` is the per-rootfolder duplicate-scan guard called from `StartScanning` before the global cap. `_GetMoveDetectionMaxFiles` reads the cap fresh per call (no cache, per memory rule). `ContinuousScanService._ExecuteScan` resolves WorkerName from `WorkerContext.Current()`, drops rootfolders pinned to other workers, and passes its name through to `StartScanning`.

**Operator usage:**
- Pin a rootfolder to the backplane-attached worker: `UPDATE RootFolders SET PreferredWorkerName='larry-worker-1' WHERE RootFolder='T:\';`
- Raise the move-detection cap: `UPDATE SystemSettings SET SettingValue='200000' WHERE SettingKey='MoveDetectionMaxFiles';`

**Deploy:** WorkerService and WebService both need to load the new code. SQL migration is already applied (587 RootFolders, all `PreferredWorkerName=NULL`). Scans continue to work pre-deploy because the Python signature change is backward-compatible (`WorkerName` defaults to `None`); only the affinity skip is dormant until the new code lands.

---

### [BUG - FIXED 2026-05-09] BuildRemuxCommand path-collision destroyed source file
**Date:** 2026-05-09 | **Fixed:** 2026-05-09 (atomic rename-and-replace in FileReplacement)
**Affects:** `Models/CommandBuilder.py` (`BuildRemuxCommand`, `BuildSubtitleFixCommand`), `Features/FileReplacement/FileReplacementBusinessService.py:_ProcessCompleteFileReplacement`. **One file lost: T:\IT - Welcome to Derry\Season 1\IT - Welcome to Derry - S01E04 - The Great Swirling Apparatus of Our Planet's Function WEBDL-480p.42.mp4** (MediaFileId 61707).

Pre-2026-05-09 `BuildRemuxCommand` computed `OutputPath = OriginalDir + os.path.splitext(MediaFile.FileName)[0] + ".mp4"`. For an .mp4 source in InPlace mode that resolved to OutputPath == InputPath. FFmpeg invoked with `-y` truncates the output before validating that input != output (return code -22 EINVAL), so the source got zeroed and FFmpeg cleaned up the empty output. The original file was destroyed.

The bug existed for the lifetime of `BuildRemuxCommand` but never triggered because the only Mode='Remux' producer (`PopulateQueueForRemux`) only fed .mkv sources where output extension `.mp4` differs from source. The cascade in `transcode-vs-remux-routing.feature.md` is the first thing that routes .mp4 sources to remux; the smoke test that surfaced the bug used a real production file.

**Two-layer fix:**
1. `Models/CommandBuilder.py`: `BuildRemuxCommand` and `BuildSubtitleFixCommand` ALWAYS use side-by-side suffix (`_remuxed.mp4` / `_subfix.mp4`) regardless of source extension. Defense-in-depth check refuses to build a command if OutputPath == InputPath would somehow occur.
2. `Features/FileReplacement/FileReplacementBusinessService.py`: `_ProcessCompleteFileReplacement` rewritten to a rename-then-replace pattern with rollback. Original is renamed to `.orig` BEFORE the staged file is moved; on any filesystem-level failure the rollback restores the `.orig` and reports failure. Original is never deleted until after the new file is verified non-zero on disk. See `transcode.flow.md` Stage 7 and `Features/TranscodeQueue/remux.flow.md` "Safety contract."

**Prior single-copy at risk:** the destroyed file was a 480p MediaVortex output from a 2026-03-26 transcode of an original 4K hevc source (snapshot in MediaFilesArchive, no file content). Operator should re-acquire via Sonarr or backup if available.

**Look first if a similar shape ever recurs:** `Models/CommandBuilder.py` `BuildRemuxCommand` line 412-466 (suffix is unconditional now), `Features/FileReplacement/FileReplacementBusinessService.py:447` (`_ProcessCompleteFileReplacement` rollback path).

**Lessons recorded:**
- Smoke tests against real production files should require an explicit `--sandbox` opt-in or operate on a known-disposable copy.
- Worker process restarts must be verified with a code-loaded check, not assumed.
- Any file-replacement flow that doesn't preserve the original until after explicit verification is one bad command away from a destructive bug.

---

### [BUG] QualityTestEnabled flip mid-run does not reach the transcode producer; in-flight job replaces file with no VMAF
**Date:** 2026-05-09
**Affects:** WorkerService.feature.md (criterion 2, criterion 15), `Features/TranscodeJob/ProcessTranscodeQueueService.py:100-101, 885-900, 1329`, `Features/QualityTesting/ShouldQualityTestService.py:34-57`

`ProcessTranscodeQueueService` caches `WorkerQualityTestEnabled` from the `WorkerConfig` dict at construction time. `WorkerConfig` is loaded once in `WorkerService._RegisterAndLoadWorkerConfig` at process startup and never refreshed, so toggling `Workers.QualityTestEnabled` mid-run does not change `IsQualityTestEnabled()` for the producer side. The capability poller does flip the *consumer* (start/stop QualityTestService), but the producer keeps writing `TranscodeAttempts.QualityTestRequired=False`. `ShouldQualityTestService` reads that False and calls `_ReplaceFileDirectly` (BypassVMAFCheck=True) -- original deleted, transcoded moved in, next job starts. Observed today on i9: VMAF was added mid-job, the in-flight transcode finished, file got replaced without VMAF, and the worker picked up the next job. Repro by starting a worker with `QualityTestEnabled=False`, queuing a job, flipping the flag (or the global) while the job runs, watching the post-success path skip the quality queue.

Secondary trap at line 100-101: `Config.get('QualityTestEnabled') or Config.get('qualitytestenabled')` silently treats a stored `False` the same as an explicit override (cached as False, shadows global), but a missing key collapses to None and falls through to global. The two paths should not behave differently.

**Violates:** WorkerService.feature.md criterion 2 ("Changing a capability flag in the Workers table takes effect within 60 seconds without restarting the process") -- the contract holds for the capability lifecycle but not for the transcode producer's QualityTestEnabled gate.

**Look first:** `Features/TranscodeJob/ProcessTranscodeQueueService.py:885-900` (`IsQualityTestEnabled` -- read live from DB instead of cached snapshot), lines 100-101 (tri-state load, drop the `or` collapse), line 1329 (the call site that stamps `QualityTestRequired` onto the success row), and `WorkerService/Main.py:88-145` (`_RegisterAndLoadWorkerConfig` is the cached snapshot source -- decide whether to refresh it on the capability poll or bypass it for read-mostly settings). Principle going forward: do not cache DB-backed settings on long-lived service instances; read fresh.

**Fix with:** `/t`

---

### [BUG - FIXED 2026-05-10] Stuck-scan detection missing + scanner is overengineered (rewrite together)
**Date:** 2026-05-09 (stuck-scan) | **Expanded:** 2026-05-10 (overengineering rolled in) | **Fixed:** 2026-05-10
**Affects:** ScanJobs table, Features/ServiceControl/StuckJobDetectionService.py, WorkerService/Main.py, Features/FileScanning/FileScanningBusinessService.py, Features/FileScanning/FileScanningRepository.py, Features/FileScanning/FileScanningController.py, Features/FileScanning/ContinuousScanService.py

**Fix:**
- Stuck-scan side: `StuckJobDetectionService.DetectAndCleanStuckScanJobs` added (matches the existing `DetectAndCleanStuckTranscodeJobs` shape -- two-tier detection on owning worker's heartbeat + `ScanJobs.LastUpdated` staleness). Wired into `WorkerService._DetectAndCleanStuckJobs` (startup) and `_StuckJobDetectionLoop` (recurring 120s cycle, configurable via `StuckJobDetectionIntervalSec`). Threshold read fresh from `SystemSettings.StuckScanThresholdMin` (default 15min, no caching per memory rule).
- 18a: `FindTranscodedFileMatch` + `IsValidTranscodeResolutionChange` deleted (post-`FileReplacement` `_transcoded/` subdir doesn't exist; zero external callers).
- 18b: 8 is-running methods consolidated to one `Repository.GetRunningScans(RootFolderPath=None)`. `__init__`'s self-state lookup, `StartScanning`'s claim guard, and the public `GetScanStatus` API all derive from this single query.
- 18c: `MaxConcurrentScans=2` and `CanStartNewScan` deleted (contradicted criterion 11's per-rootfolder claim semantics).
- 18d: `ScanDirectories` CRUD duplicates deleted from `FileScanningRepository`. Business-service wrappers route through `SystemSettingsRepository`. `FileScanningController.EnableContinuousScanning`/`DisableContinuousScanning` were misusing `AddOrUpdateScanDirectory` to write `ContinuousScanEnabled`/`IntervalMinutes` -- now use `SystemSettingsRepository.AddOrUpdateSystemSetting` correctly.

**Net LOC**: `FileScanningBusinessService.py` 1815 -> 1546 (-15%); `FileScanningRepository.py` -38 (ScanDir CRUD); `ContinuousScanService.py` -12 (CanStartNewScan delegate); `StuckJobDetectionService.py` +120 (additive); `WorkerService/Main.py` +14 (wiring).

**18e dropped from scope (intentional):** folding `ContinuousScanService` and `DuplicateDetectionService` into `FileScanningBusinessService` was reconsidered. `ContinuousScanService` has independent threading state (LastScanTime, ScanCount, ScanThread, StopEvent) and `DuplicateDetectionService` is only used by `Scripts/FindDuplicates.py` -- the live duplicate handling at `FileScanningBusinessService.py:310` already calls `Repository.CleanupDuplicateMediaFiles` directly. Neither merge would shrink real LOC, just relocate it. Original entry was overzealous on this point.

**Verify:**
- `py -c "import ast; ast.parse(open('Features/FileScanning/FileScanningBusinessService.py').read())"` syntax-clean.
- Scripts/SQLScripts/QueryDatabase.py sql "UPDATE ScanJobs SET LastUpdated=NOW()-INTERVAL '20 minutes', Status='Running' WHERE Id=<some completed row>" then wait one StuckJobDetectionIntervalSec cycle -> row should flip to Status='Failed' with ErrorMessage explaining the cleanup.
- `grep -rn "FindTranscodedFileMatch\|IsValidTranscodeResolutionChange\|CanStartNewScan\|MaxConcurrentScans" Features/ Scripts/` returns no hits in code (KNOWN-ISSUES.md mentions excluded).

---

### [HISTORICAL] Stuck-scan + overengineering bug (pre-fix context)
**Affects:** ScanJobs table, ContinuousScanService, DuplicateDetectionService, Features/FileScanning/ (entire feature -- 5,020 LOC across 7 files)

**Part 1: stuck-scan detection.** A worker that crashes mid-scan leaves its `ScanJobs` row in `Status='Running'` indefinitely. There is no equivalent of `StuckJobDetectionService` for scans -- nothing watches `LastUpdated` staleness, nothing resets stale rows, nothing kicks the next scheduled scan past the orphaned row. `scanning-on-activity-page.feature.md` criterion G15 surfaces the staleness as an amber UI indicator but does not auto-clean.

**Part 2: scanner is overengineered.** Audit on 2026-05-10 against the 17 success criteria in `FileScanning.feature.md` (after criteria 13-17 were added) found ~30-35% of the LOC has no contract backing. Rolling this into the stuck-scan rewrite because the structural cuts touch the same files the stuck-detection wiring will modify -- doing them separately means the second pass redoes most of the first.

Concrete cuts identified:
1. **`FindTranscodedFileMatch` + `IsValidTranscodeResolutionChange`** (~110 LOC, `FileScanningBusinessService.py:802-930`): predates `FileReplacement`. The current data flow writes transcoded output to the original path atomically -- there is no `_transcoded/` subdirectory anymore. Genuinely dead.
2. **Eight "is a scan running?" methods** in `FileScanningBusinessService.py`: `CheckForExistingRunningScan`, `IsScanRunning`, `IsScanRunningForRootFolder`, `GetRunningScanCount`, `CanStartNewScan`, `GetScanJobStatus`, `GetCurrentScanStatus`, `GetAllRunningScans`. Should collapse to one repository query backed by criteria 5, 8, 11.
3. **`MaxConcurrentScans=2` lever** (`CanStartNewScan`): contradicts criterion 11 (one scan per rootfolder cluster-wide). Dead concept post-host-affinity fix.
4. **`ScanDirectories` table/concept** (`GetScanDirectories`, `AddOrUpdateScanDirectory`, `DeleteScanDirectory`): criteria 9 and 10 use `RootFolders` exclusively. The `ScanDirectories` path has no criterion -- looks like an abandoned alternative. Pick one.
5. **`ContinuousScanService` (369 LOC) and `DuplicateDetectionService` (218 LOC) as separate classes**: criterion 5 is a timer + a call into `StartScanning`; criterion 4 is a repository query. Neither needs its own class with its own lifecycle. Fold back into `FileScanningBusinessService` -- the host-affinity claim guard from `FileScanning.feature.md` criterion 11 lives there too.

Net: ~1,500-1,800 LOC cuttable, all in cosmetic class boundaries and the dead `_transcoded/` reconciliation path.

**Look first:**
- `Features/ServiceControl/StuckJobDetectionService.py` -- natural extension point for stuck-scan; existing `_IsJobFrozen` shape (LastFrameAdvance / LastProgressUpdate threshold) translates to `ScanJobs.LastUpdated` directly.
- `Features/FileScanning/FileScanningBusinessService.py:802-930` -- dead `_transcoded/` reconciliation.
- `Features/FileScanning/FileScanningBusinessService.py:36-456` -- the eight is-running methods.
- `Features/FileScanning/ContinuousScanService.py`, `DuplicateDetectionService.py` -- merge candidates.

**Violates:** `FileScanning.feature.md` criterion 18 (added with this expansion). The stuck-scan side also violates `scanning-on-activity-page.feature.md` G15 indirectly (G15 surfaces but doesn't auto-clean).

**Flow doc gap:** `FileScanning.flow.md` exists. It documents the current per-worker tick model (which the host-affinity fix already targets to rewrite). The simplification pass should rewrite the "Continuous Mode Specifics" section in the same `/t` to keep flow + feature + code in sync.

**Fix with:** `/t` (single rewrite covering stuck-scan detection + simplification; estimate 4-6 hours since both touch the same files)

---

### [BUG - FIXED 2026-05-09] Worker claim path orders by SizeMB, ignoring Priority entirely
**Date:** 2026-05-09
**Affects:** `Repositories/DatabaseManager.py:1596,1638,1655`, `Features/TranscodeQueue/TranscodeQueueRepository.py:143,163`
**Fix:** all four claim/peek queries changed to `ORDER BY Priority DESC, DateAdded ASC`. `transcode.flow.md` Stage 2.2 updated to match. Verify post-WebService restart that the highest-priority pending job is the one a worker claims next.

The atomic claim path used by every worker (`ProcessTranscodeQueueService.py:346 -> DatabaseManager.ClaimNextPendingTranscodeJob`) orders pending rows by `SizeMB DESC, DateAdded ASC`. The `Priority` column is selected and returned but **never appears in any ORDER BY**. This means the entire `queue-priority.feature.md` work (impact-based scoring, manual override window 195-200) is computed at populate time and immediately ignored at claim time -- workers are still picking the largest file regardless of priority. Discovered after operator noticed the Queue UI default sort matched worker behavior, both ordering by SizeMB.

**Violates:** `queue-priority.feature.md` Success Criterion 11 ("The first item a worker would claim from a fresh queue per `ORDER BY Priority DESC, DateAdded ASC LIMIT 1` is a high-impact file").

**Fix:** change all four claim/peek queries to `ORDER BY Priority DESC, DateAdded ASC`. Update `transcode.flow.md:403` Stage 2.2 to match. The duplicate vertical-slice copy in `Features/TranscodeQueue/TranscodeQueueRepository.py` is dead code (legacy `DatabaseManager.py` is the live path) but should be fixed for consistency.

**Look first:** `Repositories/DatabaseManager.py` lines 1590-1686.

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

### [TECH DEBT] Remove legacy archive_TranscodeService/ and archive_QualityTestService/ directories
**Date:** 2026-05-08 | **Renamed (partial):** 2026-05-08
**Affects:** archive_TranscodeService/, archive_QualityTestService/, Scripts/StopAllTranscodeServices.py, Scripts/StopAllPythonServices.py, CLAUDE.md "Two Microservices" section, transcode.flow.md

Phase 2 of the architecture redesign unified both services into WorkerService. Renamed today to make the deprecation visible in the directory listing. The string identifiers "TranscodeService" / "QualityTestService" remain valid as logical job-type tags in ActiveJobs.ServiceName, ServiceStatus.ServiceName, and CrashRecoveryService — those must NOT be removed.

**Remaining cleanup:**
- `Scripts/StopAllTranscodeServices.py` and `Scripts/StopAllPythonServices.py` still reference the old names; harmless (process-name match returns no results) but should be deleted or repointed at WorkerService.
- CLAUDE.md "Two Microservices" section still describes the old split — needs to be rewritten to describe the unified WorkerService + capability flags.
- Once nothing reads from them for ~1 month, the `archive_*` directories can be deleted entirely.

**Look first:** `TranscodeService/` and `QualityTestService/` directory contents, `Features/ServiceControl/ServiceLifecycleManager.py:29-40` (drop the two SERVICES dict entries), `Scripts/StopAllTranscodeServices.py` (delete or repoint), CLAUDE.md "Two Microservices" section.

**Fix with:** `/n` (cleanup migration -- estimated 30 min: delete two dirs, prune SERVICES dict, sweep docs, leave string literals alone)

### [TECH DEBT] LocalStaging fallback decision duplicated across four sites
**Date:** 2026-05-08
**Affects:** Features/TranscodeJob/ProcessTranscodeQueueService.py

`ProcessJob`, `ProcessRemuxJob`, `ProcessSubtitleFixJob`, and `SetupFilePreparation` each independently decide whether LocalStaging mode falls back to InPlace when the worker has no StagingDirectory configured. The first three fix used a local variable that didn't propagate; the fourth re-read the system setting and silently kept building staging paths. Today's fix added the same guard to `SetupFilePreparation` so the four sites agree, but a future change to the fallback logic still has to be made in four places.

**Look first:** `Features/TranscodeJob/ProcessTranscodeQueueService.py:384-390, 526-530, 642-646, 828-836` -- four places computing `IsLocalStaging`. Extract `_GetEffectiveFileMode()` returning the resolved mode after applying the fallback.

**Fix with:** `/t` (single-file refactor)

### [BUG] Second concurrent job shows first job's progress
**Date:** 2025-05-05
**Affects:** TranscodeJob feature -- concurrent job progress tracking
**Criterion violated:** TranscodeJob.feature.md -- each running job must report independent progress

When MaxConcurrentJobs > 1 and a second job starts while the first is still running, the second job displays the same progress percentage and ETA as the first (e.g., both show 20.5% / ETA 01:41:41). Only one FFmpeg process is actually running.

**Look first:** `Features/TranscodeJob/ProcessTranscodeQueueService.py:169` (`GetStatus` returns single `currentProgress`), `GetCurrentTranscodeProgress()` in DatabaseManager (likely returns one row, not per-job), and `VideoTranscodingService.TranscodeVideo` (process spawning).

**Fix with:** `/t`

### [BUG] DatabaseManager.py monolith -- dual database access paths
**Date:** 2026-05-07
**Affects:** All features that still import from Repositories/DatabaseManager.py instead of their own Repository
**Criterion violated:** Feature vertical isolation -- each feature should access the database exclusively through its own Repository

`Repositories/DatabaseManager.py` (630+ lines) is the legacy data access layer. Features are supposed to use `Features/<Name>/<Name>Repository.py`, but some still call DatabaseManager directly. This creates two paths to the database: the feature Repository and the legacy monolith. Unclear where new queries should go, and changing a query may need updates in two places.

**Look first:** `Repositories/DatabaseManager.py` -- audit which features import from it. Cross-reference with each `Features/<Name>/<Name>Repository.py` to find overlap.

**Fix with:** `/n` (this is a migration, not a quick fix -- needs audit of all callers first)

### [BUG] Feature vertical boundaries do not match governed code
**Date:** 2026-05-07
**Affects:** TranscodeJob.feature.md, FileReplacement.feature.md, Services/CommandBuilderService.py, Services/FFmpegAnalysisService.py, Core/Services/PathTranslationService.py
**Criterion violated:** TranscodeJob.feature.md scope/criteria mismatch; FileReplacement.feature.md cross-feature dependency

TranscodeJob.feature.md declares scope `Features/TranscodeJob/**` + `WorkerService/Main.py`, but its criteria govern behavior in CommandBuilderService (conditional yadif, output mode), FFmpegAnalysisService (per-worker FFprobe), PathTranslationService (multi-prefix translation), and ProcessTranscodeQueueService (VMAF toggle, worker config loading). Separately, FileReplacement depends on MediaProbe for re-probing with no explicit contract.

**Look first:** TranscodeJob.feature.md criteria list -- each criterion that references a file outside the declared scope. `Features/FileReplacement/FileReplacementBusinessService.py` for the MediaProbe call.

**Fix with:** `/n` (architectural boundary redesign -- either expand TranscodeJob scope or extract worker/command-building into separate feature verticals)

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

## Fixed

### [FIXED] Services resolve tool paths from SystemSettings instead of per-worker config
**Date:** 2026-05-08 | **Fixed:** 2026-05-08
**Fix:** WorkerContext singleton. FFmpegService resolves: explicit arg > WorkerContext > cached > SystemSettings. FileReplacementBusinessService auto-reads PathTranslation from WorkerContext.

### [FIXED] LocalStaging mode crashes workers without StagingDirectory configured
**Date:** 2026-05-07 | **Fixed:** 2026-05-07
**Fix:** All three job types validate `self.OutputDirectory` before entering LocalStaging mode. NULL falls back to InPlace.

### [FIXED] Post-transcode pipeline does not complete (VMAF + file replacement not firing)
**Date:** 2026-05-07 | **Fixed:** 2026-05-07
**Fix:** Removed dead ShouldTestFile(). ProcessTranscodedFile() reads QualityTestRequired from TranscodeAttempt. FileReplacementBusinessService accepts PathTranslation, translates canonical paths before filesystem ops.

### [FIXED] Concurrent job progress invisible in UI
**Date:** 2026-05-08 | **Fixed:** 2026-05-08
**Fix:** Removed `INNER JOIN TranscodeQueue` from progress queries. Progress now uses `TranscodeProgress + TranscodeAttempts WHERE Success IS NULL`.
**Note:** Queue rows for concurrent jobs still disappear (cause unknown). Audit trigger `trg_transcodequeue_delete` is in place.

### [FIXED] Yadif deinterlacing applied to progressive files
**Date:** 2026-05-05 | **Fixed:** 2026-05-05
**Fix:** Set YadifMode=NULL, YadifParity=NULL on all profiles. CommandBuilder skips yadif when NULL.

### [FIXED] StuckJobDetector breaks distributed transcoding
**Date:** 2026-05-05 | **Fixed:** 2026-05-05
**Fix:** All destructive operations scoped by WorkerName/ClaimedBy. GetActiveJobsByService includes WorkerName. SignalHandler, CrashRecoveryService, QueueManagementService all filter by worker.

### [FIXED] Thread-limiting changes degraded worker transcode performance
**Date:** 2026-05-07 | **Fixed:** 2026-05-07
**Fix:** Reverted `lp=N`, `MEDIAVORTEX_MAX_CPU_THREADS`, Docker `cpus` limit. SVT-AV1 `lp` does not reduce OS thread count; Docker CFS throttling is counterproductive with many idle threads.
**Remaining:** 4 workers at 480p preset 6 still only use ~10% of a 64-CPU system (480p frame size limits SVT-AV1 parallelism -- separate investigation).

### [FIXED] FFmpegService.py cpu_affinity overrides Docker cpuset pinning
**Date:** 2026-05-07 | **Fixed:** 2026-05-07
**Fix:** FFmpegService.py and VideoTranscodingService.py skip affinity calls when `/.dockerenv` exists. Docker cpuset is the sole CPU isolation mechanism in containers.

### [FIXED] QueryDatabase.py sql command silently rolls back writes
**Date:** 2026-05-05 | **Fixed:** 2026-05-05
**Fix:** Added `--commit` flag. Default unchanged (rollback for safety).
