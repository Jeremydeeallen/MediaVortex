# Single-Instance WebService Startup

**Slug:** single-instance-startup

## What It Does

Guarantees at most one WebService runs across the whole farm. The instance name is deploy-assigned (`MEDIAVORTEX_WORKER_NAME`; farm server: `mediavortex-server`). Before binding port 5000, startup supersedes this instance's own prior process on this host, then refuses to start while another instance holds a fresh heartbeat. Restarting the same instance just works; a second instance anywhere else is refused while the owner is alive.

## Surface

- Farm server: systemd `mediavortex-server.service` starts it at boot and after every `deploy/deploy-server.py` run; `Restart=always`.
- Manual: `MEDIAVORTEX_WORKER_NAME=<name> python WebService/Main.py`. The dev launcher `StartMediaVortex.py` and fleet worker deploys never start a WebService.
- Console prints what was killed (PID + reason) or why startup was refused.

## Success Criteria

C1. On startup, the new process reads the `ServiceStatus` row for `WebService`. Only when that row is owned by this same instance AND a process with the recorded PID exists on this host AND is the WebService (cmdline contains `WebService` or process title is `WebService`) is it terminated with SIGTERM, then SIGKILL after 5s grace.
C2. After kill, the new process waits up to 10s for port 5000 to release before proceeding (handles OS socket-cleanup lag). Exits 1 if the port is still bound after the timeout.
C3. Stale scan cleanup marks Stopped only the Running/Pending scans owned by this instance (`ScanJobs.WorkerName` = instance name), AFTER the kill+wait, so an in-flight scan from the killed process is marked stopped and scans owned by workers are untouched.
C4. If `ServiceStatus.ProcessId` is NULL, points at a non-existent PID, or points at a PID owned by a non-WebService process (e.g. PID was recycled), startup proceeds without killing anything. No false positives.
C5. Two simultaneous starts of the same instance result in one running WebService at the end. The race is resolved by the second startup killing the first's partially-initialized process via the same path.
C6. The same logic applies to crashes: if the prior WebService died without clearing its PID row, the next startup detects the dead PID and proceeds (no kill needed; PID just doesn't exist).
C7. A WebService started under a different instance name than the current owner exits 1 without binding port 5000 while the owner's heartbeat is less than 90 seconds old (DB clock). Once the owner's heartbeat is 90 seconds old or older, the new instance takes ownership and starts. A DB error during the check refuses startup. Verifiable: `Tests/Contract/TestFarmServer.py::TestCrossHostSingleInstance`; live: on I9, `$env:MEDIAVORTEX_WORKER_NAME='I9-dev'; py WebService/Main.py` exits 1 while the farm server runs.
C8. The instance name is deploy-assigned. A WebService started without `MEDIAVORTEX_WORKER_NAME` exits 1 before any DB write. The dev launcher (`StartMediaVortex.py`) and fleet worker deploys never start or restart a WebService. Verifiable: `Tests/Contract/TestFarmServer.py::TestDeployAssignedIdentity`.

## Status

Active -- C1-C6 complete 2026-05-29; C7-C8 added by directive `farm-server`.

### Progress

- [x] C1-C6 same-host supersede
- [x] C7 cross-host gate (code + contract test)
- [x] C8 deploy-assigned identity (code + contract test)
- [ ] C7-C8 live smoke against the farm server

## Scope

```
WebService/Main.py
WebService/single-instance-startup.feature.md
WebService/startup.flow.md
Features/ServiceControl/ServiceStatusService.py
Features/ServiceControl/ServiceControlRepository.py
StartMediaVortex.py
Tests/Contract/TestFarmServer.py
```

## Files

| File | Role |
|------|------|
| `WebService/Main.py` | `Main()` runs `_ResolveInstanceName` (C8), `_SupersedeExistingInstance` (C1-C6), `_RefuseIfAlreadyRunning` (C7) before constructing the app. |
| `Features/ServiceControl/ServiceStatusService.py` | `RegisterServiceStartup(ServiceName, InstanceName)` is the gate; True = refuse. |
| `Features/ServiceControl/ServiceControlRepository.py` | `GetServiceOwnership` returns owner + freshness judged on the DB clock. |
| `StartMediaVortex.py` | Dev launcher starts WorkerService only (C8). |
| `WebService/startup.flow.md` | Step-by-step flow: identity, supersede, gate, scan cleanup, Flask init. |

## Notes

`ServiceStatus.InstanceName` names the owning instance. NULL means the row predates instance tracking; any instance may claim it. The heartbeat (`startup.S4`) keeps `UpdatedAt` fresh every 30s, so an owner is judged dead after three missed beats.
