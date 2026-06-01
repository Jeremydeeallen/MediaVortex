# Database Architecture

**Slug:** database-architecture

## What It Does

Defines the runtime contract for every piece of code that reads, writes,
or serializes data through PostgreSQL. Covers connection, type conventions
(especially datetime/UTC), key-casing roundtrip, query patterns, migrations,
and JSON serialization. The frontend-side timezone behavior is owned by
`Features/SystemSettings/display-timezone.feature.md` and
`Features/SystemSettings/timezone-frontend-audit.feature.md`; this doc owns
everything from the database row outward to the bytes Flask writes on the
wire.

## Concern

Captured after the 2026-05-22 Operations-page failure-list rendered
timestamps in the wrong timezone, where the cause was a serialization-path
inconsistency between two endpoints reading the same column. The same gap
caused the foundation `display-timezone.feature.md` (commit 7d9fc3d) to
ship without an enforceable contract: any future endpoint can re-introduce
the bug by bypassing `UtcJsonProvider`. This doc closes that gap by making
the contract grep-verifiable.

## Success Criteria

### A. Datetime storage

1. **Every column that stores an instant in time uses `timestamp without
   time zone`** (TIMESTAMP), not `timestamp with time zone` (TIMESTAMPTZ)
   and not `text`. The application enforces UTC at write time; the DB
   stores the naive UTC value. Verifiable:

   ```sql
   SELECT table_name, column_name, data_type
   FROM information_schema.columns
   WHERE table_schema='public'
     AND (column_name LIKE '%date%' OR column_name LIKE '%time%' OR column_name ~ 'at$')
     AND data_type NOT IN ('timestamp without time zone','bigint')
     AND column_name NOT IN ('audiosampleformat','containerformat','pixelformat',
                              'destformat','destpixelformat','currenttime','starttime','starttimes','logdate');
   ```

   Returns zero rows. (The exclusion list pins known false-positive name
   matches and vestigial dead columns. New date columns must be TIMESTAMP
   or the audit fails.)

2. **The PostgreSQL cluster runs in UTC.** Verifiable: `SHOW timezone;`
   returns `UTC`. Server-side `NOW()` and `CURRENT_TIMESTAMP` therefore
   produce UTC values, interchangeable with Python-side aware-UTC writes.

### B. Datetime writes (Python -> DB)

3. **Every Python write of an instant to a TIMESTAMP column passes a
   timezone-aware UTC `datetime` OR uses the SQL-side `NOW()` token.**
   Naive `datetime.now()` is forbidden because it returns local time and
   silently loses the offset at insertion. `datetime.utcnow()` is also
   forbidden (deprecated in 3.12+, also naive). Verifiable:

   ```bash
   grep -rEn '\bdatetime\.now\(\)|\bdatetime\.utcnow\(\)' \
     --include='*.py' Features/ Repositories/ Services/ Core/ \
     WorkerService/ WebService/
   ```

   Returns zero hits. (One known exception is documented in `Files` below
   if it cannot be eliminated; tests must reference the documented
   exception by line number.)

4. **`datetime.fromtimestamp(t)` is forbidden; use
   `datetime.fromtimestamp(t, tz=timezone.utc)`.** The naive form
   reinterprets a POSIX timestamp as local time and breaks cross-host
   comparisons. The 2026-05-15 cross-worker ping-pong bug (KNOWN-ISSUES
   "FileModificationTime cross-tz") was exactly this. Verifiable:

   ```bash
   grep -rEn 'fromtimestamp\([^,)]+\)' --include='*.py' \
     Features/ Repositories/ Services/ Core/ WorkerService/ WebService/
   ```

   Returns zero hits.

### C. Datetime reads (DB -> Python)

