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
9. **Worker startup fails fast with a clear error if FFmpeg or FFprobe binaries cannot be resolved.** `_ResolveBundledOrPathBinary()` checks the project-bundled `FFmpegMaster/bin/<binary>{.exe?}` first, then `shutil.which()`. If neither yields a real binary, `_RegisterAndLoadWorkerConfig` raises `RuntimeError` before any Workers row is written. Replaces the prior silent `Workers.FFmpegPath = NULL` registration that wedged Windows hosts.
10. **Crash recovery does not terminate the running worker.** When the recorded `ActiveJobs.ProcessId` matches `os.getpid()`, the cleanup logic treats the row as a stale prior-container artifact and skips the kill step (in Docker every Python entrypoint runs as PID 1, and a naive recorded-PID match would always hit the new process). Verified by running 4 workers through restart cycles with no spurious self-termination.
11. **SignalHandler releases the shared psycopg2 pool before `os._exit()`.** Crashing-and-restarting workers no longer leak idle DB connections (atexit handlers don't run after `os._exit`).
12. **Source-file existence is verified before any TranscodeAttempt is created.** When `MediaFile.FilePath` (translated to the local mount via PathTranslation) does not exist, the worker increments `MediaFiles.FFprobeFailureCount`, records `LastFFprobeError`, deletes the TranscodeQueue row, and returns. No noisy attempt history for files deleted between scan and transcode.
13. **`ProcessTranscodeQueueService` falls back to `FFmpegService` discovery when `WorkerContext.FFmpegPath` is `NULL`.** A loud warning logs which worker name needs its DB row populated. Stops the per-job ValueError loop in CommandBuilder when a stale Workers row has NULL paths.

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
