# Flow: Worker Build, Deploy, and Runtime

## Entry Point

`scp` source code to the worker-pool LXC, then `docker build` on the LXC.

The dev workstation does not run Docker. All image builds happen on the LXC (10.0.0.42) which has Docker CE installed via Terraform provisioning.

## Build and Deploy Pipeline

Run from the dev workstation (Git Bash). All commands use SSH to the worker-pool LXC at `10.0.0.42`.

```bash
# 1. Create target dir and copy repo source to the LXC
ssh root@10.0.0.42 'rm -rf /tmp/mediavortex-build && mkdir -p /tmp/mediavortex-build'
scp -r /c/Code/MediaVortex/* root@10.0.0.42:/tmp/mediavortex-build/

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
