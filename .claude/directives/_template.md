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

Change `Status: Active` -> `Status: Closed -- Success | Partial | Abandoned`. Add a `**Closed:** YYYY-MM-DD` line under Set. Then:

```bash
git mv .claude/directive.md .claude/directives/closed/YYYY-MM-DD-<slug>.md
cp .claude/directives/_template.md .claude/directive.md
```

Edit the new `.claude/directive.md` with the next directive. The renamed file becomes the archived record; `git log --follow` traces it.
