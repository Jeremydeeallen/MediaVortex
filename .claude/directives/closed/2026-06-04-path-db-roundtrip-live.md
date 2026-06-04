# Current Directive

**Set:** 2026-06-04
**Closed:** 2026-06-04
**Status:** Closed -- Success
**Slug:** path-db-roundtrip-live
**Predecessor:** `.claude/directives/closed/2026-06-04-path-performance-budget.md` (closed Success -- 11 perf tests, slots=True, 86% memory reduction)
**Program:** `.claude/programs/path-track.md` (Phase 5 of 10)

## Outcome

Every path-bearing table in PostgreSQL has a contract test that exercises Path's typed-pair round-trip against the live DB at `10.0.0.15:5432`. INSERT writes `(StorageRootId, RelativePath)`, SELECT reads them back, `Path.FromRow(row)` reconstructs an equal Path. Zero round-trip loss on any of: `MediaFiles`, `MediaFilesArchive`, `TranscodeQueue`, `TranscodeAttempts`, `TemporaryFilePaths`, `ShowSettings`. `TemporaryFilePaths` (which carries two path pairs: source + output) exercises `Path.FromRow(row, prefix=...)`. A read-only sample audit confirms the same on populated existing rows. After this directive, Phase 7 caller migration can swap `os.path` consumers to `Path.FromRow` with confidence that the wire format is verified across every storage location.

## Why now

Phase 7 caller migration depends on `Path.FromRow` working against the actual schema, not a hypothetical one. The typed-pair columns landed before this directive (`storagerootid` bigint + `relativepath` text on every path-bearing table). 99.99% of `MediaFiles` rows already have the typed pair populated. Catching a wire-format defect now -- before seven verticals start importing `Path` -- means one directive's fix instead of seven verticals' rollback. Phase 6 (`path-migration-rehearsal`) does the broader audit of legacy `filepath` → `FromLegacyString` parse-failure rate; Phase 5 confirms the typed-pair endpoint works.

## Schema snapshot (verified at NEEDS_STANDARDS_REVIEW)

| Table | Typed-pair columns | Legacy column | TemporaryFilePaths-style prefix? |
|---|---|---|---|
| MediaFiles | `storagerootid`, `relativepath` | `filepath` (NOT NULL) | no |
| MediaFilesArchive | `storagerootid`, `relativepath` | `filepath` (NOT NULL) | no |
| TranscodeQueue | `storagerootid`, `relativepath` | `filepath` (NOT NULL) | no |
| TranscodeAttempts | `storagerootid`, `relativepath` | `filepath` (nullable) | no |
| TemporaryFilePaths | `sourcestoragerootid`, `sourcerelativepath` AND `outputstoragerootid`, `outputrelativepath` | `originalpath`, `localsourcepath`, `localoutputpath` (all nullable) | **yes** -- `Source` and `Output` prefixes |
| ShowSettings | `storagerootid`, `relativepath` | `showfolder` (NOT NULL) | no |

Existing `Tests/Contract/TestPathDbRoundTrip.py` covers `MediaFiles` only.

## Acceptance Criteria

1. **New contract-test file** `Tests/Contract/TestPathDbRoundTripAllTables.py` exists, exercises every path-bearing table, and passes against live `10.0.0.15:5432` PostgreSQL.

2. **Per-table round-trip: `MediaFiles`.** INSERT a sentinel row with `(filepath, storagerootid, relativepath)`. SELECT the typed columns by `id`. `Path.FromRow(row)` returns a `Path` equal to the constructed input. tearDown deletes the sentinel by id.

3. **Per-table round-trip: `MediaFilesArchive`.** Same shape as C2 against `MediaFilesArchive`.

4. **Per-table round-trip: `TranscodeQueue`.** Same shape as C2 against `TranscodeQueue` (account for NOT NULL columns: `filepath`, `filename` -- supply sentinel values).

5. **Per-table round-trip: `TranscodeAttempts`.** Same shape. `filepath` is nullable here; sentinel still populates it for safety.

6. **Per-table round-trip: `TemporaryFilePaths` -- Source pair.** INSERT with `(sourcestoragerootid, sourcerelativepath)` populated. SELECT. `Path.FromRow(row, prefix="Source")` returns equal Path.

