# Current Directive

**Set:** 2026-06-02
**Status:** Active -- phase: DELIVERING
**Slug:** task-delegation-opt-in
**Replaces:** none (new directive)

## Outcome

Task-delegation mode (no-directive code edits) becomes an explicit operator opt-in via a marker file `.claude/.task-delegation-on`. Claude cannot create the marker (hook refuses any Write/Edit targeting it). When the marker is absent and no directive is active, the PreToolUse hook refuses code/contract edits with a message naming the two paths forward (`/n <slug>` or operator-creates-marker). When the marker is present, every assistant response leads with a visible warning that task-delegation is ON.

The empty-directive state stops being a free pass. The discipline lapse that produced commit `2b69d30` (substantive code change without a directive) becomes mechanically impossible by default.

## Acceptance Criteria

1. **Hook refuses code edits when no directive AND marker absent.** With `.claude/directive.md` in template state (`Slug: <previous-slug>`) and `.claude/.task-delegation-on` absent, any `Write`/`Edit` whose target is not `.claude/directive.md` itself is refused with a message naming the two paths forward (`/n <slug>` or operator-creates-marker). Verifiable: in this state, `Edit StartWorker.py` -> refusal with the named message.

2. **Hook allows code edits when no directive AND marker present.** With `.claude/directive.md` in template state and `.claude/.task-delegation-on` present, `Write`/`Edit` proceeds (subject to other rules R1-R18). Verifiable: in this state, `Edit StartWorker.py` -> succeeds (content rules still apply, but the phase gate does not fire).

3. **Hook refuses Claude-driven Write/Edit on the marker itself.** Any `Write`/`Edit`/`MultiEdit` whose target path is `.claude/.task-delegation-on` is refused regardless of directive state, with a message saying the operator must toggle this file directly. Verifiable: `Write .claude/.task-delegation-on "anything"` -> refusal.

4. **UserPromptSubmit hook emits a warning system-reminder when marker is present.** When `.claude/.task-delegation-on` exists at the time of any user prompt, the hook injects a `<system-reminder>` instructing the assistant to start its response with `WARNING: TASK-DELEGATION MODE ON -- operator opt-in via .claude/.task-delegation-on; directive discipline bypassed for this session.` Verifiable: create the marker, send any prompt, observe the warning at the top of the assistant response.

5. **`.claude/rules/ceo-mode.md` and `CLAUDE.md` document the new model.** ceo-mode.md's "Active whenever" paragraph is replaced with opt-in semantics naming the marker file. CLAUDE.md gains a one-line entry under "Where everything lives" explaining how to enable/disable task-delegation. Verifiable: `grep -l '\.task-delegation-on' CLAUDE.md .claude/rules/ceo-mode.md` returns both files; each hit describes the opt-in mechanism.

## Out of Scope

