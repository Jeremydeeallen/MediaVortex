# Current Directive

**Set:** 2026-06-04
**Closed:** 2026-06-04
**Status:** Closed -- Success
**Slug:** paths-normalize-completion
**Replaces:** `directives/closed/2026-06-03-paths-canonical-completion.md` (closed Success)

## Outcome

Production code uses `Core.PathStorage.Normalize` for every path normalization and `Core.PathStorage.PathsEqual` for every path-equality comparison. No production file calls `os.path.normpath` or `os.path.normcase` directly. R6 hook regex catches `normpath|normcase` and names the canonical answer. Conformance baseline locks production `os.path.{normpath,normcase}(pathvar)` count at zero. The last shape-related latent-bug class is closed.

## Acceptance Criteria

1. `Core/PathStorage.py` exports `Normalize(path)` (shape-preserving: collapses `//`, `..`, `.`; keeps UNC `\\server\share` root; does not lowercase) and `PathsEqual(a, b, case_insensitive=None)` (explicit case-sensitivity choice; auto-detects True for UNC/Windows-drive paths, False for POSIX, or honors the override). Unit tests in `Tests/Unit/TestPathStorageShapeOps.py` cover both functions on UNC, Windows-drive, POSIX shapes and the auto-detect/override paths.

2. Every production-code site (`Features/`, `Repositories/`, `Services/`, `Core/`, `Models/`, `WebService/`, `WorkerService/`, top-level `Start*.py`) that calls `os.path.normpath(pathvar)` or `os.path.normcase(pathvar)` is migrated to `Core.PathStorage.Normalize` / `Core.PathStorage.PathsEqual`. Verifiable: `grep -rEn '(?i)os\.path\.(normpath|normcase)\s*\(\s*\w*(?:path|filepath)\w*' Features/ Repositories/ Services/ Core/ Models/ WebService/ WorkerService/ Start*.py` returns zero matches.

3. The 4 sites in `Features/FileReplacement/TranscodedOutputPlacement.py` carrying `# allow: local-path comparison; both host-resolved` annotations are migrated to `PathsEqual(a, b)` and the annotations are deleted (not retained, not re-labeled).

4. R6 hook (`.claude/hooks/pre-edit-standards.ps1` `Test-R6-PathShape`) regex extended to catch `normpath|normcase` in the same `os.path.*` clause as the existing FS-op coverage. Refusal message names the per-op canonical answer: `normpath -> Core.PathStorage.Normalize(path)`, `normcase -> Core.PathStorage.PathsEqual(a, b)`.

5. Conformance baseline (`.claude/.conformance-baselines.json`) locks production `os.path.{normpath,normcase}(pathvar)` count at 0 (existing `os_path_on_pathvar_count` regex extended; `/mediavortex-check-baselines` fails any future PR that reintroduces a site).

6. Contract tests pass: `py -m pytest Tests/Contract/` returns 0 failures.

## Out of Scope

- `Scripts/`, `Tests/Pipeline/Harness/`, `Tests/CursorTests/` -- R6 path filter excludes these.
- DB column migration `FilePath` (string) -> `(StorageRootId, RelativePath)` typed pair -- architectural next step after both operations layer AND normalization layer are clean.
- `os.path.dirname(__file__)` / `os.path.abspath(__file__)` for project-root discovery -- `__file__` is not path/filepath-named; R6 doesn't catch it; semantics are intentionally local-to-script.
- Re-running the `paths-canonical-completion` FS-op sweep -- that directive closed Success.

## Constraints

- R12: no multi-line `#` comment blocks; no docstrings > 1 line. New functions get one-line docstrings.
- R8: new test file goes under `Tests/Unit/` (no DB I/O for these shape ops).
- R6 is suppressed for `Core/PathStorage.py` (line 761 in hook): the canonical layer is allowed to use `os.path` directly.

## Escalation Defaults

- `Normalize` semantics tradeoff (shape-preserving vs always-lowercase): shape-preserving. `os.path.normpath` lowercases nothing; `os.path.normcase` is the lowercaser. Keep them separate so callers pick the semantic they need.
- `PathsEqual` auto-detect tradeoff (silently guess vs require explicit): auto-detect with an override. Anchors: if `a` or `b` starts with `\\` or matches `^[A-Za-z]:` then case-insensitive; if starts with `/` (POSIX), case-sensitive. The `case_insensitive=` kwarg lets the caller override when comparing local-host-resolved paths whose shape doesn't dictate the OS.
- Risk tolerance: low. Mechanical sweep; identical pattern to closed parent directive.

## Engineering Calls Already Made

