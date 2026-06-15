# Pause Must Not Sweep In-Flight Claims

**Set:** 2026-06-15
**Status:** Active -- phase: IMPLEMENTING
**Slug:** pause-not-stale

## Outcome

Pausing a worker stops it from claiming **new** work but does NOT cause other workers (or itself on the next sweep) to reset its in-flight TranscodeQueue / ScanJobs / QualityTestingQueue claims. FFmpeg keeps running, post-flight finalizes normally, compute time is preserved.

## Root cause

`Features/ServiceControl/StuckJobDetectionService._IsWorkerOffline` returns `True` (= worker is offline -> sweep claims) when `Workers.Status='Paused'`. Sibling workers running their stuck-job sweep see this and clean up claims for the paused worker. Lines 236-238:

```python
# If worker explicitly marked Paused, it won't pick up new jobs
if WorkerStatus and WorkerStatus.lower() == 'paused':
    return True, "Worker status is Paused"
```

The premise is true (paused worker doesn't claim new jobs) but the conclusion is wrong (therefore it's stale and we should sweep its work). Paused worker is alive, heartbeating, and still owns its in-flight work until that work completes naturally. The same fault paths apply to `DetectAndCleanStuckScanJobs` (calls the same `_IsWorkerOffline`) and to the QualityTest sweep.

## Acceptance Criteria

1. **Paused worker with fresh heartbeat is NOT considered offline.** `_IsWorkerOffline('paused-worker-with-fresh-heartbeat')` returns `(False, ...)`. Verifiable: contract test mocks `Workers` row with `Status='Paused', LastHeartbeat=NOW()` -- assertion returns False.

2. **Genuinely stale paused worker (no heartbeat for >5min) IS offline.** The heartbeat-age check at lines 244-250 remains the only liveness criterion. Verifiable: same contract test with `LastHeartbeat=NOW() - 10min` returns True.

3. **The 3-line Paused branch is deleted.** Verifiable: `grep -n "Status is Paused" Features/ServiceControl/StuckJobDetectionService.py` returns no hits.

4. **Live remediation of two orphans.** Love Island queue row 139836 is flipped back to `Running` + ClaimedBy=dot-worker-1 so its in-flight FFmpeg can finalize when it completes. Alvin's queue row 139867 was fully deleted by the sweep and cannot be reattached -- kill the orphan FFmpeg and accept the waste, noting that with this fix it would not have happened.

## Files

```
Features/ServiceControl/StuckJobDetectionService.py
Tests/Contract/TestStuckJobDetectionService.py    -- NEW
```
