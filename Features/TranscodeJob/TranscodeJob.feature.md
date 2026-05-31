# TranscodeJob Feature

Executes FFmpeg transcode jobs from the queue, tracks progress, and handles results.

## Scope

- `Features/TranscodeJob/**`
- `WorkerService/Main.py`

## Criteria

- Jobs claimed from queue are executed via FFmpeg with the correct command built from profile settings
- Progress is tracked per-job via TranscodeProgress table and reported to the UI
- [BUG] Each running job MUST report independent progress -- when multiple jobs run concurrently, each job's progress reflects its own FFmpeg process, not another job's
- Failed jobs are marked failed with error message and do not block the queue
- Completed jobs update TranscodeAttempts with final size, duration, and FFmpeg command
- ActiveJobs table tracks running processes for stuck-job detection
- Distributed workers claim jobs atomically via SELECT FOR UPDATE SKIP LOCKED
- Worker isolation: all destructive operations (shutdown cleanup, crash recovery, stuck detection, stop) are scoped to the calling worker via ClaimedBy/WorkerName. No worker may reset, kill, or interfere with another worker's jobs.
- Interlaced routing: workers with AcceptsInterlaced=FALSE skip interlaced files in the claim query. Interlaced files remain Pending until a capable worker claims them.
- Conditional deinterlacing: yadif is applied by CommandBuilder only when MediaFile.IsInterlaced=TRUE, not based on profile settings. Progressive files never get yadif regardless of profile.
- True in-place output: transcoded file is written to the same directory as the source file. Output filename ends in `-mv.mp4.inprogress` so it coexists with the original until FileReplacement renames it and swaps the source out. There is no staging directory and no `TranscodeOutputMode` setting; in-place is the only mode.
- VMAF quality test toggle: SystemSettings.QualityTestEnabled (global on/off, default OFF). Workers.QualityTestEnabled (per-worker override, NULL = use global). TranscodeAttempts.QualityTestRequired is set from these at job creation time, not hardcoded.
- Per-worker FFprobe: Workers.FFprobePath flows through ProcessTranscodeQueueService -> CommandBuilderService -> FFmpegAnalysisService -> FFmpegService. Audio stream selection (English preferred) uses the worker's local FFprobe, not the global SystemSettings path.
- [FIXED] Progress display must not depend on TranscodeQueue: any job with an active TranscodeProgress record and TranscodeAttempts.Success IS NULL must appear in the progress UI, regardless of whether a TranscodeQueue row exists.
- [BUG] TranscodeJob scope declares `Features/TranscodeJob/**` and `WorkerService/Main.py`, but criteria govern code in `Services/CommandBuilderService.py`, `Services/FFmpegAnalysisService.py`, `Services/FFmpegService.py`, and `Core/Services/PathTranslationService.py`. Either the scope expands to cover those files, or the criteria that govern them move to separate feature docs that own those files.
- [BUG] Worker MUST verify the source file exists at the resolved local path BEFORE invoking FFprobe to build the transcode command. When the source is missing, the worker MUST: (a) record `MediaFiles.LastFFprobeError = "Source file missing"` and `LastFFprobeAttemptDate = NOW()`, (b) increment `MediaFiles.FFprobeFailureCount`, (c) DELETE the `TranscodeQueue` row, and (d) NOT create a `TranscodeAttempt` row. This must happen *before* any FFprobe/FFmpeg subprocess so missing files do not generate noisy failed-attempt history that the user has to chase.
- [BUG] When `SetupFilePreparation` fails for a remux (or any) job, the `TranscodeAttempts.ErrorMessage` MUST include the actual exception detail (e.g. the missing path), not just the generic wrapper "Failed to setup file preparation for remux". The root cause must be diagnosable from the attempts table alone without querying the Logs table. Additionally, `ProcessRemuxJob` MUST verify the source file exists at the resolved path BEFORE creating the TranscodeAttempt row, consistent with criterion 17.

