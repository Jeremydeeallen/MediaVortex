# Worker Deploy Drain (Golden Standard)

Every worker service deploy follows the same shape. No opt-out, no batch shortcuts.

## The five decisions

- **D1.** After worker code is complete: commit + push.
- **D2.** Deploy per-service independently. Services do not wait on each other.
- **D3.** Every service treated identically.
- **D4.** Per-service sequence: pause -> drain -> deploy -> back Online (drained means no more active jobs).
- **D5.** Only DB touch is `Workers.Status` (pause via existing pause feature; set Online after deploy). No other DB writes for the worker.

## Definitions

**Service** = one row in `Workers`. `larry-worker-1` and `larry-worker-2` are two independent services on one docker host; each drained + deployed + brought back Online individually. Sharing a container image is a build-time concern; runtime treatment is per-service.

**Drained** =
- `Workers.Status = 'Paused'` AND
- `SELECT COUNT(*) FROM ActiveJobs WHERE WorkerName = <name>` = 0 AND
- `SELECT COUNT(*) FROM ScanJobs WHERE WorkerName = <name> AND Status IN ('Pending','Running','Stopping')` = 0

Deploy proceeds only after all three conditions hold.

## Forbidden

- `--no-drain`, `--skip-drain`, `--force`, or any flag that bypasses the drain step.
- Batch-pausing every worker on a host and deploying the host as one atomic unit.
- Killing a worker container / process while `ActiveJobs` or Running `ScanJobs` remain for it.
- Any DB write to a `Workers` row other than `Status` during deploy.
- Restarting a live worker without first flipping to `Paused` and observing drain.

## When this rule applies (PR triggers)

- Adds or edits any script under `deploy/`.
- Adds or edits any `*deploy*.feature.md` / `*deploy*.flow.md`.
- Adds a CLI flag to any deploy script.
- Modifies any code that writes to `Workers` from an infrastructure/deploy context.

## Enforcement

Judgment gate at review + contract test `Tests/Contract/TestDeployPerWorkerDrain.py` (greps for opt-out flags, checks the rule file exists, verifies doc language).
