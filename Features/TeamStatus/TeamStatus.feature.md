# Stats Page: Worker-Aware Status

**Slug:** teamstatus

## What It Does

Updates the Stats page (/Stats) to be worker-aware for distributed transcoding:
1. Active Transcode Jobs table shows which worker is processing each job
2. Stuck jobs (Running in DB but worker offline/not processing) are identifiable and cleanable
3. Services section lists all registered workers from the Workers table with their status

## Concern

Both (UI changes + API changes)

## Success Criteria

### Active Transcode Jobs -- per-worker attribution
C1. Each row in the Active Transcode Jobs table shows the worker name (e.g. "I9-2024", "mediavortex-transcode") that claimed the job. Source: TranscodeQueue.ClaimedBy.
C2. The /api/TeamStatus/Overview response includes ClaimedBy in each ActiveJobs entry.

### Active Transcode Jobs -- stuck job cleanup
C3. A job is "stuck" when: TranscodeQueue.Status = 'Running' AND the claiming worker's LastHeartbeat is older than 5 minutes (or worker row does not exist).
C4. Stuck jobs display a visual indicator (e.g. warning badge, different row color) instead of the spinning progress icon.
C5. Each stuck job row has a "Reset" button that sets the queue item back to Pending (Status='Pending', ClaimedBy=NULL, ClaimedAt=NULL, DateStarted=NULL) and removes the corresponding ActiveJob.
C6. The reset action is a POST to /api/TeamStatus/ResetStuckJob with the QueueId. Returns Success/Failure JSON.

### Services section -- worker listing
C7. The Services section includes a card for each row in the Workers table (in addition to existing ServiceStatus entries).
C8. Each worker card shows: WorkerName, Status (Online/Offline), LastHeartbeat (relative time, e.g. "2 min ago"), MaxConcurrentJobs, and whether it AcceptsInterlaced.
C9. A worker is displayed as "Offline" if LastHeartbeat is older than 5 minutes.
C10. The /api/TeamStatus/Workers endpoint returns the Workers table rows.

## Status

COMPLETE -- both verifies passed 2026-05-09

### Progress

- [x] Read existing code: TeamStatusController, Status.html, ServiceStatusController
- [x] Create flow doc: TeamStatus.flow.md
- [x] Write feature doc with criteria
- [x] Add ClaimedBy to Overview API active jobs query
- [x] Add stuck job detection logic (compare ClaimedBy heartbeat, fallback for jobs without progress rows)
- [x] Add POST /api/TeamStatus/ResetStuckJob endpoint
- [x] Add GET /api/TeamStatus/Workers endpoint
- [x] Add Worker column to Active Transcode Jobs table in Status.html
- [x] Add stuck job visual indicator (warning row + triangle icon) + Reset button in UI
- [x] Add Workers cards to Services section in Status.html (separate Workers section above Services)
- [x] Verified 2026-05-09: two workers transcoding shows both with correct worker names
- [x] Verified 2026-05-09: stopped worker's job shows as stuck, Reset button works

## Scope

```
Features/TeamStatus/TeamStatusController.py
Templates/Status.html
```

## Files

| File | Change |
|------|--------|
| Features/TeamStatus/TeamStatusController.py | Add ClaimedBy to active jobs query, add Workers endpoint, add ResetStuckJob endpoint |
| Templates/Status.html | Add Worker column to jobs table, stuck job indicators, Reset button, Workers cards in Services section |
