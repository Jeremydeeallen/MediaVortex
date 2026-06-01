# Graceful Drain on Shutdown + Deploy

**Slug:** graceful-drain

## What It Does

Replaces the prior "kill mid-flight FFmpeg subprocesses on SIGTERM" behavior with a graceful drain across the three shutdown paths a worker can encounter:

- **Operator flips `Workers.Status` to a non-Online value** -- `_CapabilityPollingLoop` already calls `_StopAllCapabilities()` which signals each running operation to stop at its next safe boundary and waits via `ProcessingThread.join(timeout=7200)`.
- **Operating system / docker compose sends SIGTERM** -- `SignalHandler` now runs the same `_StopAllCapabilities()` path and polls until every capability handle clears (or 30-minute budget exceeded). FFmpeg subprocesses are NOT killed -- they finish their encode.
- **`deploy/deploy-fleet.py` restarts workers** -- script flips `Workers.Status='Paused'` on every target worker FIRST, waits for `ActiveJobs` to clear per worker (30-minute budget), THEN runs the deploy. After deploy, restores pre-deploy Status. `--no-drain` flag for emergency-immediate behavior.

## Surface

- Operator runs `py deploy/deploy-fleet.py` -- safe to run while workers are mid-encode. Console shows per-worker `[DRAINED]` markers as in-flight work completes.
- Operator can drain a single worker via SQL: `UPDATE Workers SET Status='Paused' WHERE WorkerName='larry-worker-1';`. The capability-polling loop on that worker observes the change within `SystemSettings.CapabilityPollingIntervalSec` (default 15s) and drains via `_StopAllCapabilities`.
- Operator sending Ctrl+C twice to a WorkerService console forces immediate exit (re-entry guard in SignalHandler).

## Success Criteria

1. SIGTERM to a WorkerService with an in-flight transcode / VMAF / remux / scan does NOT kill the FFmpeg subprocess. The encode completes naturally; the worker exits cleanly after.
2. `docker compose recreate` (the primary path the linux deploy script uses) waits up to the compose-template's `stop_grace_period` (30 min) before SIGKILLing. SignalHandler's 30-min drain budget fits inside this.
3. `py deploy/deploy-fleet.py` runs `DrainWorkers` BEFORE the per-host deploy. Each target worker is flipped to `Status='Paused'`, then polled for ActiveJobs to clear. Workers that finish drain are deployed; workers that exceed the 30-min budget cause a warning and the deploy proceeds anyway (operator-visible).
4. After deploy completes, every worker's `Status` is restored to its pre-drain value. Workers that were already Paused before drain stay Paused.
5. `--no-drain` skips DrainWorkers entirely and falls through to the prior immediate-restart behavior. Used only when in-flight work is acceptable to lose (e.g. corrupted-image deploy that needs to land now).
6. `OrphanCleanupService._SweepOrphanedQualityTestProgress` deletes any `QualityTestProgress` row whose owning `QualityTestingQueue` entry is no longer in Pending/Running, OR which has been `Status='Processing'` with no `UpdatedAt` change for >30 minutes. Prevents the UI "Currently Testing" panel from displaying zombie rows after a worker crash, drain timeout, or VMAF-loop exit that does not clear its own progress record.

## Status

PHASE 1 COMPLETE 2026-05-30 (commit `d57bdb6`). Live verification pending the next operator-initiated deploy.

## Scope

```
WorkerService/Main.py                              -- SignalHandler graceful drain
deploy/compose-templates/larry.yml                 -- stop_grace_period: 30m
deploy/compose-templates/dot.yml                   -- stop_grace_period: 30m
deploy/compose-templates/wakko.yml                 -- stop_grace_period: 30m
deploy/deploy-fleet.py                             -- DrainWorkers / RestoreWorkerStatus
Features/ServiceControl/graceful-drain.feature.md  -- this file
```

## Why this exists

Today's deploy SIGKILLed an in-flight VMAF on larry (Westworld S01E02 attempt 26133). The pattern repeats on every deploy or container restart: any operation mid-encode is lost. The DB-flag-flip path was already graceful via `_StopAllCapabilities` (defaults to 2-hour join timeout); SIGTERM bypassed it. This feature aligns SIGTERM + deploy paths with the already-graceful DB-flag path.

## Why drain time is 30 minutes

A typical 1080p NVENC AV1 encode at our `nv_cq32_sink` config runs ~1.5 minutes wall on I9; a longer libsvtav1 preset 6 software encode on Larry runs 5-15 minutes per source; VMAF on a 25-minute source runs 6-8 minutes wall on Larry. 30 minutes covers the long-form tail (a 4K source through preset 4 SVT could push 25 minutes). Configurable via `_SIGNAL_BUDGET_SECONDS` in `WorkerService/Main.py` if the workload changes.

## Related to P6

This is P6 Phase 1. Phase 2-N expand the same pattern: inventory remaining long-running operations (scan walks at sub-directory granularity, archive sweeps, orphan-cleanup loops) to make sure each one observes the stop signal at safe boundaries. Tracker: `.claude/programs/db-authority-program.md` P6.
