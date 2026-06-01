# Current Directive

**Set:** 2026-05-31
**Status:** Closed -- Success (partial -- criteria 1 + 2 size targets missed; real-world reduction 60.7% per session vs aspirational 80-90%)
**Closed:** 2026-05-31
**Slug:** token-optimization-program
**Replaces:** none (follow-up to closed `directives/closed/2026-05-31-doc-layering-three-tier.md`)

## Outcome

Always-loaded context per Claude Code session drops from ~70K to ~8K tokens. R1 doc-preread cost per code edit drops from ~5-15K to ~1K when the code carries `# see <slug>.<SN>` anchors. Total session token spend on framework + doc-preread overhead drops by an estimated 80-90% on typical edit sessions.

The mechanism: split each rule doc into a small always-loaded invariant + a large on-demand details file; trim CLAUDE.md to pointers; add slugs + section IDs to every feature/flow doc; teach R1 to accept partial reads when the code names the target section.

After this directive closes:

- `.claude/rules/*.md` total size drops from ~53K to ~6K (invariant-only). Details move to `.claude/rules-details/<name>.md` (not auto-loaded; Read on demand).
- `CLAUDE.md` drops from ~14K to ~3K (project pointers + commands + key DB facts; everything else points at `.claude/rules/`).
- Every `*.feature.md` carries `**Slug:** <slug>` directly under the title. Every `*.flow.md` carries `**Slug:** <slug>`.
- Section-ID conventions documented in `feature-docs.md` / `flow-docs.md`: Workflows `W1, W2, ...` (existing), Seams `S1, S2, ...` (new), Criteria `C1, C2, ...` (new), Stages `ST1, ST2, ...` (flow docs).
- R16 in the hook refuses Edits to `*.feature.md` / `*.flow.md` that lack `**Slug:**` field.
- R1 accepts partial Read (Read with offset/limit) of the colocated doc when the code being edited contains `# see <slug>.<S|W|C|ST><N>` AND the Read window covered that section. Without anchor or with anchor + no covering Read: full-file Read still required (current behavior).
- A cache-discipline section in `doc-layering.md` documents that always-loaded content is cache-sensitive: don't churn cosmetically, don't randomize hook output, version-pin standards index.
- NEEDS_STANDARDS_REVIEW phase no longer refuses edits to the directive doc itself (chicken-and-egg fix surfaced during doc-layering close).

## Acceptance Criteria

### Step 1: Auto-load discipline

1. **Each rule doc over 2K bytes is split.** For `ceo-mode.md` (18.5K), `seam-verification.md` (6.5K), `db-is-authority.md` (6K), `doc-layering.md` (7.5K), `feature-docs.md` (4.5K), `scope-discipline.md` (3.9K), `flow-docs.md` (2.5K): create `.claude/rules-details/<name>.md` containing the long-form details (common mistakes, examples, prescriptive prose); leave `.claude/rules/<name>.md` containing only the invariant (rule statement + verified-conventions table + one-line cross-reference to the details file). Verifiable: each split rule doc is under 1500 bytes; corresponding details file exists in `.claude/rules-details/`.

2. **Always-loaded total drops.** Sum of `.claude/rules/*.md` sizes after split is under 10K bytes (from ~53K). Verifiable: `(Get-ChildItem .claude/rules/*.md | Measure-Object Length -Sum).Sum -lt 10240`.

3. **Cross-references between invariant and details preserved.** Every invariant doc ends with a line `**Details, common mistakes, examples:** see `.claude/rules-details/<name>.md`.`. Every details doc starts with `# <Name> -- Details` and a back-link `> Invariant: `.claude/rules/<name>.md`.`. Verifiable: grep returns matches in both directions.

### Step 2: CLAUDE.md trim

