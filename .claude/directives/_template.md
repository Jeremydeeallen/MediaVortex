# Current Directive

**Set:** YYYY-MM-DD
**Status:** Active
**Replaces:** `directives/closed/<previous-slug>.md` (closed Success | Partial | Abandoned)

## Outcome

One paragraph describing the operator-observable end state. What is true after this directive is done that wasn't true before.

## Acceptance Criteria

1. ...
2. ...

(Each criterion: observable behavior, verifiable in SQL or by a single command. Rename-test, outsider-test, rewrite-test, negation-test, stability-test per `.claude/rules/feature-criteria.md`.)

## Out of Scope

- ...

## Constraints

- ...

## Escalation Defaults

- Tradeoff between A and B -> B
- Risk tolerance: low | medium | high

## Engineering Calls Already Made

- ...

## Status

Active YYYY-MM-DD -- next step.

---

## Closure (fill in when transitioning to closed)

Closure is gated on the doc supersession sweep. Do not close without completing it.

### 1. Doc supersession sweep (required)

For every doc the directive changed behavior in, walk it through the three-state decision:

| State | Action |
|---|---|
| Doc describes behavior the directive CHANGED | Update in place. Stale text = future cost. |
| Doc describes a feature the directive SUPERSEDED in part | Add a `> **Superseded in part by `<new-doc-path>`** (YYYY-MM-DD): <one-line what changed>` block at the top. Keep the original as historical record; readers see what's no longer true. |
| Doc describes something now fully REMOVED | Delete the file after `grep -r '<old-doc-basename>'` returns zero matches outside the file itself. |

Concrete sweep commands (adjust to the directive's blast radius):
```bash
# Find docs that mention the feature areas this directive touched
grep -rln "<keyword>" --include="*.feature.md" --include="*.flow.md" --include="*.md"
# For each hit: classify (update | mark superseded | delete) and act.
```

Record the sweep outcome in the directive's Status block (which docs were updated, marked superseded, or deleted). This is the audit trail.

### 2. Mark closed + archive

Change `Status: Active` -> `Status: Closed -- Success | Partial | Abandoned`. Add a `**Closed:** YYYY-MM-DD` line under Set. Then:

```bash
git mv .claude/directive.md .claude/directives/closed/YYYY-MM-DD-<slug>.md
cp .claude/directives/_template.md .claude/directive.md
```

Edit the new `.claude/directive.md` with the next directive. The renamed file becomes the archived record; `git log --follow` traces it.
