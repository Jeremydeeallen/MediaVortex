# MediaVortex — Success Scope

> **Purpose:** Single source of truth defining what MediaVortex is, what it does, and what "done" looks like for every feature. Supersedes scattered/outdated docs.
>
> **Last updated:** 2026-03-23

---

## 1. System Overview

MediaVortex is a media transcoding management system that scans media libraries, queues files for FFmpeg transcoding, executes transcode jobs, runs VMAF quality analysis, and optimizes playback for Jellyfin. It runs as **three coordinated microservices** backed by a **local PostgreSQL 16** database.

### Technology Stack

| Layer | Technology |
|-------|-----------|
| Backend | Python 3 / Flask |
| Database | PostgreSQL 16 (localhost:5432, psycopg2) |
| Frontend | Bootstrap 5 + jQuery + Chart.js + Jinja2 |
| Transcoding | FFmpeg (with libvmaf, libsvtav1, libx265, libx264) |
| Quality | VMAF (Video Multimethod Assessment Fusion) |
| Media Server | Jellyfin (integration for optimization analysis) |
| OS | Windows 11 (primary), future Linux/Proxmox workers |

### Architecture Pattern

**MVVM with feature-based modules:**

```
Template (Jinja2 HTML) → Controller (Flask Blueprint) → ViewModel → BusinessService → Repository → DatabaseService → PostgreSQL
```

### Three Microservices

| Service | Entry Point | Purpose |
|---------|-------------|---------|
| **WebService** | `WebService/Main.py` | Flask web app (port 5000) — UI + REST API |
| **TranscodeService** | `TranscodeService/Main.py` | Polls queue, executes FFmpeg jobs |
| **QualityTestService** | `QualityTestService/Main.py` | Polls queue, runs VMAF quality analysis |

All three coordinate via **database records** (no inter-process messaging). `StartMediaVortex.py` launches all three in separate Windows Terminal tabs. `StopMediaVortex.py` gracefully shuts them down.

---

## 2. Database

- **Engine:** PostgreSQL 16, running locally (NOT Docker)
- **Connection:** `localhost:5432`, database/user/password: `mediavortex`
- **Driver:** psycopg2 with `RealDictCursor` (returns lowercase keys)
- **Key mapping:** `CaseInsensitiveDict` maps lowercase PostgreSQL keys ↔ PascalCase in code
- **Known typo:** Column `transcodeattempts.ffpmpegcommand` has double 'p' — code must match
- **Migrations:** Manual via `DatabaseManager.RunMigrations()` on startup (no Alembic)

### Core Tables

| Table | Purpose |
|-------|---------|
| `RootFolders` | Directories to scan for media |
| `Seasons` | TV season organization |
| `MediaFiles` | File inventory (display-only — NOT used for transcode decisions) |
| `MediaFilesArchive` | Backup of original metadata before transcode |
| `TranscodeProfiles` | Encoding profile definitions |
| `ProfileThresholds` | Resolution-based bitrate/size rules per profile |
| `TranscodeQueue` | Jobs awaiting processing |
| `TranscodeAttempts` | Individual transcode attempt records with VMAF scores |
| `TranscodeFiles` | Aggregate transcode status per file |
| `TranscodeProgress` | Real-time progress (frame, FPS, ETA, bitrate) |
| `QualityTestQueue` | Quality tests awaiting execution |
| `QualityTestResults` | VMAF assessment results |
| `QualityTestProgress` | Real-time quality test progress |
| `ServiceStatus` | Microservice heartbeat and state |
| `ServiceCommands` | Inter-service control messages |
| `SystemSettings` | Global key-value configuration |
| `ScanJobs` | Scan operation tracking |
| `JellyfinOperations` | Imported Jellyfin FFmpeg logs |
| `TemporaryFilePaths` | Temp file tracking for cleanup |
| `ActiveJobs` | Currently running jobs |
| `Logs` | Centralized application logs |
| `ProblemFiles` | Files that failed scanning/processing |

---

## 3. Naming Conventions

**PascalCase for everything** — variables, functions, classes, files, database columns, routes, URLs.

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

### API Response Format

```python
return jsonify({'Success': True/False, 'Message': '...', 'Data': {...}}), 200
```

### Database Query Standards

- `LOWER()` required for all `FilePath` equality comparisons (Windows is case-insensitive)
- `DatabaseService.ExecuteQuery()` for SELECT
- `DatabaseService.ExecuteNonQuery()` for INSERT/UPDATE/DELETE

---

## 4. Feature Inventory

### 4.1 File Scanning

**What it does:** Discovers media files in configured directories, extracts metadata via FFprobe, tracks file changes.

