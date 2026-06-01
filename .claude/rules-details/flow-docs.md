# Flow Docs -- Details

> Invariant: `.claude/rules/flow-docs.md`.

## Why the cross-stage Seams section exists

When someone modifies stage B's output, the flow doc tells them what stage C expects -- they can't accidentally break the downstream consumer without seeing the contract first. This is the pipeline-granularity application of `.claude/rules/seam-verification.md`; intra-feature seams live in `*.feature.md` `## Seams` sections instead.

The seam-verification rule fails most often on wire-shape mismatches -- be explicit. `Workers.NvencCapable BOOLEAN, NULL means false` is a wire shape; "the worker can do NVENC" is the semantic intent (belongs in the description, not the wire shape column).

## Stage IDs operational notes

- `ST1, ST2, ...` are positional but anchored. Once assigned, a stage keeps its ID even if the pipeline is reordered (rare). If reordering happens, document the ID-to-position mapping at the top of the doc.
- New stage inserted between ST3 and ST4: gets `ST5` (or higher unused), not `ST3.5`. Sequence order is in the doc's stage-overview narrative, not in the ID.
- Deletion: ID is retired permanently. The next added stage takes the next unused number.

## Where flow docs belong vs feature docs

| Content | Home | Why |
|---|---|---|
| "Stage A produces a row of shape X; stage B reads it" | Flow doc Seams | Cross-stage contract |
| "Inside stage A, helper X is called with arguments Y" | Feature doc Seams | Intra-feature contract |
| "The pipeline has 7 stages: ST1...ST7" | Flow doc body | Pipeline structure |
| "The TranscodeQueue feature has these operator workflows" | Feature doc Workflows | Operator-visible capabilities |
| "Why we decided to use polling instead of notify" | Closed directive Decisions | About the ask, not the contract |

## Common mistakes

- Putting multiple unrelated pipelines in one flow doc -- one pipeline per flow doc; split if scope grows.
- Flow docs that describe aspirational behavior instead of current behavior -- aspirations belong in directives.
- Feature docs that duplicate flow doc content instead of referencing it -- creates two sources of truth that drift.
- Flow docs that reference feature doc criteria -- creates circular dependency. Flow doc references the feature by name + slug, not by criterion.
- ST IDs renumbered after a deletion -- breaks anchors in code and references in closed directives.
- Seam wire-shape described semantically instead of structurally -- the whole point of the Seams table is structural precision.
