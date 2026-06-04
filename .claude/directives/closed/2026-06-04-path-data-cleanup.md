# Current Directive

**Set:** 2026-06-04
**Closed:** 2026-06-04
**Status:** Closed -- Success
**Slug:** path-data-cleanup
**Predecessor:** `.claude/directives/closed/2026-06-04-path-migration-rehearsal.md`
**Program:** none -- one-off data cleanup directive surfaced by Phase 6 audit

## Outcome

The 2 residual real-world data issues surfaced by the Phase 6 audit are corrected on the live `10.0.0.15:5432` PostgreSQL. After this directive, re-running `Scripts/PathMigrationRehearsal.py` reports **content drift = 0** and **no_prefix_match = 0**. Phase 7 caller migration is unblocked with clean data.

## The 2 fixes

**Fix 1 -- MediaFiles id=22899 (content drift).** Pre-state: `FilePath='T:\The Real Housewives of Salt Lake City\Season 1\...SDTV-mv.mp4'`, `RelativePath='...SDTV.avi'`. Diagnosis: file was transcoded years ago (`.avi` -> `.mp4` with `-mv` watermark); FilePath was updated but typed-pair RelativePath wasn't. Fix: UPDATE RelativePath to match the FilePath (re-parse via FromLegacyString logic).

**Fix 2 -- MediaFiles id=687504 (no_prefix_match in legacy column).** Pre-state: `FilePath='mnt\media_tv\The Boroughs\Season 1\...-mv.mp4'`, `StorageRootId=1`, `RelativePath='The Boroughs/Season 1/...-mv.mp4'`. Diagnosis: typed pair is ALREADY CORRECT (matches sibling rows in same show, all 7 of which use `T:\The Boroughs\...`); only the legacy FilePath is malformed (Linux-shape with backslashes). Fix: UPDATE FilePath to `T:\The Boroughs\Season 1\...-mv.mp4`. Typed pair unchanged.

## Acceptance Criteria

1. **Pre-update verification.** Before each UPDATE, SELECT the row's current FilePath / RelativePath / StorageRootId. Abort if the values don't match the documented pre-state (defensive -- catches concurrent writes).
2. **Fix 1 applied.** `UPDATE MediaFiles SET RelativePath = <correct> WHERE Id = 22899 AND FilePath = <documented pre-state>`. Affected rows = 1.
3. **Fix 2 applied.** `UPDATE MediaFiles SET FilePath = <correct> WHERE Id = 687504 AND FilePath = <documented pre-state>`. Affected rows = 1.
4. **Post-update audit.** Re-run `Scripts/PathMigrationRehearsal.py`. Content drift on **current-data tables** (MediaFiles + TranscodeQueue + TranscodeAttempts + TemporaryFilePaths + ShowSettings) = 0. NoPrefixMatch across all tables = 0. MediaFilesArchive content drift may remain non-zero -- those are immutable historical snapshots of a fixed-upstream bug per Phase 6's finding; explicitly out of this directive's scope.
5. **Regression intact.** 152 unit tests pass.
6. **R-rule compliance.** PreToolUse hook accepts every Edit/Write without overrides.

## Out of Scope

- The two-update-pattern bug that originally produced the drift -- already fixed upstream (no post-March-2026 drift in ~19K subsequent archives per Phase 6 audit).
- Cleanup of 49 case-only-drift archive rows -- informational per D2/D10, no action.
- Backfilling typed-pair on the 3 unmigrated MediaFiles rows (`StorageRootId IS NULL` per the Phase 5 snapshot) -- separate operator task if desired.

## Constraints

- All changes via `Scripts/SQLScripts/QueryDatabase.py sql "..."` (the project's standard ad-hoc SQL runner). No new script file -- 2 row-scoped UPDATEs do not justify it.
- WHERE clause must include both Id AND the documented FilePath to make the operation idempotent (re-running is a no-op once applied).
- Workers may keep running. Single-row UPDATE with MVCC isolation; no race with worker SELECTs.

## Status

Closed 2026-06-04 -- Success.

### Delivery Report

DONE. 2 single-row UPDATEs against live DB, both idempotent and Id+FilePath-scoped. Re-audit: MediaFiles parse-failure 0%, current-data ContentDrift 0, NoPrefixMatch 0. 152 unit tests pass. MediaFilesArchive ContentDrift remains 5 (immutable historical snapshots, out of scope per directive). **Phase 7 caller migration is unblocked.**

### Progress

- [x] Pre-verified Fix 1 row state.
- [x] Applied Fix 1 (1 row affected, committed).
- [x] Pre-verified Fix 2 row state.
- [x] Applied Fix 2 (1 row affected, committed).
- [x] Re-ran audit; current-data ContentDrift = 0, NoPrefixMatch = 0, overall failure rate 0.0000%.
- [x] Regression check -- 152 unit tests pass.
- [x] Close + commit + push.

### Files

```
(no files modified -- 2 SQL UPDATEs against live DB only)
```

### Verification

- Pre-state matched directive (MediaFiles id=22899 .mp4 / .avi drift; id=687504 `mnt\media_tv\...`). Both UPDATEs scoped by Id AND FilePath; idempotent.
- Fix 1: `UPDATE MediaFiles SET RelativePath=... WHERE Id=22899 AND FilePath=...` → 1 row affected, committed.
- Fix 2: `UPDATE MediaFiles SET FilePath='T:\The Boroughs\...' WHERE Id=687504 AND FilePath='mnt\media_tv\...'` → 1 row affected, committed.
- Post-audit: MediaFiles ContentDrift dropped 1 → 0. NoPrefixMatch dropped 1 → 0. Overall parse-failure rate dropped 0.0010% → 0.0000%. MediaFilesArchive ContentDrift remains 5 (immutable history, out of scope).
- Regression intact: 152 unit tests pass.

### Findings

- Phase 6's diagnosis confirmed: id=687504's typed pair was already correct; only the legacy FilePath was malformed. Cleanup touched the legacy column, not the typed pair. Phase 7 callers reading the typed pair were never affected for this row.
- id=22899 cleanup brought the typed pair into sync with the FilePath (transcoded-file form). Going forward this row resolves cleanly via Path.FromRow.

### Promotions

| Source artifact | Target file | Status |
|---|---|---|
| no promotions | n/a | pure data fix; no contract amendments |
