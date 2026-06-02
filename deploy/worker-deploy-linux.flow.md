# Flow: Linux Worker Deploy (Docker)

**Slug:** worker-deploy-linux

Deploys a MediaVortex `WorkerService` container fleet to any Linux host -- LXC (Larry) or bare-metal (Wakko, dot). Same pipeline; per-host differences (hostnames, cpuset) live in `deploy/compose-templates/<name>.yml`. Counterpart to `worker-deploy-windows.flow.md` (Task Scheduler + SMB on Windows).

## Entry Point

```bash
py deploy/deploy-linux-worker.py <target>
```

`<target>` is the host's friendly name from `infrastructure/terraform/inventory.toml` (e.g. `larry`, `wakko`, `dot`) or its IP. The script reads SSH user, IP, and the matching compose template, then runs the four-step pipeline. Idempotent.

## Host Inventory

| Friendly | Hostname | IP | Host Type | CPU | Workers | Compose template |
|---|---|---|---|---|---|---|
| larry | mediavortex-workers (CT 218) | 10.0.0.42 | LXC on Proxmox larry | 2x Xeon, 64 threads | `larry-worker-1..4` (16 threads each) | `compose-templates/larry.yml` |
| wakko | client-b450m-01 | 10.0.0.230 | bare-metal (Linux Mint 22.3) | Ryzen 7 3700X, 8C/16T | `wakko-worker-1..4` (4 threads each) | `compose-templates/wakko.yml` |
| dot | client-z490v-01 | 10.0.0.193 | bare-metal | i9-10850K, 10C/20T | `dot-worker-1..4` (5 threads each) | `compose-templates/dot.yml` |

When adding a new Linux worker host:
1. Add the host to `infrastructure/terraform/inventory.toml` (friendly name, hostname, primary IP, ssh_user). Mount specifications live in the same entry: `bind_mounts` for LXC, `fstab_mounts` for bare-metal. **`inventory.toml` is the single source of truth -- never hardcode mount paths in compose templates or scripts.**
2. Create `deploy/compose-templates/<friendly>.yml` -- copy a similar host's template, adjust hostnames (`<friendly>-worker-N`) and cpuset.
3. Add a row to the table above.
4. Provision the host:
   - **LXC**: `terraform -chdir=infrastructure/terraform/mediavortex-workers apply` (reads `bind_mounts` via `inventory-query.py`).
   - **Bare-metal**: `py infrastructure/terraform/mediavortex-bare-metal-bootstrap.py --host <friendly>` (idempotent: installs `nfs-common` + Docker CE, reconciles `/etc/fstab` managed block from `fstab_mounts`, creates `/opt/mediavortex` + mountpoints, runs `mount -a`).
5. Run `py deploy/deploy-linux-worker.py <friendly>`.

## Pipeline Overview

| ID | Stage | Owns |
|---|---|---|
| ST1 | Pre-Flight Checks | SSH reachability, Docker presence, DB reachability, mount non-empty, compose template existence |
| ST2 | Build and Deploy | SyncSource -> `docker build --build-arg COMMIT_SHA=...` -> `docker compose up -d` -> cleanup |
| ST3 | Post-Deploy Verification | Containers Up; `Workers` rows Online/Paused; `WorkerShareMappings` populated; version match assertion |
| ST4 | Runtime Pipeline | Per-container startup -> `WorkerService.flow.md::ST0..ST13` ownership |

## Pre-Flight Checks (`ST1`)

The script runs these in order and exits non-zero on the first failure. Each check has a remediation hint in the failure message.