- [BUG-0022 RESOLVED 2026-05-28] **NVENC encoder path shipped.** CommandBuilder deterministically dispatches `av1_nvenc` when `ProfileSettings.UseNvidiaHardware=1`, emitting the shootout-winner knob set (preset p7, tune uhq, multipass fullres, rc vbr+cq, aq-strength 15, rc-lookahead 32, bf 7, b_ref_mode middle, pix_fmt p010le). Worker capability gate (`Workers.nvenccapable` + `DatabaseManager.ClaimNextPendingTranscodeJob`) routes NVENC jobs to NVENC-capable workers only. Two production profiles in `Profiles` table (`NVENC AV1 P7 UHQ CQ32 -480p`, `NVENC AV1 P7 UHQ CQ32 -720p`). See `Features/Profiles/nvenc-profiles.feature.md` for the full feature; `Scripts/Smoke/EncoderShootout.feature.md` for the evaluation methodology.

- **Scale filter is width-anchored, aspect-preserving.** When CommandBuilder decides to emit `-vf scale=...`, the filter shape is `scale=w=<TierWidth>:h=-2` where `TierWidth` is the target tier's canonical width (480p→854, 720p→1280, 1080p→1920, 2160p→3840) and `-2` instructs FFmpeg to compute a codec-legal even height from source aspect. There is no `scale=W:H` (forced) branch and no `PreserveAspect` toggle. Verifiable: every `TranscodeAttempts.FfpmpegCommand` containing `-vf` matches the pattern `-vf "scale=w=(854|1280|1920|3840):h=-2"`. Negation: a wide-aspect 1920x802 source targeting 720p produces `1280x534` output (preserving the 2.40:1 ratio), not `1280x720` (which would vertically stretch).

- [BUG] **TranscodeAttempts failure rows MUST identify what was attempted.** When a remux or transcode job fails at ANY stage (including pre-flight, pre-FFmpeg, or post-FFmpeg), the resulting `TranscodeAttempts` row MUST have non-NULL `ProfileName` so an operator can tell from the row alone what KIND of job failed -- 'Remux' or the specific transcode profile name. Confirmed violated against attempts 16240-16243 on 2026-05-16: 4 remux jobs failed with "No active StorageRootResolutions row for (StorageRootId=None, ...)", all rows have Success=False and ErrorMessage populated correctly per criterion 29, BUT ProfileName=NULL on every row. The queue row was deleted by the failure handler, so without joining MediaFiles via MediaFileId the operator cannot tell that these were Remux attempts and cannot distinguish them from any other failed job type. Note: `FilePath=NULL` on these rows is BY DESIGN per the FilePath-denormalization cleanup in KNOWN-ISSUES "FilePath used as denormalized natural key across 6+ tables" -- the operator joins MediaFiles via MediaFileId for the path. ProfileName is NOT in that denormalization scope. Fixed means: every TranscodeAttempts INSERT in the failure path sets `ProfileName` from the queue row's `ProcessingMode` ('Remux' literal) or from the resolved transcode profile (for non-remux jobs), regardless of how early in the pipeline the failure happens. Verifiable: trigger a remux job that fails at the Resolve() call (set StorageRootId=None on a queue row); query the resulting TranscodeAttempts row; observe `ProfileName='Remux'`.

## Seams