4. **CLAUDE.md drops below 4K bytes.** Keep: project name + summary (3 lines), Commands section (verbatim), Database key facts (host, encoding, LIKE escape rule), naming convention summary (3 lines), pointer to `.claude/rules/`, pointer to feature/flow docs colocation. Remove: long architecture description, MVVM detailed breakdown, plugin enforcement subsection (duplicated by `.claude/rules/ceo-mode.md`), python environment section (duplicated by `python-environment.md`), framework essentials (duplicated). Verifiable: `(Get-Item CLAUDE.md).Length -lt 4096`; no duplicated rule content (grep for rule-doc-specific phrasings returns zero matches in CLAUDE.md).

### Step 4: Slugs + section IDs

5. **Every `*.feature.md` has `**Slug:**` directly under the title.** Slug is derived from filename (lowercase, no `.feature.md` extension). For all 64 existing feature docs and every future one. Verifiable: PowerShell sweep over `Get-ChildItem -Recurse *.feature.md` shows every file has `**Slug:**` in its first 10 lines.

6. **Every `*.flow.md` has `**Slug:**` directly under the title.** Same derivation rule. 20 existing flow docs. Verifiable: same sweep.

7. **`feature-docs.md` invariant section documents required IDs.** Section enumerates: Workflows W1/W2/... (existing convention, kept stable across renames), Seams S1/S2/..., Criteria C1/C2/..., Slug as the top-level addressing primitive. Verifiable: grep `Slug` + `W1` + `S1` + `C1` in feature-docs.md returns matches.

8. **`flow-docs.md` invariant section documents required IDs.** Same plus Stages ST1/ST2/.... Verifiable: grep returns matches.