| Check | Command (effectively) | Expected | If it fails |
|---|---|---|---|
| Target resolvable | `inventory.toml` lookup or IP literal | A friendly name or routable IP | Add the host to `inventory.toml`. |
| SSH reachable | `ssh -o ConnectTimeout=5 root@<ip> hostname` | Hostname matches inventory | Check `_netdev`, firewall, host is up. |
| Docker installed | `ssh ... 'docker --version'` | Version string | LXC: `terraform apply` in `infrastructure/terraform/mediavortex-workers/`. Bare-metal: `py infrastructure/terraform/mediavortex-bare-metal-bootstrap.py --host <friendly>`. |
| DB reachable from target | `ssh ... 'nc -zw2 10.0.0.15 5432 && echo OK'` | `OK` | Verify postgres on `10.0.0.15`; check pg_hba.conf allows the target IP. |
| Required mounts non-empty | `ssh ... 'ls /mnt/media_tv \| head -1 && ls /mnt/movies \| head -1 && ls /mnt/xxx \| head -1'` | Each returns at least one filename | LXC: `terraform apply` re-renders the `pct set --mp<N>` lines from `inventory.toml`. Bare-metal: re-run `mediavortex-bare-metal-bootstrap.py --host <friendly>`. If `inventory.toml` is correct but the host hasn't picked it up, that's the script to run. Per `memory/KNOWN-ISSUES.md` mount-validation entry: an empty mount is treated as a failure to avoid silent corruption. |
| Compose template exists | `ls deploy/compose-templates/<friendly>.yml` | File present | Create the template from a sibling. |

## Build and Deploy (`ST2`)

Four steps. All happen via SSH from the dev workstation. The script streams output of each step.

```bash
# 1. Sync source tree to target (tar-over-ssh, filtered by .deployignore)
py deploy/SyncSource.py root@<ip> /tmp/mediavortex-build

# 2. Build the worker image on the target
ssh root@<ip> 'docker build \
    --build-arg COMMIT_SHA=$(git -C /c/Code/MediaVortex rev-parse HEAD) \
    -t mediavortex-worker:latest \
    -f /tmp/mediavortex-build/deploy/Dockerfile /tmp/mediavortex-build/'

# 3. Push the per-host compose file and start workers
scp deploy/compose-templates/<friendly>.yml root@<ip>:/opt/mediavortex/docker-compose.yml
ssh root@<ip> 'cd /opt/mediavortex && docker compose up -d'

# 4. Clean up build source
ssh root@<ip> 'rm -rf /tmp/mediavortex-build'
```

For LXC hosts (Larry): `/opt/mediavortex/` already exists -- Terraform created it during host provisioning. For bare-metal: the script creates it on first run.

For code-only redeploys: same four steps. The FFmpeg static download is cached in a Docker build layer; only the `COPY . /app` layer rebuilds. Total time on a warm host: ~30-60 seconds.

## Post-Deploy Verification (`ST3`)

The script polls the database for up to 90 seconds after step 3. Verification fails the deploy if any of these don't hold within the window.

### 1. Containers running

```bash
ssh root@<ip> 'docker ps --format "{{.Names}}\t{{.Status}}"'
```

Expected: N containers, all `Up`, none `Restarting`.

### 2. Workers rows present and Online with correct version

```bash
py Scripts/SQLScripts/QueryDatabase.py sql \
  "SELECT WorkerName, Status, FFmpegPath, SUBSTRING(Version,1,7) AS Ver, AGE(NOW(), LastHeartbeat) AS HeartbeatAge
   FROM Workers WHERE WorkerName LIKE '<friendly>-worker-%' ORDER BY WorkerName"
```

Expected per worker:
- `Status IN ('Online','Paused')` (Paused preserved by UPSERT if the row was previously paused)
- `FFmpegPath` is NOT NULL and ends in `/usr/local/bin/ffmpeg`
- `Ver` equals the first 7 chars of `git rev-parse HEAD` on the dev workstation at deploy time
- `HeartbeatAge < 60s`

The deploy script asserts the Ver match automatically; mismatch fails the deploy with exit code 3. The post-deploy line `version=<sha7>` reports the value alongside heartbeat age.

### 3. Share mappings registered

```bash
py Scripts/SQLScripts/QueryDatabase.py sql \
  "SELECT WorkerName, DriveLetter, LocalPath FROM WorkerShareMappings
   WHERE WorkerName LIKE '<friendly>-worker-%' ORDER BY WorkerName, DriveLetter"
```

Expected: 3 rows per worker (T, M, Z), each pointing at the matching bind mount.

### 4. Capabilities loaded

```bash
py Scripts/SQLScripts/QueryDatabase.py sql \
  "SELECT WorkerName, TranscodeEnabled, QualityTestEnabled, ScanEnabled
   FROM Workers WHERE WorkerName LIKE '<friendly>-worker-%' ORDER BY WorkerName"
```

