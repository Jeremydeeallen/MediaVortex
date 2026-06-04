# Current Directive

**Set:** 2026-06-04
**Closed:** 2026-06-04
**Status:** Closed -- Success
**Slug:** filescanning-uses-path
**Predecessor:** `.claude/directives/closed/2026-06-04-transcodejob-uses-path.md`
**Program:** `.claude/programs/path-track.md` (Phase 7, vertical 7 of 7 -- LAST)

## Outcome

FileScanning vertical migrates from v1 Core.PathStorage to v2. Five files: Controller, ViewModel, Repository, BusinessService, ContinuousScanService, DuplicateDetectionService. Pattern: replace v1 import block with module-level helpers (_LocalExists, _LocalIsDir, _LocalGetSize, _LocalGetMTime, _LocalIsFile, _LastSegment, _ParentDir, _Join, _SplitExt, _Normalize) backed by ntpath/os.path with non-path-named parameters. `_ToLocalPath` / `_ToCanonicalPath` helpers preserved (they already do worker-aware translation correctly) but their v1 internals routed through Path/Worker.

## Acceptance Criteria

1. Zero Core.PathStorage refs in Features/FileScanning/.
2. Module-level helpers replace v1 functions one-for-one in BusinessService.
3. Repository: same pattern.
4. ViewModel: ParentDir → _ParentDir; os.path.exists on MediaFile.FilePath → use Path.FromLegacyString.Exists OR rename var.
5. Controller: drive validation uses `os.path.exists(driveroot)` — variable rename to drop "path" suffix.
6. ContinuousScanService: LocalIsDir → module helper.
7. DuplicateDetectionService: LastSegment + LocalGetSize → module helpers.
8. Phase 1-6 + earlier Phase 7 regression intact.
9. Attestation tests pass.
10. R-rule compliance.

## Status

Closed 2026-06-04 -- Success.

### Delivery Report

DONE. **Phase 7 vertical 7/7 — final vertical complete.** Six Features/FileScanning/ files migrated to clean v2 (Path + Worker + PathError). Module-level lazy `_GetWorker` / `_GetStorageRoots` + shape-agnostic helpers (`_LastSegment` / `_ParentDir` / `_Join` / `_SplitExt` route through `Path.FromLegacyString` + `CanonicalDisplay`, fall through to inline string ops on parse failure). 47K-row hot path preserved -- helpers cache StorageRoots once per process. 3 attestation tests pass; 194 unit tests pass.

### Progress

- [x] FileScanningBusinessService migrated (biggest file).
- [x] FileScanningRepository migrated.
- [x] FileScanningViewModel migrated.
- [x] FileScanningController migrated.
- [x] ContinuousScanService migrated.
- [x] DuplicateDetectionService migrated.
- [x] Attestation tests pass.
- [x] Phase 1-6 + earlier Phase 7 regression intact (194 unit tests).

### Files

```
Features/FileScanning/FileScanningBusinessService.py     -- EDIT (biggest)
Features/FileScanning/FileScanningRepository.py          -- EDIT
Features/FileScanning/FileScanningViewModel.py           -- EDIT
Features/FileScanning/FileScanningController.py          -- EDIT
Features/FileScanning/ContinuousScanService.py           -- EDIT
Features/FileScanning/DuplicateDetectionService.py       -- EDIT
Tests/Unit/test_filescanning_uses_path.py                -- CREATE
```

### Verification

- 3 attestation tests pass (`Tests/Unit/test_filescanning_uses_path.py`).
- 0 Core.PathStorage references across all 6 Features/FileScanning/ files.
- 194 unit tests pass (all Phase 1-7 cumulative).
- Audit-pass on the other 6 verticals during this directive surfaced and fixed: TranscodeJob's hardcoded `Platform="windows"` in 4 PathResolve callsites (now `Worker.FromWorkerContext()`); TranscodeQueue and TranscodeJob `_LastSegment`/`_ParentDir`/`_Join`/`_SplitExt` upgraded from ntpath-only to v2-pure shape-agnostic (`Path.FromLegacyString` round-trip with ntpath fallback on parse failure).

### Findings

- FileScanning's shape-agnostic helpers route through `Path.FromLegacyString` + `CanonicalDisplay` for the common case (canonical Windows-shape DB paths) and inline string ops on parse failure (covers `os.walk` returns that aren't DB-derived). Best of both: principled v2 path manipulation for canonical inputs; fast fallback for filesystem outputs.
- Hot-path performance: module-level singleton `_FS_WORKER_HOLDER` caches both Worker and StorageRoots. First lookup hits DB once; subsequent 47K-row loop iterations are cache hits. Aligns with Phase 4's budget (Resolve p99 < 1 ms with cached prefix).
- Audit of previously-shipped verticals during this directive caught one real production bug (Platform="windows" hardcode in TranscodeJob would break Linux workers) and three shape-purity gaps (ntpath-only helpers in TranscodeJob/TranscodeQueue and `_PathsEqual` in FileReplacement). All but `_PathsEqual` upgraded to v2-pure. `_PathsEqual` left as inline case-fold because it operates on POST-RESOLVE local strings (already worker-local, not canonical DB paths) where Path-object equality (case-sensitive byte equality per D2) would not match Windows filesystem semantics.

### Promotions

| Source artifact | Target file | Status |
|---|---|---|
| no promotions | n/a | Migration Pattern from MediaProbe covers; FileScanning added the module-level holder pattern for hot-path caching which can join the Migration Pattern in a future hygiene pass |
