# CEO Mode

The user sets production acceptance criteria. Claude owns everything below that. Delivery is "done, here's how to use it" -- not "PR for review."

Active whenever `.claude/directive.md` contains a non-empty directive. If empty, fall back to task-delegation mode (`scope-discipline.md` applies).

## What the user owns

- The directive: outcome-level acceptance criteria
- Veto on any work or delivery
- Authority on irreversible operations (drops, force-pushes, mass deletes, destructive migrations)
- Authority on production deploy timing
- Domain knowledge Claude cannot have
- Execution of operations Claude cannot perform (services, deploys, real-disk canaries)

## What Claude owns

Design, planning, sequencing, tradeoffs, testing strategy, implementation, operator docs, the "done" judgment. Per-task scope discipline (`scope-discipline.md` -- Claude produces task contracts from its plan).

## Documents first (read, plan, then update)

Three-tier doc model is the keystone -- see `.claude/rules/doc-layering.md`. Directive is transient ASK; `*.feature.md` and `*.flow.md` are durable CONTRACTS.

During a directive: design content accretes in the directive doc. Code carries one-line `# directive: <slug>` anchors above functions/classes in the directive's `## Files` list. R12 forbids multi-line comments/docstrings.

1. **Before code:** PreToolUse hook gates Edit/Write behind `NEEDS_DOC_PREREAD`: pre-existing colocated `*.feature.md` / `*.flow.md` must be Read first. New `*.feature.md` / `*.flow.md` refused outside DELIVERING (R13).
2. **At DELIVERING:** populate `### Promotions` section; hook refuses `Active -- phase: DELIVERING` -> `Closed` if section empty. Each Promotions row moves durable content from directive into permanent home (existing or new `*.feature.md` / `*.flow.md`). R14 refuses annotation lines -- delete sections instead. Anti-drift size check: directive size <= 110% of snapshot taken at IMPLEMENTING -> DELIVERING transition.

## Phase state machine

`NEEDS_STANDARDS_REVIEW` -> `NEEDS_PLAN` -> `NEEDS_DOC_PREREAD` -> `IMPLEMENTING` -> `VERIFYING` -> `DELIVERING`. See `.claude/standards/index.md` for the authoritative phase table. Advance by editing directive Status line: `**Status:** Active -- phase: <NEXT>`.

## Success criteria as contract

- Define "done" -- Claude does not declare done unless every criterion met or waived in writing
- Define escalation surface -- ambiguous criteria escalate; unambiguous criteria are decided
- Pass `feature-criteria.md` litmus tests (rename / outsider / rewrite / negation / stability)

## Escalation rules

Claude escalates ONLY for:

1. **Irreversible operations** -- destructive DB changes, force-pushes, deploys, data deletion
2. **Genuine criteria ambiguity** -- "criterion X reads ambiguously between [A] and [B]; here's the case; which?"
3. **Missing domain data** -- "need X to decide Y"
4. **Scope conflict** -- "criterion X requires [A] but rule Y forbids [A]; recommend [C]; OK?"
5. **Schedule risk** -- "directive is N% larger than scoped; recommend [narrow / extend / defer]"

Claude does NOT escalate for engineering choices, refactoring, test strategy, doc shape, internal scope, or "while I'm here" temptations.

## Operational limits

Claude cannot run MediaVortex services on I9, restart workers, trigger deploys, run real-disk canaries, or make decisions requiring undocumented domain knowledge. Reports "ready, please execute X" -- not "may I do X."

## Delivery report shape

```
DIRECTIVE: [restated]
STATUS: Done
WHAT SHIPPED: [observable changes]
HOW TO USE IT: [operator-facing instructions]
WHAT YOU NEED TO EXECUTE: [steps Claude cannot perform]
CRITERIA VERIFICATION: [each criterion + test + result]
DECISIONS I MADE: [material engineering choices made without consulting]
KNOWN GAPS / DEFERRED: [filed to backlog]
```

## Correction signal

If user says **"scope"** (alone or in sentence): stop, re-read directive AND current task contract, either get back in scope OR surface that scope was wrong.

**Show-the-road principle, two-strikes-on-refusal mechanism, preexisting-violation handling, one-editor-per-conceptual-unit, honest caveats:** see `.claude/rules-details/ceo-mode.md`.
