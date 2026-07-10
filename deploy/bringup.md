# Bring up a new MediaVortex worker

Pick the shape, check prerequisites, run one command, verify.

## 1. Pick the shape

| The host runs... | Use |
|---|---|
| Linux under Docker (LXC, bare-metal server) | `deploy-linux-worker.py` -- see `worker-deploy-linux.flow.md` |
| Bare-metal Linux, no containers (Intel Arc / Xe workstation) | `deploy-baremetal-worker.py` -- see `worker-deploy-baremetal.flow.md` |
| Windows 10/11 -- native via Task Scheduler | `deploy-windows-worker.py` -- see `worker-deploy-windows.flow.md` |

## 2. Prerequisites (one-time per host)

The `infrastructure` repo (`https://github.com/TheAdroitDBA/infrastructure`) is the **single source of truth** for host inventory, mount specifications, and bootstrap automation. Edit `infrastructure/terraform/inventory.toml` first; the steps below consume it.

**Linux under Docker** -- host in `inventory.toml`; compose template at `deploy/compose-templates/<friendly>.yml`; root SSH from dev workstation; DB reachable on `10.0.0.15:5432`. Bringup by host shape:

- **LXC (Larry CT 218)**: provisioned by `infrastructure/terraform/mediavortex-workers/`, which reads `bind_mounts` from `inventory.toml`. `terraform apply` installs rootfs, mounts, Docker, NFS.
- **Bare-metal Docker server (dot)**: run `py infrastructure/terraform/mediavortex-bare-metal-bootstrap.py --host <friendly>` first. Reads `fstab_mounts` from `inventory.toml` and idempotently installs `nfs-common` + Docker CE, applies the managed-block in `/etc/fstab`, creates `/opt/mediavortex` + mountpoints, runs `mount -a`.

**Bare-metal Linux (Wakko / Intel Arc)** -- host in `inventory.toml`; root SSH; DB reachable on `10.0.0.15:5432`. Run `py infrastructure/terraform/mediavortex-baremetal-linux-bootstrap.py --host <friendly>` first. Installs `nfs-common`, Python 3.12, Intel `libze1` + `libze-intel-gpu1`, VA-API media drivers, reconciles `/etc/fstab` from `fstab_mounts`, drops the systemd template unit at `/etc/systemd/system/mediavortex-worker@.service`.

**Windows** -- see `worker-deploy-windows.flow.md` for the full prereq list (OpenSSH Server, Python 3.12+, SMB credential caching, Vaultwarden references).

## 3. Run the deploy

```bash
py deploy/deploy-linux-worker.py <friendly-or-ip>     # Docker on Linux
py deploy/deploy-baremetal-worker.py <friendly-or-ip> # Bare-metal Linux
py deploy/deploy-windows-worker.py <ip>               # Windows
```

Every script is idempotent. Re-running updates source and restarts the workers without duplicating `Workers` rows.

## 4. Verify

The script polls `Workers` for up to 90 seconds and exits non-zero on timeout. On success it reports each worker's `Status`, `FFmpegPath`, and `HeartbeatAge`. Expected: `Status IN ('Online', 'Paused')`, non-NULL FFmpegPath, heartbeat < 60s.

## 5. If it fails

The script names the failing check and a one-line remediation hint. Open the flow doc's Troubleshooting section keyed to the symptom.

## References

- Contract: `deploy/worker-deploy.feature.md`
- Flows: `deploy/worker-deploy-{linux,baremetal,windows}.flow.md`
- Inventory: `infrastructure/terraform/inventory.toml`
- Vault: `infrastructure/terraform/secrets.py`
- Known issues: `memory/KNOWN-ISSUES.md`
