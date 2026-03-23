# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

MediaVortex is a media transcoding and management system built with Python/Flask. It scans media files, assigns transcode profiles, queues and executes FFmpeg transcoding jobs, and integrates with Jellyfin for playback optimization.

## Commands

```bash
# Start all services (web, transcode, quality test)
py StartMediaVortex.py

# Stop all services
py StopMediaVortex.py

# Start only the web service (Flask on port 5000)
py WebService/Main.py

# Run tests
py -m pytest Tests/Contract/
py -m pytest Tests/Contract/TestQueueGet.py   # single test

# Query the database (use this instead of psql)
py Scripts/SQLScripts/QueryDatabase.py tables
py Scripts/SQLScripts/QueryDatabase.py schema <table>
py Scripts/SQLScripts/QueryDatabase.py <table> --where "..." --columns "..." --limit N
py Scripts/SQLScripts/QueryDatabase.py sql "SELECT ..."
```

## Architecture

**MVVM pattern** with feature-based verticals:

```
Templates (View) → Controller → ViewModel → BusinessService → Repository → DatabaseService
```

### Feature Verticals (in `Features/`)
Each feature contains its own Controller, ViewModel, BusinessService, Repository, and Models:

| Feature | Purpose |
|---------|---------|
| **FileScanning** | Discovers media files on disk, inserts into MediaFiles table |
| **MediaProbe** | Runs FFprobe on files, extracts/persists metadata (resolution, codec, audio languages) |
| **Profiles** | Manages transcode profiles and per-resolution thresholds |
| **TranscodeQueue** | Queue population: assigns profiles to folders, filters by resolution, creates queue items |
| **TranscodeJob** | Executes FFmpeg transcode jobs, tracks progress |
| **QualityTesting** | VMAF quality analysis on transcoded files |
| **FileReplacement** | Replaces original with transcoded file, re-probes metadata, archives original data |
| **Activity** | Activity/history dashboard |
| **FailureTracking** | Problem file tracking |
| **Optimization** | System optimization settings |
| **ServiceControl** | Start/stop microservices |
| **SQLQueries** | Ad-hoc DB query interface |
| **SystemSettings** | App configuration |

Legacy code in top-level `Controllers/`, `ViewModels/`, `Services/`, `Models/` is being migrated into `Features/`.

### Three Microservices
Separate processes coordinated via database records:
- **WebService** — Flask web app (API + UI), port 5000
- **TranscodeService** — Executes FFmpeg transcode jobs
- **QualityTestService** — Runs VMAF quality analysis

`ServiceLifecycleManager` orchestrates startup/shutdown of all three.

## Core Data Flow

```
1. SCAN:  FileScanning discovers files → inserts into MediaFiles
2. PROBE: MediaProbe runs FFprobe → populates Resolution, Codec, AudioLanguages, etc.
3. ASSIGN: User selects folder + profile in UI → bulk-updates MediaFiles.AssignedProfile
4. QUEUE: PopulateQueue filters by resolution vs ProfileThresholds.TranscodeDownTo → creates TranscodeQueue items
5. TRANSCODE: TranscodeService picks up queue items → runs FFmpeg → writes TranscodeAttempts
6. QUALITY: QualityTestService runs VMAF → updates TranscodeAttempts.VMAF
7. REPLACE: FileReplacement archives original → moves transcoded to original location → re-probes → updates MediaFiles
```

### Safety Guards
- **Audio language check**: Files without explicit English audio (`HasExplicitEnglishAudio = false`) are blocked from queue population. Files with NULL (not yet probed) are allowed through.
- **FFprobe failure limit**: Files that fail FFprobe 3+ times are skipped on subsequent scans.
- **VMAF threshold**: Files with VMAF ≥ 80 are not re-transcoded. Files with VMAF < 80 get CRF adjustment.
- **CRF floor**: Adjusted CRF cannot go below 15 — files that would need lower are logged as ProblemFiles.

## Database

