# Transcode Flow

Entry point: `StartMediaVortex.py` (all services) or individual service scripts.

## Stage Overview

```
SCAN -> PROBE -> ASSIGN -> PRIORITY -> QUEUE -> TRANSCODE -> QUALITY -> REPLACE
 (1)     (2)      (3)       (3.5)      (4)       (5)          (6)       (7)
```

Stages 1-4 require user action. Stages 5-7 are automatic once WorkerService is running:
- QUEUE -> TRANSCODE: automatic (service polls for Pending items)
- TRANSCODE -> QUALITY or REPLACE: ShouldQualityTestService.ProcessTranscodedFile is the bridge. It checks QualityTestRequired on the TranscodeAttempt: when False, skips directly to FileReplacement; when True, queues a quality test. If quality testing is paused, it also skips directly to replacement.
- QUALITY -> REPLACE: automatic if VMAF is within threshold range (default 80-100)

**Service dependency model:** Both services communicate exclusively via PostgreSQL. No HTTP calls between them. Each polls the database for its own work. FileReplacement is a library (not a service) that runs in whatever process calls it -- WorkerService when QualityTest=OFF, WorkerService's quality test loop when QualityTest=ON, WebService for manual replacement.

---

## Stage 1: SCAN -- File Discovery

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

---

## Stage 2: PROBE -- FFprobe Metadata Extraction

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

---

## Stage 3: ASSIGN -- Profile Assignment

**Trigger:** User assigns profiles in UI

**Code paths (three ways):**
1. Per-folder bulk: `POST /api/Profiles/AssignProfileToRootFolder` -> updates `MediaFiles.AssignedProfile` for all files in folder
2. Per-title via Media page: ShowSettings target resolution dropdown -> `POST /api/ShowSettings/Save`
3. At queue time: QueueByFolder and AddSuggestionsToQueue both accept ProfileId and assign it to files before queuing

**Tables written:** MediaFiles.AssignedProfile (stores profile name string, not ID), ShowSettings (target resolution per folder)

**Note:** AssignedProfile is a string field storing ProfileName, not a foreign key. Profile lookup happens at transcode time.

---

## Stage 3.5: RECOMPUTE -- Priority, Compliance, and Routing Materialization

**What it computes:** A single function (`RecomputeForFiles`) updates four cached columns on `MediaFiles` in one pass per row:

| Column | Values | Purpose |
|--------|--------|---------|
| `AssignedProfile` | profile name string or NULL | Resolved via cascade: ShowSettings per-show override -> SystemSettings.DefaultProfileName |
| `PriorityScore` | integer 1-194 | Impact-based score (bytes-saved estimate). Workers claim highest first. |
| `IsCompliant` | true / false / NULL | Whether the file already meets all codec/container/audio requirements. NULL = undecidable (no profile, no English audio, not probed). |
| `RecommendedMode` | 'Transcode' / 'Remux' / NULL | Which pipeline should handle this file. NULL = already compliant. |

**RecommendedMode decision** (from `_EvaluateCompliance`, see `transcode-vs-remux-routing.feature.md` criterion 11):

1. Hard blocks (return NULL/NULL): no English audio, no effective profile, no resolution category, no profile thresholds.
2. `Transcode` -- video codec not in `CodecCompatibility.VideoCodec` acceptable set, OR resolution downscale needed, OR estimated savings >= `QueueAdmissionConfig.MinTranscodeSavingsMB`.
3. `Remux` -- container not in acceptable set (e.g. matroska), OR audio codec not acceptable for MP4, OR audio not yet normalized.
4. Compliant (true, NULL) -- passes all checks.

The cascade is ordered: Transcode wins over Remux (if a file needs both a codec change and a container change, Transcode handles it since re-encoding produces an MP4 output anyway).

**Trigger:** Four event sources keep these columns current:

