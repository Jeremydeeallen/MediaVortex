# Profile Management

## What It Does

Defines transcode encoding profiles with per-resolution thresholds. Each profile specifies codec, preset, quality settings, and resolution-specific CRF/bitrate targets. Users assign profiles to folders to control how files are transcoded.

## Success Criteria

1. Profiles can be created, read, updated, deleted, and copied via the /settings page.
2. Each profile defines: codec (libsvtav1), preset (speed vs quality), and film grain preservation level.
3. Each profile has 4 resolution thresholds (480p, 720p, 1080p, 2160p), each with CRF, bitrate limit, and TranscodeDownTo target.
4. Profiles are assigned per-folder by the user. AssignedProfile on MediaFiles stores the profile name string.
5. ProfileThresholds.TranscodeDownTo determines the target resolution for files at each source resolution tier.
6. Deleting a profile that is assigned to folders warns the user or is blocked.
7. Profile changes do not retroactively affect already-queued or already-transcoded files.

## Status

COMPLETE

## Scope

```
Features/Profiles/**
```

## Files

| File | Role |
|------|------|
| Features/Profiles/ProfilesController.py | Flask Blueprint -- profile CRUD endpoints |
| Features/Profiles/ProfilesBusinessService.py | Profile and threshold business logic |
| Features/Profiles/ProfilesRepository.py | Profiles and ProfileThresholds database queries |
| Templates/Settings.html | Profile management section of settings page |
