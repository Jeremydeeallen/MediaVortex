---
description: Deploy a MediaVortex WorkerService to a bare-metal Linux host. See deploy/bringup.md for host selection.
argument-hint: <target-host-or-ip>
---

Deploy a MediaVortex worker. Do NOT improvise -- the deploy steps live in the flow doc and have been hardened through real incidents. Follow them.

1. Read `.claude/rules/worker-deploy.md` first. It is the single source of truth for deploy behavior (per-service pause -> drain -> deploy -> back Online, no fleet shortcuts, no --no-drain).

2. If the user said "where do I start?", point them at `deploy/bringup.md` -- the one-page runbook -- before doing anything.

3. Deploy path (bare-metal Linux only -- MediaVortex has no remote Windows workers; I9-2024 runs from its live source tree):

   - Flow doc: `deploy/worker-deploy-baremetal.flow.md`
   - Entry script: `deploy/deploy-baremetal-worker.py <target>` (idempotent; torch variant auto-detected: cu124 / xpu / cpu)
   - Targets today: larry (10.0.0.42, CT 218 LXC, CPU-only), wakko (10.0.0.230, Intel Arc B580), dot (10.0.0.193, NVIDIA RTX 4060).

4. Run the deploy. Stream output so the user sees each step. Do NOT skip verification (poll `Workers` row, confirm `Status IN ('Online','Paused')`, `FFmpegPath` non-NULL, `LastHeartbeat` < 60s, `MountValidationError IS NULL`).

5. If deploy fails, do NOT retry blindly. Read the failing step in the flow doc, identify the cause, and report to the user before attempting any fix.

6. After a successful deploy, report: hostname registered, platform, FFmpeg path resolved, heartbeat age. The user marks PASS.

## Reference

- Bring-up runbook (start here): `deploy/bringup.md`
- Deploy rule (SoT): `.claude/rules/worker-deploy.md`
- Bare-metal Linux flow: `deploy/worker-deploy-baremetal.flow.md`
- Known issues that touch deploy: `memory/KNOWN-ISSUES.md` (search for "path storage", "FFmpeg path")
