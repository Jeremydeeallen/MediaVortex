# XXX library: Stash LXC, profile-row lookup, video tier, policy-authoritative audio, cull

**Date:** 2026-10-28, revised 2026-11-25
**Status:** Approved design (operator, 2026-11-25). Phases in `Docs/superpowers/plans/2026-10-29-xxx-program.md`.

## Goal

Three operator outcomes for the xxx library (`StorageRoots.Id = 3`, canonical `Z:\`, Porky export `10.0.0.43:/srv/nfs-media-xxx_videos`):

1. 4K videos are re-encoded to AV1 at about 8 Mbps (1080p at about 3 Mbps). 1,772 xxx files are 4K; 1,514 of them run 12 Mbps or more and shrink from about 9.0 TB to about 3.1 TB.
2. Audio is one normalized track per kept language at -26 LUFS, 3 LU below the house standard (-23), so switching from shows to xxx is a little quieter. No Dialog Boost track, so no Demucs and no speech-language work for xxx. Source loudness today spans -70 to +10 LUFS.
3. Low-quality videos and videos featuring performers the operator does not want are identified and deleted with one confirmed action.

Five units, built in this order: Unit 1 Stash LXC (infra, done 2026-10-29 except performer rating), Unit 0 `profile-row-lookup` (MediaVortex prerequisite for the shows and for xxx video), Unit 2 `xxx-video-tier`, Unit 3 `xxx-audio-rule`, Unit 4 `xxx-cull`. Each MediaVortex unit is one directive.

## Unit 1: Stash LXC (infrastructure, no MediaVortex code)

| Item | Decision |
|---|---|
| Host | Porky (Proxmox, 10.0.0.43). The xxx dataset is Porky-local ZFS `tank/media/xxx_videos`; Larry only sees it over backplane NFS. |
| Container | Unprivileged Ubuntu 24.04 LXC (repo template), VMID 233, 10.0.0.45, 4 vCPU, 8 GB RAM, 64 GB on `local-zfs` |
| Media | Bind mount Porky `/tank/media/xxx_videos` to CT `/mnt/xxx` with `ro=1`. Stash never writes media. |
| Stash | Native Linux binary from the Stash release page, plus ffmpeg/ffprobe, as a systemd unit on port 9999. Data dir on CT disk. |
| Scrapers | ThePornDB (free API key) as a stash-box endpoint. StashDB is invite-only and optional; added if an invite arrives. |
| Tasks | Scan library (oshash fingerprints), run Identify against ThePornDB with performers/studios/tags created when missing. Phash generation is deferred: oshash matched most scenes without it. |
| Manual effort | Operator rates performers 1 to 5 stars in the Stash UI. Rating performers, not files, is the only manual step. |

Reddit clips (1,296 files under random-word names, under 2 minutes) will mostly stay unidentified. They are handled by the quality floor in Unit 4, not by performer rating.

Verification: Stash UI reachable from I9, every readable, non-duplicate xxx file under `/mnt/xxx/Videos` is a scene, Identify has attached performers to at least 1,500 scenes.

## Unit 0: `profile-row-lookup` directive (shared prerequisite)

Problem found 2026-11-25. Five pieces of code answer "which `ProfileThresholds` row applies to this file", and three disagree:

| Lookup | Used by | Defect |
|---|---|---|
| `ProfileRepository.GetProfileMaxTarget` | queue admission | compares the source to the profile's highest target across all rows (2160p on tiered profiles), so every sub-4K file is refused as "Upscale". No transcode since 2026-10-20 (BUG-0120). |
| `ProfileRepository.GetProfileSettingsForTargetResolution` | queue admission | profile + resolution only; class ignored |
| `ProfileRepository.GetProfileQualityForTargetResolution` | nobody | dead |
| `EncoderKnobRepository._ResolveTargetResolution` + `GetEncoderKnobsForProfile` | encode command | profile + resolution `LIMIT 1`; a 1080p source gets the live_action row (720p) or the animation row (1080p) by chance (BUG-0121) |
| `EffectiveProfileResolver._LookupThresholdsRow` | estimates, QT, compliance summary | same `LIMIT 1` |
| `TierLadderRepository.GetProfileTarget` / `GetTierEncodeKbps` | compliance | class-aware, but fed `getattr(Mf, 'ContentClass', None) or 'live_action'`; `MediaFiles` has no such column |

Design:

- One lookup: `TierLadderRepository.GetProfileRow(ProfileName, ContentClass, Resolution)` returns the joined `Profiles` + `ProfileThresholds` row. Admission, `EncoderKnobRepository`, `EffectiveProfileResolver` and `VideoVertical` all read it. The four duplicates are deleted; the two tier methods are implemented over it.
- Admission's upscale test is `source < row.TranscodeDownTo` for that file's own row.
- Content class is resolved at read, the way `FileTierResolver` resolves the tier: `ContentClassResolver.Resolve(StorageRootId, MediaFileId)` returns the class of the first genre in `MediaFiles.Genres` that has one in `GenreQualityTiers.ContentClass`, else `StorageRoots.DefaultContentClass`, else `None`. `None` is reported as `missing_input:ContentClass`; no code supplies a class. Both columns are new, nullable, CHECK `('live_action','animation')`, seeded `live_action` for the three roots and `animation` for the `Animation` genre.
- Knobs on `/settings`: "Default content class" per library in the library table; optional class per genre in the genre table. Saving either re-evaluates the library (existing `_SpawnLibraryRecompute`).
- Hook hygiene: `Get-SessionState` ignores the stale `.session-state.json` when the directive file is the template, so edits after a close are refused as "No active directive" rather than with the closed directive's phase.

Acceptance: one fixture yields the same row in admission, command, estimate and compliance reason; `AddJob` admits a 720p and a 1080p TV file without `ForceAdd`; the four lookups return 0 grep hits; TV/Movies compliance counts change only for files whose class moved from implicit live_action to animation (count reported); one TV 1080p file transcodes to 720p live on a worker.

Out of scope: Sonarr genre sync (TV has no genres, so TV class is the library default), tier ladder values, `ReassignTierProfiles` behaviour (Unit 2).

## Unit 2: `xxx-video-tier` directive

Tier 3 Better's live-action ladder is already the xxx video rule: 480p -> 480p @ 650 kbps, 720p -> 720p @ 1700, 1080p -> 1080p @ 3000, 2160p -> 2160p @ 8000 (`TargetKbps`; `VideoBitrateKbps` 8500). No new profile.

Operator steps (GUI, `/settings`): set the xxx library's default tier to 3 with "replace per-file and per-series overrides" ticked; delete classifier rule `XxxPinTier2Good` (a tiered library's path is never named by a rule, `classifier.feature.md` C9).

Code, two defects in that path:

- `ContentClassifierService.ReassignTierProfiles` only acts when the library has a `GenreSource`, so TV and xxx never reassign on a tier change although the GUI says they do. It acts for any library with a default tier.
- 2,757 xxx files carry `AssignedProfileSource` `operator` or `series` (Tier 1 Efficient, whose 4K row goes to 720p @ 900) from the old plan. Overrides are preserved by design (TV uses series overrides). The library-tier save gains a "replace per-file and per-series overrides" checkbox; when ticked the reassign includes them. Default off.

Behaviour at the gate: files under about 10 Mbps (153, about 270 GB) are skipped by the existing marginal-savings gate (`/settings`: 20% / 150 MB) and stay as they are; 10-12 Mbps files (105) save about 27% and are queued. No source-bitrate knob is added for the 153. HDR is not a concern: 7 xxx 4K files are 10-bit and none carries an HDR transfer tag.

Acceptance: `SELECT COUNT(*) FROM MediaFiles WHERE StorageRootId=3 AND AssignedProfile<>'AV1 Tier 3 Better'` is 0 after the save; one xxx 4K file at 12 Mbps or more transcodes to 2160p AV1 at about 8 Mbps on a worker and passes VMAF; a 7 Mbps xxx 4K file is not queued (reason `MarginalSavings`); TV and Movies profile assignments are unchanged.

## Unit 3: `xxx-audio-rule` directive

Root cause, confirmed 2026-11-25. Two sources of truth:

- `AudioNormalizationConfig` (per-scope policy, `/AudioNormalization` Settings): `EmitTracks` with Label, Codec, Bitrate, TargetLufs, TargetLra, Channels, LanguageFilter, IsDefaultTrack. Read by admission (`AudioPolicyAdmissionGate`) and the strategy classifier only.
- `AudioComplianceRules` (one global row, `/Admin/Compliance` + `/AudioNormalization` knob panels): `TargetIntegratedLufs -23`, `DialogBoostTargetLufs -14`, `DialogBoostTargetLra 9`, Track0/Track1 codec (opus) and bitrates, true peak, headroom, Demucs premix knobs. Read by `AudioFilterEmitter`, `PreEncodeAudioPipeline` and `AudioVertical`.

`AudioFilterEmitter.EmitTracks(MediaFile, Policy, ...)` uses the policy for `LanguageDefault` and `EnableSpeechLanguageDetection` only. Every track's target, codec and bitrate come from the rules row; Dialog Boost is emitted whenever a Demucs premix exists, and the Demucs pre-encode runs for every AudioFix. Compliance (`AudioVertical.Evaluate`) is `HasDialogBoostTrack IS TRUE`, else `no_dialog_boost`. A -26 xxx policy row would change admission only; the encode would still be -23 opus with a Dialog Boost track, and the file would loop through AudioFix forever.

Design: the policy says WHAT, the rules say HOW.

- `AudioNormalizationConfig.EmitTracks` is the only source for which tracks exist and, per track, Label, TargetLufs, TargetLra, Codec, Bitrate, Channels, LanguageFilter, IsDefaultTrack.
- `AudioComplianceRules` keeps engine constants only: `TargetTruePeakDbtp`, `SampleLimitHeadroomDb`, `AcceptableAudioCodecsCsv`, `Track1VocalsRmsFallbackDbfs`, `VocalsBoostDb`, `InstrumentalAttenDb`, the premix compressor and dynaudnorm knobs. `TargetIntegratedLufs`, `DialogBoostTargetLufs`, `DialogBoostTargetLra`, `Track0Codec`, `Track1Codec`, `Track0BitratePerChannelKbps`, `Track0MinPerChannelKbps`, `Track1StereoBitrateKbps` are dropped from the table, the repository and both GUI panels.
- Step order protects TV. (1) Migration copies the live rules values into the global policy row's tracks (Original: opus, 48 kbps per channel, -23; Dialog Boost: opus, 64 kbps, -14 / LRA 9) so the policy describes what runs today. (2) Golden contract test records a TV fixture's ffmpeg audio args. (3) Emitter iterates `Policy.EmitTracks`: `Original` -> one linear-loudnorm block per kept source stream at `track.TargetLufs`; `Dialog Boost` -> the Demucs block at its `TargetLufs`/`TargetLra`; `IsDefaultTrack` sets disposition. Golden test must still pass byte-for-byte. (4) `PreEncodeAudioPipeline` runs the Demucs chain only when the resolved policy has a `Dialog Boost` track. (5) `AudioStrategyClassifier` drops its `or -23.0` / `or -2.0` / `or 3.0` defaults; a missing value is a `missing_input` reason.
- Compliance: a file is audio-compliant when the latest successful attempt's `AudioTracksEmittedJson` labels equal the resolved policy's `EmitTracks` labels per kept language and each track's achieved integrated loudness is within `LoudnessTolerance` of its `TargetLufs`. `no_dialog_boost` is deleted; `HasDialogBoostTrack` stays as data. Before/after `AudioCompliant` counts for TV and Movies must be identical; any flip is fixed before shipping, never tolerated.
- Docs rewritten to "tracks match policy": `transcode.flow.md` D2, D6, D7 and the AudioFix verification row; `audio-normalization.feature.md` C1, C43.
- Operator (GUI): library policy row ScopeKey 3 on `/AudioNormalization`: one `Original` track, aac, 128 kbps, TargetLufs -26, TargetLra null, default. Then Review tab bulk re-measure for the deferred xxx rows (559 `ungainable_all_streams`, 257 `operator_review_pending`); the 262 `invalid_loudness_measurement` rows drain through the server's remeasurement runner.

Acceptance: TV golden audio args unchanged; TV and Movies `AudioCompliant` counts unchanged; one live TV AudioFix on a worker yields two tracks at the same codecs and loudness as before; one xxx file through AudioFix yields one aac stream at -26 within tolerance, is compliant, and the worker log shows no Demucs step; `grep -rn no_dialog_boost --include=*.py .` returns 0; 0 xxx files with reason `no_dialog_boost`.

## Unit 4: `xxx-cull` directive

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
- Changing Movies or TV audio policy values, video tiers or ladder values. Movies and TV are verified unchanged, not changed.
- Sonarr genre sync for TV (animated shows get live-action rows until it exists).
- A source-bitrate knob on profile rows (the 153 sub-10 Mbps xxx 4K files stay as they are).
- Automatic deletion without an operator confirm.
