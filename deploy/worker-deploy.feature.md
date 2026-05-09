# Feature: Worker Deploy

## What It Does

Builds and deploys MediaVortex WorkerService instances as Docker containers. Workers are stateless processes that poll the database for transcode jobs (and optionally VMAF quality tests and file scanning), run FFmpeg, and write output to shared media mounts. They scale horizontally via `docker compose up --scale worker=N` on the worker-pool LXC (provisioned by the infrastructure repo).

## Concern

Dogfood

## Success Criteria

1. `docker compose build` produces a `mediavortex-worker:latest` image containing Python 3.12, FFmpeg with SVT-AV1 2.x (`libsvtav1` encoder present), and the WorkerService code. No GitHub deploy token is baked into the image.

2. Each worker container connects to the MediaVortex PostgreSQL database (10.0.0.15:5432) using environment variables and self-registers in the `Workers` table using its container hostname as `WorkerName`. Registration includes the worker's platform-correct FFmpeg and FFprobe paths (e.g. `/usr/local/bin/ffmpeg` on Linux, `FFmpegMaster\bin\ffmpeg.exe` on Windows).

3. Each worker registers share mappings in `WorkerShareMappings` from the `MEDIAVORTEX_SHARE_MAPPINGS` env var (format: `T=/mnt/media_tv/,M=/mnt/movies/,Z=/mnt/xxx/`). Paths resolve to real files via the bind mounts from the worker-pool LXC. Windows workers that don't set this env var keep their existing mappings.

4. `FFmpegService` reads the per-worker FFmpeg/FFprobe paths from the `Workers` table config before falling back to `systemsettings` or hardcoded discovery. Workers on different platforms use their own registered paths.

5. Workers pick up queued transcode jobs from `TranscodeQueue`, claim them via `ClaimedBy`, and execute FFmpeg transcodes. Output files land in the correct media share path.

6. `docker compose up -d --scale worker=N` adjusts the number of running workers. Each new worker self-registers and begins polling. Scaled-down workers stop gracefully (no in-progress jobs abandoned).

7. Worker containers restart automatically after crashes (`restart: unless-stopped`). Workers use stable hostnames (`larry-worker-1` through `larry-worker-4`) via the Docker Compose `hostname` directive, so DB registrations survive container recreates.

8. The staging directory `/mnt/media_tv/MediaVortex/Staging` is writable from inside the worker container.

9. NFS storage traffic between the worker LXC and Brain uses the 20 Gbps bonded backplane (10.0.1.42 → 10.0.1.1, MTU 9000) instead of the LAN switch path. Verified via `ip addr show eth1` on the LXC showing 10.0.1.42/24 on vmbr1.

10. **Worker startup hard-fails when FFmpeg/FFprobe binaries cannot be resolved.** `_ResolveBundledOrPathBinary()` checks the project-bundled `FFmpegMaster/bin/<binary>{.exe?}` first, then falls back to `shutil.which()`. If neither yields a real path, `RuntimeError` is raised before any Workers row is written. Replaces the previous silent registration of `Workers.FFmpegPath = NULL` (root cause of the I9-2024 outage on 2026-05-08).

11. **Crash-recovery does not self-terminate inside Docker containers.** When the recorded `ActiveJobs.ProcessId` matches `os.getpid()`, the worker treats the entry as a stale row from a prior container instance and skips the kill step (in Docker every Python entrypoint runs as PID 1, so a naive recorded-PID match would always hit the new process). Without this guard, the worker SIGTERMs itself during recovery, exits via SignalHandler with code 0, restart-loops forever.

12. **SignalHandler releases the psycopg2 pool before `os._exit()`.** Each crashing-and-restarting worker would otherwise leak its idle DB connections (atexit handlers do not run after `os._exit`), eventually exhausting `max_connections` on the postgres host. Verified by running 4 workers through several restart cycles and confirming no growth in `pg_stat_activity` from the worker LXC IP.

13. **Source-file existence is verified before any TranscodeAttempt row is created.** When `MediaFile.FilePath` (translated to the local mount via PathTranslation) does not exist on disk, the worker increments `MediaFiles.FFprobeFailureCount`, sets `LastFFprobeError = "Source file missing on disk: ..."`, deletes the TranscodeQueue row, and returns. No noisy attempt history. Stops the dead-file retry loop where queue population kept re-adding rows for files deleted between scan and transcode.

14. **CommandBuilder failures surface in the database with a stack trace.** `Models/CommandBuilder.py` previously had a "pure function should not log" doctrine that swallowed every exception and returned `None`. The downstream "Failed to build command" log carried zero context. The wrappers now call `LogException` with `JobId`/`FilePath` before returning, so the `Logs` table has `ExceptionType`, `ExceptionMessage`, and `StackTrace` for every BuildCommand failure.

### Windows-Native Deploy Automation

15. **`deploy/deploy-windows-worker.py <target-ip>` deploys a Windows worker end-to-end in a single invocation from the dev workstation.** The script wraps the 8-step sequence in `windows-worker.flow.md` ("Deploy Sequence (Quick Reference)"). Verifiable: on a fresh Windows host with only Python 3.12 and OpenSSH Server installed, running the script with no flags produces a `Workers` row with `Status='Online'`, `Platform='windows'`, populated `FFmpegPath`, and a `LastHeartbeat` less than 60 s old, all within 90 s of the script's exit.

