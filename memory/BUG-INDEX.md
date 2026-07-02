# Bug Index

Terse one-line-per-bug index. Drill into `memory/KNOWN-ISSUES.md` for full detail.
Entry shape: `- BUG-NNNN | <active|resolved> | <area> | <desc> | <created>[ -> <resolved>]`

## Active

- BUG-0024 | active | file-scanning | Scan pipeline perf + observability (FindFuzzyFileMatch O(NxM), missing counters, single-threaded stats, silent progress writer) | 2026-05-15
- BUG-0025 | active | worker-lifecycle | Worker status / capability model cleanup (Draining broken, non-data-driven concurrency, UI-uneditable flags) | 2026-05-14
- BUG-0026 | active | quality-testing | VMAF measurement quality (held-frame bimodal -- PARTIAL FIX) + MonitorVMAFProgress emit gap | 2026-05-10
- BUG-0027 | active | path-storage | Path storage OS-coupled (CRITICAL, WORKAROUND IN PLACE; umbrella covers natural-key denorm + broken-canonical scan failures) | 2026-05-05
- BUG-0028 | active | tech-debt | Vertical-slice migration backlog (QueueManagement Cursor cleanup + DatabaseManager monolith + boundary mismatches) | 2026-05-07
- BUG-0029 | active | transcode-job | TranscodeAttempts failure rows lack ProfileName | 2026-05-16
- BUG-0030 | active | file-scanning | Status page Possibly Corrupt count has no drill-down | 2026-05-13
- BUG-0031 | active | show-settings | Next Remux Batch shows files with no audio stream | 2026-05-14
- BUG-0033 | active | deploy | Linux worker deploy flow doc incomplete (no post-deploy verification or troubleshooting) | 2026-05-13
- BUG-0034 | active | quality-testing | Terminology inconsistency: quality test (policy) vs VMAF (metric) | 2026-05-12
- BUG-0035 | active | config | env-driven config singleton __new__ never fires; knobs scattered | 2026-05-10
- BUG-0036 | active | transcode-queue | Profile-less savings estimate uses misleading SizeMB*0.5 (CRITICAL) | 2026-05-10
- BUG-0037 | active | activity-page | TECH DEBT -- Activity page conflates worker liveness and operational state | 2026-05-08
- BUG-0038 | active | system-settings | SystemSettings not normalized; /settings page does not show every row | 2026-05-08
- BUG-0040 | active | transcode-job | Second concurrent job shows first job's progress | 2026-05-05
- BUG-0043 | active | transcode-queue | TranscodeQueue claim has no codec affinity; NVENC workers grab CPU-profile jobs and burn GPU compute; fix path = worker-routing.feature.md (DRAFTED) | 2026-06-03
- BUG-0044 | active | worker-lifecycle | CpuAffinityService loses SystemSettingsRepository wiring on every worker startup; AttributeError caught, falls back to defaults, configured thermal knobs silently ignored | 2026-06-06
- BUG-0061 | active | failure-accounting | CLUSTER -- TranscodeAttempts accountability + encode-failure budget + FailedJobs operator surface + ProfileName-on-failure + ShowSettings exclusion; SOLID rewrite via new Features/FailureAccounting vertical; subsumes BUG-0055 + BUG-0060 + BUG-0029 | 2026-06-12
- BUG-0062 | active | compliance | CLUSTER -- Compliance writeback invariant enforcement; ComplianceDecision self-validates, ComplianceBucketResolver is sole (IsCompliant, WorkBucket) source, SQL CHECK + contract test; subsumes BUG-0056 | 2026-06-12
- BUG-0063 | active | activity-page | CLUSTER -- Activity dashboard SOLID rewrite; ProgressSmoothingService + ActiveJobsViewModel + WorkerStatusRenderer + ETACountdownTimer + single GetDashboardSnapshot payload; adopts DRAFTED activity-dashboard-improvements C1-C22; subsumes BUG-0057 + BUG-0058 + BUG-0059 + BUG-0040 + BUG-0037 + BUG-0025 + BUG-0007 | 2026-06-12
- BUG-0064 | active | deploy | Deploy script consolidation -- I9 local services skip deploy entirely (start with their own venv, WebService first, must stop existing I9 worker before start); remote-worker deploys have zero inter-worker dependencies; single SOLID strategy-pattern deploy script replaces deploy-linux-worker.py + deploy-windows-worker.py + fleet wrapper | 2026-06-23
- BUG-0065 | active | audio-default | Default audio track must be English when source carries multiple language audio streams -- override the "first present language" final fallback in _PickDefaultLanguage so the English stream gets disposition.default=1 | 2026-06-23
- BUG-0066 | active | audio-pipeline | Audio pipeline has silent fallback chains (LanguageDetector.Detect C11 + _PickDefaultLanguage L1) -- principle violation; silent fallbacks hide whether the primary rule fired; pipeline must fail loud or record which rule won so operator can verify the system is working; reshapes BUG-0065 fix path away from "add another fallback layer" | 2026-06-23
- BUG-0069 | active | transcodequeue / subtitle-fix | PopulateQueueForSubtitleFix references undefined existingFilePaths (latent NameError); crashes on first admitted file via existingFilePaths.add -- dead-code residue from per-FilePath dedup design replaced by pair-based dedup | 2026-06-28
- BUG-0070 | active | audio-quality | Detect transcoded files affected by deprecated 96 kbps audio bitrate -- robotic-sounding audio across library; need query/report from TranscodeAttempts.FfpmpegCommand or AudioBitrateKbps to flag re-transcode candidates | 2026-06-29
- BUG-0072 | active | media-recovery | Delete + requeue Sonarr/Radarr for shows and movies destroyed by -ac 2 forced-downmix + b:a 96k under-bitrate + MaxAudioChannels=2 global; optional reality-TV exclusion; source .mkv already replaced so files must be re-acquired | 2026-07-01
- BUG-0073 | active | audio-loudnorm | Track 0 emits identical loudnorm measured_I / measured_LRA / measured_TP / measured_thresh across every per-language Original stream; file-level EBU R128 measurement re-used per stream; non-default languages over/under-normalize; needs per-stream measurement in _BuildTrack0Chain | 2026-07-02
- BUG-0074 | resolved | audio-channels | AudioFilterEmitter._ResolveSourceChannels silently defaults to 2 when MediaFile.AudioChannels is NULL; real 5.1 sources with missing metadata ship as stereo at the 96k floor; violates C33 spirit; fail-loud or backfill AudioChannels via ffprobe before emit | 2026-07-02 -> 2026-07-02 (fail-loud via AudioPolicyUnresolvedError; Tests/Contract/TestAudioChannelsFailLoud.py 5/5)

