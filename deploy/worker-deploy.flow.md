# Flow: Worker Build, Deploy, and Runtime

## Entry Point

`scp` source code to the worker-pool LXC, then `docker build` on the LXC.

The dev workstation does not run Docker. All image builds happen on the LXC (10.0.0.42) which has Docker CE installed via Terraform provisioning.

## Build and Deploy Pipeline

| Step | Command (from dev workstation) | What It Does |
|------|-------------------------------|--------------|
| 1. Push source | `scp -r <repo> root@10.0.0.42:/tmp/mediavortex-build/` | Copies repo source to the LXC (filtered by .dockerignore) |
| 2. Build image | `ssh root@10.0.0.42 'docker build -t mediavortex-worker:latest -f /tmp/mediavortex-build/deploy/Dockerfile /tmp/mediavortex-build/'` | Builds the image on the LXC. Stage 1 downloads BtbN FFmpeg, stage 2 installs Python deps + app code |
| 3. Verify FFmpeg | `ssh root@10.0.0.42 'docker run --rm --entrypoint ffmpeg mediavortex-worker:latest -encoders 2>/dev/null \| grep libsvtav1'` | Confirms SVT-AV1 encoder is present. Must use `--entrypoint` because the image entrypoint is the Python app |
| 4. Start workers | `ssh root@10.0.0.42 'cd /opt/mediavortex && docker compose up -d'` | Starts worker containers using the LXC's docker-compose.yml (deployed by Terraform) |
| 5. Cleanup | `ssh root@10.0.0.42 'rm -rf /tmp/mediavortex-build'` | Removes build source from the LXC |

For code updates, repeat steps 1-5. The LXC's `/opt/mediavortex/docker-compose.yml` is deployed by Terraform (`terraform/mediavortex-workers/setup.sh`), not by this pipeline. It contains hardcoded DB credentials and no `build:` context.

## Runtime Pipeline (per container)

| Step | File | What It Does |
|------|------|--------------|
| 8. Entry point | `TranscodeService/Main.py` | Calls `Main()` which creates `TranscodeServiceApp` |
| 9. DB connect | `Core/Database/DatabaseService.py` | Reads `MEDIAVORTEX_DB_*` env vars, creates psycopg2 ThreadedConnectionPool (min=2, max=20) to 10.0.0.15:5432 |
| 10. Worker identity | `TranscodeService/Main.py:41` | Sets `WorkerName = socket.gethostname()` (stable hostname from compose, e.g. `larry-worker-1`), `WorkerPlatform = "linux"` |
| 11. Register worker | `Repositories/DatabaseManager.py` RegisterWorker() | UPSERT into `Workers` table: inserts or updates WorkerName, Platform, FFmpegPath (via `shutil.which`), FFprobePath, Status='Online', LastHeartbeat=NOW() |
| 11b. Register share mappings | `Repositories/DatabaseManager.py` RegisterWorkerShareMappings() | Parses `MEDIAVORTEX_SHARE_MAPPINGS` env var (e.g. `T=/mnt/media_tv/,M=/mnt/movies/,Z=/mnt/xxx/`), UPSERTs into `WorkerShareMappings` per drive letter |
| 12. Load config | `Repositories/DatabaseManager.py` GetWorkerConfig() | SELECT from `Workers` + `WorkerShareMappings` for this WorkerName. Returns FFmpegPath, FFprobePath, StagingDirectory, MaxConcurrentJobs, share drive-letter mappings |
| 13. Service status | `TranscodeService/Main.py` EnsureServiceStatusExists() | Ensures a row exists in `ServiceStatus` for "TranscodeService" |
| 14. Crash recovery | `Services/CrashRecoveryService.py` | Resets any jobs left in Running/Processing state by this worker from a previous crash |
| 15. Health loop | `TranscodeService/Main.py` HealthCheckLoop() | Thread: updates `Workers.LastHeartbeat` and `ServiceStatus.HealthStatus` every 30s |
| 16. Status poll | `TranscodeService/Main.py` PrivateStatusPollingLoop() | Thread: reads `ServiceStatus.Status` every 5s, starts/stops transcoding based on status changes |
| 17. Main loop | `TranscodeService/Main.py` MainLoop() | Blocks on ShutdownEvent, checking every 10s. SIGTERM/SIGINT triggers SignalHandler |

## Shutdown (SIGTERM from Docker)

| Step | File | What It Does |
|------|------|--------------|
| 18. Signal handler | `TranscodeService/Main.py` SignalHandler() | Kills active FFmpeg processes, resets this worker's Running/Processing queue items to Pending, deletes ActiveJobs entries, sets worker Status='Offline', calls os._exit(0) |

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
| Worker not picking up jobs | Worker registered but idle | Check `ServiceStatus.Status` is 'Running' for TranscodeService; workers respect status polling and won't process unless status is Running |
| Graceful shutdown timeout | Container kill after Docker's stop timeout (default 10s) | Long-running FFmpeg jobs may not finish; SignalHandler kills FFmpeg immediately and resets queue items to Pending for retry |
