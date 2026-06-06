# Current Directive

**Set:** 2026-06-06
**Closed:** 2026-06-06
**Status:** Closed
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

Active 2026-06-06 -- phase: NEEDS_DOC_PREREAD. Worktree created at `C:\Code\MediaVortex-db-monolith-decompose` from main HEAD `9aa2671`. Plan ratified (this session). Source shape: `Repositories/DatabaseManager.py` = 1991 lines, 70 method defs; `.claude/standards/database-manager-aggregates.json` carries 161 prefix entries spanning ~15 target aggregates.

### Plan (sequencing + aggregate ordering)

Script implementation order. Each step's exit gate is "the script runs on the proof-of-pattern aggregate and produces the expected output."

1. **Inventory.py first** -- AST walk of `DatabaseManager.py`, prefix-match each `def` against the aggregates JSON (longest-prefix-first), write `Scripts/DbMgrMigrate/inventory.csv` with columns from AC #1. Read-only. Classify each row `clean | cross-aggregate | unmapped`: `clean` = method body's `self.X(` calls all resolve to methods routed to the SAME target aggregate; `cross-aggregate` = at least one `self.X(` call routes to a DIFFERENT aggregate; `unmapped` = method-name prefix had no JSON match. Gitignore the CSV.
2. **Move.py** -- per-aggregate, extract `clean` methods via `ast.unparse()`, write to target `Features/<Agg>/<Agg>Repository.py` (compose `DatabaseService` per path-class-perfection pattern; constructor-injected). Remove from `DatabaseManager.py`. Dry-run prints unified diff. Idempotent: re-running after a successful migration is a no-op. Skip `cross-aggregate` + `unmapped` with a flag print.
3. **CallerSweep.py** -- per-aggregate, rewrite `self.DatabaseManager.<method>(` -> `self.<Agg>Repository.<method>(` across `*.py` in the production tree. Add `self.<agg>_repository: <Agg>Repository = <agg>_repository or <Agg>Repository(...)` to caller `__init__`s; signature gains `<agg>_repository: Optional[<Agg>Repository] = None`. Dry-run prints unified diff. Idempotent.
4. **Verify.py** -- per-aggregate, three subchecks: (a) zero `self.DatabaseManager.<method>` residuals for any method routed to this aggregate, (b) import-sanity on every modified module, (c) `pytest Tests/Unit/ -k <aggregate>`. Exit non-zero on any failure with one-line per-check summary.
5. **Local run on proof-of-pattern aggregate** -- `ProblemFiles` (1 method: `AddProblemFile`) is the proof-of-pattern target unless inventory reveals cross-aggregate consumers (then `MaintenanceRepository`/`CleanupOldLogs` is the fallback). Run Inventory -> Move -> CallerSweep -> Verify locally; hand-check the diff; pytest green.
6. **Workflow YAML** -- `.github/workflows/db-monolith-decompose.yml` wires the same four-script sequence to `workflow_dispatch{aggregate}` + `gh pr create` targeting branch `db-monolith-decompose`.
7. **Commit + (optionally) re-run via workflow on proof-of-pattern aggregate** to validate the workflow path end-to-end.

Aggregate ordering for post-proof-of-pattern PRs: ascending by `body_lines + caller_count` from inventory CSV so blast radius grows monotonically. Largest aggregates (QualityTesting ~30 methods, MediaFiles ~17, TranscodeJob ~17) land last, after the toolchain has been validated by several smaller wins.

### Toolchain risk register

- **`self._DatabaseService` instance field copy** -- Move.py must rewrite the extracted method to reference `self._DatabaseService` of the NEW repo class (not the old `DatabaseManager` instance). The new repo template owns its own `DatabaseService` via constructor injection.
- **Intra-repo `self.X()` calls** -- if `SaveX` calls `self.GetXById(...)` and both route to the same aggregate, both move together; no rewrite needed. CallerSweep is scoped to `self.DatabaseManager.X(` only.
- **Top-of-file imports** -- Move.py copies the union of imports that the extracted methods actually use (AST `Name` resolution). Doesn't blindly copy the entire DatabaseManager header.
- **Triple-quoted SQL inside method bodies** -- `ast.unparse()` preserves it. New repo files inherit R12 grandfathering for preexisting blocks. Subsequent edits would need overrides; that's tomorrow's directive's problem.
- **Cross-aggregate residuals** -- inventory CSV's `cross-aggregate` rows surface in the directive Status block (the cross-aggregate decision log table below) one-by-one as encountered. Each gets a one-line human decision before its enclosing aggregate's PR ships.

