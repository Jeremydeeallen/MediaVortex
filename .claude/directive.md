# Current Directive

**Set:** 2026-05-30
**Status:** Active -- phase: NEEDS_PLAN -- scaffolding the destination target, fleshing out criteria
**Slug:** unified-standards-destination
**Replaces:** Interrupts paused `nvenc-rate-anchored-remediation` and paused `ceo-mode-enforcement`. Both resume against the shape this directive produces.

## Outcome

<a id="outcome"></a>

MediaVortex has ONE standards layer, ONE workflow, ONE source of truth for design rationale, and ONE mechanism for tracking code-health debt. After this directive closes:

- `*.feature.md` files do not exist in the repo. Every prior feature doc is either a closed directive in `.claude/directives/closed/` or deleted.
- `*.flow.md` files describe current pipeline architecture; they are the only colocated `.md` artifact and are maintained by directives that change their pipeline.
- Every touched function carries a `# directive: <slug>` anchor (R15, mandatory and enforced).
- File line ceiling (R16) and method line ceiling (R17) are mechanical, with a baseline + monotonic-improvement model so monoliths can't grow but don't force big-bang refactors.
- Plan-review and code-review gates use specialized expert skills (`software-architect`, `data-expert`, `security-expert`, etc.) at phase transitions.
- Named judgment standards (no hardcoded values, no silent fallbacks, no two-place sources of truth, no magic strings as switch keys, plus the rest of the catalogue) live in `.claude/standards/judgment/` and surface at plan review.
- A conversion-debt table ranks files by gap from R16 target, making refactor prioritization objective.
- CLAUDE.md is a thin orient pointing at standards, not a duplicate of them.
- Closed directives are append-only (R18). Reading the archive is the canonical way to discover why code looks the way it does; bidirectional via R15 forward and `## Files` reverse.
- The `/n` skill ambiguity is gone: one `/n`, one workflow, one directive doc.

The repo can be fully understood by: (1) reading the unified standards, (2) reading flow docs for pipeline understanding, (3) opening code and following `# directive:` anchors to closed directives for the why. No third source of truth, no stale parallel docs, no per-area pattern guessing.

## Acceptance Criteria

<a id="criteria"></a>

Criteria below are STUBS. Each section names the intent + open questions. We flesh out the specific verifiable form per criterion during this NEEDS_PLAN phase.

### A. Standards source consolidation

<a id="a-standards-consolidation"></a>

**REVISED 2026-05-30 after auto-load investigation:** Claude Code auto-loads `.claude/rules/*.md` as project instructions by convention -- this is a product behavior tied to that specific path, not driven by settings.json. Moving rule docs OUT of `.claude/rules/` would lose the free auto-load (~18K tokens of context per session would have to be re-Read explicitly). So the consolidation shape changes: `.claude/rules/` stays as the judgment-standards home; `.claude/standards/` becomes the mechanical-rule home + index/routing layer.

1. **`.claude/rules/*.md` is the judgment-standards layer.** Existing rule docs stay; new judgment standards (`no-hardcoded-values.md`, `no-silent-fallbacks.md`, etc. -- the catalogue from section G) are ADDED here, not under standards/. Each rule doc covers one principle (split if needed). After this directive, every named judgment standard from section G has a file in `.claude/rules/`. Verifiable: every named principle is one `.claude/rules/<slug>.md` file; index.md links to it. **OPEN:** which existing rule docs need splitting vs stay one-to-one?

   **Auto-load verification subtask:** before relying on this, write a stub `.claude/rules/test-autoload.md` and confirm it appears as "project instructions" at next session start. If yes, proceed. If no, fall back to NEEDS_STANDARDS_REVIEW phase as the loading mechanism + reshape this section.

2. **`.claude/standards/mechanical/` holds the R-rule definitions** (one file per rule R1-R18, each ~30 lines: pattern, refusal message, override semantics). The hook reads these instead of carrying inline rule logic. Verifiable: hook script length drops; each `Test-R<N>` function reads its rule file. **OPEN:** does hook reload per call, or load-once-at-session-start?

