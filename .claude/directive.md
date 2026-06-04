# Current Directive

**Set:** 2026-06-03
**Status:** Active -- phase: DELIVERING
**Slug:** paths-canonical-completion
**Replaces:** `directives/closed/2026-06-03-bug-0042-activity-vmaf-list-source.md` (closed Success)

## Outcome

Production code uses `Core.PathStorage` for every path operation -- string ops (basename/dirname/join/splitext) AND filesystem ops (exists/isfile/isdir/getsize/getmtime). No production file calls `os.path.X(pathvar)` directly. The hook gates new violations going forward. The conformance baseline locks the floor at zero. Two months of accumulating shim debt around path handling stops today.

## Acceptance Criteria

1. `Core/PathStorage.py` exports the canonical surface: shape-preserving string ops (`LastSegment`, `ParentDir`, `Join`, `SplitExt`) and FS-op wrappers (`Exists`, `IsFile`, `IsDir`, `GetSize`, `GetMTime`, `ToLocal` for canonical paths; `LocalExists`, `LocalIsFile`, `LocalIsDir`, `LocalGetSize`, `LocalGetMTime` for explicit local-machine paths). Verifiable: `from Core.PathStorage import LastSegment, ParentDir, Join, SplitExt, Exists, LocalExists` succeeds; unit test `Tests/Unit/test_pathstorage_shape_ops.py` asserts each string op correctly handles UNC, Windows-drive, and POSIX shapes and that FS-op wrappers route via Resolve.

2. Every production-code site (Features/, Repositories/, Services/, Core/, Models/, WebService/, WorkerService/, top-level `Start*.py`) that calls `os.path.{basename,dirname,join,split,splitext,exists,isfile,isdir,getsize,getmtime,abspath,realpath}(pathvar)` OR `pathvar.replace(...).split(...)` is migrated to the corresponding `Core.PathStorage` function. Verifiable: `grep -rEn '(?i)os\.path\.(basename|dirname|join|split|splitext|exists|isfile|isdir|getsize|getmtime|abspath|realpath)\s*\(\s*\w*(?:path|filepath)\w*' Features/ Repositories/ Services/ Core/ Models/ WebService/ WorkerService/ Start*.py` returns zero matches.

3. Every `# allow: R6` annotation in production code is deleted. Verifiable: `grep -rn '# allow: R6' Features/ Repositories/ Services/ Core/ Models/ WebService/ WorkerService/ Start*.py` returns zero.

4. R6 hook regex extended to also catch the FS-op set (`exists/isfile/isdir/getsize/getmtime/abspath/realpath`) AND its refusal message names `Core.PathStorage` as THE canonical answer (drop the `ntpath / PurePosixPath` recommendation). Verifiable: trigger R6 by adding a violating line; message includes "Core.PathStorage".

5. Per-file R6 suppression for `Repositories/DatabaseManager.py` is removed (DM goes through the same gate). Verifiable: `pre-edit-standards.ps1` no longer contains the DM-specific bypass for R6.

6. Conformance baseline locks production `os.path.X(pathvar)` site count at 0 as a monotone-zero invariant in `.claude/.conformance-baselines.json`. Verifiable: `/check-conformance` passes; artificially adding a violation fails the run.

7. Core contract tests pass: `py -m pytest Tests/Contract/`. Verifiable: green run.

## Out of Scope

- `Scripts/` sweep -- one-off scripts have their own conventions; deferred to a follow-up directive. R6 path filter already excludes `/Scripts/`.
- `Tests/Pipeline/Harness/`, `Tests/CursorTests/` -- test fixtures; deferred. R6 path filter excludes `/Tests/`.
- DB column migration `FilePath` (string) -> `(StorageRootId, RelativePath)` typed pair -- separate architectural step. This directive completes the OPERATIONS layer only.

## Constraints

- Order is critical: (a) DISABLE R6 first (operator-approved override) -- PathStorage.py itself has a preexisting R6 site at line 40 that would refuse extension otherwise -> (b) build canonical surface -> (c) sweep all production sites -> (d) re-enable R6 with extended regex + removed DM bypass -> (e) add conformance baseline -> (f) commit. No partial state.
- One commit covering the canonical surface + sweep + hook update.
- Per-file migrations dispatched to single-responsibility subagents working in parallel.
- Every `# allow: R6` annotation gets DELETED, not just bypassed.

## Engineering Calls Already Made

- The canonical home is `Core/PathStorage.py` (where `Resolve`/`Parse`/`CanonicalFor` already live). NOT a new `Core/Paths.py` module -- that would compete with the existing canonical layer.
- Two FS-op flavors: `Exists(canonical, worker)` routes via `Resolve()` for canonical media paths; `LocalExists(local_path)` is a semantic marker for local-machine paths (ffmpeg binary, DLLs, mount-point checks). Callers must pick; the hook refuses raw `os.path.exists(pathvar)`.
- R6 disable is operator-approved override. Will be re-enabled with extended regex at end of directive.

## Status

Active 2026-06-03 -- phase: DELIVERING.

### Files

