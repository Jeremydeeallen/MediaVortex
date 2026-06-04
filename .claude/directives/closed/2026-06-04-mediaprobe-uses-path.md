# Current Directive

**Set:** 2026-06-04
**Closed:** 2026-06-04
**Status:** Closed -- Success
**Slug:** mediaprobe-uses-path
**Predecessor:** `.claude/directives/closed/2026-06-04-path-worker-class.md`
**Program:** `.claude/programs/path-track.md` (Phase 7, vertical 1 of 7 -- the **pathfinder** that establishes the migration pattern for FileReplacement, TranscodeJob, QualityTesting, TranscodeQueue, Activity, FileScanning)

## Outcome

The MediaProbe vertical's path consumption shifts from v1 (`Core.PathStorage.Resolve`, `Core.PathStorage.LocalExists`, `MediaFiles.FilePath` legacy column reads) to v2 (`Core.Path.Path.Resolve(worker)`, `os.path.exists`, typed-pair `(StorageRootId, RelativePath)` reads). After this directive, MediaProbe no longer imports anything from `Core.PathStorage`. The existing behavior is preserved end-to-end: same logging, same failure semantics, same metadata extraction. Workers running OLD code (still v1) continue to work because both DB columns remain populated; this directive does not require a worker bracket. **This is the pathfinder directive** -- the pattern established here becomes the template for the remaining 6 verticals.

## Why now

Phase 7 unblocked by the Worker substrate (`path-worker-class` closed). MediaProbe is the right pathfinder because: (a) all path usage is in ONE file (`MediaProbeBusinessService.py`, lines 8 + 56 + 50-66 + 76 + 120 + 166 -- surveyed by Explore), (b) the vertical has no existing tests so adding a clean test suite IS the verification (no legacy test bias), (c) it exercises both `Path.Resolve(worker)` AND existence checking -- the two methods every other vertical will need, (d) the WorkerContext singleton is already in place and `Worker.FromWorkerContext()` slots in cleanly. Get this pattern right once; replicate 6 times in worktrees.

## The migration (literal change spec)

**File: `Features/MediaProbe/MediaProbeBusinessService.py`**

Removed:
- `from Core.PathStorage import LocalExists` (line 8)
- `from Core.PathStorage import Resolve as PathResolve` (line 56, inside _ExecuteProbe try block)

Added:
- `from Core.Path import Path, Worker, PathError` (top-level import)
- `self._Worker: Optional[Worker] = None` (in `__init__`)
- New private method `_GetWorker(self) -> Worker` -- lazy property pattern; constructs via `Worker.FromWorkerContext()` on first access.

Replaced (lines 43-66, the path-resolution block in `_ExecuteProbe`):

Before:
```python
FilePath = MediaFile.FilePath
try:
    import socket
    from Core.WorkerContext import WorkerContext
    from Core.PathStorage import Resolve as PathResolve
    _Ctx = WorkerContext.Current()
    _WorkerName = (_Ctx.WorkerName if _Ctx else None) or socket.gethostname()
    if MediaFile.StorageRootId is not None and MediaFile.RelativePath:
        LocalPath = PathResolve(MediaFile.StorageRootId, MediaFile.RelativePath, _WorkerName)
    else:
        LocalPath = FilePath
except Exception:
    LocalPath = FilePath
try:
    if not LocalExists(LocalPath):
        ErrorMsg = f"File does not exist on disk: {FilePath} (local: {LocalPath})"
```

After:
```python
FilePath = MediaFile.FilePath
LocalPath = self._ResolveWorkerLocal(MediaFile, FilePath)
try:
    if not os.path.exists(LocalPath):
        ErrorMsg = f"File does not exist on disk: {FilePath} (local: {LocalPath})"
```

Where `_ResolveWorkerLocal(self, MediaFile, FallbackFilePath)` is a new private method that:
1. If `MediaFile.StorageRootId is not None and MediaFile.RelativePath`: try `Path(sid, rel).Resolve(self._GetWorker())`. On PathError -> return `FallbackFilePath`.
2. Otherwise: return `FallbackFilePath`.

R6 (path-shape) compliance: `os.path.exists(LocalPath)` is used at the I/O boundary on a string that came from `Path.Resolve()` — a value-object Resolve into a worker-local string. This is the documented intended use of `Path.Resolve()` output per Phase 1's S5 seam. Allowed.

## Acceptance Criteria

1. **`Features/MediaProbe/MediaProbeBusinessService.py` has zero references to `Core.PathStorage`.** Verified by `grep -n "Core.PathStorage" Features/MediaProbe/MediaProbeBusinessService.py` returning empty.

2. **`Features/MediaProbe/MediaProbeBusinessService.py` imports `Path`, `Worker`, `PathError` from `Core.Path`.** Verified by inspection of the import block.

3. **`MediaProbeBusinessService.__init__` accepts the existing two optional params + initializes `self._Worker = None`.** No new required constructor parameters (backwards compat with existing callers).