- **PostgreSQL 16** running locally (not Docker)
- Connection: `localhost:5432`, database/user/password: `mediavortex`
- Config in `Core/Database/DatabaseService.py` (env vars: `MEDIAVORTEX_DB_HOST`, `MEDIAVORTEX_DB_PORT`, `MEDIAVORTEX_DB_NAME`, `MEDIAVORTEX_DB_USER`, `MEDIAVORTEX_DB_PASSWORD`)
- Uses `psycopg2` with `RealDictCursor` returning lowercase keys
- `CaseInsensitiveDict` maps lowercase PostgreSQL keys to PascalCase for JSON responses
- **Known typo**: column `transcodeattempts.ffpmpegcommand` (double 'p') — code must match this
- **LIKE queries use `ESCAPE '!'`** — any path value used in LIKE must be escaped with `EscapeLikePattern()` from `Core.Database.DatabaseService` to handle `!`, `%`, `_` in folder names

### Key Tables
| Table | Purpose |
|-------|---------|
| **MediaFiles** | Current state of every media file (resolution, codec, audio, profile assignment) |
| **RootFolders** | Registered scan directories |
| **Profiles** | Transcode profile definitions (codec: libsvtav1, preset, film grain) |
| **ProfileThresholds** | Per-resolution settings for each profile (CRF, bitrate, TranscodeDownTo) |
| **TranscodeQueue** | Pending transcode jobs |
| **TranscodeAttempts** | Record of each transcode execution (size, duration, VMAF, FFmpeg command) |
| **TranscodeFiles** | Overall file transcode status (successful, total attempts) |
| **MediaFilesArchive** | Snapshot of original file metadata before transcode replacement |

### Profile → Threshold System
- `Profiles` table: 12 profiles (all libsvtav1, presets 6-8, various grain levels)
- `ProfileThresholds`: 4 entries per profile (480p, 720p, 1080p, 2160p), each with CRF, bitrate, TranscodeDownTo
- Profile is assigned per-folder by user (not auto-assigned)
- `AssignedProfile` on MediaFiles stores the **profile name string**, not an ID

## Naming Conventions (CRITICAL)

**PascalCase for everything**: variables, functions, classes, files, database tables/columns, routes, URLs.

```python
# Correct
RootFolderPath = "/media"
def GetTranscodeQueue():
class FileScanningBusinessService:

# Wrong
rootFolderPath = "/media"
def get_transcode_queue():
```

Exceptions: Python built-ins (`__init__`, `str()`, `len()`).

## Key Patterns

**API response format:**
```python
return jsonify({'Success': True/False, 'Message': '...', 'Data': {...}}), 200
```

**Logging** via `Core.Logging.LoggingService`:
```python
LoggingService.LogInfo("message", "ClassName", "MethodName")
LoggingService.LogException("message", exception, "ClassName", "MethodName")
```

**Database operations** (in `Core/Database/DatabaseService.py`):
- `DatabaseService.ExecuteQuery()` for SELECT (returns list of `CaseInsensitiveDict`)
- `DatabaseService.ExecuteNonQuery()` for INSERT/UPDATE/DELETE (auto-commits)
- `EscapeLikePattern(value)` — MUST use for any value in a LIKE clause with `ESCAPE '!'`

**Resolution handling**:
- Raw `Resolution` field (e.g. "1920x1080") is the canonical source — used for all transcode decisions
- `ResolutionCategory` (e.g. "1080p") is a cached display field derived from Resolution height
- `ResolutionService.CompareResolutions()` normalizes pixel dimensions to standard tiers for comparison
- `ProfileThresholds.Resolution` stores category labels ("480p", "720p", "1080p", "2160p")

**Post-transcode data flow**:
- Original metadata archived to `MediaFilesArchive` before replacement
- After file replacement, `_UpdateMediaFilesAfterReplacement()` re-probes the new file and updates ALL MediaFiles columns
- `TranscodedByMediaVortex = True` marks successfully transcoded files

## Web Routes

Pages: `/` (Home), `/Scanning`, `/TranscodeQueue`, `/Activity`, `/Status`, `/SQLQueries`, `/TranscodeProgress`, `/Optimization`, `/settings`

API endpoints are registered via Flask Blueprints in each feature's Controller.

## Frontend

Bootstrap 5 + jQuery + Chart.js, served via Jinja2 templates in `Templates/`.
