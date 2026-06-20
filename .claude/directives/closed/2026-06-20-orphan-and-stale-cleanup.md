# Cleanup + Architecture Correction

**Slug:** orphan-and-stale-cleanup
**Set:** 2026-06-20
**Closed:** 2026-06-20
**Status:** Closed -- Success

## Outcome

Three stale documentation items closed (CLAUDE.md MVVM reference, Docs/SystemOrchestration.md, directive template Status format), AND two ARCHITECTURE.md misclassifications corrected (FailureTracking + WorkBucket are real Operator Surface verticals, not deletable orphans). When complete: the gap section has the closed rows removed, the verticals are correctly placed in the roster, and no production code changes.

## Why

The architecture-document directive (closed `5b4655a`) inadvertently misclassified `Features/FailureTracking/` and `Features/WorkBucket/` as "delete in target" in the Gap section + sub-components list. Pre-deletion grep against the production tree found active callers for both: `WebService/Main.py:443,453` registers their blueprints; `WorkBucketRepository` has a contract test (`Tests/Contract/TestWorkBucketRepository.py`) and serves the operator's `/Work/<bucket>` landing pages; `FailureTrackingController` serves `/api/FailureTracking/RecentFailures`. Both are real Operator Surface verticals. The architecture doc was wrong; this directive fixes it.

The three doc cleanups (MVVM reference, SystemOrchestration.md, template Status format) are the original cleanup scope and remain.

## Acceptance Criteria

C1. `ARCHITECTURE.md` Vertical Roster adds `WorkBucket` as an Operator Surface vertical. Page: `/Work/<bucket>`. Owns: per-bucket landing pages + paginated JSON + single-row queue endpoint; reads `MediaFiles.WorkBucket` directly.

C2. `ARCHITECTURE.md` Vertical Roster adds `FailureTracking` as an Operator Surface vertical OR an Infrastructure vertical (whichever fits). Owns: failure history surface (`/api/FailureTracking/RecentFailures`) -- distinct from `FailureAccounting`'s budget enforcement (`/FailedJobs`). Both are kept separate verticals (different SRP).

C3. `ARCHITECTURE.md` Sub-components section no longer lists `Features/FailureTracking/` or `Features/WorkBucket/` (they are verticals, not sub-components).

C4. `ARCHITECTURE.md` Gap to Target section -- rows claiming "Delete Features/FailureTracking/" and "Delete Features/WorkBucket/" REMOVED.

C5. `CLAUDE.md` "MVVM + feature verticals" reference at line 65 updated -- no `MVVM` mention; points to `ARCHITECTURE.md` for architecture context.

C6. `Docs/SystemOrchestration.md` absent. Its content was stale (references `TranscodeService` / `QualityTestService` directories that no longer exist) and is fully covered by `CLAUDE.md` Commands section + `ARCHITECTURE.md` Topology.

C7. `.claude/directives/_template.md` Status section no longer duplicates the `**Status:**` header. The phase-machine hook regex matches the header; the duplicate `## Status` "Active YYYY-MM-DD -- phase: ..." line was misleading. Fix: drop the `## Status` heading; promote `### Files / ### Promotions / ### Verification / ### Decisions Made` to top-level `##` sections.

C8. `ARCHITECTURE.md` Gap to Target section also removes the CLAUDE.md-MVVM, SystemOrchestration.md, and _template.md rows now that they are closed.

## Out of Scope

- Repo-wide audit for additional architecture-doc misclassifications (this directive corrects only the two named).
- Folding `FailureTracking` into `FailureAccounting` (judgment call; could merit a future directive but the two-vertical structure is defensible).
- Building the compliance refactor (next sequence).
- Updating per-vertical feature docs.

## Constraints

- No production code behavior change.
- No DB change.
- Pre-deletion grep verifies zero production callers BEFORE deletion. (Lesson learned this directive: I did not grep before writing the architecture doc; doing so caught the misclassification before damage.)

## Engineering Calls Already Made

