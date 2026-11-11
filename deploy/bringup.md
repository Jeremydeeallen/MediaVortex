# Bring up a new MediaVortex host

Pick the shape, check prerequisites, run one command, verify. Workers: sections 1-5. The farm server (WebService): section 6.

## 1. Pick the shape

| The host runs... | Use |
|---|---|
| Bare-metal Linux (LXC container, physical Linux workstation) | `deploy-baremetal-worker.py` -- see `worker-deploy-baremetal.flow.md` |
| The WebService (farm server, `mediavortex-server`) | `deploy-server.py` -- section 6 |

MediaVortex has no remote Windows workers today. I9-2024 runs its WorkerService directly from its live source tree via `StartMediaVortex.py` / `StartWorker.py` -- no deploy step. It does not run the WebService.

## 2. Prerequisites (one-time per host)

The `infrastructure` repo (`https://github.com/TheAdroitDBA/infrastructure`) is the **single source of truth** for host inventory, mount specifications, and bootstrap automation. Edit `infrastructure/terraform/inventory.toml` first; the steps below consume it.

**Bare-metal Linux (larry LXC 218 / wakko / Intel Arc + dot / NVIDIA)** -- host in `inventory.toml`; root SSH; DB reachable on `10.0.0.15:5432`. Run `py infrastructure/terraform/mediavortex-bare-metal-bootstrap.py --host <friendly>` first. Installs `nfs-common`, Python 3.12, GPU runtime (Intel Level Zero for Arc, NVIDIA driver for RTX), reconciles `/etc/fstab` from `fstab_mounts`, drops the systemd template unit at `/etc/systemd/system/mediavortex-worker@.service`.

## 3. Run the deploy

```bash
py deploy/deploy-baremetal-worker.py <friendly-or-ip> # Bare-metal Linux
```

The script is idempotent. Re-running updates source and restarts the workers without duplicating `Workers` rows.

## 4. Verify

The script polls `Workers` for up to 90 seconds and exits non-zero on timeout. On success it reports each worker's `Status`, `FFmpegPath`, and `HeartbeatAge`. Expected: `Status IN ('Online', 'Paused')`, non-NULL FFmpegPath, heartbeat < 60s.

## 5. If it fails

The script names the failing check and a one-line remediation hint. Open the flow doc's Troubleshooting section keyed to the symptom.

## 6. The farm server (WebService)

One LXC on larry (`mediavortex-server`, CT 237, `10.0.0.49`, Ubuntu 24.04, same media bind mounts as CT 218) runs the only WebService. It starts at boot (`mediavortex-server.service`, `Restart=always`).

One-time bring-up:

1. Infra row exists in infra-db (`mediavortex-server`) and `inventory.toml` is regenerated. Then `py infrastructure/terraform/server-deploy.py --name mediavortex-server` (creates the CT, DNS, nginx, monitoring, backup).
2. Stop the WebService on I9 (`/Status` -> Stop, or end its process).
3. `py deploy/deploy-server.py` -- first run builds the venv (minutes); every later run with unchanged requirements is seconds.

Every release after that:

```bash
py deploy/deploy-server.py               # ship origin/main (push first)
py deploy/deploy-server.py --rollback    # back to the sha the last OK deploy replaced
py deploy/deploy-server.py --sha <sha>   # a specific commit on origin/main
```

Success prints per-step timings and `== SERVER ON <sha8> (DeployHistory Id=<n>) ==`; `curl http://10.0.0.49:5000/api/Version` shows the same sha. A sha that does not come up is reverted automatically (exit 1). Every run leaves one `DeployHistory` row (`HostsAttempted='mediavortex-server'`). UI: `mediavortex-server.internal.jarremy.xyz` or `http://10.0.0.49:5000`.

A second WebService anywhere else (e.g. `py WebService/Main.py` on I9 with `MEDIAVORTEX_WORKER_NAME` set) refuses to start while the server is heartbeating. Details: `worker-deploy-baremetal.flow.md` ST7, `WebService/single-instance-startup.feature.md`.

## References

- Deploy rule (SoT): `.claude/rules/worker-deploy.md`
- Flow: `deploy/worker-deploy-baremetal.flow.md`
- Inventory: `infrastructure/terraform/inventory.toml`
- Vault: `infrastructure/terraform/secrets.py`
- Known issues: `memory/KNOWN-ISSUES.md`
