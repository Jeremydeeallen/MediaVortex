# Backlog Directive: R1 Hook -- subagent transcript visibility

**Filed:** 2026-06-04 (by `paths-canonical-completion` close-out)
**Status:** Backlog -- not yet started
**Slug:** r1-subagent-transcript-fix
**Triggered by:** During `paths-canonical-completion` (2026-06-03) sweep, 4 of 23 parallel subagents blocked on R1 doc-preread refusals despite having done the correct full Reads of colocated feature/flow docs in their own subagent sessions. The R1 hook's `Get-ReadFilesFromTranscript` reads only the parent session's transcript file, not the subagent's. Symptoms: subagent runs `Read(target.feature.md, limit=50)` 3+ times, then `Edit(target.py)` -- hook refuses with "target.feature.md has not been Read this session." Affects every parent-orchestrated parallel-agent dispatch where R1 applies (i.e., any code-edit agent). Cost during BUG-0042: 4 file migrations had to be re-handled in the parent session, adding ~20 minutes + agent token waste.

## Outcome

R1 hook detects Read tool calls made by subagents, not just the parent session. Future parallel-agent dispatches that need to edit code with colocated feature/flow docs work end-to-end inside the subagent, without forcing the parent to handle the Edit. The "Reads in subagent are invisible to R1" gap is closed.

## Acceptance Criteria

1. The R1 hook's `Get-ReadFilesFromTranscript` function (currently in `.claude/hooks/pre-edit-standards.ps1`) reads the subagent transcript file when the current Edit/Write is initiated from inside a subagent. The subagent transcript path is discoverable from the hook's invocation context (likely `CLAUDE_TASK_OUTPUT_FILE` env var or similar -- needs investigation; the path observed during BUG-0042 was `C:\Users\jerem\AppData\Local\Temp\claude\C--Code-MediaVortex\<session-id>\tasks\<agent-id>.output`).

2. A live test: spawn a one-file-migration subagent that Reads a colocated `*.feature.md` then Edits the Python file in the same directory; the Edit succeeds without R1 refusal.

3. The hook continues to work for non-subagent (parent-session) edits -- no regression on the existing transcript-parsing path.

4. The hook does not double-credit Reads (parent session Reads still count; subagent Reads also count; no infinite loop on session ancestry).

5. If subagent transcript discovery is genuinely impossible from the hook's invocation context (operator-confirmed after investigation), the fallback is: extend R1 to also accept a `# see <feature-or-flow-slug>.<ID>` anchor on the Edit line itself as a substitute preread proof (anchored partial-read mode that doesn't require the hook to verify the subagent's Read history). Verifiable: subagent that adds `# see <slug>.C<N>` above its edit line succeeds without R1 refusal.

## Out of Scope

- Fixing R1 to be MORE permissive in general -- the rule's intent (colocated docs Read before code Edit) is correct. This directive only fixes the subagent visibility gap.
- Cross-session Read crediting -- if Claude is restarted between Read and Edit, the Read shouldn't count. Same-session-or-subagent only.
- Refactoring R1 to use a different mechanism (e.g. a session-scoped JSON record of Reads). The current transcript-grep approach works for parent sessions; extending it is enough.

## Reference

Parent directive (closed): `.claude/directives/closed/2026-06-03-paths-canonical-completion.md` -- Decisions Made section notes the friction.
Files affected (during BUG-0042): SystemSettingsController.py, QueueManagementBusinessService.py, TranscodedOutputPlacement.py, ComplianceGate.py -- all had to be migrated in the parent session because subagent Reads weren't visible.
Hook source: `.claude/hooks/pre-edit-standards.ps1` `Get-ReadFilesFromTranscript` (search for the function name in the file).

## Investigation First

This directive starts with a 30-minute investigation phase: read `Get-ReadFilesFromTranscript`, identify the parent-transcript-only assumption, then decide between (a) walking subagent transcript files via known temp-dir paths, (b) checking an env var for the current transcript path that gets set differently for subagents, or (c) the fallback `# see` anchor route. Operator picks the implementation path; the criteria above are written to accept any of the three.
