Reference template for feature doc shape. Copy as `<slug>.feature.md` next to the primary code file.

# Feature: [Name]

## What It Does
[1-2 sentences describing the feature from the operator's perspective.]

## Dependencies
<!--
Optional. Features that must be COMPLETE before this one can start.
For cross-repo contracts, prefix with the repo name (e.g., api:feature-name).
Delete this section if there are no dependencies.
-->
- [other-feature.feature.md -- what this feature needs from it]

## Workflows
<!--
THE LIST IS THE CONTRACT. Every operator-facing capability the feature offers
gets one row. A directive that retires a surface must edit the affected rows
or the regression review will catch the missing capability.

Required columns: ID, User action (what the operator perceives), Surface element
(the button/menu/route/CLI), Handler (HTTP/IPC/event entry point),
Backing class.method (grep-checkable code location).

Backing column MUST point at code that exists in the current tree. Each row
is verifiable by grep. If a row's backing has been deleted, the row is wrong
(either restore the capability or strike the row with a "dropped: <reason>"
annotation in the same commit that deleted the code).

Workflow IDs (W1, W2, ...) are stable -- when adding a row, take the next
unused number. Don't renumber existing rows; downstream test plans and
directive references depend on the IDs.
-->

| #  | User action | Surface element | Handler | Backing class.method |
|----|-------------|-----------------|---------|----------------------|
| W1 | [what the operator does] | [button/menu/CLI/route they touch] | [HTTP verb + path or event name] | [file:line of the entry function] |
| W2 | ... | ... | ... | ... |

## Success Criteria
<!--
Each criterion must be testable pass/fail from the outside. Consider:
- Does this feature have user-perceivable latency, frame rate, or load time?
  If so, include a performance criterion with a measurable threshold.
- Does this feature depend on an API contract? Include the verb + path +
  response shape as a criterion so both sides of the contract are testable.
- Each criterion passes the five litmus tests in `.claude/rules/feature-criteria.md`:
  rename / outsider / rewrite / negation / stability.
-->
1. [Testable pass/fail criterion.]
2. [Cover happy path, edge cases, error states.]
3. [Each criterion should survive being renamed, rewritten, or ported to another stack.]

## Seams
<!--
Required per `.claude/rules/feature-docs.md`. Enumerate every boundary that
crosses into or out of this feature: function-call seams to helpers/external
services, wire-format seams to DB/JSON/queue, UI seams to operator forms,
process seams to other workers/services.

Pipeline stage-transition seams belong in the corresponding flow doc, not here.

Wire shape MUST name the actual data shape, not the semantic intent.
`MediaFiles.Resolution TEXT, raw 'WIDTHxHEIGHT'` is wire shape;
"the file's dimensions" is semantic intent (belongs elsewhere).

Verification MUST point at something runnable: contract test, SQL audit query,
smoke script. "Tested manually" is not verification.
-->

| Seam | Producer | Wire shape | Consumer expects | Verification |
|------|----------|------------|------------------|--------------|
| [name] | [component/function] | [type/shape/format] | [component/function + assumption] | [test/contract] |

## Test Plan
<!--
Numbered table mapping criteria AND workflows to concrete test steps. Written
after criteria are approved, before implementation begins. Updated as criteria
evolve. Mark pass/fail during verification sessions.

Reference workflow IDs (W1, W2, ...) directly so the test plan stays mechanically
linked to the workflow inventory.
-->
| #  | Criterion / Workflow | Test                  | Expected            | Status |
|----|----------------------|-----------------------|---------------------|--------|
| 1  | [crit 1 summary]     | [specific action]     | [observable result] | [ ]    |
| W1 | [workflow 1 summary] | [operator action]     | [observable result] | [ ]    |

## Status
[NOT STARTED | IN PROGRESS | COMPLETE | PARKED]

### Progress
<!--
Chronological decision trail. Updated after each session. Serves three purposes:
1. Crash recovery -- next session picks up where this one left off.
2. Decision history -- records what was tried, what was rejected, and why.
3. Criteria / workflow evolution -- tracks when rows are added, amended, or dropped.

Verbs:
  - [x] / [ ]    Normal implementation step (include commit hash when done)
  - AMENDED #N   Criterion N was reworded. Quote the old text briefly.
  - ADD #N       New criterion added after initial approval.
  - ADD WN       New workflow added (and backing class.method named).
  - DROP WN      Workflow retired. Include reason. Code MUST be deleted in same commit.
  - REJECTED     Approach tried and abandoned. Reason is mandatory.
  - UPDATED      Cross-feature impact (e.g. updated another feature's criteria).

Delete completed items only after the feature is marked COMPLETE.
-->
- [ ] [First step or milestone]
- [ ] [Next step]

## Files
<!--
Key source files involved in this feature. Each file's role in one line.
The Workflows table's "Backing" column is the operator-action -> code map;
this section is the code-file -> role map. Both must agree.
-->
| File | Role |
|------|------|
| [path/to/file.py] | [one-line role description] |

## Scope
<!--
Optional. Glob patterns (one per line or comma-separated) that this feature
owns. The require-feature-doc hook uses this to allow edits to files that
match one of the listed patterns. Omit this section entirely to mean "the
whole marker-scoped directory." Do not use leading slashes. Examples:
  src/widget/**
  scripts/deploy.sh, tests/widget_test.py
-->
