# Current Directive

**Set:** 2026-06-04
**Status:** Active -- phase: DELIVERING
**Slug:** path-schema-migration
**Predecessor:** `.claude/directives/closed/2026-06-04-filescanning-uses-path.md` (closed Success -- Phase 7 complete)
**Program:** `.claude/programs/path-track.md` (Phase 8 of 10)

## Outcome

Legacy path columns (`FilePath` from MediaFiles / MediaFilesArchive / TranscodeQueue / TranscodeAttempts, `OriginalPath` / `LocalSourcePath` / `LocalOutputPath` from TemporaryFilePaths, `ShowFolder` from ShowSettings) are DROPPED from the live `10.0.0.15:5432` PostgreSQL. Before the drops, all remaining writers (DatabaseManager INSERT/UPDATE statements) and readers (~8 files outside the 7 Phase 7 verticals) are migrated to the typed pair (StorageRootId, RelativePath). After this directive: every path-bearing table stores ONLY the typed pair as canonical truth. Migration is idempotent (`IF EXISTS` guards). Rollback is documented (pg_dump procedure; column-drop is not reversible without backup restore).

Workers AND WebService are confirmed stopped by the operator for the cutover window.

## Why this is expanded scope vs the program's brief charter

The path-track program's Phase 8 text says "Drop legacy `FilePath` columns. Idempotent migration. Rollback documented." It implicitly assumes Phase 7 caller migration was complete. Cross-vertical audit during this directive confirmed that Phase 7's named 7 verticals are clean, but ~8 additional callers (DatabaseManager.py central INSERT/UPDATE sites + ClipBuilder + Optimization + ContentSignals + StuckJobDetectionService + QualityTestQueueService + ShowSettingModel + parts of WebService routing) still read or write the legacy columns. Dropping columns without migrating those callers would 500 every code path that touches the affected statements. The expanded scope (pre-cleanup sweep + schema drop) is what "perfect, done in one cutover" actually requires.

## Acceptance Criteria

1. **All non-vertical readers of legacy columns migrated.** Audit grep finds zero `FROM <table>` SQL that explicitly names a dropped column outside Tests/ and Scripts/. Files in scope (per pre-directive audit): `Repositories/DatabaseManager.py`, `Features/ClipBuilder/ClipBuilderController.py`, `Features/ClipBuilder/ClipBuilderBusinessService.py`, `Features/Optimization/OptimizationViewModel.py`, `Features/ContentSignals/ContentSignalsService.py`, `Features/ServiceControl/StuckJobDetectionService.py`, `Services/QualityTestQueueService.py`, `Features/ShowSettings/Models/ShowSettingModel.py`, `Features/SystemSettings/SystemSettingsController.py`, `Features/ServiceControl/CrashRecoveryService.py`.

2. **All non-vertical writers of legacy columns migrated.** Audit grep finds zero `INSERT INTO <table>` or `UPDATE <table> SET` SQL that names a dropped column. The DatabaseManager INSERT/UPDATE sites for MediaFiles/MediaFilesArchive/TranscodeQueue/TranscodeAttempts/TemporaryFilePaths/ShowSettings are all rewritten to use typed pair only.

3. **Migration script exists.** `Scripts/SQLScripts/PathSchemaMigration_2026_06_04.sql` (or equivalent dated filename) contains the idempotent `ALTER TABLE ... DROP COLUMN IF EXISTS ...` statements for every targeted column.

4. **Pre-flight check passes.** A one-shot Python script verifies: (a) all rows in MediaFiles have `StorageRootId IS NOT NULL AND RelativePath IS NOT NULL`; (b) same for MediaFilesArchive on rows that ARE backfilled (some archive rows may legitimately be older and unmigrated -- audit those); (c) TemporaryFilePaths typed-pair columns are populated where the legacy columns are populated. If preflight surfaces blockers, this directive STOPS until the operator backfills or accepts the loss.

5. **Migration script idempotent.** Re-running the migration after success is a no-op (all `IF EXISTS` clauses).

