# Flow Docs

One pipeline per flow doc. Features reference flows, not the reverse. One tier of the doc-layering model (`.claude/rules/doc-layering.md`).

## Required structure

Every `*.flow.md` has:

- `**Slug:** <slug>` directly under the title -- top-level addressing primitive (R16 enforced). Slug = lowercase filename without `.flow.md` extension.
- Entry point and stage overview
- Per-stage detail with stable IDs (`ST1, ST2, ...`)
- `## Seams` table with stable IDs (`S1, S2, ...`); cross-stage seams (data crossing each stage transition)

Flow docs describe what the system DOES, not what it SHOULD do (that belongs in feature docs or directives). Flow docs do NOT reference feature doc criteria -- that creates circular dependency.

## Required IDs

| Prefix | What it identifies | Example |
|---|---|---|
| `ST1, ST2, ...` | Pipeline stages | `ST3 Probe metadata` |
| `S1, S2, ...` | Cross-stage seams (transitions) | `S2 ST3 -> ST4: MediaFiles.Resolution NOT NULL` |

Code anchors: `# see <slug>.<ID>` (e.g. `# see transcode.ST5`). Enables R1 partial-read awareness.

## Seams table shape

| ID | Transition | Producer (writer) | Wire shape | Consumer (reader) expects | Verification |
|---|---|---|---|---|---|
| S1 | `ST1 -> ST2` | `<code path / DB row written>` | `<row schema + nullability + semantic meaning>` | `<code path / DB read query>` | `<test / contract>` |

Wire shape must name the actual data shape, not semantic intent. Verification must point at something runnable (contract test, SQL audit query, smoke-test script).

**Details, common mistakes, examples:** see `.claude/rules-details/flow-docs.md`.