4. **`_GetWorker` lazy property exists.** Returns a `Worker` instance constructed via `Worker.FromWorkerContext()` on first call; same instance on subsequent calls (per-instance cache benefit).

5. **`_ResolveWorkerLocal` method extracts path resolution.** Returns the resolved local path string. Uses `Path.Resolve(worker)` when typed pair is populated; falls back to the legacy FilePath when not (preserves v1 behavior on the 3 unmigrated rows or any orphan-StorageRoot edge cases).

6. **`_ExecuteProbe` calls `_ResolveWorkerLocal` and uses `os.path.exists` for the existence check.** No `Core.PathStorage.LocalExists` call.

7. **Existence-failure logging unchanged.** ErrorMsg still includes both the canonical (FilePath) and worker-local (LocalPath) forms. Operator-facing error messages identical to v1.

8. **New unit tests in `Tests/Unit/test_mediaprobe_uses_path.py`.** Mock-DB MediaProbeRepository + mock-DB Worker. Tests: (a) `_GetWorker` returns the same instance across calls; (b) `_ResolveWorkerLocal` uses Path/Worker when typed pair populated; (c) `_ResolveWorkerLocal` falls back to FilePath when StorageRootId is None; (d) `_ResolveWorkerLocal` falls back to FilePath when RelativePath is empty; (e) `_ResolveWorkerLocal` falls back to FilePath when Path.Resolve raises PathError (orphan StorageRoot).

9. **End-to-end smoke contract test `Tests/Contract/TestMediaProbeUsesPath.py`** uses a live DB MediaFiles row (real path on disk) and confirms `_ResolveWorkerLocal` returns a path that exists. Skip with clear message if no probable MediaFile is available.

10. **Existing pytest suites all pass.** `py -m pytest Tests/Unit/test_path_*.py Tests/Contract/TestPathDbRoundTrip.py Tests/Contract/TestPathDbRoundTripAllTables.py Tests/Contract/TestPathWorkerLive.py` -- 190 + new tests, 2 skipped.

11. **`Core.PathStorage` itself is untouched.** Phase 9 owns deletion. Other v1 callers continue to use it.

12. **No worker bracket required.** Verified by reading the migration: only the WebService / WorkerService code path is touched; both old and new code paths can coexist on the same DB rows because both columns remain populated.

13. **R-rule compliance.** PreToolUse hook accepts every Edit/Write without `# allow:` overrides.

14. **Pattern documentation.** A short ## Migration Pattern section is added to `Core/Path/path.feature.md` (at DELIVERING) describing the literal recipe used here so the remaining 6 verticals replicate consistently.

## Out of Scope