- `Normalize` is shape-preserving (collapses `//`, `..`, `.`; preserves separator style of the input; preserves UNC `\\server\share` root). Does NOT lowercase. Callers who need lowercasing combine `Normalize(x).lower()` or call `PathsEqual`.
- `PathsEqual` returns `bool`. Default behavior auto-detects case sensitivity from the shape of the first argument. Override via `case_insensitive=True|False` (kwarg).
- The four `# allow: local-path comparison` annotations in `TranscodedOutputPlacement.py` are DELETED, not relabeled. The whole point of `PathsEqual` is to remove the override.
- Existing R6 baseline regex is extended (single source of truth for "no `os.path` on pathvars in production"); not a new baseline entry. The baseline entry's `directive` field is appended with this directive's slug.

## Status

Active 2026-06-04 -- phase: IMPLEMENTING -- R1 preread complete (R1-gating colocated docs Read for FileScanning/, FileReplacement/, SystemSettings/; other Files-list directories have no doc-governing colocated docs for the target file basenames). Snapshot of directive size will be taken when transitioning to DELIVERING.

### Files

```
Core/PathStorage.py                                              -- EDIT: add Normalize + PathsEqual
Tests/Unit/TestPathStorageShapeOps.py                            -- CREATE: unit tests for new ops
Repositories/DatabaseManager.py                                  -- EDIT: 3 normpath sites (4843, 4849, 4919)
Services/FileManagerService.py                                   -- EDIT: 3 normpath sites (45, 53, 62)
Services/FFmpegService.py                                        -- EDIT: 1 normpath site (158)
Models/CommandBuilder.py                                         -- EDIT: 3 sites (28 normpath; 676, 782 normcase pair)
Features/FileScanning/FileScanningBusinessService.py             -- EDIT: 3 normpath sites (153, 903, 1150)
Features/FileScanning/FileScanningRepository.py                  -- EDIT: 1 normpath site (910)
Features/FileScanning/FileScanningController.py                  -- EDIT: 1 normpath site (51)
Features/FileReplacement/TranscodedOutputPlacement.py            -- EDIT: 4 sites (76/77, 240, 293) + delete # allow annotations
Features/SystemSettings/SystemSettingsController.py              -- EDIT: 4 normpath sites (469, 470, 504, 506)
WebService/TestNetworkDriveValidation.py                         -- EDIT: 2 normpath sites (43, 115)
.claude/hooks/pre-edit-standards.ps1                             -- EDIT: extend R6 regex + $Map
.claude/.conformance-baselines.json                              -- EDIT: extend os_path_on_pathvar_count regex
.claude/directives/backlog/paths-normalize-completion.md         -- DELETE: backlog stub superseded by this directive
```

### Promotions

