# Flow Docs

One pipeline per flow doc. Features reference flows, not the reverse.

## Verified conventions
- Flow docs are colocated `*.flow.md` next to the entry-point file they describe
- Each flow doc has an entry point, stage overview, and per-stage detail
- Feature docs reference flow docs for pipeline context; flow docs do not reference feature docs
- Flow docs describe what the system DOES, not what it SHOULD do (that belongs in feature docs)

## Common mistakes
- Putting multiple unrelated pipelines in one flow doc
- Flow docs that describe aspirational behavior instead of current behavior
- Feature docs that duplicate flow doc content instead of referencing it
- Flow docs that reference feature doc criteria (creates circular dependency)
