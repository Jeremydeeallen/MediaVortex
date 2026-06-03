# Current Directive

**Set:** 2026-06-03
**Status:** Active -- phase: DELIVERING
**Slug:** db-monolith-steering-hook
**Replaces:** `.claude/directives/paused/2026-06-03-bug-0042-vmaf-list-parity.md` (paused -- blocked on this directive's deliverables)

## Outcome

The hook stops being a code-quality gate for `Repositories/DatabaseManager.py` and becomes an architecture-direction router. When a directive tries to add or modify a method in the monolith, the refusal reads forward ("place it in `Features/<X>/<X>Repository.py`") instead of backward ("fix these 12 preexisting violations first"). The desired end state is documented once, in a colocated feature doc the hook cites on every steer. Incremental migration becomes the default move on every DB-layer touch -- not a future big-bang migration. Operators and Claude both see the destination on every refusal; directive scope stays narrow; line count of `Repositories/DatabaseManager.py` becomes a strictly-monotone-decreasing invariant.

## Acceptance Criteria

1. **End-state document exists and is hook-cited.** `Core/Database/repository-split.feature.md` gains a `## Perfect End State` section enumerating: no `Repositories/` directory; per-aggregate repos colocated at `Features/<X>/<X>Repository.py`; each repo inherits `Core/Database/BaseRepository`; shared helpers (`PathNormalizer`, `SqlEscape`, `WorkerCapabilityPredicate`) in `Core/Database/`; sibling contract test per repo at `Tests/Contract/Test<X>Repository.py`. The steering-hook refusal text quotes the path to this section so every reader of a refusal lands on the canonical target. Verifiable: grep the hook output for the file path; render the feature doc; confirm the section is present and matches the refusal text.

2. **Steering hook exists for `Repositories/DatabaseManager.py`.** A new check in `.claude/hooks/pre-edit-standards.ps1` (call it `Test-R<N>-DatabaseManagerSteering`) fires only on Edit/Write to `Repositories/DatabaseManager.py`. For NEW or MODIFIED methods, the refusal text names the target repo file (derived from the aggregate map) and tells the operator to put the method there. For PURE DELETIONS (carving methods out toward the migration), the check passes silently. Refusal text is prescriptive forward, not prohibitive backward. Verifiable: Edit attempt adding a method to `Repositories/DatabaseManager.py` produces a refusal naming the target repo path; pure-deletion Edit (all `new_string` empty for affected lines) passes.

3. **Aggregate-to-repo map exists and is data-driven, not hardcoded in the hook.** A new file `.claude/standards/database-manager-aggregates.json` (or `.psd1` — pick what `pre-edit-standards.ps1` reads cleanly) maps aggregate identifiers (table-name prefix, method-name prefix) to target repo paths. The steering hook reads this map per refusal. Adding a new aggregate is one row in the map, not a code change to the hook. Verifiable: add a synthetic entry to the map; trigger a refusal with the matching method name prefix; observe the new target path in the refusal text.

4. **R6 whole-file scan is suppressed on `Repositories/DatabaseManager.py`.** The R6 check (path-shape) skips this single file -- it's known debt being migrated; scanning charges rent without producing forward progress. Other files keep R6 unchanged. Verifiable: an Edit to `Repositories/DatabaseManager.py` that introduces a new method using `ntpath` does not produce an R6 refusal pointing at the 12 preexisting `os.path` violations elsewhere in the file. R6 still refuses an Edit to a different file (e.g. `Features/QualityTesting/QualityTestRepository.py`) that adds a new `os.path` call.

5. **Monotone-decrease invariant added to `check-conformance`.** The skill records the current line count of `Repositories/DatabaseManager.py` at first run, persists it in `.claude/.conformance-baselines.json`, and on every subsequent run asserts the count is <= baseline. Increases produce a violation. Verifiable: artificially raise the line count by adding lines; run `check-conformance`; confirm the violation. The same invariant applies to the count of `from Repositories.DatabaseManager import` lines across the repo.

6. **BUG-0042 can be resumed against the new hook.** Re-opening the paused directive (`2026-06-03-bug-0042-vmaf-list-parity.md`) and replaying its planned edits produces a clean run: the move of `GetRunningQualityTestProgress` to `QualityTestRepository.py` does not trip R6 on `DatabaseManager.py`'s 12 preexisting violations, and the steering refusal (if any edits target the monolith directly) names `Features/QualityTesting/QualityTestRepository.py`. Verifiable: dry-run replay of BUG-0042's Files block edits under this directive's deliverables.

## Out of Scope

- The actual migration of any aggregate out of `Repositories/DatabaseManager.py`. That happens incrementally, per directive that touches a DB method.
- `feedback_extraction_on_friction.md` rewrite. Touch only the addendum noting "the file in question is `Repositories/DatabaseManager.py`" -- the broader rule stands.
- Moving `Core/Database/repository-split.feature.md` from BACKLOG to ACTIVE on the feature stack. That belongs to operator workflow management, not this directive.
- Touching any other rule (R1, R3, R5, R7, R8, R9, R10, R11, R12, R13, R14, R15, R16, R18). This directive adds one rule and suppresses R6 for one file.
- BUG-0028's wording update. That gets a pointer to this work in its next touch, not preemptively.

## Constraints

- `R3` no caching settings in `__init__`; `R12` no multi-line docstrings in PowerShell-adjacent edited regions (the hook file is `.ps1` not Python -- R12 may not apply, confirm by reading the file's existing comment shape); `R13` no premature `*.feature.md` creation (the end-state section lands as an Edit to an existing file, not a new file).
- Steering refusal text must follow the existing hook refusal shape so escalation messaging (1st / 2nd / 3rd refusal) stays consistent across rules.
- The aggregate map is the single source of truth for aggregate boundaries. If a method name doesn't match any prefix in the map, the refusal asks the operator to add the map entry first -- it does NOT guess.

## Escalation Defaults

- Tradeoff between "hardcoded map in `.ps1`" and "external JSON/PSD1" -> external file (criterion 3).
- Tradeoff between "suppress R6 on the file" and "fix R6 cause by extracting" -> suppress (criterion 4). Extraction is the long-term cure; suppression is the bridge.
- Tradeoff between "block all edits to `Repositories/DatabaseManager.py`" and "allow with steering" -> allow with steering. Pure deletions and one-line bugfixes shouldn't require a directive of their own.
- Risk tolerance: medium. The hook is on the critical path of every code edit in the repo; a bug in the new check could refuse edits incorrectly across the codebase. Mitigate by: (a) per-file scope (only this one path triggers the new check), (b) defaulting to "allow with warning" if the map is missing or malformed, (c) explicit dry-run flag for hook authors to test the new check without affecting live edits.

## Engineering Calls Already Made

- The steering-hook target file is `Repositories/DatabaseManager.py` only. Other monoliths (if any future ones appear) get their own steering rules, not a generic "monolith" abstraction. Premature abstraction is itself a workaround pattern.
- The map's keys are method-name prefixes ("GetQualityTest", "SaveQualityTest", etc.) -- not table names directly. Rationale: PostgreSQL identifiers are case-folded; method names are PascalCase and grep-stable. Table-name matching would need an AST-level pass to figure out which tables a method's body touches; prefix matching is one regex.
- BUG-0042's paused directive doc is the canonical test case for criterion 6. Do not modify it during this directive's run -- it must be the same artifact at criterion 6 verification as it was at directive open.

## Status

Active 2026-06-03 -- phase: DELIVERING.

### Delivery report

- **DIRECTIVE:** The hook stops being a code-quality gate for `Repositories/DatabaseManager.py` and becomes an architecture-direction router. End-state shape lives in one colocated feature doc the hook cites on every steer; aggregate-to-target map is data-driven; R6 is suppressed for the single in-flight monolith; line count + import count of `Repositories/DatabaseManager.py` become strictly monotone-decreasing invariants.
- **STATUS:** Done. All six acceptance criteria PASS with concrete dry-run evidence in `### Verification`.
- **WHAT SHIPPED:**
  - New rule **R19 DatabaseManagerSteering** in `.claude/hooks/pre-edit-standards.ps1` (function `Test-R19-DatabaseManagerSteering` + dispatcher entry). Fires only on `Repositories/DatabaseManager.py`; per-`def` block detection via the existing `Get-EditRegion` + `Test-RangeOverlapsEditRegion` helpers; pure-deletion edits pass silently; `# allow: <reason>` override supported per the standard pattern.
  - **R6 per-file suppression** on `Repositories/DatabaseManager.py` (early-return at the top of `Test-R6-PathShape` with a `# directive: db-monolith-steering-hook` anchor for grep discoverability). All other files keep R6 unchanged.
  - **Aggregate-to-repo map** at `.claude/standards/database-manager-aggregates.json` (148 prefix rows; longest-prefix-first sort; `default_target_hint` + `feature_doc_anchor` for refusal text composition). Adding a new aggregate is one row, not a code change.
  - **`## Perfect End State` section** added to `Core/Database/repository-split.feature.md` (the hook's canonical citation target). Compact synopsis; reconciles directive C1 with feature doc C4 (no `BaseRepository` inheritance -- compose `DatabaseService` instead).
  - **Standards index R19 row** added to `.claude/standards/index.md` documenting the steer and the R6 suppression.
  - **Project command `/mediavortex-check-baselines`** at `.claude/commands/mediavortex-check-baselines.md` (data-driven; reads `.claude/.conformance-baselines.json`; reports per-entry PASS/FAIL/SKIP; suggests baseline tightening when current < baseline).
  - **Baselines seed** at `.claude/.conformance-baselines.json` declaring `Repositories/DatabaseManager.py` line_count=5850 + import_count=123 invariants, citing the driving feature doc.
  - **Memory addendum** in `feedback_extraction_on_friction.md` noting `Repositories/DatabaseManager.py` as the specific application; the broader rule stands.
- **HOW TO USE IT:**
  - Try to add a method to the monolith -> the Edit is refused with the target repo path; put it there instead.
  - Already know a method belongs in a new aggregate? Add one row to `.claude/standards/database-manager-aggregates.json` (`{ "match": "<prefix>", "target": "Features/<X>/<X>Repository.py" }`) and the steer routes automatically.
  - Run `/mediavortex-check-baselines` (e.g. in CI or pre-merge) to confirm the monolith has not regrown; lower the integers in `.claude/.conformance-baselines.json` as the migration progresses to ratchet the floor down.
  - Deliberate one-line bugfix landing in the monolith? Override with `# allow: one-line bugfix for <reason>` within 3 lines of the `def`; the override logs to `.claude/.standards-overrides.log` per the standard pattern.
- **WHAT YOU NEED TO EXECUTE:**
  - Resume the paused BUG-0042 directive when ready (`git mv .claude/directives/paused/2026-06-03-bug-0042-vmaf-list-parity.md .claude/directive.md` after this directive closes); replay its Files block edits -- the hook now steers cleanly per criterion 6 evidence.
  - Optional: commit and push these deliverables. Each Promotions row's `Commit` cell stays TBD until you do.
  - Optional: when you tighten the baseline (after first aggregate moves out of `DatabaseManager.py`), edit `.claude/.conformance-baselines.json` -- the new floor is whatever the current count is post-move.
- **CRITERIA VERIFICATION:** Per-criterion evidence (PASS for all six) in `### Verification` below.
- **DECISIONS I MADE:** Material engineering choices captured in `### Decisions Made` below: (1) reconciling directive C1 vs feature doc C4 BaseRepository contradiction in favor of the durable contract; (2) `## Perfect End State` shape as a compact synopsis (not duplicate criteria); (3) project-local `/mediavortex-check-baselines` command instead of modifying the upstream `claude-rails` framework (after the hook explicitly refused the cross-repo edit and the operator's "Hook Path forward is the answer" memory applied); (4) PowerShell `Get-Content.Count` semantics for `line_count` baseline (5850, not the `wc -l` 5849); (5) drop the `^` anchor on `import_count` regex so indented imports count too (a 27-line difference between anchored and unanchored counts).
- **KNOWN GAPS / DEFERRED:**
  - `.claude/.conformance-baselines.json` only seeds two invariants for one file. Other in-flight migrations (none currently) would add their own entries when relevant.
  - The aggregate map has 148 prefix rows derived from the current method inventory of `Repositories/DatabaseManager.py`. Methods added in the future without a matching prefix produce a refusal asking the operator to add a map row first -- this is intentional, not a gap.
  - BUG-0042 itself is still paused. Resuming is an operator action (per WHAT YOU NEED TO EXECUTE) and outside this directive's scope.

### Plan refinements (decisions made during NEEDS_PLAN)

- **R-rule slot:** new check is `R19` (R17 is the empty slot in the standards table but still appears in archived directives; R19 is the next clean slot after R18). Hook function name: `Test-R19-DatabaseManagerSteering`.
- **`check-conformance` lives upstream.** It is a framework slash command at `/c/Code/claude-rails/commands/check-conformance.md`, not a project skill. The "(or equivalent)" hedge in `## Files` was earned: the right move is to extend the upstream command to be data-driven -- read `.claude/.conformance-baselines.json` from the repo it runs in and enforce every monotone-decrease invariant the file declares. This keeps MediaVortex content data-driven and makes the same invariant available to any other repo on claude-rails. Cross-repo edit is justified because the upstream change is generic (no MediaVortex-specific code lands in the framework).
- **R6 suppression mechanism:** add a per-file allowlist (path string match) inside `Test-R6-PathShape`. Single-file scope, easy to remove when the migration completes. Keep allowlist next to `Test-R6-PathShape` so the suppression is discoverable from the check itself.
- **Aggregate map format:** JSON (PowerShell reads via `ConvertFrom-Json`, already used by the hook for state files). Shape: `{ "prefixes": [{ "match": "<methodNamePrefix>", "target": "<repo path>" }, ... ], "default_target_hint": "Features/<X>/<X>Repository.py" }`. Prefixes evaluated longest-first so `Get` does not shadow `GetQualityTest`.
- **Refusal-text shape for R19:** identical preamble to other rule refusals so escalation messaging (1st / 2nd / 3rd) stays consistent. Body: `R19 DatabaseManagerSteering -- <FilePath> is the monolith being migrated. New/modified method "<methodName>" belongs in <target repo path> per Core/Database/repository-split.feature.md#perfect-end-state. Pure deletions are allowed without steering.` If no prefix matches: refusal asks the operator to add the map entry first; the hook does NOT guess.

### Seam enumeration (per `seam-verification.md`)

| Seam | Producer | Wire shape | Consumer expects | Verification |
|---|---|---|---|---|
| S-A Hook -> aggregate map | `.claude/standards/database-manager-aggregates.json` | JSON `{prefixes: [{match, target}], default_target_hint}` | `Test-R19-DatabaseManagerSteering` `ConvertFrom-Json` | Round-trip: synthetic prefix in map; Edit triggers refusal naming target (criterion 3 verification) |
| S-B Hook -> repository-split feature doc | `Core/Database/repository-split.feature.md#perfect-end-state` (anchor in refusal text) | Markdown header `## Perfect End State` | Human reader of refusal navigates to section | Grep refusal text for header; render feature doc; confirm section exists (criterion 1 verification) |
| S-C Hook -> PreToolUse input | Claude Code harness (existing) | JSON with `tool_input.file_path` + `new_string` | Hook code reads same fields as R6/R12 | Existing seam; no new contract |
| S-D R19 -> R6 per-file allowlist | `Test-R6-PathShape` internal allowlist | PowerShell array of normalized paths | R6 short-circuits on match | Round-trip: synthetic `os.path.dirname(` in `Repositories/DatabaseManager.py` does NOT fire R6; same call in a different file DOES fire R6 (criterion 4) |
| S-E check-conformance -> baselines JSON | `.claude/.conformance-baselines.json` | JSON `{baselines: [{file, metric, baseline}]}` | Upstream `check-conformance.md` instructs Claude to compare | Round-trip: synthetic line-count bump produces violation on next run (criterion 5) |
| S-F check-conformance -> repo grep | Repo working tree | File contents | Grep / wc-l for line count + `from Repositories.DatabaseManager import` count | Run `check-conformance` against current tree; counts match baseline file (criterion 5) |
| S-G Hook -> R19 refusal text -> operator | Hook stdout JSON | Refusal string with rule ID + target path | Operator reads refusal, edits at target instead | BUG-0042 replay -- planned edits to `QualityTestRepository.py` succeed; any incidental edits to monolith get steered (criterion 6) |

### Files

```
.claude/standards/index.md                              -- EDIT: add row for the new R<N> steering check; document R6 per-file suppression
.claude/standards/database-manager-aggregates.json      -- CREATE: aggregate -> repo path map (data-driven; criterion 3)
.claude/hooks/pre-edit-standards.ps1                    -- EDIT: add Test-R<N>-DatabaseManagerSteering; suppress R6 on Repositories/DatabaseManager.py
Core/Database/repository-split.feature.md               -- EDIT: add ## Perfect End State section the hook cites (criterion 1)
.claude/skills/check-conformance/SKILL.md (or equivalent) -- EDIT: add monotone-decrease invariant for DatabaseManager.py line count + DM-import count
.claude/.conformance-baselines.json                     -- CREATE: initial baseline (current line count + import count)
memory/feedback_extraction_on_friction.md               -- EDIT: append one paragraph noting DatabaseManager.py special case + pointer to repository-split.feature.md
```

### Promotions

Required when phase advances to DELIVERING.

| Source artifact | Target file | Commit |
|---|---|---|
| `## Perfect End State` design content | `Core/Database/repository-split.feature.md` | TBD |
| Aggregate -> repo path mapping | `.claude/standards/database-manager-aggregates.json` | TBD |
| Steering-hook check + R6 per-file suppression | `.claude/hooks/pre-edit-standards.ps1` + row in `.claude/standards/index.md` | TBD |
| Monotone-decrease invariant | `check-conformance` skill + `.claude/.conformance-baselines.json` | TBD |
| Extraction-on-friction addendum | `memory/feedback_extraction_on_friction.md` | TBD |

### Verification

Required when phase advances to VERIFYING. One entry per acceptance criterion.

- **Criterion 1 (PASS):** `## Perfect End State` exists at `Core/Database/repository-split.feature.md` line 31. The anchor `Core/Database/repository-split.feature.md#perfect-end-state` is cited from five files: the hook (`Test-R19-DatabaseManagerSteering` refusal text), the standards index R19 row, the aggregate map's `feature_doc_anchor`, the new `mediavortex-check-baselines` command, and this directive. Section enumerates: no `Repositories/` directory; per-aggregate repos colocated at `Features/<X>/<X>Repository.py`; composing `DatabaseService` (no inheritance, per the reconciliation with feature doc C4 -- see Decisions Made); shared helpers under `Core/Database/` (PathNormalizer, SqlEscape, WorkerCapabilityPredicate); sibling contract tests per repo; under-800-line ceiling.
- **Criterion 2 (PASS):** R19 fires on Edit/Write to `Repositories/DatabaseManager.py` whose edit region overlaps a `def` block; pure-deletion edits pass silently. Evidence (Case A, synthetic): adding `def GetQualityTestResults` produces refusal `R19 DatabaseManagerSteering: ... New/modified method 'GetQualityTestResults' (line 2) belongs in Features/QualityTesting/QualityTestRepository.py per Core/Database/repository-split.feature.md#perfect-end-state. Pure deletions of methods from this file pass silently.`. Evidence (Case B): pure-deletion Edit (`new_string=""`) → `EditRegion.Mode = NoRegion` → PASS. Evidence (Case C): same edit on `Features/QualityTesting/QualityTestRepository.py` → PASS (R19 file-scoped). Refusal text follows the existing hook preamble shape (STOP header + escalation count).
- **Criterion 3 (PASS):** Aggregate map is data-driven via `.claude/standards/database-manager-aggregates.json` (148 prefix rows; longest-prefix-first sort). Hook reads it per refusal via `Get-Content | ConvertFrom-Json`. Evidence (Case A): the synthetic `GetQualityTestResults` method matched the map entry `{ "match": "GetQualityTestResults", "target": "Features/QualityTesting/QualityTestRepository.py" }`. Evidence (Case D, unmapped prefix): `def SomeBrandNewVerb(self):` produced refusal `... No prefix in .claude/standards/database-manager-aggregates.json matches this name -- the hook will not guess the target aggregate. Path forward: add a row ...`. The hook does NOT guess; it asks for a map entry first, per the directive's "If no prefix matches" rule.
- **Criterion 4 (PASS):** R6 (`Test-R6-PathShape`) early-returns for `Repositories/DatabaseManager.py`. Evidence: synthetic `os.path.dirname(some_path)` content with `$FilePath = Repositories/DatabaseManager.py` → PASS (no refusal); same content with `$FilePath = Features/QualityTesting/QualityTestRepository.py` → REFUSAL: `R6 Path shape: ... line 2 uses os.path on a path-named variable.` The suppression is single-file (path-string match in the function body, with a `# directive: db-monolith-steering-hook` anchor line for grep discoverability) -- no other file paths are exempted.
- **Criterion 5 (PASS):** `.claude/.conformance-baselines.json` declares two invariants: `Repositories/DatabaseManager.py` line_count baseline 5850 and import_count baseline 123 (`from Repositories.DatabaseManager import` matches across `*.py`, excluding `.claude/`, `venv/`, `__pycache__/`). The `/mediavortex-check-baselines` command reads the file and reports per-entry status. Evidence (positive path, current state): `line_count current=5850 baseline=5850 PASS`; `import_count current=123 baseline=123 PASS`; `Overall: PASS`. Evidence (negative path, synthetic +5 line bump): `current=5855 > baseline=5850 => FAIL (mechanism verified)`. Operator extends invariants by adding rows to the JSON; the command is data-driven. The check is a separate command (not a fork of the upstream framework `/check-conformance`) -- see Decisions Made for rationale.
- **Criterion 6 (PASS):** BUG-0042's paused directive can be resumed against the new hook. The Files block in `.claude/directives/paused/2026-06-03-bug-0042-vmaf-list-parity.md` plans extraction (move `GetRunningQualityTestProgress` from `Repositories/DatabaseManager.py` -> `Features/QualityTesting/QualityTestRepository.py`). Dry-run evidence: (6.A) synthetic Edit ADDING `def GetRunningQualityTestProgress(self):` to DM.py -> R19 refusal naming `Features/QualityTesting/QualityTestRepository.py` as the target (steering, not blocking). (6.B) synthetic Edit DELETING the method from DM.py (pure deletion, `new_string=""`) -> PASS (`EditRegion.Mode = NoRegion`; extraction carving allowed). (6.C) synthetic `os.path.dirname` in DM.py content -> R6 PASS (suppressed on this single file, no cascade on the 11 preexisting `os.path` violations). The paused directive's artifact is unchanged at this point (Engineering Calls Already Made: do not modify BUG-0042's directive doc during this run).

### Decisions Made

- **Reconciliation: criterion 1 vs `repository-split.feature.md` C4.** Directive criterion 1 enumerates "each repo inherits `Core/Database/BaseRepository`" as part of the end state. The durable feature doc's criterion 4 explicitly forbids any `BaseRepository` superclass / repository inheritance hierarchy ("Repositories compose `DatabaseService` via constructor injection"). The feature doc is the durable CONTRACT; the directive is the transient ASK. Resolution: the new `## Perfect End State` section will track the feature doc, NOT introduce a `BaseRepository` inheritance shape. The hook-cited end-state synopsis reads "per-aggregate repos colocated at `Features/<X>/<X>Repository.py`, composing `DatabaseService` (no inheritance)". The directive criterion is treated as satisfied when the synopsis enumerates the items it lists EXCEPT the `BaseRepository` line, since following both literally is impossible. (Surfaced at NEEDS_DOC_PREREAD; standing instruction said "make the reasonable call and continue", so flagged here rather than escalated.)
- **`## Perfect End State` shape.** Rather than duplicate the feature doc's existing Success Criteria, the new section is a tight synopsis (one short paragraph + bulleted target shape) intended to be hook-cited from refusal text. Details remain in Success Criteria below it. Section anchor: `#perfect-end-state`. The R19 refusal text quotes this anchor verbatim.
- **`check-conformance` extension is generic.** The upstream change at `/c/Code/claude-rails/commands/check-conformance.md` introduces a generic "read repo-local `.claude/.conformance-baselines.json` and enforce its monotone-decrease invariants" step. The MediaVortex-specific content (DatabaseManager.py line count, DM-import count) lives in the baselines file in this repo. No MediaVortex-specific code in the framework command. This makes the invariant data-driven AND project-agnostic.

---

## Closure (thin-pointer archive shape)

When this directive is ready to close: follow the standard procedure in `.claude/directives/_template.md`. Confirm Promotions table populated with commit SHAs; confirm directive did not grow during DELIVERING; `git mv` to `.claude/directives/closed/2026-06-03-db-monolith-steering-hook.md`; replace working directive with template copy.
