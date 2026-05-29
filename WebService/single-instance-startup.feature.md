# Single-Instance WebService Startup

## What It Does

Guarantees exactly one WebService process is running. Before binding port 5000, startup kills any prior WebService instance whose PID is recorded in `ServiceStatus`, waits briefly for the socket to release, then proceeds with normal initialization including stale-scan cleanup.

Replaces the prior "exit if already running" behavior. Restarting via `python WebService/Main.py` now Just Works -- the new process supersedes the old one.

## Surface

- Operator runs `python WebService/Main.py` (directly or via `StartMediaVortex.py`).
- Stale running instance is terminated automatically; no manual `StopMediaVortex.py` step required first.
- Console prints what was killed (PID + reason) so the operator can see the supersede in real time.

## Success Criteria

1. On startup, the new process reads `ServiceStatus.ProcessId` for `servicename='WebService'`. If a process with that PID exists AND is the WebService (cmdline contains `WebService/Main.py` or process title is `WebService`), it is terminated with SIGTERM then SIGKILL after 5s grace.
2. After kill, the new process waits up to 10s for port 5000 to release before proceeding (handles OS socket-cleanup lag). Exits 1 if the port is still bound after the timeout.
3. Stale scan cleanup (UPDATE ScanJobs SET Status='Stopped' WHERE Status IN ('Running','Pending')) runs AFTER the kill+wait, so an in-flight scan from the killed process is correctly marked stopped.
4. If `ServiceStatus.ProcessId` is NULL, points at a non-existent PID, or points at a PID owned by a non-WebService process (e.g. PID was recycled), startup proceeds without killing anything. No false positives.
5. Two simultaneous starts (e.g. operator double-clicks) result in one running WebService at the end. The race is resolved by the second startup killing the first's partially-initialized process via the same path.
6. The same logic applies to crashes: if the prior WebService died without clearing its PID row, the next startup detects the dead PID and proceeds (no kill needed; PID just doesn't exist).

## Status

COMPLETE 2026-05-29.

## Scope

```
WebService/Main.py
WebService/single-instance-startup.feature.md
WebService/startup.flow.md
```

## Files

| File | Role |
|------|------|
| `WebService/Main.py` | `_SupersedeExistingInstance` runs before Flask init; replaces `PrivateIsServiceAlreadyRunning` reject. |
| `WebService/startup.flow.md` | Step-by-step flow including kill, wait, scan cleanup, Flask init. |

## Notes

The `ServiceStatusService.RegisterServiceStartup` call still runs (writes the new PID + status row). It no longer gates startup -- the supersede happened upstream of the call.
