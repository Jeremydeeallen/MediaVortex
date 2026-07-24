# Feature: Worker Deploy

**Slug:** worker-deploy

## What It Does

Brings up a new host as a MediaVortex worker. One command per shape, idempotent, fail-loud. An operator who has never deployed a worker before reads `deploy/bringup.md`, picks the shape (LXC-Docker, bare-metal-Docker, bare-metal Linux, or Windows), runs one command, and within five minutes has a `Workers` row in Status='Online' with a fresh heartbeat.

Deploy contract only. Runtime invariants (FFmpeg path, crash recovery, signal handling, source pre-checks) live in `WorkerService/worker-lifecycle.feature.md`.

## Surface

- `deploy/deploy-fleet.py [--hosts <name,...>] [--no-drain]` -- **canonical operator entry.** Drains live workers via `Workers.Status='Paused'`, dispatches each host to its correct backend via `SelectDeployScript(Host)` (compose-template presence -> docker; absence -> baremetal), restarts local I9 WorkerService, restores pre-drain Status, polls `Workers.Version` until fleet matches HEAD. Per-shape scripts below are the internal backends.
- `deploy/deploy-linux-worker.py <target>` -- Docker on Linux backend. Covers LXC hosts (Larry). Refuses if no compose template. Per-host differences come from `inventory.toml`.
- `deploy/deploy-baremetal-worker.py <target>` -- Bare-metal Linux backend, no containers. Covers Intel Arc / Xe workstations (Wakko) and NVIDIA hosts (dot). Refuses if a docker compose template exists for the host (misuse -> fleet script). Installs WorkerService and Python deps directly on the host; systemd unit runs one WorkerService per configured worker slot. Torch variant auto-detected: cu124 (NVIDIA), xpu (Intel Arc), cpu (fallback).
- `deploy/deploy-windows-worker.py <target>` -- Task Scheduler + SMB on Windows (I9-2024).
- **Code updates on I9-2024 (Windows worker)** -- WorkerService runs from the `C:\Code\MediaVortex` source tree; stop + restart to apply changes, no re-deploy needed. Linux-Docker workers require `deploy-linux-worker.py <target>` per change because Docker bakes the source into the container image. Bare-metal Linux workers apply code changes via `deploy-baremetal-worker.py <target>` which rsyncs source + restarts the systemd units.
- `deploy/bringup.md` -- one-page runbook picks the shape and points at the right command.
- `deploy/worker-deploy-{linux,baremetal,windows}.flow.md` -- per-shape flow docs with parity sections.

LXC provisioning (Proxmox `pct create`, NFS mounts, Docker install) is owned by `infrastructure/terraform/mediavortex-workers/`. Bare-metal Docker host bootstrap (`nfs-common` + Docker CE + `/etc/fstab` managed block) is owned by `infrastructure/terraform/mediavortex-bare-metal-bootstrap.py`. Bare-metal Linux host bootstrap (systemd, XPU driver, Level Zero runtime, mounts) is owned by `infrastructure/terraform/mediavortex-baremetal-linux-bootstrap.py`.

The `infrastructure` repo is the **single source of truth** for host inventory and mount specs.

## Success Criteria

### Operator experience

1. **One entry per shape.** `deploy/deploy-linux-worker.py` (Docker), `deploy/deploy-baremetal-worker.py` (bare-metal Linux), and `deploy/deploy-windows-worker.py` exist. Each accepts one positional target with zero required flags.

2. **Five-minute cold bring-up.** On a prerequisites-satisfied host the deploy exits 0 within five minutes and the host has a `Workers` row with `Status IN ('Online', 'Paused')`, non-NULL `FFmpegPath`, `LastHeartbeat` under 60 seconds old, and `MountValidationError IS NULL`.

3. **Ninety-second code-only redeploy.** A second invocation after a code change reaches `Status='Online'` with fresh `LastHeartbeat` under 90 seconds.

4. **Idempotent.** The deploy script converges to the target end-state regardless of prior state. Two consecutive runs both exit 0. **Idempotent means N=1000 -- if any long-lived resource (docker build cache, log files, temp files) grows without bound across runs and can starve future runs, the deploy owns pruning it.** Disk-quota-exceeded from an accumulating docker build cache is a deploy failure, not an operator-maintenance failure.

