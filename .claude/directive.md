# Current Directive

**Set:** 2026-06-02
**Status:** Active -- phase: DELIVERING
**Slug:** version-on-deploy-doc-catchup
**Replaces:** none (doc-catchup for commit 2b69d30)

## Outcome

`deploy/version-on-deploy.feature.md` reflects the actual VERSION + BUILD_INFO shape that shipped in commit `2b69d30`. The doc currently specifies bare SHA in VERSION and exactly-three-line BUILD_INFO; the shipped code optionally appends `(ahead N)` / `(behind N)` / `(ahead N, behind M)` to VERSION and an optional `relative_to_main=<state>` line to BUILD_INFO when local HEAD diverges from `origin/main`. The doc gets updated to match reality; the latent regression in deploy strict-equality verification (criterion 5) is acknowledged in the doc as Known Gap with the deferred fix named, not silently left for the next remote Windows deploy to discover.

## Acceptance Criteria

1. **Criterion 4 (BUILD_INFO format) reflects the new optional line.** `deploy/version-on-deploy.feature.md` criterion 4 names BUILD_INFO as having `commit=<sha>`, `built_at=<UTC ISO>`, `built_by=<host>` as required lines AND an optional `relative_to_main=<state>` line where `<state>` is one of `ahead N`, `behind N`, `ahead N, behind M`. Verifiable: grep the doc for `relative_to_main` returns at least one hit naming the format and the three allowed states.

2. **VERSION shape clause reflects the new optional suffix.** The doc explicitly names that VERSION is `<sha>` when local HEAD matches `origin/main`, OR `<sha> (<state>)` when divergent (same `<state>` vocabulary as criterion 4). Verifiable: grep the doc for `(ahead` or `(behind` returns hits documenting the suffix.

3. **Criterion 5 latent-regression callout.** A new sub-bullet or paragraph under criterion 5 names that the deploy scripts' strict-equality check (`Workers.Version == ExpectedSha`) will fail when the dev workstation is ahead of `origin/main` at deploy time AND the target is a remote Windows worker (Linux containers bake VERSION at build via `--build-arg COMMIT_SHA` and don't re-stamp, so they're unaffected). The doc names the deferred fix (compare on bare-SHA prefix in `deploy-windows-worker.py`) and assigns it to a follow-up directive. Verifiable: grep the doc for "strict equality" OR "bare-SHA" returns hits naming the gap and the deferred fix.

4. **No behavior change shipped from this directive.** The shipped code (`Scripts/StampVersion.py`, `StartWorker.py`, `WorkerService/Main.py`) is NOT edited. Verifiable: `git diff main -- Scripts/ StartWorker.py WorkerService/ deploy/*.py` returns empty after this directive's commit.

## Out of Scope

- The actual fix for criterion 5's strict-equality regression (separate directive).
- Updating `WorkerService.flow.md` or other flow docs that reference VERSION shape — none confirmed via grep at start of this directive; if discovered during implementation, narrow this directive OR park as follow-up.
- Revising `2b69d30`'s commit message or amending the commit.

## Constraints

- Pure documentation change. No code, no schema, no settings.
- R14: don't add annotation lines (`deprecated`, `removed YYYY-MM-DD`, `previously`). Replace prose in place.

## Escalation Defaults

- Tradeoff: acknowledge gap vs. fix gap -> acknowledge. Reason: operator asked for doc catch-up; fix is a separate decision.
- Risk tolerance: low. Documentation only.

## Engineering Calls Already Made

- Documentation-only update. The strict-equality verification regression is latent (only fires when a remote Windows worker is deployed from a dev workstation ahead of main; there are zero remote Windows workers today). Calling it out in the doc is sufficient until someone wants to deploy REMINGTON.
- No promotion target outside the feature doc itself; this directive's content lives in `version-on-deploy.feature.md`.

## Status

Active 2026-06-02 -- phase: IMPLEMENTING -- standards already reviewed earlier this session; advancing straight to IMPLEMENTING (no new ancestor docs to read for the single file in scope).

Phases advance by editing this Status line: `**Status:** Active -- phase: <NEXT>`. The PreToolUse hook reads this line to gate tool calls.

### Files

```
deploy/version-on-deploy.feature.md   -- EDIT: criterion 4 + 5 + VERSION shape clause to match shipped 2b69d30 behavior
```

### Promotions

| Source artifact | Target file | Commit |
|---|---|---|
| Doc catch-up content for 2b69d30 | `deploy/version-on-deploy.feature.md` (the doc itself) | TBD until close |

### Verification

- **Criterion 1:** `grep -n 'relative_to_main' deploy/version-on-deploy.feature.md` returns one hit at line 44 naming the optional fourth line and the three allowed states.
- **Criterion 2:** `grep -nE '\(ahead|\(behind' deploy/version-on-deploy.feature.md` returns line 44 with literal examples `1073b8d (ahead 2)`, `2b69d30 (behind 5)`, `d7f993b (ahead 1, behind 3)`.
- **Criterion 3:** `grep -nE 'Known gap|bare-SHA' deploy/version-on-deploy.feature.md` returns line 48 naming both deploy scripts' line numbers (`deploy-windows-worker.py:422`, `deploy-linux-worker.py:358`), the latent-trigger conditions, and the deferred fix path (`Workers.Version.split()[0] == ExpectedSha`).
- **Criterion 4:** `git diff 2b69d30 -- Scripts/ StartWorker.py WorkerService/ deploy/deploy-linux-worker.py deploy/deploy-windows-worker.py | wc -l` returns 0 -- no code changes since commit 2b69d30.

### Decisions Made

- Included literal SHA examples in criterion 4 (`1073b8d (ahead 2)`, etc.) to make C2's grep verification actually match. Without concrete examples the doc only described the suffix abstractly via `(<state>)` placeholders and the grep returned empty.
- Latent-regression callout placed inline under criterion 5 (sub-paragraph) rather than as a new criterion. Reason: scope is doc catch-up for 2b69d30; promoting "fix the strict-equality check" to criterion-9 would conflate doc-catchup with future-fix authoring.
- Used backticks around concrete commit SHAs in the callout so grep + future readers can trace which commit introduced the gap.
