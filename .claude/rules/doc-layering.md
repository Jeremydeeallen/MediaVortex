# Doc Layering

Three documentation tiers. Non-overlapping roles. Each tier owns a distinct kind of content and a distinct lifetime. Lower rule docs (`ceo-mode.md`, `feature-docs.md`, `flow-docs.md`) reference this one instead of re-deriving the boundaries.

## The three tiers

| Tier | File | Lifetime | Owns | Seam scope |
|---|---|---|---|---|
| Directive | `.claude/directive.md` (active) -> `.claude/directives/closed/YYYY-MM-DD-<slug>.md` (archived) | Transient -- opens, runs, archives | The current CEO ask: outcome, acceptance criteria, plan, in-flight state, verification evidence, engineering decisions | Enumerated in the Status block before IMPLEMENTING (per `.claude/rules/seam-verification.md`); promoted to feature/flow docs at DELIVERING |
| Feature | `*.feature.md` colocated with primary code | Durable -- one per vertical, lives as long as the vertical does | What a vertical DOES + its operator-visible Workflows + its intra-feature seams | Intra-feature (function-call, helper, vertical-to-external-service) -- per `.claude/rules/feature-docs.md` |
| Flow | `*.flow.md` colocated with pipeline entry point | Durable -- one per pipeline, lives as long as the pipeline does | What the pipeline DOES + stage-by-stage detail + cross-stage seams | Cross-stage (the data crossing each stage transition in the pipeline) -- per `.claude/rules/flow-docs.md` |

The three tiers do not overlap. A piece of content lives in exactly one tier at any time:

- "We are about to do X" -> directive (transient ask)
- "This vertical does X, and you call it via these workflows, and these are its seams" -> feature doc (durable contract)
- "This pipeline runs stages A -> B -> C, and these are the wire-shape contracts between them" -> flow doc (durable contract)

## Why three tiers

The split exists because the content has three different lifetimes:

- **Directives** are short-lived. They open with an ask, close with a delivery, and archive. Re-reading old directives tells you WHY code was changed at a point in time.
- **Feature docs** are long-lived. The vertical they describe persists across many directives. Re-reading a feature doc tells you WHAT a vertical does today.
- **Flow docs** are long-lived but shaped differently. They describe the pipeline -- the rails the verticals plug into. Re-reading a flow doc tells you HOW data crosses the system today.

Without the layering, content collapses into whichever tier is most convenient at the moment -- typically the directive (because it's open and being edited) -- and the durable contracts decay. The "documentation lives only in the directive doc" rule from `ceo-mode.md` is correct DURING a directive; the missing half is what happens at the close, and that's what the Promotions section in the directive template enforces.

## Lifecycle: directive -> features/flows (promotion)

During a directive, design content accretes in the directive doc. At DELIVERING, durable content is PROMOTED to its permanent home:

| Source content in directive | Target home | Rationale |
|---|---|---|
| Seam enumeration that named cross-stage contracts | The relevant `*.flow.md`'s `## Seams` section | Cross-stage seams are flow-scope; flow doc is the durable home |
| Seam enumeration that named intra-feature contracts | The relevant `*.feature.md`'s `## Seams` section | Intra-feature seams are feature-scope |
| New operator-facing capability | The relevant `*.feature.md`'s `## Workflows` row | Workflows table is the operator-visible capability contract |
| New vertical entirely | A NEW `*.feature.md` (allowed at DELIVERING by R13) | New vertical needs a permanent home; created at DELIVERING because the shape is now known |
| New pipeline or major stage addition | A NEW `*.flow.md` (allowed at DELIVERING by R13) OR new stage rows in an existing flow doc | Same as above |
| Engineering decision made under directive ambiguity | Decisions-Made section of the archived directive | Decisions are about THIS directive's ask; they don't belong to a vertical |
| Operational rationale for THIS directive's choices | Stays in the archived directive | It is the historical record of the ask |

The PreToolUse hook gates this: closing a directive (Status `Active -- phase: DELIVERING` -> `Closed`) requires a non-empty `## Promotions` section listing the source -> target rows. Without promotion, content rots in the archive and the durable docs drift.

## Lifecycle: feature/flow content removal (deletion, not annotation)

When a directive removes a capability described in an existing `*.feature.md` / `*.flow.md`, R14 refuses annotation lines like `removed YYYY-MM-DD` / `deprecated` / `no longer used`. The obsolete section is deleted entirely. Rationale: the directive's archive carries the reason for removal, so the doc itself has no remaining job for the deleted section. Two homes for "why this was removed" creates drift.

## Archived directive shape (thin pointer)

A closed directive is a historical record, not a duplicate home for durable content. After promotion, the archive holds:

1. **Outcome** (restated)
2. **Criteria** (restated, with verification result per criterion)
3. **Promotions** (table of source -> target file -- the pointer set)
4. **Verification** (per-criterion evidence)
5. **Decisions-Made** (engineering calls made under ambiguity)

The archive does NOT hold design content that lives in a feature/flow doc. If a future reader wants to know what the vertical does, they read the feature doc. If they want to know why the directive made the choices it made, they read the archive.

This shape is enforced by the directive template (`.claude/directives/_template.md`) and gated by the hook (anti-drift size check: the directive must not grow during DELIVERING -- growth means content was duplicated rather than promoted).

## Common mistakes

- Writing a new `*.feature.md` mid-directive to "establish the vertical early" -- R13 refuses this outside DELIVERING. Reason: premature feature docs become aspirational and drift from the still-moving directive shape.
- Closing a directive without a `## Promotions` section -- the close is refused. Reason: without promotion, durable content stays buried in the archive and the feature/flow docs drift.
- Adding a `removed YYYY-MM-DD` annotation to a feature doc -- R14 refuses. Reason: annotations duplicate the directive's reason-for-removal; delete the obsolete section instead.
- Documenting a cross-stage seam in a `*.feature.md` -- belongs in the relevant `*.flow.md` per the seam-scope split. Reason: cross-stage seams describe pipeline contracts, which are flow-scope.
- Documenting an intra-feature seam in a `*.flow.md` -- belongs in the relevant `*.feature.md`. Reason: function-call seams to helpers are feature-scope.
- Treating the directive doc as a feature doc ("this directive describes how the X vertical works") -- the directive is the ASK, not the contract. The contract goes in the feature doc at promotion.

## Cross-references

- `.claude/rules/ceo-mode.md` -- Documents-first discipline, R13 / R14 enforcement, phase machine, Promotions gate
- `.claude/rules/feature-docs.md` -- feature doc shape, Workflows section, intra-feature Seams section
- `.claude/rules/flow-docs.md` -- flow doc shape, cross-stage Seams section
- `.claude/rules/seam-verification.md` -- seam enumeration discipline (which feeds the Promotions table at directive close)
- `.claude/standards/index.md` -- mechanically gated rules R13 (no-premature-docs) + R14 (no-annotation-drift) + DELIVERING phase gate