4a. **Deploy owns disk hygiene.** Every deploy script prunes any long-lived resource it created on the target that would otherwise accumulate. Docker-on-Linux prunes docker build cache + dangling images before build. Bare-metal Linux prunes stale venv caches + apt caches after install. Every deploy pre-flights a minimum-free-space check post-prune and fails loud if the target is still starved (means non-deploy artifacts filled the disk -- operator investigates). Docs/alerts monitor only; never PREVENT starvation. Prevention is the deploy's job.

5. **Pre-flight fails fast.** Missing prerequisites cause non-zero exit within 30 seconds naming the failing check and a one-line remediation hint.

6. **Verification fails the deploy.** No `Workers` row within the bring-up budget, stale `LastHeartbeat`, or pre-Online stuck state exits non-zero and names the failing step. Mount-validation failures surface the offending path.

### Conventions

7. **Worker name convention sourced from inventory.toml.** Multi-worker Linux hosts register as `<friendly>-worker-N` lowercase (`larry-worker-1..8`, `wakko-worker-1..4`, `dot-worker-1..4`). Single-worker Windows hosts register as the inventory `name` value (`I9-2024`). Docker path applies to LXC hosts only; bare-metal hosts use `deploy-baremetal-worker.py`.

8. **No credential leak.** SMB/NFS/DB credentials are read from Vaultwarden via `infrastructure/terraform/secrets.py` and passed via SSH stdin or environment variables. Grep of any deploy script for a literal credential value returns zero hits.

### Documentation

9. **One bring-up runbook.** `deploy/bringup.md` answers "I want to add host X" in fewer than 50 lines: pick shape, check prerequisites, run command, verify.

10. **Three flow docs with parity sections.** Each of `deploy/worker-deploy-{linux,baremetal,windows}.flow.md` contains: Host Inventory, Pre-Flight Checks, Build and Deploy, Post-Deploy Verification, Troubleshooting. Additional shape-specific sections are permitted.

11. **Docs match reality.** Each flow doc's Host Inventory table lists every host currently registered for that shape in the `Workers` table.

### Cleanup

12. **No stale Workers rows.** Any row whose `LastHeartbeat` is older than 1 hour AND whose `WorkerName` does not match the current naming convention is deleted.

13. **I9 file writes never return EINVAL.** FFmpeg invocations on I9-2024 (transcodes + Remux) complete `open()` of the output `.mp4.inprogress` file without intermittent `Invalid argument` failures.

14. **[BUG-0064] Deploy split is clean.**
    - **I9 local services have no deploy path.** WebService + local WorkerService start from their respective venvs. Start command brings WebService online FIRST, then WorkerService, after detecting + stopping any running instance.
    - **Remote-worker deploys are independent.** No fleet orchestration blocks host A on host B's heartbeat.
    - **One entry script per shape.** LXC-Docker, bare-metal-Docker, bare-metal Linux, and Windows-SMB each have their own strategy; no copy-paste between shapes.

### Idempotence + operator state (DOMAIN.md 2026-07-24)

15. **No destructive DELETE on Workers.** No deploy script may execute `DELETE FROM Workers` (or any variant that removes rows for the target host). Deploy MUST preserve operator-owned columns across runs: `Status`, `TranscodeEnabled`, `RemuxEnabled`, `QualityTestEnabled`, `ScanEnabled`, `MaxConcurrentJobs`, `MaxConcurrentQualityTestJobs`, `MaxCpuThreads`, `AcceptsInterlaced`, `ForceDisposition`. Verifiable: `grep -rn 'DELETE FROM Workers' deploy/` returns 0.

16. **No Status coalesce to Online.** No deploy script (or its helpers in `deploy-fleet.py`) may treat missing/NULL `Status` as `Online`. `COALESCE(Status, 'Online')` is forbidden. A missing `Status` for a captured live worker is a fail-loud condition -- the deploy exits non-zero rather than default any operator-owned column. Verifiable: `grep -rn "COALESCE.*Status.*Online" deploy/` returns 0.

17. **Slot claim is atomic against slot INSERT.** `WorkerService/Main.py._ClaimPrefixedWorkerName` reserves the slot by INSERTing the Workers row for the claimed name INSIDE the same advisory-lock scope that computed the slot. The function does not return a claimed name until a Workers row for that name exists in the DB. N concurrent processes starting from a clean state claim N distinct slot numbers, never colliding on `-1`. Verifiable: `Tests/Contract/TestWorkerSlotAtomicClaim.py` spawns N=8 concurrent calls against an empty Workers table and asserts exactly N distinct WorkerName values return.

