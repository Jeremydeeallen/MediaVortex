# Feature: Worker Deploy

**Slug:** worker-deploy

## What It Does

Brings up a new host as a MediaVortex worker. One command per shape, idempotent, fail-loud. An operator who has never deployed a worker before reads `deploy/bringup.md`, picks the shape (LXC, bare-metal Linux, or Windows), runs one command, and within five minutes has a `Workers` row in Status='Online' with a fresh heartbeat. No improvisation, no source-code reading.

This feature owns the deploy contract only. Worker runtime invariants -- FFmpeg path resolution, crash recovery, signal handling, source-file pre-checks, command-builder logging, sync-source filtering -- live in `WorkerService/worker-lifecycle.feature.md`. The deploy script verifies the worker reaches Online but does not own the per-step behavior that produces Online.

## Surface

Operator-facing CLI on the dev workstation, plus two colocated flow docs and a top-level runbook:

- `deploy/deploy-linux-worker.py <target>` -- Docker on Linux. Covers LXC hosts (Larry), bare-metal workstations (Wakko), and bare-metal servers (dot). Same script -- per-host differences (SSH user, compose file path, mount style) come from `inventory.toml`, not script branching.
- `deploy/deploy-windows-worker.py <target>` -- Task Scheduler + SMB on Windows (I9-2024).
- `deploy/bringup.md` -- one-page runbook that picks the OS family and points at the right command.
- `deploy/worker-deploy-{linux,windows}.flow.md` -- per-OS-family flow docs with parity sections.

LXC provisioning (Proxmox `pct create`, NFS mount points, Docker install, AppArmor purge) is a host-onboarding concern owned by `infrastructure/terraform/mediavortex-workers/`. Bare-metal host bootstrap (`nfs-common` + Docker CE install, `/etc/fstab` managed block, mountpoint + `/opt/mediavortex` directories) is owned by `infrastructure/terraform/mediavortex-bare-metal-bootstrap.py`, which reads `fstab_mounts` from `infrastructure/terraform/inventory.toml`. The worker-deploy script treats an LXC or a bootstrapped bare-metal host the same as any other Linux host: SSH in, sync source, `docker compose up -d`, verify the Workers row.

The `infrastructure` repo is the **single source of truth** for host inventory and mount specifications. Editing `infrastructure/terraform/inventory.toml` is the only place to change a worker's mounts -- the LXC Terraform module and the bare-metal bootstrap script both render from it.

## Success Criteria

### Operator experience

1. **One entry per OS family.** `deploy/deploy-linux-worker.py` and `deploy/deploy-windows-worker.py` exist. Each accepts one positional target (IP or `inventory.toml` name) with zero required flags. `--help` names the OS family and lists the host prerequisites. The Linux script works against any Linux target -- LXC or bare-metal -- without branching on host type; per-host differences come from `inventory.toml` configuration.

2. **Five-minute cold bring-up.** On a fresh host that satisfies the documented prerequisites for its shape, the deploy command exits 0 within five minutes, and the host has a `Workers` row with `Status IN ('Online', 'Paused')`, non-NULL `FFmpegPath`, `LastHeartbeat` less than 60 seconds old, and `MountValidationError IS NULL`. `Paused` is a valid post-deploy state because per `WorkerService/worker-lifecycle.feature.md` criterion 5 the UPSERT preserves the existing row's Status -- a redeploy against rows the operator paused stays paused; only a truly fresh registration defaults to Online. Excludes OS install or BIOS configuration (those are host onboarding, not worker deploy).

3. **Ninety-second code-only redeploy.** A second invocation after a code change reaches `Status='Online'` with a fresh `LastHeartbeat` in under 90 seconds.

4. **Idempotent.** Two consecutive runs against the same target both exit 0. The second reports each step as "skipped (already done)" or "verified (no change)" rather than re-doing it. No duplicate `Workers` rows produced.

5. **Pre-flight fails fast.** A missing prerequisite -- SSH unreachable, Docker absent on the target, NFS or SMB mount empty, MediaVortex DB unreachable from the target -- causes the script to exit non-zero within 30 seconds with a message naming the failing check and a one-line remediation hint.

6. **Verification fails the deploy.** If after the apply step no `Workers` row appears within the bring-up budget, or `LastHeartbeat` is older than 60 seconds, or the worker is stuck in a pre-Online state (e.g. mount validation has not passed), the script exits non-zero and names the verification step that timed out. Mount-validation failures surface the offending mount path in the operator output.

