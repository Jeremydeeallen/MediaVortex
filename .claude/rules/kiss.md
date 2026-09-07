# KISS

Keep It Simple. The smallest change that removes the reported symptom is the correct change. Overblown solutions are refused -- by the operator, the hook, and (eventually) by production.

## The rule

For every fix, ask: **what is the minimum change that stops the bleeding?** Ship that. File everything adjacent.

- One symptom -> one fix. Two symptoms -> two directives.
- Bug reports capture the symptom + its minimum fix. Aspirational compliance, tooling upgrades, adjacent cleanup do NOT ride along.
- Directive scope = ONE conceptual change. If the fix list has 3+ items across 3+ verticals, decompose before opening.
- "While I'm here" is refused (see `scope-discipline.md`).
- Multi-line comments, docstrings, defensive layers, and "future-proof" abstractions are refused (see R12 + `fail-loud.md`).

## Decomposition test

When drafting a bug report or directive, count:

1. Distinct symptoms (each maps to one fix)
2. Distinct principles violated (each maps to one directive)
3. Distinct code verticals touched (each = a scope-check)

If any count > 1, split. The correct output is N smaller directives, not one bloated one.

## Anti-patterns

- Bug report with "Fix scope" listing 5+ items -> pick the ONE that stops the bleed; file the rest separately.
- Directive that bundles "fix the bug + upgrade the tooling + add GUI + write migration" -> split. Bleeding first, tooling later.
- Refactor that "cleans up while fixing" -> the refactor is a separate directive.
- New abstraction to "make future fixes easier" -> YAGNI; add on the second occurrence, not the first.
- Adding a config toggle to defer a decision -> pick the correct default; toggles are debt.

## When this rule applies (PR triggers)

- Opening a bug report (`/b`)
- Opening a directive (`/n`)
- Reviewing a delivery report -- if it lists deferred items, the scope was wrong; split retroactively.

## Related

- `scope-discipline.md` -- per-task scope contract; KISS is the meta-principle above it.
- `ceo-mode.md` -- one editor per conceptual unit; matches KISS's "one directive per principle".
- `feature-criteria.md` -- criteria that pass the five litmus tests are inherently KISS-sized.
