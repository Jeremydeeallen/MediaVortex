# Scope Discipline

When the user asks for X, do exactly X. File anything else. Overrides the default instinct to be expansively helpful.

## The task contract

Before any non-trivial code change, restate the task:

```
SCOPE: [exactly what will be done]
NOT IN SCOPE: [things noticed but won't be fixed this session]
DONE WHEN: [observable success criteria]
PIPELINE SURFACES TOUCHED: [other features/files that read/write this code]
BUDGET: [file count or step cap before checking back]
```

The `NOT IN SCOPE` line is load-bearing: names what's tempting to drift into and commits to filing.

## The 7 rules

1. Do X. If Y is noticed while doing X, file it (`/b` for bugs, backlog otherwise). Do not fix Y.
2. No new abstractions, helpers, refactors, or simplifications outside task scope.
3. "While I'm here" is not a valid reason to expand scope.
4. If the task turns out bigger than scoped, stop and report. Do not expand silently.
5. No architectural suggestions mid-implementation. Save for after delivery or file to backlog.
6. No criteria added to feature docs mid-task without explicit permission.
7. No "improved" / "cleaned up" / "simplified" claims about adjacent code. That is drift.

## Mandatory pre-change checks (code edits)

Before editing any file not already Read this session:

1. Read the colocated `*.feature.md` (R1 enforced)
2. Read the colocated `*.flow.md`
3. Grep for other callers of the function being changed
4. Name the rules in `.claude/rules/` that apply
5. State the proposed change in one sentence
6. If touching a claim / decision / repo query: run `py -m pytest Tests/Contract/TestClaimAuthority.py` AND reference `db-is-authority.md` in commit

## Mandatory post-change verification

Before reporting "done":

1. Run contract tests for the affected feature
2. Import + invoke the changed function in isolation
3. State explicitly what was NOT changed in adjacent code
4. State explicitly what tests were NOT run

## Correction signal

If user says **"scope"** (alone or in sentence): stop, re-read the task contract, either get back in scope OR surface that scope was wrong. No arguing, no proceeding past redirect.

**Drift signals checklist, examples, and caveats:** see `.claude/rules-details/scope-discipline.md`.