**Key behaviors:**
- Recursive directory scanning with subprocess isolation
- Metadata extraction: resolution, codec, bitrate, duration, audio streams
- Incremental scanning: skips unchanged files via `LastModifiedDate` comparison
- Duplicate detection and cleanup (prioritizes transcode history > recency > metadata completeness)
- Continuous/periodic background scanning with configurable intervals
- Excluded directories support
- Unicode filename support

**Critical rule:** `MediaFiles` table is **display-only**. All transcoding decisions come exclusively from `ProfileThresholds`.

**UI page:** `/Scanning` (FileScanning.html)

**Key API endpoints:**
- `POST /api/Scan/Start` — Trigger manual scan
- `GET /api/Scan/ContinuousStatus` — Background scan status
- `POST /api/Scan/EnableContinuous` / `DisableContinuous` — Toggle background scanning
- `GET /api/RootFolders` — List scan directories
- `GET /api/MediaFiles` — List files (paginated, searchable)
- `GET /api/Statistics` — Database statistics
- `GET /api/TranscodeCandidates` — Files needing transcode

---

### 4.2 Profile Management

**What it does:** Define transcode encoding strategies with resolution-specific thresholds.

**Key behaviors:**
- Profile CRUD (create, read, update, delete, copy)
- Resolution-based thresholds (480p, 720p, 1080p, 2160p)
- Codec selection: libsvtav1 (AV1), libx265 (HEVC), libx264 (H.264)
- Preset control (speed vs quality tradeoff)
- Film grain preservation flag
- Deinterlacing settings (Yadif mode/parity)
- NVIDIA hardware acceleration toggle
- File size thresholds by duration (Under30Min, Under65Min, Over65Min)
- Bitrate fallback for oversized transcodes
- Bulk assignment of profiles to root folders

**UI page:** `/settings` (Settings.html — Profile Management section)

**Key API endpoints:**
- `GET /api/profiles` — List all profiles
- `GET/POST/PUT/DELETE /api/profiles/<id>` — Profile CRUD
- `POST/PUT/DELETE /api/profiles/<id>/thresholds/<id>` — Threshold CRUD
- `POST /api/profiles/assign-to-root-folder` — Bulk assign

---

### 4.3 Transcode Queue

**What it does:** Manages the queue of files awaiting FFmpeg transcoding.

**Key behaviors:**
- Populate queue from scanned files matching profile thresholds
- Priority management (1-100 scale)
- Sortable by size, priority, date added
- Paginated display (10/25/50/100 per page)
- Bulk operations: clear queue, remove by file size, cleanup duplicates
- Item count badge in navigation

**UI page:** `/TranscodeQueue` (Queue.html)

**Key API endpoints:**
- `GET /api/TranscodeQueue/GetQueue` — Paginated queue listing
- `POST /api/TranscodeQueue/PopulateQueue` — Add files to queue
- `POST /api/TranscodeQueue/ClearQueue` — Clear queue
- `GET /api/TranscodeQueue/Count` — Queue count (for nav badge)
- `POST /api/TranscodeQueue/RemoveBySize` — Bulk remove by size

---

### 4.4 Transcode Job Execution

**What it does:** Executes FFmpeg transcode commands, tracks progress, manages output files.

**Key behaviors:**
- FFmpeg command generation from profile + threshold settings
- Codec support: AV1, H.265, H.264 with configurable CRF
- Two-pass encoding support
- Real-time progress tracking (frame count, FPS, ETA, bitrate)
- File archival before transcoding (original metadata backup)
- Post-transcode file replacement (swap original with transcoded)
- Size verification before replacement
- Adaptive quality (CRF adjustment based on output size)
- Video pre-processing (deinterlacing via Yadif)
- NVIDIA hardware acceleration support
- Audio re-encoding with bitrate control and language selection (English preferred)
- Audio normalization to -23 LUFS

**UI page:** `/Activity` (Activity.html — active job monitoring)

**Key API endpoints:**
- `POST /api/Transcode/Start` — Start transcode service
- `POST /api/Transcode/Stop` — Stop service
- `POST /api/Transcode/StopAfterCurrent` — Graceful stop
- `GET /api/TranscodeJob/Current` — Current job details

---

### 4.5 Quality Testing (VMAF)

**What it does:** Compares transcoded files against originals using VMAF scoring.

**Key behaviors:**
- VMAF quality scoring (original vs transcoded)
- Quality test queueing and scheduling
- Per-file quality thresholds (passing score limits)
- Preferred attempt marking (best encode per file)
- Service status control (Paused, Running, GracefulStop)
- Result history with pagination
- Automatic queue population after transcode completion

