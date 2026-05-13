# Flow: Worker Build, Deploy, and Runtime

## Host Inventory

| Host | IP | Workers | CPU | Compose Location |
|------|-----|---------|-----|------------------|
| Larry (LXC on Proxmox) | 10.0.0.42 | larry-worker-1 through 8 | 2x Xeon (64 threads), cpuset pinned | `/opt/mediavortex/docker-compose.yml` |
| Wakko (client-b450m-01) | 10.0.0.230 | client-b450m-01 through 04 | Ryzen 7 3700X (8C/16T), 4 threads/worker | `/opt/mediavortex/docker-compose.yml` |

Deploy commands target a host by IP. When adding a new host, add it here and follow the Build and Deploy Pipeline below.

## Entry Point

`scp` source code to the target host, then `docker build` on that host.

The dev workstation does not run Docker. All image builds happen on the target host which has Docker CE installed.

## Pre-Flight Checks

Verify before any deploy (first-time or redeploy):

| Check | Command (from dev workstation) | Expected |
|-------|-------------------------------|----------|
| SSH to LXC | `ssh root@10.0.0.42 'hostname'` | `larry` |
| Docker running | `ssh root@10.0.0.42 'docker info --format "{{.ServerVersion}}"'` | Version number (e.g. `24.0.7`) |
| DB reachable from LXC | `ssh root@10.0.0.42 'nc -zw2 10.0.0.15 5432 && echo OK'` | `OK` |
| NFS mounts present on LXC | `ssh root@10.0.0.42 'ls /mnt/media_tv /mnt/movies /mnt/xxx'` | Directory listings (not empty, not error) |
| Compose file deployed | `ssh root@10.0.0.42 'test -f /opt/mediavortex/docker-compose.yml && echo OK'` | `OK` |
| No active transcode jobs | `py Scripts/SQLScripts/QueryDatabase.py sql "SELECT COUNT(*) FROM TranscodeQueue WHERE Status = 'Running' AND ClaimedBy LIKE 'larry%'"` | `0` (or drain first) |

If any check fails, resolve before proceeding. The compose file is deployed by Terraform (`terraform/mediavortex-workers/setup.sh`) -- if missing, re-apply that module.

## Build and Deploy Pipeline

Run from the dev workstation (Git Bash). All commands use SSH to the worker-pool LXC at `10.0.0.42`. Use this for first-time deploys or when the Dockerfile/requirements.txt changes.

```bash
# 1. Create target dir and copy repo source to the LXC
ssh root@10.0.0.42 'rm -rf /tmp/mediavortex-build && mkdir -p /tmp/mediavortex-build'
scp -r c:/Code/MediaVortex/* root@10.0.0.42:/tmp/mediavortex-build/
cls
# 2. Build the Docker image on the LXC
ssh root@10.0.0.42 'docker build -t mediavortex-worker:latest -f /tmp/mediavortex-build/deploy/Dockerfile /tmp/mediavortex-build/'

# 3. Recreate and start workers (picks up new image automatically)
ssh root@10.0.0.42 'cd /opt/mediavortex && docker compose up -d'

# 4. Clean up build source
ssh root@10.0.0.42 'rm -rf /tmp/mediavortex-build'
```

**Verify** (optional):
```bash
# Confirm SVT-AV1 encoder is in the image
ssh root@10.0.0.42 'docker run --rm --entrypoint ffmpeg mediavortex-worker:latest -encoders 2>/dev/null | grep libsvtav1'

# Confirm workers registered and online
py Scripts/SQLScripts/QueryDatabase.py sql "SELECT WorkerName, Status, LastHeartbeat FROM Workers WHERE WorkerName LIKE 'larry%' ORDER BY WorkerName"
```

**Notes:**
- The LXC's `/opt/mediavortex/docker-compose.yml` is deployed by Terraform (`terraform/mediavortex-workers/setup.sh`), not by this pipeline. It contains DB credentials and volume mounts.
- `scp` requires the target directory to exist first -- the `mkdir -p` in step 1 handles this.
- For code-only updates, repeat all 4 steps. The FFmpeg binary is cached in the Docker build layer and only re-downloads if the Dockerfile changes.
- Workers that are mid-transcode will be stopped by `docker compose up -d` (sends SIGTERM). The SignalHandler resets their queue items to Pending for retry. Wait for workers to finish or gracefully stop them before deploying if you want to avoid re-transcoding.