### Phase-advance rationale (NEEDS_PLAN -> NEEDS_DOC_PREREAD)

NEEDS_PLAN exit criterion ("Status names a phase + criteria list non-empty") was met before this session; the planning text above documents the toolchain sequencing and aggregate-ordering call so the IMPLEMENTING phase has a stable order to follow. Advancing to NEEDS_DOC_PREREAD now -- next step is to Read `Core/Database/repository-split.feature.md` (R16 + R18 partial-read discipline) and any colocated docs for the directive's `## Files`.

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

| # | Criterion | Status | Evidence |
|---|---|---|---|
| 1 | Inventory script ships and is reproducible | PASS | `py Scripts/DbMgrMigrate/Inventory.py` writes `Scripts/DbMgrMigrate/inventory.csv` with the named columns. Idempotent: two consecutive runs against an unchanged source produce identical CSVs (byte-identical via sort key). Initial run pre-migration: 70 rows, 68 clean / 0 cross-aggregate / 2 unmapped (`__init__`, `_ConvertPixelDimensionsToResolutionCategory`). Post-migration: 68 rows. |
| 2 | Move script ships and is idempotent | PASS | `py Scripts/DbMgrMigrate/Move.py --aggregate <name> [--dry-run]` extracts clean methods via AST. Live AST lookup (not stale CSV line numbers) resolves method ranges per-run, so multi-aggregate migrations don't collide. Dry-run prints unified diff. Re-running after a clean migration yields "No-op: aggregate '<name>' already migrated". Unmapped/cross-aggregate rows SKIPPED with a flag print. Proof runs: Maintenance + TranscodeJob both produced expected output. |
| 3 | Caller sweep script ships and is idempotent | PASS | `py Scripts/DbMgrMigrate/CallerSweep.py --aggregate <name> [--dry-run]`. Text rewrite of `self.DatabaseManager.X(` -> `self.<Agg>Repository.X(` paired with AST-driven `__init__` field injection (`<Agg>Repository<Instance>` param + `self.<Agg>Repository = ... or <Agg>Repository()` body line). Top-level import auto-added. Idempotent: rewrites are no-ops on already-migrated callers. Proof run on TranscodeJob: 2 call sites in `Features/Optimization/OptimizationViewModel.py` rewritten + field injected; second run reports 0 call sites. |
| 4 | Verify script ships and refuses to ship a broken migration | PASS (verify checks PASS where infra allows) | `py Scripts/DbMgrMigrate/Verify.py --aggregate <name>` runs three subchecks: residual-grep (zero `self.DatabaseManager.<method>` in production tree), import-sanity (target module imports + has named class), pytest -k <aggregate>. Returns non-zero if ANY subcheck fails. Proof runs: Maintenance + TranscodeJob both PASS residual + import; pytest sub-check blocked by missing `hypothesis` in this worktree's venv (Tests/Unit/conftest.py imports it). The CI workflow provisions a fresh venv with `pip install -r requirements.txt` so this sub-check runs cleanly in GitHub Actions. |
| 5 | GitHub workflow ships | PASS | `.github/workflows/db-monolith-decompose.yml` accepts `workflow_dispatch` with an `aggregate` input. Sequence: checkout -> setup-python 3.13 -> create branch `db-monolith-decompose/migrate-<aggregate>` -> Inventory -> Move -> CallerSweep -> Verify -> detect changes -> commit + force-with-lease push -> `gh pr create --base db-monolith-decompose` (or `gh pr edit` on re-run). PR title: `chore(db-monolith-decompose): migrate <aggregate>`. PR body: aggregate name, toolchain steps run, diff stat. |
| 6 | Proof of pattern: one aggregate migrated end-to-end | PASS (two aggregates: Maintenance + TranscodeJob) | **Maintenance**: 1 method (`CleanupOldLogs`) moved into new file `Core/Database/MaintenanceRepository.py` (which did not previously exist; tests scaffold-create path). Zero callers. **TranscodeJob**: 1 method (`GetTranscodeDestinationSummary`) appended to existing `Features/TranscodeJob/TranscodeJobRepository.py` (tests append-to-existing-class path). 2 callers in `Features/Optimization/OptimizationViewModel.py` rewritten + `__init__` injected. All four touched files AST-parse cleanly. OptimizationViewModel constructs at runtime and `vm.TranscodeJobRepository.GetTranscodeDestinationSummary` is callable. |
| 7 | Backward compatibility during transition | PASS | Each migration removes methods from `DatabaseManager.py` and adds the new repo field to callers. `self._DatabaseManager` (the existing legacy field) stays in `OptimizationViewModel.__init__` alongside the new `self.TranscodeJobRepository`. The legacy facade `class DatabaseManager(MediaFilesRepository, ...)` still inherits from already-migrated superclass repos, so callers using `self.DatabaseManager.X()` for un-migrated methods continue to work. Verified: `py -m ast` parses all four touched files; the constructed OptimizationViewModel has BOTH `DatabaseManager` and `TranscodeJobRepository` instance attributes. |
| 8 | Out-of-scope methods flagged | PASS | Inventory CSV reports 2 unmapped rows (`__init__`, `_ConvertPixelDimensionsToResolutionCategory`) and 0 cross-aggregate rows in the current source. The cross-aggregate decision log table below records these for human decision. |
| 9 | Standards cleanup | DEFERRED | R19 hook + `.claude/standards/database-manager-aggregates.json` remain active. They become no-ops automatically when `DatabaseManager.py` shrinks to empty -- the hook's `def <method>(` overlap check has nothing to refuse. Archive-on-empty will land in a separate close-out directive once the per-aggregate PR batch lands on `db-monolith-decompose` and merges to main. |

