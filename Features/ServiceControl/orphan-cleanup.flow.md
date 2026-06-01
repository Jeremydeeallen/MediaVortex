# Flow: Orphan Cleanup

**Slug:** orphan-cleanup

## Entry Point

`WorkerService/Main.py` -- a daemon thread (`_OrphanCleanupLoop`) on each
worker invokes `OrphanCleanupService.SweepOrphans` every
`SystemSettings.StuckJobDetectionIntervalSec` seconds (default 120 -- same
cadence as `_StuckJobDetectionLoop`; the two run as sibling threads
because they share the "operational hygiene" concern but have different
kill semantics).

This flow is the safety net for the four-table leak documented in
`KNOWN-ISSUES.md` BUG-0001. Steady-state writers (the disposition
service, `HandleJobFailure`, the queue-delete callers) are responsible
for cleanup in the normal path. This sweep catches three classes of
regression: a future code path that forgets to clean up, a crash that
leaves rows behind, and the polymorphic `ActiveJobs.QueueId` reference
that cannot be enforced with a single FK.

## Per-Cycle Decision Tree

| # | Step | What happens | Failure mode |
|---|------|--------------|--------------|
| 1 | TFP orphans | `DELETE FROM TemporaryFilePaths WHERE TranscodeAttemptId IN (SELECT Id FROM TranscodeAttempts WHERE Success IS NOT NULL)` | Steady-state hits should be 0; non-zero count emits one WARN log naming the count. Operator hunts the leaking caller. |
| 2 | ActiveJobs orphans (TranscodeService) | `DELETE FROM ActiveJobs WHERE ServiceName='TranscodeService' AND QueueId NOT IN (SELECT Id FROM TranscodeQueue)` | Each removal emits one WARN log with `QueueId` and `WorkerName` so the leaking delete-caller can be traced. |
| 3 | ActiveJobs orphans (QualityTestingService) | `DELETE FROM ActiveJobs WHERE ServiceName='QualityTestingService' AND QueueId NOT IN (SELECT Id FROM QualityTestingQueue)` | Same WARN-per-removal pattern as step 2. |
| 4 | QualityTestingQueue stale rows | `DELETE FROM QualityTestingQueue WHERE TranscodeAttemptId IN (SELECT Id FROM TranscodeAttempts WHERE Success IS NOT NULL AND QualityTestCompleted = TRUE)` | Each removal emits one WARN log with the `TranscodeAttemptId` and the attempt's `Disposition` so the operator can see which terminal path leaked it. |
| 5 | TranscodeProgress orphans | `DELETE FROM TranscodeProgress WHERE TranscodeAttemptId NOT IN (SELECT Id FROM TranscodeAttempts WHERE Success IS NULL AND CompletedDate IS NULL)` | Catches any rows the `UNIQUE (TranscodeAttemptId)` constraint cannot prevent (the constraint blocks duplicates, not orphans). |
| 6 | Single INFO summary | One INFO log per cycle: `OrphanCleanup swept: TFP=<n> ActiveJobs=<n> QTQueue=<n> Progress=<n>` | Lets the operator confirm the loop is running (per criterion 18's verifiability) and watch the trend over time. |

Every step runs in its own short transaction. One step failing does not
abort the rest of the cycle (errors are logged, the loop sleeps and
retries on the next tick).

## State Tables

```
TemporaryFilePaths
  TranscodeAttemptId  BIGINT  -- FK by convention; row lifetime = attempt in-flight

ActiveJobs
  ServiceName  TEXT    -- 'TranscodeService' | 'QualityTestingService' | 'ScanService'
  QueueId      BIGINT  -- polymorphic ref, discriminated by ServiceName

QualityTestingQueue
  TranscodeAttemptId  BIGINT  -- attempt being scored

TranscodeProgress
  TranscodeAttemptId  BIGINT UNIQUE  -- added by BUG-0001 migration; one progress row per attempt
```

## Failure Modes

- **DB unreachable**: the cycle catches, logs, sleeps for the next
  interval. One bad cycle does not crash the worker.
- **Sweep step deletes a row another worker just inserted**: the
  delete predicate re-evaluates on each cycle and is idempotent. A
  legitimate row created milliseconds before the sweep will be
  preserved on the next cycle once the attempt is no longer terminal,
  or the row was genuinely stale and the delete was correct.
- **Many orphans accumulate while a worker is offline**: when the
  worker restarts, the first sweep cycle may delete hundreds of rows.
  The WARN log fires per category (not per row) so the operator gets
  one entry per leak class rather than a flood.

## Out of Scope

- Killing stuck processes. That is `stuck-job-detection.flow.md`'s job.
  This flow is DB-only; it never touches the filesystem and never
  signals a process.
- Identifying the *current* leaking caller. The WARN logs surface the
  symptom; the fix lives in the queue-delete site or the disposition
  path, not in this sweep.
- Cross-host action. The sweep is DB-only, so every worker runs the
  same cycle. Running on multiple workers simultaneously is safe
  because every DELETE is idempotent and predicate-driven.