## Code-Only Redeploy

When you have shipped a code change and only need to update the Python code (no Dockerfile change, no new pip packages):

```bash
# Same 4 steps as above -- the Docker build layer cache makes this fast.
# FFmpeg download layer is cached; only the COPY . /app layer rebuilds.
ssh root@10.0.0.42 'rm -rf /tmp/mediavortex-build && mkdir -p /tmp/mediavortex-build'
scp -r c:/Code/MediaVortex/* root@10.0.0.42:/tmp/mediavortex-build/
ssh root@10.0.0.42 'docker build -t mediavortex-worker:latest -f /tmp/mediavortex-build/deploy/Dockerfile /tmp/mediavortex-build/'
ssh root@10.0.0.42 'cd /opt/mediavortex && docker compose up -d'
ssh root@10.0.0.42 'rm -rf /tmp/mediavortex-build'
```

For code-only updates the build takes ~30-60s (cache hit on FFmpeg layer). Workers restart within ~5s of `docker compose up -d`.

**Caution:** `docker compose up -d` sends SIGTERM to running containers. Workers mid-transcode will be interrupted (their queue items reset to Pending for retry). To avoid re-transcoding:

```bash
# Drain workers first (they finish current jobs, then stop accepting new ones)
py Scripts/SQLScripts/QueryDatabase.py sql "UPDATE Workers SET Status = 'Draining' WHERE WorkerName LIKE 'larry%'"

# Wait for active jobs to finish (poll until no Running jobs remain)
py Scripts/SQLScripts/QueryDatabase.py sql "SELECT WorkerName, COUNT(*) FROM TranscodeQueue WHERE Status = 'Running' AND ClaimedBy LIKE 'larry%' GROUP BY WorkerName"

# Once empty, deploy
ssh root@10.0.0.42 'cd /opt/mediavortex && docker compose up -d'
```

## Post-Deploy Verification

After `docker compose up -d`, verify the full startup sequence completed. Run these from the dev workstation.

### 1. Containers running

```bash
ssh root@10.0.0.42 'docker ps --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}" | grep larry'
```

Expected: 4 containers, all `Up` with no `(Restarting)`.

### 2. Workers registered with valid FFmpeg paths

```bash
py Scripts/SQLScripts/QueryDatabase.py sql "SELECT WorkerName, Status, FFmpegPath, FFprobePath, AGE(NOW(), LastHeartbeat) AS HeartbeatAge FROM Workers WHERE WorkerName LIKE 'larry%' ORDER BY WorkerName"
```

Expected per worker:
- `Status = 'Online'`
- `FFmpegPath = '/usr/local/bin/ffmpeg'` (NOT NULL)
- `FFprobePath = '/usr/local/bin/ffprobe'` (NOT NULL)
- `HeartbeatAge < 60 seconds`

If `FFmpegPath` is NULL, the FFmpeg binary is missing from the Docker image -- see Troubleshooting below.

### 3. Share mappings registered

```bash
py Scripts/SQLScripts/QueryDatabase.py sql "SELECT WorkerName, DriveLetter, LocalPath FROM WorkerShareMappings WHERE WorkerName LIKE 'larry%' ORDER BY WorkerName, DriveLetter"
```

Expected: 12 rows (4 workers x 3 drive letters: M, T, Z). Each `LocalPath` should match the bind mounts in the compose file:
- `T` -> `/mnt/media_tv/`
- `M` -> `/mnt/movies/`
- `Z` -> `/mnt/xxx/`

### 4. Capabilities enabled

```bash
py Scripts/SQLScripts/QueryDatabase.py sql "SELECT WorkerName, TranscodeEnabled, QualityTestEnabled, ScanEnabled FROM Workers WHERE WorkerName LIKE 'larry%' ORDER BY WorkerName"
```

Expected: `TranscodeEnabled = true` for all workers. New workers default to `TranscodeEnabled = true`; adjust via:

