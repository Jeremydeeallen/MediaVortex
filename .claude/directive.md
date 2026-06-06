# Current Directive

**Set:** 2026-06-06
**Status:** Active 2026-06-06 -- phase: NEEDS_PLAN
**Slug:** db-monolith-decompose
**Worktree:** `C:\Code\MediaVortex-db-monolith-decompose` on branch `db-monolith-decompose`
**Predecessor (context):** path-class-perfection (closed at 17bb44f) -- post-close honest review surfaced this as the biggest SOLID violation remaining.

## Outcome

`Repositories/DatabaseManager.py` is decomposed into per-aggregate repositories living in `Features/<Aggregate>/<Aggregate>Repository.py`, with the mechanical migration driven by a 4-script toolchain (`Scripts/DbMgrMigrate/`) and a GitHub Actions workflow that runs the toolchain per aggregate, opening one PR per aggregate. After this directive: `DatabaseManager.py` is empty (or deleted), every service depends on per-aggregate Repos via constructor injection, and the R19 steering hook can be retired.

This directive ships the TOOLCHAIN + the WORKFLOW + the first one or two aggregate migrations as a proof of pattern. The remaining aggregates land via subsequent CI-driven PRs without an active in-Claude directive -- the workflow IS the implementation surface.

## Acceptance Criteria

1. **Inventory script ships and is reproducible.** `py Scripts/DbMgrMigrate/Inventory.py` walks `Repositories/DatabaseManager.py` via Python `ast`, joins each method to its target aggregate via `.claude/standards/database-manager-aggregates.json`, and writes `Scripts/DbMgrMigrate/inventory.csv` with columns: `method_name, target_aggregate, target_file, line_start, line_end, body_lines, caller_count, classification`. Classification = `clean | cross-aggregate | unmapped`. Re-running produces an identical CSV when the source is unchanged.

2. **Move script ships and is idempotent.** `py Scripts/DbMgrMigrate/Move.py --aggregate <name> [--dry-run]` extracts methods classified `clean` for the named aggregate, writes them to the target repository file (creates the file with proper boilerplate if missing), and removes them from `DatabaseManager.py`. Dry-run prints a unified diff to stdout without writing. Re-running after a clean migration is a no-op. Cross-aggregate and unmapped methods are SKIPPED with a flag printed for human review.

3. **Caller sweep script ships and is idempotent.** `py Scripts/DbMgrMigrate/CallerSweep.py --aggregate <name> [--dry-run]` walks all `*.py` files, rewrites `self.DatabaseManager.X()` -> `self.<Aggregate>Repository.X()` where X is one of the named aggregate's methods, and adds the new repository field to caller `__init__`s when missing. Constructor injection follows the path-class-perfection pattern (`def __init__(self, ..., <agg>_repo: Optional[<Agg>Repository] = None)` defaulting to fresh construction). Dry-run prints unified diff. Idempotent across re-runs.

4. **Verify script ships and refuses to ship a broken migration.** `py Scripts/DbMgrMigrate/Verify.py --aggregate <name>` runs: (a) residual grep for `self.DatabaseManager.<method>` for any of the aggregate's methods -- must be zero in production code, (b) import-sanity test on every modified module, (c) `pytest Tests/Unit/ -k <aggregate>` -- exits non-zero on any failure with a one-line summary per check.

5. **GitHub workflow ships.** `.github/workflows/db-monolith-decompose.yml` accepts `workflow_dispatch` with an `aggregate` input. Runs Inventory -> Move -> CallerSweep -> Verify -> `gh pr create` opening a PR titled `chore(db-monolith-decompose): migrate <aggregate>` with the diff as the body. The workflow runs against `db-monolith-decompose` (this branch) -- PRs target this branch, not main, until the full migration is ready to merge.

6. **Proof of pattern: one aggregate migrated end-to-end.** Pick the smallest aggregate from the inventory CSV (lowest method count). Run the full workflow manually (or invoke the scripts locally) to produce a clean PR. The PR merges to `db-monolith-decompose`. The migrated aggregate's `Features/<X>/<X>Repository.py` exists; `DatabaseManager.py` no longer contains those methods; pytest is green; WebService + WorkerService import-sanity holds.

7. **Backward compatibility during transition.** Until the last aggregate lands, `DatabaseManager.py` keeps its un-migrated methods. Services with mixed dependencies hold BOTH `self._DatabaseManager` (for un-migrated) AND `self._<Agg>Repository` (for migrated). One field disappears per aggregate PR merged. No big-bang.

8. **Out-of-scope methods flagged.** The inventory CSV's `cross-aggregate` and `unmapped` rows constitute a human-decision list. The directive's Status block records each one as it's encountered with a one-line decision (which aggregate gets it, or stays on DatabaseManager indefinitely, or moves to a new shared utility module).