18. **Deploy scripts UPSERT deploy-owned columns only.** RegisterWorker's ON CONFLICT DO UPDATE clause enumerates ONLY deploy-owned columns (`Platform`, `FFmpegPath`, `FFprobePath`, `ShareMountPrefix`, `MaxCpuThreads`, `Version`, `BuildInfo`, `LastHeartbeat`). Operator-owned columns are absent from the ON CONFLICT UPDATE clause. Verifiable: grep the RegisterWorker SQL for any operator-owned column name in its UPDATE list returns 0.

## Deviation from conventions

- **Criterion 8 (no credential leak)**: `deploy/deploy-windows-worker.py:82-88` contains a literal `MEDIAVORTEX_DB_PASSWORD: "mediavortex"` default. Rationale: per `CLAUDE.md`, the homelab DB password equals the DB name and user; it is not a secret.

## Status

COMPLETE

## Scope

```
deploy/worker-deploy.feature.md
deploy/worker-deploy-linux.flow.md
deploy/worker-deploy-baremetal.flow.md
deploy/worker-deploy-windows.flow.md
deploy/bringup.md
deploy/deploy-linux-worker.py
deploy/deploy-baremetal-worker.py
deploy/deploy-windows-worker.py
deploy/Register-WorkerTask.ps1
deploy/Dockerfile
deploy/compose-templates/larry.yml
deploy/baremetal/
deploy/SyncSource.py
deploy/.deployignore
```

`StartWorker.py`, `WorkerService/Main.py`, `Services/FFmpegService.py`, and worker runtime invariants are owned by `WorkerService/worker-lifecycle.feature.md`.

## Files

- `deploy/worker-deploy.feature.md` -- this doc (operator-experience criteria)
- `deploy/bringup.md` -- one-page runbook covering all shapes (criterion 9)
- `deploy/worker-deploy-linux.flow.md` -- Docker on Linux flow (Larry LXC only)
- `deploy/worker-deploy-baremetal.flow.md` -- Bare-metal Linux flow (Wakko / Intel Arc + dot / NVIDIA / no containers)
- `deploy/worker-deploy-windows.flow.md` -- Task Scheduler + SMB flow (I9-2024)
- `deploy/deploy-linux-worker.py` -- Docker-on-Linux entry
- `deploy/deploy-baremetal-worker.py` -- bare-metal Linux entry
- `deploy/deploy-windows-worker.py` -- Windows entry
- `deploy/Register-WorkerTask.ps1` -- Windows Task Scheduler registration
- `deploy/Dockerfile` -- worker container image (used by Docker-on-Linux hosts only)
- `deploy/compose-templates/<friendly>.yml` -- per-host compose file for Docker-on-Linux hosts
- `deploy/baremetal/` -- systemd unit template + install scripts for bare-metal Linux hosts
- `deploy/SyncSource.py` -- tar-over-ssh source sync with `.deployignore` filtering
- `deploy/.deployignore` -- exclusion patterns for source sync

## References

The `infrastructure` repo (`https://github.com/TheAdroitDBA/infrastructure`) is authoritative for host inventory, mounts, and bootstrap.

- `WorkerService/worker-lifecycle.feature.md` -- runtime invariants the deploy verifies
- `infrastructure/docs/features/linux-worker-deploy.md` -- host-side enrollment (Linux)
- `infrastructure/docs/features/windows-worker-deploy.md` -- host-side enrollment (Windows)
- `infrastructure/terraform/inventory.toml` -- friendly-host to IP + mounts; consumed by every deploy + bootstrap
- `infrastructure/terraform/mediavortex-workers/` -- LXC provisioning for Larry CT 218
- `infrastructure/terraform/mediavortex-bare-metal-bootstrap.py` -- Docker-on-bare-metal prereq bootstrap
- `infrastructure/terraform/mediavortex-baremetal-linux-bootstrap.py` -- bare-metal Linux prereq bootstrap (Intel XPU driver, Level Zero runtime, systemd)
- `infrastructure/terraform/secrets.py` -- Vaultwarden credential access
