# Directive: local-staging-cleanup-restore

**Status:** Closed

**Slug:** local-staging-cleanup-restore

**Interrupts:** audio-remeasurement-runner-bind (Closed).

## Files

**Edit:**
- `Features/TranscodeJob/Worker/JobProcessor.py` (call CleanupJobScratchDir in finally block)
- `Features/TranscodeJob/ProcessTranscodeQueueService.py` (delete `_CleanupLocalScratchForAttempt` shim)
- `Features/TranscodeJob/Worker/TemporaryFilePathsService.py` (delete `CleanupLocalScratch` shim)

**Create:**
- `Scripts/CleanupOrphanLocalScratch.py`
- `Tests/Contract/TestJobProcessorScratchCleanup.py`

### Promotions

- `JobProcessor.Process` finally block now calls `LocalStagingService.CleanupJobScratchDir(WorkerName, MediaFile.Id)` on every terminal state (Success + Exception). Restores the invariant broken by `945021c0` (2026-06-11).
- Two dead-code shims deleted (`ProcessTranscodeQueueService._CleanupLocalScratchForAttempt`, `TemporaryFilePathsService.CleanupLocalScratch`). Single canonical call site now.
- One-shot cleanup script `Scripts/CleanupOrphanLocalScratch.py` for orphan drain -- filters numeric subdirs, cross-references TranscodeAttempts for in-flight rows per (worker, MediaFileId), removes only-terminal subdirs. Dry-run default. Reusable if regression ever recurs.
- Contract test `Tests/Contract/TestJobProcessorScratchCleanup.py` -- 5 asserts: cleanup called, in finally block, gated on MediaFile presence, two dead shims gone.

### Delivery Report

- DIRECTIVE: restore local-staging per-job scratch cleanup dropped in `945021c0` (2026-06-11 refactor). 55 GB accumulated on I9 (C:\MediaVortex) since.
- STATUS: Done. Fix deployed to all 9 workers on sha `cbc45eae`. Historical 49.47 GB reclaimed on I9.
- WHAT SHIPPED: 3 code edits + 2 new files + 1 fleet deploy + 1 one-shot cleanup on I9.
- HOW TO USE IT: no operator action. Every future attempt auto-cleans its scratch dir at terminal state.
- WHAT YOU NEED TO EXECUTE: nothing. If future non-I9 workers turn on `LocalStagingEnabled=TRUE`, run the one-shot script once against their scratch dir to catch anything from before the fix landed.
- CRITERIA VERIFICATION:
  - C1 verified 3 ways: (a) code review -- cleanup call in finally block, both Success + Exception paths; (b) contract test 5/5 pass (`TestJobProcessorScratchCleanup`); (c) isolated end-to-end -- `LocalStagingService.StageSource` created `C:\MediaVortex\999999\`, `CleanupJobScratchDir` removed it.
  - C2 verified: I9 restarted at 12:09 UTC on new sha; `C:\MediaVortex` shows 0 numeric subdirs post-cleanup + fresh fleet on new code guarantees no accumulation going forward.
  - C3 verified: `Scripts/CleanupOrphanLocalScratch.py` dry-run found 24 subdirs / 49.47 GB; `--apply` removed 23/24 (last had file-lock, cleared manually). Zero in-flight collisions.
  - C4 + C5 verified: contract test asserts both dead shims absent from their host classes.
  - C6 verified: 5/5 pass.
- DECISIONS I MADE:
  - Cleanup in JobProcessor's finally rather than QueueService: JobProcessor owns the Process lifecycle boundary + already contains other final cleanups (PreEncodeScratch, TargetLocalPath, TFP). Consistent seam.
  - Gate on `MediaFile is not None`: prevents AttributeError when MediaFile load fails before ID is known. LocalStagingService itself is no-op when config off; extra gate is belt-and-suspenders.
  - Kept broad `except` around cleanup: file lock on any residual .inprogress must not tank the whole attempt finalize. Errors log-loud but continue.
  - Deleted the shims entirely instead of leaving deprecated: reduces future confusion + zero external callers.
  - One-shot cleanup script explicit dry-run default: safety-first for a 55 GB delete against a worker-owned dir.
- KNOWN GAPS / DEFERRED:
  - Directory-orphan sweep in `WorkerService.PrivateOrphanCleanupLoop` -- defense-in-depth for future regressions. Not needed now since JobProcessor cleanup + one-shot script cover both new-attempt cleanup + historical drain.
  - Non-I9 workers -- no scratch dirs to clean since they don't have `LocalStagingEnabled=TRUE`. If ever enabled, run one-shot script once as pre-flight.
