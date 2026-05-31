# Feature Docs

Every feature has one feature doc that owns its contract. Feature docs are colocated `*.feature.md` next to the primary code.

## Verified conventions

- Feature docs are colocated `*.feature.md` next to the primary code they describe.
- Each feature doc has `## What It Does` (or `## Outcome`), `## Workflows`, `## Success Criteria`, `## Seams`, `## Status`, `## Files`, `## Scope`.
- Feature docs describe what the feature DOES and the contracts it guarantees -- not the pipeline (that's flow docs) and not aspirational behavior (that belongs in a directive).
- Feature criteria follow `.claude/rules/feature-criteria.md` (the five litmus tests: rename / outsider / rewrite / negation / stability).

## Required: `## Workflows` section per feature

Every feature doc has a `## Workflows` section enumerating every operator-facing capability the feature offers. The table is the contract -- a directive that retires a surface must edit the affected rows in the same commit that deletes the code, or regression review will catch the missing capability.

| #  | User action | Surface element | Handler | Backing class.method |
|----|-------------|-----------------|---------|----------------------|
| W1 | `<what the operator perceives>` | `<button/menu/CLI/route>` | `<HTTP verb + path or event name>` | `<file:line of entry function>` |

Backing column MUST point at code that exists in the current tree. Each row is grep-checkable. A row whose backing function has been deleted is wrong -- either restore the capability OR strike the row with a `dropped: <reason>` annotation in the same commit.

Workflow IDs (W1, W2, ...) are stable and never renumbered -- downstream test plans and directive references depend on them.

The Workflows table replaces ad-hoc "capability preservation" checklists. When refactoring or replacing a surface, reading the table is the safety net: every row is a capability that must continue to exist somewhere.

## Required: `## Seams` section per feature

Every feature doc has a `## Seams` section enumerating the boundaries that cross into or out of the feature's surface -- function-call seams to helpers / external services, wire-format seams to the DB / JSON / queue, UI seams to operator forms, process seams to other workers or services.

| Seam | Producer | Wire shape | Consumer expects | Verification |
|---|---|---|---|---|
| `<name>` | `<component / function>` | `<type / shape / format>` | `<component / function + assumption>` | `<test / contract>` |

The pipeline-stage-transition seams live in the corresponding flow doc per `.claude/rules/flow-docs.md`; the feature doc's section is for intra-feature and feature-to-external-component seams.

Wire shape must name the actual data shape, not the semantic intent. Verification must point at something runnable (contract test, SQL query, smoke script).

## Common mistakes

- Feature doc has no `## Seams` section -- every wire-format boundary becomes tribal knowledge until something breaks.
- `## Seams` lists what the feature DOES instead of what crosses its boundaries (that's `## What It Does`, a separate section).
- Wire shape is described semantically ("the file's quality score") instead of structurally (`TranscodeAttempts.VMAF DOUBLE PRECISION, NULL when not yet measured`).
- Verification column is empty or says "tested manually" -- without a runnable reference, the contract drifts silently.
- Feature doc duplicates content from flow docs instead of referencing them (creates two sources of truth that drift).
- Feature doc has no `## Workflows` section, or the table is missing the Backing column -- every operator capability becomes invisible to code review, and refactors silently drop features (the failure mode this section was created to prevent).
- A directive deletes a handler but doesn't update the corresponding Workflows row -- the row now points at code that doesn't exist. Grep on the backing column catches this; CI can be made to enforce it.
