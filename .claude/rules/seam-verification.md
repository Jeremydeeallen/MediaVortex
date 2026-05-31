# Seam Verification

When you modify any component, every directional boundary that crosses into or out of it gets enumerated and verified. Seams hide silent compensations (type coercions, defensive defaults, workaround logic); changes that don't account for them re-introduce bugs the previous code was quietly masking.

## Contents

- [When this rule applies](#when-this-rule-applies)
- [Before IMPLEMENTING: enumerate the seams](#before-implementing-enumerate-the-seams)
- [At VERIFYING: round-trip each seam](#at-verifying-round-trip-each-seam)
- [Classifying code about to be deleted](#classifying-code-about-to-be-deleted)
- [Where seams are documented](#where-seams-are-documented)
- [Why this rule exists](#why-this-rule-exists)
- [Honest caveats](#honest-caveats)

## When this rule applies

Any change that:

- Modifies or replaces a function whose callers / callees you don't fully understand
- Changes a DB column's type, default, or write path
- Adds, removes, or restructures a JSON request / response shape
- Replaces or modifies a UI form that writes to an API
- Modifies a queue producer or consumer
- Crosses a process boundary (service <-> service, worker <-> DB notify)
- Deletes legacy code (which may have contained load-bearing seam compensation)

## Before IMPLEMENTING: enumerate the seams

In the directive doc's `## Status` block (or the task contract in task-delegation mode), list every seam the change crosses:

| Seam | Producer | Wire shape | Consumer expects | Verification |
|---|---|---|---|---|
| `<name>` | `<component / code path>` | `<type / shape / format>` | `<component / code path + assumption>` | `<how it will be verified post-change>` |

Seam types to look for:

- **Function-call seam**: caller <-> callee. Wire shape = function signature + return type.
- **Wire-format seam**: serialization boundary (JSON, SQL params, query strings, file format). Wire shape = both ends' type expectations. This is where the `UseNvidiaHardware` bug lived -- a JS bool became a PostgreSQL bigint via an undocumented JS ternary.
- **State-store seam**: row / file written by one component, read by another. Wire shape = column types + nullability + semantic meaning.
- **UI seam**: operator action -> form -> API -> DB. Wire shape = form field types <-> JSON <-> API allowlist <-> DB column type.
- **Process seam**: producer writes / consumer claims (queue rows, notify endpoints, IPC). Wire shape = row schema + state machine.

## At VERIFYING: round-trip each seam

For each enumerated seam, the verification step records concrete evidence in the directive doc:

- **Function-call seam**: run the caller, verify the callee receives expected args and returns the expected shape.
- **Wire-format seam**: send the producer's output through the boundary, verify the consumer parses it correctly. For UI seams, run an operator-mediated CRUD round-trip on each type-distinct field: text, int, bool, bool-stored-as-int, select, float, NULL.
- **State-store seam**: write via the producer, SELECT via the consumer's code path, confirm the value survives.
- **Process seam**: produce a synthetic message, confirm the consumer claims and processes it.

If a seam's verification cannot be expressed concretely, the seam isn't well enough understood to ship the change.

## Classifying code about to be deleted

Before deleting any code (function, JS block, SQL fragment, helper class), classify each block per the four-bucket rubric. Mirrors `ceo-mode.md#handling-preexisting-comment--doc-violations-encountered-mid-directive` -- same discipline, applied to code instead of comments.

| Bucket | What it looks like | Path forward |
|---|---|---|
| **Pure redundancy** | Restates or trivially wraps something already done elsewhere | Delete. |
| **Workaround for an upstream/downstream quirk** | Type coercions (`? 1 : 0`, `int(x)`), defensive defaults (`x or 0`), error swallowing, retry logic | MOVE the responsibility to a principled layer (schema migration, API-layer JSON deserializer, KNOWN-ISSUES entry) BEFORE deletion. Never silently drop a workaround -- the quirk it masked resurfaces. |
| **Defensive default for a known-fragile input** | `value or 0`, `value if value else ''`, guards against NULL on a column that should never be NULL | Audit what produces the fragility, then move (fix the producer) or document (KNOWN-ISSUES + single-line code anchor). |
| **Genuinely-dead orphan** | No callers, no side effects, no compensation | Delete. |

If you can't tell which bucket a line is in, you don't yet understand the seam well enough to delete it -- read the producer or consumer first.

## Where seams are documented

Seams have permanent homes -- never leave them as tribal knowledge:

| Seam scope | Documentation home |
|---|---|
| Cross-stage pipeline seam | The relevant `*.flow.md`'s `## Seams` section (see `.claude/rules/flow-docs.md`) |
| Intra-feature component seam | The relevant `*.feature.md`'s `## Seams` section |
| Wire-format coercion that masks a schema quirk | `KNOWN-ISSUES.md` under a `BUG-NNNN`, OR a permanent design-decision section of the relevant `*.feature.md` |
| Function-call contract | Function signature + type hints; one-line docstring pointer to the doc home if non-obvious |

## Why this rule exists

The `UseNvidiaHardware` bug (BUG-0023, 2026-05-31) is the canonical example. A JS-side ternary `? 1 : 0` had been silently coercing a JS boolean to a SQL integer for years, masking a schema mismatch (the `Profiles.UseNvidiaHardware` column is `bigint`, not `BOOLEAN`). When the `unify-profile-editor` directive deleted the legacy modal, the ternary went with it; the new modal sent raw booleans; PostgreSQL rejected. The bug existed because no one had enumerated the JS<->SQL wire-format seam and noticed the ternary was load-bearing -- not orphan code.

A seam-verification pass would have caught it before delivery: the UI seam's CRUD round-trip on a `bool`-typed field would have hit the type mismatch immediately. Instead it shipped, the operator hit the 500 error, and the bug was filed retroactively.

## Honest caveats

- Seam enumeration adds time before IMPLEMENTING. That's the trade. The alternative is re-discovering silent bugs after a directive closes.
- The hook cannot mechanize "did you enumerate every seam?" -- this is a judgment-call discipline. Operator review at directive close surfaces gaps.
- The discipline applies to both CEO mode and task-delegation mode. It is about how you make any change, not about how directives are structured.