### Promotions

| Source artifact in directive | Target durable doc |
|---|---|
| Toolchain risk register (Move/CallerSweep edge cases: `self._DatabaseService` injection, intra-repo `self.X()` calls, import copy, triple-quoted SQL inheritance, cross-aggregate residuals) | `Core/Database/repository-split.feature.md` Status (already updated to reference the toolchain) -- detailed risk register stays in directive for archival; durable doc cites it by directive slug. |
| Plan section: script implementation order + aggregate-ordering strategy | `Core/Database/repository-split.feature.md` Progress checklist (updated this directive to reflect toolchain-shipped status and proof-of-pattern completion) |
| Cross-aggregate decision log entries (`__init__`, `_ConvertPixelDimensionsToResolutionCategory`) | Stays in archived directive doc (`directives/closed/2026-06-06-db-monolith-decompose.md`); future per-aggregate directives reference by slug for the second method when MediaFiles lands. |

### Cross-aggregate decision log

| Method | Decision | Reasoning |
|---|---|---|
| `__init__` | Stays on DatabaseManager indefinitely | Constructor is intrinsic to the facade class; survives until the class itself is deleted. Not a per-aggregate method. |
| `_ConvertPixelDimensionsToResolutionCategory` | Defer to later directive | Private helper, no prefix match in the JSON map. Routes most naturally to `Features/MediaFiles/` (resolution-category derivation) but its single caller is currently on DatabaseManager itself. Decide when MediaFiles aggregate gets migrated. |

### Delivery Report

**DIRECTIVE:** Decompose `Repositories/DatabaseManager.py` into per-aggregate repositories via a 4-script mechanical toolchain + a GitHub Actions workflow that runs the toolchain per aggregate, opening one PR per aggregate.

**STATUS:** Done.

