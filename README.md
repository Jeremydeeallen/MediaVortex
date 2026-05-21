# MediaVortex

Media transcoding and management system. Scans media files, assigns transcode profiles, queues and executes FFmpeg transcoding jobs (AV1 via libsvtav1), and runs VMAF quality analysis. Supports distributed transcoding across multiple machines.

## Quick Start

```bash
# Install dependencies
python -m venv venv
venv\Scripts\Activate.ps1          # Windows
source venv/bin/activate            # Linux
pip install -r requirements.txt

# Set database connection (PostgreSQL)
# Default: localhost:5432, database/user/password: mediavortex
# Override with environment variables:
#   MEDIAVORTEX_DB_HOST, MEDIAVORTEX_DB_PORT, MEDIAVORTEX_DB_NAME,
#   MEDIAVORTEX_DB_USER, MEDIAVORTEX_DB_PASSWORD

# Start all services
python StartMediaVortex.py

# Stop all services
python StopMediaVortex.py
```

Web UI available at `http://localhost:5000`.

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

Full guide: [TranscodeService/WorkerSetup.md](TranscodeService/WorkerSetup.md)

**Summary:**

1. Clone the repo on the new machine
2. Install dependencies (`pip install -r TranscodeService/requirements.txt`)
3. Mount the media network share (same files the WebService scans)
4. Set `MEDIAVORTEX_DB_*` environment variables pointing to the shared database
5. Run the migration: `python Scripts/SQLScripts/AddDistributedColumns.py`
6. Register the worker in the database (INSERT into Workers table)
7. Create the staging directory on the network share
8. Start: `python WorkerService/Main.py`

### How Workers Operate

- On startup, a worker registers itself using `socket.gethostname()`
- Every 2 seconds it claims the next pending job via `SELECT FOR UPDATE SKIP LOCKED`
- A heartbeat updates every 30 seconds; stale workers (>5 min) have their jobs reclaimed
- Path translation handles Windows/Linux differences automatically (DB stores canonical `T:\` paths)
- The staging directory must be on the network share so VMAF and file replacement can access output

### Worker Configuration (Workers table)

| Column | Purpose | Example (Windows) | Example (Linux) |
|--------|---------|-------------------|-----------------|
| WorkerName | Machine hostname | `DESKTOP-ABC` | `transcode-vm` |
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

- [TranscodeService/WorkerSetup.md](TranscodeService/WorkerSetup.md) -- step-by-step worker setup for Windows and Linux
- [Docs/SystemOrchestration.md](Docs/SystemOrchestration.md) -- service startup and management options
- [transcode.flow.md](transcode.flow.md) -- detailed transcode pipeline reference