**UI page:** `/TranscodeQueue` (Queue.html — Quality Testing Queue section) and `/Activity`

**Key API endpoints:**
- `POST /api/QualityTest/AddToQueue` — Queue file for testing
- `GET /api/QualityTesting/History` — Test result history
- `GET /api/QualityTesting/Progress` — Current test progress
- `POST /api/QualityTest/Pause` / `Resume` — Control processing
- `POST /api/QualityTest/StopAfterCurrent` — Graceful stop

---

### 4.6 Service Control & Monitoring

**What it does:** Manage lifecycle and health of all three microservices.

**Key behaviors:**
- Start/stop/pause/resume individual services
- Health monitoring with heartbeat polling (every 30 seconds)
- Stuck job detection (timeout after configurable inactivity)
- Crash recovery for orphaned processes
- Graceful shutdown with job completion monitoring
- Inter-service command queue (ServiceCommands table)
- System resource monitoring (CPU, memory, disk, temperature)
- Individual CPU core temperature display

**UI page:** `/Status` (Status.html)

**Key API endpoints:**
- `POST /api/ServiceControl/<service>/<action>` — Control services
- `GET /api/Status` — All service statuses
- `GET /api/Status/SystemResources` — CPU, memory, disk
- `GET /api/Status/CpuTemperatures` — Core temperatures
- `GET /api/health` — Health check

---

### 4.7 Jellyfin Optimization

**What it does:** Analyzes Jellyfin FFmpeg logs to identify playback optimization opportunities.

**Key behaviors:**
- SSH connection to Jellyfin server for FFmpeg log import
- Categorize operations: DirectStream, Transcode, Remux
- Transcode reason analysis (codec incompatibility, subtitle burn-in, etc.)
- Device analysis (client capabilities)
- Recommendations for pre-transcoding to reduce server load

**UI page:** `/Optimization` (Optimization.html)

**Key API endpoints:**
- `POST /api/Optimization/TestConnection` — Test Jellyfin SSH
- `POST /api/Optimization/SyncJellyfin` — Import logs
- `GET /api/Optimization/ServerOverview` — Operation statistics
- `GET /api/Optimization/DeviceAnalysis` — Client analysis

---

### 4.8 Clip Builder

**What it does:** Extract and compile video clips from media files.

**Key behaviors:**
- Search indexed files or browse filesystem
- Video player with custom controls (speed, seek, scrub)
- Clip marking with configurable duration (1-120 seconds)
- Timeline visualization with zoom
- Compilation export to target length (60/120 seconds)
- Optional 30-second version
- Preset save/load

**UI page:** `/ClipBuilder` (ClipBuilder.html)

---

### 4.9 SQL Queries (Debug Tool)

**What it does:** Ad-hoc database querying for troubleshooting.

**Key behaviors:**
- Quick-query buttons: Queue Status, Active Jobs, Stuck Jobs, Recent Errors, Error Summary, Service Health, Database Info
- Custom SQL execution
- Recent failure display with force-complete option for stuck jobs

**UI page:** `/SQLQueries` (SQLQueries.html)

---

### 4.10 System Settings

**What it does:** Global configuration management.

**Key settings:**
- FFmpeg/FFprobe executable paths (with test button)
- CPU thread limit (1-32)
- CPU affinity: temperature threshold, monitoring interval, cooling wait
- Continuous scan interval
- Excluded directories
- Jellyfin connection settings (host, SSH port, user, key, API port, API key)

**UI page:** `/settings` (Settings.html)

---

## 5. UI Pages (Complete Inventory)

| Route | Template | Purpose |
|-------|----------|---------|
| `/` | Home.html | Landing page with feature cards and quick actions |
| `/settings` | Settings.html | Profile management, scan directories, FFmpeg paths, CPU settings |
| `/Scanning` | FileScanning.html | File discovery, continuous scanning, database statistics |
| `/TranscodeQueue` | Queue.html | Transcode queue + quality testing queue |
| `/Activity` | Activity.html | Active job monitoring, start/stop controls, recent attempts |
| `/Status` | Status.html | System resources, CPU temps, service health |
| `/SQLQueries` | SQLQueries.html | Database query tool, stuck job management |
| `/Optimization` | Optimization.html | Jellyfin integration and playback analysis |
| `/ClipBuilder` | ClipBuilder.html | Video clip extraction and compilation |
| (error) | Error.html | Error display (404, 500) |

### Global UI Features (Base.html)
- Navigation bar with active link highlighting
- Queue count badge (auto-refreshes every 30 seconds)
- Persistent error display with copy button
- Toast notifications (success, info, warning, danger)

---

## 6. Code Organization

