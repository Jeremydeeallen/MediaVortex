# Claim Authority

Every TranscodeAttempts row has exactly one owner. Only that owner writes to it. The DB enforces the "one in-flight attempt per MediaFileId" invariant with a partial UNIQUE index. There is exactly one sanctioned cross-worker terminal write path -- the abandonment sweeper -- and it runs on heartbeat expiration, not on peer opinion.

## The invariant

```
CREATE UNIQUE INDEX ta_one_inflight_per_mfid
  ON TranscodeAttempts (MediaFileId)
  WHERE Success IS NULL;
```

Two in-flight attempts for the same MediaFileId is physically impossible. If any code path (present or future) tries to INSERT a second Success-NULL row for a MediaFileId that already has one, the DB refuses. Callers catch `IntegrityError`, roll back their claim, pick the next queue row.

Migration: `Scripts/SQLScripts/AddSingleInflightAttemptInvariant_2026_07_11.py`. Idempotent (`CREATE UNIQUE INDEX IF NOT EXISTS`).

## The claim (atomic, single TX)

Every claim function issues one statement per queue table -- `UPDATE ... WHERE Id = (SELECT ... FOR UPDATE OF tq SKIP LOCKED LIMIT 1) RETURNING ...`. Two workers cannot claim the same queue row. Two workers cannot land in-flight attempts for the same MediaFileId (the UNIQUE index refuses). Two guarantees, layered.

Current callers: `Features/TranscodeQueue/TranscodeQueueRepository.ClaimNextPendingJob` (Transcode + Remux via `ProcessingModes.ClaimCapabilityFlag`), `Features/QualityTesting/QualityTestRepository.ClaimQualityTestJob` (QT).

## Owner authority

- The worker whose WorkerName is on the attempt row is the sole authority to write terminal state (`Success`, `Disposition`, `Vmaf`, `ErrorMessage`, progress-table rows).
- Cross-worker writes are forbidden except through the abandonment sweeper (below).
- Owner-side stuck-detect filters at the SELECT layer -- `StuckJobDetectionService.DetectAndCleanStuckTranscodeJobs`, `.DetectAndCleanHungEncodes`, `.DetectAndCleanStuckQualityTestJobs` all restrict to `WorkerName = WorkerContext.Current().WorkerName`. Remote-owned jobs are never inspected + never written.

## The abandonment sweeper (single cross-worker exception)

`Features/ServiceControl/AttemptAbandonmentSweeper.SweepStaleOwners(AbandonmentMinutes=5)` runs on every worker's OrphanCleanup tick. Its only statement:

```
UPDATE TranscodeAttempts
SET Success = FALSE, ErrorMessage = 'owner_abandoned'
WHERE Success IS NULL
  AND WorkerName IN (
    SELECT WorkerName FROM Workers
    WHERE Status <> 'Online' AND LastHeartbeat < NOW() - INTERVAL '5 min'
  );
```

Idempotent. Runs on every live worker. Releases the `ta_one_inflight_per_mfid` slot for MediaFileIds whose owner is heartbeat-stale + Offline. The next claim on that MediaFileId then proceeds normally.

This is the ONLY cross-worker terminal write in the system. Every other worker-owned attempt is written by its owner.

## Worker identity is deterministic (deploy-assigned)

`WorkerName` is assigned at deploy time via `MEDIAVORTEX_WORKER_NAME` env var. Bare-metal: systemd `EnvironmentFile=/etc/mediavortex/instance-%i.env` sets one file per instance (deploy writes them). Docker: compose sets `MEDIAVORTEX_WORKER_NAME` per service. Runtime slot-claim, advisory locks, heartbeat-staleness reclaim, prefix env vars, and `socket.gethostname()` fallbacks are forbidden. `WorkerService.Main._ResolveWorkerName` fail-louds when the env var is missing -- no derivation from any other source.

Reason (2026-07-25 recurring incident): runtime slot-claim races produced N processes with identical WorkerName, each holding a `BoundedSemaphore(MaxConcurrentJobs=1)`, each claiming one job = N concurrent per WorkerName. Root class: identity was computed, not assigned. Deterministic assignment closes the class.

## Per-worker concurrency invariant (DB-authoritative)

Every claim query gates on `<in-flight count for this worker> < <cap column>` via `Core.Database.WorkerCapabilityPredicate.BuildInflightCapPredicate(WorkerName, JobType)`. Shape per job type:

| JobType | In-flight table | In-flight predicate | Cap column |
|---|---|---|---|
| `Transcode` | `TranscodeAttempts` | `Success IS NULL AND WorkerName = ?` | `Workers.MaxConcurrentJobs` |
| `QualityTest` | `QualityTestingQueue` | `Status = 'Running' AND ClaimedBy = ?` | `Workers.MaxConcurrentQualityTestJobs` |

The DB is the authority. A misdeployed second process for the same WorkerName cannot exceed the cap because the SECOND concurrent claim query sees `count = MaxConcurrentJobs` and refuses. Client-side `WorkerLoopService.SlotSemaphore` remains as a rate-limiter (prevents thread explosion in the happy path), but the invariant lives in DB.

## What is forbidden

- Cross-host stuck-detect writing to `TranscodeAttempts` / `TranscodeQueue` / `TranscodeProgress` / `ActiveJobs` for jobs owned by another worker.
- Any `WHERE`-clause comparison of `ActiveJobs.WorkerName` against `socket.gethostname()`. Use `WorkerContext.Current().WorkerName`.
- Any two-step `SELECT id then UPDATE id` claim pattern. Use one statement with `FOR UPDATE SKIP LOCKED`.
- Any code path that INSERTs a second `TranscodeAttempts` row with `Success IS NULL` for a MediaFileId that already has an in-flight attempt. The DB refuses; callers catch `IntegrityError` + retry with the next queue row.
- Runtime WorkerName derivation from `MEDIAVORTEX_WORKER_PREFIX`, hostname, container ID, or any slot-claim mechanism. `MEDIAVORTEX_WORKER_NAME` is the sole source; fail-loud when unset.
- Claim queries that omit `BuildInflightCapPredicate` for their JobType. Per-worker concurrency lives in the DB gate, not in client code.

## When this rule applies (PR triggers)

- Adds or edits any `Claim*` function against a queue table.
- Adds any UPDATE on `TranscodeAttempts` / `TranscodeQueue` / `TranscodeProgress` / `ActiveJobs`.
- Adds any stuck-detect / hung-detect / abandonment path.
- Changes `AttemptAbandonmentSweeper` or its schedule.

If your PR touches any of the above, run `py -m pytest Tests/Contract/TestClaimAuthority.py Tests/Contract/TestAbandonmentSweeper.py` and reference this rule in the PR description.

## Related

- `.claude/rules/db-is-authority.md` -- DB is SOT for runtime state; claim invariants live in the DB, not in code caches.
- `.claude/rules/fail-loud.md` -- IntegrityError on duplicate INSERT is fail-loud by construction; do not swallow.
- `transcode.flow.md` -- Job Claiming Mechanism section describes the runtime shape.
