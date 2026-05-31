# Current Directive

**Set:** 2026-05-30
**Status:** Paused 2026-05-30 -- phase was IMPLEMENTING -- interrupted by nvenc-rate-anchored-remediation
**Slug:** ceo-mode-enforcement
**Replaces:** none (new directive)

## Outcome

Mechanical enforcement of MediaVortex coding standards via Claude Code hooks. When `.claude/directive.md` is non-empty, the session enters a phase state machine (`NEEDS_STANDARDS_REVIEW` -> `NEEDS_PLAN` -> `NEEDS_DOC_PREREAD` -> `IMPLEMENTING` -> `VERIFYING` -> `DELIVERING`); a `PreToolUse` hook refuses any `Edit`/`Write` tool call that fails phase gates or any of 15 named content rules. Standards violations the operator has paid tokens for in past sessions (hardcoded seed values, cached DB settings, env-var creep, multi-line comments, scope drift via new feature/flow docs, etc.) are caught at write-time, not at user-review-time. Result: ~70% reduction in token waste from "Claude knows the standard, ignores it, gets corrected, fixes it" loops.

## Acceptance Criteria

### A. Hooks installed and active

1. **Two hooks registered in `.claude/settings.json`**: `SessionStart` -> `.claude/hooks/session-start-ceo.ps1`, `PreToolUse` (matcher: `Write|Edit|MultiEdit`) -> `.claude/hooks/pre-edit-standards.ps1`. Verifiable: `Get-Content .claude/settings.json | ConvertFrom-Json | Select-Object -ExpandProperty hooks` returns both entries.

2. **Both hook scripts exist and are syntactically valid PowerShell.** Verifiable: `pwsh -NoProfile -Command "[scriptblock]::Create((Get-Content .claude/hooks/pre-edit-standards.ps1 -Raw))"` exits 0; same for `session-start-ceo.ps1`.

### B. Phase state machine

3. **`SessionStart` hook detects non-template directive.** When `.claude/directive.md` contains a `**Slug:**` line whose value is not empty and not the placeholder string `<previous-slug>`, the hook writes `.claude/.session-state.json` with `{"directive_slug": "<slug>", "phase": "NEEDS_STANDARDS_REVIEW", "session_started_at": "<ISO>"}` and emits the standards-review reminder via `additionalContext`. Verifiable: simulate by invoking the hook with a non-empty directive.md; the JSON file is created with expected shape.

4. **Phase exit gates enforced by `PreToolUse` hook.** For each phase, the hook reads `.claude/.session-state.json` and the session transcript, applies the exit criterion below, and refuses or allows the tool call accordingly. Verifiable: per-phase contract tests under `.claude/hooks/Tests/` simulate transcripts and assert allow/deny.

   | Phase | Exit criterion | Tools allowed |
   |---|---|---|
   | `NEEDS_STANDARDS_REVIEW` | Transcript shows `Read` of every `.claude/rules/*.md` and `.claude/standards/index.md` | Read/Grep/Glob/Bash (read-only) |
   | `NEEDS_PLAN` | Directive doc edited; its Status line names a phase; criteria list non-empty | Read/Grep/Glob/Bash/Write (directive doc only) |
   | `NEEDS_DOC_PREREAD` | Transcript shows `Read` of any `*.feature.md` / `*.flow.md` ancestors of files the plan touches | Read/Grep/Glob/Bash; Write directive doc only |
   | `IMPLEMENTING` | All content rules pass on every Edit/Write | All tools, gated by content rules |
   | `VERIFYING` | Plan's verification section records evidence per criterion | Read/Grep/Bash; Edit directive doc only |
   | `DELIVERING` | Delivery report drafted in directive doc Status | All tools |

5. **Phase advances via explicit marker write to directive doc.** The directive doc's `**Status:** Active -- phase: <PHASE>` line is the source of phase truth. The hook reads it; if it differs from `.session-state.json`, the hook validates the new phase's entry preconditions before updating state. A phase skip (e.g., jumping `NEEDS_PLAN` -> `IMPLEMENTING`) is refused. Verifiable: edit Status line to a downstream phase without satisfying intermediate exits; hook refuses the Write.

### C. Content rules (15, all included now)

6. **Rule R1 (Doc preread)**: Edit/Write to any `.py` / `.js` / `.html` / `.sql` whose SAME-DIRECTORY `*.feature.md` or `*.flow.md` has not been Read this session -> refuse. Same-directory only -- no walk-up to repo root. If a colocated doc does not exist, the rule does not fire. Verifiable: simulate edit of `Features/X/foo.py` where `Features/X/X.feature.md` exists but has not been Read; hook refuses. Edit of `Models/foo.py` with no colocated doc; hook allows.

7. **Rule R2 (Seed evidence)**: Write to any `Scripts/SQLScripts/Add*.py` whose INSERT statements contain numeric literals not annotated with `# from: <path>[:<line>]` on the same or adjacent line -> refuse. Cited `<path>` must exist; cited file must contain a literal-match for the value. Verifiable: write a seed script with `INSERT ... VALUES (30)` and no comment; hook refuses. Add `# from: docs/canary.md`; hook refuses because docs/canary.md doesn't exist. Create the file with `30` in it; hook allows.

