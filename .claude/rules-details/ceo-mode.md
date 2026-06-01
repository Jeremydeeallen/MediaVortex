# CEO Mode -- Details

> Invariant: `.claude/rules/ceo-mode.md`.

## Show the road, not the wall

Every rule, refusal message, and policy doc in CEO mode is prescriptive: it names the path forward, not just the violation. A refusal that says "X is wrong" leaves the reader stuck; a refusal that says "X is wrong; do Y next" advances the work. Hook messages, this rule doc, and any future policy you write follow the same shape -- the reader leaves the message knowing the next action, not just the prohibition.

This applies recursively: when you cite policy in code review, in a directive doc, or in a refusal, lead with the path forward.

## Two strikes on a hook refusal

When the SAME hook rule refuses the SAME file twice in the same session, the second refusal includes a `STOPPED` preamble. That preamble means the workaround path you keep trying does not exist; the prescribed `Path forward:` in the refusal text is the answer. Iterating produces only token cost and no progress.

The pivot at the 2nd refusal is one of two options, both literal:

| Option | When | What it looks like |
|---|---|---|
| **(a) Do the prescribed Path forward literally** | The refusal's `Path forward:` is concrete and bounded | Open the file or doc the refusal names. Apply the action it names. No reinterpretation, no clever variant. |
| **(b) Ask the operator to unblock** | The prescribed path is genuinely unworkable for a stateable reason | One sentence: "Hook refused R<N> on `<file>` for the Nth time; the prescribed path is `<X>` but I think it would `<consequence>`; can you confirm?" |

**What the 2nd refusal is NOT a license for:**

- Opening a follow-up directive to escape -- we're working on the CURRENT directive; pivoting is itself a workaround.
- Another variant of the same workaround (different override placement, different escape syntax). Refusal counter doesn't distinguish variants.
- Editing a different file as distraction. 2-strike state is per file.

**Why this exists:** the `UseNvidiaHardware` work and the `commandbuilder-comment-promotion` directive both surfaced cases where I tried 5+ variants of an `# allow:` override against an R12 refusal before doing the prescribed classify-then-fix pass. Estimated cost: 10K+ tokens of wall-banging per loop.

State tracked in `.claude/.refusal-state.json` keyed on `(rule_id, file_path_lowercase)`. Resets per session.

## Handling preexisting comment / doc violations encountered mid-directive

When you touch a file and the hook flags a preexisting R12, R6, or similar legacy violation on code outside this directive's surface:

**Step 1: classify the block** into one of four buckets:

| Bucket | What it looks like | Path forward |
|---|---|---|
| **Pure WHAT-redundancy** | Comment restates the code | Delete entirely. |
| **Active-directive WHY** | Rationale that emerged during THIS directive | Put in current `.claude/directive.md`; leave `# directive: <slug>` anchor in code. |
| **Permanent-invariant WHY** | BUG refs, hard-won constraints | Open a new directive; **MOVE** content to permanent home (`KNOWN-ISSUES.md` under BUG-NNNN, or relevant `*.feature.md`); leave single-line anchor in code. |
| **Surprising WHY that fits nowhere** | A genuine "this code looks weird because..." note | Collapse to single-line comment. R12 allows one line. |

**Step 2: scope decision.** If many blocks across many sections (5+ blocks, or all in one subsystem), classification IS its own directive. Open `<file>-comment-promotion`.

**Step 3: code anchors.** Every moved block leaves a one-line pointer: `# BUG-NNNN`, `# see <doc-path>`, `# directive: <slug>`.

**Override usage (`# allow: <reason>`):** Reserve for cases where the proper fix would expand current directive's surface beyond reason. R6 path-shape migration is the canonical case. For R12, the proper fix is almost always cheaper than an override.

## One editor per conceptual unit (no parallel UIs)

When a directive surfaces new fields in a UI that already edits related fields on the same conceptual unit (Profile + Thresholds; Job + Progress; User + Settings), the directive's outcome includes unifying the editors. ONE editor for the conceptual unit when the directive closes.

**Path forward when you find a legacy editor that overlaps your work:**

1. **Inventory** the editors that touch the conceptual unit.
2. **Classify the overlap:**
   - Strict subset (your fields subset of legacy): extend in place
   - Strict superset (yours covers everything): retire the legacy editor in the same directive
   - Overlapping but neither covers: unify into one
   - Disjoint: two editors OK; document why
3. **Retirement / unification IS part of "done."** Do NOT ship parallel UI and defer retirement.
4. **Distinction from preexisting-comment policy:** that policy DEFERS independent legacy debt. THIS rule is for debt you CREATED -- yours to finish.

**Verification:** operator can answer "where do I edit X?" with exactly one URL + modal. "Basic fields here and advanced there..." = not done.

**Judgment, not hook-gated.** Operator review at delivery surfaces violations.

## Reporting cadence

**At delivery:** the full report shape (see invariant).

**Mid-cycle:** ONLY when escalating. One sentence + question + recommendation. Not a status update.

**On demand (user asks "where are we"):** report against directive's criteria -- what's done, what's left, what's blocked. Not a task-level enumeration.

## Interaction with scope-discipline.md

Scope-discipline still applies per-task. CEO mode does not relax it -- it shifts where the task contract comes from. In CEO mode, Claude produces task contracts itself from the plan; in task-delegation mode, the user produces them.

The "scope" correction signal works in both modes.

## Honest caveats

- Claude's judgment may differ from the user's. The price of autonomous delivery is some choices made differently than the user would have.
- Loose criteria amplify this risk. Tight criteria minimize it.
- "Done" depends on criteria quality. Garbage in, garbage out.
- This mode rewards investment in criteria-writing up front. It penalizes loose specs.
