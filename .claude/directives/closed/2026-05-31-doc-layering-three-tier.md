# Current Directive

**Set:** 2026-05-31
**Status:** Closed -- Success
**Closed:** 2026-05-31
**Slug:** doc-layering-three-tier
**Replaces:** none (meta-framework work, parallel to product directives)

## Outcome

The three-tier documentation model is a named, stated invariant in this repo: directive = transient ask, `*.feature.md` = durable vertical contract (intra-feature seams), `*.flow.md` = durable pipeline contract (cross-stage seams). The model is enforced where mechanizable and cross-referenced where it isn't.

After this directive closes:

- `.claude/rules/doc-layering.md` exists as the keystone invariant. `ceo-mode.md`, `feature-docs.md`, and `flow-docs.md` reference it instead of re-deriving the boundaries.
- R13 ("no new `*.feature.md` / `*.flow.md` files") is reframed as "no premature feature/flow docs" -- creation is allowed during the DELIVERING phase only. The hook code matches.
- The directive template carries a required `## Promotions` section listing every piece of durable content + its target home (feature/flow file).
- The closed-directive archive format is thin-pointer: Outcome + Criteria + Promotions + Verification + Decisions-Made. Design rationale promoted into features/flows on close; the archive does not duplicate it.
- The PreToolUse hook refuses any Edit that transitions directive Status from `Active -- phase: DELIVERING` to `Closed` unless the `## Promotions` section is present and non-empty, and the directive did not grow during DELIVERING (anti-drift size check via snapshot recorded at IMPLEMENTING -> DELIVERING transition).
- `flow-docs.md` terminology confirmed as "cross-stage" (already correct; no change needed beyond cross-referencing doc-layering.md).

## Acceptance Criteria

1. **`.claude/rules/doc-layering.md` exists.** Single page. States the three-tier model (directive / feature / flow) with role + durability + seam-ownership columns. Verifiable: file exists; section headings match the model; cross-references from `ceo-mode.md`, `feature-docs.md`, `flow-docs.md` resolve to anchors in this file.

2. **R13 row in `.claude/standards/index.md` is reframed.** Description now reads "New `*.feature.md` / `*.flow.md` files are refused outside DELIVERING phase. At DELIVERING, creation is allowed so durable content can be promoted out of the directive doc into its permanent home." Source column adds `doc-layering.md`. Verifiable: grep for the new wording in `.claude/standards/index.md`; the prior wording does not appear.

3. **`Test-R13-NoNewFeatureDocs` in `.claude/hooks/pre-edit-standards.ps1` is amended.** The check reads the current session phase (via `Get-SessionState`) and returns `null` (allow) when `$Phase -eq 'DELIVERING'`. Refusal text is updated to name the phase-aware behavior. Verifiable: function body shows the phase check; refusal message names DELIVERING as the allowed phase.

4. **`.claude/directives/_template.md` has a `## Promotions` section.** Section is templated with one example row showing `<durable content> -> <target file>` shape. Section header includes inline note that it is required at DELIVERING and gated by the hook. Verifiable: `grep '## Promotions' .claude/directives/_template.md` returns one match; the example row is present.

5. **`.claude/directives/_template.md` Closure section uses thin-pointer format.** Five sections after Closure-trigger: Outcome (restated), Criteria (restated), Promotions (pointers to target files + commit SHAs), Verification (per-criterion evidence), Decisions-Made (engineering calls). No design-content section. Verifiable: section headings in the Closure block match the five-section template; the prior "Doc supersession sweep" subsection is replaced (its job is now done by the Promotions table).

6. **`.claude/rules/flow-docs.md` references `doc-layering.md`.** A single line at the top of "Verified conventions" or "Required: `## Seams` section per flow" points at `doc-layering.md` as the higher-level invariant. The existing terminology (stage transition, cross-stage seams) is verified present and unchanged. Verifiable: grep `doc-layering.md` in flow-docs.md returns at least one match; grep `cross-stage` returns at least one existing match (no change needed there).

7. **`.claude/rules/feature-docs.md` references `doc-layering.md`.** Symmetric to criterion 6. Verifiable: grep `doc-layering.md` in feature-docs.md returns at least one match.

8. **`.claude/rules/ceo-mode.md` "Documents first" section references `doc-layering.md`.** Single-line pointer. The existing R13 / R14 wording is updated to match the reframed R13 (creation allowed at DELIVERING). Verifiable: grep `doc-layering.md` in ceo-mode.md returns at least one match; the "New `*.feature.md` / `*.flow.md` files are refused (R13)" line is updated.

