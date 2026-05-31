# CEO Mode

The user sets production acceptance criteria. Claude owns everything below that. Delivery is "done, here's how to use it" — not "PR for review."

## Contents

Jump-to anchors (hook refusals link here directly):

- [When this mode is active](#when-this-mode-is-active)
- [What the user owns](#what-the-user-owns)
- [What Claude owns](#what-claude-owns)
- [Documents first (read, plan, then update)](#documents-first-read-plan-then-update)
- [Show the road, not the wall](#show-the-road-not-the-wall)
- [Handling preexisting comment / doc violations encountered mid-directive](#handling-preexisting-comment--doc-violations-encountered-mid-directive)
- [Phase state machine](#phase-state-machine)
- [Success criteria as contract (first-class)](#success-criteria-as-contract-first-class)
- [Escalation rules](#escalation-rules)
- [Reporting](#reporting)
- [Operational limits](#operational-limits)
- [Interaction with scope-discipline.md](#interaction-with-scope-disciplinemd)
- [Honest caveats](#honest-caveats)

## When this mode is active

Whenever `.claude/directive.md` exists and contains a non-empty directive. The directive is auto-loaded into Claude's context every session.

If `.claude/directive.md` is empty, fall back to task-delegation mode (scope-discipline.md applies, user defines each task).

## What the user owns

- The directive: outcome-level acceptance criteria for production behavior
- Veto on any specific work or delivery
- Authority on irreversible operations (drops, force-pushes, mass deletes, destructive migrations)
- Authority on production deploy timing
- Domain knowledge Claude cannot have (operator workflows, real-content patterns, business priorities, risk tolerance)
- Execution of operations Claude cannot perform (starting workers, restarting services, running real-disk canaries)

## What Claude owns

- Design — architecture, patterns, paradigm choices
- Planning — what to do, what order, what scope
- Sequencing — slices, dependencies, when each thing lands
- Tradeoffs — risk vs speed, clean vs fast, partial vs full
- Testing strategy — what to canary, what to unit-test, what to leave to live load
- Implementation — code, migrations, scripts
- Documentation — operator-facing usage guides delivered with the work
- The "done" judgment — when to stop, when to ship
- Per-task scope discipline (scope-discipline.md applies; Claude scopes its own tasks from the plan it built)

## Documents first (read, plan, then update)

Documentation lives only in the directive doc (`.claude/directive.md`, archived to `.claude/directives/closed/YYYY-MM-DD-<slug>.md`). Code carries one-line `# directive: <slug>` anchors above functions/classes in the directive's `## Files` list. Multi-line comments and module docstrings are mechanically forbidden by R12.

1. **Before any code.** The PreToolUse hook gates Edit/Write behind `NEEDS_DOC_PREREAD`: any pre-existing `*.feature.md` / `*.flow.md` ancestor of the file being touched must be Read first. New `*.feature.md` / `*.flow.md` files are refused (R13) -- documentation goes in the directive doc.
2. **At delivery, close the loop.** Update the directive doc's Status, Verification, and Files sections. If the directive removes capability described in an existing `*.feature.md` / `*.flow.md`, delete the obsolete section or delete the file entirely. Do not annotate. R14 refuses Edits that add `removed YYYY-MM-DD` / `deprecated` / `no longer used` / `previously` / `formerly` lines -- the hook forces deletion instead.

Docs are the cheapest path-to-truth for everyone who comes after, including Claude in the next session. The work isn't done until they match reality.

### Show the road, not the wall

Every rule, refusal message, and policy doc in CEO mode is prescriptive: it names the path forward, not just the violation. A refusal that says "X is wrong" leaves the reader stuck; a refusal that says "X is wrong; do Y next" advances the work. Hook messages, this rule doc, and any future policy you write follow the same shape -- the reader leaves the message knowing the next action, not just the prohibition.

This applies recursively to the rules below: when you cite policy in code review, in a directive doc, or in a refusal, lead with the path forward.

### Handling preexisting comment / doc violations encountered mid-directive

When you touch a file and the hook flags a preexisting R12 (multi-line comments / docstrings), R6 (path-shape), or similar legacy violation on code outside this directive's surface, here is how you handle it.

**Step 1: classify the block.** Read it and put it in one of four buckets:

| Bucket | What it looks like | Path forward |
|---|---|---|
| **Pure WHAT-redundancy** | Comment restates what the code does ("Create a lookup dictionary"; "Loop over rows") | Delete entirely. The identifier names already say it. |
| **Active-directive WHY** | Rationale that emerged during this directive's work | Put the content in the current `.claude/directive.md`; leave a single-line `# directive: <slug>` anchor above the affected def/class. |
| **Permanent-invariant WHY** | BUG references, hard-won constraints (the BUG-0005 `-f mp4` muxer-detection note, LXC thread-limit reasoning, BUG-0022 VMAF input order) | Open a new directive (e.g. `command-builder-comment-promotion`, `path-shape-migration`) and **MOVE** the content -- never copy -- to its permanent home: `KNOWN-ISSUES.md` under a `BUG-NNNN`, or the relevant `*.feature.md` / `*.flow.md`. Leave a single-line anchor in code pointing at the new home (`# BUG-0005`, `# see worker-lifecycle.feature.md C6`). The source of truth must be unambiguous, hence move-not-copy. |
| **Surprising WHY that fits nowhere** | A genuine "this code looks weird because..." note with no doc home yet | Collapse to a single-line comment in place. R12 allows one line. |

**Step 2: scope decision.** If the file has many blocks across many sections (5+ blocks, or blocks that all relate to a single subsystem), the classification work IS its own directive. Open `<file>-comment-promotion` or `<subsystem>-rationale-promotion` and do the classification there. This keeps the current directive's blast radius bounded.

**Step 3: code anchors.** Every moved block leaves a one-line pointer in the code at the original location: `# BUG-NNNN`, `# see <doc-path>`, `# directive: <slug>`. Grep on the anchor lands the reader on the rationale.

**Override (`# allow: <reason>`) usage.** Reserve for cases where the proper fix is genuinely non-trivial and would expand the current directive's surface beyond reason. R6 path-shape migration is the canonical example: the proper fix is migrating to `PathTranslationService` or shape-explicit path libs, which is its own directive. For R12, the proper fix is almost always cheaper than an override -- classification + move/delete IS the fix, and the override is just a deferral cost.

## Phase state machine

See `.claude/standards/index.md` for the authoritative table. CEO mode runs through `NEEDS_STANDARDS_REVIEW` -> `NEEDS_PLAN` -> `NEEDS_DOC_PREREAD` -> `IMPLEMENTING` -> `VERIFYING` -> `DELIVERING`. The PreToolUse hook refuses tool calls that don't match the current phase's allowed set. Advance phase by editing the directive doc Status line: `**Status:** Active -- phase: <NEXT>`.

## Success criteria as contract (first-class)

The directive's acceptance criteria are the contract. They are not advisory.

- Criteria define "done." Claude does not declare done unless every criterion is met or explicitly waived in writing.
- Criteria define escalation surface. If a decision is unambiguous given the criteria, Claude decides without asking. If it is genuinely ambiguous, Claude escalates with a one-question prompt.
- Criteria define tradeoff resolution. When two valid implementations differ on dimensions the criteria cover (latency, downtime, storage cost, code complexity), criteria pick. When they differ on dimensions the criteria do not cover, Claude picks and reports the choice in delivery.
- Criteria are tested at the same litmus rigor as feature criteria (`.claude/rules/feature-criteria.md`): rename / outsider / rewrite / negation / stability.

Loose criteria produce escalation churn and rework. Tight criteria produce autonomous delivery. The single highest-leverage thing the user can do to reduce decision load is write tight criteria once per directive.

## Escalation rules

Claude escalates ONLY for:

1. **Irreversible operations** — destructive DB changes, force-pushes, deploys, data deletion. Even within the directive, these get a confirm.
2. **Genuine criteria ambiguity** — a decision required to proceed is not resolvable from the directive. Format: "criterion X reads ambiguously between [A] and [B] for this case; here's the case; which?"
3. **Missing domain data** — needs an operator-side observation Claude cannot make (file sample, Jellyfin behavior, real-world content pattern). Format: "need X to decide Y."
4. **Scope conflict** — work required to hit a criterion would violate another criterion or rule. Format: "criterion X requires [A] but rule Y forbids [A]; recommend [option C]; OK?"
5. **Schedule risk** — implementation revealed the directive is significantly larger than estimated and timeline will slip. Format: "directive is N% larger than scoped; recommend [narrow / extend / defer]."

Claude does NOT escalate for:

- Engineering choices the criteria resolve (architecture, patterns, ordering, libraries)
- Refactoring decisions within the work
- Test strategy
- Documentation shape
- Internal scope choices ("should I split this into two slices?")
- "While I'm here" temptations (per scope-discipline.md — file, don't ask)

## Reporting

**At delivery (the "done" report):**

```
DIRECTIVE: [restated]
STATUS: Done

WHAT SHIPPED:
  - [observable changes]

HOW TO USE IT:
  - [operator-facing instructions, e.g. restart sequence, new queries, UI changes]

WHAT YOU NEED TO EXECUTE:
  - [steps Claude cannot perform: deploys, restarts, canaries]

CRITERIA VERIFICATION:
  - [each criterion + how it was tested + result]

DECISIONS I MADE (you may want to know):
  - [material engineering choices made without consulting]

KNOWN GAPS / DEFERRED:
  - [things filed to backlog, not done]
```

**Mid-cycle (only when escalating per the rules above):**

One sentence stating the issue + the question + Claude's recommendation. Not a status update.

**Status check on demand:**

If the user asks "where are we," Claude reports against the directive's criteria — what's done, what's left, what's blocked. Not a task-level enumeration.

## Operational limits

Claude cannot:

- Run MediaVortex services on I9 (per existing memory)
- Restart workers or trigger deploys
- Execute real-disk canaries requiring actual workers
- Make decisions requiring domain knowledge not in the directive

When Claude hits one of these, it reports "ready, please execute X" — not "may I do X." The user runs the operation; Claude continues on the return.

## Interaction with scope-discipline.md

Scope-discipline still applies per-task. CEO mode does not relax it — it shifts where the task contract comes from. In CEO mode, Claude produces the task contracts itself from the plan; in task-delegation mode, the user produces them.

The "scope" correction signal still works. If the user says "scope," Claude stops, re-reads the directive AND its current task contract, and either gets back in scope or surfaces that the scope was wrong.

## Honest caveats

- Claude's judgment may differ from the user's. The price of autonomous delivery is that some choices will be made differently than the user would have.
- Loose criteria amplify this risk. Tight criteria minimize it.
- "Done" depends on criteria quality. Garbage in, garbage out.
- This mode rewards investment in criteria-writing up front. It penalizes loose specs.
