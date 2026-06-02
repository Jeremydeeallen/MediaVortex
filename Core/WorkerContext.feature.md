# WorkerContext

**Slug:** workercontext

Process-level singleton providing per-worker configuration to all services in the process.

> **Note on path translation:** the `PathTranslation` field exposed by this singleton is the runtime side of a known workaround for OS-coupled path storage. See `memory/KNOWN-ISSUES.md` -- entry `[BUG - CRITICAL - WORKAROUND IN PLACE] Canonical path storage is OS-coupled` -- for the diagnosis, full symptom list, and the target architecture (`path-storage.feature.md`). Do not document the path-translation problem here; link to memory/KNOWN-ISSUES.md.

## Surface

Internal API only -- no UI or HTTP surface. Consumed by FFmpegService, FileReplacementBusinessService, ProcessTranscodeQueueService, and any service that needs worker-specific paths.

## Scope

- `Core/WorkerContext.py`
- Integration points: `Services/FFmpegService.py`, `Features/FileReplacement/FileReplacementBusinessService.py`, `Features/TranscodeJob/ProcessTranscodeQueueService.py`

## Success Criteria

1. WorkerContext.Initialize() is called exactly once per process at startup (WorkerService and WebService entry points).
2. WorkerContext.Current() returns the initialized context from any module in the process, or None if not initialized.
3. FFmpegService resolves FFprobe and FFmpeg paths from WorkerContext before falling back to SystemSettings. No call site needs to pass FFprobePath explicitly for the path to be correct on any platform.
4. FileReplacementBusinessService resolves PathTranslation from WorkerContext when not provided explicitly. Post-transcode re-probe and file operations use the correct worker-local paths.
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
