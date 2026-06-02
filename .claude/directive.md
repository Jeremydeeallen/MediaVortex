# Current Directive

**Set:** 2026-06-02
**Status:** Active -- phase: IMPLEMENTING -- criteria approved 2026-06-02; executing.
**Slug:** migrate-bugs-compliance
**Replaces:** (none -- framework maintenance, not feature work)

## Outcome

MediaVortex's bug tracker matches the claude-rails shape: `memory/KNOWN-ISSUES.md` (sectioned under `## Active` with at least one `### <area>` subsection + `## Resolved`) and `memory/BUG-INDEX.md` (terse one-line-per-bug index with `## Active` and `## Recently Resolved (last 10)`). All 57 cross-references across the repo point at the new path. Re-running `/migrate-bugs` is a no-op.

## Acceptance Criteria

1. `memory/KNOWN-ISSUES.md` exists; root `memory/KNOWN-ISSUES.md` does not. Verifiable: `Test-Path memory/KNOWN-ISSUES.md` true, `Test-Path memory/KNOWN-ISSUES.md` false.
2. `memory/KNOWN-ISSUES.md` has top-level `## Active` heading (exact text) and at least one `### <area>` subsection beneath it, plus a `## Resolved` heading. Verifiable: grep for `^## Active$`, `^### `, `^## Resolved$`.
3. `memory/BUG-INDEX.md` exists with `## Active` and `## Recently Resolved (last 10)` headings. Verifiable: grep.
4. Every numbered bug entry currently in memory/KNOWN-ISSUES.md is listed in BUG-INDEX.md with correct active/resolved classification per the entry's own header annotation (RESOLVED/FIXED -> resolved; others -> active). The 8 entries currently misfiled under `## Open` but marked RESOLVED/FIXED appear in INDEX as resolved. Verifiable: cross-check BUG-NNNN list.
5. All 57 files that reference `memory/KNOWN-ISSUES.md` are updated to reference `memory/KNOWN-ISSUES.md` (or the relative form appropriate to the referrer's location). Verifiable: `grep -r "memory/KNOWN-ISSUES.md"` returns only `memory/KNOWN-ISSUES.md` or `memory/KNOWN-ISSUES-ARCHIVE.md` matches.
6. Re-running `/migrate-bugs` after this directive closes reports `already compliant -- no changes`.

## Out of Scope

- Per-entry area subsection regrouping (entries stay under `### uncategorized` initially).
- ID minting for the ~30 unnumbered `### [BUG]` / `### [TECH DEBT]` entries (they remain unnumbered; not indexed since INDEX entries require an ID).
- Content-move of the 8 RESOLVED-but-misfiled entries within memory/KNOWN-ISSUES.md (INDEX classifies them correctly without the move).
- Adding `Repro:` / `Evidence:` / `First place to look:` lines to entries that lack them.

These belong in a follow-up directive (`migrate-bugs-compliance-deep`).

## Constraints

- `memory/KNOWN-ISSUES-ARCHIVE.md` is not touched.
- Cross-reference sweep is verbatim string replace `memory/KNOWN-ISSUES.md` -> `memory/KNOWN-ISSUES.md`. Files that already qualify the path are left alone.
- This is framework maintenance; no contract tests apply. Verification is `git status`, `grep`, and re-running `/migrate-bugs`.

## Escalation Defaults

- Risk tolerance: low (mostly mechanical text edits + one file move)

## Engineering Calls Already Made

- `## Open` rename -> `## Active` matches claude-rails shape.
- Single `### uncategorized` area subsection used as shape placeholder (defers per-entry area assignment without losing compliance).
- BUG-INDEX is the operationally-useful artifact and carries correct active/resolved classification even when memory/KNOWN-ISSUES.md body has not yet been physically reorganized.
- Sweep references in a single coordinated pass (per earlier operator answer).

## Status

Active -- phase: IMPLEMENTING.

### Files

```
memory/KNOWN-ISSUES.md      -- EDIT: rename heading, insert area subsection (moved from root via git mv, already staged)
memory/BUG-INDEX.md         -- CREATE: terse one-line-per-bug index
~57 files                   -- EDIT: verbatim sweep memory/KNOWN-ISSUES.md -> memory/KNOWN-ISSUES.md
```

### Promotions

| Source artifact | Target file | Commit |
|---|---|---|
| no promotions | n/a | framework maintenance, no code/contract changes |

### Verification

- **Criterion 1:** TBD at VERIFYING
- **Criterion 2:** TBD at VERIFYING
- **Criterion 3:** TBD at VERIFYING
- **Criterion 4:** TBD at VERIFYING
- **Criterion 5:** TBD at VERIFYING
- **Criterion 6:** TBD at VERIFYING

### Decisions Made

- TBD during execution