5. **`DatabaseService.ExecuteQuery` returns each row as a
   `CaseInsensitiveDict`** whose values for TIMESTAMP columns are naive
   `datetime` objects (no tzinfo). Application code that compares these
   against tz-aware datetimes must explicitly bridge — either strip the
   tzinfo from the aware side (`aware.replace(tzinfo=None)`) or add UTC to
   the naive side (`naive.replace(tzinfo=timezone.utc)`). Verifiable: a
   contract test in `Tests/Contract/` constructs both forms and asserts
   the bridge is documented.

6. **`CaseInsensitiveDict` preserves PascalCase keys for round-tripping
   to JSON.** PostgreSQL returns lowercase column names; the SELECT-clause
   parser in `DatabaseService._parse_select_columns` rewrites stored keys
   to the PascalCase form written in the SQL. Application code may read by
   either case; serialization always emits PascalCase. Verifiable: a unit
   test constructs a query with mixed casing in the SELECT clause and
   asserts the JSON output uses the PascalCase form.

### D. Datetime serialization (Python -> JSON)

7. **The Flask app sets `app.json = UtcJsonProvider(app)` exactly once at
   startup.** Verifiable:

   ```bash
   grep -rEn 'UtcJsonProvider' --include='*.py' WebService/
   ```

   Returns one assignment site (in `WebService/Main.py`) and zero
   re-assignments after blueprint registration.

8. **Every datetime that reaches `jsonify(...)` is serialized to ISO-8601
   with `Z` suffix** (e.g. `2026-05-22T13:46:19.126366Z`). Verifiable: a
   black-box probe hits every API endpoint that returns a datetime and
   asserts the serialized form matches `^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(\.\d+)?Z$`.
   String forms `2026-05-22 13:46:19.126366` (space, no Z),
   `Fri, 22 May 2026 13:46:19 GMT` (RFC 822), or `2026-05-22T13:46:19`
   (T but no Z) indicate the provider was bypassed or stale code is
   running.

9. **No endpoint calls `str(datetime)`, `datetime.isoformat()`,
   `.strftime()`, or any other manual format on a datetime before passing
   it to `jsonify`.** The provider is the single conversion point.
   Verifiable:

   ```bash
   grep -rEn "str\([A-Za-z_]+Date\)|\.strftime\(" \
     --include='*.py' Features/ Repositories/ Services/
   ```

   Returns zero hits inside controller code paths that build response
   payloads.

### E. Query patterns

10. **`FilePath` equality and LIKE comparisons are case-insensitive** via
    `LOWER(FilePath) = LOWER(?)` or `LOWER(FilePath) LIKE LOWER(?)`. Owned
    by `Docs/DatabaseStandards.md` (existing); referenced here so the full
    DB contract is in one index.

11. **LIKE patterns that interpolate user-provided values escape `%`, `_`,
    and `!` via `EscapeLikePattern()` and include `ESCAPE '!'`.** File
    paths frequently contain `(`, `)`, `_`, `&` etc.; the escape character
    `!` is chosen because it never appears in file paths. Verifiable:
    every `LIKE` query that takes a FilePath parameter is followed by
    `ESCAPE '!'` in the SQL text.

12. **The `transcodeattempts.ffpmpegcommand` column name has a known typo
    (double `p`).** Code MUST match the typo exactly. Documented in
    CLAUDE.md; reasserted here so a future rename is recognized as a
    schema migration, not a bug fix.

### F. Migrations

13. **Every script in `Scripts/SQLScripts/` is idempotent** — re-running
    on an already-migrated database makes no destructive changes and
    affects zero rows on a no-op pass. Use `IF NOT EXISTS`, `ON CONFLICT
    DO NOTHING`, defensive `DO $$ ... END $$` blocks. Owned by
    `.claude/rules/data-integrity.md`.

14. **Adding a `NOT NULL` column requires either a `DEFAULT` value or a
    two-step migration** (add nullable -> backfill -> set NOT NULL). The
    `MediaFilesArchive` table preserves prior values before destructive
    replacements (see `.claude/rules/data-integrity.md`).

