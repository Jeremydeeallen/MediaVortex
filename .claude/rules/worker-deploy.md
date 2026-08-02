# Worker Deploy

The procedure for deploying new code to a worker. Domain rule set by the operator (2026-08-02): worker deploys drain in-flight work before killing the process. Mid-encode kills are not acceptable during a planned deploy -- they leave `.inprogress` files on disk, waste encode work, and generate `worker crashed/restarted` attempt-row noise the operator has to triage. `worker-lifecycle-invariants.md` I1 (ActiveJobs boot cleanup) is a safety net for genuine crashes only, NOT a substitute for graceful drain during a planned restart.

## Deploy shape (5 steps, same for baremetal and windows-local)

1. **Pause** -- `UPDATE Workers SET Status='Paused' WHERE WorkerName=self`.
2. **Drain-wait** -- poll every 5s until `COUNT(*) FROM ActiveJobs WHERE WorkerName=self` == 0 AND `COUNT(*) FROM ScanJobs WHERE WorkerName=self AND Status IN ('Pending','Running','Stopping')` == 0. No max timeout -- drain is the contract, honor it.
3. **Kill** -- hard kill is fine here (drain confirmed idle). `Stop-Process` (windows-local) or `systemctl kill -s KILL` (baremetal).
4. **Start** -- `pythonw` (windows-local) or `systemctl start` (baremetal). Return code is the verification (`worker-lifecycle-invariants.md` I3).
5. **Online** -- `UPDATE Workers SET Status='Online'` only if worker was Online before deploy.

## Fleet deploy

Two phases:

- **STEP 1 -- per-host source sync.** rsync the source tree to each remote host in parallel, install deps if fingerprint changed. Windows-local target: no-op. Executed once per host regardless of how many worker instances that host runs.
- **STEP 2 -- per-worker restart.** Every worker's 5-step deploy runs in parallel. Wall time is bounded by the slowest-draining worker, not the sum.

## Forbidden

- **`--no-drain`, `--skip-drain`, `--force`, or any flag that bypasses drain.** Kill-mid-encode is not allowed for planned deploys. If a machine is truly hung and drain can't complete, that is a separate incident -- fix the hang or take the host down manually. Do NOT paper over it with a deploy flag.
- **Making Windows and Linux deploy paths diverge in shape.** Same 5 steps both places; only the kill and start mechanisms differ.
- **Deploying past a failed drain.** If drain won't complete for a worker, that worker's deploy fails cleanly. Other workers continue. Operator investigates.

## When this rule applies (PR triggers)

- Adds or edits any script under `deploy/`.
- Adds a CLI flag to a deploy script.

## Related

- `.claude/rules/worker-lifecycle-invariants.md` -- durable system properties (ActiveJobs lifetime, Version resolution, fail-loud start).
- `WorkerService/worker-lifecycle.feature.md` -- worker startup + crash recovery.
- `.claude/rules/claim-authority.md` -- claim invariants.
