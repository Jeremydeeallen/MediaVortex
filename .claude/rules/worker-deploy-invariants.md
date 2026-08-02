# Worker Deploy Invariants

Deploy is: **sync code to target host (if remote) + restart process**. Nothing else. The extra steps deploys used to have (pause, drain-wait, VERSION stamp, verify loop) were compensations for worker-side bugs that no longer exist. Do not re-add them.

## The four domain invariants

**I1. Process kill is safe.** Killing a WorkerService process at any point -- mid-encode, mid-scan, mid-probe -- never loses a job. Killed process's in-flight work returns to `Pending` via the next boot's crash-recovery + stuck-job detection cycle. Consequence: drain-before-kill is not required.

**I2. `ActiveJobs` rows are valid only while the owning process is alive.** WorkerService boot deletes every `ActiveJobs WHERE WorkerName = self` before any capability thread starts. Enforced by `WorkerService.Main._RecoverFromCrash`. Consequence: orphan `ActiveJobs` rows never survive a boot. Drain-wait against `ActiveJobs` count cannot deadlock.

**I3. `Workers.Version` is derived from the running code tree.** Worker resolves sha at boot in this order: (a) `.git/HEAD` if present at repo root, else (b) `VERSION` file at repo root. Same-host deploys (I9) have `.git/` available -- no stamp step needed. Remote deploys (baremetal) don't ship `.git/` (rsync excludes it), so the baremetal sync step stamps `VERSION`. Deploy shape follows: same-host = kill+start; remote = sync (with stamp) + kill+start. Consequence: `Workers.Version` is always correct on next heartbeat; deploy does not need a poll-until-heartbeat verification loop.

**I4. Start fails loudly.** Any failure during WorkerService boot (missing env var, missing venv, broken import) crashes with a non-zero exit code before the heartbeat loop starts. Consequence: `Start-Process` / `systemctl start` return code IS the verification. Deploy does not need a poll-until-heartbeat loop; if the start returned success, the worker is running.

## Deploy shape (two verbs)

- **`sync-host <hostname>`** -- rsync the source tree to a remote host, install deps if fingerprint changed. Same-host (I9) target: no-op. Executed once per host regardless of how many worker instances live on that host.
- **`restart-worker <workername>`** -- stop the process, start the process. Windows-local uses `Stop-Process` + `Start-Process pythonw`. Linux uses `systemctl restart mediavortex-worker@N`. No pause, no drain-wait, no verify loop, no VERSION stamp, no DB writes.

Fleet deploy is: sync-host once per host in parallel, restart-worker once per worker in parallel. Composition, not orchestration.

## Forbidden

- **Restoring drain-wait, pause-before-kill, VERSION stamp, or verify loops.** Every one of those compensates for a broken invariant. If a real bug makes them seem necessary again, fix the invariant, don't re-add the compensation.
- **Making Windows and Linux deploy paths diverge in shape.** Sync mechanism differs (no-op vs rsync); restart mechanism differs (Stop-Process vs systemctl); shape does not.
- **DB writes from deploy.** Deploy does not touch `Workers.Status`, `ActiveJobs`, or any other row. The worker manages its own state.

## When this rule applies (PR triggers)

- Adds or edits any script under `deploy/`.
- Adds or edits `WorkerService/Main.py` startup path (invariant I2 lives here).
- Modifies `Workers.Version` write path (invariant I3 lives on the heartbeat writer).
- Adds a CLI flag to a deploy script.

## Related

- `WorkerService/worker-lifecycle.feature.md` C10-C13 -- crash recovery = kill recovery (same path); ActiveJobs sweep is the invariant.
- `deploy/worker-deploy.feature.md` -- the two-verb deploy shape.
- `.claude/rules/claim-authority.md` -- claim invariants that make I1 possible (SKIP LOCKED reclaim after kill).
