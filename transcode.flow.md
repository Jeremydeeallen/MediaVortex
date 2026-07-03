# Transcode Flow

**Slug:** transcode

**Canonical compliance + bucket + admission contract:** see `docs/superpowers/specs/2026-06-22-compliance-symmetry-design.md`. This flow doc retains the pipeline shape and stage IDs; per-stage compliance and bucket-derivation prose has been consolidated into the spec.

Entry point: `StartMediaVortex.py` (all services) or individual service scripts.

## Stage Overview

```
SCAN -> PROBE -> ASSIGN -> RECOMPUTE -> QUEUE -> TRANSCODE -> DISPOSITION -> VMAF -> ACTION
 ST1     ST2      ST3        ST4         ST5       ST6          ST7         ST8     ST9
```

ST<N> stage IDs are stable; never renumbered (`.claude/rules/flow-docs.md`). The detailed stage headings below carry both the historical "Stage N" label and the ST<N> ID so existing references in feature docs ("Stage 6", "Stage 3.5") still resolve. New code anchors use `# see transcode.ST<N>`.

Stages ST1-ST5 require user action. Stages ST6-ST9 are automatic once WorkerService is running:
- QUEUE -> TRANSCODE (ST5 -> ST6): automatic (service polls for Pending items)
- TRANSCODE -> DISPOSITION -> VMAF or ACTION (ST6 -> ST7 -> ST8 or ST9): `Features/QualityTesting/Disposition/PostTranscodeDispositionDecider.Decide` is the single decision function -- reads `TranscodeAttempts.QualityTestRequired` + `VMAF` + `PostTranscodeGateConfig` and returns one of `Replace`/`BypassReplace`/`Pending`/`Requeue`/`Discard`/`NoReplace`. `DispositionDispatcher.Dispatch` routes accordingly: `Pending` enqueues to QualityTestingQueue (ST8); any other disposition goes straight to ST9.
- VMAF -> ACTION (ST8 -> ST9): automatic if VMAF is within threshold range (default 80-100)

**Service dependency model:** Both services communicate exclusively via PostgreSQL. No HTTP calls between them. Each polls the database for its own work. FileReplacement is a library (not a service) that runs in whatever process calls it -- WorkerService when QualityTest=OFF, WorkerService's quality test loop when QualityTest=ON, WebService for manual replacement.

---

## Seams

Stage-transition data contracts. See `Features/TranscodeJob/TranscodeJob.feature.md` and `Features/FileReplacement/FileReplacement.feature.md` for intra-feature seams.

| ID | Transition | Producer (writer) | Wire shape | Consumer (reader) expects | Verification |
|---|---|---|---|---|---|
| S1 | `ST5 -> ST6` (QUEUE -> TRANSCODE) | `QueueManagementBusinessService` | `TranscodeQueue.(Id BIGINT, StorageRootId BIGINT, RelativePath TEXT, AssignedProfile TEXT, ProcessingMode TEXT, AcceptsInterlaced BOOLEAN) Status='Pending'` | `Features/TranscodeQueue/TranscodeQueueRepository.ClaimNextPendingTranscodeJob` -- atomic claim via `FOR UPDATE OF tq SKIP LOCKED`; gated by three additive filters (a) `BuildClaimPredicate` for `TranscodeEnabled` + `Status='Online'`, (b) NVENC EXISTS gate (`Profiles.usenvidiahardware=0` OR `Workers.nvenccapable=TRUE`), (c) `BuildAllowedProfilesPredicate` for the per-worker profile allowlist (`Workers.AllowedProfiles IS NULL` OR `mf.AssignedProfile = ANY(string_to_array(...))` -- NULL = accept all, `""` = accept none, CSV = explicit allowlist) | `SELECT COUNT(*) FROM TranscodeQueue WHERE Status='Pending'` decrements by 1 per claim; `Tests/Contract/TestClaimAuthority.py` + `Tests/Contract/TestWorkerAllowedProfiles.py` |
| S2 | `ST6 -> ST7` (TRANSCODE -> DISPOSITION) | `ProcessTranscodeQueueService` (on encode success) | `TranscodeAttempts.(Id BIGINT, Success=NULL, QualityTestRequired BOOLEAN, VMAF NULL or score)` + `TemporaryFilePaths.(TranscodeAttemptId, SourceStorageRootId BIGINT, SourceRelativePath TEXT, OutputStorageRootId BIGINT, OutputRelativePath TEXT, LocalSourcePath TEXT NULL, LocalOutputPath TEXT NULL)`. Paths stored as typed pair `(StorageRootId, RelativePath)`; worker-local staging paths persisted in the LocalSourcePath/LocalOutputPath columns when active. Worker resolves canonical to local via `Path.Resolve(Worker)`; UI/logs use `Path.CanonicalDisplay(GetPrefixMap())`. **In-place (default):** resolved output path ends in `-mv.mp4.inprogress` adjacent to source on shared mount; `TranscodeAttempts.VMAF=NULL` at seam crossing. **Staged Mode B (opt-in, `LocalVmafFirst=FALSE`):** local `.inprogress` produced in `Workers.LocalScratchDir/<MediaFileId>/`; copy-back step ships it to canonical before this seam fires so downstream consumers see the canonical path unchanged; `VMAF=NULL` at crossing. **Staged Mode A (opt-in, `LocalVmafFirst=TRUE AND QualityTestEnabled=TRUE`):** worker runs libvmaf locally and populates `TranscodeAttempts.VMAF` BEFORE this seam; passing scores get copy-back identical to Mode B, failing scores reach this seam with no canonical `.inprogress` written | `Features/QualityTesting/Disposition/DispositionDispatcher.Dispatch(AttemptId)` reads `TranscodeAttempts.QualityTestRequired` + `VMAF` + `PostTranscodeGateConfig`; routes to `QualityTestQueueService.AddToQualityTestQueue` (ST8) when VMAF=NULL and QualityTestRequired=TRUE, or directly to the action handler for the disposition `PostTranscodeDispositionDecider.Decide` returned (Mode A staged-VMAF case skips ST8 and decides Replace/Requeue/NoReplace inline). Reads canonical TFP pair; staging is transparent to the consumer | `SELECT COUNT(*) FROM TemporaryFilePaths WHERE TranscodeAttemptId IN (SELECT Id FROM TranscodeAttempts WHERE Success IS NULL)` -> in-flight count; `Tests/Contract/TestLocalStaging.py` for the staging path; `Tests/Contract/TestDispositionDispatcher.py` for the disposition decomposition |
| S3 | `ST7 -> ST8` (DISPOSITION -> VMAF) | `DispositionDispatcher.Dispatch` when `Disposition='Pending'` (VMAF=NULL AND QualityTestRequired=TRUE) | `QualityTestingQueue.(Id BIGINT, TranscodeAttemptId BIGINT) Status='Pending'`; `TranscodeAttempts.ForceDisposition IS NULL` | `DatabaseManager.ClaimQualityTestJob` -- atomic claim; `QualityTestingBusinessService.ExecuteVMAF` reads source+output paths from `TemporaryFilePaths` | `SELECT COUNT(*) FROM QualityTestingQueue WHERE Status='Pending'` decrements by 1 per claim |
| S4 | `ST8 -> ST9` (VMAF -> ACTION) | `QualityTestingBusinessService` | `TranscodeAttempts.vmaf DOUBLE PRECISION NOT NULL, QualityTestCompleted=TRUE`; `ForceDisposition TEXT NULL` (operator override) | `Features/QualityTesting/Disposition/PostTranscodeDispositionDecider.Decide` (called by `DispositionDispatcher.Dispatch`) -- Replace when `VMAF >= VmafAutoReplaceMinThreshold` and `ForceDisposition IS NULL`; operator `ForceDisposition` bypasses the threshold | `SELECT COUNT(*) FROM TranscodeAttempts WHERE QualityTestCompleted=TRUE AND VMAF IS NULL` -> 0; `Tests/Contract/TestDispositionDecider.py` |
| S5 | `ST9 -> done` (ACTION -> end) | `FileReplacementBusinessService.ProcessFileReplacement` dispatching to `TranscodedOutputPlacement.Execute` | `MediaFiles.(StorageRootId, RelativePath, FileName, Codec, Resolution, SizeMB, TranscodedByMediaVortex or RemuxedByMediaVortex = TRUE, etc.)` updated; `MediaFilesArchive` row written; `TranscodeAttempts.FileReplaced=TRUE`; `TemporaryFilePaths` row deleted at the disposition chokepoint. On update failure the rename is rolled back; no orphan `-mv.<ext>` on disk; `Success=False` carries the real update error. See `Features/FileReplacement/transcoded-output-placement.feature.md` C13/S4 (BUG-0067). | `MediaFiles` is the authoritative post-replacement record; `MediaFilesArchive` has the pre-replacement snapshot | `SELECT COUNT(*) FROM TemporaryFilePaths tfp JOIN TranscodeAttempts ta ON ta.Id = tfp.TranscodeAttemptId WHERE ta.FileReplaced=TRUE` -> 0 (no orphaned TFP after successful replace); `Tests/Contract/TestFileReplacementRollbackOnUpdateFailure.py` (3/3 PASS) for the rollback path |
| S6 | `ST3 / ST4 / ST5 / ST6 -> any consumer of resolution semantics` | Any scan/compliance/queue/encode code holding a resolution string | `MediaFiles.Resolution TEXT` (raw `'WIDTHxHEIGHT'` from ffprobe) + `MediaFiles.ResolutionCategory TEXT` (`'480p'`/`'720p'`/`'1080p'`/`'2160p'`) | Typed `Resolution` + `ResolutionTier` value objects via `Core/Resolution/`. `Resolution.FromAny` is the sole string parser; `ResolutionTierRegistry.FromDims` (max-edge) + `FromCategory` are the sole boundary maps; `WidthAnchoredScalePolicy.Decide` is the sole producer of `scale=w=...:h=-2` filter strings; tier thresholds live in the `ResolutionTiers` DB table (data-driven, operator-tunable, OCP). No raw resolution-string `==` / `!=` compares remain in the encode + compliance call chain. | `Tests/Contract/TestResolution.py` + `TestResolutionTier.py` + `TestScalePolicy.py` + `TestEncoderKnobNormalizeResolution.py`; live MIB-II re-encode (TranscodeAttempt 37754) -- output 1280x694, FileReplaced=TRUE, 82.94% reduction. See `Core/Resolution/resolution-types.feature.md`. |