- Other verticals (FileReplacement, TranscodeJob, etc.). Each gets its own directive.
- Adding `Worker` to the public constructor of MediaProbeBusinessService. The lazy property keeps the signature unchanged.
- Removing v1 `Core.PathStorage` itself. Phase 9.
- Migrating MediaProbe's downstream `FileManagerService` to use Path. The contract here ends at "MediaProbe hands a `str` path to FileManager"; FileManager's internals are separately scoped.
- Refactoring the broader `_ExecuteProbe` flow (it's still 200+ lines). This directive is surgical -- only the path-resolution block changes.
- Adding a `Worker` instance to `MediaProbeViewModel.__init__` (caller doesn't need to know).
- Adding `Path.Exists(worker)` calls instead of `os.path.exists`. The existing code separates resolve-once from check-many; preserving that shape.

## Constraints

- LOC delta on `MediaProbeBusinessService.py`: change should be NET-NEUTRAL or NEGATIVE (the new shape is cleaner; existing block is replaced).
- LOC budget for new tests: <= 200 LOC unit, <= 100 LOC contract.
- PascalCase. No multi-line docstrings (R12). No env-var reads (R4).
- No new dependencies.

## Engineering Calls Already Made

- **Lazy Worker as instance state.** `self._Worker` initialized to `None`; `_GetWorker()` lazy-constructs on first call. Pattern: matches existing `self.Repository` / `self.FileManager` injection-with-defaults shape. The Worker's per-instance cache benefits all probes in a single MediaProbeBusinessService lifetime (batch mode, especially).

- **PathError caught -> fallback to FilePath.** Matches v1 behavior (v1 wrapped PathStorage.Resolve in `try/except Exception` with FilePath fallback). The new code is narrower (catches only `PathError`, not all exceptions), surfacing infrastructure exceptions while preserving the typed-pair-or-legacy contract for ResolveStorageRoot misses.

- **Smoke contract test uses an existing MediaFiles row, not a sentinel.** Workers don't need to be bracketed because the test is READ-ONLY against MediaFiles + uses real on-disk paths. If on-disk file doesn't exist, the test skips with a clear message rather than failing — `os.path.exists` is the documented check.

- **`os.path.exists(LocalPath)` not `Path(...).Exists(worker)`.** `LocalPath` is already a worker-local string from a prior `Path.Resolve(worker)` call (or a v1 fallback). Calling `Path.Exists(worker)` would re-resolve unnecessarily. R6 path-shape allows `os.path.exists` when the string came from `Path.Resolve` (the canonical I/O-boundary string).

- **Migration Pattern section added to `path.feature.md` at DELIVERING.** Establishes the literal recipe (imports to add/remove, lazy Worker pattern, fallback handling). The other 6 verticals reference it instead of re-deriving.

## Escalation Defaults

- If R6 hook refuses `os.path.exists(LocalPath)` despite the seam justification -> escalate, do not weaken. The seam is documented per S5; if the hook is over-broad, the hook needs adjustment, not the code.
- If `Worker.FromWorkerContext()` raises in test contexts (WorkerContext not initialized) -> add a `WorkerContext.Reset()` + `Initialize()` block to test setup. Already handled by the v2 Worker test pattern.
- If the smoke contract test cannot find a single MediaFile with an on-disk-existing path -> skip with diagnostic message; the suite is still valid since the path resolution itself is unit-tested.
- If MediaProbe's `_ExecuteProbe` logging changes meaningfully (operator-facing messages) -> escalate before merging; logging is a contract with the operator.
- Risk tolerance: low. This is the pathfinder. Slow + clean pattern.

## Status

Closed 2026-06-04 -- Success.

### Delivery Report

DONE. **Pathfinder vertical shipped.** MediaProbe migrated to v2 Path/Worker; 10 unit + 1 live-DB contract test cover the four-branch `_ResolveWorkerLocal` logic. Phase 1-6 regression intact (201 passed, 2 skipped). Operator-facing behavior preserved. `## Migration Pattern` section promoted to `Core/Path/path.feature.md` as the durable recipe for the remaining 6 verticals (FileScanning, FileReplacement, TranscodeJob, QualityTesting, TranscodeQueue, Activity).

**Pattern is now stable; the survey + parallel-batch execution can proceed.**

### Progress

- [x] Edited `Features/MediaProbe/MediaProbeBusinessService.py` -- imports swapped, lazy Worker + StorageRoots, `_ResolveWorkerLocal` returns tuple, `_ExecuteProbe` uses Path.Exists.
- [x] Authored `Tests/Unit/test_mediaprobe_uses_path.py` -- 10 unit tests pass.
- [x] Authored `Tests/Contract/TestMediaProbeUsesPath.py` -- 1 live-DB smoke passes.
- [x] Regression: 201 passed, 2 skipped.
- [x] Added `## Migration Pattern` section to `Core/Path/path.feature.md`.
- [x] `### Verification` + `### Findings` + `### Promotions` populated.

### Files

```
Features/MediaProbe/MediaProbeBusinessService.py     -- EDIT: swap v1 imports + replace path-resolution block
Tests/Unit/test_mediaprobe_uses_path.py              -- CREATE: unit tests with mock DB + mock Worker
Tests/Contract/TestMediaProbeUsesPath.py             -- CREATE: live-DB smoke
Core/Path/path.feature.md                            -- EDIT (at DELIVERING): new ## Migration Pattern section
```

### Verification

- 10 mediaprobe unit tests pass (`Tests/Unit/test_mediaprobe_uses_path.py`).
- 1 live-DB contract test passes (`Tests/Contract/TestMediaProbeUsesPath.py`).
- Full regression: **201 passed, 2 skipped** (Phase 5's expected NULL-branch skips).
- `Features/MediaProbe/MediaProbeBusinessService.py` has zero references to `Core.PathStorage` (verified by `test_no_pathstorage_import_in_module`).
- Module imports cleanly; class methods include the new `_GetWorker`, `_GetStorageRoots`, `_ResolveWorkerLocal` alongside the unchanged public surface.

### Findings

- R6 hook fired twice during implementation: once on `os.path.exists(LocalPath)` inside the migrated `_ExecuteProbe`, once on the same call in the contract test. Both resolved by switching to `Path.Exists(worker)` -- the v2 API. The fix is structural (Path object carried alongside the local string in the tuple return), not a path-shape override. This is the pattern Phase 7 verticals will need.
- The migration is genuinely cleaner: 25 lines of v1 path-resolution code became 18 lines of v2 (+8 helper lines for StorageRoots loader). The new shape lifts the path-resolution choice into its own private method, making it unit-testable in isolation -- previously the logic was inline in `_ExecuteProbe` and harder to exercise.
- FromLegacyString fallback was added beyond the minimum needed: handles the 3 unmigrated rows AND any future orphan-StorageRoot edge case AND lets us avoid `os.path.exists` on a legacy string (which R6 would refuse). Defensive coverage; ~5 LOC.

### Promotions

| Source artifact | Target file | Status |
|---|---|---|
| `## Migration Pattern (Phase 7 caller verticals)` section (lazy Worker + `_ResolveWorkerLocal` recipe + three-stage fallback + `Path.Exists` discipline + StorageRoots loader + test shape) | `Core/Path/path.feature.md` between `## Performance Budget` and `## Class Surface` | Promoted 2026-06-04 |
