# Bring up a new MediaVortex worker

Pick the shape, check prerequisites, run one command, verify.

## 1. Pick the shape

| The host runs... | Use |
|---|---|
| Bare-metal Linux (LXC container, physical Linux workstation) | `deploy-baremetal-worker.py` -- see `worker-deploy-baremetal.flow.md` |

MediaVortex has no remote Windows workers today. I9-2024 runs WebService + WorkerService directly from its live source tree via `StartMediaVortex.py` / `StartWorker.py` -- no deploy step.

## 2. Prerequisites (one-time per host)

The `infrastructure` repo (`https://github.com/TheAdroitDBA/infrastructure`) is the **single source of truth** for host inventory, mount specifications, and bootstrap automation. Edit `infrastructure/terraform/inventory.toml` first; the steps below consume it.

**Bare-metal Linux (larry LXC 218 / wakko / Intel Arc + dot / NVIDIA)** -- host in `inventory.toml`; root SSH; DB reachable on `10.0.0.15:5432`. Run `py infrastructure/terraform/mediavortex-baremetal-linux-bootstrap.py --host <friendly>` first. Installs `nfs-common`, Python 3.12, GPU runtime (Intel Level Zero for Arc, NVIDIA driver for RTX), reconciles `/etc/fstab` from `fstab_mounts`, drops the systemd template unit at `/etc/systemd/system/mediavortex-worker@.service`.

## 3. Run the deploy

```bash
py deploy/deploy-baremetal-worker.py <friendly-or-ip> # Bare-metal Linux
```

The script is idempotent. Re-running updates source and restarts the workers without duplicating `Workers` rows.

## 4. Verify

The script polls `Workers` for up to 90 seconds and exits non-zero on timeout. On success it reports each worker's `Status`, `FFmpegPath`, and `HeartbeatAge`. Expected: `Status IN ('Online', 'Paused')`, non-NULL FFmpegPath, heartbeat < 60s.

## 5. If it fails

The script names the failing check and a one-line remediation hint. Open the flow doc's Troubleshooting section keyed to the symptom.

## References

- Deploy rule (SoT): `.claude/rules/worker-deploy.md`
- Flow: `deploy/worker-deploy-baremetal.flow.md`
- Inventory: `infrastructure/terraform/inventory.toml`
- Vault: `infrastructure/terraform/secrets.py`
- Known issues: `memory/KNOWN-ISSUES.md`
