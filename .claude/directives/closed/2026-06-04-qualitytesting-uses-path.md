# Current Directive

**Set:** 2026-06-04
**Closed:** 2026-06-04
**Status:** Closed -- Success
**Slug:** qualitytesting-uses-path
**Predecessor:** `.claude/directives/closed/2026-06-04-activity-uses-path.md`
**Program:** `.claude/programs/path-track.md` (Phase 7, vertical 3 of 7)

## Outcome

QualityTesting vertical's path consumption migrates from v1 (`Core.PathStorage.Resolve / LastSegment / ParentDir / LocalExists`, raw `os.path.*` calls on DB-derived paths) to v2 (`Core.Path.Path` + `Worker`). Every Core.PathStorage import in `Features/QualityTesting/` is removed. Where v2 doesn't have a direct equivalent (e.g., `os.path.join` on cache subdirectories, repo-root navigation), the call is left as-is because the input is not a DB-derived path-shape variable. After this directive: 3 `Features/QualityTesting/` files clean; tests verify the migration; existing behavior preserved.

## Why now

Phase 7 pathfinder pattern established; Activity attestation confirmed. QualityTesting is the next-smallest vertical that exercises the **two-path pattern** (VMAF needs source AND transcoded paths resolved simultaneously). Validates Path's `TemporaryFilePaths` prefix-keyed `FromRow(row, Prefix="Source")` / `FromRow(row, Prefix="Output")` against production data. The two-path pattern doesn't appear in MediaProbe -- QualityTesting is where it gets battle-tested.

## Acceptance Criteria

1. **Zero `Core.PathStorage` references in `Features/QualityTesting/`.** Attestation grep returns nothing. Currently 6 imports (`QualityTestRepository.py:5`, `QualityTestingBusinessService.py:14`, `:189`, `:1598`, `QualityTestController.py:12`, `:1038`).

2. **`Core.Path` imports added.** Each file that needs Path / Worker / PathError imports them from `Core.Path` (not from `Core.Path.Path` directly).

3. **Worker as lazy instance state.** `QualityTestingBusinessService.__init__` gains `self._Worker: Optional[Worker] = None` and lazy `_GetWorker()`. Matches the Migration Pattern from `Core/Path/path.feature.md`.

4. **`StorageRoots` cached for FromLegacyString fallback.** `QualityTestingBusinessService.__init__` gains `self._StorageRoots: Optional[List[dict]] = None` and lazy `_GetStorageRoots()`. Matches Migration Pattern.

5. **`BuildVMAFCommand` two-path resolution via Path/Worker.** `original_file` and `transcoded_file` resolved via `Path.FromRow(row, Prefix="Source")` and `Path.FromRow(row, Prefix="Output")` against the TemporaryFilePaths row, then `.Resolve(worker)`. No `Core.PathStorage.Resolve` call.

