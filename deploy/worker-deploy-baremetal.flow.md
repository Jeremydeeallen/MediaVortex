# Flow: Bare-Metal Linux Worker Deploy

**Slug:** worker-deploy-baremetal

Deploys the MediaVortex `WorkerService` directly on a bare-metal Linux host with no containers. Intended for Intel Arc / Xe workstations (Wakko) where hardware demucs runs against `torch.xpu`. Runs one systemd unit per configured worker slot, all from a single Python venv on the host.

Counterpart flows:
- `worker-deploy-linux.flow.md` -- Docker on Linux (LXC, bare-metal servers)
- `worker-deploy-windows.flow.md` -- Task Scheduler + SMB (I9-2024)

## Entry Point

```bash
py deploy/deploy-baremetal-worker.py <target>
```

`<target>` is the host's friendly name from `infrastructure/terraform/inventory.toml` (e.g. `wakko`) or its IP. The script reads SSH user, IP, worker count, and torch variant, then runs the pipeline. Idempotent.

## Host Inventory

| Friendly | Hostname | IP | Host Type | CPU | GPU | Workers |
|---|---|---|---|---|---|---|
| wakko | client-b450m-01 | 10.0.0.230 | bare-metal (Linux Mint 22.3 Zena / Ubuntu 24.04 base) | Ryzen 7 3700X, 8C/16T | Intel Arc B580 (Battlemage) | `wakko-worker-1..4` (4 threads each) |

When adding a new bare-metal Linux worker host:

1. Add the host to `infrastructure/terraform/inventory.toml`:
   ```toml
   [[services]]
   name = "<friendly>"
   ssh_user = "root"
   worker_count = 4
   nics = [{ role = "primary", ip = "10.0.0.NNN" }]
   fstab_mounts = [
     { source = "10.0.0.42:/mnt/media_tv", target = "/mnt/media_tv", type = "nfs" },
     { source = "10.0.0.42:/mnt/movies",   target = "/mnt/movies",   type = "nfs" },
     { source = "10.0.0.42:/mnt/xxx",      target = "/mnt/xxx",      type = "nfs" },
   ]
   ```
2. Add a row to the table above.
3. Provision the host: `py infrastructure/terraform/mediavortex-baremetal-linux-bootstrap.py --host <friendly>` (installs `nfs-common`, Python 3.12, Intel `libze1` + `libze-intel-gpu1`, VA-API media drivers, systemd unit template, reconciles `/etc/fstab` from `fstab_mounts`).
4. Run `py deploy/deploy-baremetal-worker.py <friendly>`.

## Pipeline Overview

| ID | Stage | Owns |
|---|---|---|
| ST1 | Pre-Flight Checks | SSH reachability, Python 3.12 presence, DB reachability, mount non-empty, Intel Arc device visible |
| ST2 | Detect torch variant | `nvidia-smi` -> cu124, else `lspci` Intel Arc `[8086:e*xx]` -> xpu, else cpu |
| ST3 | Sync + Install | rsync source to `/opt/mediavortex/src`, create venv at `/opt/mediavortex/host-venv`, install torch wheel from `download.pytorch.org/whl/<variant>` (only exception to requirements.txt rule -- needs variant-specific index-url), then `pip install -r WorkerService/requirements.txt` for every other dep. All non-torch software installs go through requirements.txt; enforced by `Tests/Contract/TestDeployPipInstallsRequirementsTxt.py`. |
| ST4 | Systemd Apply | Render one `mediavortex-worker@<n>.service` per worker slot from template; `systemctl daemon-reload` + `enable` + `restart` |
| ST5 | Post-Deploy Verification | `systemctl is-active` all N units; `Workers` rows Online/Paused; `WorkerShareMappings` populated; version match |
| ST6 | Runtime Pipeline | Per-worker startup -> `WorkerService.flow.md::ST0..ST13` ownership |

## Pre-Flight Checks (`ST1`)

The script runs these in order and exits non-zero on the first failure.

