---
description: Deploy a MediaVortex WorkerService. Two scripts -- one for bare-metal Linux (all Linux hosts) and one for Windows (Task Scheduler + SMB). See deploy/bringup.md for shape selection.
argument-hint: <baremetal|windows> <target-host-or-ip>
---

Deploy a MediaVortex worker. Do NOT improvise -- the deploy steps live in the flow docs and have been hardened through real incidents. Follow them.

1. Read `deploy/worker-deploy.feature.md` first. It is the single source of truth for the operator-experience criteria (one entry per OS family, 5-minute cold bring-up, idempotent, fail-loud, no credential leaks).

2. If the user said "where do I start?" or did not specify a shape, point them at `deploy/bringup.md` -- the one-page runbook -- before doing anything.

3. Pick the deploy path based on `$ARGUMENTS`:

   - **`baremetal`** (native systemd + host venv on Linux — physical hosts AND LXC containers):
     - Flow doc: `deploy/worker-deploy-baremetal.flow.md`
     - Entry script: `deploy/deploy-baremetal-worker.py <target>` (idempotent; torch variant auto-detected: cu124 / xpu / cpu)
     - Targets today: larry (10.0.0.42, CT 218 LXC, CPU-only), wakko (10.0.0.230, Intel Arc B580), dot (10.0.0.193, NVIDIA RTX 4060).

   - **`windows`** (native, Task Scheduler):
     - Flow doc: `deploy/worker-deploy-windows.flow.md` (covers prerequisites, SMB credential caching, storage path resolutions, and troubleshooting)
     - Entry script: `deploy/deploy-windows-worker.py <target>` (idempotent)
     - Targets today: I9-2024

4. If the user did not specify a shape, ask before doing anything.

5. Run the deploy. Stream output so the user sees each step. Do NOT skip verification (poll `Workers` row, confirm `Status IN ('Online','Paused')`, `FFmpegPath` non-NULL, `LastHeartbeat` < 60s, `MountValidationError IS NULL`).

6. If deploy fails, do NOT retry blindly. Read the failing step in the flow doc, identify the cause, and report to the user before attempting any fix.

7. After a successful deploy, report: hostname registered, platform, FFmpeg path resolved, heartbeat age. The user marks PASS.

## Reference

- Bring-up runbook (start here): `deploy/bringup.md`
- Feature doc (success criteria, status, progress): `deploy/worker-deploy.feature.md`
- Bare-metal Linux flow: `deploy/worker-deploy-baremetal.flow.md`
- Windows flow: `deploy/worker-deploy-windows.flow.md`
- Known issues that touch deploy: `memory/KNOWN-ISSUES.md` (search for "path storage", "FFmpeg path")