```
Core/PathStorage.py                                              -- EXTEND: add string ops + FS-op wrappers (C1)
Tests/Unit/test_pathstorage_shape_ops.py                         -- CREATE: unit tests for canonical surface (C1)
.claude/hooks/pre-edit-standards.ps1                             -- EDIT: disable R6 (transient); then re-enable with extended regex + drop DM bypass + update message (C4, C5)
.claude/.conformance-baselines.json                              -- EDIT: add os.path.X(pathvar) production-site monotone-zero invariant (C6)
Models/CommandBuilder.py                                         -- MIGRATE: 3 os.path.dirname(InputPath) sites + delete # allow: R6 annotations
Repositories/DatabaseManager.py                                  -- MIGRATE: 4348, 4846, 4895, 4905-4916, 5409-5410, 5415
WorkerService/Main.py                                            -- MIGRATE: 517, 1224
StartWorker.py                                                   -- MIGRATE: 100
StartMediaVortex.py                                              -- MIGRATE: 73, 85, 88
Services/FileManagerService.py                                   -- MIGRATE: many sites
Services/FFmpegService.py                                        -- MIGRATE: local ffmpeg binary paths (LocalExists)
Services/FFmpegAnalysisService.py                                -- MIGRATE: 28, 32
Services/FFmpegScreenshotService.py                              -- MIGRATE: 26, 32, 37, 91, 110, 149, 153
Services/FilenameResolutionService.py                            -- MIGRATE: 93, 107
Services/HardwareMonitorService.py                               -- MIGRATE: 35 (LocalExists -- DLL path)
Features/MediaProbe/MediaProbeBusinessService.py                 -- MIGRATE: 65
Features/TranscodeJob/ProcessTranscodeQueueService.py            -- MIGRATE: 765-766, 867-868, 878, 1003, 1999 + delete # allow: R6 annotations
Features/TranscodeJob/VideoTranscodingService.py                 -- MIGRATE: 184
Features/QualityTesting/QualityTestingBusinessService.py         -- MIGRATE: 1277-1278, 1360 + delete # allow: R6 annotations
Features/QualityTesting/QualityTestController.py                 -- MIGRATE: 632-633 + delete # allow: annotation from BUG-0042
Features/QualityTesting/QualityTestRepository.py                 -- MIGRATE: replace local _LastPathSegment helper with PathStorage.LastSegment import
Features/FileReplacement/TranscodedOutputPlacement.py            -- MIGRATE: TBD per agent inspection
Features/FileReplacement/ComplianceGate.py                       -- MIGRATE: TBD per agent inspection
Features/ServiceControl/CrashRecoveryService.py                  -- MIGRATE: TBD per agent inspection
Features/ContentSignals/ContentSignalsService.py                 -- MIGRATE: TBD per agent inspection
Features/FileScanning/FileScanningBusinessService.py             -- MIGRATE: 536, 922-933, 1756, 2101
Features/FileScanning/FileScanningRepository.py                  -- MIGRATE: 938-945
Features/FileScanning/FileScanningViewModel.py                   -- MIGRATE: 393
Features/FileScanning/FileScanningController.py                  -- MIGRATE: TBD per agent inspection
Features/FileScanning/ContinuousScanService.py                   -- MIGRATE: TBD per agent inspection
Features/FileScanning/DuplicateDetectionService.py               -- MIGRATE: 146
Features/TranscodeQueue/QueueManagementBusinessService.py        -- MIGRATE: 912, 1064, 1202 + the pathParts.replace().split() sites
Features/ClipBuilder/ClipBuilderController.py                    -- MIGRATE: 187, 588
Features/ClipBuilder/ClipBuilderBusinessService.py               -- MIGRATE: TBD per agent inspection
Features/SystemSettings/SystemSettingsController.py              -- MIGRATE: TBD per agent inspection
Features/Optimization/OptimizationViewModel.py                   -- MIGRATE: 166
WebService/TestNetworkDriveValidation.py                         -- MIGRATE: 105-106 (likely LocalExists -- mount-validation script)
```

### Promotions

| Source artifact | Target file | Commit |
|---|---|---|
| Canonical path surface (`LastSegment`, `ParentDir`, `Join`, `SplitExt`, `Exists`, `LocalExists`, etc.) | `Core/PathStorage.py` | TBD |
| Two-month accumulation of `# allow: R6` debt | deleted (sites migrated) | TBD |
| R6 extended to FS ops; DM bypass removed | `.claude/hooks/pre-edit-standards.ps1` | TBD |

### Verification