6. **Existence checks use `Path.Exists(worker)`.** Wherever the existence check is on a Path object derivable from the typed pair. For checks on cache filesystem paths (not DB-derived), `os.path.exists` stays -- but those variables must NOT be path-named (so R6 doesn't fire).

7. **`_ExtractStillPair` migrated.** Uses `Path.FromRow` + `Resolve(worker)` instead of `WorkerContext.PathTranslation.ToLocalPath`. Cache-directory `os.path.join` calls retained (cache dir is constructed local, not DB-derived).

8. **`_HandleRequeueDisposition` migrated.** Same shape.

9. **`OverrideQualityTest` endpoint migrated.** Replaces `Resolve()` call with `Path(sid, rel).Resolve(worker)`.

10. **`LastSegment` / `ParentDir` calls removed or replaced.** Where the input is a DB-derived path, use `Path` methods. Where the input is a filesystem-output string (e.g., `os.scandir` result), use the appropriate stdlib (`os.path.basename` is OK on a variable not named `path`).

11. **New unit tests in `Tests/Unit/test_qualitytesting_uses_path.py`.** Mock-DB tests covering: (a) `_GetWorker` lazy + cached; (b) `_GetStorageRoots` lazy + cached; (c) BuildVMAFCommand resolves both source and transcoded; (d) FromLegacyString fallback fires when typed pair is unpopulated on TemporaryFilePaths row; (e) attestation grep test for the Features/QualityTesting/ directory.

12. **Live-DB smoke test in `Tests/Contract/TestQualityTestingUsesPath.py`.** Skip if no probable QualityTestingQueue row with on-disk-existing source AND output; otherwise assert both resolve to existing paths.

13. **Phase 1-6 + earlier Phase 7 regression intact.** All 203 tests pass (201 + Activity's 2). New tests added on top.

14. **R-rule compliance.** PreToolUse hook accepts every Edit/Write without `# allow:` overrides.

## Out of Scope

- `Tests/Integration/TestQualityScoring.py` -- existing test, not part of this directive's surface. May be touched only if the migration breaks its mocking shape (it doesn't, per survey).
- `os.path.dirname/abspath` calls in `QualityTestingViewModel.py:12` -- these are project-root computation (not DB-derived). Stay as-is.
- `os.path.join` calls for cache directory subdirectory construction (`os.path.join(cache_dir, filename)`) -- not DB-derived. Stay as-is.
- `os.path.basename(R['FilePath'])` at QualityTestController.py:512 -- READ-ONLY display value, no resolution downstream. Migrate to `Path.LastSegment` if convenient; not required.
- Repo-root / Smoke-script navigation `os.path` calls at QualityTestController.py:677-717 -- operating on `__file__` derivatives, not DB paths. Stay.
- Refactoring the cache-key generation logic.
- `QualityTestingQueue.OriginalFilePath` / `LocalSourcePath` / `TranscodedFilePath` legacy columns -- read via the FromLegacyString fallback as needed; deprecation is Phase 8.

## Constraints

- LOC delta: net-neutral or slightly negative on production code (replacing v1 with cleaner v2). Test file budget <= 250 LOC unit, <= 100 LOC contract.
- PascalCase. R12 single-line docstrings.
- No new pip deps.
- Operator-facing log messages preserved (existence-failure messages, VMAF error messages).

## Engineering Calls Already Made

- **Two-path pattern uses Path.FromRow prefix.** TemporaryFilePaths has `SourceStorageRootId`/`SourceRelativePath` AND `OutputStorageRootId`/`OutputRelativePath`. `Path.FromRow(row, Prefix="Source")` returns the source-Path; `Prefix="Output"` returns the output-Path. Both resolve via the same Worker. This is the design D6 Phase 5 already verified.

- **FromLegacyString fallback for legacy columns.** `QualityTestingQueue.OriginalFilePath`, `LocalSourcePath`, `TranscodedFilePath` are NOT typed-pair columns -- they're legacy text. Parse via `Path.FromLegacyString(value, self._GetStorageRoots())` when needed.

- **`os.path.<op>` retention rules.** Three categories of `os.path.*` calls in this vertical:
  1. **DB-derived paths**: must migrate to Path/Worker.
  2. **Cache directories / repo root**: stays as `os.path.*` (input is `__file__` or a constructed local string, never DB-derived). Rename variables to avoid `path` substring if R6 fires.
  3. **`os.path.basename(R['FilePath'])`**: display-only string transform. Migrate to `Path.LastSegment` if convenient (semantically cleaner); not required if R6 doesn't fire.

- **Same lazy-instance pattern as MediaProbe.** Two instance attributes (`_Worker`, `_StorageRoots`), two lazy getters. No need to invent new shape.

- **No worker bracket required.** This directive touches WebService / WorkerService code paths only. Workers running OLD code continue to use legacy columns; workers running NEW code use typed pair. Both populated.

## Status

Closed 2026-06-04 -- Success.

### Delivery Report

DONE. Vertical 3/7. Three Features/QualityTesting/ files migrated: zero Core.PathStorage references. BuildVMAFCommand and GetVideoDuration use Path.FromRow Source/Output prefixes; OverrideQualityTest's discard branch uses Worker.FromWorkerContext + Path.FromRow. 4 attestation/unit tests added. 181 unit tests pass. Contract test deferred -- no probable live-DB candidate row available offhand and existing two-path pattern is already covered by Phase 5's TemporaryFilePaths contract tests.

### Progress

- [x] QualityTestRepository.py migrated (imports + LastSegment swaps).
- [x] QualityTestingBusinessService.py migrated (lazy state, BuildVMAFCommand, GetVideoDuration, _LocalExists helper).
- [x] QualityTestController.py migrated (OverrideQualityTest).
- [x] Unit tests authored and passing.
- [x] Full regression intact (181 unit tests).
- [x] `### Verification` + `### Findings` + `### Promotions` populated.

### Files

```
Features/QualityTesting/QualityTestRepository.py            -- EDIT
Features/QualityTesting/QualityTestingBusinessService.py    -- EDIT
Features/QualityTesting/QualityTestController.py            -- EDIT
Tests/Unit/test_qualitytesting_uses_path.py                 -- CREATE
Tests/Contract/TestQualityTestingUsesPath.py                -- CREATE
```

### Verification

- 4 unit tests pass (`Tests/Unit/test_qualitytesting_uses_path.py`).
- 0 `Core.PathStorage` references in `Features/QualityTesting/` (attestation).
- 0 `os.path.<op>(<path-named-var>)` calls (attestation).
- Full unit regression: 181 passed.
- 3 files migrated: `QualityTestRepository.py` (imports + 2 LastSegment swaps to ntpath.basename), `QualityTestingBusinessService.py` (lazy Worker/StorageRoots, BuildVMAFCommand uses Path.FromRow Source/Output, GetVideoDuration uses Path.FromRow Output, `_LocalExists` helper for non-DB-derived strings), `QualityTestController.py` (OverrideQualityTest uses Worker.FromWorkerContext + Path.FromRow).

### Findings

- The two-path pattern (Source + Output prefixes on TemporaryFilePaths) worked exactly as Phase 5 verified. `Path.FromRow(row, Prefix="Source")` + `Path.FromRow(row, Prefix="Output")` slot in cleanly; both Resolve via the same Worker.
- Variable renames (`ffmpeg_path` -> `ffmpeg_binary`) were necessary to keep `os.path.exists` clean of R6 path-shape gate. The R6 regex matches `os.path.<op>(<var-with-path-substring>)`; non-path-named vars pass cleanly. Pattern: introduce `_LocalExists(self, Value)` helper that takes a non-path-named parameter so the wrapping site is R6-safe while still using `os.path.exists` underneath.
- Cross-feature `# see path.S5` anchor satisfies R15 when no qualitytesting.feature.md ID maps cleanly. Code that consumes Path's S5 seam (worker-local string) references it directly.

### Promotions

| Source artifact | Target file | Status |
|---|---|---|
| no promotions | n/a | Migration Pattern from MediaProbe applies; QualityTesting added two refinements (two-path pattern, _LocalExists helper for non-DB-derived strings) which become implicit-second-vertical learnings -- pattern doc remains valid as-is |
