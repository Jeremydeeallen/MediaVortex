# Bug Index

Terse one-line-per-bug index. Drill into `memory/KNOWN-ISSUES.md` for full detail.
Entry shape: `- BUG-NNNN | <active|resolved> | <area> | <desc> | <created>[ -> <resolved>]`

## Active

- BUG-0002 | active | file-replacement | Silent-output Remux MediaFiles purge | 2026-05-16
- BUG-0007 | active | activity-page | Worker capability toggle no UI refresh | 2026-05-22
- BUG-0020 | active | worker-lifecycle | Workers must own processes end-to-end; -mv only when compliant | 2026-05-26

## Recently Resolved (last 10)

- BUG-0012 | resolved | show-settings | Quick Fix batch rows blank Title for UNC paths | 2026-05-22 -> 2026-06-02
- BUG-0006 | resolved | transcode-queue | Quick/AudioFix routed to Transcode capability poller | 2026-05-18 -> 2026-06-02
- BUG-0005 | resolved | transcode-queue | FFmpeg muxer auto-detect fails on .mp4.inprogress | 2026-05-18 -> 2026-06-02
- BUG-0003 | resolved | audio-completion | Remux profile re-encodes audio | 2026-05-16 -> 2026-06-02
- BUG-0004 | resolved | worker-lifecycle | Workers.Status=Paused does not gate capability claiming | 2026-05-18 -> 2026-06-02
- BUG-0011 | resolved | jellyfin-notify | JellyfinNotify HTTP 500, WARNING does not log payload | 2026-05-22 -> 2026-06-02
- BUG-0018 | resolved | orphan-cleanup | OrphanCleanupService races FileReplacement during VMAF window (rolled into BUG-0020) | 2026-05-25 -> 2026-06-02
- BUG-0015 | resolved | file-replacement | Orphan -mv.mp4 disk files without MediaFiles row (rolled into BUG-0020) | 2026-05-24 -> 2026-06-02
- BUG-0010 | resolved | file-replacement | TemporaryFilePaths cleanup only on success branch (rolled into BUG-0020) | 2026-05-22 -> 2026-06-02
- BUG-0009 | resolved | file-replacement | FileReplacement Success=false orphans TFP rows (rolled into BUG-0020) | 2026-05-22 -> 2026-06-02