## Failure Modes (to recognize at a glance)

| Symptom | Likely cause | Where to look |
|---|---|---|
| API returns `"2026-05-22 13:46:19.126366"` (space, no Z) | `str(datetime)` somewhere before jsonify; OR stale process predating `UtcJsonProvider` | The controller; or the WebService process start time |
| API returns `"Fri, 22 May 2026 13:46:19 GMT"` (RFC 822) | `UtcJsonProvider` not wired; Flask default in use | `WebService/Main.py` `app.json` assignment |
| API returns `"2026-05-22T13:46:19"` (T but no Z) | A naive `isoformat()` call ahead of jsonify | Search for `.isoformat()` in the responding endpoint |
| Cross-worker `HasFileChanged` flips every file | A writer used naive local time (`datetime.now()` or naive `fromtimestamp`) | KNOWN-ISSUES "FileModificationTime cross-tz"; check criterion B3/B4 grep |
| Same physical file shows as two rows | Mixed-case FilePath insertion bypassed `LOWER()` | `Docs/DatabaseStandards.md` |
| Special character in path silently truncates LIKE match | Missing `EscapeLikePattern()` and `ESCAPE '!'` | criterion E11 |

## Surface

This feature has no end-user UI surface — the contract is enforced at
code-review time and via the grep audits in the Success Criteria. The
verification commands above ARE the surface for anyone changing DB code.

## Status

DRAFTED -- awaiting first audit pass to establish baseline.

### Progress

- [x] Doc written; verification grep commands enumerated
- [ ] Run criterion A1 audit; record any non-conformant columns as either
      exclusions (vestigial / not-actually-dates) or migrations
- [ ] Run criterion B3 audit; eliminate the known `WorkerService/Main.py:142`
      `datetime.now()` (stale-threshold compare) OR add it to the
      documented exception list
- [ ] Run criterion B4 audit (`fromtimestamp` without `tz=`)
- [ ] Run criterion D8 endpoint probe; identify any endpoints that ship
      non-Z datetime strings, including the 2026-05-22 Operations-page
      Failures regression
- [ ] Run criterion D9 grep; flag any manual stringification of dates in
      controllers
- [ ] Add a `Tests/Contract/TestDatabaseArchitecture.py` that runs A1, B3,
      B4, D8, D9 as automated regressions

## Scope

```
Core/Database/
Core/Web/UtcJsonProvider.py
Repositories/DatabaseManager.py
Repositories/*Repository.py
Features/*/
WebService/Main.py
WorkerService/Main.py
Scripts/SQLScripts/
```

## Files

| File | Role |
|------|------|
| `Core/Database/DatabaseService.py` | Connection pool, `ExecuteQuery`, `ExecuteNonQuery`, `CaseInsensitiveDict`, SELECT-clause PascalCase parser |
| `Core/Web/UtcJsonProvider.py` | Single conversion point for datetime -> JSON |
| `WebService/Main.py` | Wires `app.json = UtcJsonProvider(app)` and the per-process `MV_TIMEZONE` injection |
| `Repositories/DatabaseManager.py` | Domain repository facade; thin wrapper over `DatabaseService` |
| `Docs/DatabaseSchema.md` | Full column inventory; reference for criterion A1 audit |
| `Docs/DatabaseStandards.md` | FilePath case-insensitivity (criterion E10) |
| `.claude/rules/data-integrity.md` | Migration idempotency + archive-before-destructive (criteria F13, F14) |
| `Features/SystemSettings/display-timezone.feature.md` | Foundation feature for the display layer (downstream consumer of this contract) |
| `Features/SystemSettings/timezone-frontend-audit.feature.md` | Surface-by-surface audit of the display layer |
| `WorkerService/Main.py:142` | Known exception: naive `datetime.now()` used for `timedelta` comparison (not a DB write). Eliminate in Progress step 2. |