### Target Structure (Features-based MVVM)

```
Features/
  {FeatureName}/
    {FeatureName}Controller.py    — Flask Blueprint routes
    {FeatureName}ViewModel.py     — UI state + data transformation
    {FeatureName}BusinessService.py — Business logic
    {FeatureName}Repository.py    — Database queries
    Models/                       — Data structures
```

### Current Features Directories

| Feature | Status |
|---------|--------|
| `Features/FileScanning/` | Complete MVVM |
| `Features/TranscodeQueue/` | Complete MVVM |
| `Features/TranscodeJob/` | Complete MVVM |
| `Features/Profiles/` | Complete MVVM |
| `Features/QualityTesting/` | Complete MVVM |
| `Features/ServiceControl/` | Complete MVVM |
| `Features/Activity/` | ViewModel only |
| `Features/FileReplacement/` | Complete MVVM |
| `Features/ClipBuilder/` | Controller + BusinessService |
| `Features/Optimization/` | Complete MVVM |
| `Features/SQLQueries/` | Controller only |
| `Features/SystemSettings/` | Controller + Repository |
| `Features/TeamStatus/` | Controller only (new, minimal) |
| `Features/FailureTracking/` | Controller |

### Legacy Directories (Being Migrated)

| Directory | Contents | Status |
|-----------|----------|--------|
| `Controllers/` | 14 files — mostly stubs redirecting to Features | Transitional |
| `ViewModels/` | 11 files — legacy UI state management | Being replaced |
| `Services/` | 20+ files — shared services (FFmpeg, CPU, hardware) | Partially migrated |
| `Models/` | 20+ files — data structure definitions | Being moved to Features |
| `Repositories/DatabaseManager.py` | Monolithic data access (630+ lines) | Being split into feature repos |

### Shared Infrastructure (Stays at top-level)

| Directory | Purpose |
|-----------|---------|
| `Core/Database/` | PostgreSQL connection pooling, CaseInsensitiveDict |
| `Core/Logging/` | Centralized logging service |
| `Core/FFmpeg/` | FFmpeg utilities |
| `Core/FileSystem/` | File system operations |
| `Core/Hardware/` | Hardware monitoring |
| `Services/CpuAffinityService.py` | CPU pinning (shared across services) |
| `Services/FFmpegService.py` | FFmpeg command execution (shared) |
| `Services/FFmpegAnalysisService.py` | Codec/bitrate extraction (shared) |
| `Services/CommandBuilderService.py` | FFmpeg command generation (shared) |
| `Services/ResolutionService.py` | Resolution logic (shared) |
| `Services/FileManagerService.py` | File I/O (shared) |

---

## 7. Audio Strategy

Three rules for Jellyfin-compatible audio:

1. **Language:** English preferred (`eng`/`en` tags), highest channel count if multiple English streams
2. **Normalization:** -23 LUFS loudness (industry standard)
3. **Codec:** AAC for transcode, copy-if-compatible for remux. MP4-compatible: aac, ac3, eac3, mp3. Re-encode triggers: dts, truehd, flac, pcm_*

---

## 8. Future: Distributed Transcoding

**Status:** NOT STARTED — design documented in memory

**Plan:**
- Move orchestration (Flask API + PostgreSQL) to a Proxmox VM
- Worker agents on physical machines poll central API for jobs
- Transcode in-place via network share mounts (no file transfer)
- Worker registration and health tracking via database
- Implementation phases 1-4 defined

---

## 9. Documentation Audit

### Documents to KEEP (Current & Accurate)

| File | Why |
|------|-----|
| `CLAUDE.md` | Primary dev guide — accurate |
| `Docs/DatabaseSchema.md` | Auto-generated schema reference |
| `Docs/DatabaseStandards.md` | Critical: LOWER() for FilePath queries |
| `Docs/ERD.md` | Auto-generated entity relationships |
| `Docs/AudioStrategy.md` | Audio rules — current |
| `Docs/CpuOptimizationSettings.md` | CPU config — current |
| `Docs/FFMPEGAndVMAFDetails.md` | FFmpeg/VMAF reference — current |
| `Docs/Codecs/CodecOptionsIndex.md` | Codec reference — current |
| `Docs/Codecs/LibSvtAv1Options.md` | AV1 options — current |
| `Docs/Codecs/LibX265Options.md` | HEVC options — current |
| `Docs/UtilityScripts.md` | Script reference — maintained |
| `Docs/Workflows/TranscodingWorkflow.md` | Transcode flow — current |
| `Docs/Workflows/FileScanningWorkflow.md` | Scan flow — current |
| `Docs/Workflows/TranscodeExecutionWorkflow.md` | Execution flow — current |
| `Docs/Workflows/TranscodeQueueManagementWorkflow.md` | Queue ops — current |
| `Docs/Workflows/QualityTestingArchitectureSimplified.md` | QT architecture — current |
| `Docs/MicroServiceQualityTest/MicroServiceQualityTest.md` | QT service spec — current |
| `Docs/MicroServiceQualityTest/QualityTestDatabaseWorkflow.md` | QT DB flow — current |
| `Docs/MicroServiceQualityTest/VMAFOptimization.md` | VMAF tuning — current |
| `Docs/MicroServiceTranscode/MicroServiceTranscodePlan.md` | Transcode service spec — current |
| `Docs/SystemWide/AutomatedCrashRecovery.md` | Crash recovery — current |
| `Docs/TemperatureMonitoringLimitations.md` | Temp monitoring — current |
| `Docs/FutureImprovements/FutureImprovements.md` | Roadmap — properly labeled |
| `Docs/FutureImprovements/QualityTestingFutureFeatures.md` | QT roadmap — properly labeled |