---

## Stage 1: SCAN -- File Discovery (`ST1`)

**Trigger:** User clicks scan or calls `POST /api/Scan/Start`

**Code path:**
- `Features/FileScanning/FileScanningController.py` -> `FileScanningViewModel.StartScanning()` -> `FileScanningBusinessService.StartScanning()`
- Recursively walks directory tree via `FileManagerService`
- For each media file: inserts/updates `MediaFiles` row with FilePath, FileName, SizeMB

**Tables written:** MediaFiles (insert/update), RootFolders (LastScannedDate), ScanJobs (progress)

**Safety guards:**
- Duplicate detection: existing files by path are updated, not re-inserted
- Concurrent scan limit: max 2 scans at once

**Output:** MediaFiles rows with basic file info (no metadata yet)

**Orphan-profile claim guard (2026-06-04):** `DatabaseManager.ClaimNextPendingTranscodeJob` joins `TranscodeQueue` to `Profiles` on `AssignedProfile = profilename` and requires `Profiles.profilename IS NOT NULL`. Queue rows whose `AssignedProfile` does not match any current `Profiles.profilename` (renamed, deleted, typo) stay `Pending` -- they are not claimed and are not silently failed. Operator action: fix the queue row's `AssignedProfile` to a live profile name (or update the profile to match), then the worker picks it up on the next poll.

---

## Stage 2: PROBE -- FFprobe Metadata Extraction (`ST2`)

**Trigger:** Two paths:
1. **Automatic after scan** -- `FileScanningBusinessService.PerformScan()` Step 7 calls `MediaProbeService.ProbeFilesNeedingMetadata(RootFolderId)` at the end of every scan. This is the primary path -- every scanned file is probed in the same operation.
2. **Manual** -- `POST /api/MediaProbe/ProbeAll` or `/api/MediaProbe/Probe/{id}`.

**Code path:**
- `Features/MediaProbe/MediaProbeController.py` -> `MediaProbeBusinessService.ProbeFile()` -> `_ExecuteProbe()`
- Runs `ffprobe` on each file
- Extracts: Resolution, Codec, VideoBitrateKbps, AudioBitrateKbps, DurationMinutes, FrameRate, AudioLanguages, HasExplicitEnglishAudio, SubtitleFormats, ContainerFormat, etc.
- After successful probe: calls `RecomputeForFiles([MediaFileId])` which populates `PriorityScore`, `AssignedProfile`, `IsCompliant`, and `RecommendedMode` in a single pass (see Stage 3.5).

**Tables written:** MediaFiles (all metadata columns, FFProbeFailureCount, plus PriorityScore/AssignedProfile/IsCompliant/RecommendedMode via the recompute hook)

**Safety guards:**
- FFprobe failure limit: files with 3+ failures are permanently skipped (resettable via ResetFailures endpoint)
- Sets `HasExplicitEnglishAudio`: NULL (not probed), true (English found), false (confirmed non-English)
- Recompute failure does NOT roll back the probe -- metadata is always saved.

**Output:** MediaFiles rows with full metadata and computed routing fields. `HasExplicitEnglishAudio` is the critical field for queue safety. `RecommendedMode` determines whether the file enters the Transcode or Remux pipeline.

**Path handling note:** `FFmpegService.ExecuteFFprobe` is handed a worker-native path string (the output of `Path.Resolve(Worker)`); it performs no separator translation. The worker OS owns the separator. `ParentDir` / `Normalize` helpers in `Core/Path/LocalPath.py` delegate to `os.path` and do not rewrite separators across platforms.

---

## Stage 3: ASSIGN -- Profile Assignment (`ST3`)

**Trigger:** User assigns profiles in UI

**Code paths (three ways):**
1. Per-folder bulk: `POST /api/Profiles/AssignProfileToRootFolder` -> updates `MediaFiles.AssignedProfile` for all files in folder
2. Per-title via `/Work/<bucket>` page: per-series profile override via `SeriesProfiles` table
3. At queue time: QueueByFolder and AddSuggestionsToQueue both accept ProfileId and assign it to files before queuing

**Tables written:** MediaFiles.AssignedProfile (stores profile name string, not ID), SeriesProfiles (target resolution per series)

**Note:** AssignedProfile is a string field storing ProfileName, not a foreign key. Profile lookup happens at transcode time.

---

## Stage 3.5: RECOMPUTE -- Priority, Compliance, and Routing Materialization (`ST4`)

`RecomputeForFiles(MediaFileIds)` writes four legacy cached columns (`AssignedProfile`, `PriorityScore`, `IsCompliant`, `RecommendedMode`) and five new bucket columns (`WorkBucket`, `OperationsNeededCsv`, `ComplianceGateBlocked`, `ComplianceEvaluatedAt`, `HasForcedSubtitles`) on each MediaFile in one bulk UPDATE per batch. The compliance evaluation pipeline is owned by `Features/Compliance/compliance.flow.md` and `Features/Compliance/compliance.feature.md`. Triggers: probe completion, file replacement completion, AssignedProfile change, admin `POST /api/Compliance/Recompute`.

**Output:** Every MediaFiles row carries up-to-date routing fields. Consumers:
- `NextTranscodeBatch(Drive)` reads `NeedsTranscode` for the TV / Movies "Next Batch" cards on the Transcode pane.
- `SmartPopulateQueue(Mode='Quick'|'Remux'|'AudioFix')` reads `NeedsQuick` / `RecommendedMode` for the Quick Fix / Remux / AudioFix cards.
- Activity page compliance widget reads `IsCompliant` for library-wide stats.
- No consumer recomputes -- all read the materialized columns.

See `Features/TranscodeQueue/priority-materialization.feature.md` and `Features/TranscodeQueue/transcode-vs-remux-routing.feature.md` for criteria.

---

## Stage 4: QUEUE -- TranscodeQueue Population (`ST5`)

**Trigger:** Multiple paths to queue files:

| Path | Endpoint | Safety guards applied |
|------|----------|----------------------|
| Full populate | `POST /api/TranscodeQueue/PopulateQueue` | All guards (audio, resolution, VMAF, CRF floor) |
| Work bucket: queue by folder | `POST /api/WorkBucket/QueueByFolder` | Audio language, probed (Resolution NOT NULL), dedup, already-transcoded |
| Work bucket: batch (NextTranscodeBatch -- TV/Movies cards; SmartPopulate -- Quick Fix/Remux/AudioFix cards) | `POST /api/WorkBucket/AddToQueue` | Dedup only (user explicitly chose files) |
| Single file add | `POST /api/TranscodeQueue/AddJob` | All guards (audio, resolution, VMAF, CRF floor) |

**Full populate code path** (most guards):
- `Features/TranscodeQueue/TranscodeQueueController.py` -> `QueueManagementBusinessService.PopulateQueueFromMediaFiles()`
- Gets files with assigned profiles, ordered by size DESC
- For each file, checks:
  1. Already in queue? Skip
  2. Previously transcoded with VMAF >= 80? Skip
  3. Previously transcoded with VMAF < 80? Check CRF adjustment. If adjusted CRF < 15 floor -> log to ProblemFiles, skip
  4. `HasExplicitEnglishAudio = false`? Skip (NULL is allowed through)
  5. **Marginal-savings gate** (new behaviour, criterion-tracked in `marginal-savings-gate.feature.md`): admit when source resolution >= target resolution AND estimated savings >= `SystemSettings('MinTranscodeSavingsMB')`. Same-resolution-target combinations (e.g. 720p -> 720p with a slower preset / lower CRF) are admitted as long as savings clear the threshold. Upscales (source < target) are always blocked.
- Creates TranscodeQueueModel, saves to TranscodeQueue

**QueueByFolder code path** (Media page `+` button):
- `Features/WorkBucket/WorkBucketController.py` -> `QueueByFolder()`
- SQL query filters: not transcoded, not in queue, `HasExplicitEnglishAudio IS NULL OR true`, SizeMB > 0
- Passes to `AddSuggestionsToQueue()` which assigns profile and consults the marginal-savings gate before inserting queue rows.

**Tables written:** TranscodeQueue (new items), ProblemFiles (if CRF adjustment fails)

**Safety guards summary:**
- **Audio language** (CRITICAL): files with `HasExplicitEnglishAudio = false` blocked at all queue paths
- **VMAF quality gate**: files with VMAF >= 80 not re-transcoded. Bypassed by `AddJobToQueue(ForceAdd=True)` (used by `QueueAdmissionAppService.AdmitOne` from /Work/<bucket> per-row Queue button); WARN log records the override -- see `TranscodeQueue.feature.md` C11 [BUG-0078]
- **CRF floor**: adjusted CRF cannot go below 15; files logged to ProblemFiles
- **Marginal-savings gate** (`marginal-savings-gate.feature.md`): see below.
- **Dedup**: files already in queue are skipped
- **No-savings filter**: files with `MediaFiles.LastTranscodeOutcome = 'NoSavings'` are blocked from re-queueing at all entry paths (set by Stage 7 post-flight gate)

**Marginal-savings gate (estimated bytes saved):**