9. **`.claude/hooks/pre-edit-standards.ps1` `Test-PhaseGate` adds a DELIVERING case that gates directive-close.** When the Edit changes Status from `Active -- phase: DELIVERING` to `Closed`, the hook refuses unless: (a) the post-edit directive content contains a non-empty `## Promotions` section, AND (b) a snapshot file `.claude/.delivering-snapshot.json` exists for this directive AND post-edit directive size is `<= snapshot size + tolerance`. If snapshot does not exist for this directive, the close is allowed (snapshot missing means the directive never transitioned cleanly through DELIVERING; the gate is best-effort). Verifiable: function code shows the DELIVERING case; a simulated close-without-promotions Edit is refused; a simulated close-with-promotions Edit is allowed.

10. **Snapshot recording on IMPLEMENTING -> DELIVERING transition.** When the Edit changes Status from `IMPLEMENTING` to `DELIVERING`, the hook writes `.claude/.delivering-snapshot.json` with `{slug, size_bytes, timestamp}` BEFORE returning allow. Verifiable: function code shows the snapshot write; simulated phase transition produces the snapshot file with the correct fields.

11. **All edits to `.claude/rules/` and `.claude/hooks/` and `.claude/standards/` and `.claude/directives/` are landed in a single commit at directive close.** Verifiable: `git log -1 --name-only` after close shows all touched paths in one commit.

## Out of Scope

- The paused `unified-standards-destination` directive's proposal that `*.feature.md` files cease to exist. This directive's three-tier model is compatible with that future, but does not require it.
- The paused `ceo-mode-enforcement` directive's broader phase-machine refinements. This directive only adds the DELIVERING gate; it does not refactor other phases.
- Promoting any existing `*.feature.md` / `*.flow.md` content. This directive establishes the model and tooling; the operator decides per-feature when to apply it.
- Migrating existing closed directives to thin-pointer format. New format applies to future closures.

## Constraints

