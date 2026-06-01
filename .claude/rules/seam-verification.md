# Seam Verification

When you modify any component, every directional boundary that crosses into or out of it gets enumerated and verified. Seams hide silent compensations (type coercions, defensive defaults, workaround logic); changes that don't account for them re-introduce bugs the previous code was quietly masking.

## When this rule applies

Any change that:

- Modifies or replaces a function whose callers / callees you don't fully understand
- Changes a DB column's type, default, or write path
- Adds, removes, or restructures a JSON request / response shape
- Replaces or modifies a UI form that writes to an API
- Modifies a queue producer or consumer
- Crosses a process boundary (service <-> service, worker <-> DB notify)
- Deletes legacy code (which may have contained load-bearing seam compensation)

## Before IMPLEMENTING: enumerate

In the directive's `## Status` block (or task contract in task-delegation mode), list every seam the change crosses:

| Seam | Producer | Wire shape | Consumer expects | Verification |
|---|---|---|---|---|

Seam types: function-call, wire-format (JSON / SQL / file), state-store (DB row, file), UI (form -> API -> DB), process (queue rows, IPC).

**Persistent seam SOT lives in the flow doc.** Once a pipeline has a `*.flow.md` with a populated `## Seams` table (`.claude/rules/flow-docs.md`), that table is the durable source of truth for the cross-stage seams the pipeline carries. Directive-time enumeration becomes optional when every seam the directive crosses is already covered by an existing flow-doc row -- the directive's table then only enumerates SEAMS THE DIRECTIVE ADDS OR CHANGES, and existing seams are referenced by `<flow-slug>.S<N>` without restating. VERIFYING still records evidence per crossed seam regardless of where it is documented.

## At VERIFYING: round-trip

For each enumerated seam, record concrete evidence:

- **Function-call**: run the caller, verify args + return shape.
- **Wire-format**: send producer's output through the boundary, verify consumer parses correctly. For UI seams, CRUD round-trip on each type-distinct field (text, int, bool, bool-stored-as-int, select, float, NULL).
- **State-store**: write via producer, SELECT via consumer's code path, confirm value survives.
- **Process**: produce synthetic message, confirm consumer claims and processes.

If verification can't be expressed concretely, the seam isn't well enough understood to ship the change.

## Classifying code about to be deleted (four-bucket rubric)

| Bucket | What it looks like | Path forward |
|---|---|---|
| **Pure redundancy** | Restates something done elsewhere | Delete. |
| **Workaround for upstream/downstream quirk** | Type coercions, defensive defaults, error swallowing, retry logic | MOVE to a principled layer (schema migration, deserializer, KNOWN-ISSUES entry) BEFORE deletion. |
| **Defensive default for known-fragile input** | `value or 0`, guards against NULL on never-NULL column | Audit producer; fix it or document with KNOWN-ISSUES + one-line code anchor. |
| **Genuinely-dead orphan** | No callers, no side effects | Delete. |

If you can't tell which bucket, read the producer or consumer first.

## Where seams are documented

| Seam scope | Documentation home |
|---|---|
| Cross-stage pipeline seam | The relevant `*.flow.md`'s `## Seams` section |
| Intra-feature component seam | The relevant `*.feature.md`'s `## Seams` section |
| Wire-format coercion masking a schema quirk | `KNOWN-ISSUES.md` under a `BUG-NNNN`, OR permanent design section of the relevant `*.feature.md` |
| Function-call contract | Function signature + type hints; one-line docstring pointer if non-obvious |

**Details, examples (UseNvidiaHardware case), and caveats:** see `.claude/rules-details/seam-verification.md`.