1. **Probe completion** -- `MediaProbeBusinessService._ExecuteProbe` calls `RecomputeForFiles([MediaFileId])` after writing probe metadata. Since probe runs automatically at the end of every scan (Stage 2), this is the initial population path for newly discovered files.
2. **File replacement completion** -- `FileReplacementBusinessService._ProcessCompleteFileReplacement` calls `RecomputeForFiles([MediaFileId])` after updating the MediaFiles row with new metadata. This is what clears `RecommendedMode` after a successful remux or transcode.
3. **AssignedProfile change** -- profile assignment endpoints invoke `ComputePriorityScoresForFiles` (alias for `RecomputeForFiles`) for affected MediaFileIds.
4. **Admin recompute** -- `POST /api/PriorityMaterialization/Recompute` (explicit operator action, optional `ProfileName` / `Drive` / `ShowFolder` filters).

**Code path:**
- `Features/TranscodeQueue/QueueManagementBusinessService.py`:
  - `RecomputeForFiles(MediaFileIds)` -- loads all caches once (profiles, thresholds, show overrides, audio normalization set, codec compatibility sets, queue admission config), then evaluates each row. Single bulk UPDATE writes all four columns.
  - `ComputePriorityScoresForFiles(MediaFileIds)` -- backwards-compat alias, calls `RecomputeForFiles`.
- `Features/PriorityMaterialization/PriorityMaterializationController.py` -- admin endpoint.

**Tables read:** MediaFiles, Profiles, ProfileThresholds, ShowSettings, SystemSettings, CodecCompatibility, QueueAdmissionConfig, AudioNormalizationLog.

**Tables written:** MediaFiles (AssignedProfile, PriorityScore, IsCompliant, RecommendedMode).

**Failure semantics:**
- The recompute hook never blocks the triggering operation. If recompute fails (DB error, missing inputs), the trigger (probe / replace / assign) still returns Success=True.
- A failed recompute leaves prior values untouched -- never silently zeroed or nulled.
- Per-row failures in the bulk loop are logged and skipped; remaining rows still update.
- A `LogWarning` row is emitted naming the MediaFileId and reason whenever the fallback path runs (NULL AssignedProfile, no ProfileThresholds row). Per the loud-failure rule, silent fallbacks are forbidden.

**Output:** Every MediaFiles row carries up-to-date routing fields. Consumers:
- `SmartPopulateQueue(Mode='Remux')` reads `RecommendedMode` to show remux candidates.
- `SmartPopulateQueue(Mode='Transcode')` reads `RecommendedMode` to show transcode candidates.
- Activity page compliance widget reads `IsCompliant` for library-wide stats.
- No consumer recomputes -- all read the materialized columns.

See `Features/TranscodeQueue/priority-materialization.feature.md` and `Features/TranscodeQueue/transcode-vs-remux-routing.feature.md` for criteria.

---

## Stage 4: QUEUE -- TranscodeQueue Population

**Trigger:** Multiple paths to queue files:

| Path | Endpoint | Safety guards applied |
|------|----------|----------------------|
| Full populate | `POST /api/TranscodeQueue/PopulateQueue` | All guards (audio, resolution, VMAF, CRF floor) |
| Media page: queue by folder | `POST /api/ShowSettings/QueueByFolder` | Audio language, probed (Resolution NOT NULL), dedup, already-transcoded |
| Media page: batch (SmartPopulate) | `POST /api/ShowSettings/AddToQueue` | Dedup only (user explicitly chose files) |
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
- `Features/ShowSettings/ShowSettingsController.py` -> `QueueByFolder()`
- SQL query filters: not transcoded, not in queue, `HasExplicitEnglishAudio IS NULL OR true`, SizeMB > 0
- Passes to `AddSuggestionsToQueue()` which assigns profile and consults the marginal-savings gate before inserting queue rows.

**Tables written:** TranscodeQueue (new items), ProblemFiles (if CRF adjustment fails)

**Safety guards summary:**
- **Audio language** (CRITICAL): files with `HasExplicitEnglishAudio = false` blocked at all queue paths
- **VMAF quality gate**: files with VMAF >= 80 not re-transcoded
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

**Priority calculation (impact-based, range 1-194):**