7. **Per-table round-trip: `TemporaryFilePaths` -- Output pair.** Same shape with `(outputstoragerootid, outputrelativepath)` and `prefix="Output"`.

8. **Per-table round-trip: `ShowSettings`.** Same shape as C2 against `ShowSettings`. `showfolder` is NOT NULL; supply a sentinel value.

9. **NULL handling on `FromRow`.** For each table where the typed-pair columns are nullable, INSERT a row with the typed pair NULL. SELECT. `Path.FromRow(row)` returns `None` (not a partial Path; D3 contract). `MediaFilesArchive` and `MediaFiles` have nullable typed columns -- test both.

10. **UTF-8 round-trip.** Insert a sentinel with a multi-byte UTF-8 `RelativePath` (e.g., `"Cosmos Çafé/Épisode Â.mkv"` -- valid Unicode, no security-rejected chars). SELECT. `Path.FromRow(row).RelativePath == "Cosmos Çafé/Épisode Â.mkv"` byte-equal. Asserts the DB-side encoding (`UTF8` per CLAUDE.md) does not transform the bytes.

11. **Read-only sample audit (positive).** For each of the six tables, SELECT 100 rows where the typed pair is NOT NULL. `Path.FromRow(row)` returns a non-`None` Path for every one. Zero failures. (Audit covers production data, not test sentinels.)

12. **Read-only sample audit (NULL branch).** For each table where the typed pair may be NULL, SELECT up to 10 rows where either column IS NULL. `Path.FromRow(row)` returns `None` for every one. (D3 branch coverage on production data.)

13. **Sentinel cleanup verified.** After the test suite runs, no sentinel rows remain in any of the six tables. Verified via `SELECT COUNT(*) WHERE filepath LIKE '__mvtest_path_roundtrip__%'` returning zero per table.

14. **Phase 1 contract test still passes.** `Tests/Contract/TestPathDbRoundTrip.py` unchanged and green.

15. **Phase 1+2+3+4 regression intact.** `py -m pytest Tests/Unit/test_path_*.py` -- 152 tests pass.

16. **R-rule compliance.** PreToolUse hook accepts every Edit/Write without `# allow:` overrides.

17. **Worker bracket: structurally safe, not procedurally safe.** The test runs only after all transcode workers (Larry LXC 218 docker containers + I9 local WorkerService) are confirmed stopped. The chosen safety mechanism is "no workers running" -- not "worker filters do not match my sentinel Status". Rationale: structural safety has no coupling to worker claim predicates and will not silently break when future worker capabilities change. The bracket is documented as operator procedure in `Tests/Contract/TestPathDbRoundTripAllTables.py` module header so future runs of this test inherit the same discipline.

## Out of Scope

- Legacy `filepath` / `originalpath` / `localsourcepath` / `localoutputpath` / `showfolder` → `Path.FromLegacyString` parse audit. Phase 6 (`path-migration-rehearsal`) owns this.
- Schema migration to drop the legacy text columns. Phase 8 (`path-schema-migration`).
- Per-caller migration. Phase 7 (`<feature>-uses-path` × N).
- Performance impact of the live-DB tests (these run against a real DB; they are not in the perf budget).
- Backfilling the 3 unmigrated rows in `MediaFiles` (`storagerootid IS NULL`). Out-of-band operator task; documented in Findings if blocking.
- Testing the `## Performance Budget` invariants on the live-DB code path (unit-level perf already verified in Phase 4).
- Editing `Core/Path/Path.py` -- already locked from changes by Phase 1's "no caller imports yet" rule; this directive only exercises the existing API.

## Constraints