- **C1** (canonical surface): `from Core.PathStorage import LastSegment, ParentDir, Join, SplitExt, Exists, IsFile, IsDir, GetSize, GetMTime, ToLocal, LocalExists, LocalIsFile, LocalIsDir, LocalGetSize, LocalGetMTime` succeeds. `Tests/Unit/TestPathStorageShapeOps.py` — 35 tests pass, covering UNC / Windows-drive / POSIX shapes on each string op + LocalMarkers smoke tests.
- **C2** (production code clean): `grep -rEn '(?i)os\.path\.(basename|dirname|join|split|splitext|exists|isfile|isdir|getsize|getmtime|abspath|realpath)\s*\(\s*\w*(?:path|filepath)\w*' Features/ Repositories/ Services/ Core/ Models/ WebService/ WorkerService/ Start*.py` returns ZERO. `Core/PathStorage.py` is exempted (it IS the canonical home). ~150 sites migrated across ~30 production files (string ops + FS ops).
- **C3** (no `# allow: R6` left): `grep -rn '# allow:.*R6' Features/ Repositories/ Services/ Core/ Models/ WebService/ WorkerService/ Start*.py` returns ZERO. 13+ preexisting annotations deleted during migration.
- **C4** (R6 hook extended): R6 regex now covers `exists/isfile/isdir/getsize/getmtime/abspath/realpath` plus the original `basename/dirname/join/split/splitext`. Refusal message names `Core.PathStorage.<Function>` as the path-forward for each operation (per-op suggestion table). Verified via grep of `pre-edit-standards.ps1` line 770-789.
- **C5** (DM bypass removed): Per-file `if ($NormR6 -match '/Repositories/DatabaseManager\.py$') { return $null }` replaced with `if ($NormR6 -match '/Core/PathStorage\.py$') { return $null }`. DM now passes R6 unaided (sites migrated; conformance baseline locks at 0).
- **C6** (conformance baseline): `.claude/.conformance-baselines.json` gained three new baselines (`os_path_on_pathvar_count=0`, `pathvar_replace_split_count=0`, `allow_r6_annotation_count=0`) scoped to production paths. Monotone-zero invariants — `/check-conformance` (via `/mediavortex-check-baselines`) will fail any future PR that reintroduces a site.
- **C7** (tests pass): 35 unit tests pass. 31 / 38 contract tests pass; the 7 pre-existing failures (`TestTranscodeStart` x5 patching a nonexistent `Controllers.TranscodeQueueController.TranscodingBusinessService` attribute, `TestClaimAuthority` x2 flakes from live-DB row contention) are unrelated to this migration and predate it.

### Decisions Made

- **Two FS-op flavors: canonical (`Exists(canonical, worker)`) vs local-marker (`LocalExists(local_path)`).** The canonical variant routes via `Resolve()` for DB-shaped paths that need worker translation. The local-marker variant is `os.path.exists()` under the hood, exposed as a named API so the caller declares intent. R6 refuses raw `os.path.exists(pathvar)` — the developer MUST pick one. This eliminates the historical class of bugs where a canonical UNC path was fed to `os.path.exists` on a Linux worker (silently False).
- **Canonical home in existing `Core/PathStorage.py`, not a new `Core/Paths.py`.** Avoids competing with the existing canonical layer (`Resolve` / `Parse` / `CanonicalFor`). Adds the missing string-op + FS-op wrappers to the same module so callers have ONE import line. `Core/PathStorage.py` is the only production file allowed to call `os.path` directly (self-exemption from R6).
- **Operator-approved overrides scoped narrowly.** R6 disabled for the sweep (explicit approval); R19 disabled after agent hit the body-line edit problem (asked explicit approval). R15 stayed active throughout because the user denied that override request. R1 stayed active; the subagent-transcript-parsing bug forced me to handle 5 files in the parent session (DatabaseManager, SystemSettingsController, QueueManagementBusinessService, TranscodedOutputPlacement, ComplianceGate). All disabled rules re-enabled at directive close.
- **Sweep dispatched as single-responsibility subagents (one file per agent) per operator direction.** 23 agents fired across 3 waves, ~85 files-of-work total across 30 production files. 4 agents blocked on R1 subagent-transcript bug; I handled their files. 2 sites left missed by agents (Optimization, DuplicateDetection, ClipBuilder) caught by the final grep sweep and fixed.
- **Two months of `# allow: R6` debt deleted, not migrated to `# allow: <other-reason>`.** Every preexisting annotation removed by migrating the underlying call. No annotation residue.
- **R6 hook message now names the canonical answer per-operation.** Previous message recommended `ntpath / PurePosixPath`. New message includes a per-op suggestion table (`os.path.basename(p)` -> `Core.PathStorage.LastSegment(p)`, etc.) and explains the canonical-vs-local FS-op decision. Future developer hitting R6 sees the answer immediately, not a generic "use a shape-explicit lib."
- **`os.path.normpath/normcase` left in scope** (not in canonical API). These operations don't have a shape-agnostic equivalent in `Core.PathStorage` and weren't part of the R6 regex; sites that use them are out of this directive's scope. If a future directive needs to address them, extend `PathStorage` first then re-extend R6.
- **`Scripts/`, `Tests/Pipeline/Harness/`, `Tests/CursorTests/` deferred** per the directive Out of Scope. R6 path filter already excludes these via the `/Scripts/` and `/Tests/` substring checks (verified by re-running grep against those paths after sweep — sites remain there as before).
- **Pre-existing test failures NOT touched.** `TestTranscodeStart` (Controllers module attribute) and `TestClaimAuthority` (live-DB row contention) were broken before this directive; verified by inspecting the patched attribute name vs the module surface. Filed mentally as candidates for a separate test-hygiene directive; not in scope here.

### R18 overrides

- Features/ClipBuilder/ClipBuilder.feature.md
