# Doc Layering

Three documentation tiers. Non-overlapping roles. Each tier owns a distinct kind of content and a distinct lifetime.

## The three tiers

| Tier | File | Lifetime | Owns | Seam scope |
|---|---|---|---|---|
| Directive | `.claude/directive.md` -> `.claude/directives/closed/YYYY-MM-DD-<slug>.md` | Transient | The current CEO ask: outcome, criteria, plan, in-flight state, verification, decisions | Enumerated before IMPLEMENTING; promoted to feature/flow docs at DELIVERING |
| Feature | `*.feature.md` colocated with code | Durable | What a vertical DOES + Workflows + intra-feature seams | Intra-feature: function-call, helper, vertical-to-external-service |
| Flow | `*.flow.md` colocated with pipeline entry | Durable | What the pipeline DOES + stages + cross-stage seams | Cross-stage: data crossing each stage transition |
| Glossary | `GLOSSARY.md` at repo root | Durable | Terminology + deprecated-term pointers. Four buckets (project vocabulary / media-encoding / job model / infrastructure). Every entry names an authoritative source. | None -- terminology only, no seams |

Content has exactly one tier-appropriate home at any time. The directive is the ASK, not the contract. Features and flows are the CONTRACTS.

## Required at directive close (mechanically enforced)

The hook refuses `Active -- phase: DELIVERING` -> `Closed` unless:

1. `### Promotions` section in the directive is non-empty. Each row: `<source artifact in directive> -> <target *.feature.md / *.flow.md>`. New feature/flow files allowed at DELIVERING (R13 relaxes here for promotion).
2. Directive size <= 110% of snapshot taken at IMPLEMENTING -> DELIVERING transition. Growth means content was duplicated into the directive rather than promoted out.

R14 refuses annotation lines (`removed YYYY-MM-DD` / `deprecated` / `no longer used`) in feature/flow docs. Delete obsolete sections instead.

## Cache discipline (token-cost invariant)

Always-loaded content (`.claude/rules/*.md`, `CLAUDE.md`, `MEMORY.md`, the active directive doc) is prompt-cache sensitive. Every byte counts per session, every change invalidates cache. Discipline:

- New rules land in `.claude/rules-details/` first. They graduate to `.claude/rules/` only when proven invariant.
- Invariant files are tight (target < 1500 bytes each). Detailed prose, examples, common-mistakes, and prescriptive how-to live in the colocated `.claude/rules-details/<name>.md`.
- Hook output is deterministic (no timestamps in stable text, stable row order in `standards/index.md`, no cosmetic churn).
- Refactor that doesn't change meaning is forbidden in always-loaded files.

## Cross-references

- `ceo-mode.md` -- directive lifecycle, R13 / R14, phase machine
- `feature-docs.md` -- feature doc shape, Workflows, intra-feature Seams, Slug + IDs
- `flow-docs.md` -- flow doc shape, cross-stage Seams, Slug + IDs
- `seam-verification.md` -- seam enumeration discipline
- `standards/index.md` -- R13, R14, R16, DELIVERING gate

**Details, common mistakes, examples:** see `.claude/rules-details/doc-layering.md`.
