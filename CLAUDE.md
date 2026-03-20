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

**MVVM pattern** with feature-based modules:

```
Templates (View) → Controller → ViewModel → BusinessService → Repository → DatabaseService
```

Each feature in `Features/` contains its own Controller, ViewModel, BusinessService, Repository, and Models. Legacy code in top-level `Controllers/`, `ViewModels/`, `Services/`, `Models/` directories is being migrated into `Features/`.

**Three microservices** run as separate processes, coordinated via database records:
- **WebService** - Flask web app (API + UI)
- **TranscodeService** - Executes FFmpeg transcode jobs
- **QualityTestService** - Runs quality analysis on transcoded files

`ServiceLifecycleManager` orchestrates startup/shutdown of all three.

## Database

- **PostgreSQL 16** running locally (not Docker)
- Connection: `localhost:5432`, database/user/password: `mediavortex`
- Config in `Core/Database/DatabaseService.py` (env vars: `MEDIAVORTEX_DB_HOST`, `MEDIAVORTEX_DB_PORT`, `MEDIAVORTEX_DB_NAME`, `MEDIAVORTEX_DB_USER`, `MEDIAVORTEX_DB_PASSWORD`)
- Uses `psycopg2` with `RealDictCursor` returning lowercase keys
- `CaseInsensitiveDict` maps lowercase PostgreSQL keys to PascalCase for JSON responses
- **Known typo**: column `transcodeattempts.ffpmpegcommand` (double 'p') — code must match this

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

**File scanning data flow**: MediaFiles table is display-only. All transcoding settings come from `ProfileThresholds` based on the assigned profile. MediaFiles resolution/codec fields are NOT used for transcoding decisions.

**Database operations**:
- `DatabaseService.ExecuteQuery()` for SELECT
- `DatabaseService.ExecuteNonQuery()` for INSERT/UPDATE/DELETE

## Web Routes

Pages: `/` (Home), `/Scanning`, `/TranscodeQueue`, `/Activity`, `/Status`, `/SQLQueries`, `/TranscodeProgress`, `/Optimization`, `/settings`

API endpoints are registered via Flask Blueprints in each feature's Controller.

## Frontend

Bootstrap 5 + jQuery + Chart.js, served via Jinja2 templates in `Templates/`.
