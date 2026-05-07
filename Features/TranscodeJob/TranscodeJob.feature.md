# TranscodeJob Feature

Executes FFmpeg transcode jobs from the queue, tracks progress, and handles results.

## Scope

- `Features/TranscodeJob/**`
- `TranscodeService/Main.py`

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
- True in-place output: transcoded file is written to the same directory as the source file (not a staging directory). Output filename includes target resolution (e.g. 480p) so it coexists with the original until replacement.
- Output location mode: SystemSettings.TranscodeOutputMode controls output placement. "InPlace" = same directory as source (default). "Staging" = worker's StagingDirectory or SystemSettings.StagingDirectory.
- VMAF quality test toggle: SystemSettings.QualityTestEnabled (global on/off, default OFF). Workers.QualityTestEnabled (per-worker override, NULL = use global). TranscodeAttempts.QualityTestRequired is set from these at job creation time, not hardcoded.
- Per-worker FFprobe: Workers.FFprobePath flows through ProcessTranscodeQueueService -> CommandBuilderService -> FFmpegAnalysisService -> FFmpegService. Audio stream selection (English preferred) uses the worker's local FFprobe, not the global SystemSettings path.
- [BUG] TranscodeJob scope declares `Features/TranscodeJob/**` and `TranscodeService/Main.py`, but criteria govern code in `Services/CommandBuilderService.py`, `Services/FFmpegAnalysisService.py`, `Services/FFmpegService.py`, and `Core/Services/PathTranslationService.py`. Either the scope expands to cover those files, or the criteria that govern them move to separate feature docs that own those files.

## Progress

- [x] Single-job transcoding pipeline
- [x] Distributed worker support (Phase 1)
- [x] Fix: worker isolation -- SignalHandler, CrashRecovery, StuckJobDetector, QueueManagement scoped by WorkerName
- [x] Interlaced routing: AcceptsInterlaced flag on Workers, claim query filters by IsInterlaced
- [x] Conditional deinterlacing: CommandBuilder applies yadif based on MediaFile.IsInterlaced, not profile
- [x] True in-place output: CommandBuilder uses source file directory instead of OutputDirectory
- [x] Output location mode: add TranscodeOutputMode setting, respect InPlace vs Staging
- [x] VMAF toggle: add QualityTestEnabled global setting (default OFF) and per-worker column
- [ ] Per-worker FFprobe: wire Workers.FFprobePath through to audio stream analysis
- [ ] Fix: concurrent job progress isolation (see KNOWN-ISSUES.md)
