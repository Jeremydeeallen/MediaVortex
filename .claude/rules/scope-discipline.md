# Scope Discipline

When the user asks for X, do exactly X. File anything else. This rule overrides the default instinct to be expansively helpful.

## The task contract

Before any non-trivial code change, restate the task in this shape. The user confirms or corrects before any code is touched.

```
SCOPE: [exactly what will be done]
NOT IN SCOPE: [things noticed but won't be fixed this session]
DONE WHEN: [observable success criteria]
PIPELINE SURFACES TOUCHED: [other features/files that read/write this code]
BUDGET: [file count or step cap before checking back]
```

If the task can't be expressed in this form, the task isn't clean. Ask for the missing piece before starting. If the contract is rejected, negotiate before code is touched.

The `NOT IN SCOPE` line is load-bearing. It names what's tempting to drift into and commits to filing rather than fixing.

## The rules

1. When the user asks for X, do X. If Y is noticed while doing X, file it (`/b` for bugs, backlog note otherwise). Do not fix Y.
2. No new abstractions, helpers, refactors, or simplifications unless they are in the task scope.
3. "While I'm here" is not a valid reason to expand scope.
4. If the task turns out to be bigger than scoped, stop and report. Do not expand silently.
5. No architectural suggestions in the middle of an implementation task. Save them for after delivery or file to backlog.
6. No criteria, slices, or success-criteria added to feature docs mid-task without explicit permission.
7. No "improved" / "cleaned up" / "simplified" claims about adjacent code. That is drift announcing itself.

## Mandatory pre-change checks (for code edits)

Before editing any file not already read this session:

1. Read the feature doc that owns the code (walk `*.feature.md` from the file's directory upward)
2. Read the flow doc for the pipeline (walk `*.flow.md` similarly)
3. Grep for other callers of the function being changed
4. Name the rules in `.claude/rules/` that apply
5. State the proposed change in one sentence
6. If the change touches a claim, decision, or repository query: run `py -m pytest Tests/Contract/TestClaimAuthority.py` AND reference `.claude/rules/db-is-authority.md` in the commit message. The conformance suite must stay green.

Slow + correct beats fast + broken.

## Mandatory post-change verification

Before reporting "done":

1. Run the specific contract tests for the affected feature
2. Import + invoke the changed function in isolation
3. State explicitly what was NOT changed in adjacent code that could have been
4. State explicitly what tests were NOT run that probably should have been

The "did NOT" lines force honesty about coverage gaps.

## Drift signals (self-check before each response)

If any of these appear in the proposed response, drift is happening:

- Multiple files changed when one would do
- A new helper function or class not in task scope
- Simplification or rename of unrelated code
- Phrases: "let me also," "while I'm here," "I noticed," "I also fixed," "improved," "cleaned up," "took the opportunity to"
- Architectural suggestion mid-implementation
- "This is also a problem in [other file]" while editing the current file

If present: stop, re-read the task contract, decide whether the work needs re-scoping or filing.

## Correction signal

If the user says **"scope"** (alone or in a sentence), stop, re-read the original task contract, and either:

- Get back in scope, OR
- Surface that the scope was wrong and request re-scoping

Do not argue. Do not proceed past the redirect. The user's redirect is the authority.

## Honest caveats

- Drift will still happen sometimes. The point is to make it visible fast.
- Pre-change checks add time. That is the trade.
- Default training pushes toward expansive helpfulness; these rules are the counterweight. They have to be applied at every response, not just at session start.
