# MediaVortex

Media transcoding and management system. Scans media files, assigns transcode profiles, queues and executes FFmpeg transcoding jobs (AV1 via libsvtav1), and runs VMAF quality analysis. Supports distributed transcoding across multiple machines.

## Quick Start

Each service has its OWN virtual environment. There is no single shared venv --
`StartMediaVortex.py` launches each service with `<Service>/venv/Scripts/python.exe`.

```powershell
# Install dependencies (one venv per service)
py -m venv WebService\venv
WebService\venv\Scripts\python.exe -m pip install -r WebService\requirements.txt

py -m venv WorkerService\venv
WorkerService\venv\Scripts\python.exe -m pip install -r WorkerService\requirements.txt

# Set database connection (PostgreSQL)
# Default: localhost:5432, database/user/password: mediavortex
# Override with environment variables:
#   MEDIAVORTEX_DB_HOST, MEDIAVORTEX_DB_PORT, MEDIAVORTEX_DB_NAME,
#   MEDIAVORTEX_DB_USER, MEDIAVORTEX_DB_PASSWORD

# Start all services
py StartMediaVortex.py

# Stop all services
py StopMediaVortex.py
```

Web UI available at `http://localhost:5000`.

### Starting a single service

```powershell
# WebService only
& WebService\venv\Scripts\python.exe WebService\Main.py

# WorkerService only -- MEDIAVORTEX_WORKER_NAME is REQUIRED (fail-loud if unset)
$env:MEDIAVORTEX_WORKER_NAME = $env:COMPUTERNAME
& WorkerService\venv\Scripts\python.exe WorkerService\Main.py
```

The root `venv/` is for scripts and tests only. It does not carry the service
dependencies, so starting a service with it fails on import.

## Architecture

Two microservices coordinated via PostgreSQL:

| Service | Purpose |
|---------|---------|
| **WebService** | Flask web app (API + UI), port 5000 |
| **WorkerService** | Unified worker: transcoding, VMAF quality testing, and file scanning |

Workers read per-worker capability flags (TranscodeEnabled, QualityTestEnabled, ScanEnabled) and status (Online/Draining/Offline) from the Workers table. Workers can run on the same machine or be distributed across multiple hosts.

## Core Pipeline

```
SCAN -> PROBE -> ASSIGN -> QUEUE -> TRANSCODE -> QUALITY -> REPLACE
```

1. **Scan** -- discover media files on disk
2. **Probe** -- extract metadata via FFprobe (resolution, codec, audio languages)
3. **Assign** -- user picks a transcode profile per folder
4. **Queue** -- populate queue based on profile thresholds
5. **Transcode** -- FFmpeg encodes to AV1 (automatic, workers poll for jobs)
6. **Quality** -- VMAF analysis on output (automatic)
7. **Replace** -- swap original with transcoded file if VMAF >= 80 (automatic)

## Distributed Transcoding

MediaVortex supports multiple transcoding workers. Each worker connects directly to PostgreSQL and claims jobs atomically -- no central coordinator needed.

### Adding a Worker

1. Clone the repo on the new machine
2. Create the worker venv and install dependencies:
   `py -m venv WorkerService\venv` then
   `WorkerService\venv\Scripts\python.exe -m pip install -r WorkerService\requirements.txt`
3. Mount the media network share (same files the WebService scans)
4. Set `MEDIAVORTEX_DB_*` environment variables pointing to the shared database
5. Set `MEDIAVORTEX_WORKER_NAME` to this worker's assigned identity
6. Register the worker in the database (INSERT into Workers table)
7. Create the staging directory on the network share
8. Start: `& WorkerService\venv\Scripts\python.exe WorkerService\Main.py`

For the deployed fleet, `deploy/deploy-fleet.py` performs steps 2-8 and assigns
`MEDIAVORTEX_WORKER_NAME` per instance. See `.claude/rules/worker-deploy.md`.

### How Workers Operate

- `WorkerName` is deploy-assigned via the `MEDIAVORTEX_WORKER_NAME` environment
  variable. It is never derived at runtime; the worker exits if the variable is
  unset. `StartMediaVortex.py` supplies `COMPUTERNAME` when launching locally.
- Every 2 seconds it claims the next pending job via `SELECT FOR UPDATE SKIP LOCKED`
- A heartbeat updates every 30 seconds; stale workers (>5 min) have their jobs reclaimed
- Path translation handles Windows/Linux differences automatically (DB stores canonical `T:\` paths)
- The staging directory must be on the network share so VMAF and file replacement can access output

### Worker Configuration (Workers table)

| Column | Purpose | Example (Windows) | Example (Linux) |
|--------|---------|-------------------|-----------------|
| WorkerName | Deploy-assigned identity (`MEDIAVORTEX_WORKER_NAME`) | `I9-2024` | `wakko-worker-1` |
| Platform | OS type | `windows` | `linux` |
| FFmpegPath | FFmpeg binary | `C:\ffmpeg\bin\ffmpeg.exe` | `/usr/bin/ffmpeg` |
| ShareMountPrefix | Local mount path | `T:\` | `/mnt/media/` |
| ShareCanonicalPrefix | DB path format | `T:\` | `T:\` |
| MaxConcurrentJobs | Parallel jobs (1-5) | `1` | `2` |

### Checking Worker Status

```bash
python Scripts/SQLScripts/QueryDatabase.py workers --columns "WorkerName, Platform, Status, LastHeartbeat, MaxConcurrentJobs"
```

## Database

PostgreSQL 16. Key tables:

| Table | Purpose |
|-------|---------|
| MediaFiles | Current state of every media file |
| Profiles | Transcode profile definitions (libsvtav1) |
| ProfileThresholds | Per-resolution CRF/bitrate settings |
| TranscodeQueue | Pending transcode jobs |
| TranscodeAttempts | Record of each transcode execution |
| Workers | Registered transcoding machines |

## Project Structure

```
MediaVortex/
  WebService/           Flask web app
  WorkerService/        Unified worker service (transcode, VMAF, scanning)
  Features/             Feature verticals (Controller/ViewModel/BusinessService/Repository)
  Core/                 Shared services (Database, Logging, PathTranslation)
  Templates/            Jinja2 HTML templates (Bootstrap 5 + jQuery)
  Scripts/              Utility and migration scripts
  Tests/                Contract tests (pytest)
  StartMediaVortex.py   Start all services
  StopMediaVortex.py    Stop all services
```

## Running Tests

```bash
python -m pytest Tests/Contract/
python -m pytest Tests/Contract/TestQueueGet.py   # single test
```

## Further Documentation

- [ARCHITECTURE.md](ARCHITECTURE.md) -- vertical roster, cross-cutting concerns, data flow
- [DOMAIN.md](DOMAIN.md) -- domain decisions (what the system does and why)
- [transcode.flow.md](transcode.flow.md) -- detailed transcode pipeline reference
- [CLAUDE.md](CLAUDE.md) -- commands, database conventions, naming rules