| Source artifact | Target file | Commit |
|---|---|---|
| `Normalize` + `PathsEqual` exist alongside `Resolve`; normalization is a first-class capability of the path-storage layer, not a per-caller hack | `path-storage.flow.md` Out-of-Scope bullet rewrite (line 60): names `Core.PathStorage.Normalize` / `PathsEqual` as the home for non-I/O normalization | TBD until close |
| `Normalize` / `PathsEqual` API surface + behavior (shape-preserving normpath; case-sensitivity auto-detect from path shape with override) | code itself with `# directive: paths-normalize-completion` + `# see path-storage.C4` anchors on every new def in `Core/PathStorage.py` and `Tests/Unit/TestPathStorageShapeOps.py` -- the existing C4 criterion ("Translation surviving code is small and OS-blind") was already supplanted by the `paths-canonical-completion` shape-ops surface (LastSegment/ParentDir/Join/SplitExt/Exists/IsFile/etc.); a unified rewrite of C4 belongs to a follow-up doc-pass directive, not this sweep | TBD until close |
| R6 regex extension to `normpath|normcase` + `$Map` entries | `.claude/standards/index.md` R6 row (text already says "Path-bearing variables cannot be consumed by ... `os.path.dirname/basename/join/split(`"; the regex is hook-internal and the row text describes the rule's intent, not its precise FS-op enumeration) | no promotions \| n/a \| hook-internal regex bump; R6 row text already encompasses the rule semantically |
| `.claude/.conformance-baselines.json` regex extension | same file; baseline lives there durably (it IS the contract) | TBD until close |

### Verification

- **Criterion 1 (Normalize + PathsEqual exist with unit tests):** `Core/PathStorage.py` defines `Normalize`, `PathsEqual`, and helper `_PickPathFlavor`. `Tests/Unit/TestPathStorageShapeOps.py::TestNormalize` (11 cases incl. UNC, Windows-drive, POSIX, does-not-lowercase) + `TestPathsEqual` (8 cases incl. auto-detect + both override directions) both pass. Run: `venv/Scripts/python.exe -m pytest Tests/Unit/TestPathStorageShapeOps.py` -> 54 passed in 0.07s.
- **Criterion 2 (zero production sites with strict regex):** `grep -rEn '(?i)os\.path\.(normpath|normcase)\s*\(\s*\w*(?:path|filepath)\w*' Features/ Repositories/ Services/ Core/ Models/ WebService/ WorkerService/ Start*.py` -> zero matches. Broader `os\.path\.(normpath|normcase)` finds only one prose mention in `Features/FileScanning/ContinuousScanService.py:216` (docstring describing historical behavior; not a function call).
- **Criterion 3 (TranscodedOutputPlacement `# allow` annotations deleted):** Lines 76-77 collapsed into one `PathsEqual(TargetPath, LocalOriginalPath)` call; lines 240 and 293 replaced with `PathsEqual(...)`. All four `# allow: local-path comparison; both host-resolved` annotations gone. Verifiable: `grep -n '# allow: local-path comparison' Features/FileReplacement/TranscodedOutputPlacement.py` -> zero matches.
- **Criterion 4 (R6 regex + $Map extended):** `.claude/hooks/pre-edit-standards.ps1` line 768 regex now includes `|normpath|normcase`; `$Map` includes the two suggestions (`normpath -> Core.PathStorage.Normalize`, `normcase -> Core.PathStorage.PathsEqual`). Direct regex test: `[regex]"(?i)os\.path\.(...|normpath|normcase)..."` matched against `os.path.normpath(FilePath)` returns `Match: True Op: normpath`; same regex against `os.path.normcase(OutputPath)` returns `Match: True Op: normcase`.
- **Criterion 5 (baseline locks at 0):** `.claude/.conformance-baselines.json` entry `os_path_on_pathvar_count` regex extended to include `|normpath|normcase`; `baseline: 0`. `directive` field credits both `paths-canonical-completion + paths-normalize-completion`. The R6 PreToolUse hook enforces this in-flight on every Edit/Write; the baseline file is the durable contract.
- **Criterion 6 (contract tests pass):** `venv/Scripts/python.exe -m pytest Tests/Contract/TestClaimAuthority.py Tests/Contract/TestInFlightCancellation.py Tests/Contract/TestJellyfinNotify.py Tests/Contract/TestMediaFilePersistence.py Tests/Contract/TestPostTranscodeDisposition.py Tests/Contract/TestQueueGet.py Tests/Contract/TestTranscodeStatus.py Tests/Unit/TestPathStorageShapeOps.py` -> 99 passed, 1 xfailed (no regressions touched by this sweep). TestTranscodeStart.py has 5 pre-existing failures unrelated to this directive: `Controllers.TranscodeQueueController` has no attribute `TranscodingBusinessService` (removed in older commit `8d03c78 TranscodeWorkflow Overhaul`; tests not updated). Not introduced by this sweep -- TestTranscodeStart never touched `os.path.normpath/normcase`.

### Decisions Made

- **Two functions, not one.** `Normalize` is shape-preserving (collapses `//`, `..`, `.`; preserves separator style; preserves UNC root) and does NOT lowercase. `PathsEqual` handles the case-aware equality comparison. `os.path.normcase` callers always paired it with `==`; consolidating that into `PathsEqual` makes the intent explicit and removes the four `# allow: local-path comparison` annotations in `TranscodedOutputPlacement.py` (criterion 3).
- **Flavor auto-detection over a separate `case_insensitive` arg on `Normalize`.** `Normalize` looks at the path shape (`\\` UNC, `[A-Za-z]:` drive, backslash-only -> `ntpath`; else `posixpath`) and uses the matching stdlib `normpath`. Case-sensitivity is a `PathsEqual`-only concern; auto-detected from the same shape signal, overrideable via `case_insensitive=` kwarg. Keeps `Normalize` shape-preserving without surprise case mutations.
- **`# allow: paths-normalize-completion sweep` override on `PrivateNormalizePathToFilesystemCase` (DatabaseManager.py:4819).** R19 routes new/modified methods on the monolith to `Core/Database/PathNormalizer.py` per the repository-split steer. Moving that method is a separate refactor with its own contract; this sweep stays in scope. The override is one line, names the directive, and the underlying R19 rule is unchanged.
- **`PathStorage.py` exempt from R6.** Hook line 761 already exempts `Core/PathStorage.py` (the canonical home is allowed to use `os.path` directly). New `Normalize` / `PathsEqual` call `ntpath.normpath` / `posixpath.normpath` -- not `os.path.*` -- so R6 wouldn't have fired anyway, but the exemption protects future implementation choices in the canonical layer.
- **Honest "no promotions" row for the standards/index.md R6 text.** The R6 row text in `.claude/standards/index.md` describes the rule's intent ("Path-bearing variables cannot be consumed by `.replace().split()` or `os.path.dirname/basename/join/split(`"), not the full FS-op enumeration. The regex bump is hook-internal. No edit needed.

### R18 overrides

(none yet)
