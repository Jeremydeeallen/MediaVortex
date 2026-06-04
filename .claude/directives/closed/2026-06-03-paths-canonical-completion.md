# Archived Directive

**Set:** 2026-06-03
**Closed:** 2026-06-03
**Status:** Closed -- Success
**Slug:** paths-canonical-completion
**Replaces:** `directives/closed/2026-06-03-bug-0042-activity-vmaf-list-source.md` (closed Success)

## Outcome

Production code uses `Core.PathStorage` for every path operation -- string ops (basename/dirname/join/splitext) AND filesystem ops (exists/isfile/isdir/getsize/getmtime). No production file calls `os.path.X(pathvar)` directly. The hook gates new violations going forward. The conformance baseline locks the floor at zero. Two months of accumulating shim debt around path handling stops today.

## Acceptance Criteria

1. `Core/PathStorage.py` exports the canonical surface: shape-preserving string ops (`LastSegment`, `ParentDir`, `Join`, `SplitExt`) and FS-op wrappers (`Exists`, `IsFile`, `IsDir`, `GetSize`, `GetMTime`, `ToLocal` for canonical paths; `LocalExists`, `LocalIsFile`, `LocalIsDir`, `LocalGetSize`, `LocalGetMTime` for explicit local-machine paths). Verifiable: `from Core.PathStorage import LastSegment, ParentDir, Join, SplitExt, Exists, LocalExists` succeeds; unit test `Tests/Unit/TestPathStorageShapeOps.py` asserts each string op correctly handles UNC, Windows-drive, and POSIX shapes and that FS-op wrappers route via Resolve.

2. Every production-code site (Features/, Repositories/, Services/, Core/, Models/, WebService/, WorkerService/, top-level `Start*.py`) that calls `os.path.{basename,dirname,join,split,splitext,exists,isfile,isdir,getsize,getmtime,abspath,realpath}(pathvar)` OR `pathvar.replace(...).split(...)` is migrated to the corresponding `Core.PathStorage` function. Verifiable: grep returns zero matches across production paths.

3. Every `# allow: R6` annotation in production code is deleted.

4. R6 hook regex extended to also catch the FS-op set AND its refusal message names `Core.PathStorage` as THE canonical answer.

5. Per-file R6 suppression for `Repositories/DatabaseManager.py` is removed (DM goes through the same gate).

6. Conformance baseline locks production `os.path.X(pathvar)` site count at 0 as a monotone-zero invariant.

7. Core contract tests pass.

## Out of Scope

- `Scripts/` sweep -- one-off scripts have their own conventions; deferred. R6 path filter already excludes `/Scripts/`.
- `Tests/Pipeline/Harness/`, `Tests/CursorTests/` -- test fixtures; deferred. R6 path filter excludes `/Tests/`.
- DB column migration `FilePath` (string) -> `(StorageRootId, RelativePath)` typed pair -- separate architectural step.

## Status

Closed 2026-06-03 -- Success.

### Promotions

| Source artifact | Target file | Commit |
|---|---|---|
| Canonical path surface (`LastSegment`, `ParentDir`, `Join`, `SplitExt`, `Exists`, `LocalExists`, etc.) | `Core/PathStorage.py` | 65a3eaa |
| Two-month accumulation of `# allow: R6` debt | deleted (sites migrated) | 65a3eaa |
| R6 extended to FS ops; DM bypass swapped for Core/PathStorage.py self-exemption | `.claude/hooks/pre-edit-standards.ps1` | 65a3eaa |
| Conformance baselines (monotone-zero) for os.path.X(pathvar), pathvar.replace().split(), and `# allow: R6` annotations | `.claude/.conformance-baselines.json` | 65a3eaa |
| Unit tests for canonical surface (35 tests across UNC/drive/POSIX) | `Tests/Unit/TestPathStorageShapeOps.py` | 65a3eaa |

### Verification