- Migrating closed directives or rewriting prior session history.
- Skill-side changes to `/b`, `/t`, `/bs` to scaffold mini-directives automatically. (Mitigation suggestion `_template-bugfix.md` deferred; they'll flow through `/n` for now.)
- Replacing the `<previous-slug>` template sentinel with a different empty-detection mechanism. The current sentinel works once this directive ships -- the marker file replaces task-delegation auto-fallback.
- Audit / re-open of prior task-delegation commits (`2b69d30`, etc.). Separate housekeeping.

## Constraints

- No DB schema change.
- No worker protocol change.
- The marker file's name (`.claude/.task-delegation-on`) is fixed by this directive -- no parameterization, no SystemSettings knob. The point is binary opt-in, not configuration.
- The warning string must be visually distinct enough that the operator notices it even when scanning quickly (leading "WARNING:" + line break before the response body).

## Escalation Defaults

- Tradeoff: hook refusal message verbose vs. terse -> verbose with both paths forward named. Reason: operator surprise on first hit should be self-resolving.
- Tradeoff: marker file in `.claude/` vs. repo root -> `.claude/`. Reason: keeps framework state colocated; `git status` still surfaces it.
- Risk tolerance: low. Affects every future session's gate behavior.

## Engineering Calls Already Made

- Marker file as a binary presence-check, not a value-bearing config file. Simplicity over flexibility.
- The PreToolUse hook is the right enforcement point because it already runs on every Write/Edit and has access to file paths + directive state.
- The UserPromptSubmit hook is the right injection point because it runs once per user message, before the assistant generates its response, so a system-reminder reliably reaches the model.
- `.claude/.task-delegation-on` is tracked by git (`git add` it when present) so the state is visible in `git status` and recoverable across sessions. The operator can `git rm` it to disable.

## Status

Active 2026-06-02 -- phase: NEEDS_STANDARDS_REVIEW -- standards already reviewed in this session (rules auto-loaded, standards/index.md read earlier); advancing to NEEDS_PLAN next.

Phases advance by editing this Status line: `**Status:** Active -- phase: <NEXT>`. The PreToolUse hook reads this line to gate tool calls. See `.claude/standards/index.md` for the phase machine.

### Files

```
.claude/hooks/pre-edit-standards.ps1   -- EDIT: refuse-when-no-directive logic + marker-write guard
.claude/hooks/user-prompt-submit.ps1   -- CREATE (or extend existing): emit warning system-reminder when marker present
.claude/settings.json                  -- EDIT: register UserPromptSubmit hook (if not already registered)
.claude/rules/ceo-mode.md              -- EDIT: replace fallback paragraph
CLAUDE.md                              -- EDIT: document opt-in mechanism in "Where everything lives"
```

### Promotions

| Source artifact | Target file | Commit |
|---|---|---|
| Opt-in policy + warning shape | `.claude/rules/ceo-mode.md` (extended in this directive's Files; no separate promotion at close) | TBD until close |
| Operator-visible toggle instructions | `CLAUDE.md` (extended in this directive's Files; no separate promotion at close) | TBD until close |
| no separate feature/flow doc promotions | n/a | this directive is pure framework infrastructure -- the policy lives in ceo-mode.md which is the rule itself |

### Verification

- **Criterion 1:** Smoke-tested under synthetic RepoRoot 2026-06-02 with empty directive + no marker; hook returned `{"permissionDecision":"deny", ...}` with the documented two-paths-forward message. PASS.
- **Criterion 2:** Same synthetic RepoRoot, marker created via `New-Item`; hook stdout empty (= allow). PASS.
- **Criterion 3:** Live in this session: `Write .claude/.task-delegation-on` was refused with the documented operator-only message ("The operator must create/delete this file directly..."). PASS.
- **Criterion 4:** UserPromptSubmit hook run two ways: (a) live with marker absent -- exit 0, no output (the no-warning case); (b) synthetic RepoRoot with marker present -- emitted `{"hookSpecificOutput":{"hookEventName":"UserPromptSubmit","additionalContext":"WARNING: TASK-DELEGATION MODE ON -- ..."}}`. Both arms PASS for the hook script. Runtime injection into the assistant's response will be verified by the operator after this directive closes (create marker, send any prompt, observe warning at top of response).
- **Criterion 5:** `grep -l '\.task-delegation-on' CLAUDE.md .claude/rules/ceo-mode.md` returns both files; each hit names the opt-in mechanism + operator-only constraint. PASS.

### Decisions Made

- Marker file lives at `.claude/.task-delegation-on` (under `.claude/`, dot-prefixed, no extension). Hidden-by-convention but `git status` still surfaces it for visibility.
- Marker-write guard fires regardless of directive state -- even an active directive cannot create or delete the marker via Claude. Only the operator's direct filesystem access can toggle it.
- Hook + standards files (`.claude/hooks/`, `.claude/standards/`, `.claude/rules/`, `.claude/directives/`, `.claude/plans/`) are NOT exempt from the task-delegation gate. Reason: editing the enforcement layer itself is exactly the kind of work that needs a directive; carving out an exemption would defeat the policy on the first session.
- UserPromptSubmit hook output uses `additionalContext` (the documented field for injecting system-reminder-shaped context) rather than blocking. The warning is information, not a refusal.
- Directive-doc edits are exempt from the gate when no directive is active. Reason: `/n` scaffolds the directive doc as its first write; the operator advances phases by editing the Status line. Without this exemption the system would be permanently wedged on the first directive-less session.