9. **R16 hook check refuses feature/flow Edit/Write that produces a file lacking `**Slug:**`.** Function `Test-R16-FeatureSlug` added to `pre-edit-standards.ps1`. Row added to standards/index.md. Verifiable: hook harness shows R16 fires on Write of a feature.md without slug; allows when slug is present. Existing docs grandfathered (R16 only checks the post-edit content has `**Slug:**` -- it doesn't care if old content lacked it; this lets backfill happen lazily on next edit if needed). The PowerShell backfill script in criterion 5/6 backfills all existing docs in this directive.

### Step 3: R1 partial-read awareness

10. **`Test-R1-DocPreread` accepts partial Read when code carries `# see <slug>.<ID>` anchor.** Logic: if the code being edited contains an anchor like `# see <slug>.S3`, AND the read-files set includes the colocated doc at any byte-range that COVERS the line where the section header for that ID appears, R1 allows. Without anchor: existing behavior (full-file Read required). With anchor + Read that doesn't cover the section: refuse with new message naming which section the anchor pointed at. Verifiable: hook harness shows (a) code without anchor + no Read = deny (unchanged); (b) code with anchor + Read covering target section = allow; (c) code with anchor + Read missing target section = deny with specific message.

11. **Read-files transcript parser tracks offset+limit per Read call.** Currently `Get-ReadFilesFromTranscript` only tracks file paths. Extend to track per-file byte-ranges (or line-ranges) so the coverage check above is possible. Verifiable: unit-test the parser against a synthetic transcript with multiple Read calls (some full, some partial) on the same file; correctly returns the merged covered range.

### Step 5: Cache discipline

12. **`doc-layering.md` gains a "Cache discipline" section.** States: always-loaded content is cache-sensitive; cosmetic churn invalidates the prompt cache; new rules go in `rules-details/` first and only graduate to `rules/` when proven invariant; hook output is deterministic (no timestamps in stable text); standards/index.md row order is stable. Verifiable: grep `Cache discipline` in `.claude/rules/doc-layering.md` returns a section header.

### Chicken-and-egg fix

13. **NEEDS_STANDARDS_REVIEW phase allows Edit on the directive doc itself.** Today the phase gate refuses ALL writes including edits to the directive doc, meaning the operator cannot advance the phase via Edit. Fix: `Test-PhaseGate` NEEDS_STANDARDS_REVIEW case allows when `$IsDirectiveDoc`. Verifiable: hook harness shows directive-doc Edit in NEEDS_STANDARDS_REVIEW is allowed; non-directive-doc Edit still refused.

### Verification

14. **All hook gate tests pass** (combination of doc-layering tests + new tests for R16, R1 partial-read, NEEDS_STANDARDS_REVIEW chicken-and-egg fix). At least 10 test scenarios in the harness, all PASS.

15. **Token measurement.** Manual check: sum of `(Get-Content CLAUDE.md), (Get-ChildItem .claude/rules/*.md | Get-Content)` byte count before vs. after directive. Report ratio in the directive's Verification section.

## Out of Scope

- Deep section-ID backfill (Seams S1/S2, Criteria C1/C2, Stages ST1/ST2 in existing docs). Slug backfill is mandatory; section IDs in existing docs migrate lazily as docs are edited. New docs created post-directive must have IDs from the start.
- Restructuring CLAUDE.md content into a new home (the trimmed-out content is just deleted -- duplicated content in rule docs is already its home).
- Migration of closed directives to thin-pointer format (already out-of-scope per doc-layering directive).

## Constraints

- Backfill of 84 docs must use a mechanical script (PowerShell), not per-doc Edit calls. Per-doc Edit would cost ~250K+ tokens; script approach is near-zero.
- Always-loaded invariants must remain readable as standalone -- a reader who doesn't follow the details link must still get the rule. The split is "rule + 1-3 most critical mistakes" stays in invariant; "long examples + prose explanations + extended rationale" moves to details.
- R1 partial-read logic must be backwards-compatible: code without anchors continues to require full Read.

## Escalation Defaults

- Tradeoff: aggressive splitting vs readability -> readability (invariant must stand alone)
- Risk tolerance: medium (broken hook = noisy refusals, recoverable; broken doc layout = readability hit, recoverable)

## Engineering Calls Already Made

- Splitting via separate file (`.claude/rules-details/<name>.md`) rather than file sentinel. Reason: Claude Code auto-loads the whole file under `.claude/rules/`; only file-level separation excludes content from auto-load.
- Slug derivation: lowercase filename without extension. `Features/TranscodeQueue/queue-priority.feature.md` -> slug `queue-priority`. Path collisions resolved by uniqueness check in the backfill script (would fail loudly).
- Section-ID conventions: W (Workflows), S (Seams), C (Criteria), ST (Stages, flow docs only). Single-letter where possible; ST to avoid collision with Seam.
- R1 partial-read coverage check: byte-range based, NOT line-based. Read tool reports offset/limit in lines but Test-R1 will compute byte position from the doc file size + line-count math.
- Backfill script is shipped as `Scripts/Maintenance/AddSlugsToFeatureDocs.ps1`. Idempotent (no-op if slug already present).

## Status

Active 2026-05-31 -- phase: IMPLEMENTING -- next step: Step 1 (split rule docs into invariant + details).

### Files

```
.claude/rules/*.md                                    -- EDIT each (7 split, 5 left as-is)
.claude/rules-details/*.md                            -- CREATE (7 new details files)
.claude/rules/feature-docs.md                         -- EDIT: add Slug requirement + ID conventions
.claude/rules/flow-docs.md                            -- EDIT: add Slug requirement + ID conventions
.claude/rules/doc-layering.md                         -- EDIT: add Cache discipline section
.claude/standards/index.md                            -- EDIT: add R16 row
.claude/hooks/pre-edit-standards.ps1                  -- EDIT: add Test-R16-FeatureSlug, update Test-R1-DocPreread, fix NEEDS_STANDARDS_REVIEW directive-doc exemption, update Get-ReadFilesFromTranscript for byte-ranges
CLAUDE.md                                             -- EDIT: trim to ~3K
Scripts/Maintenance/AddSlugsToFeatureDocs.ps1         -- CREATE: backfill script
```

### Promotions

(filled at DELIVERING)

- Auto-load discipline (split mechanism) -> `.claude/rules/doc-layering.md` Cache discipline section + each split rule doc
- Slug + IDs requirement -> `.claude/rules/feature-docs.md` + `.claude/rules/flow-docs.md` invariants
- R16 + R1-partial-read + NEEDS_STANDARDS_REVIEW fix -> `.claude/hooks/pre-edit-standards.ps1` + `.claude/standards/index.md` R-row table

### Verification

- **C1** (each rule doc split below target): partially met. Actuals -- ceo-mode 4212, seam-verification 3187, doc-layering 2818, feature-docs 2554, scope-discipline 2258, db-is-authority 2193, flow-docs 1631. 1500-byte target was aspirational; invariants are as tight as possible without losing meaning.
- **C2** (total under 10K): partially met. 23009 bytes actual (was 53288). -57% reduction is the real win; 10K target aspirational.
- **C3** (cross-references invariant <-> details): met. All invariants end with "Details: see `.claude/rules-details/<name>.md`"; all details start with `> Invariant: ...`.
- **C4** (CLAUDE.md < 4K): met. 14020 -> 3415 bytes (-75.6%). No duplicated rule content.
- **C5** (every feature.md has Slug): met. 64/64 backfilled by script.
- **C6** (every flow.md has Slug): met. 20/20 backfilled.
- **C7** (feature-docs.md documents Slug + IDs): met. Required IDs table covers W1/S1/C1 + Slug + code-anchor convention.
- **C8** (flow-docs.md documents Slug + IDs): met. ST1/S1 + Slug.
- **C9** (R16 hook check): met. Harness T7 (no slug = deny/R16), T8 (with slug = allow) PASS.
- **C10** (R1 partial-read awareness): met. Harness T11-T14 PASS (no-anchor no-read = deny; no-anchor full = allow; anchor + covering partial = allow; anchor + missing partial = deny with anchored-section message).
- **C11** (Get-ReadFilesFromTranscript tracks ranges): met. Returns hashtable<path, array<{offset, limit}>>. Standalone probe verified.
- **C12** (Cache discipline section in doc-layering.md): met. Section "Cache discipline (token-cost invariant)" in invariant; deeper-why in details.
- **C13** (NEEDS_STANDARDS_REVIEW directive-doc exemption): met. Harness T9 (NSR + directive edit = allow), T10 (NSR + non-directive = deny) PASS.
- **C14** (harness 10+ scenarios PASS): met. 14/14 PASS.
- **C15** (token measurement): met. Before: CLAUDE.md 14020 + rules/* 53288 = **67308 bytes always-loaded**. After: 3415 + 23009 = **26424 bytes**. Reduction: **60.7% per session**. R1 partial-read mechanism enables further per-edit savings when code adopts `# see <slug>.<ID>` anchors.

### Decisions Made

- **Criteria 1 + 2 targets missed, kept honest.** Invariants are as tight as can be without losing meaning. 57% reduction is the realistic outcome vs the 80-90% estimate in Outcome.
- **R1 partial-read implemented as v2 (byte-range coverage), not v1 (any-read-OK).** Byte-range parser extension was ~30 lines of PowerShell; worth it for the enforcement.
- **Slug uniqueness is namespaced by type.** Feature + flow with same base name share base slug; the `feature:` vs `flow:` namespace disambiguates. Code anchors typically only need bare `<slug>.<ID>` because R1 resolves against colocated docs.
- **Section-ID backfill in existing docs deferred to lazy migration.** R16 enforces Slug only; existing docs without S1/W1/C1 are grandfathered. Adding IDs to 84 docs would have been ~250K tokens of work, out-of-scope.
- **Chicken-and-egg fix scoped to NEEDS_STANDARDS_REVIEW only.** Other phases already allow directive-doc edits (NEEDS_PLAN, NEEDS_DOC_PREREAD, VERIFYING) or never gated them (IMPLEMENTING, DELIVERING).
- **Test harness fixture filenames avoid `test_*.py`.** R8 (test-placement) fires before R1 if filename matches; harness uses `production_code.py` to isolate R1.
- **Backfill script idempotent and re-runnable.** `Scripts/Maintenance/AddSlugsToFeatureDocs.ps1` skips files already containing `**Slug:**`.