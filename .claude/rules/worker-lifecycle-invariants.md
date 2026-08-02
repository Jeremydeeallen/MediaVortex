# Worker Lifecycle Invariants

Durable system properties that must always hold, regardless of how a worker was started, stopped, or crashed. Deploy procedure (`worker-deploy.md`) relies on these. Recovery from unplanned crashes (OOM, power loss, kernel panic, hard kill from outside deploy) also relies on these.

## The invariants

**I1. `ActiveJobs` rows are valid only while the owning process is alive.** WorkerService boot deletes every `ActiveJobs WHERE WorkerName = self` before any capability thread starts. Enforced by `WorkerService.Main._RecoverFromCrash`. Consequence: orphan rows from OOM, power loss, kernel panic, or SIGKILL never survive a boot. Any code that reads `ActiveJobs` can trust the rows correspond to a currently-live process.

**I2. In-flight jobs survive process death.** If a WorkerService process dies mid-encode (crash OR deploy kill), the job's `TranscodeAttempts` row gets marked `Success=FALSE, ErrorMessage='worker crashed/restarted'` by stuck-job detection, the `TranscodeQueue` row returns to `Pending`, and the next claim by any capable worker reclaims it. Death is not job loss; death is job requeue. Note: for PLANNED deploys, `worker-deploy.md` drains first to avoid the waste-and-noise of a mid-encode kill, but the invariant holds regardless.

**I3. `Workers.Version` is derived from the running code tree.** Worker resolves sha at boot in this order: (a) `.git/HEAD` if present at repo root, else (b) `VERSION` file at repo root. Same-host deploys (I9) have `.git/` -- no VERSION stamp needed. Remote deploys (baremetal) don't ship `.git/` (rsync excludes it), so the baremetal sync step stamps `VERSION`. `Workers.Version` is correct on next heartbeat after any boot -- deploy verification is one-shot "did start succeed," not a poll loop.

**I4. Start fails loudly.** Any failure during WorkerService boot (missing env var, missing venv, broken import, DB unreachable during identity registration) crashes with a non-zero exit code BEFORE the heartbeat loop starts. `Start-Process` / `systemctl start` return code IS the verification of a successful boot.

## When this rule applies (PR triggers)

- Adds or edits `WorkerService/Main.py` startup path (I1 + I4 live here).
- Modifies `Workers.Version` write path (I3 lives on the heartbeat writer + boot resolver).
- Adds or edits stuck-job detection or `TranscodeAttempts` finalization on crash (I2 lives here).

## Related

- `.claude/rules/worker-deploy.md` -- the deploy procedure that relies on these invariants.
- `WorkerService/worker-lifecycle.feature.md` C10-C13 -- crash recovery criteria.
- `.claude/rules/claim-authority.md` -- claim + reclaim mechanics.