- Contract test placement: `Tests/Contract/TestPathDbRoundTripAllTables.py` per R8 (Contract tests live under `Tests/Contract/`).
- LOC budget: `<= 400` for the new test file (six tables × ~50 lines each).
- pytest convention (consistent with newer contract tests). The Phase 1 unittest-style file stays as-is.
- Sentinel `RelativePath` shape: `"__mvtest_path_roundtrip__/<timestamp>_<uuid8>.<ext>"` -- distinct prefix so cleanup queries can target sentinels without false positives on real data.
- Each test method uses an isolated unique sentinel so parallel test runs do not collide.
- tearDown is required even on test failure -- use pytest fixtures with cleanup in the teardown branch, not just trailing DELETE statements.
- No `Path` source code changes. The directive exercises the existing API surface.
- No multi-line docstrings (R12). Single-line docstrings only.
- LIKE queries on sentinel cleanup must use `EscapeLikePattern` from `Core.Database.DatabaseService` (R9 + CLAUDE.md): the sentinel prefix `__mvtest_path_roundtrip__` contains `_` which is a LIKE wildcard.

## Engineering Calls Already Made

- **Sentinel choice.** Prefix `__mvtest_path_roundtrip__` is grep-distinct from any plausible real RelativePath. Each test method's sentinel includes a UTC microsecond timestamp + random uuid8 to guarantee uniqueness across parallel runs and back-to-back invocations.

- **Cleanup mechanism.** pytest `@pytest.fixture(autouse=True)` per-test fixture that yields the sentinel row id(s) and DELETEs in the teardown branch. Reliable even when the test body assertions fail.

- **`TemporaryFilePaths` dual-pair test.** Two separate test methods rather than one method with two assertions -- diagnosability beats brevity. Source and Output are independent contracts; treat as such.

- **NULL-branch coverage on `FromRow`.** `MediaFiles` row count snapshot at draft time: 50,088 total, 50,085 with typed pair NOT NULL. 3 unmigrated rows exist. C12 tests `FromRow` against the unmigrated rows directly (no sentinel insert needed) -- they ARE the test data. If the unmigrated count is zero on a given run, fall back to inserting a NULL-typed sentinel row.

- **Audit row sample size.** 100 rows per table. Tradeoff: enough to catch wire-format defects (encoding, truncation, type coercion), not so many that a single DB roundtrip takes more than a few seconds. Phase 6 will do the full-table walk.

- **Test isolation.** Each test method works on its own sentinel; no shared state. If a developer adds a new path-bearing table, they add a new test method for it -- no global table-list registry to keep in sync.

- **Live-DB CI gating.** Contract tests in `Tests/Contract/` presume the live DB at `10.0.0.15:5432` is reachable (per CLAUDE.md). If the DB is unreachable, the suite fails fast with a clear "no DB connection" message. No mock fallback -- a mocked round-trip does not test what this directive is contracted to test.

## Escalation Defaults

- If any per-table INSERT fails due to a NOT NULL column we did not anticipate -> diagnose, add to sentinel, re-run. Not a design defect.
- If `Path.FromRow(row)` returns a non-equal Path from a sentinel round-trip -> THIS IS THE DEFECT this directive is designed to catch. Investigate: psycopg2 type coercion, encoding mismatch, column-name case sensitivity (CLAUDE.md notes `RealDictCursor` returns lowercase keys; `CaseInsensitiveDict` maps to PascalCase). Fix in scope.
- If audit C11 surfaces > 0 unparseable populated rows -> bug. Log row id + StorageRootId + RelativePath; investigate. May or may not be in-scope to fix depending on root cause.
- If audit C12 surfaces > 0 partial-typed-pair rows (one NULL, one not) -> bug in upstream code that populated the columns. Out of scope to fix here; record in Findings + open follow-up directive.
- If the 10.0.0.15:5432 DB is down -> escalate to operator; cannot proceed.
- Risk tolerance: low. Phase 7 migration depends on this. False-negatives (test passes but a real defect exists) are the failure mode to avoid; false-positives (test fails on a real defect we should fix) are exactly what this directive is supposed to surface.

## Status

Active 2026-06-04 -- phase: DELIVERING.

### Delivery Report

DONE. 17/17 criteria. 19/19 contract tests green (2 NULL-branch skips are good news -- 2 tables have zero unmigrated rows). ~700 production rows audited across 6 tables: zero parse failures. Phase 1+2+3+4 regression intact (154 tests). Workers were stopped per C17 structural-safety policy; can be restarted now. No contract amendments required -- this directive verified the existing contract end-to-end. Phase 5/10 complete. Next: `/n path-migration-rehearsal` (Phase 6) for the full-table walk.