```bash
py Scripts/SQLScripts/QueryDatabase.py sql "UPDATE Workers SET QualityTestEnabled = true WHERE WorkerName = 'larry-worker-1'"
```

### 5. First job claimed (optional, requires queued work)

```bash
py Scripts/SQLScripts/QueryDatabase.py sql "SELECT QueueId, ClaimedBy, Status, DateStarted FROM TranscodeQueue WHERE ClaimedBy LIKE 'larry%' ORDER BY DateStarted DESC LIMIT 5"
```

Expected timing after containers start:
- **0-10 s**: containers up, DB connection established, Workers row UPSERT-ed
- **0-30 s**: capability poller reads flags, transcode loop starts
- **30-90 s**: first job claimed (if queue has eligible work and worker status is Online)

### 6. FFmpeg binary verification (if FFmpegPath issues suspected)

```bash
# Verify FFmpeg exists inside a running container
ssh root@10.0.0.42 'docker exec larry-worker-1 which ffmpeg'
# Expected: /usr/local/bin/ffmpeg

# Verify SVT-AV1 encoder is available
ssh root@10.0.0.42 'docker exec larry-worker-1 ffmpeg -encoders 2>/dev/null | grep libsvtav1'
# Expected: V..... libsvtav1 ...

# Verify FFprobe
ssh root@10.0.0.42 'docker exec larry-worker-1 which ffprobe'
# Expected: /usr/local/bin/ffprobe
```

### 7. Bind mount verification

```bash
ssh root@10.0.0.42 'docker exec larry-worker-1 ls /mnt/media_tv/ | head -5'
ssh root@10.0.0.42 'docker exec larry-worker-1 ls /mnt/movies/ | head -5'
ssh root@10.0.0.42 'docker exec larry-worker-1 ls /mnt/xxx/ | head -5'
```

Expected: directory listings showing media content. If empty or error, the LXC bind mounts are missing.

## Troubleshooting

### Worker registered but FFmpegPath is NULL

**Symptom:** `Workers` row exists with `Status='Online'` but `FFmpegPath = NULL`. All transcode jobs fail with "Failed to build transcoding command".

**Diagnosis:**
```bash
# Check container logs for the FFmpeg resolution step
ssh root@10.0.0.42 'docker logs larry-worker-1 2>&1 | grep -i "ffmpeg\|resolve\|binary\|RuntimeError" | tail -20'

# Verify the binary exists in the image
ssh root@10.0.0.42 'docker exec larry-worker-1 ls -la /usr/local/bin/ffmpeg /usr/local/bin/ffprobe'
```

**Root cause:** The Dockerfile's FFmpeg download stage failed silently, or the binary was not copied to the final stage. The `_ResolveBundledOrPathBinary()` function checks `shutil.which('ffmpeg')` -- if the binary isn't on PATH inside the container, it returns None.

**Fix:** Rebuild the image. If the BtbN download URL is stale, check https://github.com/BtbN/FFmpeg-Builds/releases for the current `latest` tag.

### Worker not picking up jobs

**Symptom:** Workers are Online with valid FFmpegPath but idle.

**Checklist:**
```bash
# 1. Verify status is Online (not Draining or Offline)
py Scripts/SQLScripts/QueryDatabase.py sql "SELECT WorkerName, Status FROM Workers WHERE WorkerName LIKE 'larry%'"

# 2. Verify TranscodeEnabled is true
py Scripts/SQLScripts/QueryDatabase.py sql "SELECT WorkerName, TranscodeEnabled FROM Workers WHERE WorkerName LIKE 'larry%'"

# 3. Verify there are actually queued items
py Scripts/SQLScripts/QueryDatabase.py sql "SELECT COUNT(*) FROM TranscodeQueue WHERE Status = 'Pending'"

# 4. Check for errors in the Logs table
py Scripts/SQLScripts/QueryDatabase.py sql "SELECT Message, ExceptionMessage, CreatedAt FROM Logs WHERE Source LIKE 'larry%' ORDER BY CreatedAt DESC LIMIT 10"
```

### Container crash-looping

**Symptom:** `docker ps` shows `Restarting` status; `docker logs` shows rapid exits.