### Documents to UPDATE (Outdated Content)

| File | Issue | Fix |
|------|-------|-----|
| `Docs/Architecture.md` | References SQLite instead of PostgreSQL | Replace SQLite → PostgreSQL 16 |
| `Docs/SystemOrchestration.md` | Says "logs stored in MediaVortex.db" | Change to PostgreSQL |
| `Docs/ImplementationPlan.md` | Checkboxes don't reflect actual status | Update completion status |
| `OPTIMIZATION_IMPLEMENTATION.md` | Phase 2 status unclear | Clarify what's done vs pending |

### Documents to DELETE or DEMOTE (Obsolete/Aspirational)

| File | Reason |
|------|--------|
| `Docs/DatabaseMigrationStrategy.md` | Proposes Alembic — never implemented, misleading |
| `Docs/CacheManagement.md` | References pre-microservice architecture, questionable relevance |
| `Docs/CSSArchitecture.md` | Verify if still relevant to current CSS approach |
| `Docs/FileScanningFlow.md` | Duplicated by `Docs/Workflows/FileScanningWorkflow.md` (check which is newer) |
| `Docs/ShouldQualityTestServiceImplementationPlan.md` | Implementation plan — likely completed |
| `Docs/Checklists/TemporaryFilePathsImplementationPlan.md` | Implementation plan — likely completed |
| `Docs/Workflows/ArchitectureWorkflowGettingStarted.md` | Getting started guide — verify if current |
| `Docs/Workflows/ArchitectureWorkflowToWalkingSkeleton.md` | Walking skeleton — historical |
| `Docs/Workflows/MediaFilesWorkflow.md` | Verify if duplicated by other workflow docs |
| `Docs/Workflows/ResolutionStandardizationWorkflow.md` | Verify if implemented or aspirational |
| `Docs/FileScanner/SolveLowerCaseRequirements.md` | Solved — superseded by DatabaseStandards.md |
| `Docs/RAID_Recovery_After_Power_Surge.md` | Infrastructure incident log — not app docs |
| `Docs/ProxmoxBootDriveBackupSystem.md` | Infrastructure — not app docs |
| `Templates/TranscodeProgress.html` | Deleted in git (shows as ` D` in status) |
| `.claude/skills/db-query/SKILL.md` | Deleted in git |
| `.claude/skills/ui-expert/SKILL.md` | Deleted in git |
| `.claude/skills/video-expert/SKILL.md` | Deleted in git |

### Other Files to Review

| File | Question |
|------|----------|
| `docker-compose.yml` | Not used for current setup — add comment or move to `deploy/` |
| `specs/002-add-a-feature/plan.md` | References SQLite — old spec file |

---

## 10. Success Criteria

MediaVortex is "done" when:

1. **File scanning** discovers all media files in configured directories with accurate metadata
2. **Profiles** define complete encoding strategies for all target codecs and resolutions
3. **Queue management** correctly populates, prioritizes, and manages the transcode backlog
4. **Transcode execution** produces properly encoded files with correct codec, quality, and audio settings
5. **Quality testing** validates transcoded output meets VMAF quality thresholds
6. **File replacement** safely swaps originals with verified transcodes
7. **Service control** provides reliable start/stop/pause/resume with crash recovery
8. **System monitoring** shows real-time resource usage and service health
9. **Jellyfin optimization** identifies and queues files that cause server-side transcoding
10. **All three microservices** run independently and coordinate via database
11. **UI** provides full control over all features with real-time status updates
12. **Code organization** follows MVVM in `Features/` with PascalCase naming throughout