Every queue insertion runs `QueueManagementBusinessService.CalculatePriority(MediaFile, ProfileSettings)` which returns an integer between 1 and 194. Workers claim with `ORDER BY Priority DESC, DateAdded ASC`, so higher priority is more urgent.

Score is the bytes-saved estimate, computed deterministically from the configured profile target:

1. `target_size_mb = ((profile.VideoBitrateKbps + profile.AudioBitrateKbps) * MediaFile.DurationMinutes * 60) / (8 * 1024)`
2. `estimated_savings_mb = max(0, MediaFile.SizeMB - target_size_mb)`
3. `score = log10(estimated_savings_mb + 1)` -- log dampens outliers so a single 30 GB rip doesn't swamp the queue
4. `priority = clamp(1 + (score / 5.0) * 193, 1, 194)`

The 6-slot window 195-200 is reserved for manual user overrides (the `POST /api/TranscodeQueue/PrioritizeJob` endpoint). Auto-assignment never produces a value in that range, so a manually-set 200 always beats any auto-prioritized item.

When `MediaFile.DurationMinutes` or `MediaFile.AssignedProfile` is NULL, or when no `ProfileThresholds` row exists for the resolution category, the function falls back to `estimated_savings_mb = SizeMB * 0.5` and emits a `LogWarning` naming the MediaFileId and the missing input. Silent fallbacks are forbidden per the Phase 2a loud-failure rule.

Rationale: ordering by raw size (the legacy behavior) put already-efficient AV1 files at the top of the queue and ignored compression headroom. Reading the actual configured profile target (rather than guessing via a codec multiplier) means already-efficient sources correctly land at savings = 0 -> priority 1, and a profile change automatically reflects in the next CalculatePriority call. See `Features/TranscodeQueue/queue-priority.feature.md` for the full criteria.

---

## Stage 5: TRANSCODE -- FFmpeg Job Execution

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
  8. Build FFmpeg command (libsvtav1, preset, CRF, film grain, bitrates)
  9. Execute FFmpeg via `VideoTranscodingService.TranscodeVideo()`
  10. Monitor progress (frames / total_frames), update TranscodeProgress
  11. On completion: record TranscodeAttempt with size reduction, duration, command

**File staging (controlled by `TranscodeFileMode` SystemSetting):**
- **InPlace** (default): FFmpeg reads directly from the network path. On the primary machine this is the raw DB path (e.g. `T:\ShowName\file.mkv`). On remote workers, `PathTranslationService.ToLocalPath()` converts to the local mount (e.g. `/mnt/media/ShowName/file.mkv`).
- **CopyLocal**: copies source to `C:\MediaVortex\Source\{FileName}` before transcoding (legacy behavior). Useful if network is unreliable or for local-only files.
- **LocalStaging**: copies source from NFS to the worker's local disk (`/staging/{WorkerName}/`), FFmpeg reads and writes entirely on local storage, then copies the output back to NFS `StagingDirectory` and deletes local files. Eliminates NFS I/O bottleneck for CPU-bound transcodes. Crash recovery skips the source copy if the local file already exists. `TemporaryFilePaths` stores canonical NFS paths so downstream stages (VMAF, FileReplacement) are unaware of local staging.
- Output writes to the worker's configured `StagingDirectory` (from Workers table). Defaults to `C:\MediaVortex\` if not configured. In LocalStaging mode, output goes to local disk first, then is copied to StagingDirectory.
- Setting is read per-job via `GetTranscodeFileMode()` -> `SystemSettingsRepository.GetSystemSetting('TranscodeFileMode')`.
- To change: `POST /api/SystemSettings/TranscodeFileMode` with `{"Value": "LocalStaging"}`, `"CopyLocal"`, or `"InPlace"`.