| Check | Command (effectively) | Expected | If it fails |
|---|---|---|---|
| Target resolvable | `inventory.toml` lookup or IP literal | A friendly name or routable IP | Add the host to `inventory.toml`. |
| SSH reachable | `ssh -o ConnectTimeout=5 root@<ip> hostname` | Hostname matches inventory | Check firewall, host is up. |
| Python 3.12 installed | `ssh ... 'python3.12 --version'` | Version string | `py infrastructure/terraform/mediavortex-baremetal-linux-bootstrap.py --host <friendly>` |
| DB reachable from target | `ssh ... 'nc -zw2 10.0.0.15 5432 && echo OK'` | `OK` | Verify postgres on `10.0.0.15`; check pg_hba.conf allows the target IP. |
| Required mounts non-empty | `ssh ... 'ls /mnt/media_tv \| head -1 && ls /mnt/movies \| head -1 && ls /mnt/xxx \| head -1'` | Each returns at least one filename | Re-run `mediavortex-baremetal-linux-bootstrap.py --host <friendly>`. |
| Intel Arc device visible (xpu targets) | `ssh ... 'lspci -nn \| grep -iE "vga\|3d\|display" \| grep -iE "\\[8086:e"'` + `ls /dev/dri/renderD*` | lspci row + at least one renderD device | Verify PCIe seating; kernel `i915`/`xe` driver loaded (`dmesg \| grep -i xe`); install `libze1 libze-intel-gpu1` on host. |

## Detect torch variant (`ST2`)

```python
def _DetectTorchVariant(Target):
    if ssh("nvidia-smi ..."):
        return "cu124"
    if ssh("lspci -nn ... [8086:e"):
        return "xpu"
    return "cpu"
```

Wheels come from `https://download.pytorch.org/whl/<variant>`:
- `cu124` -- CUDA 12.4 build; bundles `nvidia-*` runtime libs.
- `xpu` -- Intel XPU build; bundles `intel-pti` + `intel-sycl-rt` + `intel-cmplr-lib-rt`. Requires host packages `libze1` + `libze-intel-gpu1` (installed by the bootstrap script) to talk to `/dev/dri/renderD*`. No IPEX, no oneAPI apt install.
- `cpu` -- CPU-only fallback.

## Sync + Install (`ST3`)

```bash
# 1. Sync source tree to target
rsync -az --delete --exclude-from=deploy/.deployignore ./ root@<ip>:/opt/mediavortex/src/

# 2. Create / reuse venv (torch pinned via index-url; everything else via requirements.txt)
ssh root@<ip> '
  python3.12 -m venv /opt/mediavortex/host-venv --upgrade-deps
  /opt/mediavortex/host-venv/bin/pip install --index-url https://download.pytorch.org/whl/<variant> torch==2.6.0 torchaudio==2.6.0
  /opt/mediavortex/host-venv/bin/pip install -r /opt/mediavortex/src/WorkerService/requirements.txt
'

# 3. Stamp the deployed SHA into /opt/mediavortex/VERSION
ssh root@<ip> 'echo "<git rev-parse HEAD>" > /opt/mediavortex/VERSION'
```

## Systemd Apply (`ST4`)

Systemd template unit at `/etc/systemd/system/mediavortex-worker@.service`:

```ini
[Unit]
Description=MediaVortex Worker %i
After=network-online.target
Wants=network-online.target
RequiresMountsFor=/mnt/media_tv /mnt/movies /mnt/xxx

[Service]
Type=simple
ExecStart=/opt/mediavortex/host-venv/bin/python -m WorkerService.Main
WorkingDirectory=/opt/mediavortex/src
Environment=MEDIAVORTEX_WORKER_NAME=%l-worker-%i
Environment=MEDIAVORTEX_SHARE_MAPPINGS=T=/mnt/media_tv/,M=/mnt/movies/,Z=/mnt/xxx/
Environment=MEDIAVORTEX_DB_HOST=10.0.0.15
Environment=MEDIAVORTEX_DB_PORT=5432
Environment=MEDIAVORTEX_DB_NAME=mediavortex
Environment=MEDIAVORTEX_DB_USER=mediavortex
Environment=MEDIAVORTEX_DB_PASSWORD=mediavortex
Environment=CPUSET=%i
Restart=on-failure
RestartSec=5s
TimeoutStopSec=30m

[Install]
WantedBy=multi-user.target
```

`%l` = short hostname; `%i` = worker slot index. So `mediavortex-worker@1.service` on host `wakko` produces `MEDIAVORTEX_WORKER_NAME=wakko-worker-1`.

Apply per slot:
```bash
ssh root@<ip> '
  systemctl daemon-reload
  for i in 1 2 3 4; do
    systemctl enable mediavortex-worker@$i.service
    systemctl restart mediavortex-worker@$i.service
  done
'
```

CPU pinning is applied at runtime via `os.sched_setaffinity` inside `WorkerService/Main.py` using the `CPUSET` env var (4 threads per slot on a 16-thread Ryzen 7).

## Post-Deploy Verification (`ST5`)

The script polls the database for up to 90 seconds after the systemd restart. Verification fails the deploy if any of these don't hold within the window.

### 1. Units active

