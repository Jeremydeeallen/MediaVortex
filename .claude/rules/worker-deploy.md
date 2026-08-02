# Worker Deploy

The single source of truth for how MediaVortex code reaches the workers. Operator invokes `py deploy/deploy-fleet.py` (no arguments). Every Enabled worker gets the new code in parallel; each worker is independent of every other worker.

## Domain rules

Set by the operator (2026-08-02); do NOT re-derive.

1. **Drain lives in the code, not the operator's head.** Every worker deploy pauses, waits for in-flight work to complete, then restarts. Operator does not check "is anyone busy" before firing. Mid-encode kills leave `.inprogress` files + noise + wasted encode time -- not acceptable for planned deploys.
2. **Per-worker independence.** Worker A's drain does not block worker B's restart, and worker B's return to Online. No cross-worker or cross-host barriers. Wakko workers restart the moment wakko sync finishes; larry's slow sync does not block them.
3. **Zero-parameter fleet script.** `py deploy/deploy-fleet.py` deploys every Enabled worker in parallel. No flags to opt out, override, or narrow. Selective per-worker use is available via `py deploy/deploy-worker.py <WorkerName>` for operator recovery.
4. **Parallel rollout.** Once code is tested and ready, all workers roll out concurrently. Fleet wall time is bounded by the slowest-draining single worker, not the sum.

## Baremetal on-disk layout

```
/opt/mediavortex/
  src-<sha_current>/                    <-- rsync target for current deploy
  src-<sha_prior>/                      <-- older; draining workers still cwd'd here
  host-venv-<fp_current>/               <-- per-fingerprint venv (installed if fingerprint changed)
  host-venv-<fp_prior>/                 <-- older; draining workers still bound here
  src-legacy-<YYYYMMDD-HHMMSS>/         <-- one-time migration artifact (never GC'd)
  host-venv-legacy-<YYYYMMDD-HHMMSS>/   <-- one-time migration artifact (never GC'd)
/etc/systemd/system/mediavortex-worker@.service   <-- fully-resolved paths, rendered per deploy
/etc/mediavortex/instance-<N>.env                 <-- MEDIAVORTEX_WORKER_NAME=<friendly>-worker-<N>
/etc/mediavortex/worker.env                       <-- DB credentials, bootstrapped once
```

**Invariants:**

- `rsync` only ever writes to a NEW `src-<sha>` dir. Never touches existing dirs.
- New `host-venv-<fp>` only when deps fingerprint changed. Same-fp reuse skips reinstall.
- Systemd unit rewritten per deploy with resolved absolute paths pointing at `src-<sha_current>` + `host-venv-<fp_current>`. Draining worker's running process is bound to whatever the unit said at its exec time; symlink swaps do not affect a running process's argv.
- `systemctl daemon-reload` happens once per deploy. Running workers' argv is frozen; only next `systemctl restart` picks up new unit config.
- GC keeps last 5 versioned `src-*` and last 5 versioned `host-venv-*`. Legacy dirs (`-legacy-*`) never GC'd.
- Migration: one-time detection of pre-versioned real dirs at `/opt/mediavortex/src` and `/opt/mediavortex/host-venv`, renamed to `-legacy-<timestamp>`. Idempotent.

**Zero mixed-state risk:** draining worker's `cwd` = `src-<old_sha>` (real path, not symlink). Its Python binary = `host-venv-<old_fp>/bin/python` (bound by `execve` at start). Rsync of new code writes to a different dir. New venv install writes to a different dir. Lazy imports resolve to old dir. Restart picks up new dir. Never both simultaneously.

## Windows-local (I9-2024)

Single worker + WebService, both from `C:\Code\MediaVortex` git tree. Drain-then-restart is sufficient (no cross-worker contention on same host). No versioning needed. Worker reads sha from `.git/HEAD` at boot (`worker-lifecycle-invariants.md` I3).

## Per-worker deploy pipeline (5 steps)

Same shape for baremetal and windows-local; only step 3 mechanism differs.

1. **Pause** -- `UPDATE Workers SET Status='Paused' WHERE WorkerName=<self>`.
2. **Drain-wait** -- poll every 5s until `ActiveJobs WHERE WorkerName=<self>` == 0 AND `ScanJobs WHERE WorkerName=<self> AND Status IN ('Pending','Running','Stopping')` == 0. No hard timeout; drain is the contract.
3. **Kill** -- hard kill is safe here (drain confirmed idle). Baremetal: `systemctl kill -s TERM <unit>`. Windows-local: `psutil.Process.terminate()`.
4. **Start** -- baremetal: `systemctl start <unit>`. Windows-local: `subprocess.Popen(pythonw, WorkerService/Main.py)` + `Popen(pythonw, WebService/Main.py)`. Return code = verification (`worker-lifecycle-invariants.md` I4).
5. **Online** -- `UPDATE Workers SET Status='Online'` if worker was Online before deploy; otherwise leave Paused.

