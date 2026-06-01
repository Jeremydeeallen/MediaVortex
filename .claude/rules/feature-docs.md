# Feature Docs

Every feature has one feature doc that owns its contract. Feature docs are colocated `*.feature.md` next to the primary code. One tier of the doc-layering model (`.claude/rules/doc-layering.md`).

## Required structure

Every `*.feature.md` has:

- `**Slug:** <slug>` directly under the title -- top-level addressing primitive (R16 enforced). Slug = lowercase filename without `.feature.md` extension.
- `## What It Does` (or `## Outcome`) -- one paragraph
- `## Workflows` -- table with stable IDs (`W1, W2, ...`); see Required IDs below
- `## Success Criteria` -- numbered with stable IDs (`C1, C2, ...`)
- `## Seams` -- table with stable IDs (`S1, S2, ...`); intra-feature seams only (cross-stage seams go in flow docs)
- `## Status` -- current state + Files block

Criteria pass the five litmus tests (`.claude/rules/feature-criteria.md`): rename / outsider / rewrite / negation / stability.

## Required IDs (stable, never renumbered)

| Prefix | What it identifies | Example | Reason for stability |
|---|---|---|---|
| `W1, W2, ...` | Operator-facing workflows | `W3 Replace transcoded file` | Test plans + directive references depend on it |
| `S1, S2, ...` | Intra-feature seams | `S2 CommandBuilder -> ffmpeg argv` | Code can carry `# see <slug>.S2` anchors |
| `C1, C2, ...` | Success criteria | `C5 VMAF >= 80 blocks re-queue` | Closed directives cite them by ID |

Code anchors: `# see <slug>.<ID>` (e.g. `# see transcode-queue.S2`). Enables R1 partial-read awareness -- a Read of just the anchor's section satisfies the doc-preread requirement.

## Workflows table shape

| #  | User action | Surface element | Handler | Backing class.method |
|----|-------------|-----------------|---------|----------------------|
| W1 | `<what the operator perceives>` | `<button/menu/CLI/route>` | `<HTTP verb + path or event name>` | `<file:line of entry function>` |

Backing column MUST point at code that exists in the current tree. A row whose backing function has been deleted is wrong -- restore the capability OR strike the row with `dropped: <reason>` in the same commit.

## Seams table shape

| ID | Seam | Producer | Wire shape | Consumer expects | Verification |
|---|---|---|---|---|---|
| S1 | `<name>` | `<component / function>` | `<type / shape / format>` | `<component / function + assumption>` | `<test / contract>` |

Wire shape must name the actual data shape (not semantic intent). Verification must point at something runnable.

**Details, common mistakes, examples:** see `.claude/rules-details/feature-docs.md`.
