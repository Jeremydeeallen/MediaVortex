# WorkerService - Unified Worker

## Summary

Single entry point that replaces separate TranscodeService + QualityTestService processes.
Each worker reads per-worker capability flags (TranscodeEnabled, QualityTestEnabled, ScanEnabled)
and status (Online, Draining, Offline) from its own Workers table row.

## Surface

- `WorkerService/Main.py` -- process entry point (Docker ENTRYPOINT, StartMediaVortex tab)
- `POST /api/TeamStatus/Workers/<name>/Status` -- set per-worker status
- `GET /api/TeamStatus/Workers` -- returns capability flags alongside existing worker info

## Scope

- WorkerService/**
- Scripts/SQLScripts/AddWorkerCapabilities.py

## Success Criteria

1. A single WorkerService process can transcode, run VMAF quality tests, and scan files
   based on which capability flags are enabled in its Workers row.
2. Changing a capability flag in the Workers table takes effect within 60 seconds
   without restarting the process.
3. Setting a worker's status to "Draining" causes it to finish its current job
   and stop picking up new work. Setting it to "Online" resumes work.
4. Setting a worker's status to "Offline" stops all capabilities.
5. The schema migration is idempotent -- running it multiple times produces the same result.
6. WebService no longer starts ContinuousScanService; on-demand API scanning still works.
7. Docker containers use WorkerService as their entry point.
8. StartMediaVortex.py launches WebService + WorkerService (not TranscodeService).

## Status

COMPLETE

### Progress

- [x] Schema migration (AddWorkerCapabilities.py)
- [x] WorkerService/Main.py with capability lifecycle
- [x] Per-worker status polling (5s) and capability polling (60s)
- [x] Remove ContinuousScanService from WebService/Main.py
- [x] Update Dockerfile ENTRYPOINT
- [x] Update ServiceLifecycleManager SERVICES dict
- [x] Update StartMediaVortex.py
- [x] Add POST /api/TeamStatus/Workers/<name>/Status endpoint
- [x] Update GET /api/TeamStatus/Workers to include capability flags
- [x] Feature doc
- [x] Deployed to 4 Docker workers, verified transcode jobs processing correctly
- [x] WorkerService.flow.md created