**Path handling for distributed workers:**
- DB stores all paths in canonical (Windows) format: `T:\ShowName\file.mkv`
- `PathTranslationService` converts canonical <-> local using `ShareMountPrefix` and `ShareCanonicalPrefix` from Workers table
- Input paths: translated FROM canonical TO local before FFmpeg reads them
- Output paths: translated FROM local BACK TO canonical before storing in `TemporaryFilePaths`
- This ensures VMAF and FileReplacement (running on the primary machine) can always find files via the canonical `T:\` path
- `StagingDirectory` MUST be on the network share so all machines can access output files

**Key files for file staging:**
- `Features/TranscodeJob/ProcessTranscodeQueueService.py` -- `SetupFilePreparation()` reads setting, translates paths, returns effective input path
- `Features/TranscodeJob/TranscodingFileManagerService.py` -- `CopyFile()` uses `shutil.copy2()`, `SetupTranscodingDirectories(OutputDirectory)` creates directories
- `Services/CommandBuilderService.py` -- receives `InputPath`, `FFmpegPath`, `OutputDirectory` from TranscodingSettings, passes to `CommandBuilder`
- `Models/CommandBuilder.py` -- uses `CommandData['InputPath']` for FFmpeg `-i`, `CommandData['FFmpegPath']` for executable, `CommandData['OutputDirectory']` for output location
- `Core/Services/PathTranslationService.py` -- `ToLocalPath()` and `ToCanonicalPath()` for cross-platform translation

**FFmpeg command structure:**
- Executable: from `Workers.FFmpegPath` (falls back to `FFmpegMaster\bin\ffmpeg.exe`)
- Codec: libsvtav1 (all profiles)
- Preset: 6-8 (from profile)
- Quality: CRF from ProfileThresholds.Quality (adaptive if retranscode)
- Film grain: from profile
- Output: `{StagingDirectory}\{filename}_{resolution}.mp4`

**Tables written:** TranscodeAttempt (new), TranscodeFiles (aggregated), TranscodeProgress (real-time), ActiveJobs (with WorkerName), MediaFilesArchive, TranscodeQueue (status -> Running, ClaimedBy -> WorkerName), TemporaryFilePaths (canonical paths)

**Safety guards:**
- Atomic job claiming: `SELECT FOR UPDATE SKIP LOCKED` prevents two workers claiming the same job
- Crash recovery: stuck jobs (>12h) reset to Pending on service start
- ActiveJob tracking prevents duplicate processing (includes WorkerName for distributed identification). `ActiveJobs.ProcessId` is the worker's Python PID; `ActiveJobs.FFmpegPid` (added by stuck-job-detection.feature.md) is the FFmpeg subprocess PID -- the only legitimate kill target for stuck-job cleanup
- Worker heartbeat: 30-second interval, stale >5 min = worker offline, its jobs marked stuck
- Recurring stuck-job detection: each worker self-monitors its own jobs every `SystemSettings.StuckJobDetectionIntervalSec` (default 120s). Tier 1 catches dead workers via heartbeat, Tier 2 catches frame-stagnation hangs (default 5 min via `FrozenProgressThresholdMin`), Tier 3 catches dead-FFmpeg cases via `FFmpegPid` liveness + name check. Cleanup kills only `FFmpegPid` (never the worker), gated by host-locality. See `Features/ServiceControl/stuck-job-detection.flow.md`.
- CPU thermal management: waits for cool-down between jobs
- FFmpeg errors captured in TranscodeAttempt.ErrorMessage

---

## Stage 6: DISPOSITION -- Post-Transcode Decision

**Trigger:** Worker calls `DecidePostTranscodeDisposition(TranscodeAttemptId)` immediately after a successful transcode (TranscodeAttempt.Success=true). Single function, single call site, single return.

The disposition decision is **the only post-transcode branch point**. It reads from data-driven config and returns `(Disposition, Reason, AuditPayload)`. All five legacy decision sites (`ShouldQualityTestService`, `_ReplaceFileDirectly`, `CheckAndTriggerAutoReplace`, `ProcessFileReplacement`'s `BypassVMAFCheck` parameter, `ProcessFileReplacementWithVMAF`) are retired in favor of this one function. See `Features/QualityTesting/post-transcode-disposition.feature.md`.

**Inputs (data-driven):**

| Input | Source |
|---|---|
| `TranscodeAttempt.QualityTestRequired` | per-attempt flag, set at attempt creation from `Workers.QualityTestEnabled` |
| `TranscodeAttempt.NewSizeBytes` vs `OldSizeBytes` | post-flight savings gate |
| `QualityTestResults.VMAFScore` | populated by VMAF run, NULL when no test ran |
| `VmafCapableWorkerOnline` (computed) | `SELECT 1 FROM Workers WHERE QualityTestEnabled=TRUE AND Status='Online' AND LastHeartbeat > NOW() - INTERVAL '90 seconds'`. Replaces the legacy `ServiceStatus.QualityTestService` row, which was a fossil written only by the retired QualityTestService process. |
| `PostTranscodeGateConfig.VmafAutoReplaceMinThreshold` | typed column, default 88 |
| `PostTranscodeGateConfig.VmafAutoReplaceMaxThreshold` | typed column, default 98 |
| `PostTranscodeGateConfig.WhenVmafUnavailable` | `'block'` (default, safe) or `'bypass'` (operator opt-in) |
| `ProfileThresholds.KeepSource` | per-profile, controls `.orig` cleanup post-replace |

**Decision table** (canonical -- code MUST mirror this 1:1):

| Success | NewSize >= OldSize | QualityTestRequired | VMAF score | VmafCapableWorkerOnline | WhenVmafUnavailable | Disposition | Reason |
|---|---|---|---|---|---|---|---|
| false | n/a | n/a | n/a | any | any | `Discard` | `TranscodeFailed` |
| true | true (no savings) | any | any | any | any | `Discard` | `NoSavings` |
| true | false | false | n/a | any | any | `BypassReplace` | `QualityTestNotRequired` |
| true | false | true | NULL | true | any | `Pending` | `AwaitingVmaf` |
| true | false | true | < min | any | any | `Requeue` | `VmafBelowMin` |
| true | false | true | >= min, <= max | any | any | `Replace` | `VmafPassed` |
| true | false | true | > max | any | any | `NoReplace` | `VmafAboveMax` |
| true | false | true | NULL | false | block | `NoReplace` | `VmafServicePaused` |
| true | false | true | NULL | false | bypass | `BypassReplace` | `VmafServicePausedBypassed` |

**Disposition outcomes:**

| Disposition | What happens |
|---|---|
| `Replace` | FileReplacement proceeds: archive original, atomic rename, re-probe, update MediaFiles, settle `.orig` per `KeepSource`. |
| `BypassReplace` | Same as `Replace` mechanically -- the only difference is the audit reason. The file IS replaced; operator can query why VMAF was skipped. |
| `NoReplace` | Both files left in place. Staged transcoded output retained on the worker's `StagingDirectory` for operator inspection / manual replay. The TranscodeAttempt is final (no requeue). |
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

**Tables written:** TranscodeAttempts (Disposition, DispositionReason, DispositionDecidedAt), QualityTestQueue (when disposition='Pending' and not yet queued), MediaFiles (LastTranscodeOutcome on Discard/NoSavings), ProblemFiles (when Requeue with adjusted CRF below floor).

---

## Stage 7: VMAF -- Quality Test Execution (when Disposition='Pending' on first decision)

**Trigger:** Worker with `Workers.QualityTestEnabled=true` polls `QualityTestQueue` for rows added by the disposition function (Stage 6 row `Pending`/`AwaitingVmaf`).

**Code path:**
- `WorkerService/Main.py` -> `QualityTestingBusinessService.ProcessQualityTestQueue()`
- For each pending test:
  1. Build FFmpeg VMAF command: compare original vs transcoded using `libvmaf`
  2. Execute, parse JSON output for VMAF score (0-100)
  3. Insert `QualityTestResults` row with the score
  4. Re-call `DecidePostTranscodeDisposition(TranscodeAttemptId)` -- this time the VMAF score is available, the disposition will be `Replace` / `NoReplace` / `Requeue` per the table.

**Tables written:** QualityTestResults (new), TranscodeAttempts (VMAF score, QualityTestCompleted, Disposition+Reason re-decided).

---

## Stage 8: ACTION -- Execute the Disposition

**Trigger:** Disposition committed (anything other than `Pending`).

**Replace / BypassReplace path:**
- `Features/FileReplacement/FileReplacementBusinessService.ProcessFileReplacement(TranscodeAttemptId)` -- single entry point, no `BypassVMAFCheck` parameter (the disposition told us already).
  1. Validate TranscodeAttempt exists and FileReplaced=false
  2. Validate both original and transcoded files exist (path translation applied)
  3. Archive original metadata to MediaFilesArchive
  4. **Atomic rename-and-replace**: rename `original.ext -> original.ext.orig` as a backup, then move the staged file to `<originalbasename>-mv.<output-ext>` in the same directory. Verify target non-zero. On any filesystem-level failure, rollback restores the `.orig` and returns Success=false. The `-mv` suffix is the canonical MediaVortex on-disk marker -- structurally distinct from the source filename, defending against same-name collision regressions and giving operators a glance-readable "this was transcoded" signal. See `Features/FileReplacement/transcoded-output-placement.feature.md`.
  5. Re-probe new file via FFprobe (worker's FFprobe path)
  6. Update MediaFiles with new metadata, set TranscodedByMediaVortex=true. `MediaFiles.FilePath` now ends in `-mv.<ext>`.
  7. **Recompute compliance**: calls `RecomputeForFiles([MediaFileId])` to update `IsCompliant`, `RecommendedMode`, `PriorityScore`, `AssignedProfile`. This is what clears `RecommendedMode='Remux'` after a successful remux (container is now MP4, audio is normalized) so the file is not re-queued. If the file still needs work (e.g. remuxed but codec is h264), `RecommendedMode` flips to `'Transcode'`. See `transcode-vs-remux-routing.feature.md` criterion 17. Failure does NOT roll back -- file is on disk correctly.
  8. Settle `.orig` per `ProfileThresholds.KeepSource` (delete or rename to `<originalbasename>.old.<orig-ext>`). FileScanning skips `.old.<ext>` artifacts.

**Discard path:**
- Delete staged transcoded file from worker's `StagingDirectory`
- When reason is `NoSavings`: `MediaFiles.LastTranscodeOutcome='NoSavings'`

**Requeue path:**
- Delete staged transcoded file
- `AdaptiveQualityService.CalculateAdjustedCRF(previous_crf, vmaf_score)` -> new CRF
- If adjusted CRF >= 15 floor: insert new TranscodeQueue row with the lower CRF
- Else: log to ProblemFiles (file cannot be improved further)

**NoReplace path:**
- No filesystem changes. Staged file remains in `StagingDirectory` until operator manually clears or `Scripts/SQLScripts/CleanStagingOlderThan.py` runs.

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
MediaFiles.AssignedProfile   -- set at RECOMPUTE (cascade from ShowSettings/SystemSettings), read at TRANSCODE
MediaFiles.PriorityScore     -- set at RECOMPUTE, used by worker claim ORDER BY
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
- `TranscodeFileMode` -- `InPlace` (default) or `CopyLocal`. Controls whether source files are copied locally before transcoding.
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

Current (single-worker) flow:
1. `ProcessQueueLoop()` calls `GetNextJob()` every ~2 seconds when a slot is available
2. `GetNextJob()` delegates to `DatabaseManager.GetNextPendingTranscodeJob()`
3. Repository executes: `SELECT ... FROM TranscodeQueue WHERE Status = 'Pending' ORDER BY SizeMB DESC, DateAdded ASC LIMIT 1`
4. Separate UPDATE sets Status = 'Running' via `UpdateTranscodeQueueStatus(Job.Id, "Running")`

Race condition: Steps 3 and 4 are non-atomic. Two workers could SELECT the same row before either UPDATEs it. Fixed in distributed mode with `ClaimNextPendingTranscodeJob()` using `SELECT FOR UPDATE SKIP LOCKED`.

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
3. Loads its config (FFmpegPath, StagingDirectory, ShareMountPrefix, MaxConcurrentJobs) from Workers row
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
| 2.2 | Claim job atomically | `GetNextJob()` -> `DatabaseManager.ClaimNextPendingTranscodeJob(WorkerName)` | `UPDATE TranscodeQueue SET Status='Running', ClaimedBy=%s, ClaimedAt=NOW(), DateStarted=NOW() WHERE Id = (SELECT Id FROM TranscodeQueue WHERE Status='Pending' ORDER BY Priority DESC, DateAdded ASC LIMIT 1 FOR UPDATE SKIP LOCKED) RETURNING *` | TranscodeQueue.Status = `Running`, ClaimedBy = hostname |
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
| 3.8 | Store canonical paths | `PrivateCreateTemporaryFilePathRecord(AttemptId, OrigPath, CanonicalSource, CanonicalOutput)` | `INSERT INTO TemporaryFilePaths (TranscodeAttemptId, OriginalPath, LocalSourcePath, LocalOutputPath)` | All paths stored as canonical `T:\...` format (via `PathTranslation.ToCanonicalPath()`) |
| 3.9 | Update attempt with command | `DatabaseManager.UpdateTranscodeAttempt()` | `UPDATE TranscodeAttempts SET FfpmpegCommand=%s, ...` | -- |

### Phase 4: FFmpeg Execution

| Step | Action | Function | DB Call | Status Change |
|------|--------|----------|---------|---------------|
| 4.1 | Launch FFmpeg | `ExecuteTranscoding()` -> `VideoTranscodingService.StartTranscoding()` | -- | FFmpeg subprocess spawned |
| 4.2 | Track progress | `VideoTranscodingService` parses stderr | `INSERT/UPDATE TranscodeProgress (TranscodeAttemptId, CurrentFrame, TotalFrames, Percent, Speed, FPS, ...)` | Progress updated in real-time |
| 4.3 | Heartbeat continues | `HealthCheckLoop()` (background thread) | `UPDATE Workers SET LastHeartbeat = NOW()` | Proves worker is alive to other workers |
| 4.4 | FFmpeg completes | `VideoTranscodingService` returns result | -- | Output file exists in StagingDirectory |

### Phase 5: Post-Transcode Handling

| Step | Action | Function | DB Call | Status Change |
|------|--------|----------|---------|---------------|
| 5.1 | Calculate size reduction | `HandleTranscodingResult()` | -- | -- |
| 5.2 | Mark attempt successful | `DatabaseManager.UpdateTranscodeAttempt()` | `UPDATE TranscodeAttempts SET Success=True, CompletedDate=NOW(), NewSizeBytes=%s, SizeReductionBytes=%s, SizeReductionPercent=%s, QualityTestRequired=True` | Attempt marked successful |
| 5.3 | Update TranscodeFiles | `UpdateTranscodeFileRecord()` | `INSERT/UPDATE TranscodeFiles (FilePath, SuccessfulAttemptId, ...)` | File-level status updated |
| 5.4 | Bridge: quality test or replace | `ShouldQualityTest.ProcessTranscodedFile(AttemptId, OrigPath, OutputPath)` -- checks `TranscodeAttempts.QualityTestRequired`. If False or service paused: calls `FileReplacementBusinessService.ProcessFileReplacement(AttemptId, BypassVMAFCheck=True)` directly (delete original, update DB). If True: `QualityTestQueueService.AddToQualityTestQueue()` | QualityTestRequired=False: archive + delete original + UPDATE MediaFiles + DELETE TemporaryFilePaths. QualityTestRequired=True: `INSERT INTO QualityTestQueue (...)` | QualityTestQueue.Status = `Pending` (if queued) or file replaced (if skipped) |
| 5.5 | Delete from TranscodeQueue | `DatabaseManager.DeleteTranscodeQueueItem(Job.Id)` | `DELETE FROM TranscodeQueue WHERE Id = %s` | Job removed from queue |
| 5.6 | Clean progress | `DatabaseManager.DeleteTranscodeProgress(AttemptId)` | `DELETE FROM TranscodeProgress WHERE TranscodeAttemptId = %s` | -- |
| 5.7 | Complete ActiveJob | `DatabaseManager.CompleteActiveJob(ActiveJobId, Success=True)` | `UPDATE ActiveJobs SET Status='Completed', CompletedAt=NOW()` | ActiveJobs.Status = `Completed` |

### Phase 6: Quality Testing (WorkerService with QualityTestEnabled=TRUE)

| Step | Action | Function | DB Call | Status Change |
|------|--------|----------|---------|---------------|
| 6.1 | Claim quality job | WorkerService quality test loop polls | `SELECT FROM QualityTestQueue WHERE Status='Pending'` | QualityTestQueue.Status = `Running` |
| 6.2 | Read paths from DB | Reads TemporaryFilePaths | `SELECT OriginalPath, LocalOutputPath FROM TemporaryFilePaths WHERE TranscodeAttemptId = %s` | Paths are canonical `T:\...` -- accessible from primary machine |
| 6.3 | Run VMAF | FFmpeg VMAF comparison (original vs transcoded) | -- | Both files read from network share via canonical paths |
| 6.4 | Store VMAF score | `UpdateTranscodeAttempt()` | `UPDATE TranscodeAttempts SET VMAF = %s, QualityTestCompleted = True` | VMAF score recorded |
| 6.5 | Decide: pass/fail | VMAF >= 80 = pass | -- | -- |

### Phase 7: File Replacement (if VMAF passes, or directly after transcode when QualityTestRequired=False)

| Step | Action | Function | DB Call | Status Change |
|------|--------|----------|---------|---------------|
| 7.1 | Trigger replacement | `FileReplacementBusinessService.ProcessFileReplacement(AttemptId, BypassVMAFCheck)` | -- | PathTranslation passed from caller |
| 7.2 | Read file paths | from TemporaryFilePaths | `SELECT OriginalPath, LocalOutputPath FROM TemporaryFilePaths WHERE TranscodeAttemptId = %s` | Canonical paths: `T:\...\output.mkv` and `T:\...\original.mkv` |
| 7.3 | Archive original metadata | `_ArchiveOriginalFileDetails()` | `INSERT INTO MediaFilesArchive (...)` | Snapshot before destructive ops |
| 7.4 | Delete original (or rename if KeepSource) | `_ProcessCompleteFileReplacement()` translates canonical paths via `PathTranslation.ToLocalPath()` | -- | `os.remove(LocalOriginalPath)` or `os.rename(..., .old)` |
| 7.5 | Move output if needed | InPlace: skip (already in correct dir). Staged: `shutil.move()` | -- | `os.path.normpath` comparison decides |
| 7.6 | Update MediaFiles | `_UpdateMediaFilesAfterReplacement()` re-probes transcoded file | `UPDATE MediaFiles SET FilePath=..., Resolution=..., Codec=..., SizeMB=..., TranscodedByMediaVortex=True, LastScannedDate=NOW()` | MediaFiles reflects new file |
| 7.7 | Mark attempt replaced | | `UPDATE TranscodeAttempts SET FileReplaced=True, FileReplacedDate=NOW()` | -- |
| 7.8 | Cleanup temp paths | `_CleanupTemporaryFilePaths()` | `DELETE FROM TemporaryFilePaths WHERE TranscodeAttemptId = %s` | No orphaned rows |

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
| Database (canonical) | Windows backslash | `T:\Shows\Show Name\S01E01.mkv` |
| Linux worker local | Forward slash, mount prefix | `/mnt/media/Shows/Show Name/S01E01.mkv` |
| Windows worker local | Same as canonical | `T:\Shows\Show Name\S01E01.mkv` |
| TemporaryFilePaths (DB) | Always canonical | `T:\MediaVortex\Staging\S01E01.mkv` |
| FFmpeg command (local) | Worker's native format | `/mnt/media/MediaVortex/Staging/S01E01.mkv` |

Translation happens at two points:
1. **Input**: `SetupFilePreparation()` calls `PathTranslation.ToLocalPath()` before FFmpeg reads
2. **Output**: `PrivateCreateTemporaryFilePathRecord()` calls `PathTranslation.ToCanonicalPath()` before writing to DB

This ensures any machine (VMAF on primary, FileReplacement on primary) can always find both files via canonical paths on the shared network drive.
