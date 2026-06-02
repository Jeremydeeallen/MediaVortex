# Bug Index

Terse one-line-per-bug index. Drill into `memory/KNOWN-ISSUES.md` for full detail.
Entry shape: `- BUG-NNNN | <active|resolved> | <area> | <desc> | <created>[ -> <resolved>]`

## Active

- BUG-0002 | active | file-replacement | Silent-output Remux MediaFiles purge | 2026-05-16
- BUG-0003 | active | audio-completion | Remux profile re-encodes audio (PENDING OPERATOR VERIFICATION) | 2026-05-16
- BUG-0004 | active | worker-lifecycle | Workers.Status='Paused' does not gate capability claiming | 2026-05-18
- BUG-0005 | active | transcode-queue | FFmpeg muxer auto-detect fails on .mp4.inprogress | 2026-05-18
- BUG-0006 | active | transcode-queue | Quick/AudioFix routed to Transcode capability poller | 2026-05-18
- BUG-0007 | active | activity-page | Worker capability toggle no UI refresh | 2026-05-22
- BUG-0009 | active | file-replacement | FileReplacement Success=false orphans TFP rows | 2026-05-22
- BUG-0010 | active | file-replacement | TemporaryFilePaths cleanup only on success branch | 2026-05-22
- BUG-0011 | active | jellyfin-notify | JellyfinNotify HTTP 500, WARNING does not log payload | 2026-05-22
- BUG-0012 | active | show-settings | Quick Fix batch rows blank Title for UNC paths | 2026-05-22
- BUG-0015 | active | file-replacement | Orphan -mv.mp4 disk files without MediaFiles row | 2026-05-24
- BUG-0018 | active | orphan-cleanup | OrphanCleanupService races FileReplacement during VMAF window | 2026-05-25
- BUG-0020 | active | worker-lifecycle | Workers must own processes end-to-end; -mv only when compliant | 2026-05-26

## Recently Resolved (last 10)

- BUG-0016 | resolved | file-replacement | Orphan -mv.mp4 MediaFiles cause unique violations | 2026-05-24 -> 2026-06-02
- BUG-0023 | resolved | profiles | Legacy ProfileManagementModal corrupted NVENC Codec column | 2026-05-31 -> 2026-05-31
- BUG-0022 | resolved | quality-testing | VMAF measurement + NVENC adoption | 2026-05-28 -> 2026-05-29
- BUG-0021 | resolved | file-replacement | Codec/AudioCodec/AudioComplete stale on MediaFiles | 2026-05-27 -> 2026-05-27
- BUG-0019 | resolved | linear-loudnorm | AudioNormalizationMode NULL after loudnorm | 2026-05-25 -> 2026-05-27
- BUG-0014 | resolved | linear-loudnorm | Linear-loudnorm overshoots TargetTruePeak | 2026-05-24 -> 2026-05-26
- BUG-0017 | resolved | file-replacement | MediaFiles.FileSize NULL on most rows | 2026-05-24 -> 2026-05-25
- BUG-0013 | resolved | audio-completion | AudioComplete not flipped after loudnorm | 2026-05-23 -> 2026-05-23
- BUG-0008 | resolved | nfs-windows | I9 intermittent NFS write failures (EINVAL) | 2026-05-22 -> 2026-05-22
- BUG-0001 | resolved | orphan-cleanup | Stuck-item cleanup gaps across operational rows | 2026-05-16 -> 2026-05-17