# Feature: Capability Control Plane (single gate per worker capability)

**Slug:** capability-control-plane

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

### AMENDMENT 2026-05-18 -- Quick capability + Status precondition

Context: original doc enumerated three capabilities (Transcode, QualityTest, Scan). The 2026-05 Quick-Fix collapse introduced a single "Quick" dispatch class that covers container/codec remux AND audio normalization in one indivisible FFmpeg pass (see `Features/TranscodeQueue/media-tabs-and-loudness.feature.md` and `Features/CommandBuilder/command-builder.feature.md`). The capability surface has to extend to cover it, and the long-standing assumption that `Workers.Status` is purely cosmetic has to be codified -- BUG-0004 caught a Paused worker happily claiming jobs because no code path treats Status as a precondition.

6. **`RemuxEnabled` is a first-class capability gate.** The Workers table carries `RemuxEnabled BOOLEAN` alongside `TranscodeEnabled` / `QualityTestEnabled` / `ScanEnabled`. The Quick dispatch loop (the one that claims `ProcessingMode IN ('Quick','Remux','AudioFix')`) is gated on it identically to how the transcode loop is gated on `TranscodeEnabled`. Toggling `RemuxEnabled=FALSE` stops the Quick loop within the 90 s capability-poll interval; toggling `RemuxEnabled=TRUE` starts it. Verifiable: with a Quick row in queue, flip the flag and observe the loop start/stop in worker logs and the row claim/no-claim behavior. The name is `RemuxEnabled` rather than `QuickEnabled` because container fix is the load-bearing work; audio normalize is the cheap rider.

7. **Audio normalization is NOT a separate capability.** There is no `AudioFixEnabled` column. A worker that has `RemuxEnabled=TRUE` will claim any Quick row, whether the actual work is container fix only, audio normalize only, or both. The "Quick" path is indivisible: workers either do all of it or none of it. Verifiable: `grep -rE "AudioFixEnabled|AudioEnabled" Features/ Repositories/ WorkerService/` returns zero matches. Two capability switches at the dispatch level, not three.

8. **Worker Status is the master precondition** (BUG-0004). No capability loop claims work when `Workers.Status != 'Online'`. This applies to every capability uniformly: Transcode, Remux, QualityTest, Scan. `Status` values `Draining`, `Offline`, `Paused`, `MountValidationError`, etc. all block claim regardless of the per-capability `*Enabled` flag. The `_CapabilityPollingLoop` evaluates `*Enabled AND Status='Online' AND LastHeartbeat > NOW() - INTERVAL '90 seconds'` (already the documented combined gate at the top of this doc -- criterion 8 codifies it as a HARD requirement, not a documented intention). Verifiable: set `Workers.Status='Paused'` on a worker with `TranscodeEnabled=TRUE` and a Transcode row in queue; within 90 s the worker stops claiming. Set Status back to 'Online' and claiming resumes within 90 s.

9. **Worker card UI surfaces two capability switches** labeled by what they cover, not by their internal class names. Concretely: a `Transcode` toggle (binds to `Workers.TranscodeEnabled`) and a `Quick (audio + remux)` toggle (binds to `Workers.RemuxEnabled`). QualityTest and Scan continue to surface as their own toggles since they're orthogonal capabilities. The label "Quick (audio + remux)" is the contract: when an operator turns Quick off, they're shutting down container remux AND audio normalization, and the label says so. Verifiable: render the worker card; the two media-work toggles read `Transcode` and `Quick (audio + remux)`; clicking each writes the corresponding DB column.

10. **Atomic capability flip is reflected by the next poll cycle, not the next process restart.** Criteria 2-4 already cover this for QT and Transcode; criterion 10 extends it to Remux and to the Status precondition. Operator changes a worker card toggle -> DB write -> next `_CapabilityPollingLoop` tick (≤60 s) -> capability starts or stops on that worker. No restart required for any capability change, including Status flips. Verifiable: flip any combination of `Status`, `TranscodeEnabled`, `RemuxEnabled`, `QualityTestEnabled`, `ScanEnabled` mid-flight; observe the corresponding lifecycle log line within 90 s; no `kill`/restart issued.

## Status

**IMPLEMENTED 2026-05-10** for criteria 1-5.
**AMENDMENT DRAFT 2026-05-18** for criteria 6-10 -- adds Quick capability gate, codifies Status precondition (resolves BUG-0004), defines worker card UI label contract.

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

### Progress (Amendment 2026-05-18)

- [x] 10. Surface the gap during Quick-Fix smoke test (RemuxEnabled exists in DB but no contract; BUG-0004 filed against the Status hole)
- [x] 11. Draft criteria 6-10 covering Quick capability, Status precondition, UI label contract
- [ ] 12. Operator approves amendment criteria
- [ ] 13. Verify `RemuxEnabled` column exists on Workers (add migration if missing)
- [ ] 14. Verify Quick dispatch loop in `ProcessTranscodeQueueService` reads `RemuxEnabled` (likely already true; add the explicit gate read if not)
- [ ] 15. Add `Status='Online'` precondition to capability-poll lifecycle predicate `_ShouldRunCapability` -- fixes BUG-0004
- [ ] 16. Audit worker card template -- relabel "Quick" toggle to `Quick (audio + remux)` per criterion 9
- [ ] 17. Live verification: flip each toggle (Transcode/Quick/QualityTest/Scan/Status) mid-flight; observe correct loop start-stop within 90 s
- [ ] 18. Run `/bs BUG-0004` after criterion 8 verifies

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