```bash
ssh root@<ip> 'systemctl is-active mediavortex-worker@1 mediavortex-worker@2 mediavortex-worker@3 mediavortex-worker@4'
```

Expected: all `active` -- none `failed`, `activating`, `deactivating`.

### 2. Workers rows present and Online with correct version

```bash
py Scripts/SQLScripts/QueryDatabase.py sql \
  "SELECT WorkerName, Status, FFmpegPath, SUBSTRING(Version,1,7) AS Ver, AGE(NOW(), LastHeartbeat) AS HeartbeatAge
   FROM Workers WHERE WorkerName LIKE '<friendly>-worker-%' ORDER BY WorkerName"
```

Expected per worker:
- `Status IN ('Online','Paused')`
- `FFmpegPath` is NOT NULL and points at a host FFmpeg binary
- `Ver` equals the first 7 chars of `git rev-parse HEAD` on the dev workstation at deploy time
- `HeartbeatAge < 60s`

### 3. Share mappings registered

```bash
py Scripts/SQLScripts/QueryDatabase.py sql \
  "SELECT WorkerName, DriveLetter, LocalPath FROM WorkerShareMappings
   WHERE WorkerName LIKE '<friendly>-worker-%' ORDER BY WorkerName, DriveLetter"
```

Expected: 3 rows per worker (T, M, Z), each pointing at the matching host mount.

### 4. Torch xpu smoke (Intel Arc targets)

```bash
ssh root@<ip> '/opt/mediavortex/host-venv/bin/python -c "
import torch
print(\"torch:\", torch.__version__)
print(\"xpu avail:\", torch.xpu.is_available())
print(\"xpu name:\", torch.xpu.get_device_name(0))
"'
```

Expected: `torch: 2.X.Y+xpu`, `xpu avail: True`, GPU name matches inventory (e.g. `Intel(R) Arc(TM) B580 Graphics`).

### 5. Capabilities loaded

```bash
py Scripts/SQLScripts/QueryDatabase.py sql \
  "SELECT WorkerName, TranscodeEnabled, QualityTestEnabled, ScanEnabled
   FROM Workers WHERE WorkerName LIKE '<friendly>-worker-%' ORDER BY WorkerName"
```

Default for new workers: `TranscodeEnabled=true`, others off. Adjust via Activity UI or direct SQL after verification passes.

## Troubleshooting

### `torch.xpu.is_available()` returns False

Check host `/dev/dri/` visibility and Level Zero loader presence:

```bash
ssh root@<ip> '
  ls -la /dev/dri
  ldconfig -p | grep libze_loader
  dpkg -l | grep -iE "libze1|libze-intel-gpu"
'
```

Expected: `renderD128` (or similar) present; `libze_loader.so.1` in ldconfig; `libze1` + `libze-intel-gpu1` installed. If any missing, run `mediavortex-baremetal-linux-bootstrap.py --host <friendly>` to reconcile.

### Worker registers but FFmpegPath is NULL

Host FFmpeg binary missing or not in venv's PATH. Verify:

```bash
ssh root@<ip> 'which ffmpeg && which ffprobe && ffmpeg -version | head -1'
```

Fix: install FFmpeg on the host (host distro package or download the BtbN static build to `/usr/local/bin/`).

### Worker stuck `Paused`, deploy verification times out

Mount validation failed. Surface the offending mount:

```bash
py Scripts/SQLScripts/QueryDatabase.py sql \
  "SELECT WorkerName, MountValidationError FROM Workers WHERE WorkerName LIKE '<friendly>-worker-%'"
```

Common cause: NFS mount empty (local filesystem showing through). Fix on the host (`mount -a`, check `/etc/fstab`), then `systemctl restart 'mediavortex-worker@*.service'`.

### Systemd unit crash-looping

```bash
ssh root@<ip> 'journalctl -u mediavortex-worker@1.service --no-pager -n 100'
```

Common causes:
- DB unreachable (`psycopg2.OperationalError`) -- check `10.0.0.15:5432`.
- Venv broken -- reinstall: `rm -rf /opt/mediavortex/host-venv && py deploy/deploy-baremetal-worker.py <friendly>`.
- torch xpu wheel mismatch -- delete `/opt/mediavortex/host-venv` and redeploy.

## Failure Modes

