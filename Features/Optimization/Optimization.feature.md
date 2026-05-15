# Jellyfin Optimization

## What It Does

Analyzes Jellyfin FFmpeg logs to identify playback optimization opportunities. Shows which files cause server-side transcoding and recommends pre-transcoding to reduce Jellyfin server load.

## Success Criteria

1. SSH connection to the Jellyfin server imports FFmpeg log entries into JellyfinOperations.
2. Operations are categorized as DirectStream, Transcode, or Remux.
3. Transcode reason analysis identifies why Jellyfin transcoded (codec incompatibility, subtitle burn-in, resolution, etc.).
4. Device analysis shows which client devices trigger the most server-side transcoding.
5. The /Optimization page displays operation statistics and per-device breakdowns.
6. SSH connection can be tested from the UI before importing logs.
7. Recommendations identify files that should be pre-transcoded to eliminate server-side transcoding.
8. The Jellyfin sync form on /Optimization completes a sync round-trip without surfacing a "paramiko is not installed" error. The WebService runtime has `paramiko` available, and any missing-dependency condition is reported through the standard `{Success: false, Message}` envelope rather than raising a raw ImportError into the user-visible response.

## Status

COMPLETE

## Scope

```
Features/Optimization/**
```

## Files

| File | Role |
|------|------|
| Features/Optimization/OptimizationController.py | Flask Blueprint -- optimization endpoints |
| Features/Optimization/OptimizationBusinessService.py | Log analysis, categorization, recommendations |
| Features/Optimization/OptimizationRepository.py | JellyfinOperations database queries |
| Templates/Optimization.html | Optimization UI page |
