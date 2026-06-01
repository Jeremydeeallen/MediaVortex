# Doc Layering -- Details

> Invariant: `.claude/rules/doc-layering.md`.

## Why three tiers

Content has three different lifetimes:

- **Directives** are short-lived. They open with an ask, close with a delivery, and archive. Re-reading old directives tells you WHY code was changed at a point in time.
- **Feature docs** are long-lived. The vertical they describe persists across many directives. Re-reading a feature doc tells you WHAT a vertical does today.
- **Flow docs** are long-lived but shaped differently. They describe the pipeline -- the rails the verticals plug into. Re-reading a flow doc tells you HOW data crosses the system today.

Without layering, content collapses into whichever tier is most convenient -- typically the directive (because it's open and being edited) -- and the durable contracts decay. The "documentation lives only in the directive doc" rule from `ceo-mode.md` is correct DURING a directive; the missing half is what happens at the close, and that's what the Promotions section enforces.

## Lifecycle: directive -> features/flows (promotion)

During a directive, design content accretes in the directive doc. At DELIVERING, durable content is PROMOTED:

| Source content in directive | Target home | Rationale |
|---|---|---|
| Seam enumeration -- cross-stage contracts | The relevant `*.flow.md`'s `## Seams` section | Cross-stage seams are flow-scope |
| Seam enumeration -- intra-feature contracts | The relevant `*.feature.md`'s `## Seams` section | Intra-feature seams are feature-scope |
| New operator-facing capability | The relevant `*.feature.md`'s `## Workflows` row | Workflows table is the operator-visible capability contract |
| New vertical entirely | A NEW `*.feature.md` (R13 allows at DELIVERING) | New vertical needs a permanent home; created when shape is known |
| New pipeline or major stage addition | A NEW `*.flow.md` (R13 allows at DELIVERING) OR new stage rows | Same as above |
| Engineering decision under directive ambiguity | Decisions-Made section of the archived directive | About THIS directive's ask, not the vertical |
| Operational rationale for THIS directive's choices | Stays in the archived directive | Historical record of the ask |

## Archived directive shape (thin pointer)

After promotion, the archive holds:

1. **Outcome** (restated)
2. **Criteria** (restated, with verification result per criterion)
3. **Promotions** (table of source -> target file)
4. **Verification** (per-criterion evidence)
5. **Decisions-Made** (engineering calls made under ambiguity)

The archive does NOT hold design content that lives in a feature/flow doc. Future readers go to the feature doc for "what the vertical does"; to the archive for "why the directive made its choices."

## Cache discipline -- the deeper why

Claude Code auto-loads everything under `.claude/rules/` into the system prompt at session start. That content is replayed every turn. Cost compounds across long sessions.

The prompt cache provides a way to skip re-tokenizing unchanged content. But the cache invalidates the moment any byte changes. Implications:

- Cosmetic churn in always-loaded files (whitespace shifts, reordering, rewording with same meaning) is gratuitous cache invalidation. Don't.
- Adding a sentence to a rule doc costs every session forever. The math:  one sentence (~50 bytes) * tens of sessions / week * weeks = real cost. Edit with intent.
- Putting prescriptive prose in always-loaded files is what made the rules grow to ~53K. Prose belongs in details.

The graduation rule: a rule becomes always-loaded after it has fired at least 3 times AND survived one quarter without amendment. Until then, it lives in `rules-details/` and is opt-in via Read.

## Common mistakes

- Writing a new `*.feature.md` mid-directive to "establish the vertical early" -- R13 refuses outside DELIVERING. Premature feature docs become aspirational and drift from the still-moving directive shape.
- Closing a directive without a `## Promotions` section -- the close is refused. Without promotion, durable content stays buried in the archive and the feature/flow docs drift.
- Adding a `removed YYYY-MM-DD` annotation to a feature doc -- R14 refuses. Annotations duplicate the directive's reason-for-removal; delete the obsolete section instead.
- Documenting a cross-stage seam in a `*.feature.md` -- belongs in the relevant `*.flow.md`.
- Documenting an intra-feature seam in a `*.flow.md` -- belongs in the relevant `*.feature.md`.
- Treating the directive doc as a feature doc ("this directive describes how the X vertical works") -- the directive is the ASK, not the contract.
- Adding prose to a `.claude/rules/<name>.md` invariant doc -- belongs in `.claude/rules-details/<name>.md`. Always-loaded content stays tight.
