# Backlog Directive: SQL to Repository (Architecture Pass)

**Filed:** 2026-06-01 (by `drop-api-prefix` mid-session discovery that 15 of 16 controllers embed inline triple-quoted SQL)
**Status:** Backlog -- not yet started
**Slug:** sql-to-repository
**Triggered by:** `drop-api-prefix` session 2 audit revealed near-universal embedding of triple-quoted SQL strings in controllers. The R12 hook update (2026-06-01) refuses triple-quoted SQL and mandates Repository placement for business-logic SQL, but the architecture doc this refusal points at (`.claude/rules/sql-architecture.md`) does not exist yet, and no Repository structure exists for several feature verticals. This directive writes the architecture doc and executes the extraction.

## Outcome

`.claude/rules/sql-architecture.md` exists and is the canonical reference for how SQL is written and where it lives in MediaVortex. Every business-logic file (controllers, services, view models) is free of triple-quoted SQL strings and inline SQL. All SQL lives in `Repositories/<X>Repository.py` methods, written as implicit string concatenation. Scripts (`Scripts/SQLScripts/`, `Scripts/QueryDatabase.py`), Tests (`Tests/`), and SQLQueriesController (operator-typed SQL) retain inline SQL by exemption -- but still use implicit string concatenation. R12's SQL detection branch fires on zero in-scope files. The R12 hook's refusal message links to the now-existing `sql-architecture.md`.

## Acceptance Criteria

1. **Architecture rule written.** `.claude/rules/sql-architecture.md` exists with these sections:
   - **Format rule.** SQL strings use implicit string concatenation. Triple-quoted SQL is forbidden. Right shape: `("SELECT col1, col2 " "FROM tbl " "WHERE id = %s")`. Wrong shape: `"""SELECT col1, col2 FROM tbl WHERE id = %s"""`.
   - **Placement rule.** Business-logic SQL belongs in `Repositories/<Feature>Repository.py` methods. Controllers / services / view models call repository methods; they do not write SQL.
   - **Placement exemptions.** `Scripts/SQLScripts/*` (migrations -- by R11 idempotent), `Scripts/QueryDatabase.py` (ad-hoc diagnostic CLI), `Tests/` (test setup/assertion fixtures), `Features/SQLQueries/SQLQueriesController.py` (executes operator-typed SQL from request body, not a hardcoded string). All exemptions still honor the format rule.
   - **Dynamic queries.** When a query is assembled from filter parameters, the assembly happens in the Repository method. Static SQL fragments use implicit string concatenation; dynamic parts (WHERE clauses, IN lists) are parameterized via `%s` placeholders.
   - **Repository naming.** Per-feature `Repositories/<Feature>Repository.py`. Cross-feature DB utility code stays in `Repositories/DatabaseManager.py`.
   - **One method per query.** Each Repository method owns one query (or one query + its dynamic-WHERE assembly). No general-purpose `Execute(query, params)` indirection that bypasses the Repository abstraction.

2. **R12 message updated** to link the new doc. The hook's SQL refusal text appends: `"See .claude/rules/sql-architecture.md for the canonical pattern."`. Verifiable: trigger R12 with a synthetic triple-quoted SQL Write; refusal message contains the new path.

3. **Zero triple-quoted SQL in business-logic files.** Across `Features/*/<Controller|Service|ViewModel|BusinessService>*.py`, `WebService/*.py`, `WorkerService/*.py`, `Models/*.py`, `Core/*.py`, `Repositories/*.py` (yes -- even Repositories use implicit concatenation, not triple-quotes), `grep -P '"""[\s\S]{0,200}\b(SELECT|INSERT INTO|UPDATE \w+ SET|DELETE FROM|CREATE (TABLE|INDEX|VIEW)|DROP (TABLE|INDEX|VIEW)|ALTER TABLE)'` returns zero matches. Verifiable: a grep-based audit script enumerates findings; expected count is 0.

4. **Zero inline SQL in controllers, services, view models, business services.** `grep -E 'Execute(Query|NonQuery)\(' Features/*/<Controller|Service|ViewModel|BusinessService>*.py WebService/*.py WorkerService/*.py` returns zero matches. The exception list (`Scripts/SQLScripts`, `Scripts/QueryDatabase.py`, `Tests/`, `SQLQueriesController`) is permitted. Verifiable: audit script enumerates each match; non-zero matches outside the exemption list are violations.

5. **Repository surface mapped.** A migration manifest at the directive's `## Status` block lists every controller/service that had SQL extracted, with columns: `Source file:line` -> `Target Repository:method` -> `Query shape one-liner`. At least 15 controllers + their associated services are tracked. Verifiable: the manifest is non-empty and every source file in the manifest grep-clean (criteria 3 + 4) post-extraction.

6. **All extracted Repository methods unit-tested.** For every new Repository method, a contract test exercises it against the live DB OR a Mock that asserts the SQL shape. Tests live in `Tests/Contract/`. Verifiable: `py -m pytest Tests/Contract/` passes; test count rises by at least the number of new Repository methods.

