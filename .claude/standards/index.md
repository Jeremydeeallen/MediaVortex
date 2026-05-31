# Standards Index

Single source of truth for what is mechanically gated. The PreToolUse hook (`.claude/hooks/pre-edit-standards.ps1`) cites this file in every refusal.

Override any single check with `# allow: <reason>` within 3 lines of the offending pattern. Reason must be non-empty. All overrides append to `.claude/.standards-overrides.log`.

## Phase gates (`.claude/.session-state.json` driven)

| Phase | Exit criterion | Tools allowed |
|---|---|---|
| NEEDS_STANDARDS_REVIEW | Read every `.claude/rules/*.md` + this file | Read / Grep / Glob / read-only Bash |
| NEEDS_PLAN | Directive doc Status names a phase + criteria list non-empty | + Write directive doc only |
| NEEDS_DOC_PREREAD | Read every `*.feature.md` / `*.flow.md` ancestor of files in plan `## Files` | + Write directive doc only |
| IMPLEMENTING | All content rules pass per Edit/Write | All tools, gated by content rules |
| VERIFYING | Verification section records evidence per criterion | Read / Grep / Bash; Edit directive doc only |
| DELIVERING | Delivery report drafted in directive doc Status | All tools |

## Content rules

| ID | Description | Source | Hook function |
|---|---|---|---|
| R1 | Edit/Write to code requires prior Read of any same-directory `*.feature.md` / `*.flow.md`. Same-directory only -- no walk-up | `.claude/rules/ceo-mode.md` (Documents first) | `Test-R1-DocPreread` |
| R2 | Seed scripts (`Scripts/SQLScripts/Add*.py`): INSERT numeric literals require `# from: <path>` citation; cited path must exist and contain the literal | `.claude/rules/db-is-authority.md` + directive doc criteria 11-12 from prior nvenc-rate-anchored work | `Test-R2-SeedEvidence` |
| R3 | No `self._cached_*` / `self._*_settings` / `self._config_snapshot` in `__init__` of Services / Repositories | `.claude/rules/db-is-authority.md` | `Test-R3-NoCachedSettings` |
| R4 | No `os.environ.get(` / `os.getenv(` outside `Core/Database/DatabaseService.py`, `StartMediaVortex.py`, `StopMediaVortex.py`, `WebService/Main.py` bootstrap, worker `Main.py` bootstrap | `.claude/rules/db-is-authority.md` (data-driven) | `Test-R4-NoEnvVars` |
| R5 | `ExecuteQuery(` cannot wrap `INSERT` / `UPDATE` / `DELETE` strings | `CLAUDE.md` (Database operations) | `Test-R5-ExecuteQueryMisuse` |
| R6 | Path-bearing variables cannot be consumed by `.replace().split(` or `os.path.dirname/basename/join/split(` | `.claude/rules/data-integrity.md` (path shape-agnostic) | `Test-R6-PathShape` |
| R7 | `ON DELETE CASCADE` not allowed on polymorphic FK columns (`QueueId` / `JobId` / `EntityId` / `TargetId`) | `.claude/rules/data-integrity.md` | `Test-R7-PolymorphicCascade` |
| R8 | New `test_*.py` / `Test*.py` files must be under `Tests/Contract/` or `Tests/Unit/` | `.claude/rules/test-placement.md` | `Test-R8-TestPlacement` |
| R9 | `LIKE` queries require `EscapeLikePattern(` in the same function | `CLAUDE.md` (LIKE queries) | `Test-R9-LikeEscape` |
| R10 | `Repositories/` functions starting with `Claim` must call `BuildClaimPredicate` | `.claude/rules/db-is-authority.md` (claim authority) | `Test-R10-ClaimPredicate` |
| R11 | Migrations: `CREATE TABLE`/`CREATE INDEX` requires `IF NOT EXISTS`; `INSERT INTO` requires `ON CONFLICT` | `.claude/rules/data-integrity.md` (idempotent migrations) | `Test-R11-MigrationIdempotency` |
| R12 | No consecutive `#` comment blocks > 1 line, no docstrings > 1 line, no module-level docstrings | `.claude/rules/ceo-mode.md` (single-line code anchor) | `Test-R12-CommentVolume` |
| R13 | No new `*.feature.md` / `*.flow.md` files. New documentation lives in the directive doc only | This file + `.claude/rules/ceo-mode.md` | `Test-R13-NoNewFeatureDocs` |
| R14 | Edits to existing `*.feature.md` / `*.flow.md` cannot add annotation lines (`removed YYYY-MM-DD` / `deprecated` / `no longer used` / `previously` / `formerly`). Delete sections instead | This file + `.claude/rules/ceo-mode.md` | `Test-R14-AnnotationDrift` |
| R15 | Edits to functions/classes in the directive doc's `## Files` section require `# directive: <slug>` line directly above the `def` / `class` | This file | `Test-R15-DirectiveAnchor` |

## What is NOT gated

Judgment-call standards the hook cannot mechanically catch. These remain operator-reviewed:

- Scope discipline ("while I'm here", `NOT IN SCOPE` violations) -- `.claude/rules/scope-discipline.md`
- Feature criteria litmus tests (rename / outsider / rewrite / negation / stability) -- `.claude/rules/feature-criteria.md`
- Semantic doc accuracy (does the doc still describe reality after the code change)
- Evidence-citation realism (R2 verifies the cited file exists and contains the literal; it cannot verify the cited file is REAL evidence vs. a doc Claude wrote to game the gate)
- Naming quality (whether a function/class name is a useful grep anchor per the one-line code-anchor convention)

## How to add a rule

Append one function `Test-R<N>-<Name>` to `.claude/hooks/pre-edit-standards.ps1`. Add a row to the table above. The hook's dispatcher iterates `Get-Command -Module Self -Name 'Test-R*-*'` -- no other plumbing.
