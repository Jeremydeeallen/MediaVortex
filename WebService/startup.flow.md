# WebService Startup Flow

**Slug:** startup

Entry point: `WebService/Main.py:Main()` -> `WebServiceApp.__init__()`.

## Steps

| # | Step | What happens | Failure mode |
|---|------|--------------|--------------|
| 1 | Supersede existing instance | Read `ServiceStatus.ProcessId` for `servicename='WebService'`. If PID exists and the process matches (cmdline contains `WebService/Main.py` OR process title is `WebService`), SIGTERM; after 5s grace, SIGKILL. | PID NULL / process gone / non-WebService PID -> skip kill silently. |
| 2 | Wait for port 5000 to release | Poll `socket.connect(('127.0.0.1', 5000))` until connection refused OR 10s elapsed. | Timeout -> exit 1 with "Port 5000 still bound by another process". |
| 3 | Cleanup stale scans | `UPDATE ScanJobs SET Status='Stopped', ErrorMessage='Application restarted', EndTime=NOW() WHERE Status IN ('Running','Pending')`. | DB error -> log warning, continue (existing behavior). |
| 4 | Initialize WorkerContext | Load Workers row for `socket.gethostname()`, register FFmpeg paths. | Missing row -> log warning, continue with empty context. |
| 5 | Register controllers + blueprints | Standard Flask wiring. | Import error -> propagates, exit 1. |
| 6 | Register with ServiceStatusService | `ServiceStatusService.RegisterServiceStartup('WebService', MaxConcurrentJobs=1)` writes the NEW process's PID to `ServiceStatus`. | DB error -> log + continue (heartbeat will retry). |
| 7 | Start background threads | `ServiceStatusTracker` (heartbeat every 30s), `StatusPoller` (control-plane every 5s), `JellyfinSync` (one-shot). | Thread launch error -> log + continue. |
| 8 | `app.run(host='0.0.0.0', port=5000)` | Flask binds the socket and serves. | Bind error -> propagates (means step 2's wait was too short OR an unrelated process now holds 5000). |

## Code pointers

| File | Where | Why |
|------|-------|-----|
| `WebService/Main.py:_SupersedeExistingInstance` | Step 1+2 | Kill + wait |
| `WebService/Main.py` initializer (cleanup_query block) | Step 3 | Stale scan reset |
| `Services/ServiceStatusService.RegisterServiceStartup` | Step 6 | Writes PID to ServiceStatus |
| `Repositories/DatabaseManager.UpdateServiceStatus` | Step 7 (heartbeat) | Per-30s liveness write |
