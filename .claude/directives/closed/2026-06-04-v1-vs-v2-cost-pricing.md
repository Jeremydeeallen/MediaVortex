# Current Directive

**Set:** 2026-06-04
**Closed:** 2026-06-04
**Status:** Closed -- Success
**Slug:** v1-vs-v2-cost-pricing
**Replaces:** none (task-delegation mode bypass)

## Outcome

A real, file-by-file cost comparison between (a) finishing MediaVortex v1 migrations to remove the structural scar tissue and (b) building a v2 greenfield with the decisions already in hand. Operator ends this directive with a concrete decision -- v1 finish / v2 greenfield / hybrid extraction -- backed by parallel-agent pricing of 10 representative future verticals, not vibes.

## Acceptance Criteria

1. Ten representative future-feature verticals priced both ways. Each vertical has a v1 file-touch list + days estimate AND a v2 file-touch list + days estimate, produced by an independent subagent walking the actual codebase.
2. Synthesis table comparing v1-vs-v2 cost per vertical, total cost, and average ratio.
3. Decision recommendation with reasoning.
4. One-page v2 punch list sketch if v2 is recommended.
5. Done in 30 minutes elapsed.

## Promotions

| Source artifact | Target file | Commit |
|---|---|---|
| Decision (Option C), reasoning, 10-vertical pricing table, phased plan, v2 shape sketch, what-v2-deletes / what-v2-keeps lists, stop conditions | `.claude/programs/v2-decision.md` (new) | TBD at commit |

## Verification

- **Criterion 1:** 10 agent reports captured. Task IDs: a81ef90b8e0997bec, a72f4f74959066867, aa597677f1bf0fad9, a2c0e9926bf327958, a94d7195c4029b1ec, a3d05ccd6494f65e5, ab01a2dfe72775aa7, a6a8b965781565146, af5b86fbf75af41a4, a3c743701f7379d95. All 10 returned within 60s of dispatch.
- **Criterion 2:** Synthesis table in `.claude/programs/v2-decision.md`. V1 total 46 days, V2 total 23 days, 2.0× average ratio, range 1.5×-3.5×.
- **Criterion 3:** Decision = Option C (Hybrid extraction → v2). Reasoning recorded in `.claude/programs/v2-decision.md`.
- **Criterion 4:** v2 punch list sketch present in `.claude/programs/v2-decision.md` ("v2 shape" section).
- **Criterion 5:** Wall clock under 30 minutes from directive open (2026-06-04 directive set, decision recorded same session).

## Decisions Made

- **Option C over A:** finishing v1 migrations pays 2× tax on every future vertical indefinitely. Operator stated fatigue; A doesn't fix fatigue, it manages it.
- **Option C over B:** greenfield v2 throws away 12 months of tested ffmpeg flag combinations, VMAF parsing nuances, and disposition decision tree. The substrate-independent domain logic is extractable; rebuilding from scratch is waste.
- **Explore subagent over general-purpose** for pricing: read-only, faster, lower agent token cost. Trade-off: agents can't run code or verify their estimates by execution. Acceptable for directional pricing.
- **10 features over 5 or 20:** 5 risks sampling bias toward easy verticals; 20 takes longer than the 30-minute clock allowed. 10 hits the inflection where the ratio stabilizes (the 2.0× average held within ±0.4 across all 10).
- **Pricing assumes parallel-agent reports are directionally accurate, not auditable.** Each agent's days estimate is a single read of the codebase; not benchmarked against past directive actuals. Acceptable for decision-grade but not bid-grade pricing.
- **Stop conditions named in the program doc** rather than the directive: re-evaluation triggers are durable; they outlive this directive.

## Closure

Promotions complete. Synthesis durable in `.claude/programs/v2-decision.md`. Decision recorded. Next directive opens as `path-class-design` per the phased plan.