- **C1** (canonical surface): `from Core.PathStorage import LastSegment, ParentDir, Join, SplitExt, Exists, IsFile, IsDir, GetSize, GetMTime, ToLocal, LocalExists, LocalIsFile, LocalIsDir, LocalGetSize, LocalGetMTime` succeeds. `Tests/Unit/TestPathStorageShapeOps.py` -- 35 tests pass.
- **C2** (production code clean): grep returns ZERO across `Features/ Repositories/ Services/ Core/ Models/ WebService/ WorkerService/ Start*.py`. `Core/PathStorage.py` is exempted (canonical home). ~150 sites migrated across ~30 production files.
- **C3** (no `# allow: R6` left): grep returns ZERO. 13+ preexisting annotations deleted.
- **C4** (R6 hook extended): R6 regex now covers `exists/isfile/isdir/getsize/getmtime/abspath/realpath` plus original `basename/dirname/join/split/splitext`. Refusal message names `Core.PathStorage.<Function>` per-op with a suggestion table.
- **C5** (DM bypass removed): per-file `/Repositories/DatabaseManager\.py$` bypass replaced with `/Core/PathStorage\.py$` self-exemption. DM passes R6 unaided.
- **C6** (conformance baseline): three monotone-zero invariants added (`os_path_on_pathvar_count`, `pathvar_replace_split_count`, `allow_r6_annotation_count`).
- **C7** (tests pass): 35 unit tests pass. 31/38 contract tests pass; 7 pre-existing failures (TestTranscodeStart x5, TestClaimAuthority x2) unrelated to this migration.

### Decisions Made

- **Two FS-op flavors: canonical (`Exists(canonical, worker)`) vs local-marker (`LocalExists(local_path)`).** Forces the caller to declare intent. Eliminates the historical bug class where a canonical UNC path was fed to `os.path.exists` on a Linux worker (silently False).
- **Canonical home in existing `Core/PathStorage.py`, not a new `Core/Paths.py`.** Avoids competing with the existing canonical layer (`Resolve` / `Parse` / `CanonicalFor`). One import line. `Core/PathStorage.py` is the only production file allowed to call `os.path` directly.
- **Operator-approved overrides scoped narrowly.** R6 disabled for sweep (explicit approval); R19 disabled after agent hit body-line edit problem (explicit approval). R15 stayed active (operator denied that override). R1 stayed active; subagent-transcript-parsing bug forced 5 files to be migrated in the parent session (DatabaseManager, SystemSettingsController, QueueManagementBusinessService, TranscodedOutputPlacement, ComplianceGate). All disabled rules re-enabled at directive close.
- **Sweep dispatched as single-responsibility subagents per operator direction.** 23 agents across 3 waves, ~30 production files. 4 agents blocked on R1 subagent-transcript bug; I handled their files. 3 sites missed by agents (Optimization x4, DuplicateDetection x1, ClipBuilder x10) caught by final grep sweep and fixed.
- **Two months of `# allow: R6` debt deleted, not migrated to `# allow: <other-reason>`.** Every preexisting annotation removed by migrating the underlying call.
- **R6 hook message rewritten with per-op suggestion table.** Previous message recommended generic `ntpath / PurePosixPath`. New message names `Core.PathStorage.LastSegment` / `ParentDir` / `LocalExists` etc. per operation, explains canonical-vs-local FS-op decision.
- **`os.path.normpath/normcase` left in scope** (not in canonical API). Future directive should extend `PathStorage` first then re-extend R6.
- **Pre-existing test failures NOT touched** (TestTranscodeStart Controllers module drift; TestClaimAuthority live-DB row contention). Filed as candidates for a separate test-hygiene directive.

### Known Follow-ups

- `Scripts/` sweep: ~40+ remaining sites, one-off conventions, separate directive.
- `Tests/Pipeline/Harness/`, `Tests/CursorTests/`: test fixtures.
- DB column migration `FilePath` (string) -> typed `(StorageRootId, RelativePath)` pair -- the architectural next step now that the operations layer is canonical.
- `os.path.normpath/normcase` sites if/when needed.
- Pre-existing test failures (TestTranscodeStart, TestClaimAuthority).
- Subagent-transcript-parsing gap in the R1 hook (caused 4 agents to block on perfectly-correct doc Reads).