Default for new workers: `TranscodeEnabled=true`, others off. Adjust via Activity UI or direct SQL after verification passes.

### 5. First job claimed (optional)

If the queue has eligible Pending work, expect a job claimed within 30-90 s of containers coming Up. Not required for deploy success.

## Troubleshooting

### Worker registers but FFmpegPath is NULL

The Dockerfile's FFmpeg download stage failed or the binary was not copied to the final stage. Reproduce inside the container:

```bash
ssh root@<ip> 'docker exec <friendly>-worker-1 ls -la /usr/local/bin/ffmpeg /usr/local/bin/ffprobe'
ssh root@<ip> 'docker logs <friendly>-worker-1 2>&1 | grep -i "ffmpeg\|resolve\|RuntimeError" | tail -20'
```

Fix: rebuild the image. If the BtbN download URL is stale, check `github.com/BtbN/FFmpeg-Builds/releases` for the current `latest` tag.

### Worker stuck `Paused`, deploy verification times out

Mount validation failed. The worker stays Paused and surfaces the offending mount via `Workers.MountValidationError`.

```bash
py Scripts/SQLScripts/QueryDatabase.py sql \
  "SELECT WorkerName, MountValidationError FROM Workers WHERE WorkerName LIKE '<friendly>-worker-%'"
```

Common cause: the NFS mount exists but is empty (local filesystem showing through). Fix the mount on the host (`mount -a`, check `/etc/fstab`), then `docker compose restart` on the target.

### Container crash-looping

```bash
ssh root@<ip> 'docker inspect <friendly>-worker-1 --format "{{.State.ExitCode}} {{.RestartCount}}"'
ssh root@<ip> 'docker logs --tail 50 <friendly>-worker-1'
```

Common causes:
- DB unreachable (`psycopg2.OperationalError`) -- check `10.0.0.15:5432` from the target.
- Connection slots exhausted -- check `pg_stat_activity` on the DB host.
- Python import error -- rebuild image with `--no-cache`.

### Share mappings not registering

```bash
ssh root@<ip> 'docker exec <friendly>-worker-1 printenv MEDIAVORTEX_SHARE_MAPPINGS'
```

Expected: `T=/mnt/media_tv/,M=/mnt/movies/,Z=/mnt/xxx/`. If empty or wrong, fix `deploy/compose-templates/<friendly>.yml` and redeploy.

### Path errors during transcode

```bash
py Scripts/SQLScripts/QueryDatabase.py sql \
  "SELECT FilePath FROM TranscodeQueue WHERE ClaimedBy = '<friendly>-worker-1' ORDER BY DateStarted DESC LIMIT 1"
ssh root@<ip> 'docker exec <friendly>-worker-1 ls -la "/mnt/media_tv/<relative-path>"'
```

Common causes:
- Bind mount missing in compose
- NFS export not mounted on the host (`ls /mnt/media_tv` returns empty from the host itself)
- File deleted between queue population and transcode claim (handled by source-file pre-check; queue row deleted, MediaFile bumped)

## Failure Modes

| Failure | Symptom | Resolution |
|---|---|---|
| AppArmor blocks Docker build (LXC) | `unable to apply apparmor profile` during any `RUN` | The host setup must `apt-get purge -y apparmor` so Docker detects AppArmor as unavailable. Re-run host provisioning. |
| BtbN download fails during build | Dockerfile stage 1 exits non-zero | Retry; the URL occasionally rotates. Check the current `latest` tag at `github.com/BtbN/FFmpeg-Builds/releases`. |
| DB unreachable at container start | `psycopg2.OperationalError` in logs, container restarts | Verify `10.0.0.15:5432` is reachable from the target; check `pg_hba.conf` for the target's IP. |
| Bind mount missing on host | FFmpeg writes fail with ENOENT or EACCES | Verify mount points exist and contain data: `ls /mnt/media_tv /mnt/movies /mnt/xxx` on the target. |
| Stale worker rows from prior naming | Old `client-XXX-NN` rows linger after a rename to friendly naming | Delete the stale rows: `DELETE FROM Workers WHERE WorkerName IN (...) AND LastHeartbeat < NOW() - INTERVAL '1 hour'`. |
| Empty mount silently corrupts state | Worker claims jobs, hits per-file source-missing, deletes queue rows | Fixed by mount validation (worker-lifecycle criteria 20, 21). A worker now stays Paused and reports the offending mount. |

