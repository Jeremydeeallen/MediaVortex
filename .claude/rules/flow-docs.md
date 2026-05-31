# Flow Docs

One pipeline per flow doc. Features reference flows, not the reverse.

## Verified conventions
- Flow docs are colocated `*.flow.md` next to the entry-point file they describe
- Each flow doc has an entry point, stage overview, and per-stage detail
- Feature docs reference flow docs for pipeline context; flow docs do not reference feature docs
- Flow docs describe what the system DOES, not what it SHOULD do (that belongs in feature docs)

## Required: `## Seams` section per flow

Every flow doc has a `## Seams` section that enumerates the data crossing each stage transition. For a flow with stages A -> B -> C, the section lists:

| Transition | Producer (writer) | Wire shape | Consumer (reader) expects | Verification |
|---|---|---|---|---|
| A -> B | `<code path / DB row written>` | `<row schema + nullability + semantic meaning>` | `<code path / DB read query>` | `<test / contract that catches drift>` |
| B -> C | ... | ... | ... | ... |

Why: when someone modifies stage B's output, the flow doc tells them what stage C expects -- they can't accidentally break the downstream consumer without seeing the contract first. This is the pipeline-granularity application of `.claude/rules/seam-verification.md`; intra-feature seams live in `*.feature.md` `## Seams` sections instead.

Seam attributes per row:

- **Wire shape** must name the actual data shape, not the semantic intent. `Workers.NvencCapable BOOLEAN, NULL means false` is a wire shape; "the worker can do NVENC" is the semantic intent (belongs in the description). The seam-verification rule fails most often on wire-shape mismatches, so be explicit.
- **Verification** must point at something runnable: a contract test, a SQL audit query, a smoke-test script. "Eyeball the row" is not verification.

## Common mistakes
- Putting multiple unrelated pipelines in one flow doc
- Flow docs that describe aspirational behavior instead of current behavior
- Feature docs that duplicate flow doc content instead of referencing it
- Flow docs that reference feature doc criteria (creates circular dependency)
