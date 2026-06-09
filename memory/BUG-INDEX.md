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
- BUG-0048 | active | command-builder | _BuildRemuxShape missing -f mp4 -movflags +faststart (BUG-0005 regression scoped only to Transcode dispatch); every Remux job fails return code 234 | 2026-06-09
- BUG-0049 | active | audio-pipeline | BuildAudioFilters raises RuntimeError on ungainable_peak instead of emitting dynamic-mode loudnorm; violates linear-loudnorm.feature.md C10 (dynamic fallback) + C2 (no longer block) | 2026-06-09
- BUG-0050 | active | quality-testing | AdaptiveQualityService.ShouldRetranscode references undefined `FilePath` in LogDebug at line 160 -- NameError raised on every first-attempt path | 2026-06-09
- BUG-0051 | active | transcode-queue | ProcessRemuxQueueService._ClaimNextRemuxJob raises AttributeError 'object has no attribute DatabaseManager' despite __init__ assigning it -- workers losing the wiring at runtime | 2026-06-09
- BUG-0052 | active | path-storage | Core/PathStorage.py source deleted; .pyc cache remains; 6 importers (StartWorker.py + 5 tests/scripts) ModuleNotFoundError on invocation; CLAUDE.md still documents the dead module | 2026-06-09
- BUG-0053 | active | tests | Tests/Contract/TestMediaProbeUsesPath.py SELECTs non-column m.FilePath (computed property, not DB column) -- psycopg2 UndefinedColumn during contract suite | 2026-06-09

- BUG-0002 | active | file-replacement | Silent-output Remux MediaFiles purge | 2026-05-16
- BUG-0007 | active | activity-page | Worker capability toggle no UI refresh | 2026-05-22
- BUG-0020 | active | worker-lifecycle | Workers must own processes end-to-end; -mv only when compliant (C3 FR-internal TFP leak absorbed by filereplacement-decompose 2026-06-02; C5 operator zero-candidate fleet pass remains) | 2026-05-26

## Recently Resolved (last 10)

- BUG-0047 | resolved | transcode-queue | dot-worker-1 not claiming NVENC silent no-op; root cause = no GPU passthrough in Docker (fixed by linux-nvenc-passthrough); operator-visibility GUI checkbox + tile warning badge shipped via worker-routing C15 | 2026-06-08 -> 2026-06-08
- BUG-0042 | resolved | activity-page | Active Jobs list omits VMAF runs while badge counts them; operator kills workers thinking they are hung, orphaning claimed rows | 2026-06-03 -> 2026-06-03
- BUG-0032 | resolved | file-replacement | Stale .orig recovery for at-risk files | 2026-05-14 -> 2026-06-02
- BUG-0041 | resolved | sql-queries | QueryDatabase.py truncates long text columns at 60 chars | 2026-05-13 -> 2026-06-02
- BUG-0012 | resolved | show-settings | Quick Fix batch rows blank Title for UNC paths | 2026-05-22 -> 2026-06-02
- BUG-0006 | resolved | transcode-queue | Quick/AudioFix routed to Transcode capability poller | 2026-05-18 -> 2026-06-02
- BUG-0005 | resolved | transcode-queue | FFmpeg muxer auto-detect fails on .mp4.inprogress | 2026-05-18 -> 2026-06-02
- BUG-0003 | resolved | audio-completion | Remux profile re-encodes audio | 2026-05-16 -> 2026-06-02
- BUG-0004 | resolved | worker-lifecycle | Workers.Status=Paused does not gate capability claiming | 2026-05-18 -> 2026-06-02
- BUG-0011 | resolved | jellyfin-notify | JellyfinNotify HTTP 500, WARNING does not log payload | 2026-05-22 -> 2026-06-02
