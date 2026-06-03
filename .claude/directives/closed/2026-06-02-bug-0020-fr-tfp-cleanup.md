# Current Directive

**Set:** 2026-06-02
**Status:** Closed -- Abandoned
**Closed:** 2026-06-02
**Slug:** bug-0020-fr-tfp-cleanup
**Replaces:** `directives/closed/2026-06-02-bug-0020-worker-ownership.md` (closed Partial -- C3 follow-up named there)

## Outcome

Every terminal exit from `FileReplacementBusinessService.ProcessFileReplacement` -- success OR failure -- deletes the attempt's `TemporaryFilePaths` row before returning. After this directive lands, the orphan-cleanup safety-net sweep for TFP rows finds zero candidates on a fresh fleet pass for any attempt whose worker is alive, and the `FileReplacement` feature doc's criterion C12 ([BUG-0010]) flips from OPEN to MET.

## Acceptance Criteria

1. `FileReplacementBusinessService.ProcessFileReplacement` deletes the attempt's `TemporaryFilePaths` row on every terminal return path, not only the success branch. Verifiable: induce each non-success exit path (transcode_attempt missing, transcoded file missing on disk, size-guard refusal, archive failure, `_ProcessCompleteFileReplacement` returning `Success=False`, top-level exception) and observe `SELECT COUNT(*) FROM TemporaryFilePaths WHERE TranscodeAttemptId=<id>` returns 0 by the time the function returns.

2. The cleanup is structural (single chokepoint), not duplicated. Either `_CleanupTemporaryFilePaths` is called from a `finally` block in `ProcessFileReplacement`, OR every non-success path re-dispositions through `PostTranscodeDispositionService._CommitDisposition` (which already owns terminal-state TFP cleanup for Discard/NoReplace/Requeue). Verifiable: grep shows exactly one cleanup-emitting site per terminal path; no per-branch `_CleanupTemporaryFilePaths(...)` calls sprinkled into early returns.

3. Cleanup is idempotent and safe when the TFP row is already gone. Verifiable: invoke the chokepoint twice for the same `AttemptId`; the second call returns without raising and without emitting an error-level log line.

4. `FileReplacement.feature.md` C12 ([BUG-0010]) is updated from OPEN to MET with a one-line evidence reference (commit + the test/SQL that demonstrates per-path cleanup). The feature doc's Status block reflects the change.

## Out of Scope

- Refactoring `_ProcessCompleteFileReplacement`'s return shape into a richer disposition object (would touch the worker hot path; out of scope for a cleanup-routing fix).
- The OrphanCleanupService liveness-gated sweep -- already shipped in `a5d9a9e` under the predecessor directive; this directive only fixes the FR-internal leak paths.
- Operator-side criterion C5 of BUG-0020 (zero-candidate fleet pass) -- operator-runnable; covered separately when the deploy lands.
- Touching MediaFiles persistence (C14 / BUG-0021) -- separate vertical.

## Constraints

- One commit per criterion when criteria correspond to distinct edits. C1+C2+C3 likely collapse to a single structural edit; C4 is a docs-only commit.
- No service restart authorization implied; deploy step is operator's call.
- Do not introduce a new disposition value or change `_CommitDisposition`'s contract -- if the structural choice is "route through dispositioner," the existing dispositions cover the cases.
- R12: no multi-line comments / docstrings added during the edit. One-line `# directive: bug-0020-fr-tfp-cleanup` anchor above each touched function.

## Escalation Defaults

- Tradeoff "finally-block in ProcessFileReplacement" vs "re-disposition through `_CommitDisposition`" -> **finally-block**, because the failure paths today already log + return cleanly; routing them through dispositioner would change observable disposition rows for paths that currently emit none, expanding scope.
- Risk tolerance: low (touches a function on the post-encode hot path; failure modes are visible to the next sweep).

## Engineering Calls Already Made

- The C3 follow-up was deliberately deferred from the parent directive when hook state (R1 anchored-section recognition) became uncooperative; the parent's Decisions Made line documents that the right move was to reopen with a fresh session rather than fight the gate. This directive is that fresh session.
- Vertical home: `Features/FileReplacement/`. The leak lives inside `FileReplacementBusinessService.ProcessFileReplacement`; the feature doc that owns the contract (C12) is `Features/FileReplacement/FileReplacement.feature.md`. Slug `bug-0020-fr-tfp-cleanup` matches both the parent directive's named follow-up slug and the vertical it touches.
- The chokepoint already exists for the success branch at `FileReplacementBusinessService.py:217-225`; the structural fix is moving the call up into a `finally` so it covers every terminal exit.

## Status

Active 2026-06-02 -- phase: NEEDS_STANDARDS_REVIEW -- awaiting operator to advance to NEEDS_PLAN.

Phases advance by editing this Status line: `**Status:** Active -- phase: <NEXT>`. The PreToolUse hook reads this line to gate tool calls. See `.claude/standards/index.md` for the phase machine.

### Files

```
Features/FileReplacement/FileReplacementBusinessService.py    -- EDIT: try/finally TFP cleanup around ProcessFileReplacement (C1, C2, C3)
Features/FileReplacement/FileReplacement.feature.md           -- EDIT: flip C12 from OPEN to MET; update Status block (C4)
```

### R1 preread surface (acknowledged upfront)

`FileReplacementBusinessService.py` has FOUR colocated feature docs. R1 requires each be Read (full or anchored-partial) once per session before any Edit. Plan accounts for this:

- `FileReplacement.feature.md` (95 lines) -- partial-read via offset; contains C12 (the criterion this directive flips). R18 override declared below.
- `post-transcode-pipeline.feature.md` -- partial-read; contains C15 (terminal-state TFP cleanup contract; documents the `_CommitDisposition` chokepoint pattern this directive's finally-block complements).
- `remuxed-flag.feature.md` -- partial-read; out of scope but R1-required.
- `transcoded-output-placement.feature.md` -- partial-read; out of scope but R1-required.

All four are now Read in this session (state established). No further preread cost for this directive.

### R18 overrides

- `Features/FileReplacement/FileReplacement.feature.md` (95 lines; DELIVERING-time C12 + Status block edit needs the full doc in scope)

### Promotions

| Source artifact | Target file | Commit |
|---|---|---|
| no promotions | n/a | abandoned -- architecture pivot; the try/finally workaround was symptomatic. `_CleanupTemporaryFilePaths` belongs in `PostTranscodeDispositionService._CommitDisposition` per `post-transcode-pipeline.feature.md` C15. Superseded by `filereplacement-decompose`, which makes the relocation literal. |

### Verification

(populated at VERIFYING)

### Decisions Made

(populated during execution)