| Failure | Symptom | Resolution |
|---|---|---|
| Intel Arc device missing at boot | `torch.xpu.is_available()` False; `/dev/dri/renderD*` absent | Reseat card; check kernel driver (`dmesg \| grep -iE "xe\|i915"`). |
| PyTorch xpu wheel install fails | `pip install torch==*+xpu` returns 403 or timeout | Retry; check `download.pytorch.org/whl/xpu/` availability. |
| DB unreachable at unit start | `psycopg2.OperationalError` in journalctl, unit restarts | Verify `10.0.0.15:5432` is reachable from the target; check `pg_hba.conf`. |
| NFS mount missing on host | FFmpeg writes fail with ENOENT or EACCES | `mount -a`; verify `/etc/fstab`. |
| torch xpu STFT unavailable on new Arc SKU | Demucs runs but exits with `OpenCL error -1` on `torch.stft` | Track Intel's XPU kernel coverage; interim: fall back to CPU demucs per host, or use OpenVINO EP path. |

## Seams

| ID | Transition | Producer (writer) | Wire shape | Consumer (reader) expects | Verification |
|---|---|---|---|---|---|
| S1 | `ST3 -> ST4` (venv install -> systemd apply) | Deploy script rsyncs source + installs wheels + writes `/opt/mediavortex/VERSION` | Filesystem tree under `/opt/mediavortex/` + `VERSION` file | Systemd unit starts, `WorkerService/Main.py` reads `VERSION` at boot | `ssh root@<ip> 'cat /opt/mediavortex/VERSION'` matches dev `git rev-parse HEAD` |
| S2 | `ST5` Workers row check | `WorkerService.flow.md::S1` (worker registration) | `Workers.(WorkerName, Status, FFmpegPath, Version)` | Deploy verification SQL within 90s window | `SELECT Status, FFmpegPath, SUBSTRING(Version,1,7) FROM Workers WHERE WorkerName LIKE '<friendly>-worker-%'` -- Online/Paused, non-NULL FFmpegPath, matching Ver |
| S3 | `ST5` share mappings | `WorkerService.flow.md::S2` (env var -> WorkerShareMappings) | `WorkerShareMappings.(WorkerName, DriveLetter, LocalMountPrefix)` -- 3 rows per worker (T, M, Z) | Used by every read/write of paths inside the process | `SELECT COUNT(*) FROM WorkerShareMappings WHERE WorkerName LIKE '<friendly>-worker-%'` = N_workers * 3 |
| S4 | host mount source-of-truth | Operator writes `infrastructure/terraform/inventory.toml` `fstab_mounts` | TOML config consumed by bare-metal bootstrap script | Systemd `RequiresMountsFor=` and env-var `MEDIAVORTEX_SHARE_MAPPINGS` reference the same paths | Diff systemd unit env against inventory entries -- mount paths match |
| S5 | `ST5 -> ST6` (version assertion) | Deploy script | Exit code 3 if `Workers.Version` (per worker) != stamped SHA from dev HEAD | Operator sees deploy failure; rolls back or retries | Console line `version=<sha7>` on success; exit 3 on mismatch |
| S6 | XPU device -> demucs | Host `/dev/dri/renderD*` + `libze1` + torch xpu wheel | `torch.xpu.is_available() == True`; `torch.xpu.get_device_name(0)` matches inventory GPU | Audio pre-encode pipeline calls `demucs.separate -d xpu` | `ST5` step 4 torch xpu smoke output |

## Runtime Pipeline (per worker) (`ST6`)

The deploy verifies the worker reaches Online. The per-step behavior that produces Online is owned by `WorkerService/worker-lifecycle.feature.md` and `WorkerService/WorkerService.feature.md`:

| Step | Owner doc | What it produces |
|---|---|---|
| DB connect | `WorkerService.feature.md` crit 1, 7 | psycopg2 pool to `10.0.0.15:5432` |
| Worker identity | -- | `WorkerName = MEDIAVORTEX_WORKER_NAME` from systemd env |
| Register worker | `WorkerService.feature.md` crit 9 | UPSERT into `Workers`; FFmpegPath resolved via `_ResolveBundledOrPathBinary` |
| Register share mappings | -- | UPSERT `WorkerShareMappings` from `MEDIAVORTEX_SHARE_MAPPINGS` |
| Mount validation | `worker-lifecycle.feature.md` crit 20, 21 | Each storage mount checked exists, non-empty, not local-fs |
| Load capabilities | `WorkerService.feature.md` crit 1, 2 | TranscodeEnabled / QualityTestEnabled / ScanEnabled / RemuxEnabled read |
| Crash recovery | `worker-lifecycle.feature.md` crit 10-13 | Orphaned ActiveJobs cleaned, `.inprogress` files removed |
| Health loop | -- | Heartbeat every 30s |
| Status poll | `worker-lifecycle.feature.md` crit 1-5 | Online/Paused transitions |
| Capability poll | `WorkerService.feature.md` crit 2 | Capability + concurrency changes within 15s |
