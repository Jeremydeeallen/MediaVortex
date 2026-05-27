# Bring up a new MediaVortex worker

Pick the OS family, check prerequisites, run one command, verify.

## 1. Pick the OS family

| The host runs... | Use |
|---|---|
| Linux (LXC or bare-metal) -- Docker available | `deploy-linux-worker.py` -- see `worker-deploy-linux.flow.md` |
| Windows 10/11 -- native via Task Scheduler | `deploy-windows-worker.py` -- see `worker-deploy-windows.flow.md` |

## 2. Prerequisites (one-time per host)

The `infrastructure` repo (`https://github.com/TheAdroitDBA/infrastructure`) is the **single source of truth** for host inventory, mount specifications, and bootstrap automation. Edit `infrastructure/terraform/inventory.toml` first; the steps below consume it.

**Linux** -- host in `infrastructure/terraform/inventory.toml`; compose template at `deploy/compose-templates/<friendly>.yml`; root SSH from dev workstation; DB reachable on `10.0.0.15:5432`. Bringup splits by host shape:

- **LXC (Larry CT 218)**: provisioned by `infrastructure/terraform/mediavortex-workers/`, which reads `bind_mounts` from `inventory.toml` via `infrastructure/terraform/inventory-query.py`. `terraform apply` installs everything (rootfs, mounts, Docker, NFS).
- **Bare-metal (wakko, dot)**: run `py infrastructure/terraform/mediavortex-bare-metal-bootstrap.py --host <friendly>` first. The bootstrap reads `fstab_mounts` from `inventory.toml` and idempotently installs `nfs-common` + Docker CE, applies the managed-block in `/etc/fstab`, creates `/opt/mediavortex` + every mountpoint, and runs `mount -a`. Re-running is a no-op.

After the host-shape step, `/mnt/{media_tv,movies,xxx}` are mounted, Docker is installed, and `deploy-linux-worker.py` will pass pre-flight.

**Windows** -- see `worker-deploy-windows.flow.md` "Pre-Flight Checks" and "Storage Path Resolutions" for the full prereq list (OpenSSH Server, Python 3.12+, SMB credential caching, Vaultwarden references). That doc is the operational source of truth -- no Windows-specific values are duplicated here.

## 3. Run the deploy

```bash
# Dry-run the pre-flight before touching the host:
py deploy/deploy-linux-worker.py <target> --check     # Linux
py deploy/deploy-windows-worker.py <ip> --check       # Windows

# Then deploy:
py deploy/deploy-linux-worker.py <friendly-or-ip>
py deploy/deploy-windows-worker.py <ip>
```

Both scripts are idempotent. Re-running updates source and recreates containers / restarts the scheduled task without duplicating Workers rows.

## 4. Verify

The script polls `Workers` for up to 90 seconds and exits non-zero on timeout. On success it reports each worker's `Status`, `FFmpegPath`, and `HeartbeatAge`. Expected: `Status IN ('Online', 'Paused')`, non-NULL FFmpegPath, heartbeat < 60s. Paused on redeploy is normal -- promote via Activity UI when ready.

## 5. If it fails

The script names the failing check and a one-line remediation hint. Don't retry blindly -- open the flow doc's Troubleshooting section keyed to the symptom.

## References

- Contract: `deploy/worker-deploy.feature.md`
- Flows: `deploy/worker-deploy-{linux,windows}.flow.md`
- Inventory: `infrastructure/terraform/inventory.toml`
- Vault: `infrastructure/terraform/secrets.py`
- Known issues: `KNOWN-ISSUES.md`
