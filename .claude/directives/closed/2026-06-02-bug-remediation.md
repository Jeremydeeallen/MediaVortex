# Current Directive

**Set:** 2026-06-02
**Closed:** 2026-06-02 -- Success
**Status:** Closed -- Success
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

- **Criterion 1:** 7 closures verified -- BUG-0016 (86a26e0), BUG-0011 (07d5705), BUG-0004 (3a441c6), BUG-0009/0010/0015/0018 (eb88841 rolled into BUG-0020), BUG-0003/0005/0006/0012 (this commit). All have entries in KNOWN-ISSUES-ARCHIVE.md with RESOLVED date markers.
- **Criterion 2:** BUG-INDEX.md `## Recently Resolved (last 10)` reflects all closures with `resolved` status and `-> <date>` appended.
- **Criterion 3:** Cap maintained at 10; older closures (BUG-0001/0008/0013/0014/0017) trimmed off as newer arrivals pushed past the limit. Their prose remains in archive.
- **Criterion 4:** `Select-String -Path memory/KNOWN-ISSUES.md -Pattern 'RESOLVED|FIXED|HISTORICAL'` returns only `MOSTLY RESOLVED` (BUG-0016 superseded mid-session, still applicable to the umbrella close) and `PARTIALLY RESOLVED` TECH DEBT (Phase 2b still active). No active-status bug has a closed-tagged header.

### Decisions Made

- BUG-0009/0010/0015/0018 closed as `ROLLED INTO BUG-0020` rather than independently fixed; the bugs themselves explicitly named this consolidation path. BUG-0020 verification will subsume them.
- BUG-0003 was tagged "PENDING OPERATOR VERIFICATION" in original entry; closed on operator confirmation that no follow-up has been needed and the audio-completion model is live.
- Per-entry feature-doc tag stripping done inline (criterion text preserved, just `[BUG-NNNN]` removed) -- avoids the criterion-link cleanup deferred in the prior migrate-bugs-compliance directive.
