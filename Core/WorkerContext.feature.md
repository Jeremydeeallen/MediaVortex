# WorkerContext

**Slug:** workercontext

Process-level singleton providing per-worker configuration to all services in the process.

> **Note on path translation:** the legacy `PathTranslation` field was removed by `path-perfect-implementation` Step 3 (2026-06-05). Per-worker mount resolution now goes through `Core/Path/Worker.ResolveStorageRoot(StorageRootId) -> AbsolutePath` reading `StorageRootResolutions`. Inverse lookup (local string -> typed `Path`) is `Worker.LocalToPath(local_str)`. See `path.feature.md` Seams S11 (Worker resolution) and S10 (PathFs filesystem ops).

## Surface

Internal API only -- no UI or HTTP surface. Consumed by FFmpegService, FileReplacementBusinessService, ProcessTranscodeQueueService, and any service that needs worker-specific paths.

## Scope

- `Core/WorkerContext.py`
- Integration points: `Services/FFmpegService.py`, `Features/FileReplacement/FileReplacementBusinessService.py`, `Features/TranscodeJob/ProcessTranscodeQueueService.py`

## Success Criteria

1. WorkerContext.Initialize() is called exactly once per process at startup (WorkerService and WebService entry points).
2. WorkerContext.Current() returns the initialized context from any module in the process, or None if not initialized.
3. FFmpegService resolves FFprobe and FFmpeg paths from WorkerContext before falling back to SystemSettings. No call site needs to pass FFprobePath explicitly for the path to be correct on any platform.
4. FileReplacementBusinessService resolves worker-local paths via `Path.Resolve(Worker.FromWorkerContext())` for the typed-pair source + output rows read from TemporaryFilePaths. Post-transcode re-probe and file operations use the correct worker-local paths; existence checks go through `PathFs.Exists(P, Worker)` per `path.S10`.
5. A Linux worker running WorkerService gets FFprobe/FFmpeg paths from the Workers table (via WorkerContext), not from SystemSettings. MediaFiles records are updated correctly after file replacement.

## Status

COMPLETE

### Progress

- [x] Created Core/WorkerContext.py singleton
- [x] FFmpegService reads from WorkerContext before SystemSettings
- [x] WorkerService/Main.py calls WorkerContext.Initialize()
- [x] WebService/Main.py calls WorkerContext.Initialize()
- [x] FileReplacementBusinessService auto-reads PathTranslation from WorkerContext
- [x] ProcessTranscodeQueueService simplified to use WorkerContext
