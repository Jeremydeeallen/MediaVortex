# Scope Discipline -- Details

> Invariant: `.claude/rules/scope-discipline.md`.

## Drift signals (self-check before each response)

If any of these appear in the proposed response, drift is happening:

- Multiple files changed when one would do
- A new helper function or class not in task scope
- Simplification or rename of unrelated code
- Phrases: "let me also," "while I'm here," "I noticed," "I also fixed," "improved," "cleaned up," "took the opportunity to"
- Architectural suggestion mid-implementation
- "This is also a problem in [other file]" while editing the current file

If present: stop, re-read the task contract, decide whether the work needs re-scoping or filing.

## Why the task contract has to be explicit

If the task can't be expressed in the SCOPE/NOT-IN-SCOPE/DONE-WHEN/SURFACES/BUDGET form, the task isn't clean -- ask for the missing piece before starting. If the contract is rejected, negotiate before code is touched. The contract is the artifact that makes drift visible -- without it, every drift looks like reasonable progress.

## Why "while I'm here" is forbidden

It's the most common drift pattern. The local justification ("I'm already in this file, the fix is small") ignores the cumulative cost: the diff grows, the PR review surface grows, the scope creeps, the "done" judgment gets blurred. A 3-file change presented as a 1-file change burns operator trust and adds review time.

The replacement is filing: `/b` for bugs, backlog note for ideas. The file-not-fix discipline keeps the original task visible.

## Honest caveats

- Drift will still happen sometimes. The point is to make it visible fast.
- Pre-change checks add time. That is the trade.
- Default training pushes toward expansive helpfulness; these rules are the counterweight. They have to be applied at every response, not just at session start.