- Mechanical phase gate must not break the current IMPLEMENTING phase: edits to `.claude/hooks/pre-edit-standards.ps1` itself in IMPLEMENTING must continue to pass (the file is in the .claude/* exempt path set; phase gate still applies but content rules don't).
- Snapshot file `.claude/.delivering-snapshot.json` is per-directive (keyed on slug). Older snapshots from prior directives can persist; the gate ignores snapshots whose slug does not match the active directive.
- Anti-drift size check is a soft guard: 10% growth tolerance. Aggressive enough to catch "wrote a new feature description into the closing directive," lenient enough to not refuse "added one verification line."

## Escalation Defaults

- Tradeoff: gate strictness vs operator friction -> lenient (allow close on missing snapshot; warn on growth, refuse only on missing Promotions section)
- Risk tolerance: medium (this is framework work; bad gates produce loud refusals that operator can fix in seconds)

## Engineering Calls Already Made

- `## Promotions` section format: markdown bulleted list of `<source artifact> -> <target file path>` rows. Optional commit-SHA column added at close. Hook only checks the section is present and non-empty -- does not parse the rows.
- Snapshot tolerance: 10% (1.10 * snapshot_size_bytes). Threshold encoded as constant at top of hook for easy adjustment.
- Phase-gate detection of `IMPLEMENTING -> DELIVERING`: hook re-reads the directive doc text from disk (before-edit state) and the synthesized post-edit content; compares the phase regex between the two. If transition matches, write snapshot.
- R13 phase check uses `Get-SessionState` (already defined in hook). When session state is absent, R13 falls back to the strict refusal (safer default).

## Status

Active 2026-05-31 -- phase: IMPLEMENTING -- next step: create `.claude/rules/doc-layering.md`, then amend `_template.md`, then amend standards/index.md, then amend hook script. Phase advances to VERIFYING after all 11 criteria have edits landed; DELIVERING after the simulated-close test passes; Closed after Promotions are committed.

### Files

```
.claude/rules/doc-layering.md                   -- CREATE: keystone invariant doc
.claude/rules/ceo-mode.md                       -- EDIT: cross-reference doc-layering.md; reframe R13 mention
.claude/rules/feature-docs.md                   -- EDIT: cross-reference doc-layering.md
.claude/rules/flow-docs.md                      -- EDIT: cross-reference doc-layering.md
.claude/standards/index.md                      -- EDIT: amend R13 row description + source
.claude/directives/_template.md                 -- EDIT: add ## Promotions section; restructure Closure to thin-pointer format
.claude/hooks/pre-edit-standards.ps1            -- EDIT: amend Test-R13-NoNewFeatureDocs (phase-aware); add DELIVERING case to Test-PhaseGate (promotions check + snapshot read); add snapshot write on IMPLEMENTING->DELIVERING
```

### Promotions

(filled at DELIVERING)

- doc-layering invariant -> `.claude/rules/doc-layering.md` (new file, commit: TBD)
- R13 phase-aware wording -> `.claude/standards/index.md` (commit: TBD)
- Promotions section + thin-pointer archive shape -> `.claude/directives/_template.md` (commit: TBD)
- DELIVERING phase gate + snapshot logic -> `.claude/hooks/pre-edit-standards.ps1` (commit: TBD)

### Verification

- **C1** (doc-layering.md exists): file written, 7544 bytes; sections present: three-tier table, Why three tiers, Lifecycle: directive -> features/flows (promotion), Lifecycle: feature/flow content removal, Archived directive shape, Common mistakes, Cross-references.
- **C2** (R13 row reframed in standards/index.md): `grep '^| R13' .claude/standards/index.md` returns the new wording: "No premature `*.feature.md` / `*.flow.md` files. Creation refused outside DELIVERING phase; at DELIVERING, creation is allowed so durable content can be promoted...". Source column lists `doc-layering.md`.
- **C3** (Test-R13 phase-aware): function body calls `Get-SessionState` and returns null when phase is DELIVERING. Refusal text names the phase and points at `doc-layering.md`. Verified by hook harness TEST 1 (IMPLEMENTING + new .feature.md = deny) and TEST 2 (DELIVERING + new .feature.md = allow).
- **C4** (Promotions in _template.md): `### Promotions` section present with note "Required when phase advances to DELIVERING. The hook refuses Status `Active -- phase: DELIVERING` -> `Closed` if this section is empty." Example row in source -> target -> commit shape.
- **C5** (Thin-pointer Closure): Closure section in _template.md shows five-section archive table (Outcome / Acceptance Criteria / Promotions / Verification / Decisions Made). Old "Doc supersession sweep" subsection removed; its job is now done by the Promotions table + R14 (annotation refusal).
- **C6** (flow-docs.md cross-reference): grep `doc-layering.md` returns 1 hit. Existing "cross-stage" terminology verified present (no change required).
- **C7** (feature-docs.md cross-reference): grep `doc-layering.md` returns 1 hit.
- **C8** (ceo-mode.md cross-reference + R13 wording updated): grep `doc-layering.md` returns 1 hit. "Documents first" section rewritten: refusal-outside-DELIVERING phrasing matches R13; Promotions gate + anti-drift size check both documented in step 2.
- **C9** (DELIVERING gate added to Test-PhaseGate): function body shows DELIVERING case checking (a) Promotions non-empty and (b) size <= 110% of snapshot. Verified by hook harness TEST 4 (close without Promotions = deny), TEST 5 (close with Promotions + matching snapshot = allow), TEST 6 (close, directive grew past tolerance = deny).
- **C10** (snapshot on IMPLEMENTING -> DELIVERING): IMPLEMENTING case in Test-PhaseGate writes `.claude/.delivering-snapshot.json` with slug + size_bytes + timestamp when post-edit content advances phase to DELIVERING. Verified by hook harness TEST 3 (snapshot file created, contains slug=doc-layering-three-tier and size_bytes=315 for the synthetic test directive).
- **C11** (single commit at close): TBD -- happens at close. Promotions table will be updated with commit SHA in the same step.

### Decisions Made

- 10% size-growth tolerance for the anti-drift check. Tight enough to catch "wrote a new feature description into the closing directive," lenient enough not to flag adding a verification line. Hard-coded as `1.10` constant in `Test-PhaseGate` for easy adjustment.
- Snapshot file `.claude/.delivering-snapshot.json` is per-directive, keyed on slug. Stale snapshots from prior directives are ignored (gate checks `$Snap.slug -eq $CurrentSlug`).
- `Get-SessionState` made directive-doc-authoritative for phase + slug (was reading stale session-state.json after intra-session phase advances). session-state.json now only contributes `session_started_at` for the refusal-repeat counter. This was load-bearing for both R13 phase-awareness and the DELIVERING gate to work in a single session.
- Promotions section content check uses heuristic "any non-placeholder line counts" rather than parsing rows -- the hook only enforces the section is populated, not the row shape. Row shape is enforced by the template, not the hook (operator-readable).
- `R13` refusal text refactored to name the current phase explicitly. Operator gets phase context in the refusal message, which is faster to debug than a generic "wrong phase" error.
- Did NOT add a `DELIVERING -> Closed` phase to the formal state machine table in standards/index.md beyond the gate description. Reason: Closed is not a phase claude operates in; it's the terminal state after archive. The gate fires during the Edit that performs the transition, which IS in DELIVERING phase.