Replaces the legacy "source must be strictly greater than target resolution" filter. The new evaluator returns `(admit, reason)` per file. Block reasons: `Upscale`, `MarginalSavings`, `MissingProfile`.

Estimated target size formula:

| Profile shape | Formula | Notes |
|---|---|---|
| `ProfileThresholds.VideoBitrateKbps > 0` | `target_mb = ((video_kbps + audio_kbps) * duration_min * 60) / (8 * 1024)` | Same formula as `CalculatePriority`. Used for fixed-bitrate profiles. |
| `ProfileThresholds.VideoBitrateKbps = 0` (CRF only) | `target_mb = (CrfBitrateEstimates.EstimatedKbps * duration_min * 60) / (8 * 1024)` | Lookup keyed on `(Codec, TargetResolution, CRF)`. The estimate table is normalized, GUI-editable, and seeded from observed `TranscodeAttempts` averages. |
| Estimate row missing for `(Codec, Resolution, CRF)` | (no estimate computed) | Gate **fails open** -- file admitted, single `WARNING` logged per missing key per populate run. |

Configuration knobs (data-driven, all in **dedicated normalized tables -- not the legacy SystemSettings KV store**, all GUI-editable on the `/settings` page in the "Queue Tuning" card):

| Knob | Storage | Default |
|---|---|---|
| Threshold | `QueueAdmissionConfig.MinTranscodeSavingsMB` (single-row config, `Id=1` CHECK) | 150 |
| Missing-estimate policy | `QueueAdmissionConfig.MissingEstimatePolicy` | `'admit'` (fail-open) |
| CRF -> bitrate estimates | `CrfBitrateEstimates` table, columns `(Id, Codec, Resolution, Crf, EstimatedKbps, LastUpdated, Source)` | seeded from `TranscodeAttempts` history on migration |

Both tables are read fresh per call (no caching, per the standing rule against cached DB-backed settings -- see `memory/feedback_no_cached_db_settings.md`).

**Priority / claim order:**

Queue insertion writes `Priority = 0`. Workers claim largest non-compliant first, with a 195-200 window reserved for manual overrides (operator Priority modal, AudioFix folder-pin hints). The full contract is owned by `Features/TranscodeQueue/queue-priority.feature.md` -- not restated here.

Queue admission (whether a file enters the queue at all) is owned by `Features/TranscodeQueue/marginal-savings-gate.feature.md`. The estimated-bytes-saved math lives there now, not in the claim path.

---

## Stage 5: TRANSCODE -- FFmpeg Job Execution (`ST6`)

**Trigger:** WorkerService running with TranscodeEnabled=TRUE (started via `StartMediaVortex.py` or per-worker Online status)

**Code path:**
- `WorkerService/Main.py` -> `ProcessTranscodeQueueService.ProcessQueueLoop()`
- Main loop: polls TranscodeQueue for Pending items, spawns worker threads (up to MaxConcurrentJobs)
- Each worker calls `ProcessJob()`:
  1. Create ActiveJob record
  2. Update queue status -> Running
  3. Load MediaFile metadata
  4. **Pre-flight: source file existence check.** Translate `MediaFile.FilePath` to local via PathTranslation, call `os.path.exists()`. If missing: increment `MediaFiles.FFprobeFailureCount`, record `LastFFprobeError = "Source file missing on disk: ..."`, delete TranscodeQueue row, delete ActiveJob row, return -- **no TranscodeAttempt is created**. Stops the dead-file retry loop where queue population kept re-adding rows for files deleted between scan and transcode.
  5. Create TranscodeAttempt record (only if source confirmed present)
  6. Load profile thresholds (CRF, bitrate, codec settings)
  7. File preparation (see File Staging below)
  8. Build FFmpeg command. Video args are profile-driven (libsvtav1 / av1_nvenc, preset, CRF, film grain, bitrates). **Audio args are produced by the audio vertical's public seam** -- the shape calls `AudioPolicyResolver.GetEffectivePolicy(MediaFile)` + `AudioStreamProbe.Probe(InputPath)` + `AudioFilterEmitter.EmitTracks(MediaFile, Policy, AudioStreams)` and concatenates the returned `TrackBlock`s into the argv. The shape NEVER constructs loudnorm / dialnorm / handler_name args directly; everything audio-related is the audio vertical's contract. Post-flight: `FileReplacement.TranscodedOutputPlacement` calls `AudioStateService.MarkAudioComplete` to flip the row's audio-state machine. See `Features/AudioNormalization/audio-normalization.feature.md` `## Cross-Vertical Contract` for the locked seam list.
  9. Execute FFmpeg via `VideoTranscodingService.TranscodeVideo()`
  10. Monitor progress (frames / total_frames), update TranscodeProgress
  11. On completion: record TranscodeAttempt with size reduction, duration, command

**File staging (in-place by default; per-worker local-scratch opt-in):**
- **Default path (no staging).** FFmpeg reads directly from the network mount. On the primary machine this is the raw DB path (e.g. `T:\ShowName\file.mkv`). On remote workers, `PathTranslationService.ToLocalPath()` converts to the local mount (e.g. `/mnt/media_tv/ShowName/file.mkv`). FFmpeg writes the encoded output as `<basename>-mv.mp4.inprogress` **next to the source**. `FileReplacement` renames `-mv.mp4.inprogress` → `-mv.mp4` and deletes the original. See `Features/FileReplacement/transcoded-output-placement.feature.md` for the durable contract.
- **Opt-in local staging (per `Features/TranscodeJob/local-staging.feature.md`).** When `Workers.LocalStagingEnabled=TRUE`, `Workers.LocalScratchDir` is set, and source `SizeMB >= LocalStagingConfig.MinSizeMB` (default 500), `LocalStagingService.StageSource` bulk-copies the source from the shared mount to `<LocalScratchDir>/<MediaFileId>/<basename>` before ffmpeg runs. The encode produces `<LocalScratchDir>/<MediaFileId>/<basename>-mv.<ext>.inprogress`. After `_VerifyInProgressFile` succeeds, the worker takes one of two disposition modes per the `Workers.LocalVmafFirst` flag:
  - **Mode B (default, `LocalVmafFirst=FALSE` or `QualityTestEnabled=FALSE`).** `_CopyBackStagedOutput` ships the local `.inprogress` to the canonical side-by-side path on the shared mount; downstream `FileReplacement` + cross-worker VMAF reach it unchanged.
  - **Mode A (`LocalVmafFirst=TRUE` AND `QualityTestEnabled=TRUE`).** `QualityTestingBusinessService.RunLocalVmafForAttempt` runs libvmaf against the local source/output pair BEFORE any copy-back, writes the score to `TranscodeAttempts.VMAF`. Score >= `PostTranscodeGateConfig.VmafAutoReplaceMinThreshold` -> falls through to the Mode B copy-back path; `PostTranscodeDispositionService` reads the populated VMAF, decides `Replace`, and `FileReplacement` runs against the canonical paths. Score < min -> `SkipModeBCopyBack=True`, `_CleanupLocalScratchForAttempt` fires, no canonical `.inprogress` is written, and `PostTranscodeDispositionService` decides `Requeue / VmafBelowMin` from the same VMAF read (no `FileReplacement`, audit only). Mode A `RunLocalVmafForAttempt` failure -> falls through to Mode B so a different worker can claim the canonical VMAF row.
  `LocalStagingService.CleanupJobScratchDir` removes the per-job scratch subdir on success; `_CleanupFailedAttemptFiles` does the same on failure via `LocalStagingService.Cleanup` on each local path. `CrashRecoveryService._SweepLocalStagingOrphans` runs on `RecoverServiceJobs("TranscodeService")` startup and deletes numeric scratch subdirs whose `TemporaryFilePaths`/`TranscodeAttempts` rows show no in-flight work for this worker.
  Motivation: the Microsoft SMB client on Windows drops long-duration file handles under GPU-paced reads (per `memory/feedback_ms_nfs_client_unreliable.md`); bulk-copy uses a different IO pattern SMB handles reliably. Worker-gated + size-gated so backplane-NFS workers (Linux containers) keep the in-place path unchanged.

**Path handling for distributed workers:**
- DB stores paths as typed pair `(StorageRootId BIGINT, RelativePath TEXT)`. No drive letter, no UNC, no platform separator in the canonical form.
- `Path.Resolve(Worker)` joins the worker-local prefix (from `StorageRootResolutions.AbsolutePath`) with `RelativePath` using the worker-platform separator. Returns a worker-native string suitable for ffmpeg / `os.open`.
- `Path.CanonicalDisplay(GetPrefixMap())` renders Windows-shaped display (`T:\Show\file.mkv`) for UI / logs regardless of worker OS.
- Worker passes the resolved string straight to ffmpeg. `CommandBuilder._NormalizeFfmpegPath` does NOT rewrite separators; the worker OS owns them.

**Key files for file staging:**
- `Features/TranscodeJob/ProcessTranscodeQueueService.py` -- `SetupFilePreparation()` resolves the worker-local source path via `Path.Resolve(Worker)`
- `Models/CommandBuilder.py` -- `BuildFFmpegCommand` places the `.inprogress` output next to the source; `_NormalizeFfmpegPath` performs no cross-platform separator rewrites
- `Core/Path/Path.py` -- `Resolve(Worker)` / `CanonicalDisplay(prefixes)` -- the only path-shape boundary
- `Core/Path/LocalPath.py` -- `os.path` wrapper for worker-local operations (basename / dirname / exists / join) on the output of `Resolve`
- `Services/PathTranslationService.py` -- still in use by a few legacy verticals; full deprecation deferred to Phase 9

**FFmpeg command structure:**
- Executable: from `Workers.FFmpegPath` (falls back to `FFmpegMaster\bin\ffmpeg.exe`)
- Codec: libsvtav1 (all profiles)
- Preset: 6-8 (from profile)
- Quality: CRF from ProfileThresholds.Quality (adaptive if retranscode)
- Film grain: from profile
- Output: `<source_dir>/<basename>-mv.mp4.inprogress` (renamed to drop `.inprogress` by FileReplacement)

