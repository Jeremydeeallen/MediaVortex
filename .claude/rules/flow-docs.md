# Flow Docs

One pipeline per flow doc. Features reference flows, not the reverse. One tier of the doc-layering model (`.claude/rules/doc-layering.md`).

**Flow doc is the navigation hub for pipeline-shaped code.** Stable `ST<N>` stage IDs + a complete `## Seams` table make a flow doc indexable: a code anchor `# see <flow-slug>.ST<N>` lets a reader navigate via a partial Read of the named stage section instead of full Reads of every colocated `*.feature.md`. R1 (`.claude/standards/index.md`) accepts this anchored partial Read as a substitute for colocated feature-md preread. R18 enforces partial-read discipline on `*.feature.md` (limit<=50).

**Invariant -- one flow per pipeline shape.** Two `*.flow.md` files describing one conceptual operation is refused. Sub-flows are legitimate ONLY when both hold: (a) the nested pipeline has enough stage variance to warrant its own stage graph (e.g. audio normalization's Demucs pre-pass + Track 0 emit + Track 1 emit); (b) every parent-flow entry converges on it. Absent both, fold into the parent. Reason: divergent flow docs mask orchestration-level mode-branching (`.claude/rules/call-graph-audit.md` Signal 1). Enforcement: NEEDS_STANDARDS_REVIEW call-graph audit reviews every `*.flow.md` pair -- unify or explicitly name the carve-out.

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
