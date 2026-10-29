# XXX library: Stash LXC, cull vertical, normalization-only audio

**Date:** 2026-10-28
**Status:** Approved design, not yet planned

## Goal

Two operator outcomes for the xxx library (`StorageRoots.Id = 3`, canonical `Z:\`, NFS `10.0.0.42:/mnt/xxx`):

1. Audio is normalized to one consistent level across files. No Dialog Boost track. Source loudness today spans -70 to +10 LUFS with per-folder standard deviation of 5 to 10 LU.
2. Low-quality videos and videos featuring performers the operator does not want are identified and deleted with one confirmed action.

Three independent units, built in this order: Stash LXC (infra), `xxx-audio-rule` (directive), `xxx-cull` (directive).

## Unit 1: Stash LXC (infrastructure, no MediaVortex code)

| Item | Decision |
|---|---|
| Host | larry (Proxmox, 10.0.0.42), beside Postgres CT 203 and workers CT 218 |
| Container | Unprivileged Debian 12 LXC, 2 vCPU, 4 GB RAM, 32 GB disk, static IP on 10.0.0.0/24 |
| Media | Bind mount larry `/mnt/xxx` to CT `/mnt/xxx`, read-only. Stash never writes media. |
| Stash | Native Linux binary from the Stash release page, plus ffmpeg/ffprobe, as a systemd unit on port 9999. Data dir on CT disk. |
| Scrapers | StashDB (free account, API key) and ThePornDB (free API key). Both configured as stash-box endpoints. |
| Tasks | Scan library, generate perceptual hashes, run Identify against both stash-boxes. Phash matching catches renamed files. |
| Manual effort | Operator rates performers 1 to 5 stars in the Stash UI. Rating performers, not files, is the only manual step. |

Reddit clips (1,296 files under random-word names, under 2 minutes) will mostly stay unidentified. They are handled by the quality floor in Unit 3, not by performer rating.

Verification: Stash UI reachable from I9, scene count equals the count of xxx files under `/mnt/xxx`, Identify has attached performers to at least the 1,642 scene-release files.

## Unit 2: `xxx-audio-rule` directive

Opens after `movies-video-rule` closes.

Root cause: `AudioVertical.Evaluate` (`Features/AudioNormalization/AudioVertical.py`) returns compliant only when `MediaFiles.HasDialogBoostTrack = TRUE`. A policy with no Dialog Boost track would leave every xxx file non-compliant forever and re-queue it to AudioFix without end.

Changes:

- Audio compliance is judged against the file's resolved policy (`AudioPolicyResolver.GetEffectivePolicy`): the tracks the latest successful attempt emitted match the policy's `EmitTracks` labels, and achieved loudness is within `LoudnessTolerance` of `TargetIntegratedLufs`. The Dialog Boost column stays as data; it stops being the compliance test.
- The admission-gate SQL in `AudioPolicyAdmissionGate` gains the `folder` scope so it matches the resolver's `item > folder > library > global` walk. Today the SQL skips `folder`.
- Operator adds a `library` row, ScopeKey `3`, on the `/AudioNormalization` Settings tab: `EmitTracks` = one `Original` track, aac, `TargetLufs` -23, `TargetLra` null, default track. No code for this step.
- Existing xxx files flip to the AudioFix bucket once, normalize, and become compliant under the new test.

Acceptance: 0 xxx files with reason `no_dialog_boost`; a normalized xxx file is compliant with exactly one audio stream per kept language; Movies and TV compliance snapshot unchanged (same before/after test shape as `movies-video-rule` criterion 9).

## Unit 3: `xxx-cull` directive

Opens once the operator has rated performers in Stash.

- New vertical `Features/Cull/`. Reads Stash GraphQL fresh per request (db-is-authority, no cache): scene file path, performers, performer rating. Joins to `MediaFiles` on `StorageRootId = 3` and `RelativePath`.
- Cull rules live in a DB table and are editable on `/settings` (gui-editable-knobs): performer rating at or below N drops; minimum height in pixels; minimum video kbps; minimum duration in minutes. A file matching any rule is a candidate. Each candidate carries its reason.
- `/Admin/Cull` page lists candidates with reason, performer names, and Stash thumbnail. Operator selects rows and presses one delete button. A confirm step precedes unlink.
- Delete runs through the existing file-removal path: unlink on disk via `Core.Path.LocalPath`, remove the `MediaFiles` row, notify Jellyfin. Stash is told nothing; its next scan drops the missing scene.
- Quality-floor rules work before Stash has any data, so the obvious low-quality set (480p, sub-2-minute clips, low bitrate) can go first.

Acceptance: every candidate shows exactly one or more rule reasons; deleting a selected set removes the file on disk and the DB row and triggers one Jellyfin notify; a file with no Stash match and above every quality floor is never a candidate.

## Out of scope

- Face recognition of any kind.
- Stash writing to media or to the MediaVortex database.
- Changing Movies or TV audio policy or compliance.
- Automatic deletion without an operator confirm.