## Fleet orchestration

`deploy/deploy-fleet.py` shape (see the code for the exact ThreadPoolExecutor pattern):

- One `ThreadPoolExecutor` sized to `remote_host_count + enabled_worker_count`.
- Per remote host: one Future runs `deploy-baremetal-worker.py <host>` (rsync + venv + unit render + GC).
- Per Enabled worker: one Future gates on ITS host's sync Future (or `None` for windows-local), then runs `deploy-worker.py <WorkerName>` subprocess.
- Windows-local workers have no host-sync dependency; their Future runs immediately.
- `DeployHistory` row inserted at fleet-script entry, updated at exit.

## Forbidden

- **`--no-drain`, `--skip-drain`, `--force`, `--include-stale`, or any flag on any deploy script that bypasses drain or narrows the target set.** Fleet script is zero-parameter by design.
- **Making Windows and Linux deploy paths diverge in shape.** Same 5-step per-worker pipeline both places; only the kill+start mechanism differs.
- **`DELETE FROM Workers`** in any deploy script. Deploy preserves operator-owned columns across runs (`Status`, `TranscodeEnabled`, `RemuxEnabled`, `QualityTestEnabled`, `ScanEnabled`, `ProbeEnabled`, `LanguageEnabled`, `MaxConcurrentJobs`, `MaxConcurrentQualityTestJobs`, `MaxCpuThreads`, `AcceptsInterlaced`, `ForceDisposition`).
- **`COALESCE(Status, 'Online')`** in any deploy script. Missing `Status` on a captured live worker is fail-loud (deploy exits non-zero rather than default an operator-owned column).
- **Mutating `src-<sha>` or `host-venv-<fp>` after initial creation.** Every deploy writes to a NEW versioned dir. Draining workers must be able to trust that their startup version's files have not changed.
- **Rendering the systemd unit template with symlink paths.** Unit's `WorkingDirectory` + `ExecStart` MUST be fully-resolved versioned paths. Symlinks between versions would let daemon-reload affect running (draining) processes' path resolution.

## Idempotence + hygiene

- **Idempotent.** N consecutive fleet deploys converge to the same end state. Includes N=1000 -- long-lived resources (torch caches, apt caches, versioned dirs) must not grow without bound. GC caps versioned-dir count at 5.
- **Deploy owns disk hygiene.** Every deploy script prunes what it created. Pre-flight fails loud if the target is still starved after prune (means non-deploy artifacts filled the disk; operator investigates).
- **No credential leak.** SMB/NFS/DB credentials read from Vaultwarden via `infrastructure/terraform/secrets.py` and passed via SSH stdin or environment variables. Homelab DB password equals DB name equals DB user; documented in CLAUDE.md, not a secret.

## Worker identity

`WorkerName` is deploy-assigned via `MEDIAVORTEX_WORKER_NAME` env var. Baremetal: systemd `EnvironmentFile=/etc/mediavortex/instance-%i.env` writes one file per systemd instance. Windows-local: `deploy-worker.py`'s `_SpawnDetached` sets the env var in the child's process environment. `WorkerService.Main._ResolveWorkerName` fails loud if the env var is unset.

Per-worker concurrency (`Workers.MaxConcurrentJobs`) is DB-enforced at claim time via `Core.Database.WorkerCapabilityPredicate.BuildInflightCapPredicate`. A second process accidentally sharing a WorkerName cannot exceed the cap because the DB refuses the second concurrent claim.

## DeployHistory audit

Every fleet-script invocation writes one row to `DeployHistory`:

- `StartedAt`, `CompletedAt`, `PriorSha`, `NewSha`, `ElapsedSeconds`
- `HostsAttempted` (CSV of worker names), `HostsSucceeded` (CSV)
- `Outcome` = `RUNNING` (in progress) / `OK` / `PARTIAL` / `FAILED`
- `ErrorMessage` (nullable)

Row INSERTed at fleet-script entry; UPDATEd at exit. Partial runs stay `Outcome='RUNNING'` with `CompletedAt IS NULL` until the next fleet-start's cleanup pass sweeps them to `Outcome='KILLED'`.

## When this rule applies (PR triggers)

- Adds or edits any script under `deploy/`.
- Adds or edits `WorkerService/Main.py` startup path (I1-I4 in `worker-lifecycle-invariants.md` live here).
- Modifies systemd unit rendering.

## Related

- `.claude/rules/worker-lifecycle-invariants.md` -- durable system properties (ActiveJobs lifetime, Version resolution, fail-loud start, in-flight job survives process death).
- `WorkerService/worker-lifecycle.feature.md` -- worker startup + crash recovery contract.
- `.claude/rules/claim-authority.md` -- claim + reclaim invariants that make crash-safe restart possible.