16. **Deploy is idempotent.** Re-running `deploy-windows-worker.py` against an already-deployed host completes without error, skips work that has already been done (existing venv, env vars, registered task), and leaves the same final state. Verifiable: two consecutive runs against the same target both exit 0; the second run reports each step as "skipped (already done)" or "verified (no change)" rather than re-doing it.

17. **No credential value appears on a process command line, in the operator's transcript, or on disk in plaintext during deploy.** Credentials are read from Vaultwarden via `infrastructure/terraform/secrets.py`, passed to remote PowerShell via SSH stdin into `-EncodedCommand` blocks, and never logged or echoed. Verifiable: `grep` the script's source for any literal credential value returns zero hits; running the script with `--dry-run` and grepping the captured stdout/stderr for the literal Synology password returns zero hits; `Get-WinEvent` and `ps` on the target during deploy never show the values.

18. **Deploy verification fails the script with a non-zero exit code if the worker does not register within 90 s of triggering the task.** The script polls the `Workers` row after `Start-ScheduledTask` and treats absence-of-row OR `LastHeartbeat` older than 60 s as a deploy failure. Verifiable: pointing the script at a target where Task Scheduler will not fire (e.g., a wrong IP) results in exit code != 0 and a log line naming the verification step that timed out.

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
- [x] 11. Crash-recovery skip-self-PID guard (criterion 11)
- [x] 12. SignalHandler releases DB pool before os._exit (criterion 12)
- [x] 13. Postgres max_connections raised 30 -> 200 on 10.0.0.15 (also needs to land in infrastructure-repo postgresql.conf so a fresh deploy starts at 200 -- pending)
- [x] 14. FFmpeg/FFprobe registration falls back to project bundle, hard-fails on neither (criterion 10)
- [x] 15. Source-file pre-flight check in ProcessJob (criterion 13)
- [x] 16. CommandBuilder loud-failure pattern (criterion 14)
- [ ] 17. Add backplane NIC (10.0.1.42 on vmbr1) for 20 Gbps NFS storage path
- [ ] 18. Persist `max_connections=200` in infrastructure-repo postgresql.conf (so CT 203 rebuild starts at 200)
- [x] 19. `StartWorker.py` + `deploy/Register-WorkerTask.ps1` + `deploy/Bootstrap-WorkerCreds.ps1` shipped (per-host setup pieces; verified on REMINGTON 2026-05-09 — Workers row Online with heartbeating)
- [x] 20. `deploy/deploy-windows-worker.py` written (2026-05-09). Meets criteria 15-18: end-to-end automation in 8 steps, idempotent (auto-skips already-built venv via pre-flight detection, `Register-WorkerTask.ps1` overwrites with `-Force`), no plaintext leak (vault read via importlib + SSH stdin into `-EncodedCommand` blocks), verified Online polling against `Workers` row with 90s timeout. Tested against REMINGTON: full idempotent re-run completes in ~15s with `Workers.Remington: Status=Online, FFmpegPath set, heartbeat 8s old`. Manual verification of criterion 17 needed: outsider should grep the script for literal credential values (returns zero) and inspect a deploy run's stdout/stderr (no values).

NEXT: Apply the backplane NIC (step 17) and persist max_connections (step 18). Windows-deploy automation is feature-complete pending user PASS verification of criterion 17. Flow docs: `deploy/worker-deploy.flow.md` (Linux/Docker) and `deploy/windows-worker.flow.md` (Windows-native).

## Scope

```
deploy/Dockerfile
deploy/docker-compose.yml
deploy/worker-deploy.feature.md
deploy/worker-deploy.flow.md
deploy/windows-worker.flow.md
deploy/deploy-windows-worker.py
deploy/Register-WorkerTask.ps1
deploy/Bootstrap-WorkerCreds.ps1
StartWorker.py
WorkerService/Main.py
Services/FFmpegService.py
```

## Files

- `deploy/Dockerfile` - Multi-stage Docker image build (Linux/Docker path)
- `deploy/docker-compose.yml` - Compose config for building and running workers (Linux/Docker path)
- `deploy/worker-deploy.flow.md` - Build, deploy, and runtime flow doc (Linux/Docker path)
- `deploy/windows-worker.flow.md` - Build, deploy, and runtime flow doc (Windows-native path)
- `deploy/deploy-windows-worker.py` - End-to-end Windows-native deploy automation (criteria 15-18)
- `deploy/Register-WorkerTask.ps1` - Idempotent Task Scheduler registration for the Windows-native worker
- `deploy/Bootstrap-WorkerCreds.ps1` - DPAPI/Credential-Manager hardening for Windows hosts (run from RDP/console only -- cmdkey refuses from SSH)
- `StartWorker.py` - Windows-native launcher: mounts SMB shares in-process, then launches WorkerService\Main.py
- `WorkerService/Main.py` - Unified worker entry point (both platforms)
- `Repositories/DatabaseManager.py` - RegisterWorker(), GetWorkerConfig(), GetWorkerShareMappings()
- `Services/FFmpegService.py` - FFmpeg/FFprobe path resolution (reads per-worker config, then systemsettings, then hardcoded discovery)
- `Core/Database/DatabaseService.py` - PostgreSQL connection pooling (reads MEDIAVORTEX_DB_* env vars)