## Seams

| ID | Transition | Producer (writer) | Wire shape | Consumer (reader) expects | Verification |
|---|---|---|---|---|---|
| S1 | `ST2 -> ST3` (build -> running container) | `docker build --build-arg COMMIT_SHA=<dev HEAD>` + `docker compose up -d` | Docker image `mediavortex-worker:latest` with `/opt/mediavortex/VERSION` baked in by the Dockerfile | Container starts -> `WorkerService.flow.md::ST2` reads `VERSION` and UPSERTs `Workers.Version` | `ssh root@<ip> 'docker run --rm --entrypoint cat mediavortex-worker:latest /opt/mediavortex/VERSION'` matches dev `git rev-parse HEAD` |
| S2 | `ST3` Workers row check | `WorkerService.flow.md::S1` (worker registration) | `Workers.(WorkerName, Status, FFmpegPath, Version)` | Deploy verification SQL within 90s window | `SELECT Status, FFmpegPath, SUBSTRING(Version,1,7) FROM Workers WHERE WorkerName LIKE '<friendly>-worker-%'` -- Online/Paused, non-NULL FFmpegPath, matching Ver |
| S3 | `ST3` share mappings | `WorkerService.flow.md::S2` (env var -> WorkerShareMappings) | `WorkerShareMappings.(WorkerName, DriveLetter, LocalMountPrefix)` -- 3 rows per worker (T, M, Z) | Used by every read/write of paths inside the container | `SELECT COUNT(*) FROM WorkerShareMappings WHERE WorkerName LIKE '<friendly>-worker-%'` = N_workers * 3 |
| S4 | host mount source-of-truth | Operator writes `infrastructure/terraform/inventory.toml` `bind_mounts` / `fstab_mounts` | TOML config consumed by Terraform module + bare-metal bootstrap script | Compose templates render mount points from inventory; never hardcoded | Diff `deploy/compose-templates/<friendly>.yml` against inventory entries -- mount paths match |
| S5 | `ST3 -> ST4` (version assertion) | Deploy script | exit code 3 if `Workers.Version` (per worker) != stamped SHA from dev HEAD | Operator sees deploy failure; rolls back or retries | Console line `version=<sha7>` on success; exit 3 on mismatch |

## Runtime Pipeline (per container) (`ST4`)

The deploy verifies the worker reaches Online. The per-step behavior that produces Online is owned by `WorkerService/worker-lifecycle.feature.md` and `WorkerService/WorkerService.feature.md`:

| Step | Owner doc | What it produces |
|---|---|---|
| DB connect | `WorkerService.feature.md` crit 1, 7 | psycopg2 pool to `10.0.0.15:5432` |
| Worker identity | -- | `WorkerName = socket.gethostname()` from compose `hostname:` |
| Register worker | `WorkerService.feature.md` crit 9 | UPSERT into `Workers`; FFmpegPath resolved via `_ResolveBundledOrPathBinary` |
| Register share mappings | -- | UPSERT `WorkerShareMappings` from `MEDIAVORTEX_SHARE_MAPPINGS` |
| Mount validation | `worker-lifecycle.feature.md` crit 20, 21 | Each storage mount checked exists, non-empty, not local-fs |
| Load capabilities | `WorkerService.feature.md` crit 1, 2 | TranscodeEnabled / QualityTestEnabled / ScanEnabled / RemuxEnabled read |
| Crash recovery | `worker-lifecycle.feature.md` crit 10-13 | Orphaned ActiveJobs cleaned, `.inprogress` files removed |
| Health loop | -- | Heartbeat every 30s |
| Status poll | `worker-lifecycle.feature.md` crit 1-5 | Online/Paused transitions |
| Capability poll | `WorkerService.feature.md` crit 2 | Capability + concurrency changes within 15s |