8. **Rule R3 (No cached settings)**: Edit/Write to `**/Services/**`, `**/Repositories/**`, or `Features/**/*Service.py` whose `__init__` assigns to `self._cached_*`, `self._*_settings`, or `self._config_snapshot` -> refuse. Verifiable: write a service with `self._cached_thresholds = ...` in `__init__`; hook refuses.

9. **Rule R4 (No env vars outside bootstrap)**: Edit/Write to any `.py` containing `os.environ.get(` or `os.getenv(` outside `Core/Database/DatabaseService.py`, `StartMediaVortex.py`, `StopMediaVortex.py`, `WebService/Main.py` bootstrap section, and worker `Main.py` bootstrap section -> refuse. Verifiable: add `os.environ.get('FOO')` in a Features/ file; hook refuses.

10. **Rule R5 (ExecuteQuery misuse)**: Edit/Write containing `ExecuteQuery(` whose argument string matches `^\s*(INSERT|UPDATE|DELETE)\s` (case-insensitive) -> refuse. Verifiable: write `Db.ExecuteQuery("UPDATE Foo SET ...")`; hook refuses.

11. **Rule R6 (Path-shape laxity)**: Edit/Write where any variable whose name matches `(?i)path|filepath` is consumed by `.replace(.*).split(` or `os.path.(dirname|basename|join|split)\(` -> refuse. Verifiable: write `filepath.replace('\\\\','/').split('/')`; hook refuses.

12. **Rule R7 (Polymorphic FK CASCADE)**: Edit/Write to `Scripts/SQLScripts/*.py` containing `ON DELETE CASCADE` within an `ALTER TABLE` or `CREATE TABLE` referencing column names `QueueId|JobId|EntityId|TargetId` -> refuse. Verifiable: write an `ALTER TABLE ActiveJobs ADD FOREIGN KEY (QueueId) REFERENCES TranscodeQueue(Id) ON DELETE CASCADE`; hook refuses.

13. **Rule R8 (Test placement)**: Write to a path matching `test_*.py` or `Test*.py` outside `Tests/Contract/` and `Tests/Unit/` -> refuse. Verifiable: try `Write` to `Features/Foo/test_foo.py`; hook refuses.

14. **Rule R9 (LIKE without EscapeLikePattern)**: Edit/Write whose content includes `LIKE %s` or `LIKE '%' || %s || '%'` patterns in a function body that does not contain `EscapeLikePattern(` -> refuse. Verifiable: write a repository function using `LIKE %s ESCAPE` without calling `EscapeLikePattern`; hook refuses.

15. **Rule R10 (Claim-query bypass)**: Edit/Write to `Repositories/**/*.py` defining a function whose name starts with `Claim` and whose body contains `EXISTS (SELECT 1 FROM Workers` without importing `BuildClaimPredicate` at module top -> refuse. Verifiable: write a `ClaimXyzJob` function with a hand-rolled Workers EXISTS clause; hook refuses.

16. **Rule R11 (Migration idempotency)**: Edit/Write to `Scripts/SQLScripts/*.py` containing `CREATE TABLE` without `IF NOT EXISTS`, `ALTER TABLE` without `IF EXISTS` (for drops/renames), `CREATE INDEX` without `IF NOT EXISTS`, or `INSERT INTO` without `ON CONFLICT` -> refuse. Verifiable: write `CREATE TABLE Foo (...)`; hook refuses. Add `IF NOT EXISTS`; hook allows.

17. **Rule R12 (Comment volume)**: Edit/Write to any `.py` containing a consecutive `#` comment block longer than 1 line, any `"""..."""` docstring spanning > 1 line, or any module-level docstring -> refuse. Verifiable: write a function with a 3-line `#` comment block; hook refuses.

18. **Rule R13 (New feature/flow docs)**: Write to a non-existent path matching `*.feature.md` or `*.flow.md` -> refuse with pointer to use the directive doc instead. Verifiable: try Write to `Features/NewFeature/foo.feature.md`; hook refuses.

19. **Rule R14 (Annotation drift)**: Edit to existing `*.feature.md` or `*.flow.md` whose diff ADDS lines matching `removed \d{4}-\d{2}-\d{2}|deprecated|no longer used|previously |formerly ` -> refuse with the deletion-not-annotation message. Verifiable: edit an existing feature.md to add a "removed 2026-05-30" line; hook refuses.

20. **Rule R15 (Directive anchor)**: Edit/Write to a `.py` file listed in the directive doc's `## Files` section, modifying a function/class definition, without `# directive: <slug>` on the line immediately above the `def`/`class` -> refuse. Verifiable: edit a function in a directive-listed file without the anchor comment; hook refuses.

### D. Override mechanism

