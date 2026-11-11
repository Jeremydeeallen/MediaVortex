# WebService Startup Flow

**Slug:** startup

Entry point: `WebService/Main.py:Main()` (farm server: systemd `mediavortex-server.service`, `Restart=always`) runs ST0, ST1+ST2 and ST6 before constructing `WebServiceApp(InstanceName)`, whose initializer runs ST4, ST3, ST5 and ST7; `Run()` is ST8. IDs are stable; rows are in execution order.

## Steps

| ID | Step | What happens | Failure mode |
|---|------|--------------|--------------|
| ST0 | Resolve instance identity | `MEDIAVORTEX_WORKER_NAME` is the deploy-assigned instance name (farm server: `/etc/mediavortex/server.env` sets `mediavortex-server`). Every later step keys ownership on it. | Unset or blank -> `RuntimeError` -> exit 1 before any DB write. |
| ST1 | Supersede same instance | Read `ServiceStatus` for `servicename='WebService'`. Only when its `InstanceName` equals this instance and its PID is a live WebService process on this host (cmdline contains `WebService` OR process title is `WebService`): SIGTERM; after 5s grace, SIGKILL. | Row owned by another instance -> skip (ST6 decides). PID gone / non-WebService PID -> skip kill. Errors print and continue; ST6 still gates. |
| ST2 | Wait for port 5000 to release | Poll `socket.connect(('127.0.0.1', 5000))` until connection refused OR 10s elapsed. | Timeout -> exit 1 with "port 5000 still bound". |
| ST6 | Single-instance gate | `ServiceStatusService.RegisterServiceStartup('WebService', InstanceName)`. Refuses when another instance owns the row and its `UpdatedAt` is within 90 seconds of the DB clock, or when this instance's recorded PID is still alive on this host. A foreign owner with a stale heartbeat is taken over (logged). On allow, writes `Status='Starting'`, `ProcessId`, `InstanceName`. | Refusal -> exit 1 with "WebService is already running". DB error -> refusal. |
| ST4 | Initialize WorkerContext + code version | `SchemaChecker.AssertMatches()`; `WorkerContext.Initialize(WorkerName=InstanceName, Platform=platform.system(), FFmpegPath/FFprobePath discovered by `FFmpegService` (bundled FFmpegMaster first, PATH second))`. `App.config['CodeSha']` from `Core.CodeVersion.ResolveCodeVersion()` (S5). | Any error -> log warning, continue with empty context (KNOWN-ISSUES). |
| ST3 | Cleanup stale scans | `UPDATE ScanJobs SET Status='Stopped', ErrorMessage='Application restarted', EndTime=NOW() WHERE Status IN ('Running','Pending') AND WorkerName = <InstanceName>`. Scans owned by workers are never touched. | DB error -> log warning, continue. |
| ST5 | Register controllers + blueprints | Standard Flask wiring. | Import error -> propagates, exit 1. |
| ST7 | Start background threads | `ServiceStatusTracker` (heartbeat every 30s), `StatusPoller` (control-plane every 5s), `JellyfinSync` (one-shot). | Thread launch error -> log + continue. |
| ST8 | `waitress.serve(app, host='0.0.0.0', port=5000, threads=32)` | Production WSGI binds the socket and serves; 32-thread pool handles concurrent endpoint calls cleanly. Replaced Flask dev server's `app.run(threaded=True)` because the dev server serialized concurrent requests under GIL contention (10 parallel snapshots took 3.8s vs 0.29s solo). | Bind error -> propagates (means ST2's wait was too short OR an unrelated process now holds 5000). |

## Seams