```bash
# Check exit code and restart count
ssh root@10.0.0.42 'docker inspect larry-worker-1 --format "{{.State.ExitCode}} {{.RestartCount}}"'

# Check last few log lines
ssh root@10.0.0.42 'docker logs --tail 50 larry-worker-1'
```

**Common causes:**
- DB unreachable (psycopg2.OperationalError) -- check `10.0.0.15:5432` from 10.0.0.42
- Connection slots exhausted -- check `pg_stat_activity` count on the DB
- Python import error (missing package) -- rebuild image with `--no-cache`

### Share mappings not registering

**Symptom:** `WorkerShareMappings` has no rows for a worker, or LocalPath values are wrong.

```bash
# Check the MEDIAVORTEX_SHARE_MAPPINGS env var inside the container
ssh root@10.0.0.42 'docker exec larry-worker-1 printenv MEDIAVORTEX_SHARE_MAPPINGS'
# Expected: T=/mnt/media_tv/,M=/mnt/movies/,Z=/mnt/xxx/
```

If missing, the env var is not set in `/opt/mediavortex/docker-compose.yml` on the LXC. That file is managed by Terraform -- update in `terraform/mediavortex-workers/setup.sh` and re-apply.

### Transcoding fails with path errors

**Symptom:** TranscodeAttempts show failures with "No such file or directory" for source paths.

**Diagnosis:**
```bash
# Check the path translation is working (canonical T:\ path -> /mnt/media_tv/)
py Scripts/SQLScripts/QueryDatabase.py sql "SELECT FilePath FROM TranscodeQueue WHERE ClaimedBy = 'larry-worker-1' ORDER BY DateStarted DESC LIMIT 1"

# Verify the file exists on the worker's mount
ssh root@10.0.0.42 'docker exec larry-worker-1 ls -la "/mnt/media_tv/<relative-path-from-above>"'
```

**Common causes:**
- Bind mount not configured in compose (LXC-level)
- NFS export not mounted on the LXC itself (`ls /mnt/media_tv` on the LXC returns empty)
- File was deleted between queue population and transcode claim

## Runtime Pipeline (per container)

| Step | File | What It Does |
|------|------|--------------|
| 8. Entry point | `WorkerService/Main.py` | Calls `Main()` which creates `WorkerServiceApp` |
| 9. DB connect | `Core/Database/DatabaseService.py` | Reads `MEDIAVORTEX_DB_*` env vars, creates psycopg2 ThreadedConnectionPool (min=2, max=20) to 10.0.0.15:5432 |
| 10. Worker identity | `WorkerService/Main.py` | Sets `WorkerName = socket.gethostname()` (stable hostname from compose, e.g. `larry-worker-1`), `WorkerPlatform = platform.system().lower()` |
| 11. Register worker | `Repositories/DatabaseManager.py` RegisterWorker() | UPSERT into `Workers` table: inserts or updates WorkerName, Platform, FFmpegPath (via `shutil.which`), FFprobePath, Status='Online', LastHeartbeat=NOW() |
| 11b. Register share mappings | `Repositories/DatabaseManager.py` RegisterWorkerShareMappings() | Parses `MEDIAVORTEX_SHARE_MAPPINGS` env var (e.g. `T=/mnt/media_tv/,M=/mnt/movies/,Z=/mnt/xxx/`), UPSERTs into `WorkerShareMappings` per drive letter. **Workaround for OS-coupled path storage -- see `KNOWN-ISSUES.md` entry `[BUG - CRITICAL - WORKAROUND IN PLACE] Canonical path storage is OS-coupled` for the diagnosis and target architecture (`path-storage.feature.md`).** |
| 12. Initialize WorkerContext | `Core/WorkerContext.py` | Singleton initialized with FFmpegPath, FFprobePath, PathTranslation from Workers/WorkerShareMappings. All services in the process resolve tool paths from WorkerContext. |
| 13. Load capabilities | `WorkerService/Main.py` _LoadCapabilitiesFromDB() | Reads `TranscodeEnabled`, `QualityTestEnabled`, `ScanEnabled` from Workers row. Starts/stops capability loops accordingly. |
| 14. Crash recovery | `Services/CrashRecoveryService.py` | Resets any jobs left in Running/Processing state by this worker from a previous crash |
| 15. Health loop | `WorkerService/Main.py` _HealthCheckLoop() | Thread: updates `Workers.LastHeartbeat` every 30s |
| 16. Status poll | `WorkerService/Main.py` _StatusPollingLoop() | Thread: reads `Workers.Status` every 5s, handles Online/Draining/Offline transitions |
| 16b. Capability poll | `WorkerService/Main.py` _CapabilityPollingLoop() | Thread: reads capability flags from Workers every 60s, starts/stops transcode/VMAF/scan loops on change |
| 17. Main loop | `WorkerService/Main.py` Run() | Blocks on ShutdownEvent. SIGTERM/SIGINT triggers SignalHandler |