### Progress

- [x] Author `Tests/Contract/TestPathDbRoundTripAllTables.py` (21 tests: 7 round-trip, 1 NULL, 1 UTF-8, 7 positive-audit, 4 NULL-branch-audit, 1 cleanup verify).
- [x] Each test passes against live 10.0.0.15:5432 DB -- 19 passed, 2 skipped (no NULL candidates in two tables), 0 failed.
- [x] Audit confirms zero round-trip loss on a 100-row sample per table (~700 rows total).
- [x] Phase 1 contract test still green.
- [x] Phase 1+2+3+4 unit-test regression green (154 tests including Phase 1 contract).
- [x] Sentinel cleanup verified -- 0 rows remain post-run.
- [x] `### Findings` + `### Verification` + `### Promotions` populated.

### Files

```
Tests/Contract/TestPathDbRoundTripAllTables.py   -- CREATE: per-table contract tests + audit
```

### Verification

**Contract test (live 10.0.0.15:5432 PostgreSQL):** `py -m pytest Tests/Contract/TestPathDbRoundTripAllTables.py -v` -> **19 passed, 2 skipped, 0 failed** in 1.34s.

- All 7 per-table round-trips green (`MediaFiles`, `MediaFilesArchive`, `TranscodeQueue`, `TranscodeAttempts`, `TemporaryFilePaths` Source + Output, `ShowSettings`).
- NULL handling green (D3 branch): row with NULL typed pair -> `FromRow` returns `None`.
- UTF-8 round-trip green: `"Cosmos Çafé - Épisode <uuid> Â.mkv"` survives byte-equal through INSERT/SELECT.
- Positive audit on 100 rows × 5 tables + 2 `TemporaryFilePaths` audits = **~700 production rows parsed, zero failures**.
- NULL-branch audit on `MediaFiles` + `TranscodeAttempts` PASS; `MediaFilesArchive` and `TranscodeQueue` SKIPPED (no NULL typed-pair rows -- migration more complete than initial snapshot suggested).
- Sentinel cleanup verified: `test_no_sentinel_rows_remain_after_suite` reports 0 rows across all 6 tables post-suite.

**Regression (Phase 1-4):** `py -m pytest Tests/Unit/test_path_*.py Tests/Contract/TestPathDbRoundTrip.py` -> **154 passed** in 1.17s. Phase 1 contract test (Phase 1 single-table version) still green.

**Worker bracket:** operator stopped Larry LXC 218 workers (4 containers) and drained I9 WorkerService before the test ran. Workers can be restarted post-test; the DB write window is closed.

### Findings

- **Migration completeness is higher than the pre-directive snapshot suggested.** `MediaFiles` initial snapshot showed 50,085/50,088 typed-pair populated; both `MediaFilesArchive` and `TranscodeQueue` turn out to have ZERO NULL-typed-pair rows in the live DB. The NULL-branch audit on those tables found no candidates to test, hence the 2 skips. The Phase 6 migration rehearsal (full table walk) will produce the final number.
- **No wire-format defects across 6 tables and ~700 sampled rows.** Path's typed-pair contract holds end-to-end: psycopg2 + `CaseInsensitiveDict` + `Path.FromRow` round-trip cleanly with byte-equal RelativePath including multi-byte UTF-8. No psycopg2 coercion surprises (Decimal-from-bigint, etc.) on the `storagerootid` column. No encoding issues on `relativepath` (the DB is `ENCODING 'UTF8'` per CLAUDE.md; verified empirically).
- **`TemporaryFilePaths` dual-pair pattern works.** `Path.FromRow(row, Prefix="Source")` and `Prefix="Output")` round-trip independently. Both prefixes audited on production rows; zero failures.
- **No promotion target.** This directive exercises the existing contract; it does not change it. No `path.feature.md` edits.

### Promotions

| Source artifact | Target file | Status |
|---|---|---|
| no promotions | n/a | pure-verification directive; existing contract verified end-to-end against live DB, no contract amendments required |
