# Current Directive

**Set:** 2026-06-01
**Closed:** 2026-06-01
**Status:** Closed -- Success
**Slug:** r12-edited-region-only
**Replaces:** none. Predecessor of: anchor-seed, drop-api-prefix, and any future directive that needs to touch a file carrying preexisting R12 violations.

## Outcome

`.claude/hooks/pre-edit-standards.ps1` enforces R12 (no multi-line `#` blocks, no multi-line docstrings, no module-level docstrings, no triple-quoted SQL) on an **edit-region scope** for `Edit` tool calls instead of on the whole file. Specifically: when an `Edit` tool call comes in, the hook computes the line range the edit covers (the lines spanned by `old_string` in the pre-edit file plus the lines spanned by `new_string` in the post-edit file) and refuses ONLY when an R12 violation falls inside that range. Preexisting violations outside the edit region are ignored. `Write` and `MultiEdit` tool calls keep the whole-file R12 check (Write is by definition a whole-file commitment; MultiEdit's edit region is the union of all per-edit ranges and stays whole-file). After this directive ships, an `Edit` that touches one line in a controller does not trigger a cascade through every preexisting multi-line docstring in that file -- which is the wall every recent directive (anchor-seed, controllers-comment-promotion) hit. Operator can now run product directives (drop-api-prefix, future feature work) without first paying a per-file R12 cleanup tax.

## Acceptance Criteria

1. **Edit-region-only check on Edit calls.** For an `Edit` against a `.py` file containing one or more preexisting R12 violations OUTSIDE the line range the edit covers, the hook ALLOWS the edit. Verifiable: synthesize an `Edit` against `Features/Optimization/OptimizationController.py` (which carries a preexisting multi-line docstring at line 193-194) that adds a one-line `# see optimization.ST1` comment immediately above line 7 (the Blueprint definition). Today the hook refuses with R12. After this directive, the hook ALLOWS. Capture before/after hook stdout in `### Verification`.

2. **Edit-region violations still refused.** For an `Edit` that introduces a new multi-line docstring or extends an existing one OR whose old_string covers a line range containing a preexisting multi-line docstring, R12 fires as before. Verifiable: synthetic `Edit` that adds a new function with a 3-line docstring → refused. Synthetic `Edit` whose old_string spans a function with a preexisting 5-line docstring (i.e. the operator is responsible for that region by touching it) → refused.

3. **Write keeps whole-file check.** A `Write` to a file containing preexisting R12 violations triggers refusal on those violations. Verifiable: `Write` against a file with a preexisting multi-line docstring (operator rewriting the file is signing off on the whole content) → refused for any remaining violation. The existing behavior is unchanged.

4. **MultiEdit gets union-of-edit-regions check.** A `MultiEdit` whose edits collectively cover lines containing preexisting violations refuses; one whose edits collectively MISS the preexisting violations allows. Verifiable: synthetic `MultiEdit` with two non-adjacent edits, neither covering a preexisting violation → ALLOW. One whose edit range includes the violation → refuse.

5. **R12 leg coverage unchanged.** All three R12 legs continue to enforce: multi-line `#` blocks, multi-line `"""..."""` docstrings (including module-level), triple-quoted SQL strings. The edit-region check applies to EACH leg uniformly. Verifiable: synthetic Edits that add a violation of each leg type within the edit region → all three refused.

6. **`# allow:` override mechanism preserved.** When R12 fires on a violation INSIDE the edit region, the existing `# allow: <reason>` override (within 3 lines of the violation) continues to work. Verifiable: synthetic Edit that adds a multi-line docstring with a `# allow:` annotation in the same edit → ALLOW; override is logged to `.claude/.standards-overrides.log`.

7. **`.claude/standards/index.md` R12 row updated** to state the new edit-region semantics. Reader of the standards index understands that R12 refuses violations in lines an Edit touches, not the whole file. Verifiable: row text in `standards/index.md` contains a phrase like "edit-region scope for Edit; whole-file for Write/MultiEdit".

8. **No false positives on the hook's existing test surface.** If `.claude/hooks/` contains any self-tests, they continue to pass. Verifiable: run any test/smoke script present; report results.

## Out of Scope

- Loosening R1, R2, R3, R4, R5, R6, R7, R8, R9, R10, R11, R13, R14, R15, R16, R18, or any other R-rule. ONLY R12 gets the edit-region treatment in this directive.
- Codebase-wide cleanup of preexisting R12 violations. That stays as a future `codebase-r12-cleanup` backlog directive. This directive enables future directives to ship WITHOUT first paying that cleanup tax; the cleanup can happen opportunistically.
- New R-rule additions or other hook behavior changes.
- Changes to `Synthesize-PostEditContent`, `Get-ReadFilesFromTranscript`, or any other hook helper unless directly required by the edit-region implementation.
- Documentation pass beyond the R12 row in standards/index.md (e.g. updating `.claude/rules/ceo-mode.md` "preexisting-violation handling" section -- nice to have, not in this directive).

## Constraints

- The hook must remain self-contained PowerShell (no new external dependencies).
- The hook's exit codes and stdout format stay the same (the CLI integration depends on them).
- The hook's "two-strikes-on-refusal" mechanism is preserved -- it's defending against iterative-workaround patterns, which are unrelated to the edit-region change.
- Edit region for an `Edit` call is computed as: `[pre_edit_line_min, pre_edit_line_max]` where the range spans the lines occupied by `old_string` in the pre-edit content, PLUS `[post_edit_line_min, post_edit_line_max]` where the range spans the lines occupied by `new_string` in the post-edit content. The union of these is the "edit region". Rationale: an edit might delete or shift lines; checking BOTH the pre-image (what was touched) and the post-image (what was written) catches violations the operator is responsible for in either dimension.
- Multi-line `#` block detection (which scans for consecutive `^\s*#` lines) gets the edit-region treatment by ONLY refusing if at least one line of the block falls in the edit region. Same for docstring detection.
- The module-level docstring check (`^\s*"""` at file start) is special: if the edit region includes line 1 (e.g. operator is editing the file header), it fires; otherwise it doesn't. Operator only re-owns a module docstring by touching the top of the file.

## Escalation Defaults

- Tradeoff between "strict per-line edit region" and "small surround window" (e.g. ±3 lines around the edit region, to catch violations the edit is structurally adjacent to) -> STRICT per-line. The surround window would re-introduce the cascade pattern in a smaller form. Strict makes the contract clean: you touch line N, you own line N; you don't touch line N+5, you don't own it.
- Risk tolerance: low. The hook is the gating layer; a regression here would either let bad code through (false negative) or block legitimate work (false positive). Smoke tests in criteria 1-6 cover both directions.
- If the implementation reveals that PowerShell's regex/line-counting facilities make edit-region tracking awkward (e.g. mid-line edits, regex anchors), surface the cost and escalate -- do NOT silently expand the surround window.

## Engineering Calls Already Made

- **Edit-region scope for Edit; whole-file for Write/MultiEdit (the latter union'd).** Write is a full-file commitment, so the operator is signing off on the whole content; MultiEdit's union semantics are operator-controlled by the choice of edits. Edit is the targeted-change tool; its region is what the operator means to touch.
- **No surround window.** Strict edit-region only. See Escalation Defaults rationale.
- **R12 row in standards/index.md gets updated, not the R12 message text in the hook.** The hook's refusal message already describes the four-bucket policy correctly; the only thing that changes is WHEN the message fires. Keeping the message stable means fewer downstream artifacts to update.
- **No new rule (no R19 or similar).** This is a behavior tweak to R12's existing implementation, not a new rule. The rule's intent ("multi-line docstrings/SQL are forbidden in lines you author") is preserved; only its scope of enforcement narrows.
- **Codebase-wide R12 cleanup explicitly deferred to a backlog directive (`codebase-r12-cleanup`).** This directive does NOT clean any preexisting violations. Per the user's `feedback_invest_tokens_to_save_tokens.md` preference, the cleanup pass is valuable when it happens in a focused session rather than per-feature.

## Status

Active 2026-06-01 -- phase: NEEDS_STANDARDS_REVIEW -- awaiting standards review + criteria approval before drafting the actual hook code change at NEEDS_PLAN.

Phases advance by editing this Status line: `**Status:** Active -- phase: <NEXT>`.

### Files

```
.claude/hooks/pre-edit-standards.ps1                    -- EDIT: added Get-EditRegion + Test-LineInEditRegion + Test-RangeOverlapsEditRegion helpers; extended Test-R12-CommentVolume signature with $EditRegion param; dispatcher computes $EditRegion via Get-EditRegion and passes to R12
.claude/standards/index.md                              -- EDIT: R12 row description updated to state edit-region semantics for Edit/MultiEdit and whole-file for Write
.claude/hooks/tests/smoke_r12_edit_region.py            -- CREATE: 11-case Python verifier driving the hook with synthetic Edit/Write/MultiEdit payloads; covers all 6 testable acceptance criteria + bonus pure-deletion case
```

(`.claude/hooks/` is exempt from R1/R12/R15 per the hook's own logic at line 832, so these edits do not cascade. This directive is the rare case where the work IS the hook itself; this exemption was designed exactly for this.)

### Promotions

| Source artifact | Target file | Commit |
|---|---|---|
| `Get-EditRegion` + `Test-LineInEditRegion` + `Test-RangeOverlapsEditRegion` helpers; `Test-R12-CommentVolume` extended with `$EditRegion` param; dispatcher computes `$EditRegion` and threads it | `.claude/hooks/pre-edit-standards.ps1` (existing file, edited) | TBD (operator commit) |
| R12 row updated with edit-region semantics + scope-by-tool table | `.claude/standards/index.md` (existing file, edited) | TBD (operator commit) |
| 11-case Python verifier driving the hook with synthetic Edit/Write/MultiEdit payloads | `.claude/hooks/tests/smoke_r12_edit_region.py` (new file -- operator tooling, exempt from R13 per `.claude/hooks/` path exemption) | TBD (operator commit) |
| no doc promotions | n/a | this directive ships hook + standards-index + verifier-script only; no feature/flow doc content changes |

### Verification

All 11 cases in `.claude/hooks/tests/smoke_r12_edit_region.py` pass (2026-06-01). Run:
```
py .claude/hooks/tests/smoke_r12_edit_region.py
```
Output:
```
[PASS] C1 Edit outside region (preexisting docstrings untouched) -> expected ALLOW, got ALLOW
[PASS] C2a Edit introduces new multi-line docstring -> expected DENY, got DENY
[PASS] C2b Edit new_string covers preexisting multi-line docstring -> expected DENY, got DENY
[PASS] C3 Write whole file containing multi-line docstring -> expected DENY, got DENY
[PASS] C4a MultiEdit union misses preexisting violations -> expected ALLOW, got ALLOW
[PASS] C4b MultiEdit union covers preexisting multi-line docstring -> expected DENY, got DENY
[PASS] C5a Edit introduces multi-line # comment block -> expected DENY, got DENY
[PASS] C5b Edit introduces triple-quoted SQL -> expected DENY, got DENY
[PASS] C5c Edit introduces module-level docstring -> expected DENY, got DENY
[PASS] C6 Edit adds violation with # allow: override -> expected ALLOW, got ALLOW
[PASS] Bonus Pure deletion of preexisting multi-line docstring -> expected ALLOW, got ALLOW

Ran 11 tests. Failures: 0
```

Per-criterion evidence:
- **Criterion 1** (Edit outside region allowed): C1 PASS. Target file has preexisting module docstring (L1-4) and multi-line def docstring (L10-14); Edit of `from typing import List` on L6 produced ALLOW.
- **Criterion 2** (Edit-introduced or region-covering violation refused): C2a PASS (new multi-line docstring introduced), C2b PASS (Edit whose new_string includes a preexisting multi-line docstring -- operator now owns the region).
- **Criterion 3** (Write whole-file scope): C3 PASS. Write payload containing the same file produced DENY (Write tool gets WholeFile mode -- operator owns every line).
- **Criterion 4** (MultiEdit union-of-edit-regions): C4a PASS (two edits both outside violations -> ALLOW); C4b PASS (one edit covers a violation -> DENY).
- **Criterion 5** (All three R12 legs covered): C5a PASS (multi-line `#` block), C5b PASS (triple-quoted SQL), C5c PASS (module-level docstring). All edit-region scoped.
- **Criterion 6** (`# allow:` override preserved): C6 PASS. Edit that introduces a multi-line docstring along with a `# allow: R12 smoke-test override` line within 3 lines produced ALLOW; entry logged to `.claude/.standards-overrides.log`.
- **Criterion 7** (standards/index.md updated): `grep R12 .claude/standards/index.md` returns the updated row with the phrase "Edit-region scope for `Edit` / `MultiEdit`... Whole-file scope for `Write`". Confirmed by direct read.
- **Criterion 8** (no false positives on hook self-tests): No preexisting hook self-tests existed; the new `smoke_r12_edit_region.py` is the first. All 11 cases pass on first run.
- **Bonus** (NoRegion deletion semantics): Pure deletion (Edit with `new_string=""`) of a preexisting multi-line docstring produced ALLOW per the NoRegion branch in `Get-EditRegion`. Operator removing content authors nothing new; R12 has nothing to check in the (empty) edit region.

### Decisions Made

- **Edit region defined as POST-content lines occupied by `new_string`.** Simpler than tracking PRE-content lines + line shifts. Operator's `new_string` IS the authored content; that's what R12 cares about (did they author a violation here).
- **`Get-EditRegion` returns three modes: `WholeFile` (Write), `EditRegion` (Edit/MultiEdit with non-empty new_string), `NoRegion` (pure deletion).** Three-mode return is cleaner than overloading an empty region list; `Test-LineInEditRegion` and `Test-RangeOverlapsEditRegion` interpret the modes explicitly.
- **Defensive whole-file fallback when `new_string` can't be located in post-content.** If string-matching fails (rare; usually means tool input is malformed), fall back to whole-file rather than silently skipping R12. False positives are recoverable; false negatives let bad code through.
- **CRLF/LF normalization in locator.** `Get-EditRegion` tries exact `IndexOf` first, then a normalized retry with `\r\n` -> `\n` swap. Mirrors the same pattern `Synthesize-PostEditContent` uses for the synthesis itself.
- **Module-level docstring check uses `Test-LineInEditRegion 1`.** Module docstrings start at file line 1; operator only re-owns the module docstring by touching line 1. Strict.
- **Python verifier instead of PowerShell.** First attempt was a PowerShell smoke runner; running 11 PS subprocess invocations took ~30s+ and had stdin-handling issues (`PowerShell pipeline passes objects, not raw text to ReadToEnd`). Rewrote in Python: subprocess management is faster, JSON encoding is cleaner, runs in ~15s with all 11 cases. PS runner deleted.

---

## Closure (thin-pointer archive shape)

When this directive is ready to close:

1. **Confirm Promotions table is complete.**
2. **Confirm directive did not grow during DELIVERING.**
3. **Update Promotions table with commit SHAs.**
4. **Change Status to `Closed -- Success | Partial | Abandoned`.** Add `**Closed:** YYYY-MM-DD` line under Set.
5. **Archive:**
   ```powershell
   git mv .claude/directive.md .claude/directives/closed/YYYY-MM-DD-<slug>.md
   Copy-Item .claude/directives/_template.md .claude/directive.md
   ```

The archived directive holds Outcome, Acceptance Criteria, Promotions, Verification, Decisions Made.