- BUG-0002 | active | file-replacement | Silent-output Remux MediaFiles purge | 2026-05-16
- BUG-0007 | active | activity-page | Worker capability toggle no UI refresh | 2026-05-22
- BUG-0020 | active | worker-lifecycle | Workers must own processes end-to-end; -mv only when compliant (C3 FR-internal TFP leak absorbed by filereplacement-decompose 2026-06-02; C5 operator zero-candidate fleet pass remains) | 2026-05-26

## Recently Resolved (last 10)

- BUG-0068 | resolved | transcode-emit | AudioFilterEmitter STRATEGY_REVIEW bypass + TranscodeShape bare -c:a copy fallback; closed by directive `audio-pipeline-fail-loud` (Phase D wiring + 53/53 audio contract tests PASS); REVIEW now routes through AudioDispositionResolver + ceiling clamp, empty-Blocks branch uses EAC3OrPassthroughCodecPolicy.Decide, AudioPolicyUnresolvedError fails loud with verdict persistence | 2026-06-23 -> 2026-06-27
- BUG-0067 | resolved | file-replacement | TranscodedOutputPlacement orphan-on-failure; closed by /t BUG-0067 within `worker-runtime-state` directive -- Execute + FinalizePartialReplacement now roll back the rename + return Success=False with the real update error; SameSlot path defers BackupPath delete until update commits; contract test TestFileReplacementRollbackOnUpdateFailure 3/3 PASS | 2026-06-23 -> 2026-06-23
- BUG-0055 | superseded | transcode-queue | TranscodeQueue has no encode-failure cap; folded into BUG-0061 (failure-accounting cluster) at filing time; evidence preserved in KNOWN-ISSUES | 2026-06-12 -> 2026-06-12
- BUG-0056 | superseded | compliance | Compliance writes contradictory rows; folded into BUG-0062 (writeback-invariant cluster) at filing time | 2026-06-12 -> 2026-06-12
- BUG-0057 | superseded | activity-page | FPS/Speed columns raw spot values; folded into BUG-0063 (activity-dashboard SOLID cluster) at filing time | 2026-06-12 -> 2026-06-12
- BUG-0058 | superseded | activity-page | ETA recomputes erratically; folded into BUG-0063 at filing time | 2026-06-12 -> 2026-06-12
- BUG-0059 | superseded | activity-page | Active Jobs hidden during drain; folded into BUG-0063 at filing time | 2026-06-12 -> 2026-06-12
- BUG-0060 | superseded | transcode-job | 1455 orphan TranscodeAttempts; folded into BUG-0061 at filing time | 2026-06-12 -> 2026-06-12
- BUG-0053 | resolved | tests | Tests/Contract/TestMediaProbeUsesPath.py SELECTs non-column m.FilePath; closed by prereq hotfix 42ed437 (SELECT rewritten to typed pair) | 2026-06-09 -> 2026-06-12
- BUG-0052 | resolved | path-storage | Core/PathStorage.py importers migrated to Core.Path.LocalPath/PathFs; CLAUDE.md docs swept; closed by prereq hotfix 42ed437 | 2026-06-09 -> 2026-06-12
- BUG-0051 | resolved | transcode-queue | ProcessRemuxQueueService AttributeError; closed structurally by perfect-solid-transcode-pipeline-phase3 commit 39d04a1 (file deleted, surface gone) | 2026-06-09 -> 2026-06-12