3. **`.claude/standards/index.md` is the entry point**, listing every mechanical R-rule + every named judgment standard with one-line summary + link to the canonical doc. Verifiable: every R-rule and every judgment standard has exactly one entry; entries link to existing files; no orphans.

4. **CLAUDE.md becomes thin orient** built on the [multica-ai/andrej-karpathy-skills](https://github.com/multica-ai/andrej-karpathy-skills) 4-rule base (think before coding / simplicity first / surgical changes / goal-driven execution), plus MediaVortex-specific pointers (standards index, flow docs, directives/closed/, naming + commands). Verbatim Karpathy content stashed in `### Karpathy CLAUDE.md content (locked, source for merge)` working-notes section below. Total target ~80 lines. Verifiable: line count ≤ 90; Karpathy 4 rules present verbatim; pointers to standards / flow docs / directives present; no embedded R-rule definitions; no embedded judgment-standards prose.

   **OPEN:** which CLAUDE.md sections survive (naming, commands, project overview) vs move to standards (architecture pattern, key tables, etc.)? Current CLAUDE.md is ~250 lines; ~170 lines need to go somewhere or disappear.

### B. Workflow consolidation

<a id="b-workflow-consolidation"></a>

**REVISED 2026-05-30 after superpowers adoption decision:** The workflow phase machine + plan-doc + criteria pattern is largely supplied by [obra/superpowers](https://github.com/obra/superpowers) (brainstorming / writing-plans / TDD / subagent-driven-development / code-review skills). Install command: `/plugin install superpowers@claude-plugins-official` (operator runs this; not gated by directive). Workflow criteria below describe how MediaVortex-specific shapes (directive doc, phase markers, CEO authority split) sit on top of superpowers.

5. **One `/n` skill.** When `.claude/directive.md` is non-empty and not the template, `/n` opens a new directive (current CEO behavior). When the template, `/n` opens a fresh directive. Internally `/n` invokes superpowers' brainstorming skill to walk criteria, then drafts the directive doc shape on top. The legacy feature-based `/n` is retired or its file deleted from the skill registry. Verifiable: `/n <slug>` always produces directive-doc behavior; `*.feature.md` is never created; brainstorming skill is invoked during criteria-drafting. **OPEN:** does `/n` wrap brainstorming explicitly or just let it auto-trigger from context?

6. **`.claude/current-feature` stack retired.** Closed directives in `.claude/directives/closed/` are the historical record. Verifiable: file does not exist (or exists empty as an explicit "intentionally empty" marker); no skill/script references it. **OPEN:** are the 5 paused entries currently in `.claude/current-feature` (media-tabs-and-loudness, scan drives ad-hoc, linear-loudnorm, pipeline-test-harness, compliance-gated-rename) closed-as-abandoned, converted to directives, or just deleted? Each needs a per-feature decision.

7. **R13 changes from "no new" to "none exist."** Every existing `*.feature.md` is either migrated to a closed directive or deleted. New rule wording: "`*.feature.md` files do not exist in the repo." Verifiable: `Get-ChildItem -Recurse -Filter '*.feature.md'` returns zero results.

### C. Feature-doc migration sweep

<a id="c-feature-migration"></a>

8. **Inventory captured.** Every existing `*.feature.md` is listed with its current Status (COMPLETE / in-flight / abandoned) and a per-file disposition (convert / merge / delete). Verifiable: this directive's `### Inventory` section lists every file with disposition. **OPEN:** full inventory below to be filled during this NEEDS_PLAN phase. Known so far:
   - `Features/Profiles/nvenc-rate-anchored.feature.md` (COMPLETE, convert)
   - `Features/Profiles/nvenc-profiles.feature.md` (TODO: status check)
   - `Features/ContentClassifier/content-classifier.feature.md` (TODO)
   - `Features/ServiceControl/graceful-drain.feature.md` (TODO)
   - `Features/QualityTesting/post-transcode-disposition.feature.md` (TODO)
   - `Features/QualityTesting/qt-queue-visibility-and-override.feature.md` (TODO)
   - `Scripts/Smoke/EncoderShootout.feature.md` (TODO)
   - `WorkerService/worker-lifecycle.feature.md` (TODO)
   - **OPEN:** glob-sweep for full set

9. **Convert: feature doc -> closed directive.** Each "convert" disposition produces `.claude/directives/closed/YYYY-MM-DD-<slug>.md` carrying outcome / criteria / files list / status. Original deleted in the same commit. Date = feature's COMPLETE date if recorded, else `synthesized 2026-05-30`. Verifiable: every converted feature has a closed-directive sibling with matching slug.

10. **Delete: feature doc fully redundant with flow doc + code.** Some feature docs (likely the older ones) describe behavior fully captured in the flow doc; their closed-directive form would carry no information not already there. These are deleted outright. Verifiable: deletion noted in this directive's Verification.

11. **Flow docs preserved unchanged unless their feature doc carried information not in the flow.** In that case, the missing content moves to the flow doc, then the feature doc is deleted. Verifiable: per-flow-doc diff shows additions are sourced from feature-doc migrations.

### D. Bidirectional index

<a id="d-bidirectional-index"></a>

12. **R15 (directive anchor) is reaffirmed as mandatory.** Every function/class touched by a directive has `# directive: <slug>` directly above its `def`/`class` line. No grace period; new touches must comply. Verifiable: hook test simulates non-anchored edit on a directive-listed file; refused.

13. **R18 (closed-directive append-only) added.** Edits to files under `.claude/directives/closed/` are refused. To supersede a closed directive, open a new one that names the prior one in `**Replaces:**`. Verifiable: hook simulates edit of a closed directive file; refused with pointer to supersede pattern.

14. **`Scripts/Directives/WhatTouchedThis.py <path>` exists** and greps closed directives' `## Files` sections for the given path, returning slugs in chronological order. Verifiable: invoke against `Models/CommandBuilder.py`; returns the closed directive that touched it last.

15. **Directive granularity guidance written into standards.** Soft cap on file count per directive (TBD: 8? 10?); large scope splits into a program of small directives. Verifiable: standards doc has the guidance; plan-review gate checks file count and flags. **OPEN:** hard cap or soft cap? What's the right number?

### E. File and method line discipline

<a id="e-line-ceilings"></a>

16. **R16 (file line ceiling) added** with baseline + monotonic-improvement model:
    - Per-directory target configurable (e.g., `Features/*/Controller.py` = 150, `Models/` = 200, `Scripts/SQLScripts/Add*.py` = 100). Defaults in `.claude/standards/file-size-targets.json`.
    - `.claude/.file-baselines.json` snapshots every file's current line count at directive close.
    - Edit/Write to a file: new file size ≤ max(target, baseline). Files at/under target held there; files over baseline can only shrink.
    - Verifiable: simulated Edit that grows a baseline-tracked file past its baseline → refused; Edit that shrinks it → allowed.
    - **OPEN:** how are baselines updated when a refactor directive intentionally restructures? Mechanism: refactor directives include `baseline_update` block in their criteria.

17. **R17 (method line ceiling) added**, unconditional on touched functions:
    - Any function modified in any Edit must end ≤ 50 lines (configurable).
    - Surrounding monolithic file can stay over R16 baseline; the touched function must conform.
    - Verifiable: simulated edit producing a 60-line function → refused; 50-line → allowed.
    - **OPEN:** what counts as "touched"? Whole-function rewrite vs single-line patch? Likely: any def/class whose body the diff alters.

18. **Conversion-debt table script.** `Scripts/Directives/ConversionDebt.py` reports files sorted by `(baseline - target)` so the worst SRP offenders are visible and prioritizable. Verifiable: invoke; produces ranked table; top entries match known monoliths (e.g., `WorkerService/Main.py`).

19. **Refactor directives are first-class.** Standards doc explicitly names "refactor directive" as a legitimate directive shape (outcome = decompose file X; no new features). The plan-review gate accepts these. Verifiable: standards doc has the entry; example refactor-directive template in `.claude/directives/_template-refactor.md`.

### F. Plan and code review gates

<a id="f-review-gates"></a>

**REVISED 2026-05-30 after superpowers adoption:** superpowers' code-review and subagent-driven-development skills implement the review patterns. MediaVortex layer = the phase hook enforces invocation of these skills at specific phase transitions, not their implementation.

20. **Plan-review gate between NEEDS_PLAN and NEEDS_DOC_PREREAD.** The hook refuses the phase advance unless the session transcript shows invocation of superpowers' brainstorming skill (or the `software-architect` claude-rails agent) against the directive's criteria + Files list. Verifiable: try advancing without the review; refused. With the review; allowed.
    - **OPEN:** which review skill is the gate? superpowers brainstorming vs claude-rails software-architect vs both?
    - **OPEN:** is the review's output captured in the directive doc as a section, or just in the transcript?

21. **Code-review gate between IMPLEMENTING and VERIFYING.** The hook refuses phase advance unless superpowers' requesting-code-review skill has been invoked against the diff. Specialized expert skills (data-expert / security-expert) are opt-in additional reviewers per directive.
    - **OPEN:** how does the hook know which expert to require beyond the base code-review? Tag system on the directive ("expert: data" / "expert: security")? Auto-detection from touched paths?

22. **Litmus check criterion-by-criterion.** During plan-review, the reviewer applies the 5 feature-criteria tests (rename / outsider / rewrite / negation / stability) to each criterion. superpowers' code-review skill has a "pre-review checklist" pattern that maps to this; MediaVortex extension is the 5-test litmus. Verifiable: review output includes pass/fail per criterion per test.

### G. Named judgment standards

<a id="g-judgment-standards"></a>

Each entry is a named principle, not hook-gated but surfaced at plan review. The catalogue below is the FIRST PASS; we add/refine as we agree.

23. **No hardcoded values where DB-driven is possible.** Already memory-captured (`feedback_no_hardcoded_values.md`); gets a canonical file in `.claude/standards/judgment/no-hardcoded-values.md`.

24. **No silent fallbacks.** Missing data → explicit error, not degraded mode. Reason: silent fallbacks produce bugs that hide for weeks; explicit errors surface the gap. Per directive `nvenc-rate-anchored.feature.md` criterion 8 wording: clear error message naming the file and the column, no silent fallback to CQ.

25. **No two-place sources of truth.** Same claim/decision in two repositories → drift. One canonical, others route to it. Already in `db-is-authority.md`; promoted to named judgment standard.

26. **No magic strings as switch keys.** Profile names, status enums in `if x == 'literal'` switches. Use columns, enums, or typed dispatch.

27. **No boot-cached dynamic config.** `self._cached_*` in `__init__` of services/repositories. Already R3 (mechanical); judgment-layer entry explains WHY (db-authority).

28. **No god-objects / single-responsibility at file level.** Companion to R16/R17. Judgment-layer entry: a file does one thing; if you find yourself naming the file with "and," split.

29. **No YAGNI violations.** Schema columns / branches added "just in case." If the second use case isn't shipping, the column isn't either.

30. **No tests over-coupled to implementation.** Tests assert behavior, not internal call sequences or log strings.

31. **No annotation drift in docs.** Already R14 (mechanical); judgment-layer entry explains WHY (docs as spec, not log).

32. **No implicit temporal coupling.** A-must-be-called-before-B without enforcement. Explicit construction-time wiring instead.

33. **No cross-feature reach-around.** Feature A's controller accessing Feature B's repository directly. Use explicit cross-feature APIs.

34. **Outside-in design preserved.** User-facing features start with the flow doc (what the user sees) before any implementation. The flow doc is the contract criteria must trace to.

35. **Criteria as contract.** Done is defined per-criterion, with evidence in the directive's Verification section. No "ship and document later."

36. **OPEN:** what else? We've listed pain points 1-20 from the elephant discussion; not all need to be judgment standards. Walk that list once and decide per item.

### H. Hook + state machine

<a id="h-hook-state"></a>

37. **Hook loads rule definitions from `.claude/standards/mechanical/R*.md` files**, not from inline PowerShell. Verifiable: hook script ≤ N lines (TBD); each `Test-R<N>` reads its rule file at session start. **OPEN:** N value.

38. **Phase machine extended with review gates** (criteria 20, 21). Verifiable: phase transitions refused without satisfying review.

39. **Override mechanism unchanged.** `# allow: <reason>` still works per-rule, logged to `.claude/.standards-overrides.log`. No global disable.

40. **`.gitignore`** covers `.session-state.json`, `.standards-overrides.log`, `.file-baselines.json`. Verifiable: `git status` does not show them as untracked.

### I. Memory cleanup

<a id="i-memory-cleanup"></a>

41. **Memory entries that duplicate new judgment standards get deleted.** Specifically: entries that are now load-bearing in `.claude/standards/judgment/` are removed from the user-memory index, with the standards file as the canonical home. Memory keeps only entries that capture operator preferences not expressible as repo-checked standards (e.g., I9 ownership, NFS reliability, ebur128 parser anchor).
    - **OPEN:** walk MEMORY.md entry-by-entry and decide.

42. **Memory entries renamed to match standards file slugs** where they survive but are now backed by a standards file. Verifiable: each memory entry's `description` line names the standards file it complements.

## Out of Scope

<a id="out-of-scope"></a>

- Actually executing the nvenc remediation or any other deferred work. This directive only sets up the unified shape; nvenc resumes after, against that shape.
- Production code changes other than what's necessary to add `# directive:` anchors to existing functions that get touched as part of standards consolidation (likely few or none).
- Migrating closed directives in `.claude/directives/closed/` -- they're already in target shape.
- Rewriting flow docs. They stay as-is unless content from a deleted feature doc needs to merge into one (criterion 11).
- Changing skill or hook plugin packaging (the `~/claude-config` plugin, the claude-rails distribution). Local repo changes only; upstream skill/plugin changes are a separate problem.
- Auto-running the conversion sweep on every `.py` file. R16 baselines are captured; refactor directives convert. No mass refactor.

## Constraints

<a id="constraints"></a>

- **No production behavior change.** This is a meta-directive about how we work. If a production file is touched at all, only to add `# directive:` anchor lines OR to migrate a colocated feature doc. No logic edits.
- **R14 (annotation drift) applies to flow docs during migration.** Adding "(formerly in feature.md)" lines is forbidden; merged content reads as native flow-doc content.
- **All migrations idempotent.** Re-running the destination-directive's migration scripts on a partially-converted repo produces no diffs.
- **Existing closed directives are not edited.** R18 applies even before it's added; the migration sweep does not touch the existing closed-directive archive.
- **No new env vars.** All config comes from files already in `.claude/` or memory.

## Escalation Defaults

<a id="escalation-defaults"></a>

- Tradeoff between "split a `.claude/rules/*.md` doc into multiple judgment standards" vs "keep as one" -> default SPLIT when a doc covers >2 distinct invariants; KEEP when it's one cohesive principle.
- Tradeoff between "convert feature doc to closed directive" vs "delete outright" -> default CONVERT when the feature has criteria + status worth preserving; DELETE when the content duplicates the flow doc + code.
- Tradeoff between "rich plan-review (architect + 1-2 specialized experts)" vs "minimal (architect only)" -> default ARCHITECT-ONLY for the gate to keep token cost predictable; specialized expert is opt-in per directive via a tag.
- Risk tolerance: low on losing operator-validated content (memory, flow docs, closed directives); medium on workflow simplification (some short-term friction is acceptable for long-term clarity).

## Engineering Calls Already Made

<a id="engineering-calls"></a>

- Destination is implemented as ONE directive, not a program of many. Reason: a program creates per-piece commits but the unified shape needs to land as a coherent state. Partial standards consolidation is worse than current state because it adds N+1 sources of truth.
- Feature docs do not survive as a parallel layer (operator explicit decision this session). Migration is delete-or-convert; no read-only legacy state.
- Closed directives are append-only (R18). Reason: their value is being trustworthy historical records; editable closed directives are no better than editable feature docs.
- Baseline + monotonic-improvement model on R16/R17 (operator-discussed). Reason: hard-fail on existing monoliths breaks production work; pure grandfather lets monoliths win.
- Plan-review and code-review gates use the existing claude-rails skill catalogue (software-architect, data-expert, security-expert, etc.). Reason: those skills already exist; no need to build new agent roles.

## Status

<a id="status"></a>

Active 2026-05-30 -- phase: NEEDS_PLAN -- fleshing out criteria. The directive doc is the working scratch; flesh-out happens here non-linearly via the anchors above. No phase advance until every `**OPEN:**` is resolved AND the operator ratifies the full criteria set.

### Progress

<a id="progress"></a>

- [x] Outcome drafted (need ratification before considered locked)
- [x] Criteria sections scaffolded with anchors
- [ ] Open questions resolved per section (see `**OPEN:**` markers below)
- [ ] Feature-doc inventory completed (criterion 8 full list)
- [ ] Memory walk completed (criterion 41 disposition list)
- [ ] Pain-point catalogue walked for judgment-standard candidates (criterion 36)
- [ ] Per-directory file-size targets set (criterion 16 config)
- [ ] Hook reload mechanism decided (criterion 2)
- [ ] Plan-review expert selection mechanism decided (criterion 20)
- [ ] Code-review expert selection mechanism decided (criterion 21)
- [ ] Directive granularity cap decided (criterion 15)
- [ ] Method-touched definition decided (criterion 17)
- [ ] CLAUDE.md surviving sections decided (criterion 4)
- [ ] Rule-doc fold mapping decided (criterion 1)
- [ ] Operator ratifies full criteria set -- advance to NEEDS_DOC_PREREAD

### Open questions

<a id="open-questions"></a>

Collected from `**OPEN:**` markers above for visibility. Resolve each, then strike from this list.

1. (crit 1) Rule-doc fold mapping: which `.claude/rules/*.md` merge vs stay distinct?
2. (crit 2) Hook reload: per-call or load-once-at-session-start?
3. (crit 4) CLAUDE.md surviving sections: which stay, which move to standards?
4. (crit 5) `/n` skill mechanics: edit plugin file or local override?
5. (crit 6) `.claude/current-feature` paused entries: close-abandoned / convert / delete per entry?
6. (crit 8) Feature-doc full inventory + disposition.
7. (crit 15) Directive granularity: hard cap or soft? what number?
8. (crit 16) Per-directory R16 targets: what values per directory?
9. (crit 16) Baseline update on refactor directives: mechanism shape?
10. (crit 17) "Touched function" definition: whole rewrite vs any diff line?
11. (crit 20) Plan-review expert selection: default architect-only? auto-detect?
12. (crit 20) Plan-review output captured in directive or just transcript?
13. (crit 21) Code-review expert selection mechanism?
14. (crit 36) Pain-point walk for additional judgment standards.
15. (crit 37) Hook script length target.
16. (crit 41) Memory entry walk + disposition.

### Files

<a id="files"></a>

This list is TENTATIVE -- changes during flesh-out as we resolve OPENs.

```
.claude/directive.md                                    -- THIS doc
.claude/standards/index.md                              -- EDIT: add judgment-section, R16/R17/R18, refactor-directive entry
.claude/standards/mechanical/R*.md                      -- NEW: one file per R-rule (extracted from hook + standards/index.md)
.claude/standards/judgment/*.md                         -- NEW: one file per named principle
.claude/standards/file-size-targets.json                -- NEW: per-directory R16 targets
.claude/rules/                                          -- DELETE entire directory after fold (criterion 1)
.claude/hooks/pre-edit-standards.ps1                    -- EDIT: load rules from files, add R16/R17/R18, add review-gate checks
.claude/hooks/session-start-ceo.ps1                     -- EDIT: initialize baseline file if missing
.claude/.file-baselines.json                            -- NEW (gitignored): per-file line-count baselines
.gitignore                                              -- EDIT: add .file-baselines.json
CLAUDE.md                                               -- EDIT: thin orient (~50 lines)
MEMORY.md                                               -- EDIT: prune entries duplicated by judgment standards
Scripts/Directives/WhatTouchedThis.py                   -- NEW: code -> directive reverse-index helper
Scripts/Directives/ConversionDebt.py                    -- NEW: file-size debt table
Features/**/*.feature.md                                -- DELETE or MIGRATE per criterion 8 inventory
WorkerService/worker-lifecycle.feature.md               -- DELETE or MIGRATE per inventory
Scripts/Smoke/EncoderShootout.feature.md                -- DELETE or MIGRATE per inventory
.claude/directives/closed/YYYY-MM-DD-<slug>.md          -- NEW: one per converted feature doc
.claude/directives/_template.md                         -- EDIT: align with new shape if needed
.claude/directives/_template-refactor.md                -- NEW: refactor-directive template
.claude/current-feature                                 -- DELETE per criterion 6
```

### Verification (filled during VERIFYING phase)

<a id="verification"></a>

Per criterion -- to be recorded here when each one passes.

### Closure

<a id="closure"></a>

Closure is gated on all criteria + the doc supersession sweep (criterion 8-11 capture this directly).

After close: pull `nvenc-rate-anchored-remediation` and `ceo-mode-enforcement` back to active in fresh sessions, each running against the unified shape.

---

## Working notes

<a id="working-notes"></a>

Free-form area for flesh-out scratch. Move resolved items to the appropriate criterion + strike from `### Open questions`.

### Flesh-out queue (next session priorities)

- Pain-point catalogue walked (criterion 36): determines size of judgment-standards section.
- Feature-doc inventory (criterion 8): determines size of migration sweep.
- Memory walk (criterion 41): determines cleanup scope.

These three are the highest-leverage flesh-outs because they bound the size of the directive. Once we know "N judgment standards, M feature docs to migrate, K memory entries to clean," the directive's size and shape lock.

### External adoptions locked

**superpowers** ([obra/superpowers](https://github.com/obra/superpowers)) -- workflow layer. Install: `/plugin install superpowers@claude-plugins-official`. Provides skills: brainstorming, writing-plans, test-driven-development, subagent-driven-development, requesting-code-review, using-git-worktrees. Maps to MediaVortex layer as:
- brainstorming -> drives NEEDS_PLAN criteria-drafting
- writing-plans -> shape of the directive doc's criteria + files + verification sections (we extend with CEO-mode-specific Escalation Defaults + Engineering Calls Already Made + closure block)
- subagent-driven-development -> the dispatcher pattern under plan-review and code-review gates
- requesting-code-review -> the IMPLEMENTING -> VERIFYING gate skill
- test-driven-development -> optional discipline, not phase-gated
- using-git-worktrees -> optional for parallel exploration, not phase-gated

**Karpathy 4 rules** ([multica-ai/andrej-karpathy-skills](https://github.com/multica-ai/andrej-karpathy-skills)) -- CLAUDE.md base. Lifted verbatim into our CLAUDE.md during IMPLEMENTING phase. Source content stashed below.

### Karpathy CLAUDE.md content (locked, source for merge)

The following block is the verbatim source for the rules section of our merged CLAUDE.md. During IMPLEMENTING, this block lifts wholesale into `CLAUDE.md`, followed by MediaVortex-specific pointers (standards index, flow docs, directives/closed/, naming conventions, commands).

```markdown
# Behavioral guidelines (Karpathy-derived)

Behavioral guidelines to reduce common LLM coding mistakes. Merge with project-specific instructions as needed.

**Tradeoff:** These guidelines bias toward caution over speed. For trivial tasks, use judgment.

## 1. Think Before Coding

**Don't assume. Don't hide confusion. Surface tradeoffs.**

Before implementing:
- State your assumptions explicitly. If uncertain, ask.
- If multiple interpretations exist, present them - don't pick silently.
- If a simpler approach exists, say so. Push back when warranted.
- If something is unclear, stop. Name what's confusing. Ask.

## 2. Simplicity First

**Minimum code that solves the problem. Nothing speculative.**

- No features beyond what was asked.
- No abstractions for single-use code.
- No "flexibility" or "configurability" that wasn't requested.
- No error handling for impossible scenarios.
- If you write 200 lines and it could be 50, rewrite it.

Ask yourself: "Would a senior engineer say this is overcomplicated?" If yes, simplify.

## 3. Surgical Changes

**Touch only what you must. Clean up only your own mess.**

When editing existing code:
- Don't "improve" adjacent code, comments, or formatting.
- Don't refactor things that aren't broken.
- Match existing style, even if you'd do it differently.
- If you notice unrelated dead code, mention it - don't delete it.

When your changes create orphans:
- Remove imports/variables/functions that YOUR changes made unused.
- Don't remove pre-existing dead code unless asked.

The test: Every changed line should trace directly to the user's request.

## 4. Goal-Driven Execution

**Define success criteria. Loop until verified.**

Transform tasks into verifiable goals:
- "Add validation" -> "Write tests for invalid inputs, then make them pass"
- "Fix the bug" -> "Write a test that reproduces it, then make it pass"
- "Refactor X" -> "Ensure tests pass before and after"

For multi-step tasks, state a brief plan:
1. [Step] -> verify: [check]
2. [Step] -> verify: [check]
3. [Step] -> verify: [check]

Strong success criteria let you loop independently. Weak criteria ("make it work") require constant clarification.

**These guidelines are working if:** fewer unnecessary changes in diffs, fewer rewrites due to overcomplication, and clarifying questions come before implementation rather than after mistakes.
```

### Overlap with existing MediaVortex scope-discipline.md

Karpathy rules 2 and 3 substantially overlap with `.claude/rules/scope-discipline.md`. During IMPLEMENTING, decide whether scope-discipline.md is folded into CLAUDE.md (since the 4 rules cover most of it) OR stays as a deeper standards-layer doc that scope-discipline.md becomes after editing. Likely the latter: CLAUDE.md gets the 4 high-level rules + pointer to scope-discipline.md for the task-contract shape and pre/post checks.

### Workflow-layer overlap reductions to claim

After superpowers adoption, the destination directive's scope reduces by:
- Sections F (review gates): adopt superpowers code-review; we just gate phase advance on its invocation
- Section H (hook + state machine): only the phase-gate enforcement and content rules (R1-R18) stay MediaVortex-custom; the brainstorm/plan/review workflow comes from superpowers
- Section B (workflow consolidation): one `/n` that wraps superpowers brainstorming for criteria + writes directive shape; significantly smaller than hand-rolled

Net: maybe 25-30% of the destination directive's planned criteria become "adopt superpowers skill X for criterion Y" instead of "build mechanism Z." Lower implementation cost, fewer OPENs to resolve.
