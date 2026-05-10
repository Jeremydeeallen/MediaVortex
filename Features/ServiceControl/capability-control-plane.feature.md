# Feature: Capability Control Plane (single gate per worker capability)

## What It Does

Establishes that the **sole** operational gate for whether a worker runs a capability (transcode, VMAF quality test, scan) is:

```
Workers.<Capability>Enabled = TRUE
  AND Workers.Status = 'Online'
  AND Workers.LastHeartbeat > NOW() - INTERVAL '90 seconds'
```

The capability poller (`WorkerService._CapabilityPollingLoop`, 60 s) is the one mechanism that translates this state into "loop running / loop stopped". No code path inside any processing loop re-litigates the question by reading a separate "is the service paused?" row.

In particular: `ServiceStatus.<X>Service.Status` is **informational only**. It may be surfaced on a Status page or used for lifecycle reporting, but it is never an input to a "should I do work?" decision in any worker loop.

## Concern

Operator dogfood, 2026-05-10. The post-transcode-disposition feature shipped with the disposition function correctly migrated from `ServiceStatus.QualityTestService` to a computed `Workers` query (commit `afdca4a`) -- but the **VMAF processing loop itself** still reads `ServiceStatus.QualityTestService.Status='Paused'` and skips work, gated on the same fossilized row. The legacy `QualityTestService` process (retired into `archive_QualityTestService/`) was the only live writer of that row; nothing in the unified WorkerService updates it. The row has been frozen at `Paused` since 2026-01-26.

The same anti-pattern exists symmetrically in `ProcessTranscodeQueueService.ProcessQueueLoop:287` against `ServiceStatus.TranscodeService` -- nobody has flipped that one to `Paused` recently so the bug is dormant, but the gate is just as dead. Flipping `Workers.TranscodeEnabled=False` stops the loop via `_StopTranscodeCapability`, but flipping `ServiceStatus.TranscodeService='Paused'` would also stop it -- two knobs, one of which has no live writer. Future operator confusion is guaranteed.

The contract this feature establishes makes the capability flag the *single* source of truth and retires `ServiceStatus.<X>Service` as a gate.

## Surface

- **Operator-visible behavior.**
  - To pause VMAF on a worker: `UPDATE Workers SET QualityTestEnabled=FALSE WHERE WorkerName='X'`. The capability poller picks up the change within 60 s and the loop exits cleanly.
  - To pause VMAF fleet-wide: same UPDATE for every worker.
  - To pause the whole worker (any capability): `UPDATE Workers SET Status='Draining'` (graceful) or `Status='Offline'` (hard stop).
  - `ServiceStatus.QualityTestService.Status` no longer pauses anything. (It is still written by lifecycle code for reporting; it is no longer read as a gate.)
- **No new HTTP endpoints, no new UI, no schema change.** The `ServiceStatus` rows remain in the database for backward compatibility and informational display. Reads-as-gate are removed.

## Success Criteria

1. **Single gate, no double-checks.** No code in any worker processing loop reads `ServiceStatus.<X>Service.Status` to decide whether to claim or skip work. Verifiable: `grep -rn "GetServiceStatus" Features/QualityTesting/ProcessQualityTestQueueService.py Features/TranscodeJob/ProcessTranscodeQueueService.py` returns zero matches inside any `*Loop`, `Run`, `ProcessJob`, `ClaimNextJob`, or related method body. (`grep` against `GetServiceStatus` is allowed elsewhere -- display, health, lifecycle -- but not in the processing path.)

2. **Capability flag stops the loop within the poll interval.** Setting `Workers.QualityTestEnabled=FALSE` for a worker stops VMAF processing on that worker within 90 seconds, with no `ServiceStatus.QualityTestService` write required. Verifiable: with the worker's QT loop running and a job in `QualityTestingQueue`, flip `QualityTestEnabled=FALSE`. Within 90 s the worker logs `Quality test capability stopped`. The queue row is not claimed by that worker after the flip.

3. **Capability flag starts the loop within the poll interval.** Symmetric to criterion 2: setting `Workers.QualityTestEnabled=TRUE` starts VMAF processing within 90 s, with no `ServiceStatus.QualityTestService` write. Verifiable: with the worker running but QT off, and a job in `QualityTestingQueue`, flip `QualityTestEnabled=TRUE`. Within 90 s the worker logs `Quality test capability started` and `Successfully claimed quality test job <id>`.

4. **Symmetric coverage for transcode.** Criteria 2 and 3 apply identically to `Workers.TranscodeEnabled` and the transcode loop. Verifiable: same flip-and-observe test against `TranscodeQueue` and the transcode capability lifecycle logs.

5. **`ServiceStatus.<X>Service.Status` is informational only.** Manually setting `ServiceStatus.QualityTestService.Status='Paused'` for a worker that has `Workers.QualityTestEnabled=TRUE` does NOT stop VMAF processing. Verifiable: with the worker running, write `Paused` to the row; queue rows continue to be claimed and processed. (Operators who want to pause VMAF must use the capability flag.)

## Status

**IMPLEMENTED 2026-05-10** -- this feature was scoped, drafted, and shipped in one pass to unblock the i9 + larry smoke test of the post-transcode-disposition feature.

### Progress

- [x] 1. Surface the bug shape during the i9 smoke test (worker terminal showed `QualityTestService is paused, skipping queue processing` despite `Workers.QualityTestEnabled=TRUE`)
- [x] 2. Articulate the principle (one control plane per concern; per-worker capability flag is the sole gate)
- [x] 3. Draft this feature doc with 5 success criteria
- [x] 4. Operator approval (granted in the same conversation)
- [x] 5. Delete the `ServiceStatus` gate read in `ProcessQualityTestQueueService.ProcessQueueLoop`
- [x] 6. Delete the symmetric `ServiceStatus` gate read in `ProcessTranscodeQueueService.ProcessQueueLoop`
- [x] 7. Update `transcode.flow.md` Stage 2 (transcode claim) and Stage 7 (VMAF execution) to drop any reference to `ServiceStatus.<X>Service` as a gate
- [x] 8. Update `KNOWN-ISSUES.md` to note the symmetric retirement and link to this feature doc
- [x] 9. Live verification on i9: with the new code, restart the worker; observe the QT loop claims `QualityTestingQueue` row 893 within seconds (the row that motivated this feature)

## Scope

```
Features/QualityTesting/ProcessQualityTestQueueService.py
Features/TranscodeJob/ProcessTranscodeQueueService.py
transcode.flow.md
KNOWN-ISSUES.md
```

## Files

| File | Role |
|---|---|
| `Features/QualityTesting/ProcessQualityTestQueueService.py` | `ProcessQueueLoop` -- delete the `GetServiceStatus("QualityTestService")` gate (lines 131-143) |
| `Features/TranscodeJob/ProcessTranscodeQueueService.py` | `ProcessQueueLoop` -- delete the `GetServiceStatus("TranscodeService")` gate (lines 285-295) |
| `transcode.flow.md` | Drop `ServiceStatus.<X>Service` references from Stage 2 / Stage 7 inputs and gate descriptions |
| `KNOWN-ISSUES.md` | Update the env-driven-config entry to note this feature retires `ServiceStatus`-as-gate as part of the broader pattern cleanup |

## Deviation from conventions

None. Each criterion is observable from outside the codebase (DB query + log inspection), passes the rename / outsider / rewrite / negation / stability tests.
