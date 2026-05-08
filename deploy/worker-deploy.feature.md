# Feature: Worker Deploy

## What It Does

Builds and deploys MediaVortex TranscodeService workers as Docker containers. Workers are stateless processes that poll the database for transcode jobs, run FFmpeg, and write output to shared media mounts. They scale horizontally via `docker compose up --scale worker=N` on the worker-pool LXC (provisioned by the infrastructure repo).

## Concern

Dogfood

## Success Criteria

1. `docker compose build` produces a `mediavortex-worker:latest` image containing Python 3.12, FFmpeg with SVT-AV1 2.x (`libsvtav1` encoder present), and the TranscodeService code. No GitHub deploy token is baked into the image.

2. Each worker container connects to the MediaVortex PostgreSQL database (10.0.0.15:5432) using environment variables and self-registers in the `Workers` table using its container hostname as `WorkerName`. Registration includes the worker's platform-correct FFmpeg and FFprobe paths (e.g. `/usr/local/bin/ffmpeg` on Linux, `FFmpegMaster\bin\ffmpeg.exe` on Windows).

3. Each worker registers share mappings in `WorkerShareMappings` from the `MEDIAVORTEX_SHARE_MAPPINGS` env var (format: `T=/mnt/media_tv/,M=/mnt/movies/,Z=/mnt/xxx/`). Paths resolve to real files via the bind mounts from the worker-pool LXC. Windows workers that don't set this env var keep their existing mappings.

4. `FFmpegService` reads the per-worker FFmpeg/FFprobe paths from the `Workers` table config before falling back to `systemsettings` or hardcoded discovery. Workers on different platforms use their own registered paths.

5. Workers pick up queued transcode jobs from `TranscodeQueue`, claim them via `ClaimedBy`, and execute FFmpeg transcodes. Output files land in the correct media share path.

6. `docker compose up -d --scale worker=N` adjusts the number of running workers. Each new worker self-registers and begins polling. Scaled-down workers stop gracefully (no in-progress jobs abandoned).

7. Worker containers restart automatically after crashes (`restart: unless-stopped`). Workers use stable hostnames (`larry-worker-1` through `larry-worker-4`) via the Docker Compose `hostname` directive, so DB registrations survive container recreates.

8. The staging directory `/mnt/media_tv/MediaVortex/Staging` is writable from inside the worker container.

9. NFS storage traffic between the worker LXC and Brain uses the 20 Gbps bonded backplane (10.0.1.42 → 10.0.1.1, MTU 9000) instead of the LAN switch path. Verified via `ip addr show eth1` on the LXC showing 10.0.1.42/24 on vmbr1.

## Status

IN PROGRESS

### Progress

- [x] 1. Write Dockerfile (multi-stage: FFmpeg static + Python app)
- [x] 2. Write docker-compose.yml (build context + production config)
- [x] 3. Provision worker-pool LXC (CT 218, 10.0.0.42) via terraform scaffold + apply
- [x] 4. Build image on worker-pool LXC and verify FFmpeg SVT-AV1 present
- [x] 5. ~~Transfer image~~ (built directly on LXC via scp + docker build)
- [x] 6. Start workers on LXC (docker compose up -d)
- [x] 7. Verify DB self-registration (Workers table: 4 workers Online with stable hostnames)
- [x] 8. Queue transcode jobs and verify end-to-end processing
- [x] 9. Stable hostnames (larry-worker-1 through 4) via YAML anchors + hostname directive
- [x] 10. Crash recovery marks stale TranscodeAttempts as failed (prevents ghost rows in Stats)
- [ ] 11. Add backplane NIC (10.0.1.42 on vmbr1) for 20 Gbps NFS storage path

NEXT: Apply backplane NIC via Terraform (step 11). Flow doc at deploy/worker-deploy.flow.md.

## Scope

```
deploy/Dockerfile
deploy/docker-compose.yml
deploy/worker-deploy.feature.md
deploy/worker-deploy.flow.md
TranscodeService/Main.py
Services/FFmpegService.py
```

## Files

- `deploy/Dockerfile` - Multi-stage Docker image build
- `deploy/docker-compose.yml` - Compose config for building and running workers
- `deploy/worker-deploy.flow.md` - Build, deploy, and runtime flow doc
- `TranscodeService/Main.py` - Worker entry point
- `Repositories/DatabaseManager.py` - RegisterWorker(), GetWorkerConfig(), GetWorkerShareMappings()
- `Services/FFmpegService.py` - FFmpeg/FFprobe path resolution (reads per-worker config, then systemsettings, then hardcoded discovery)
- `Core/Database/DatabaseService.py` - PostgreSQL connection pooling (reads MEDIAVORTEX_DB_* env vars)
