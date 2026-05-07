# Service Control

## What It Does

Manages the lifecycle and health of all three microservices (WebService, TranscodeService, QualityTestService). Provides start/stop/pause/resume controls, health monitoring, stuck job detection, and crash recovery.

## Success Criteria

1. Each microservice can be started, stopped, paused, and resumed independently from the /Status page.
2. Health monitoring polls each service's heartbeat every 30 seconds via the ServiceStatus table.
3. Stuck job detection identifies transcode jobs that have been running beyond a configurable timeout with no progress updates.
4. Crash recovery detects orphaned processes (service died without cleanup) and resets their queue items to Pending.
5. Graceful shutdown waits for the current job to complete before stopping the service.
6. Inter-service commands are queued via the ServiceCommands table (no direct inter-process messaging).
7. System resource monitoring (CPU usage, memory, disk space) is displayed on the /Status page.
8. CPU core temperatures are displayed individually when available.
9. StartMediaVortex.py launches all three services. StopMediaVortex.py gracefully shuts them all down.

## Status

COMPLETE

## Scope

```
Features/ServiceControl/**
```

## Files

| File | Role |
|------|------|
| Features/ServiceControl/ServiceControlController.py | Flask Blueprint -- service control endpoints |
| Features/ServiceControl/StuckJobDetectionService.py | Stuck job detection and reset |
| StartMediaVortex.py | Launch all services |
| StopMediaVortex.py | Graceful shutdown |
