# Current Directive

**Set:** 2026-06-02
**Status:** Active -- phase: IMPLEMENTING -- operator-driven bug close-outs.
**Slug:** bug-remediation
**Replaces:** (none -- continuation of bug-tracker hygiene work)

## Outcome

Operator-flagged completed bugs are closed using the new `/bs` archive-on-resolve policy: prose moves from `memory/KNOWN-ISSUES.md` `## Active` directly to `memory/KNOWN-ISSUES-ARCHIVE.md`; `memory/BUG-INDEX.md` reflects the close in `## Recently Resolved (last 10)`. Active section in KNOWN-ISSUES.md stays lean.

## Acceptance Criteria

1. Each bug the operator names as completed is removed from `## Active` of `memory/KNOWN-ISSUES.md` and present in `memory/KNOWN-ISSUES-ARCHIVE.md` with a resolved-date marker on its header.
2. Each closed bug has its `BUG-NNNN` line moved from `## Active` to `## Recently Resolved (last 10)` in `memory/BUG-INDEX.md`, with `active` -> `resolved` and `-> <date>` appended.
3. If `## Recently Resolved` exceeds 10 lines, oldest fall off (prose already in archive).
4. No bug listed as `active` in BUG-INDEX has a header in KNOWN-ISSUES.md still tagged `RESOLVED` / `FIXED` / `HISTORICAL`.

## Out of Scope

- Investigating WHY any bug is closed -- operator authority; Claude does not re-litigate.
- Touching feature-doc criteria. /bs would normally do this; for bulk historical close-outs the criterion-link cleanup is deferred.

## Constraints

- Use `/bs`-style archive-on-resolve (prose directly to archive, not to `## Resolved` staging).
- BUG-0016's in-flight close (already started in current dirty tree) rolls into this directive's first commit.

## Engineering Calls Already Made

- Tracker shape compliance already done under `migrate-bugs-compliance` (closed). This directive is the recurring close-out work that policy enables.

## Status

Active -- phase: IMPLEMENTING.

### Files

```
memory/KNOWN-ISSUES.md             -- EDIT: cut closed-bug entries from ## Active
memory/KNOWN-ISSUES-ARCHIVE.md     -- EDIT: append cut entries with resolved-date marker
memory/BUG-INDEX.md                -- EDIT: move BUG-NNNN lines Active -> Recently Resolved
```

### Promotions

| Source artifact | Target file | Commit |
|---|---|---|
| no promotions | n/a | tracker hygiene, no contract/feature changes |

### Verification

- **Criterion 1:** TBD at VERIFYING
- **Criterion 2:** TBD at VERIFYING
- **Criterion 3:** TBD at VERIFYING
- **Criterion 4:** TBD at VERIFYING

### Decisions Made

- TBD during execution