## Shutdown (SIGTERM from Docker)

| Step | File | What It Does |
|------|------|--------------|
| 18. Signal handler | `WorkerService/Main.py` _SignalHandler() | Kills active FFmpeg processes, resets this worker's Running/Processing queue items to Pending, deletes ActiveJobs entries, sets worker Status='Offline', calls os._exit(0) |

## Environment Variables

| Variable | Default (compose) | Default (code) | Purpose |
|----------|-------------------|----------------|---------|
| `MEDIAVORTEX_DB_HOST` | 10.0.0.15 | localhost | PostgreSQL host |
| `MEDIAVORTEX_DB_PORT` | 5432 | 5432 | PostgreSQL port |
| `MEDIAVORTEX_DB_NAME` | mediavortex | mediavortex | Database name |
| `MEDIAVORTEX_DB_USER` | mediavortex | mediavortex | Database user |
| `MEDIAVORTEX_DB_PASSWORD` | mediavortex | mediavortex | Database password |
| `MEDIAVORTEX_SHARE_MAPPINGS` | `T=/mnt/media_tv/,M=/mnt/movies/,Z=/mnt/xxx/` | (none) | Drive letter to local mount path mappings, registered in `WorkerShareMappings` at startup |

The compose defaults (in the LXC's docker-compose.yml) override the code defaults (localhost), so workers connect to the correct DB without additional configuration.

## Failure Modes

| Failure | Symptom | Resolution |
|---------|---------|------------|
| AppArmor blocks Docker build | `unable to apply apparmor profile` during any RUN step | Docker-in-LXC: the kernel AppArmor interface is not exposed into the container. Fix: `apt-get purge -y apparmor` in setup.sh removes the `apparmor_parser` binary so Docker detects AppArmor as unavailable and skips it for builds and runtime. No daemon.json or per-service `security_opt` needed |
| BtbN download fails during build | Dockerfile stage 1 exits non-zero, `docker compose build` fails | Retry; check GitHub release URL; BtbN releases are tagged `latest` and occasionally rotate |
| DB unreachable at container start | psycopg2.OperationalError in logs, container restarts (restart: unless-stopped) | Verify 10.0.0.15:5432 is reachable from 10.0.0.42; check PostgreSQL pg_hba.conf allows the worker IP |
| Stale worker DB entries | Container recreates with random hostnames leave orphaned Workers rows | Fixed: docker-compose.yml uses YAML anchors with explicit `hostname:` per service (larry-worker-1 through 4). `socket.gethostname()` returns the stable name, so registrations survive recreates and crash recovery matches its own previous entries |
| Bind mount missing on LXC | FFmpeg writes fail with ENOENT or EACCES | Verify LXC mount points: `ls /mnt/media_tv /mnt/movies /mnt/xxx` on 10.0.0.42 |
| Image not built on LXC | `docker compose up` fails with "image not found" | Re-run scp + docker build pipeline (steps 1-2) |
| Staging directory not writable | Transcode jobs fail when writing temp output | Check `/mnt/media_tv/MediaVortex/Staging` exists and is writable (Dockerfile creates the mount point, but the real directory must exist on the NFS share) |
| Worker not picking up jobs | Worker registered but idle | Check `Workers.Status` is 'Online' for the worker; workers poll their own status and won't process unless status is Online. Also verify capability flags (TranscodeEnabled, QualityTestEnabled) are set. |
| Graceful shutdown timeout | Container kill after Docker's stop timeout (default 10s) | Long-running FFmpeg jobs may not finish; SignalHandler kills FFmpeg immediately and resets queue items to Pending for retry |
| Crash-loop with exit code 0 in <0.5s, no log output | `docker ps` shows `Restarting (0)` repeatedly; `docker logs` empty | Resolved 2026-05-08. Root cause was crash-recovery sending SIGTERM to the recorded `ActiveJobs.ProcessId` from a previous run. In Docker every Python entrypoint is PID 1, so the new container's PID matched the stale row and the worker terminated itself via its own SignalHandler. Fix: `Features/ServiceControl/CrashRecoveryService.py` skips the kill step when `process_id == os.getpid()`. |
| `psycopg2.OperationalError: remaining connection slots are reserved for SUPERUSER` | Worker startup connects, then fails with the slot error after several restarts | Resolved 2026-05-08. Root cause was the SignalHandler calling `os._exit(0)` which bypasses `atexit` cleanup, so each crashing worker leaked its `ThreadedConnectionPool(min=2)` idle connections on the postgres host. Compounded by `max_connections=30` on the DB, exhausting slots within a few restart cycles. Fix: SignalHandler in WorkerService/Main.py, WebService/Main.py, and TranscodeService/Main.py now call `DatabaseService._pool.closeall()` before `os._exit(0)`. Postgres `max_connections` raised from 30 to 200 on 10.0.0.15 (CT 203). |
| Worker registers with `Workers.FFmpegPath = NULL` (Windows) | Subsequent jobs all fail with bland "Failed to build transcoding command" message and no exception details | Resolved 2026-05-08. `shutil.which('ffmpeg')` returns `None` on Windows hosts where FFmpeg isn't on PATH; that NULL was written verbatim into Workers and propagated through WorkerContext into `CommandData['FFmpegPath']`, where Models/CommandBuilder raised ValueError that the broad `except` block swallowed silently. Fix: `_ResolveBundledOrPathBinary()` checks the project-bundled `FFmpegMaster/bin/` location first, falls back to PATH, and raises `RuntimeError` if neither yields a real binary. CommandBuilder now `LogException`s before returning None. ProcessTranscodeQueueService falls back to `FFmpegService` discovery when WorkerContext path is NULL with a loud warning. |
| FFmpeg command in DB references the wrong absolute path on Windows (e.g. `C:\Code\Automation\MediaVortex\FFmpegMaster\bin\ffmpeg.exe`) | TranscodeAttempts.FFpmpegCommand contains a path to a directory that no longer exists | Resolved 2026-05-08. `Models/CommandBuilder.py` had three sites with `or 'C:\\Code\\Automation\\MediaVortex\\FFmpegMaster\\bin\\ffmpeg.exe'` hardcoded fallbacks. `Features/ClipBuilder/ClipBuilderBusinessService.py` had a module-level constant pointing at the same dead path. All purged in commit 87aaf58; the project moved to `C:\Code\MediaVortex\` and the old directory was deleted. |
| Worker claims a job whose source file no longer exists | Endless retry loop where queue population keeps re-adding the same dead-file row | Resolved 2026-05-08. `ProcessJob` now performs an `os.path.exists()` pre-flight on the locally-resolved source path BEFORE creating any TranscodeAttempt. On miss: increments `MediaFiles.FFprobeFailureCount`, records `LastFFprobeError`, deletes the queue item, returns without creating an attempt row. Existing scan-time guard (`FFprobeFailureCount >= 3 -> skip on subsequent scans`) then keeps queue population from re-targeting it. |
| Post-replacement re-probe fails with "No such file or directory" on a file that exists at the new path | TranscodeAttempt shows `Success=true, FileReplaced=true` but MediaFiles row is not updated; queue keeps re-claiming the file | Resolved 2026-05-08. `Features/FileReplacement/FileReplacementBusinessService.py` used `os.path.dirname()` on a Windows-flavored canonical DB path. On Linux workers `os.path` doesn't recognize `\\` as a separator -> dirname returned empty string -> the new path was just the filename -> FFprobe ran in CWD and failed. Fix: use `ntpath.dirname` / `ntpath.join` for canonical paths regardless of host platform. One-shot recovery script `Scripts/FixStuckPostReplacementFiles.py` re-probes and updates rows that were left in this state. |
