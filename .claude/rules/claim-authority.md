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

## What is forbidden

- Cross-host stuck-detect writing to `TranscodeAttempts` / `TranscodeQueue` / `TranscodeProgress` / `ActiveJobs` for jobs owned by another worker.
- Any `WHERE`-clause comparison of `ActiveJobs.WorkerName` against `socket.gethostname()`. Use `WorkerContext.Current().WorkerName`.
- Any two-step `SELECT id then UPDATE id` claim pattern. Use one statement with `FOR UPDATE SKIP LOCKED`.
- Any code path that INSERTs a second `TranscodeAttempts` row with `Success IS NULL` for a MediaFileId that already has an in-flight attempt. The DB refuses; callers catch `IntegrityError` + retry with the next queue row.

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
