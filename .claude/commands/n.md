---
description: Start a new CEO directive. Pauses any active directive, opens a fresh directive doc, walks operator through outcome + acceptance criteria. No code until criteria approved.
argument-hint: <directive-slug>
---

New directive: $ARGUMENTS

Follow in order. Do not write code before step 8.

1. Read CLAUDE.md, KNOWN-ISSUES.md, and `~/.claude/projects/<this-repo>/memory/MEMORY.md` for related context on `$ARGUMENTS`. Look for prior closed directives in `.claude/directives/closed/` whose slug or outcome touches the same area.

2. **Pivot check.** Read `.claude/directive.md`. If `**Slug:**` is a real slug (not the `<previous-slug>` placeholder) and `**Status:**` starts with `Active`:
   - If `git status --porcelain` returns output, commit a pause snapshot first: `git add -A && git commit -m "chore(pause): <current-slug> paused -- preempted by $ARGUMENTS"`.
   - Move the existing directive to archive: `git mv .claude/directive.md .claude/directives/closed/$(date +%Y-%m-%d)-<current-slug>.md`. Edit its `**Status:**` line to `Closed -- Paused -- preempted by $ARGUMENTS on YYYY-MM-DD`.

3. Copy the template to the active position: `cp .claude/directives/_template.md .claude/directive.md`.

4. Edit `.claude/directive.md` header:
   - `**Set:** <today, YYYY-MM-DD>`
   - `**Status:** Active -- phase: NEEDS_STANDARDS_REVIEW`
   - `**Slug:** $ARGUMENTS`
   - `**Replaces:** <prior-slug-archived-this-session>` or `none (new directive)`

5. With the operator, draft the **Outcome** paragraph. One paragraph describing the operator-observable end state. Be concrete -- criteria flow from outcome clarity. Tight outcome -> tight criteria -> autonomous delivery.

6. Draft **Acceptance Criteria** as a numbered list. Each criterion MUST pass the litmus tests in `.claude/rules/feature-criteria.md` (rename / outsider / rewrite / negation / stability). Each MUST be verifiable in SQL or by a single command. Reject vague criteria; force specifics.

7. Fill in **Out of Scope** (explicit boundaries -- what this directive is NOT doing), **Constraints** (operational limits, e.g. "no service restart required"), **Escalation Defaults** (named tradeoff defaults so I do not have to ask), **Engineering Calls Already Made** (decisions baked in), and `## Files` (planned files for R15 directive-anchor enforcement). Per `.claude/rules/ceo-mode.md`: loose criteria amplify escalation; tight criteria amplify autonomous delivery.

8. Report the directive as ready for review. List unresolved questions if any. NO code until the operator explicitly approves the criteria. Approval triggers the operator to advance phase from `NEEDS_STANDARDS_REVIEW` to `NEEDS_PLAN` by editing the `**Status:**` line in the directive doc.

The PreToolUse hook (`.claude/hooks/pre-edit-standards.ps1`) reads phase from the directive doc per call; once `**Status:** Active -- phase: <X>` updates, the gate behavior switches immediately. No service restart needed.
