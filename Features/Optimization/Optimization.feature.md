# Jellyfin Optimization

**Slug:** optimization

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

## Cross-Vertical Contract

### Columns the Optimization vertical WRITES

| Column | Written by |
|---|---|
| JellyfinOperations.* | SSH log import |

### Columns READS

| Column | Read by | Owner |
|---|---|---|
| JellyfinOperations.* | Page rendering | self |
| MediaFiles.{Id, FilePath, Codec, Resolution} | Recommendation matching | FileScanning + MediaProbe |
| SystemSettings.{Jellyfin*} | Connection config | SystemSettings |

### Stable function entry points

| Class.method | External caller(s) |
|---|---|
| JellyfinRepository.SSHImportLogs() -> ImportSummary | /Optimization page sync button |
| OptimizationService.RecommendPreTranscodes() -> List[Recommendation] | UI |

### HTTP API surface

| Method + URL | Purpose |
|---|---|
| GET /Optimization | Render the page |
| POST /api/Optimization/SyncJellyfin | Trigger SSH log import |
| POST /api/Optimization/TestConnection | Validate SSH connection |
| GET /api/Optimization/Recommendations | Per-device recommendations |

### What is EXPLICITLY NOT a contract

- Internal log-parsing regex -- Jellyfin log format evolves
- Per-device transcode-reason categorization -- heuristic
- The SSH client library (paramiko) -- swappable