7. **R12 SQL-detection branch returns zero hits on in-scope files.** After extraction completes, intentionally try to Edit a controller adding `Db.ExecuteQuery("""SELECT 1""")`. R12 refuses with the SQL-specific message. Try the same in a Repository file. R12 refuses with the SQL-specific message (format rule still applies). Try in a `Scripts/SQLScripts/` migration -- R12 refuses with the placement-exempt message (format rule only). All three behaviors verifiable via synthetic Edits during VERIFYING.

8. **Migrations and tests audited for format compliance.** Even though placement-exempt, `Scripts/SQLScripts/*.py` and `Tests/*` are swept for triple-quoted SQL and converted to implicit string concatenation. Verifiable: same grep as criterion 3, scope expanded to those paths; result zero.

9. **CLAUDE.md cross-reference.** CLAUDE.md "Key patterns" section (currently shows `DatabaseService.ExecuteQuery(...)`) is updated to say SQL belongs in Repositories with implicit string concatenation, with a one-line link to `sql-architecture.md`.

10. **No behavior change.** End-to-end smoke: the WebService starts, every page loads, the deferred `/api/...` endpoints (and the in-scope-renamed ones) return the same JSON shape and status codes as before. `py -m pytest Tests/Contract/` matches the pre-directive pass/fail count. Verifiable: smoke run + test suite results recorded in Verification.

## Out of Scope

- Performance optimization of extracted queries. The extraction preserves existing query semantics; tuning is a separate concern.
- Schema changes. Migrations stay in `Scripts/SQLScripts/`; this directive doesn't add or alter tables.
- Replacing `DatabaseService` / `DatabaseManager` infrastructure. They remain the connection-layer primitives; Repositories sit on top.
- ORM introduction. This directive uses raw SQL via psycopg2; no SQLAlchemy or similar.
- Stored procedures. None currently used; not introduced here.

## Constraints

- Every Repository method name is a verb-phrase describing what it does (e.g. `GetMediaFilesByPriority`, `MarkAudioComplete`, `DeleteOrphanedTfp`). Match `feature-docs.md` Workflow column conventions.
- Repositories DO NOT contain business logic. They translate inputs to SQL and rows to dicts/dataclasses; no decisions, no caching, no conditional behavior beyond the SQL itself.
- All SQL in Repository methods uses implicit string concatenation. Triple-quoted SQL is refused even there.
- LIKE queries continue to require `EscapeLikePattern()` per R9.
- Per `db-is-authority.md` rule: no cached settings on Repository instances. Each method reads fresh.
- Per R10: Claim functions use `BuildClaimPredicate`.

## Escalation Defaults

- If a query spans data from multiple feature verticals: prefer the consumer feature's Repository, OR `Repositories/DatabaseManager.py` for cross-feature plumbing. Escalate if neither fits.
- Risk tolerance: medium-high. Architecture passes are uncertainty-heavy at the seams; budget extra time for unexpected coupling discoveries.
- If a controller has 20+ inline queries and per-method extraction would dominate the session: surface the count, propose splitting that controller's extraction to its own session.

## Engineering Calls Already Made

- Repositories produce dataclass instances OR `CaseInsensitiveDict` (existing pattern). Decision per Repository file, documented in its module-level one-line comment.
- New Repositories created when no per-feature Repository exists (e.g. `Repositories/ActivityRepository.py` if Activity has no existing one). Existing Repositories extended in place.
- Repository methods do not handle Flask `request` / `jsonify`; they receive parsed inputs and return Python data. Controllers translate.
- Migrations are placement-exempt because R11 already enforces their idempotency invariants -- moving each migration's SQL to a Repository would add ceremony without payoff for one-shot schema changes.

## Sequencing rationale

Runs SECOND in the three-directive chain (flow-docs-as-hub -> sql-to-repository -> drop-api-prefix). Reason: (a) the architecture pass touches every controller, so R18 partial-Read discipline + flow-doc surgical navigation (added by flow-docs-as-hub) reduce per-controller cost; (b) once SQL is out of controllers, they become thin enough that the URL rename in drop-api-prefix is mechanically trivial.

## Status

Backlog -- not yet started. Promote to active by:

1. Copying this file's body into `.claude/directive.md`
2. Updating Status line to `Active YYYY-MM-DD -- phase: NEEDS_STANDARDS_REVIEW`
3. Setting **Filed:** to **Set:**
4. `git rm .claude/directives/backlog/sql-to-repository.md`

### Pre-flight inventory (audit baseline for session 1)

Confirmed by 2026-06-01 grep against `Features/**/*Controller*.py`:

```
Features/Activity/ActivityController.py
Features/AudioCompletion/AudioCompletionController.py
Features/ClipBuilder/ClipBuilderController.py
Features/FailureTracking/FailureTrackingController.py
Features/FileScanning/FileScanningController.py
Features/MediaProbe/MediaProbeController.py
Features/QualityTesting/QualityTestController.py
Features/ServiceControl/ServiceControlController.py
Features/ServiceControl/ServiceStatusController.py
Features/ShowSettings/ShowSettingsController.py
Features/SQLQueries/SQLQueriesController.py  -- placement-exempt
Features/TeamStatus/TeamStatusController.py
Features/TranscodeJob/TranscodeJobController.py
Features/TranscodeQueue/AudioFixPriorityHintsController.py
Features/TranscodeQueue/QueueResetController.py
Features/TranscodeQueue/TranscodeQueueController.py
```

Services and view models will be audited at NEEDS_PLAN.