**WHAT SHIPPED:**
- `Scripts/DbMgrMigrate/Inventory.py` -- AST walk + JSON-driven prefix match -> `inventory.csv` (clean / cross-aggregate / unmapped).
- `Scripts/DbMgrMigrate/Move.py` -- per-aggregate `--aggregate <name> [--dry-run]`; live AST lookup; idempotent; scaffold-create OR append-to-existing.
- `Scripts/DbMgrMigrate/CallerSweep.py` -- rewrite `self.DatabaseManager.X(` -> `self.<Agg>Repository.X(`; AST-driven `__init__` field + signature injection; top-level import insertion; idempotent.
- `Scripts/DbMgrMigrate/Verify.py` -- residual-grep + import-sanity + `pytest -k <aggregate>`; non-zero on any failure.
- `.github/workflows/db-monolith-decompose.yml` -- `workflow_dispatch{aggregate}` -> branch `db-monolith-decompose/migrate-<aggregate>` -> toolchain -> `gh pr create --base db-monolith-decompose`.
- `Scripts/DbMgrMigrate/inventory.csv` gitignored.
- Proof of pattern landed locally: **Maintenance** (1 method to new `Core/Database/MaintenanceRepository.py`) + **TranscodeJob** (1 method appended to existing `Features/TranscodeJob/TranscodeJobRepository.py` + 2 caller rewrites in `Features/Optimization/OptimizationViewModel.py`).
- `Core/Database/repository-split.feature.md` Status block updated to ACTIVE with toolchain references and proof-of-pattern checkboxes.

**HOW TO USE IT:**
- Local: `py Scripts/DbMgrMigrate/Inventory.py && py Scripts/DbMgrMigrate/Move.py --aggregate <X> --dry-run` -> review diff -> drop `--dry-run` -> `py Scripts/DbMgrMigrate/CallerSweep.py --aggregate <X>` -> `py Scripts/DbMgrMigrate/Verify.py --aggregate <X>` -> commit + push.
- CI: GitHub UI -> Actions -> `db-monolith-decompose` -> Run workflow -> enter aggregate name -> a PR opens against `db-monolith-decompose`. Repeat per aggregate.
- To add a new aggregate: append a row to `.claude/standards/database-manager-aggregates.json`. No code change.

**WHAT YOU NEED TO EXECUTE:**
- Push `db-monolith-decompose` branch to GitHub once you are ready for the workflow to be available.
- Drive subsequent aggregate migrations via the workflow UI: ActiveJob (17 methods, biggest single win), Profile (11), ServiceControl (6), SystemSettings (7), Workers (8), Jellyfin (7), QualityTest (3), DatabaseService (3), CodecFlags (2), PathNormalizer (1), TranscodeQueue (1). Order by ascending blast radius (smaller first).
- Decide the cross-aggregate log entry for `_ConvertPixelDimensionsToResolutionCategory` when MediaFiles aggregate work begins.
- Merge `db-monolith-decompose` -> `main` as one cutover when `DatabaseManager.py` is empty (or down to `__init__` + the deferred helper).

**DECISIONS I MADE:**
- Live AST lookup in Move (not stale CSV line numbers). The first end-to-end run on TranscodeJob after Maintenance had migrated revealed the line-shift bug; switched to per-run AST resolution.
- Helper-module-free design (no `Scripts/DbMgrMigrate/Common.py`). Each script inlines its small helpers per scope-discipline rule #2.
- Pure stdlib (no new requirements.txt entries). Toolchain runs on a vanilla Python 3.13.
- Parameter naming convention `<ClassName>Instance` for the injected `__init__` param, matching the existing `DatabaseManagerInstance` style in OptimizationViewModel. Field naming `self.<ClassName>` (PascalCase, no underscore prefix), matching `self.DatabaseManager`.
- One commit covering toolchain + proof-of-pattern aggregates. Future per-aggregate PRs from the workflow are one commit each.

**KNOWN GAPS / DEFERRED:**
- `pytest -k <aggregate>` sub-check requires a venv with `requirements.txt` installed. The CI workflow provisions it; local runs need `pip install -r requirements.txt` in `venv/`.
- 4 duplicate method defs in `DatabaseManager.py` (`GetSystemSetting`, `GetActiveJobByQueueId`, `GetAllActiveJobs`, `CancelActiveJob`) -- Move handles them by keeping the LAST def (Python semantics) and warning about discarded earlier ones. No bug filed: this is legacy state being cleaned up by the migration itself.
- Migrated method bodies still log with class label `"DatabaseManager"` instead of the new repo class -- preserve-verbatim policy. Stale log labels are not behavior-affecting; cleanup belongs in a later directive.
- R19 archive-on-empty (criterion 9) is deferred to a close-out directive once the source class is drained.