| ID | Transition | Producer (writer) | Wire shape | Consumer (reader) expects | Verification |
|---|---|---|---|---|---|
| S1 | `ST1 -> ST2` (kill -> port-wait) | `_SupersedeExistingInstance` issues SIGTERM/SIGKILL to this instance's prior PID | OS-level process termination; socket released by OS | `socket.connect(('127.0.0.1', 5000))` returns ConnectionRefusedError | Manual: launch WebService twice under the same `MEDIAVORTEX_WORKER_NAME`; observe the supersede console line; verify port 5000 free via `netstat` |
| S2 | `ST3` stale-scan reset | This step (writer) | `ScanJobs.(Status='Stopped', ErrorMessage='Application restarted', EndTime=NOW())` for this instance's previously-Running rows only | `/Operations` recent scans card excludes housekeeping reasons by default | `SELECT COUNT(*) FROM ScanJobs WHERE Status='Running' AND WorkerName='<InstanceName>'` -> 0 after restart; worker-owned Running rows unchanged |
| S3 | `ST6` ServiceStatus write | `ServiceStatusService.RegisterServiceStartup` | `ServiceStatus.(ServiceName='WebService', ProcessId INT, InstanceName TEXT, Status='Starting', UpdatedAt=NOW())` | The next start of the same instance uses `ProcessId` for ST1; any other instance's ST6 reads `InstanceName` + `UpdatedAt` | `Tests/Contract/TestFarmServer.py::TestCrossHostSingleInstance` |
| S4 | `ST7` heartbeat -> `ST6` freshness | `ServiceStatusTracker` thread writes every 30s | `ServiceStatus.UpdatedAt=NOW()` | `/Stats` page (`teamstatus.flow.md::S3`) reads `ServiceStatus` for the badge; ST6 of another instance treats `UpdatedAt` within 90s (three missed beats) as alive | Wait 60s, observe two writes via `SELECT UpdatedAt FROM ServiceStatus WHERE ServiceName='WebService'` |
| S5 | `ST4 -> HTTP` running code version | `Core.CodeVersion.ResolveCodeVersion()` -> `App.config['CodeSha']` | `GET /api/Version` -> `{'Success': true, 'Data': {'Sha': <git sha>, 'Instance': <InstanceName>}}`; sha from `.git/HEAD` on a checkout, the `VERSION` file on a deployed tree, `unknown` otherwise | `deploy/deploy-server.py` (`worker-deploy-baremetal.ST7`) declares a deploy done only when this equals the target sha | `Tests/Contract/TestFarmServer.py::TestCodeVersion`; `curl http://<server>:5000/api/Version` |
| S6 | `ST0 -> ST4` storage roots for the instance | `Scripts/SQLScripts/SeedServerStorageRootResolutions.py` (farm server) / `WorkersRepository.RegisterStorageRootResolutions` | `StorageRootResolutions.(WorkerName=<InstanceName>, StorageRootId, AbsolutePath, IsActive)`; farm server: T/M/X -> `/mnt/media_tv/`, `/mnt/movies/`, `/mnt/xxx/` | WorkerContext resolves canonical paths for background runners (audio remeasurement, scans) the same way the larry workers do | `Tests/Contract/TestFarmServer.py::test_server_instance_resolves_storage_roots` |

## Code pointers

| File | Where | Why |
|------|-------|-----|
| `WebService/Main.py:_ResolveInstanceName` | ST0 | Deploy-assigned identity |
| `WebService/Main.py:_SupersedeExistingInstance` | ST1+ST2 | Same-instance kill + wait |
| `WebService/Main.py:_RefuseIfAlreadyRunning` -> `Features/ServiceControl/ServiceStatusService.RegisterServiceStartup` | ST6 | Cross-host gate; writes PID + InstanceName |
| `Features/ServiceControl/ServiceControlRepository.GetServiceOwnership` | ST6 | Owner + freshness on the DB clock |
| `WebService/Main.py` initializer (cleanup_query block) | ST3 | Owner-scoped stale scan reset |
| `Core/CodeVersion.ResolveCodeVersion`, `Features/ServiceControl/ServiceStatusController.GetCodeVersion` | S5 | Running sha over HTTP |
| `Repositories/DatabaseManager.UpdateServiceStatus` | ST7 (heartbeat) | Per-30s liveness write |