| Seam | Producer | Wire shape | Consumer expects | Verification |
|---|---|---|---|---|
| `TranscodeQueue` claim | `QueueManagementBusinessService` | `TranscodeQueue.(StorageRootId BIGINT, RelativePath TEXT, AssignedProfile TEXT, ProcessingMode TEXT, AcceptsInterlaced BOOLEAN) Status='Pending'` | `DatabaseManager.ClaimNextPendingTranscodeJob` (`FOR UPDATE OF tq SKIP LOCKED`); NVENC profiles additionally gate on `Workers.nvenccapable=TRUE` | `SELECT COUNT(*) FROM TranscodeQueue WHERE Status='Pending'` decrements after claim |
| `EncoderKnobRepository` → `GetTranscodingSettings` | `Profiles` + `ProfileThresholds` DB join on ProfileName + normalized resolution category | `EncoderKnobs` dataclass `.ToDict()` dict; `ProcessTranscodeQueueService.GetTranscodingSettings` injects `SourceVideoBitrateKbps=MediaFile.VideoBitrateKbps`. Normalization: long-edge bucket via `_NormalizeResolution` -- `max(W,H) >= 3840 → '2160p'`, `>= 1920 → '1080p'`, `>= 1280 → '720p'`, else `'480p'`. So `'1920x802'` (letterbox crop) → `'1080p'`, not `'720p'` | `CommandBuilder` reads `ProfileSettings` dict keys | Smoke: `py /tmp/smoke_legacy.py` (SVT) + `py /tmp/smoke_canary.py` (NVENC VBR) |
| In-place output path | `CommandBuilder.GenerateOutputFileName` | Worker-local path `{source_dir}/{basename}-mv.mp4.inprogress`. No `StagingDirectory`. `TranscodeOutputMode` row was vestigial (unread); removed by `Scripts/SQLScripts/RemoveVestigialOutputModeSetting.py` | `PrivateCreateTemporaryFilePathRecord` writes canonical form to `TemporaryFilePaths.(OutputStorageRootId, OutputRelativePath)` | After encode: `{source_dir}/{basename}-mv.mp4.inprogress` exists adjacent to source on shared mount |
| `TemporaryFilePaths` → VMAF / FileReplacement | `ProcessTranscodeQueueService.PrivateCreateTemporaryFilePathRecord` | `TemporaryFilePaths.(TranscodeAttemptId BIGINT, OriginalPath TEXT, LocalSourcePath TEXT, LocalOutputPath TEXT, OutputStorageRootId BIGINT, OutputRelativePath TEXT)` -- paths in canonical DB form | `QualityTestingBusinessService` and `FileReplacementBusinessService` both read this row to locate the transcoded file. `UpdateTemporaryFilePath` is called after encode to write `LocalOutputPath` | `SELECT COUNT(*) FROM TemporaryFilePaths tfp JOIN TranscodeAttempts ta ON ta.Id = tfp.TranscodeAttemptId WHERE ta.Success IS NULL AND ta.FileReplaced IS NOT TRUE` → count of in-flight encodes |
| `MediaFiles.IsInterlaced` → CommandBuilder yadif | `MediaFiles.isinterlaced BOOLEAN NULL` (NULL = not probed = treated as progressive) | Python check: `str(RawInterlaced).strip().lower() in ('1','true','yes','t')` | `CommandBuilder.BuildVideoFilters` applies yadif only when `IsInterlaced` evaluates True | `SELECT COUNT(*) FROM MediaFiles WHERE isinterlaced IS NULL AND transcodedbymedavortex IS NULL` → files not yet probed (treated as progressive) |

## Progress

- [x] Single-job transcoding pipeline
- [x] Distributed worker support (Phase 1)
- [x] Fix: worker isolation -- SignalHandler, CrashRecovery, StuckJobDetector, QueueManagement scoped by WorkerName
- [x] Interlaced routing: AcceptsInterlaced flag on Workers, claim query filters by IsInterlaced
- [x] Conditional deinterlacing: CommandBuilder applies yadif based on MediaFile.IsInterlaced, not profile
- [x] True in-place output: CommandBuilder writes the `.inprogress` output next to the source. The legacy `TranscodeOutputMode` / `TranscodeFileMode` settings + `Workers.StagingDirectory` column were removed 2026-05-21 once LocalStaging was retired.
- [x] VMAF toggle: add QualityTestEnabled global setting (default OFF) and per-worker column
- [x] Per-worker FFprobe: WorkerContext singleton provides FFprobePath to FFmpegService automatically, no explicit threading needed
- [ ] Fix: concurrent job progress isolation (see KNOWN-ISSUES.md)