9. **Standards cleanup.** When `DatabaseManager.py` shrinks to empty or near-empty, the R19 hook + `.claude/standards/database-manager-aggregates.json` get archived (R19 stays in the hook but its trigger condition becomes a no-op when the monolith is gone). Directive close-out records when this happens.

## Out of Scope (filed as backlog directives)

These are documented as the SOLID-completion follow-ups; this directive is step 1 of 4. The other 3 are filed in `.claude/directives/backlog/` so they don't get lost:

- **`dbsession-protocol-extract`** -- Repos depend on a `DatabaseSession` Protocol, not the concrete `DatabaseService` + `psycopg2`. Unlocks SQLite-for-tests, in-memory tests, engine swaps.
- **`query-vs-write-split`** -- CQRS-light: per-aggregate `<X>Reader` + `<X>Writer` separation so reads can be cached aggressively while writes stay DB-truth.
- **`business-service-decompose`** -- The 2000+ line services (FileScanning, QualityTesting, TranscodeJob) get sub-module decomposition. Each is its own directive, sequenced after the repo split lands.

## Constraints

- **Worktree isolation.** This directive's work happens entirely on branch `db-monolith-decompose` in worktree `C:\Code\MediaVortex-db-monolith-decompose`. Main worktree at `C:\Code\MediaVortex` continues uninterrupted on the postgresql maintenance directive.
- **No DB credentials in the GitHub workflow.** The 4 scripts are pure AST + grep + filesystem. No DB calls. The workflow runs against repo source only.
- **One commit per aggregate** (per `feedback_one_logical_change_per_commit.md`). Move + CallerSweep + Verify run as one logical unit, committed together. The workflow enforces this.
- **Backward-compat during transition** is the discipline. No "big bang" rewrite. Each merged aggregate PR leaves the codebase in a buildable + testable + deployable state.
- **Cross-aggregate methods get a human decision.** Don't auto-classify them. Surface in the directive Status block, decide, then re-run the toolchain.
- **PascalCase** for new file/function/class names; the existing R-rule set applies.

## Engineering Calls Already Made

- **Script-driven over agent-driven migration.** Mechanical work doesn't need LLM tokens. Scripts handle 80-90% of cases; LLM handles edge cases (cross-aggregate, test fixtures, the last-mile DatabaseManager shrink).
- **AST over regex.** Method extraction needs to handle multi-line bodies with nested strings/quotes/triple-quoted SQL. `ast.unparse()` (Python 3.9+) is safer than regex slicing.
- **Worktree over branch-in-place.** Multiple directives in flight (postgresql maintenance + this one) without filesystem collisions. Each worktree's `.claude/directive.md` is independent.
- **Workflow targets `db-monolith-decompose` branch, not main.** Per-aggregate PRs land here first; the full migration merges to main as one operator-controlled cutover.
- **JSON-driven aggregate mapping.** `.claude/standards/database-manager-aggregates.json` already exists and is the source of truth. Don't reinvent it.
- **Backward-compat during transition.** Services with mixed dependencies hold both fields; the field disappears per aggregate landed. No risky big-bang.

## Phase machine notes

- Currently NEEDS_PLAN. Next phase advance: plan how to discover the inventory + pick aggregate ordering. After plan is ratified, advance to NEEDS_DOC_PREREAD, then IMPLEMENTING.
- The 4 scripts + the workflow + the proof-of-pattern aggregate constitute the IMPLEMENTING work. VERIFYING records pytest + smoke results. DELIVERING populates Promotions table pointing at `Core/Database/repository-split.feature.md`.

## Status

Active 2026-06-06 -- phase: NEEDS_PLAN. Worktree created at `C:\Code\MediaVortex-db-monolith-decompose` from main HEAD `9aa2671`. Next session reads this file, advances phase, and plans the script implementation order.

### Files (planned)

```
Scripts/DbMgrMigrate/Inventory.py                            -- CREATE
Scripts/DbMgrMigrate/Move.py                                 -- CREATE
Scripts/DbMgrMigrate/CallerSweep.py                          -- CREATE
Scripts/DbMgrMigrate/Verify.py                               -- CREATE
Scripts/DbMgrMigrate/inventory.csv                           -- CREATE (generated; gitignored)
.github/workflows/db-monolith-decompose.yml                  -- CREATE
Core/Database/repository-split.feature.md                    -- EDIT (record this directive's contract in Status; add workflow reference)
Repositories/DatabaseManager.py                              -- EDIT (shrinks per aggregate PR)
Features/<Aggregate>/<Aggregate>Repository.py                -- CREATE per aggregate (~20-30 files total over the migration)
```

### Verification

(Populated at VERIFYING; one entry per acceptance criterion.)

### Promotions

(Populated at DELIVERING.)

### Cross-aggregate decision log

(Populated as `cross-aggregate` and `unmapped` methods surface.)

| Method | Decision | Reasoning |
|---|---|---|
| TBD | TBD | TBD |