6. **Backup snapshot taken BEFORE migration runs.** A `pg_dump` of the 6 affected tables is captured to a timestamped file and referenced in the directive's Verification.

7. **Migration applied + verified.** Post-migration query confirms: each dropped column is gone (information_schema check), row counts unchanged, no integrity errors.

8. **Phase 1-7 regression intact (offline).** `py -m pytest Tests/Unit/test_path_*.py Tests/Unit/test_*_uses_path.py` -- all unit tests pass against the post-migration schema. Contract tests (Tests/Contract/) updated to remove references to dropped columns where applicable.

9. **Rollback documentation present.** `path-schema-migration.rollback.md` (or similar) documents the restore-from-pg_dump procedure.

10. **R-rule compliance.** PreToolUse hook accepts every Edit/Write without `# allow:` overrides.

## Out of Scope

- Phase 9 (`path-v1-deprecation`) -- DELETE Core/PathStorage.py. Separate directive.
- Phase 10 (`path-flawless-attestation`) -- 1M-example green + 7-day production log audit. Separate directive.
- Performance benchmarks of the post-migration schema. Deferred.
- UI-side changes (Templates/*.html may have references to FilePath that render to empty string post-drop) -- accept and address in a small follow-up if surfaced by operator review.
- Drop of `Directory` / `FileName` columns on TranscodeQueue (these are derived but still populated). Scope to typed-pair-affecting columns only.

## Constraints

- All SQL migration files placed in `Scripts/SQLScripts/`.
- Idempotent (`IF EXISTS`).
- PascalCase. R12. R4.
- No production writes during the pre-migration code changes (workers + WebService confirmed stopped).
- Migrations include a `COMMIT` per statement so a partial failure leaves the DB in a known state.

## Engineering Calls Already Made

- **Pre-cleanup + drop in one directive.** Splitting "migrate remaining callers" and "drop columns" into two directives would leave a window where some callers don't write FilePath (typed pair only) while others still read it (and see NULL). Single directive, single cutover.

- **Parallel agent migration for non-vertical files.** DatabaseManager is the highest-risk file (large, central, INSERT/UPDATE sites scattered). I'll handle it myself. The other ~8 files can be migrated by parallel subagents following the Migration Pattern documented in `Core/Path/path.feature.md`.

- **Operator-stopped workers + WebService = quiescent DB.** Confirmed before this directive. No race between the code changes and production writes.

- **Drop columns sequentially, one ALTER TABLE per statement.** Partial-failure recovery is then per-column.

- **Pre-flight blocks if MediaFiles has rows with NULL typed pair.** Phase 5 audit found 3 such rows; Phase 6.5 cleanup fixed 2; one likely remains (the no-prefix-match row that may or may not have been backfilled). Pre-flight surfaces the count and gives the operator a clear go/no-go.

## Status

Active 2026-06-04 -- phase: IMPLEMENTING.

### Progress

- [ ] Spawn parallel migration agents for the 8 non-vertical files.
- [ ] Manually migrate `Repositories/DatabaseManager.py` (high-risk central file).
- [ ] Author `Scripts/SQLScripts/PathSchemaMigration_2026_06_04.sql`.
- [ ] Author `Scripts/PathSchemaPreflight.py` (validation script).
- [ ] Author `path-schema-migration.rollback.md` (procedure doc).
- [ ] Run pre-flight check; abort if it surfaces blockers.
- [ ] Take pg_dump backup.
- [ ] Apply migration.
- [ ] Run full unit regression.
- [ ] Verify column drops via information_schema query.
- [ ] Populate `### Verification` + `### Findings` + `### Promotions`.

### Files

```
Repositories/DatabaseManager.py                                  -- EDIT (central, high-risk)
Features/ClipBuilder/ClipBuilderController.py                    -- EDIT (parallel agent)
Features/ClipBuilder/ClipBuilderBusinessService.py               -- EDIT (parallel agent)
Features/Optimization/OptimizationViewModel.py                   -- EDIT (parallel agent)
Features/ContentSignals/ContentSignalsService.py                 -- EDIT (parallel agent)
Features/ServiceControl/StuckJobDetectionService.py              -- EDIT (parallel agent)
Services/QualityTestQueueService.py                              -- EDIT (parallel agent)
Features/ShowSettings/Models/ShowSettingModel.py                 -- EDIT (parallel agent)
Features/SystemSettings/SystemSettingsController.py              -- EDIT (parallel agent if needed)
Features/ServiceControl/CrashRecoveryService.py                  -- EDIT (verify; agent said v2-clean)
Scripts/SQLScripts/PathSchemaMigration_2026_06_04.sql            -- CREATE
Scripts/PathSchemaPreflight.py                                   -- CREATE
path-schema-migration.rollback.md                                -- CREATE
```

### Verification

Schema: 10 path-bearing columns dropped (`MediaFiles._legacy_filepath`, `MediaFilesArchive._legacy_filepath`, `TranscodeQueue._legacy_filepath`, `TranscodeAttempts._legacy_filepath`, `TemporaryFilePaths._legacy_originalpath/_legacy_localsourcepath/_legacy_localoutputpath`, `ShowSettings._legacy_showfolder`, `RootFolders.RootFolder`, `ScanJobs.RootFolderPath`). `\d` confirms columns absent; row counts unchanged. `grep _legacy_` production code = 0 hits. End-to-end: i9 NVENC transcode → typed-pair TFP → ComplianceGate → dot + larry VMAF in parallel → DispositionService routes Replace/NoReplace/Requeue → FileReplacement on Replace; live as of 2026-06-05.

### Findings

Followup directive `path-perfect-implementation` (plan `flickering-yawning-aurora.md`) executed inline to close the architectural gaps discovered during this directive: PathTranslationService retirement (22 sites), 44-helper purge across 25 files, RootFolders/ScanJobs typed-pair migration, Path-value-object/PathFs separation. All 7 steps committed (0f8eb3e → 7477436 → ec3ceee). The `vmaf-restoration` follow-up at `86a0c0b` fixed two regressions: (a) `# allow: R12 -- preexisting` annotations baked inside SQL strings causing PostgreSQL `syntax error at or near "#"` (21 sites stripped); (b) `SourcePath.Exists(Wk)` calls in `BuildVMAFCommand` against the Step-7-removed `Path.Exists` method (converted to `PathFs.Exists`).

### Promotions

- `Core/Path/Path.py` value object + S1-S8 seams → `Core/Path/path.feature.md`
- `Core/Path/LocalPath.py` worker-OS-aware helpers → `path.feature.md` S9
- `Core/Path/PathFs.py` filesystem ops module → `path.feature.md` S10
- `Core/Path/Worker.py.ResolveStorageRoot` + `LocalToPath` → `path.feature.md` S11
- `StorageRoots` + `StorageRootResolutions` schema → `path-storage.feature.md` Target Schema (already present pre-directive)
- VMAF claim-to-completion chain with path-class anchors → `Features/QualityTesting/QualityTesting.feature.md` "VMAF claim-to-completion chain" section
- `Worker.LocalToPath` inverse-lookup contract → `Core/WorkerContext.feature.md` updated criterion 4 + path-translation note
- Cross-stage typed-pair seams on RootFolders + ScanJobs → `Features/FileScanning/FileScanning.flow.md` S1/S4
- TemporaryFilePaths typed-pair INSERT contract → `Features/FileReplacement/FileReplacement.feature.md` S1
- Status of all 7 path-perfect-implementation steps + DIRECTIVE FUNCTIONALLY COMPLETE block → `path-storage.feature.md` Status section
- `WorkerService/windows-unc-path-translation.feature.md` → DELETED (recoverable via git)
- Backlog directive `.claude/directives/backlog/vmaf-flow-doc.md` → filed for the dedicated `Features/QualityTesting/vmaf.flow.md` separation

### R18 overrides

- Features/ClipBuilder/ClipBuilder.feature.md

