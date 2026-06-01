# WebService Startup Flow

**Slug:** startup

Entry point: `WebService/Main.py:Main()` -> `WebServiceApp.__init__()`.

## Steps

| ID | Step | What happens | Failure mode |
|---|------|--------------|--------------|
| ST1 | Supersede existing instance | Read `ServiceStatus.ProcessId` for `servicename='WebService'`. If PID exists and the process matches (cmdline contains `WebService/Main.py` OR process title is `WebService`), SIGTERM; after 5s grace, SIGKILL. | PID NULL / process gone / non-WebService PID -> skip kill silently. |
| ST2 | Wait for port 5000 to release | Poll `socket.connect(('127.0.0.1', 5000))` until connection refused OR 10s elapsed. | Timeout -> exit 1 with "Port 5000 still bound by another process". |
| ST3 | Cleanup stale scans | `UPDATE ScanJobs SET Status='Stopped', ErrorMessage='Application restarted', EndTime=NOW() WHERE Status IN ('Running','Pending')`. | DB error -> log warning, continue (existing behavior). |
| ST4 | Initialize WorkerContext | Load Workers row for `socket.gethostname()`, register FFmpeg paths. | Missing row -> log warning, continue with empty context. |
| ST5 | Register controllers + blueprints | Standard Flask wiring. | Import error -> propagates, exit 1. |
| ST6 | Register with ServiceStatusService | `ServiceStatusService.RegisterServiceStartup('WebService', MaxConcurrentJobs=1)` writes the NEW process's PID to `ServiceStatus`. | DB error -> log + continue (heartbeat will retry). |
| ST7 | Start background threads | `ServiceStatusTracker` (heartbeat every 30s), `StatusPoller` (control-plane every 5s), `JellyfinSync` (one-shot). | Thread launch error -> log + continue. |
| ST8 | `app.run(host='0.0.0.0', port=5000)` | Flask binds the socket and serves. | Bind error -> propagates (means ST2's wait was too short OR an unrelated process now holds 5000). |

## Seams

| ID | Transition | Producer (writer) | Wire shape | Consumer (reader) expects | Verification |
|---|---|---|---|---|---|
| S1 | `ST1 -> ST2` (kill -> port-wait) | `_SupersedeExistingInstance` issues SIGTERM/SIGKILL to prior PID | OS-level process termination; socket released by OS | `socket.connect(('127.0.0.1', 5000))` returns ConnectionRefusedError | Manual: launch WebService, observe console line printing PID killed; verify port 5000 free via `netstat` |
| S2 | `ST3` stale-scan reset | This step (writer) | `ScanJobs.(Status='Stopped', ErrorMessage='Application restarted', EndTime=NOW())` for previously-Running rows | `/Operations` recent scans card excludes housekeeping reasons by default | `SELECT COUNT(*) FROM ScanJobs WHERE Status='Running' AND WorkerName='WebService'` -> 0 after restart |
| S3 | `ST6` ServiceStatus write | `ServiceStatusService.RegisterServiceStartup` | `ServiceStatus.(servicename='WebService', processid BIGINT NOT NULL, status='Online', lastheartbeat=NOW())` | Future restarts use `processid` for `ST1`'s supersede; informational only per `capability-control-plane` | `SELECT processid FROM ServiceStatus WHERE servicename='WebService'` matches `os.getpid()` of the running process |
| S4 | `ST7` heartbeat cadence | `ServiceStatusTracker` thread writes every 30s | `ServiceStatus.lastheartbeat=NOW()` | `/Stats` page (`teamstatus.flow.md::S3`) reads `ServiceStatus` for service badge state | Wait 60s, observe two heartbeat writes via `SELECT lastheartbeat FROM ServiceStatus WHERE servicename='WebService'` |

## Code pointers

| File | Where | Why |
|------|-------|-----|
| `WebService/Main.py:_SupersedeExistingInstance` | Step 1+2 | Kill + wait |
| `WebService/Main.py` initializer (cleanup_query block) | Step 3 | Stale scan reset |
| `Services/ServiceStatusService.RegisterServiceStartup` | Step 6 | Writes PID to ServiceStatus |
| `Repositories/DatabaseManager.UpdateServiceStatus` | Step 7 (heartbeat) | Per-30s liveness write |
