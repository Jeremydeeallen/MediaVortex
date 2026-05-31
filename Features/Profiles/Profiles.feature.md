# Profile Management

## What It Does

Defines transcode encoding profiles with per-resolution thresholds. Each profile specifies codec, preset, quality settings, and resolution-specific CRF/bitrate targets. Users assign profiles to folders to control how files are transcoded.

## Success Criteria

1. Profiles can be created (via SQL/migration), read, updated, and deleted via the /settings page.
2. Each profile defines: codec (`libsvtav1` or `av1_nvenc`), preset, film grain, and the full set of encoder knobs (tune, multipass, pixel format, audio, deinterlace, NVENC gate, rate-control mode).
3. Each profile has 4 resolution thresholds (480p, 720p, 1080p, 2160p), each with quality, bitrate limits, TranscodeDownTo target, and per-resolution encoder knobs (rcLookahead, bFrames, bRefMode, Gop, scale, etc.).
4. Profiles are assigned per-folder by the user. AssignedProfile on MediaFiles stores the profile name string.
5. ProfileThresholds.TranscodeDownTo determines the target resolution for files at each source resolution tier.
6. Deleting a profile that is assigned to folders warns the user or is blocked.
7. Profile changes do not retroactively affect already-queued or already-transcoded files.
8. There is exactly ONE editor for the Profile + ProfileThresholds conceptual unit: the cogs modal (`ShowProfileKnobs`). Verifiable: `grep -n 'id="ProfileManagementModal"' Templates/Settings.html` returns 0 matches.

## Status

COMPLETE

## Scope

```
Features/Profiles/**
```

## Files

| File | Role |
|------|------|
| `Features/Profiles/ProfileController.py` | Flask Blueprint -- profile CRUD + PATCH /knobs endpoint |
| `Features/Profiles/ProfileService.py` | Profile and threshold business logic |
| `Features/Profiles/ProfileRepository.py` | Profiles and ProfileThresholds database queries |
| `Features/Profiles/ProfileManagementViewModel.py` | Profile serialization for the settings UI (GET /api/profiles) |
| `Features/Profiles/EncoderKnobRepository.py` | Single read path: `GetEncoderKnobsForProfile` for CommandBuilder |
| `Templates/Settings.html` | Profile management section of settings page (cogs modal is the canonical editor) |

## Seams

| Seam | Producer | Wire shape | Consumer expects | Verification |
|---|---|---|---|---|
| UI → PATCH /api/profiles/<id>/knobs | `Settings.html` `ShowProfileKnobs` JS (`ReadField` coercions) | JSON `{Profile: {col: val}, Thresholds: [{Id, col: val}]}`. `bool_int` fields (UseNvidiaHardware): `parseInt` → int 0/1; `bool` fields: JS boolean; `int`: `parseInt`; `float`: `parseFloat` | `ProfileController.patch_profile_knobs` filters keys through `PROFILE_COLS`/`THRESHOLD_COLS` allowlist; unknown keys silently dropped | PATCH all 20 Profile + 20 Threshold fields; verify non-allowlisted fields absent in DB |
| PATCH → PostgreSQL UPDATE | `ProfileController.patch_profile_knobs` -- column names from allowlist, parameterized values | `UPDATE Profiles SET col=%s WHERE Id=%s` / `UPDATE ProfileThresholds SET col=%s WHERE Id=%s AND ProfileId=%s` | PostgreSQL `Profiles` (`usenvidiahardware BIGINT`, `preset BIGINT`, `faststart BOOLEAN`) + `ProfileThresholds` (`preserveaspect BOOLEAN`, `maxbitratemultiplier NUMERIC`) | Post-PATCH `SELECT` confirms values round-trip correctly (esp. bool_int → bigint) |
| AssignedProfile → TranscodeQueue | Folder-assignment UI writes `MediaFiles.AssignedProfile TEXT` (profile name string) | `MediaFiles.AssignedProfile TEXT` matched by string equality to `Profiles.ProfileName` | `TranscodeQueue` JOINs `Profiles ON ProfileName = AssignedProfile` to find profile settings | `SELECT mf.AssignedProfile FROM MediaFiles mf LEFT JOIN Profiles p ON p.ProfileName = mf.AssignedProfile WHERE mf.AssignedProfile IS NOT NULL AND p.Id IS NULL` → 0 rows |
| Profiles + ProfileThresholds → CommandBuilder | `EncoderKnobRepository.GetEncoderKnobsForProfile(ProfileName, SourceResolution)` JOIN on name + resolution tier | `EncoderKnobs` dataclass `.ToDict()` dict; `ProcessTranscodeQueueService.GetTranscodingSettings` injects `SourceVideoBitrateKbps` from `MediaFile.VideoBitrateKbps` | `CommandBuilder` reads `ProfileSettings` dict keys directly | Smoke: `py /tmp/smoke_legacy.py` (SVT); `py /tmp/smoke_canary.py` (NVENC VBR) |
| ProfileThresholds.TranscodeDownTo → queue filter | `ProfileThresholds.transcodedownto TEXT NOT NULL` (values: '480p', '720p', '1080p', '2160p', 'No downscaling') | String resolved by `ResolutionService.CompareResolutions` | `TranscodeQueue.PopulateQueue` filters source resolutions eligible for queuing per profile assignment | `SELECT * FROM ProfileThresholds WHERE transcodedownto NOT IN ('480p','720p','1080p','2160p','No downscaling')` → 0 rows |
