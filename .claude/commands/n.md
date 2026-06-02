---
description: Start a new CEO directive. Discovers related context, pauses any active directive, scaffolds the directive doc with Outcome + Acceptance Criteria. No code until criteria approved.
argument-hint: <directive-slug or outcome description>
---

New directive: $ARGUMENTS

Follow in order. Do not write code before step 9.

1. **Discovery.** Read CLAUDE.md, the project's issue tracker (path discovered from CLAUDE.md; fallback `memory/KNOWN-ISSUES.md`), and `~/.claude/projects/<repo>/memory/MEMORY.md` for context on `$ARGUMENTS`. Scan `.claude/directives/closed/` for closed directives whose slug or outcome overlap; cite any that are relevant.

2. **Slug shape.** If `$ARGUMENTS` is a descriptive sentence rather than a kebab-case slug, propose a short kebab-case slug derived from the outcome (e.g. "fix library compliance as a whole" -> `library-compliance-completeness`). Surface the proposed slug to the operator; use it for the rest of the steps.

3. **Pivot check.** Read `.claude/directive.md`.
   - If `**Slug:**` is a real slug (not `<previous-slug>` placeholder) AND `**Status:**` starts with `Active`:
     - If `git status --porcelain` returns output, commit a pause snapshot: `git add -A && git commit -m "chore(pause): <current-slug> paused -- preempted by <new-slug>"`.
     - Archive: `git mv .claude/directive.md .claude/directives/closed/YYYY-MM-DD-<current-slug>.md`. Edit its `**Status:**` to `Closed -- Paused -- preempted by <new-slug> on YYYY-MM-DD`.
   - If the active directive doc is in template state (Slug is `<previous-slug>` placeholder or Status does not start with `Active`), skip the archive step -- nothing to pause.

4. **Scaffold from template.** Copy `.claude/directives/_template.md` to `.claude/directive.md`.

5. **Edit the header:**
   - `**Set:** <today, YYYY-MM-DD>`
   - `**Status:** Active -- phase: NEEDS_STANDARDS_REVIEW`
   - `**Slug:** <new-slug>`
   - `**Replaces:** <prior-slug-archived-this-session>` or `none (new directive)`

6. **Draft Outcome.** One paragraph describing the operator-observable end state. What is true after this directive ships that wasn't true before. Concrete over abstract. Tight outcome drives tight criteria drives autonomous delivery.

7. **Draft Acceptance Criteria as a numbered list.** Each criterion MUST pass the litmus tests in `.claude/rules/feature-criteria.md` (rename / outsider / rewrite / negation / stability) AND be verifiable in SQL or by a single command. Reject vague criteria; force specifics. If a criterion's evidence path can't be named in one sentence, the criterion is not yet sharp enough.

8. **Fill remaining sections:**
   - `## Out of Scope` -- explicit boundaries (what this directive is NOT doing).
   - `## Constraints` -- operational limits ("no service restart required", "no DB migrations", etc.).
   - `## Escalation Defaults` -- named tradeoff defaults so escalation is rare.
   - `## Engineering Calls Already Made` -- decisions baked in.
   - `### Files` -- planned files for R15 directive-anchor enforcement.

9. **Report ready for review.** Surface unresolved questions if any. NO code until the operator explicitly approves the criteria. Approval signal: the operator advances phase via `**Status:** Active -- phase: NEEDS_PLAN` in the directive doc (or skips to a later phase if standards have been recently reviewed in this session).

The PreToolUse hook (`.claude/hooks/pre-edit-standards.ps1`) reads phase from the directive doc per call; once the Status line updates, the gate behavior switches immediately. No service restart needed.

## What this command does NOT do

- It does NOT create `*.feature.md` files. Feature docs are durable contracts; they live colocated with code and are created at DELIVERING via the directive's `### Promotions` table (R13). If the directive scope happens to create one, that happens at close-out, not now.
- It does NOT push onto a feature stack. The framework-default `/n` (feature stack) is intentionally not used in this project -- CEO mode replaces feature scaffolding with directive scaffolding.
- It does NOT touch code, run tests, or modify the database. Discovery + scaffolding only.
