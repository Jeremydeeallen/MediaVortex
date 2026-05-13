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
14. [BUG] **Per-worker capability flags (`TranscodeEnabled`, `QualityTestEnabled`, `ScanEnabled`) are editable from the web UI.** Today they exist as columns on the `Workers` table and are read by the `_CapabilityPollingLoop` (60s interval), but no API endpoint or template control writes them -- the operator has to run raw SQL (`UPDATE Workers SET ScanEnabled=true WHERE WorkerName='I9-2024'`) to change them. Fixed = each row on the Activity page worker list (or a dedicated control on the Settings page) has three toggle controls (transcode / quality test / scan), saving each toggle persists to the corresponding Workers column via a POST endpoint, and the worker's capability poller picks up the change within 60s. The existing Online/Draining/Offline status buttons on Activity provide the precedent for the same per-worker pattern.
16. **Per-capability concurrency is read from dedicated Workers columns.** `MaxConcurrentTranscodeJobs` (default 1, CPU-bound), `MaxConcurrentQualityTestJobs` (default 2, I/O-bound VMAF), and `MaxConcurrentRemuxJobs` (default 2, I/O-bound container copy) each control their respective capability's thread pool. Setting `Workers.MaxConcurrentQualityTestJobs=3` for a worker causes that worker's quality test loop to run up to 3 concurrent VMAF jobs. The legacy `MaxConcurrentJobs` column is preserved but no longer read.
17. **Remux is a separate capability with its own queue service and concurrency.** `ProcessRemuxQueueService` claims only `ProcessingMode='Remux'` rows from TranscodeQueue. `ProcessTranscodeQueueService` excludes remux rows from its claim query. The `RemuxEnabled` column on Workers controls whether a worker picks up remux jobs (default TRUE). Remux concurrency is independent of transcode concurrency.
18. [BUG] **Per-capability concurrency changes take effect within 60 seconds without restarting the worker process (data-driven contract).** When the operator changes `MaxConcurrentTranscodeJobs`, `MaxConcurrentQualityTestJobs`, or `MaxConcurrentRemuxJobs` in the Workers table (via Settings UI or direct DB update), the running worker's capability polling loop detects the new value and adjusts the running thread pool size on its next cycle. If concurrency increases from 1 to 2, an additional consumer thread starts claiming jobs immediately. If concurrency decreases from 3 to 1, excess threads finish their current job and do not claim new ones. No restart required. Verifiable: with a worker running 1 transcode thread, `UPDATE Workers SET MaxConcurrentTranscodeJobs=2` and observe a second job claimed within 60 seconds.
15. [BUG] **`QualityTestEnabled` flips reach the running `ProcessTranscodeQueueService` within the 60s capability-poll window (criterion 2 contract).** Today the worker only refreshes capabilities at the *capability lifecycle* level (start/stop `QualityTestService` consumer), but the *transcode producer's* gate (`ProcessTranscodeQueueService.WorkerQualityTestEnabled`) is read once from the `WorkerConfig` snapshot at service construction and never refreshed. Result: a worker that started with `QualityTestEnabled=False` keeps writing `TranscodeAttempts.QualityTestRequired=False` after a successful transcode even after the DB row flips to True, so `ShouldQualityTestService.ProcessTranscodedFile` calls `_ReplaceFileDirectly` (BypassVMAFCheck=True) -- the original is deleted and the next queue item starts, with no VMAF protection. A separate trap at `Features/TranscodeJob/ProcessTranscodeQueueService.py:100-101` (`Config.get('QualityTestEnabled') or Config.get('qualitytestenabled')`) silently treats a stored `False` per-worker value the same as an explicit override and shadows the global setting; a missing key collapses to `None` and falls through. Fixed = (a) `IsQualityTestEnabled()` returns the live Workers-row value (or its global fallback) on every call, with the per-worker override path distinguishing "explicit False" from "use global" using a tri-state load (e.g. column read returning None vs True vs False) instead of `a or b`; (b) toggling `Workers.QualityTestEnabled` between two transcodes on a running worker causes the *next* completed transcode to enqueue (or skip) a quality test according to the new value, without restart; (c) regression test or DB-verifiable check confirms a `False -> True` flip mid-run results in `TranscodeAttempts.QualityTestRequired=True` on the very next attempt's success row.

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
