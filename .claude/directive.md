# Directive: local-staging-cleanup-restore

**Status:** Active -- phase: IMPLEMENTING

**Slug:** local-staging-cleanup-restore

**Interrupts:** audio-remeasurement-runner-bind (Closed).

## Context

`C:\MediaVortex\` on I9 has accumulated 29 per-job scratch dirs (~55GB) with source files + `.inprogress` outputs from Aug 11+ Since June 11. Local-staging (`Workers.LocalStagingEnabled=TRUE`) copies each source to `<LocalScratchDir>\<MediaFileId>\<basename>`, encodes there, ships output back to canonical, then was supposed to remove the per-job dir.

Root cause: commit `945021c0` (2026-06-11) `refactor(worker-loop-method-extraction)` deleted the four `Process*Job` methods on `ProcessTranscodeQueueService` and moved bodies to `JobProcessor` strategies. The refactor removed the `self._CleanupLocalScratchForAttempt(Job.MediaFileId)` call sites from the deleted methods but never re-added them to the new `JobProcessor.Process` finally path. Function still exists at `ProcessTranscodeQueueService.py:1662` -- zero external callers (dead).

Second dead-code path: `TemporaryFilePathsService.CleanupLocalScratch` (line 115) same shape, zero external callers.

## Acceptance Criteria

- C1: `JobProcessor.Process` calls `LocalStagingService.CleanupJobScratchDir(WorkerName, MediaFileId)` at attempt terminal state (both Success and Exception paths). Idempotent -- no-ops when local-staging inactive for the worker.
- C2: New I9 attempts leave no residue at `C:\MediaVortex\<MediaFileId>\` post-finalization.
- C3: Existing 29 stale dirs on I9 -- one-shot cleanup script `Scripts/CleanupOrphanLocalScratch.py` walks `<LocalScratchDir>`, cross-references `TranscodeAttempts` for that MediaFileId's terminal state, removes only-terminal subdirs. Safe against in-flight jobs.
- C4: `ProcessTranscodeQueueService._CleanupLocalScratchForAttempt` (dead-code shim) deleted since `JobProcessor` calls the service directly.
- C5: `TemporaryFilePathsService.CleanupLocalScratch` (dead-code shim) deleted for the same reason.
- C6: Contract test `Tests/Contract/TestJobProcessorScratchCleanup.py` covers Success + Exception paths + no-op-when-staging-disabled.

## Call-Graph Audit

1. Multiple flow docs -- clean. transcode.flow.md is single owner.
2. Mode-branching -- clean. Cleanup runs uniformly across all modes that JobProcessor handles.
3. Shared-column sparse -- root cause is dead-code call sites; N/A.
4. Config-driven graph -- clean. `LocalStagingEnabled` flag changes DATA (whether staging fires) not orchestration -- cleanup calls into LocalStagingService which no-ops when config off.
5. OOS explicit below.

## Out of Scope

- (a) `WorkerService.PrivateOrphanCleanupLoop` catch-all sweep. Existing sweep is DB-orphan focused; adding a directory-orphan sweep is a defense-in-depth follow-up.
- (a) VariantJobProcessor scratch dirs (test-mode variants) -- follow separate code path; not affected by this bug.
- (b) Historical 55GB on I9 -- one-shot script (C3) drains; not a design change.

## Files

**Edit:**
- `Features/TranscodeJob/Worker/JobProcessor.py` (call CleanupJobScratchDir in finally block)
- `Features/TranscodeJob/ProcessTranscodeQueueService.py` (delete `_CleanupLocalScratchForAttempt` shim)
- `Features/TranscodeJob/Worker/TemporaryFilePathsService.py` (delete `CleanupLocalScratch` shim)

**Create:**
- `Scripts/CleanupOrphanLocalScratch.py`
- `Tests/Contract/TestJobProcessorScratchCleanup.py`

## Status

Phase: NEEDS_STANDARDS_REVIEW
Opened: 2026-08-17
Owner: claude-opus-4-7