21. **`# allow: <reason>` suppresses one check.** A line containing `# allow: <reason>` within 3 lines of the offending pattern suppresses the specific rule firing on that pattern. Reason must be non-empty. Every suppression is appended to `.claude/.standards-overrides.log` as a single JSON line: `{"ts": "<ISO>", "rule": "<Rn>", "file": "<path>", "line": <n>, "reason": "<text>"}`. Verifiable: include `# allow: bootstrap shim` next to an `os.environ.get(`; R4 does not fire; log file has the entry.

### E. Standards index

22. **`.claude/standards/index.md` enumerates every gated rule**, with: rule ID (R1-R15), one-line description, source rule doc (link to `.claude/rules/*.md` or memory file), hook function name. The hook's refusal messages cite this file. Verifiable: every R1-R15 has an entry; every entry points to an existing source.

### F. Existing rule and memory cleanup

23. **`.claude/rules/ceo-mode.md` subsection "Spell out what the new state ISN'T" is deleted.** Replaced by: "When a directive removes a capability, delete the describing section or file. Do not annotate with 'removed YYYY-MM-DD' lines; the hook (R14) refuses such Edits." Verifiable: grep for "Spell out what the new state ISN'T" in `.claude/rules/ceo-mode.md`; zero matches.

24. **MEMORY.md superseded entries removed.** The entries for `feedback_no_verbose_code_comments`, `feedback_ceo_mode_documents_first`, `feedback_no_cached_db_settings`, `feedback_data_driven_settings` are deleted from the index AND their target files deleted. Replaced by one pointer line at the top: `- [Standards are mechanically enforced](.claude/standards/index.md) — see .claude/hooks/pre-edit-standards.ps1; the hook is authoritative.` Verifiable: those four memory filenames do not exist; the pointer entry exists in MEMORY.md.

### G. .gitignore

25. **`.claude/.session-state.json` and `.claude/.standards-overrides.log` are gitignored.** Verifiable: `git status` shows neither file after the hook writes them.

## Out of Scope

- Judgment-call standards: scope drift ("while I'm here"), feature-criteria litmus tests, semantic doc accuracy. Hook cannot catch these.
- Migration of existing `*.feature.md` / `*.flow.md` files to the directive-doc model. They stay until a future directive touches their code.
- A Linux (`.sh`) companion hook script. PowerShell is sufficient for the current Claude Code host (Windows i9).
- Backfilling `# directive: <slug>` anchors into existing code. Anchors are required only when this or a future directive touches the function/class.
- A CI-side check that mirrors the hook. The hook is a write-time gate; CI is a separate problem.

## Constraints

- Hook must not block Read/Grep/Glob in any phase except where explicitly noted. Discovery must remain cheap.
- Hook failure modes (script error, missing pwsh, JSON parse fail) MUST emit a `permissionDecision: "ask"` payload, not silently allow. Better to prompt the user than skip enforcement.
- Override log is append-only. Hook never rewrites it.
- All file paths in hook output use forward slashes for cross-quote-shell safety.

## Escalation Defaults

- Tradeoff between false-positive refusals and false-negative allows -> prefer false-positive (refuse). User can `# allow:` override; silent miss is invisible.
- Tradeoff between strict regex and tolerant regex -> strict. R12-R15 are content checks where ambiguity is the failure mode.
- Risk tolerance: low (this is the safety net; the safety net failing silently is the worst outcome).

## Engineering Calls Already Made

- Phase tracking in JSON file (`.claude/.session-state.json`), not in directive doc. Directive doc Status line is the operator-readable narrative; JSON is the machine-readable authority.
- One hook script, not 15. Rules are functions inside one PowerShell file. Adding rule N+1 is one function append; no settings.json edits.
- `# allow: <reason>` is the only override; no global disable, no per-rule disable, no `# noqa`-style multi-rule. Force operators to name the reason every time.
- Override log is gitignored. Pattern-of-use is informational, not a permanent audit; deleting periodically is fine.
- Existing `*.feature.md` / `*.flow.md` files keep their doc-preread gate (R1) until they're migrated. Forbidding NEW ones (R13) is the forward-going rule; cleanup is opportunistic.

## Status

Active 2026-05-30 -- phase: IMPLEMENTING -- writing hook scripts.

### Files

```
.claude/directive.md                    -- THIS doc (the directive + plan + status)
.claude/standards/index.md              -- NEW: rule registry, hook citations
.claude/hooks/pre-edit-standards.ps1    -- NEW: PreToolUse hook (15 rules + phase gate)
.claude/hooks/session-start-ceo.ps1     -- NEW: SessionStart hook (phase init)
.claude/settings.json                   -- NEW: hook registration (or extend settings.local.json)
.claude/rules/ceo-mode.md               -- EDIT: delete "Spell out what the new state ISN'T" section
.gitignore                              -- EDIT: add .session-state.json + .standards-overrides.log
MEMORY.md (user memory)                 -- EDIT: prune superseded entries; add hook pointer
```

### Verification (filled during VERIFYING phase)

Per criterion -- to be recorded here when each one passes.

### Closure

Closure is gated on completion of all 25 criteria + the doc supersession sweep per `.claude/rules/ceo-mode.md`.
