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

- BUG-0002 | active | file-replacement | Silent-output Remux MediaFiles purge | 2026-05-16
- BUG-0007 | active | activity-page | Worker capability toggle no UI refresh | 2026-05-22
- BUG-0020 | active | worker-lifecycle | Workers must own processes end-to-end; -mv only when compliant (C3 FR-internal TFP leak absorbed by filereplacement-decompose 2026-06-02; C5 operator zero-candidate fleet pass remains) | 2026-05-26

## Recently Resolved (last 10)

- BUG-0055 | superseded | transcode-queue | TranscodeQueue has no encode-failure cap; folded into BUG-0061 (failure-accounting cluster) at filing time; evidence preserved in KNOWN-ISSUES | 2026-06-12 -> 2026-06-12
- BUG-0056 | superseded | compliance | Compliance writes contradictory rows; folded into BUG-0062 (writeback-invariant cluster) at filing time | 2026-06-12 -> 2026-06-12
- BUG-0057 | superseded | activity-page | FPS/Speed columns raw spot values; folded into BUG-0063 (activity-dashboard SOLID cluster) at filing time | 2026-06-12 -> 2026-06-12
- BUG-0058 | superseded | activity-page | ETA recomputes erratically; folded into BUG-0063 at filing time | 2026-06-12 -> 2026-06-12
- BUG-0059 | superseded | activity-page | Active Jobs hidden during drain; folded into BUG-0063 at filing time | 2026-06-12 -> 2026-06-12
- BUG-0060 | superseded | transcode-job | 1455 orphan TranscodeAttempts; folded into BUG-0061 at filing time | 2026-06-12 -> 2026-06-12
- BUG-0053 | resolved | tests | Tests/Contract/TestMediaProbeUsesPath.py SELECTs non-column m.FilePath; closed by prereq hotfix 42ed437 (SELECT rewritten to typed pair) | 2026-06-09 -> 2026-06-12
- BUG-0052 | resolved | path-storage | Core/PathStorage.py importers migrated to Core.Path.LocalPath/PathFs; CLAUDE.md docs swept; closed by prereq hotfix 42ed437 | 2026-06-09 -> 2026-06-12
- BUG-0051 | resolved | transcode-queue | ProcessRemuxQueueService AttributeError; closed structurally by perfect-solid-transcode-pipeline-phase3 commit 39d04a1 (file deleted, surface gone) | 2026-06-09 -> 2026-06-12
- BUG-0050 | resolved | quality-testing | AdaptiveQualityService FilePath NameError; closed structurally by perfect-solid-transcode-pipeline Phase 1 (RetranscodeDecider pure fn, no FilePath identifier) | 2026-06-09 -> 2026-06-12
- BUG-0049 | resolved | audio-pipeline | BuildAudioFilters ungainable_peak; closed by perfect-solid-transcode-pipeline-phase2 (typed UngainablePeakError + dynamic-mode fallback per linear-loudnorm.feature.md C10) | 2026-06-09 -> 2026-06-12
- BUG-0048 | resolved | command-builder | RemuxShape missing -f mp4 -movflags +faststart; closed by perfect-solid-transcode-pipeline-phase2 (unconditional emit + contract test loops every dispatch) | 2026-06-09 -> 2026-06-12
- BUG-0054 | resolved | transcode-queue | Upscale block missed 480p->720p step; root cause = ProfileSettings.TargetResolution collapses to source when per-source-row TranscodeDownTo is blank/'No downscaling'; fix = ProfileRepository.GetProfileMaxTarget(profile) read by EvaluateQueueAdmission + Cartesian contract test | 2026-06-09 -> 2026-06-09
- BUG-0047 | resolved | transcode-queue | dot-worker-1 not claiming NVENC silent no-op; root cause = no GPU passthrough in Docker (fixed by linux-nvenc-passthrough); operator-visibility GUI checkbox + tile warning badge shipped via worker-routing C15 | 2026-06-08 -> 2026-06-08
- BUG-0042 | resolved | activity-page | Active Jobs list omits VMAF runs while badge counts them; operator kills workers thinking they are hung, orphaning claimed rows | 2026-06-03 -> 2026-06-03
- BUG-0041 | resolved | sql-queries | QueryDatabase.py truncates long text columns at 60 chars | 2026-05-13 -> 2026-06-02
