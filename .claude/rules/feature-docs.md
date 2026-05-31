# Feature Docs

Every feature has one feature doc that owns its contract. Feature docs are colocated `*.feature.md` next to the primary code.

## Verified conventions

- Feature docs are colocated `*.feature.md` next to the primary code they describe.
- Each feature doc has `## Outcome` (or `## What It Does`), `## Success Criteria`, `## Status`, `## Scope`, `## Files`.
- Feature docs describe what the feature DOES and the contracts it guarantees -- not the pipeline (that's flow docs) and not aspirational behavior (that belongs in a directive).
- Feature criteria follow `.claude/rules/feature-criteria.md` (the five litmus tests: rename / outsider / rewrite / negation / stability).

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