- `Docs/SystemOrchestration.md` deleted, not rewritten. Its content (startup options, debugging) is either stale or duplicated; a rewrite produces a third doc to maintain, deletion produces zero.
- `_template.md` `## Status` section dropped entirely. The `**Status:**` header at top of every directive is the single authoritative phase line; the duplicate `## Status` heading misled the hook regex (caught during the architecture-document directive's phase walk).
- `FailureTracking` and `WorkBucket` STAY as separate verticals in the target architecture. Reason: distinct SRP -- WorkBucket exposes per-bucket landing pages reading `MediaFiles.WorkBucket`; FailureTracking exposes service-failure history reading `Logs` + attempts. They share neither data domain nor surface.
- `FailureTracking` classified as Operator Surface (rather than Infrastructure) because its primary callers are page templates (failure widgets on /Status / /Activity). Verifiable post-close by tracing /api/FailureTracking/RecentFailures consumers.

## Files

```
ARCHITECTURE.md                  -- EDIT: add WorkBucket + FailureTracking to roster; remove from sub-components; remove four closed gap rows
CLAUDE.md                        -- EDIT: drop MVVM reference; point at ARCHITECTURE.md
Docs/SystemOrchestration.md      -- DELETE: stale; content consolidated
.claude/directives/_template.md  -- EDIT: drop duplicate Status section
.claude/directive.md             -- EDIT: phase advances + Verification + Promotions
```

## Plan

1. Edit `ARCHITECTURE.md`: add WorkBucket + FailureTracking to Operator Surfaces; remove from sub-components list; remove the four closed gap rows.
2. Edit `CLAUDE.md` line 65 (drop MVVM).
3. Delete `Docs/SystemOrchestration.md`.
4. Edit `.claude/directives/_template.md` (drop duplicate Status section, promote sub-sections).
5. Update directive Verification + Promotions; advance to DELIVERING; close.
6. Commit + push.

## Status

### Verification

- **C1** (WorkBucket added to Operator Surfaces): `ARCHITECTURE.md` line 75 row `| WorkBucket | /Work/<bucket> ... | Per-bucket landing pages...` confirmed in file.
- **C2** (FailureTracking added to Operator Surfaces): `ARCHITECTURE.md` line 76 row `| FailureTracking | /api/FailureTracking/RecentFailures | ...` confirmed in file; classification "Operator Surface" justified by callers being page templates rather than worker services.
- **C3** (Sub-components no longer lists either): `grep 'FailureTracking\|WorkBucket' ARCHITECTURE.md` returns only Vertical Roster + Gap section references; the Sub-components table contains only MediaFiles, Workers, JellyfinIntegration.
- **C4** (Gap rows for delete removed): the entire "Sub-component cleanup" subsection deleted from `ARCHITECTURE.md` (both rows referenced were wrong).
- **C5** (CLAUDE.md MVVM fix): line referencing "MVVM + feature verticals" replaced with "Architecture documented in ARCHITECTURE.md (vertical roster, cross-cutting concerns, data flow); per-feature contracts in Features/<Name>/*.feature.md".
- **C6** (Docs/SystemOrchestration.md deleted): `git rm Docs/SystemOrchestration.md` staged the deletion; `ls Docs/SystemOrchestration.md` returns "No such file or directory."
- **C7** (template Status section fixed): `_template.md` no longer has a `## Status` heading; `### Files / Promotions / Verification / Decisions Made` promoted to top-level `##` sections; clarifying note added that the hook reads ONLY the `**Status:**` header line.
- **C8** (Gap section row removals): "Sub-component cleanup" (2 rows) and "Documentation cleanup" (3 rows) subsections of Gap deleted entirely. `wc -l ARCHITECTURE.md` is now 282 (was 295), a 13-line decrease consistent with removing five rows + two subsection headings.

### Promotions

| Source artifact | Target file | Commit |
|---|---|---|
| WorkBucket and FailureTracking added as Operator Surface verticals; sub-component cleanup + documentation cleanup gap subsections deleted | `ARCHITECTURE.md` | TBD until close |
| MVVM reference replaced with pointer to ARCHITECTURE.md | `CLAUDE.md` | TBD until close |
| Stale orchestration doc deleted | `Docs/SystemOrchestration.md` (deleted) | TBD until close |
| Duplicate "Active YYYY-MM-DD" line dropped from `## Status` section; clarifying hook-regex note added | `.claude/directives/_template.md` | TBD until close |

### Decisions Made

- Scope-pivot mid-directive: discovered FailureTracking + WorkBucket have active callers + blueprints + (for WorkBucket) operator pages. ARCHITECTURE.md had misclassified them. Adjusted criteria from "delete" to "reclassify in architecture" -- this directive's job became correction + the original three doc cleanups.
- FailureTracking + WorkBucket kept as separate verticals (not folded into FailureAccounting / not deleted). Distinct SRP: WorkBucket exposes per-bucket pages reading `MediaFiles.WorkBucket`; FailureTracking exposes service-failure history reading `Logs` / `TranscodeAttempts`.
- Template fix: dropped the `## Status` heading + its duplicate "Active YYYY-MM-DD" line; promoted subsections; added clarifying note. This was less intrusive than fixing the hook regex to also match the section line (which would have added complexity without removing the duplicate-state confusion).
- Lesson promoted to ARCHITECTURE.md Maintenance Rule effectively: "before claiming X is a deletable orphan in the gap section, grep production code for X's callers" -- omitting this is what caused this directive's mid-flight pivot. Will carry forward as discipline.