**Tables written:** TranscodeAttempt (new), TranscodeFiles (aggregated), TranscodeProgress (real-time), ActiveJobs (with WorkerName), MediaFilesArchive, TranscodeQueue (status -> Running, ClaimedBy -> WorkerName), TemporaryFilePaths (canonical paths)

**Safety guards:**
- Atomic job claiming: `SELECT FOR UPDATE SKIP LOCKED` prevents two workers claiming the same job
- Crash recovery: stuck jobs (>12h) reset to Pending on service start
- ActiveJob tracking prevents duplicate processing (includes WorkerName for distributed identification). `ActiveJobs.ProcessId` is the worker's Python PID; `ActiveJobs.FFmpegPid` (added by stuck-job-detection.feature.md) is the FFmpeg subprocess PID -- the only legitimate kill target for stuck-job cleanup
- Worker heartbeat: 30-second interval, stale >5 min = worker offline, its jobs marked stuck
- Recurring stuck-job detection: each worker self-monitors its own jobs every `SystemSettings.StuckJobDetectionIntervalSec` (default 120s). Tier 1 catches dead workers via heartbeat, Tier 2 catches frame-stagnation hangs (default 5 min via `FrozenProgressThresholdMin`), Tier 3 catches dead-FFmpeg cases via `FFmpegPid` liveness + name check. Cleanup kills only `FFmpegPid` (never the worker), gated by host-locality. See `Features/ServiceControl/stuck-job-detection.flow.md`.
- CPU thermal management: waits for cool-down between jobs
- FFmpeg errors captured in TranscodeAttempt.ErrorMessage

### ST6 Strategy variants -- per-ProcessingMode `BuildCommand` + `HandleResult`

ST6 has one orchestration body (`Features/TranscodeJob/Worker/JobProcessor.Process`) and per-mode Strategy classes (`Features/TranscodeJob/Worker/Strategies/<Mode>JobStrategy.py`). Each Strategy implements:

| Mode | Strategy class | BuildCommand emits | HandleResult marks |
|---|---|---|---|
| Transcode | `TranscodeJobStrategy` | Full re-encode argv via `EncodeShapeRegistry.Get('Transcode').Build` | `QualityTestRequired=<config>` |
| Remux | `RemuxJobStrategy` | `-c:v copy` + audio normalize (loudnorm) + mp4 container | `QualityTestRequired=False` (no VMAF; remux quality is byte-defined) |
| AudioFix | `AudioFixJobStrategy` | Same as Remux but with audio-policy attestation forced | `QualityTestRequired=False` |
| SubtitleFix | `SubtitleFixJobStrategy` | Subtitle extraction + stream selection per `Services.FFmpegAnalysisService.SelectPreferredSubtitleStream` | `QualityTestRequired=False` |
| Quick | `RemuxJobStrategy` (alias) | Same as Remux | `QualityTestRequired=False` |

The orchestration shape (ActiveJob create -> Mark Running -> Load MediaFile -> Setup file prep -> BuildCommand -> ExecuteFFmpeg -> Verify output -> `PostEncodeMeasurementService.Measure` -> HandleResult -> Cleanup) is identical for every mode. PostEncode measurement runs universally; per-mode strategies cannot opt out.

Adding a new ProcessingMode is one `INSERT INTO ProcessingModes` row + one `<NewMode>JobStrategy` class + one `Registry.Register('NewMode', NewModeJobStrategy)` line in `ProcessTranscodeQueueService.ProcessJob` registry initialization. No other file changes.

Audio-policy attestation contract (was in `remux.flow.md` ST9): `Strategy.HandleResult` is called AFTER `PostEncodeMeasurementService.Measure` has populated `TranscodeAttempts.AudioPolicyResolved` and `AudioTracksEmittedJson`. Mode-specific HandleResult bodies MUST NOT consume these columns directly -- they belong to the downstream ComplianceGate evaluation.

Same-slot rename safety (was in `remux.flow.md` ST11): all post-flight modes use `Features/FileReplacement/FilesystemRenameWithBackup` with `Apply` -> `Commit` (on success) or `Rollback` (on update failure). Source file is never at the path FFmpeg writes to (PrepareReplacement moves it). Both layers must independently fail before any data loss; the 2026-05-09 bug pattern cannot recur.

**Historical-attempt attestation (post-2026-06-28 only).** The `JobProcessor.Process` Template Method calls `PostEncodeMeasurementService.Measure` AFTER every successful FFmpeg run, populating `TranscodeAttempts.AudioPolicyResolved` + `AudioTracksEmittedJson`. Pre-2026-06-28 TranscodeAttempts (created by the deleted three-processor pipeline) have these columns NULL by construction -- they predate the universal attestation hook. Operator-facing analytics that group by attestation should filter `AttemptDate >= '2026-06-28'` or treat NULL as "not measured." No backfill is provided; per the `transcode-worker-unification` directive Out of Scope, historical attempts remain NULL.

---

## Stage 6: DISPOSITION -- Post-Transcode Decision (`ST7`)

**Trigger:** Worker calls `DecidePostTranscodeDisposition(TranscodeAttemptId)` immediately after a successful transcode (TranscodeAttempt.Success=true). Single function, single call site, single return.

