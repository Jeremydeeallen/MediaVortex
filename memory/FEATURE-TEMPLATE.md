Reference template for feature doc shape. Copy as `<name>.feature.md` next to the primary code file.

# Feature: [Name]

## What It Does
[1-2 sentences describing the feature from the user's perspective.]

## Dependencies
<!--
Optional. Features that must be COMPLETE before this one can start.
For cross-repo contracts, prefix with the repo name (e.g., api:feature-name).
Delete this section if there are no dependencies.
-->
- [other-feature.feature.md -- what this feature needs from it]

## Success Criteria
<!--
Each criterion must be testable pass/fail from the outside. Consider:
- Does this feature have user-perceivable latency, frame rate, or load time?
  If so, include a performance criterion with a measurable threshold.
- Does this feature depend on an API contract? Include the verb + path +
  response shape as a criterion so both sides of the contract are testable.
-->
1. [Testable pass/fail criterion.]
2. [Cover happy path, edge cases, error states.]
3. [Each criterion should survive being renamed, rewritten, or ported to another stack.]

## Test Plan
<!--
Numbered table mapping criteria to concrete test steps. Written after
criteria are approved, before implementation begins. Updated as criteria
evolve. Mark pass/fail during verification sessions.
-->
| # | Criterion | Test | Expected | Status |
|---|-----------|------|----------|--------|
| 1 | [summary] | [specific user action] | [observable result] | [ ] |

## Status
[NOT STARTED | IN PROGRESS | COMPLETE | PARKED]

### Progress
<!--
Chronological decision trail. Updated after each session. Serves three purposes:
1. Crash recovery -- next session picks up where this one left off.
2. Decision history -- records what was tried, what was rejected, and why.
3. Criteria evolution -- tracks when criteria are added, amended, or clarified.

Verbs:
  - [x] / [ ]    Normal implementation step (include commit hash when done)
  - AMENDED #N   Criterion N was reworded. Quote the old text briefly.
  - ADD #N        New criterion added after initial approval.
  - REJECTED      Approach tried and abandoned. Reason is mandatory.
  - UPDATED       Cross-feature impact (e.g. updated another feature's criteria).

Delete completed items only after the feature is marked COMPLETE.
-->
- [ ] [First step or milestone]
- [ ] [Next step]

## Files
- [Key source files involved in this feature.]

## Scope
<!--
Optional. Glob patterns (one per line or comma-separated) that this feature owns.
The require-feature-doc hook uses this to allow edits to files that match one of
the listed patterns. Omit this section entirely to mean "the whole marker-scoped
directory." Do not use leading slashes. Examples:
  src/widget/**
  scripts/deploy.sh, tests/widget_test.py
-->