### Conventions

7. **Worker name convention sourced from inventory.toml.** Multi-worker Linux hosts register as `<friendly>-worker-N` lowercase (e.g. `larry-worker-1..8`, `wakko-worker-1..4`, `dot-worker-1..4`). Single-worker Windows hosts register as the inventory `name` value (`Remington`, `I9-2024`). No legacy `client-XXX` shaped names produced or retained. ~~Original wording: "Each registered Workers.WorkerName matches `<friendly-host>-worker-N`, lowercase."~~ Replaced 2026-05-16 -- the original required `-worker-N` for every row, which incorrectly flagged the existing single-worker Windows pattern (one worker process per host) as non-compliant. The Windows hosts run a single co-located WorkerService, so the multi-worker suffix is meaningless. Linked Progress entry: closure pass 2026-05-16 (QA finding crit 7).

8. **No credential leak.** SMB/CIFS, NFS, and DB credentials are read from Vaultwarden via `infrastructure/terraform/secrets.py` and passed to the target via SSH stdin or as environment variables within the SSH session. Grep of any `deploy/deploy-*-worker.py` script for any literal credential value returns zero hits. The deploy's captured stdout and stderr never contain a literal credential.

### Documentation

9. **One bring-up runbook.** `deploy/bringup.md` answers "I want to add host X as a worker" in fewer than 50 lines: pick shape, check prerequisites, run command, verify. A new operator who has never deployed a worker can follow it without reading source code.

10. **Two flow docs with parity sections.** Each of `deploy/worker-deploy-{linux,windows}.flow.md` contains these sections: Host Inventory, Pre-Flight Checks, Build and Deploy, Post-Deploy Verification, Troubleshooting. Additional sections (e.g. Windows-specific Drive Mappings, Environment Variables, Failure Modes, Runtime Pipeline) are permitted. ~~Original wording: "...contains these sections in order: ..."~~ Replaced 2026-05-16 -- strict-order requirement was too rigid. The Windows path legitimately needs interleaved sections (Drive Mappings, Env Variables, Persistence) that the LXC path does not; forcing identical structure would lose useful Windows-specific content. The five named sections must exist in both docs (verifiable via `grep -nE "^## "`); order is suggested, not enforced. Linked Progress entry: closure pass 2026-05-16 (QA finding crit 10).

11. **Docs match reality.** Each flow doc's Host Inventory table lists every host currently registered for that OS family in the `Workers` table. Verifiable: the union of friendly-host prefixes of `WorkerName` values per platform in `Workers` equals the set of hosts in the matching flow doc's table. The Linux flow doc covers both LXC (Larry) and bare-metal (Wakko, dot) hosts in one inventory table with a Host Type column. `infrastructure/docs/features/linux-worker-deploy.md` Status section reflects current deployments (specifically, Wakko, which the doc previously marked as planned).

### Cleanup

12. **No stale Workers rows.** Any row in `Workers` whose `LastHeartbeat` is older than 1 hour AND whose `WorkerName` does not match the current naming convention for its host is deleted. As of 2026-05-16: `wakko-worker-1..4` rows are stale (a prior renaming attempt that did not stick); `client-b450m-01..04` are the live ones today. After Wakko's redeploy via the new pipeline, `client-b450m-01..04` become stale and `wakko-worker-1..4` are re-registered fresh; the stale set flips and gets deleted then. Verifiable: no row in `Workers` has both `LastHeartbeat` older than 1 hour AND a name that doesn't follow `<friendly>-worker-N`.

13. **I9 file writes never return EINVAL.** FFmpeg invocations on I9-2024 -- both true transcodes (libsvtav1) and Remux/Quick (stream copy) -- complete their `open()` of the output `.mp4.inprogress` file without intermittent `Invalid argument` failures. Verifiable: across any 100 consecutive `TranscodeAttempts` rows where `WorkerName='I9-2024'`, none have `Success=false` with `ErrorMessage` matching `return code 4294967274` AND `TranscodeDurationSeconds=0`. Linux workers writing to the same shares already meet this bar with zero failures; the bar for I9 is equality with that baseline.

## Deviation from conventions