The disposition decision is **the only post-transcode branch point**. It reads from data-driven config and returns `(Disposition, Reason, AuditPayload)`. All five legacy decision sites (`ShouldQualityTestService`, `_ReplaceFileDirectly`, `CheckAndTriggerAutoReplace`, `ProcessFileReplacement`'s `BypassVMAFCheck` parameter, `ProcessFileReplacementWithVMAF`) are retired in favor of this one function. See `Features/QualityTesting/post-transcode-disposition.feature.md`.

**Inputs (data-driven):**

| Input | Source |
|---|---|
| `TranscodeAttempt.QualityTestRequired` | per-attempt flag, set at attempt creation from `Profiles.QualityTestRequired` (per-profile column, editable on `/settings` profile cogs modal). When the profile's flag is FALSE, every attempt for that profile skips VMAF. |
| `TranscodeAttempt.NewSizeBytes` vs `OldSizeBytes` | post-flight savings gate |
| `QualityTestResults.VMAFScore` | populated by VMAF run, NULL when no test ran |
| `VmafCapableWorkerOnline` (computed) | `SELECT 1 FROM Workers WHERE QualityTestEnabled=TRUE AND Status='Online' AND LastHeartbeat > NOW() - INTERVAL '90 seconds'`. Replaces the legacy `ServiceStatus.QualityTestService` row, which was a fossil written only by the retired QualityTestService process. |
| `PostTranscodeGateConfig.VmafAutoReplaceMinThreshold` | typed column, default 88 |
| `PostTranscodeGateConfig.VmafAutoReplaceMaxThreshold` | typed column, default 98 |
| `PostTranscodeGateConfig.WhenVmafUnavailable` | `'block'` (default, safe) or `'bypass'` (operator opt-in) |
| `PostTranscodeGateConfig.QualityTestEnabled` | typed BOOLEAN, default TRUE. Operator master switch -- when FALSE, every successful transcode short-circuits to `BypassReplace` / `QualityTestingGloballyDisabled`. Editable on `/settings` Post-Transcode card. |

**Decision table** (canonical -- code MUST mirror this 1:1):

| Success | NewSize >= OldSize | QualityTestRequired | VMAF score | Disposition | Reason |
|---|---|---|---|---|---|
| false | n/a | n/a | n/a | `Discard` | `TranscodeFailed` |
| true (and `QualityTestEnabled=FALSE` globally) | n/a | n/a | n/a | `BypassReplace` | `QualityTestingGloballyDisabled` |
| true | true (no savings) | any | any | `Discard` | `NoSavings` |
| true | false | false | n/a | `BypassReplace` | `QualityTestNotRequired` |
| true | false | true | NULL | `Pending` | `AwaitingVmaf` |
| true | false | true | < min | `Requeue` | `VmafBelowMin` |
| true | false | true | >= min, <= max | `Replace` | `VmafPassed` |
| true | false | true | > max | `NoReplace` | `VmafAboveMax` |

**Note (2026-05-29):** the legacy `VmafCapableWorkerOnline` / `WhenVmafUnavailable` branching is retired. `Pending/AwaitingVmaf` is now the only outcome when VMAF is required and no score is available -- the row is enqueued to `QualityTestingQueue` regardless of whether a capable worker is currently online. Operators see the pending work in the queue surface (Stage 7) and either bring a capable worker online OR override the row to force an immediate disposition. `VmafServicePaused` / `VmafServicePausedBypassed` reasons remain in the closed enum for audit history (legacy attempts) but are no longer emitted by new decisions. See `Features/QualityTesting/qt-queue-visibility-and-override.feature.md`.

**Disposition outcomes:**

| Disposition | What happens |
|---|---|
| `Replace` | FileReplacement proceeds: archive original, rename `.inprogress` -> `-mv.<ext>`, re-probe, update MediaFiles, delete source. On post-rename update failure the rename is rolled back (no orphan, source intact) and `Success=False` is returned with the real error. See `Features/FileReplacement/transcoded-output-placement.feature.md` C13/S4. |
| `BypassReplace` | Same as `Replace` mechanically -- the only difference is the audit reason. The file IS replaced; operator can query why VMAF was skipped. |
| `NoReplace` | Both files left in place. The `.inprogress` output sits next to the source for operator inspection / manual replay. The TranscodeAttempt is final (no requeue). |
| `Requeue` | Staged file deleted. ProblemFiles row created with `ErrorType='VmafBelowMin'` and the VMAF score / min-threshold in the message. Operator action required: choose a profile with a lower CRF or accept the result. **Not auto-creating a new TranscodeQueue row** -- TranscodeQueue has no CRF column, so a new row would re-run at the same CRF and reproduce the low VMAF. Real auto-requeue requires a schema change (a `QualityOverride` column or a stricter sibling profile) -- tracked separately. |
| `Discard` | Staged file deleted. `MediaFiles.LastTranscodeOutcome='NoSavings'` set when reason is NoSavings; queue's no-savings filter prevents re-queueing. |
| `Pending` | No action yet. The TranscodeAttempt's disposition is re-evaluated when the VMAF result lands. The worker's VMAF processing loop calls `DecidePostTranscodeDisposition` again after writing the score. |

**Audit trail (queryable):**

`TranscodeAttempts` gains three columns recording the disposition decision:

| Column | Type | Purpose |
|---|---|---|
| `Disposition` | text | One of the values in the table above. Indexed for operator queries like "what didn't replace and why?". |
| `DispositionReason` | text | The exact enum value from the Reason column. Free-text NOT permitted. |
| `DispositionDecidedAt` | timestamp | When the decision was committed. Distinguishes "decided NoReplace" from "still Pending". |

Operator query for the "why didn't this replace?" question:
```sql
SELECT FilePath, Disposition, DispositionReason, DispositionDecidedAt
FROM TranscodeAttempts
WHERE Success=true AND FileReplaced=false AND Disposition <> 'Pending'
ORDER BY DispositionDecidedAt DESC;
```

**Tables written:** TranscodeAttempts (Disposition, DispositionReason, DispositionDecidedAt), QualityTestQueue (when disposition='Pending' and not yet queued), MediaFiles (LastTranscodeOutcome on Discard/NoSavings), ProblemFiles (when Requeue with adjusted CRF below floor), TemporaryFilePaths (DELETE at the chokepoint for `Discard`/`NoReplace`/`Requeue` -- BUG-0001 criterion 15; `Replace`/`BypassReplace` defer TFP cleanup to FileReplacement's success branch since the canonical paths are still needed).

---

## Stage 7: VMAF -- Quality Test Execution (when Disposition='Pending' on first decision) (`ST8`)

**Trigger:** Stage 6 enqueued a row to `QualityTestingQueue` with `Status='Pending'`. Two consumers can resolve the row:

| Path | Consumer | Condition |
|---|---|---|
| Normal VMAF run | Any worker with `Workers.QualityTestEnabled=true` polls `QualityTestingQueue WHERE Status='Pending' AND ForceDisposition IS NULL` | Capable worker is online and heartbeating |
| Operator override | WebService endpoint `POST /api/QualityTest/Override` sets `ForceDisposition='Replace'` or `'Discard'` on a queue row; WebService acts immediately | Operator decides to short-circuit (no worker available, or known-good encode, or known-bad encode) |

**Normal VMAF path:**
- `WorkerService/Main.py` -> `QualityTestingBusinessService.ProcessQualityTestQueue()`
- For each pending test:
  1. Build FFmpeg VMAF command: compare original vs transcoded using `libvmaf` (input order: `-i transcoded -i original`; see `QualityTesting.feature.md` C11c)
  2. Execute, parse XML output for VMAF score (0-100) + motion-filtered metrics
  3. Insert `QualityTestResults` row with the score; update `TranscodeAttempts.VMAF` + `QualityTestCompleted`
  4. Re-call `DecidePostTranscodeDisposition(TranscodeAttemptId)` -- this time the VMAF score is available, the disposition will be `Replace` / `NoReplace` / `Requeue` per the table
  5. UPDATE QualityTestingQueue SET Status='Completed' for this row

**Operator override path:**
- Operator POSTs `{queueId, forceDisposition: 'Replace'|'Discard', reason: 'optional note'}` to `/api/QualityTest/Override`
- WebService (no worker capability required -- has DB + share access):
  1. UPDATE QualityTestingQueue SET ForceDisposition=$1, OverrideSetAt=NOW(), Status='Cancelled' WHERE Id=$2
  2. Write `TranscodeAttempts.Disposition='BypassReplace'` (for Replace) or `'Discard'` (for Discard); `DispositionReason='OperatorForcedReplace'` or `'OperatorDiscarded'`
  3. If Replace: call `FileReplacementBusinessService.ProcessFileReplacement(attemptId)` synchronously
  4. If Discard: delete the `.inprogress` output and the TFP row
- Worker poll query excludes `ForceDisposition IS NOT NULL` rows so a worker can't race the override.

**Tables written:** QualityTestResults (normal path), QualityTestingQueue (Status flip, ForceDisposition + OverrideSetAt on override), TranscodeAttempts (VMAF score + QualityTestCompleted on normal path; Disposition+Reason on either path).

---

## Stage 8: ACTION -- Execute the Disposition (`ST9`)

**Trigger:** Disposition committed (anything other than `Pending`).

**Replace / BypassReplace path:**
- `Features/FileReplacement/FileReplacementBusinessService.ProcessFileReplacement(TranscodeAttemptId)` orchestrates; dispatches to `TranscodedOutputPlacement.Execute` for the rename + MediaFiles refresh + source delete (extracted 2026-06-02 via `filereplacement-decompose`). No `BypassVMAFCheck` parameter -- the disposition already decided.
  1. Validate TranscodeAttempt exists and FileReplaced=false.
  2. Validate both source and staged files exist; resolve canonical paths to worker-local via `Path.Resolve(Worker)`.
  3. Archive original metadata to MediaFilesArchive.
  4. Compliance gate (`ComplianceGate.Evaluate`): re-runs the cascade compliance predicate against the staged file. On refusal, delete the `.inprogress`, mark the attempt `Disposition='NoReplace'` / `DispositionReason='ComplianceGateFailed'`, source untouched. See `Features/FileReplacement/compliance-gated-rename.feature.md`.
  5. **Rename `.inprogress` -> `<basename>-mv.<ext>`** (`TranscodedOutputPlacement.Execute`). Two paths depending on whether source path equals target path:
     - **Non-SameSlot** (typical): single `os.rename(staged, target)`. Source is untouched at this step; source delete happens at step 8 only after MediaFiles update succeeds.
     - **SameSlot** (source already ends in `-mv.<ext>`, e.g. re-encoded MV output): rename `source -> <source>.replacing.bak`, then `os.rename(staged, target)`. If the second rename fails, restore from `.replacing.bak`. Backup is NOT deleted yet -- it is the rollback target for step 7.
     The `-mv` suffix is the canonical MediaVortex on-disk marker -- structurally distinct from the source filename, defending against same-name collision regressions and giving operators a glance-readable "this was transcoded" signal. See `Features/FileReplacement/transcoded-output-placement.feature.md` C4.
  6. Re-probe new file via FFprobe (worker's local FFprobe path on the worker-resolved path).
  7. Update MediaFiles with new metadata; set ONE of `TranscodedByMediaVortex=True` (Mode='Transcode') or `RemuxedByMediaVortex=True` + `RemuxedByMediaVortexDate=NOW()` (Mode in 'Remux','SubtitleFix','AudioFix','Quick'). `MediaFiles.FilePath` (typed pair) now points at `-mv.<ext>`. **On failure** (unique-key collision on `(StorageRootId, RelativePath)`, re-probe error, or any update error): rollback fires -- non-SameSlot deletes the renamed `-mv.<ext>` orphan; SameSlot renames `target -> staged` then `.replacing.bak -> source` then deletes the staging artifact. Returns `Success=False` with the real update error in `ErrorMessage`; source is bit-identical to its pre-call state. See BUG-0067 + `Features/FileReplacement/transcoded-output-placement.feature.md` C13/S4. SameSlot only: on update SUCCESS, `.replacing.bak` is removed.
  8. **Recompute compliance**: `RecomputeForFiles([MediaFileId])` updates `IsCompliant`, `RecommendedMode`, `PriorityScore`, `AssignedProfile`. Clears `RecommendedMode='Remux'` after a successful remux (container is now MP4, audio is normalized) so the file is not re-queued. If the file still needs work (e.g. remuxed but codec is h264), `RecommendedMode` flips to `'Transcode'`. See `transcode-vs-remux-routing.feature.md` criterion 17. Failure of this recompute does NOT roll back -- the file is on disk correctly and the next scheduled recompute will reconcile.
  9. Delete source file from disk (non-SameSlot only; SameSlot has no separate source to delete). `MarkAudioComplete` runs if the FFmpeg command contained loudnorm.

**Discard path:**
- Delete the `.inprogress` output next to the source
- When reason is `NoSavings`: `MediaFiles.LastTranscodeOutcome='NoSavings'`

**Requeue path:**
- Delete the `.inprogress` output
- `Features/TranscodeJob/Adjustments/AdjustmentRegistry.Get('cq').Calculate(PreviousAttempt, ProfileSettings, GateThreshold)` -> `KnobOverrides(CRF=new_crf)`
- If adjusted CRF >= 15 floor: insert new TranscodeQueue row with the lower CRF
- Else: log to ProblemFiles (file cannot be improved further)

**NoReplace path:**
- No filesystem changes. The `.inprogress` output sits next to the source until an operator clears it manually.

**Tables written:** MediaFiles (new metadata on Replace/BypassReplace), MediaFilesArchive (snapshot before replace), TranscodeAttempts (FileReplaced, FileReplacedDate), TranscodeQueue (new row on Requeue), ProblemFiles (CRF floor breach), QualityTestQueue (cleared on disposition commit).

**Safety guards:**
- Archive-before-delete: original metadata always saved before the rename.
- Rename-then-replace with rollback: original is never destroyed until the new file is verified.
- `FileReplaced` flag prevents duplicate replacements.
- Re-probe after move ensures metadata reflects actual file.
- `TranscodedByMediaVortex=true` prevents infinite re-queue loops.
- **Disposition is final** for non-Pending values. The function is idempotent: calling `DecidePostTranscodeDisposition` again on a row that already has Disposition set returns the existing decision unchanged (no double-replace, no decision drift).

**Operator override:** `POST /api/MediaFiles/<id>/ResetTranscodeOutcome` clears `LastTranscodeOutcome` so a NoSavings file can be retried.

---

## Cross-Stage Data Flow

```
MediaFiles.FilePath          -- created at SCAN, used everywhere
MediaFiles.Resolution        -- set at PROBE, checked at QUEUE
MediaFiles.HasExplicitEnglishAudio -- set at PROBE, checked at QUEUE
MediaFiles.AssignedProfile   -- set at RECOMPUTE (cascade from SeriesProfiles/SystemSettings), read at TRANSCODE
MediaFiles.PriorityScore     -- set at RECOMPUTE, read by non-claim consumers (SmartPopulate helpers, backfill scripts); NOT consulted on the worker claim path (see queue-priority.feature.md)
MediaFiles.IsCompliant       -- set at RECOMPUTE, checked at QUEUE (compliant files blocked)
MediaFiles.RecommendedMode   -- set at RECOMPUTE, read by SmartPopulate to route Transcode vs Remux
MediaFiles.TranscodedByMediaVortex -- set at REPLACE, checked at QUEUE

TranscodeQueue.Status        -- Pending -> Running -> Completed/Failed
TranscodeAttempt.VMAF        -- set at QUALITY, checked at QUEUE (retranscode decision)
TranscodeAttempt.FileReplaced -- set at REPLACE, prevents re-replacement
```

## Two Microservices

| Service | Process | Port | Role |
|---------|---------|------|------|
| WebService | `WebService/Main.py` | 5000 | Flask API + UI. Handles stages 1-4 and 7 |
| WorkerService | `WorkerService/Main.py` | -- | Stages 5-6. Transcode, VMAF, and scanning based on per-worker capability flags |

Coordinated via `ServiceLifecycleManager` in `StartMediaVortex.py`.

## SystemSettings Infrastructure

Runtime-configurable key-value store in PostgreSQL. Used for transcode file mode, FFmpeg paths, scan directories, excluded directories, and other settings.

**Table:** `SystemSettings` -- columns: `Id`, `SettingKey` (text), `SettingValue` (text), `Description`, `DataType` (default 'string'), `LastModified`

**Key files:**
- `Features/SystemSettings/SystemSettingsRepository.py` -- `GetSystemSetting(Key)`, `AddOrUpdateSystemSetting(Key, Value, Description)`, `RunMigrations()`
- `Features/SystemSettings/SystemSettingsController.py` -- REST API under `/api/SystemSettings/`

**API:**
- `GET /api/SystemSettings/<Key>` -- get a setting value
- `POST /api/SystemSettings/<Key>` -- set/update (body: `{"Value": "...", "Description": "..."}`)
- `DELETE /api/SystemSettings/<Key>` -- remove a setting

**Transcode-relevant settings:**
- `FFmpegPath`, `FFprobePath` -- tool locations
- `ExcludedDirectories` -- comma-separated list of directories to skip during scanning

---

## Service Architecture

### WorkerService Startup Sequence

```
WorkerService/Main.py
  -> Main()
    -> WorkerServiceApp.__init__()
      -> DatabaseManager created
      -> Worker identity (hostname, platform)
      -> RegisterWorker() -- UPSERT into Workers table
      -> WorkerContext.Initialize() -- singleton with FFmpeg/FFprobe paths, share mappings
      -> ProcessTranscodeQueueService created
    -> app.Run()
      -> RecoverFromCrash()                -- CrashRecoveryService resets orphaned jobs
      -> DetectAndCleanStuckJobs()         -- StuckJobDetectionService cleans frozen jobs
      -> _StartHealthMonitoring()          -- 30-second heartbeat thread
      -> _StartStatusPolling()             -- 5-second status polling (Workers.Status)
      -> _StartCapabilityPolling()         -- 60-second capability polling
      -> _LoadCapabilitiesFromDB()         -- reads TranscodeEnabled, QualityTestEnabled, ScanEnabled
      -> _ApplyCapabilities()              -- starts/stops capability loops
      -> MainLoop()                        -- blocks on ShutdownEvent
```

### Job Claiming Mechanism

Distributed claim flow (current):
1. `ProcessQueueLoop()` calls `GetNextJob()` every ~2 seconds when a slot is available
2. `GetNextJob()` delegates to `Features/TranscodeQueue/TranscodeQueueRepository.ClaimNextPendingTranscodeJob(WorkerName, AcceptsInterlaced)`
3. Repository executes a single atomic `UPDATE ... WHERE Id = (SELECT ... FOR UPDATE OF tq SKIP LOCKED) RETURNING ...` that:
   - Filters `tq.Status = 'Pending'` and `tq.ProcessingMode` matches Transcode
   - Joins MediaFiles (`mf`) + Profiles (`p`) for routing context
   - Applies `BuildClaimPredicate(WorkerName, 'TranscodeEnabled')` -- worker is Online and TranscodeEnabled
   - Applies the NVENC EXISTS gate -- `p.usenvidiahardware=0` OR worker has `nvenccapable=TRUE`
   - Applies `BuildAllowedProfilesPredicate(WorkerName)` -- `w.AllowedProfiles IS NULL` (accept all) OR `mf.AssignedProfile = ANY(string_to_array(w.AllowedProfiles, ','))` (explicit allowlist match). Operator sets per-worker via `POST /api/TeamStatus/Workers/<name>/AllowedProfiles`; takes effect on the next claim tick (db-is-authority single-emitter pattern)
   - Orders per the claim contract in `queue-priority.feature.md`: `(CASE WHEN tq.Priority >= 195 THEN tq.Priority ELSE 0 END) DESC, tq.SizeMB DESC NULLS LAST, tq.DateAdded ASC`
   - Locks via `FOR UPDATE OF tq SKIP LOCKED` -- two workers racing the same row is impossible
4. On successful claim, logs `WorkerName`, `JobId`, `ProfileName`, `WorkerAllowedProfiles` (`<all>` / `<none>` / CSV) for routing observability

Legacy (single-worker, non-atomic) flow `GetNextPendingTranscodeJob` is retained for the local dev path but is not used by distributed workers.

### ActiveJobs Tracking

Table: `ActiveJobs`
- Created per job via `DatabaseManager.CreateActiveJob(ServiceName, JobType, QueueId, ProcessId, ThreadId, WorkerName)`
- Columns: Id, ServiceName, JobType, QueueId, ProcessId, ThreadId, WorkerName, Status, CreatedAt, UpdatedAt
- ProcessId stores `os.getpid()` (Python worker PID, NOT FFmpeg PID)
- WorkerName identifies which worker owns the job -- all queries/cleanup are scoped by this
- Used by StuckJobDetectionService to correlate running jobs with worker heartbeats

### Stuck Job Detection

Three-tier detection (all scoped by WorkerName):
1. **Worker heartbeat** (Tier 1): `_IsWorkerOffline(WorkerName)` -- if LastHeartbeat > 5 min stale, worker is offline and all its jobs are stuck. Works across machines.
2. **Progress stagnation** (Tier 2): `_IsJobFrozen()` checks `TranscodeProgress.LastFrameAdvance` -- if no frame advance for 15 minutes, job is frozen. Works across machines.
3. **Local PID check** (Tier 3): `IsProcessAlive(ProcessId)` -- only runs for local jobs (WorkerName == hostname). Checks if the Python worker process is still alive. PID reuse is guarded by Tier 1 (heartbeat staleness).

Cleanup: resets TranscodeQueue to Pending (clears ClaimedBy/ClaimedAt), marks TranscodeAttempt as failed, deletes TranscodeProgress, updates ActiveJobs to Failed.

### Crash Recovery

`CrashRecoveryService.RecoverServiceJobs("TranscodeService")` runs at startup, scoped to this worker:
- Finds ActiveJobs for this service AND this worker (WorkerName filter)
- Verifies if their processes are still running locally
- Resets orphaned jobs (dead process) back to Pending, clears ClaimedBy
- Never touches other workers' jobs

### MaxConcurrentJobs

- Default: 1 (hardcoded in `PrivateHandleStatusChange` call to `Run(MaxConcurrentJobs=1)`)
- Validated range: 1-5 (in `ProcessTranscodeQueueService.Run()`)
- Controls thread pool: `ProcessQueueLoop` only starts new job threads when `len(self.ActiveJobs) < self.MaxConcurrentJobs`

### ServiceLifecycleManager

`StartMediaVortex.py` uses `ServiceLifecycleManager` to start both services:
- WebService (Flask, port 5000) -- in-process
- WorkerService -- separate process via subprocess

Each service registers in `ServiceStatus` table with ProcessId, enabling cross-service health monitoring.

### Worker Registration (Distributed)

In distributed mode, each WorkerService instance:
1. Calls `RegisterWorker(WorkerName)` on startup (UPSERT into Workers table)
2. Updates `Workers.LastHeartbeat` every 30 seconds via HealthCheckLoop
3. Loads its config (FFmpegPath, ShareMountPrefix, MaxConcurrentJobs) from Workers row
4. Uses `ClaimNextPendingTranscodeJob(WorkerName)` for atomic job claiming with `SKIP LOCKED`

---

## Distributed Transcode: Complete Lifecycle Reference

End-to-end trace from worker installation through finished product. Every function, DB call, and status transition.

### Phase 0: Worker Installation

| Step | Action | Function/Command | DB Call | Status Change |
|------|--------|-----------------|---------|---------------|
| 0.1 | Clone repo | `git clone` | -- | -- |
| 0.2 | Create venv + install deps | `pip install -r requirements.txt` | -- | -- |
| 0.3 | Mount network share | `net use T:` / `mount -t cifs` | -- | -- |
| 0.4 | Set env vars | `MEDIAVORTEX_DB_HOST`, `_PORT`, `_NAME`, `_USER`, `_PASSWORD` | -- | -- |
| 0.5 | Run migration | `python Scripts/SQLScripts/AddDistributedColumns.py` | `CREATE TABLE Workers (...)`, `ALTER TABLE TranscodeQueue ADD COLUMN ClaimedBy`, `ALTER TABLE TranscodeQueue ADD COLUMN ClaimedAt`, `ALTER TABLE ActiveJobs ADD COLUMN WorkerName` | -- |
| 0.6 | Register worker in DB | Manual INSERT via `QueryDatabase.py` | `INSERT INTO Workers (...) ON CONFLICT (WorkerName) DO UPDATE ...` | Workers row created |
| 0.7 | Create staging directory | `mkdir T:\MediaVortex\Staging` or `/mnt/media/MediaVortex/Staging` | -- | -- |

### Phase 1: Service Startup

| Step | Action | Function | DB Call | Status Change |
|------|--------|----------|---------|---------------|
| 1.1 | Identify self | `WorkerServiceApp.__init__()` | -- | `WorkerName = socket.gethostname()` |
| 1.2 | Register + load config | `_RegisterAndLoadWorkerConfig()` | `INSERT INTO Workers ... ON CONFLICT DO UPDATE SET Status='Online', LastHeartbeat=NOW()` then `SELECT * FROM Workers WHERE WorkerName = %s` | Workers.Status = `Online` |
| 1.3 | Initialize WorkerContext | `WorkerContext.Initialize()` | -- | Singleton stores FFmpeg/FFprobe paths, share mappings for all services in the process |
| 1.4 | Create ProcessTranscodeQueueService | `ProcessTranscodeQueueService.__init__()` | -- | PathTranslationService initialized from WorkerContext |
| 1.5 | Crash recovery | `RecoverFromCrash()` -> `CrashRecoveryService.RecoverServiceJobs()` | `UPDATE TranscodeQueue SET Status='Pending' WHERE Status='Running'` (for orphaned jobs) | Orphaned jobs -> `Pending` |
| 1.6 | Stuck job detection | `DetectAndCleanStuckJobs()` -> `StuckJobDetectionService.DetectAndCleanStuckTranscodeJobs()` | Checks `ActiveJobs`, `Workers.LastHeartbeat`, `TranscodeProgress` | Stuck jobs -> `Failed` |
| 1.7 | Start health monitor | `_StartHealthMonitoring()` -> `_HealthCheckLoop()` (30s interval) | `UPDATE Workers SET LastHeartbeat = NOW()` | Heartbeat ticking |
| 1.8 | Start status polling | `_StartStatusPolling()` -> `_StatusPollingLoop()` (5s interval) | `SELECT Status FROM Workers WHERE WorkerName = %s` | Watching for Online/Draining/Offline |
| 1.8b | Start capability polling | `_StartCapabilityPolling()` -> `_CapabilityPollingLoop()` (60s interval) | `SELECT TranscodeEnabled, QualityTestEnabled, ScanEnabled FROM Workers WHERE WorkerName = %s` | Watching for capability changes |
| 1.9 | Load + apply capabilities | `_LoadCapabilitiesFromDB()` + `_ApplyCapabilities()` | reads Workers row | Starts/stops transcode, VMAF, scan loops based on flags |

### Phase 2: Job Claiming (Atomic)

| Step | Action | Function | DB Call | Status Change |
|------|--------|----------|---------|---------------|
| 2.1 | Check for work | `ProcessQueueLoop()` polls every 2s | -- | -- |
| 2.2 | Claim job atomically | `GetNextJob()` -> `DatabaseManager.ClaimNextPendingTranscodeJob(WorkerName)` | `UPDATE TranscodeQueue SET Status='Running', ClaimedBy=%s, ClaimedAt=NOW(), DateStarted=NOW() WHERE Id = (SELECT Id FROM TranscodeQueue WHERE Status='Pending' ORDER BY (CASE WHEN Priority >= 195 THEN Priority ELSE 0 END) DESC, SizeMB DESC NULLS LAST, DateAdded ASC LIMIT 1 FOR UPDATE SKIP LOCKED) RETURNING *` -- see `queue-priority.feature.md` | TranscodeQueue.Status = `Running`, ClaimedBy = hostname |
| 2.3 | Create ActiveJob | `DatabaseManager.CreateActiveJob(ServiceName, JobType, QueueId, ProcessId, ThreadId, WorkerName)` | `INSERT INTO ActiveJobs (ServiceName, JobType, QueueId, ProcessId, ThreadId, WorkerName, Status, StartedAt) VALUES (...)` | ActiveJobs row created, Status = `Running` |

### Phase 3: Job Processing

| Step | Action | Function | DB Call | Status Change |
|------|--------|----------|---------|---------------|
| 3.1 | Create attempt record | `CreateTranscodeAttempt(Job)` | `INSERT INTO TranscodeAttempts (FilePath, AttemptDate, Quality, OldSizeBytes, Success=NULL, ...)` | TranscodeAttempts row created |
| 3.2 | Load media metadata | `GetMediaFileData(Job)` -> `DatabaseManager.GetMediaFileByPath()` | `SELECT * FROM MediaFiles WHERE LOWER(FilePath) = LOWER(%s)` | -- |
| 3.3 | Archive original | `ArchiveOriginalFileDetails(MediaFile, AttemptId)` | `INSERT INTO MediaFilesArchive (...)` | Archive row created |
| 3.4 | Load profile + settings | `GetTranscodingSettings(Job, MediaFile)` | `SELECT FROM ProfileThresholds`, `SELECT FROM CodecFlags`, `SELECT FROM CodecParameters`, check CRF overrides in SystemSettings | FFmpegPath + OutputDirectory included in return |
| 3.5 | Translate input path | `SetupFilePreparation(Job, MediaFile, AttemptId)` | -- | `PathTranslation.ToLocalPath(Job.FilePath)` converts `T:\...` to `/mnt/media/...` on Linux |
| 3.6 | Setup staging dir | `TranscodingFileManagerService.SetupTranscodingDirectories(OutputDirectory)` | -- | Creates staging dir if needed |
| 3.7 | Build FFmpeg command | `BuildTranscodeCommand()` -> `CommandBuilderService.BuildCommand()` -> `CommandBuilder.BuildCommand()` | -- | Reads `FFmpegPath` and `OutputDirectory` from CommandData (with `or` fallback to defaults) |
| 3.8 | Store typed-pair paths | `PrivateCreateTemporaryFilePathRecord(AttemptId, SourcePath, OutputPath)` | `INSERT INTO TemporaryFilePaths (TranscodeAttemptId, SourceStorageRootId, SourceRelativePath, OutputStorageRootId, OutputRelativePath)` | Paths stored as typed pair `(StorageRootId, RelativePath)`. Worker resolves to local via `Path.Resolve(Worker)`; UI/logs use `Path.CanonicalDisplay(GetPrefixMap())`. |
| 3.9 | Update attempt with command | `DatabaseManager.UpdateTranscodeAttempt()` | `UPDATE TranscodeAttempts SET FfpmpegCommand=%s, ...` | -- |

### Phase 4: FFmpeg Execution

| Step | Action | Function | DB Call | Status Change |
|------|--------|----------|---------|---------------|
| 4.1 | Launch FFmpeg | `ExecuteTranscoding()` -> `VideoTranscodingService.StartTranscoding()` | -- | FFmpeg subprocess spawned |
| 4.2 | Track progress | `VideoTranscodingService` parses stderr | `INSERT/UPDATE TranscodeProgress (TranscodeAttemptId, CurrentFrame, TotalFrames, Percent, Speed, FPS, ...)` | Progress updated in real-time |
| 4.3 | Heartbeat continues | `HealthCheckLoop()` (background thread) | `UPDATE Workers SET LastHeartbeat = NOW()` | Proves worker is alive to other workers |
| 4.4 | FFmpeg completes | `VideoTranscodingService` returns result | -- | `.inprogress` output file exists next to source |

### Phase 5: Post-Transcode Handling

| Step | Action | Function | DB Call | Status Change |
|------|--------|----------|---------|---------------|
| 5.1 | Calculate size reduction | `HandleTranscodingResult()` | -- | -- |
| 5.2 | Mark attempt successful | `DatabaseManager.UpdateTranscodeAttempt()` | `UPDATE TranscodeAttempts SET Success=True, CompletedDate=NOW(), NewSizeBytes=%s, SizeReductionBytes=%s, SizeReductionPercent=%s, QualityTestRequired=True` | Attempt marked successful |
| 5.3 | Update TranscodeFiles | `UpdateTranscodeFileRecord()` | `INSERT/UPDATE TranscodeFiles (FilePath, SuccessfulAttemptId, ...)` | File-level status updated |
| 5.4 | Bridge: decide disposition | `Features/QualityTesting/Disposition/PostTranscodeDispositionDecider.Decide(AttemptId)` -- single decision function, no per-caller branching. Reads `TranscodeAttempts` row + `PostTranscodeGateConfig` + (when present) the VMAF score; returns one of `Replace` / `BypassReplace` / `Pending` / `Requeue` / `Discard` / `NoReplace` with a reason. `DispositionDispatcher.Dispatch` then routes to the matching action. | Writes `TranscodeAttempts.Disposition` + `DispositionReason`. If `Pending`: `INSERT INTO QualityTestingQueue (TranscodeAttemptId, Status='Pending')`. If `Replace`/`BypassReplace`: synchronous call into `FileReplacementBusinessService.ProcessFileReplacement(AttemptId)` -- which dispatches into `TranscodedOutputPlacement.Execute`. | `TranscodeAttempts.Disposition` populated; `QualityTestingQueue` row created only when `Pending`. |
| 5.5 | Delete from TranscodeQueue | `DatabaseManager.DeleteTranscodeQueueItem(Job.Id)` | `DELETE FROM TranscodeQueue WHERE Id = %s` | Job removed from queue |
| 5.6 | Clean progress | `DatabaseManager.DeleteTranscodeProgress(AttemptId)` | `DELETE FROM TranscodeProgress WHERE TranscodeAttemptId = %s` | -- |
| 5.7 | Complete ActiveJob | `DatabaseManager.CompleteActiveJob(ActiveJobId, Success=True)` | `UPDATE ActiveJobs SET Status='Completed', CompletedAt=NOW()` | ActiveJobs.Status = `Completed` |

### Phase 6: Quality Testing (WorkerService with QualityTestEnabled=TRUE)

| Step | Action | Function | DB Call | Status Change |
|------|--------|----------|---------|---------------|
| 6.1 | Claim quality job | WorkerService quality test loop polls | `SELECT FROM QualityTestQueue WHERE Status='Pending'` | QualityTestQueue.Status = `Running` |
| 6.2 | Read paths from DB | Reads TemporaryFilePaths | `SELECT SourceStorageRootId, SourceRelativePath, OutputStorageRootId, OutputRelativePath FROM TemporaryFilePaths WHERE TranscodeAttemptId = %s` | Paths stored as typed pair `(StorageRootId, RelativePath)`. Worker resolves to local via `Path.Resolve(Worker)`; UI/logs use `Path.CanonicalDisplay(GetPrefixMap())`. |
| 6.3 | Run VMAF | FFmpeg VMAF comparison (original vs transcoded) | -- | Both files read from network share via canonical paths |
| 6.4 | Store VMAF score | `UpdateTranscodeAttempt()` | `UPDATE TranscodeAttempts SET VMAF = %s, QualityTestCompleted = True` | VMAF score recorded |
| 6.5 | Decide: pass/fail | VMAF >= 80 = pass | -- | -- |

### Phase 7: File Replacement (if VMAF passes, or directly after transcode when QualityTestRequired=False)

Per-step detail of Stage 8 ACTION above (Replace / BypassReplace path). Step IDs match the Stage 8 numbering; the table adds the function + DB-call granularity.

| Step | Action | Function | DB Call | Status Change |
|------|--------|----------|---------|---------------|
| 7.1 | Orchestrate | `FileReplacementBusinessService.ProcessFileReplacement(TranscodeAttemptId)` | `SELECT * FROM TranscodeAttempts WHERE Id = %s AND FileReplaced=FALSE` | Caller resolves source + staged paths via TemporaryFilePaths typed pair `(StorageRootId, RelativePath)`. |
| 7.2 | Archive | `_ArchiveOriginalFileDetails()` | `INSERT INTO MediaFilesArchive (...)` | Snapshot before destructive ops. |
| 7.3 | Compliance gate | `ComplianceGate.Evaluate(stagedPath, sourceMediaFileId, ffmpegCommand)` | (synthesizes candidate row, calls `QueueManagementBusinessService._EvaluateCompliance`) | On refusal: delete `.inprogress`, record `Disposition='NoReplace'` / `DispositionReason='ComplianceGateFailed'`, return early. Source untouched. |
| 7.4 | Rename `.inprogress` -> `-mv.<ext>` | `TranscodedOutputPlacement.Execute` | -- | Non-SameSlot: `os.rename(staged, target)`. SameSlot: `os.rename(source, source + '.replacing.bak')` then `os.rename(staged, target)` with restore-from-`.replacing.bak` if inner rename fails. |
| 7.5 | Verify target | `LocalGetSize(target)` | -- | Logs WARN if zero bytes. |
| 7.6 | Re-probe + update MediaFiles | `_UpdateMediaFilesAfterReplacement(Mode=...)` -- FFprobe the new file, write all metadata columns. Sets ONE flag: `TranscodedByMediaVortex=True` (Mode='Transcode') or `RemuxedByMediaVortex=True` + `RemuxedByMediaVortexDate=NOW()` (Mode in 'Remux','SubtitleFix','AudioFix','Quick'). Mode comes from `TranscodeAttempts.ProfileName`. See `Features/FileReplacement/remuxed-flag.feature.md`. | `UPDATE MediaFiles SET StorageRootId=..., RelativePath=..., FileName=..., Resolution=..., Codec=..., SizeMB=..., <one of Transcoded/RemuxedByMediaVortex>=TRUE, LastScannedDate=NOW(), NeedsReprobe=FALSE WHERE Id = %s` | MediaFiles reflects the new file with the right flag for the mode. **On failure**: rollback fires (BUG-0067 -- non-SameSlot deletes the renamed `-mv.<ext>` orphan; SameSlot renames target back to staged, then `.replacing.bak` back to source, then deletes staging artifact). Returns `Success=False` with the real error in `ErrorMessage`. See `Features/FileReplacement/transcoded-output-placement.feature.md` C13/S4. |
| 7.7 | Remove SameSlot backup | (only when SameSlot AND step 7.6 succeeded) | -- | `os.remove(source + '.replacing.bak')`. Deferred from step 7.4 so rollback in 7.6 has a valid backup. |
| 7.8 | Recompute compliance | `QueueManagementBusinessService().RecomputeForFiles([MediaFileId])` | `UPDATE MediaFiles SET IsCompliant=..., RecommendedMode=..., PriorityScore=..., AssignedProfile=... WHERE Id = %s` | Clears `RecommendedMode='Remux'` after successful remux, flips to `'Transcode'` if more work needed. Failure here does NOT roll back -- file is on disk correctly. |
| 7.9 | Delete source (non-SameSlot only) | `os.remove(LocalOriginalPath)` | -- | SameSlot: no separate source to delete (source path equals target path). |
| 7.10 | Mark attempt replaced | | `UPDATE TranscodeAttempts SET FileReplaced=TRUE, FileReplacedDate=NOW() WHERE Id = %s` | -- |
| 7.11 | Cleanup TFP + notify Jellyfin | `PostTranscodeDispositionService.CleanupTemporaryFilePaths(TranscodeAttemptId)` (BUG-0010 chokepoint), `Services/JellyfinNotifyService.NotifyJellyfin([{Path, UpdateType='Modified'}])` | `DELETE FROM TemporaryFilePaths WHERE TranscodeAttemptId = %s` | TFP cleared at the disposition chokepoint (one DELETE point, not per-feature). Jellyfin notify posts to `/Library/Media/Updated`; failure is non-fatal (WARNING + continue). Unconditional -- if FileReplacement moved the file, the notify fires. See `jellyfin-push-notify.feature.md`. |

### Phase 8: Shutdown (scoped to this worker only)

| Step | Action | Function | DB Call | Status Change |
|------|--------|----------|---------|---------------|
| 8.1 | SIGINT/SIGTERM received | `_SignalHandler()` or `Shutdown()` | -- | -- |
| 8.2 | Kill local FFmpeg processes | `proc.kill()` for active jobs | -- | Only kills local processes |
| 8.3 | Reset this worker's jobs | | `UPDATE TranscodeQueue SET Status='Pending', ClaimedBy=NULL, ClaimedAt=NULL WHERE Status IN ('Running', 'Processing') AND ClaimedBy = %s` | This worker's jobs back to Pending |
| 8.4 | Clear this worker's active jobs | | `DELETE FROM ActiveJobs WHERE ServiceName='TranscodeService' AND WorkerName = %s` | -- |
| 8.5 | Mark worker offline | `DatabaseManager.UpdateWorkerStatus(WorkerName, "Offline")` | `UPDATE Workers SET Status='Offline' WHERE WorkerName = %s` | Workers.Status = `Offline` |
| 8.6 | Update ServiceStatus | | `UPDATE ServiceStatus SET Status='Stopped', ProcessId=0, IsProcessing=False` | ServiceStatus.Status = `Stopped` |

### Path Translation Reference

| Context | Path Format | Example |
|---------|-------------|---------|
| Database (typed pair) | `(StorageRootId BIGINT, RelativePath TEXT)`; forward slashes, no leading slash, no drive letter | `(1, "Shows/Show Name/S01E01.mkv")` |
| Display (UI / logs) | `Path.CanonicalDisplay(GetPrefixMap())` -- Windows-shaped regardless of worker OS | `T:\Shows\Show Name\S01E01.mkv` |
| Linux worker local | `Path.Resolve(Worker)` joins worker prefix + RelativePath, forward slashes | `/mnt/media/Shows/Show Name/S01E01.mkv` |
| Windows worker local | `Path.Resolve(Worker)` joins worker prefix + RelativePath, backslashes | `T:\Shows\Show Name\S01E01.mkv` |
| TemporaryFilePaths (DB) | Always typed pair `(StorageRootId, RelativePath)`. Display via `Path.CanonicalDisplay`. Worker-local via `Path.Resolve(Worker)`. | `(1, "MediaVortex/Staging/S01E01.mkv")` |
| FFmpeg command (local) | Worker's native format, output of `Path.Resolve(Worker)` -- no separator rewriting downstream | `/mnt/media/MediaVortex/Staging/S01E01.mkv` |

Resolution happens at one point: `Path.Resolve(Worker)` joins the worker-local prefix from `StorageRootResolutions.AbsolutePath` with `RelativePath` using the worker-platform separator. Writers store `(StorageRootId, RelativePath)`; readers resolve via `Path.Resolve(Worker)` for I/O and `Path.CanonicalDisplay(GetPrefixMap())` for display.

This ensures any machine (VMAF on primary, FileReplacement on primary) can always find both files via canonical paths on the shared network drive.