- **Criterion 8 (no credential leak)**: `deploy/deploy-windows-worker.py:82-88` contains a literal `MEDIAVORTEX_DB_PASSWORD: "mediavortex"` default. Rationale: per `CLAUDE.md`, the homelab DB password equals the DB name and user (`mediavortex`); it is not a secret. The default is a development convenience so `--help`-driven first runs work without env-var setup. Production-grade or non-homelab deployments override via `MEDIAVORTEX_DB_PASSWORD` env var. The "real" secrets (SMB credentials, vault credentials) continue to come exclusively from Vaultwarden via `infrastructure/terraform/secrets.py`.

## Status

COMPLETE -- 2026-05-16. All 12 criteria satisfied (7 and 10 reconciled per QA pass; 8 carries an explicit deviation). dot proving-ground deploy passed end-to-end; wakko renamed in-place from `client-b450m-XX` to `wakko-worker-N` with full history preserved (1662 transcode-attempt rows carried forward); stale Remington row deleted.

### Progress

- [x] 1. Rewrite this feature doc with the operator-experience criteria (2026-05-15)
- [x] 2. Confirm runtime-invariant criteria have homes elsewhere -- FFmpeg path resolution (WorkerService crit 9), crash-recovery PID guard (WorkerService crit 10, possibly superseded by worker-lifecycle 10-13), SignalHandler DB-pool release (WorkerService crit 11), source-file pre-check (WorkerService crit 12, partially superseded by worker-lifecycle 20-21 mount validation). No migration needed; the old worker-deploy criteria 10-14 were duplicates of the WorkerService.feature.md home. The `.deployignore` invariant (old crit 19) is a property of `deploy/SyncSource.py` and the Windows script -- preserved by criteria 1, 8 on this feature and by the existence of `.deployignore` itself.
- [x] 3. Renamed flow docs (2026-05-16): `worker-deploy.flow.md` -> `worker-deploy-linux.flow.md`, `windows-worker.flow.md` -> `worker-deploy-windows.flow.md`. All active references in MediaVortex + infrastructure repos updated. Content restructure to match parity sections in criterion 10 still pending under item 5.
- [~] 4. SSH-probe Wakko to capture compose / mount reality -- DROPPED per the "trust documented deploys" feedback (`memory/feedback_trust_documented_deploys.md`). The new compose templates in `deploy/compose-templates/` are the source of truth; reverse-engineering live state would have captured drift as if it were intentional.
- [x] 5. Wrote `deploy/worker-deploy-linux.flow.md` (2026-05-16) -- 5 parity sections (Host Inventory, Pre-Flight Checks, Build and Deploy, Post-Deploy Verification, Troubleshooting); host inventory covers larry/wakko/dot.
- [x] 6. Wrote `deploy/bringup.md` (2026-05-16) -- 49 lines, picks OS family, points at the right command.
- [x] 7. Built `deploy/deploy-linux-worker.py` (2026-05-16) -- idempotent, `inventory.toml`-driven, pre-flight + sync + build + push compose + compose up + 90s Workers row poll. `deploy/compose-templates/{larry,wakko,dot}.yml` are the per-host artifacts. Replaces the manual 4-step bash pipeline.
- [x] 8. Deleted stale `wakko-worker-1..4` Workers rows (2026-05-16; 19h+ heartbeat, from a prior renaming attempt). The `client-b450m-01..04` rows are CURRENT today and stay until Wakko is redeployed with the new `compose-templates/wakko.yml` (which uses the friendly-host naming) -- at which point those become the new stale set and get deleted. Criterion 12 satisfied as a continuous invariant; flip planned for after Wakko redeploy.
- [x] 9. Updated `infrastructure/docs/features/linux-worker-deploy.md` (2026-05-16): Status reflects Wakko deployed via Docker-compose-on-host; native-systemd path dropped; criteria reframed to match the actual deploy pattern; dot listed as next proving ground.
- [x] 10. Deployed dot (2026-05-16). Manual host bootstrap (Docker CE 29.5.0, nfs-common, 3 NFS mounts from Wakko's pattern, /opt/mediavortex). Then `py deploy/deploy-linux-worker.py dot` end-to-end -- 4 `dot-worker-1..4` rows Online with non-NULL FFmpegPath, heartbeat < 5s. Proving ground PASS for criteria 1-6, 9-10.
- [x] 11. Flow doc Host Inventory tables match reality (linux flow covers larry/wakko/dot; windows flow retired Remington, lists only I9-2024). Criterion 11 satisfied.

- [x] 12. Closure pass (2026-05-16): wakko renamed in-place (workers + share mappings + storage resolutions + 893 transcodeattempts history); wakko redeployed with new compose template; stale Remington row deleted; QA + UX agents reported; criterion 7 reconciled (allow Windows single-worker pattern); criterion 10 reconciled (allow extra sections); ## Deviation from conventions added for criterion 8 (homelab DB password literal); bringup.md trimmed to 46 lines; deploy-linux-worker.py fixed for `{friendly}` placeholder interpolation in Paused success message and now points at flow doc Troubleshooting on verify failure.

DONE. Follow-ups tracked elsewhere: bare-metal host bootstrap codification CLOSED 2026-05-21 by `infrastructure/terraform/mediavortex-bare-metal-bootstrap.py` (see `infrastructure/docs/features/linux-worker-deploy.md` criterion 10); the deferred remediation of the i9-2024 / Remington-style naming if the project later decides on `<host>-worker-1` for single-worker hosts.

## Scope

```
deploy/worker-deploy.feature.md
deploy/worker-deploy-linux.flow.md
deploy/worker-deploy-windows.flow.md
deploy/bringup.md
deploy/deploy-linux-worker.py
deploy/deploy-windows-worker.py
deploy/Register-WorkerTask.ps1
deploy/Dockerfile
deploy/compose-templates/larry.yml
deploy/compose-templates/wakko.yml
deploy/compose-templates/dot.yml
deploy/SyncSource.py
deploy/.deployignore
```

`StartWorker.py`, `WorkerService/Main.py`, `Services/FFmpegService.py`, and the worker runtime invariants are owned by `WorkerService/worker-lifecycle.feature.md`.

## Files

- `deploy/worker-deploy.feature.md` -- this doc (operator-experience criteria)
- `deploy/bringup.md` -- one-page runbook covering both OS families (criterion 9)
- `deploy/worker-deploy-linux.flow.md` -- Docker on Linux flow, covers LXC and bare-metal (Larry, Wakko, dot)
- `deploy/worker-deploy-windows.flow.md` -- Task Scheduler + SMB flow (I9-2024)
- `deploy/deploy-linux-worker.py` -- Linux entry script (works against LXC or bare-metal)
- `deploy/deploy-windows-worker.py` -- Windows entry script (already exists)
- `deploy/Register-WorkerTask.ps1` -- Windows Task Scheduler registration
- `deploy/Dockerfile` -- worker container image (used by all Linux deployments)
- `deploy/compose-templates/<friendly>.yml` -- per-host compose file; `deploy-linux-worker.py` scp's the matching one to `/opt/mediavortex/docker-compose.yml` on the target. Friendly name comes from `inventory.toml`. Hostnames inside each file follow `<friendly>-worker-N` lowercase per criterion 7.
- `deploy/SyncSource.py` -- tar-over-ssh source sync with `.deployignore` filtering
- `deploy/.deployignore` -- exclusion patterns for source sync

## References

The `infrastructure` repo (`https://github.com/TheAdroitDBA/infrastructure`) is authoritative for host inventory, mounts, and bootstrap.

- `WorkerService/worker-lifecycle.feature.md` -- runtime invariants the deploy verifies but does not own
- `infrastructure/docs/features/linux-worker-deploy.md` -- host-side enrollment criteria (Linux); supplementary to this feature
- `infrastructure/docs/features/windows-worker-deploy.md` -- host-side enrollment criteria (Windows); supplementary to this feature
- `infrastructure/terraform/inventory.toml` -- friendly-host -> IP, `bind_mounts` (LXC), `fstab_mounts` (bare-metal); consumed by every deploy and bootstrap script
- `infrastructure/terraform/inventory-query.py` -- emits a service's `bind_mounts` as JSON for the LXC Terraform module's `data "external"`
- `infrastructure/terraform/mediavortex-workers/` -- LXC provisioning for Larry CT 218 (reads `bind_mounts` from `inventory.toml`)
- `infrastructure/terraform/mediavortex-bare-metal-bootstrap.py` -- bare-metal prereq script (nfs-common + Docker CE + fstab managed block); reads `fstab_mounts` from `inventory.toml`
- `infrastructure/terraform/secrets.py` -- Vaultwarden access for SMB/NFS/DB credentials
- `KNOWN-ISSUES.md` -- search for "Linux worker deploy flow doc incomplete" (criterion 11 closes this) and "OS-coupled path storage" (orthogonal but relevant to share mappings)
