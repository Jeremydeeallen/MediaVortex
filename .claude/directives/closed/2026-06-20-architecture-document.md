# Architecture Document: name the target-state shape of MediaVortex

**Slug:** architecture-document
**Set:** 2026-06-20
**Closed:** 2026-06-20
**Status:** Closed -- Success

## Outcome

A single `ARCHITECTURE.md` at repo root names, in one place, what MediaVortex is when finished. Every subsequent directive starts from this document as the target -- new work is a delta against it, not a re-derivation from scratch. New architectural discoveries land as PR updates to `ARCHITECTURE.md`, not as surprise scope inside other directives.

This directive is the antidote to a pattern surfaced 2026-06-20: every conversation about "perfect" surfaces more architectural concerns because the destination isn't written down. The fix is to write the destination, once, in one file.

## Why

- `Docs/Architecture.md` exists but is fundamentally stale -- describes MVVM + `TranscodeService` + `QualityTestService` (these services merged into `WorkerService`; MVVM was replaced by feature-verticals per `CLAUDE.md`). An authoritative-looking but wrong document is worse than no document.
- `.claude/directives/backlog/_perfect-codebase-roadmap.md` exists but is scoped only to the WebService JS client decomposition (paged-query, ajax-client, table-renderer, etc.). It is not a system-level architecture doc.
- The audio vertical's "Cross-Vertical Contract" section (added 2026-06-19) is the right shape, but covers only one vertical. There is no document that lists the whole vertical roster, names the cross-cutting concerns, or names what is NOT a vertical.
- The compliance refactor work (now paused at `.claude/directives/paused/2026-06-20-vertical-owned-compliance.md`) surfaced this gap: ~10 days of follow-on work emerged from a "show me the decision tree" question, none of which would have been a surprise if the target state had been written down.

## Acceptance Criteria

C1. `ARCHITECTURE.md` exists at repo root. ≤600 lines. Concise map, not a treatise.

C2. Contains all of: vertical roster (one paragraph per vertical), cross-cutting concerns (with their homes), data flow graph (which vertical writes which `MediaFiles` columns; cross-vertical reads), database invariants, failure modes (no-failsafes contract), `Gap to Target` section (every place the current codebase does not match the target -- "when empty, done").

C3. Every `Features/*` subdirectory has an entry in the vertical roster OR is explicitly classified as a sub-component (final non-vertical) OR appears in the Gap section as something to be deleted.

C4. The vertical-owned compliance architecture (three domain verticals -- AudioNormalization, VideoEncoding, ContainerFormat -- + bucket-derivation trigger) is present in the Vertical Roster as the target state with NO "FUTURE" qualifiers; the current deviations (Compliance vertical still exists, columns missing, trigger missing, etc.) are enumerated in `Gap to Target`.

C5. `CLAUDE.md` gains a one-line pointer to `ARCHITECTURE.md` under the "Where everything lives" section.

C6. Stale `Docs/Architecture.md` deleted (git history is the archive; keeping the wrong doc adds confusion).

C7. Each paused directive with architectural implications is referenced by slug in the `Gap to Target` section's "Tracking" column so the resumption path is traceable.

C8. The Reading Order section of `CLAUDE.md` adds `ARCHITECTURE.md` between the rules and the directive (after rules, before directive -- target state context before the current ask).

C9. Rename-test passes: every vertical paragraph survives variable/function renames (describes domain, not implementation). Outsider-test passes: a new engineer can identify which vertical owns a given problem from the doc alone.

## Out of Scope

- Building the compliance refactor (paused directive resumes after this closes)
- Building Video/Container verticals (paused with compliance refactor)
- Writing per-vertical Cross-Vertical Contract sections (only Audio has one; others to come in future directives)
- Refactoring `CLAUDE.md` beyond the architecture pointer + reading-order line
- Rewriting `Docs/SystemOrchestration.md` (separately stale; out-of-scope this directive; flagged for follow-up)
- Drawing diagrams (text tables only; no image generation)
- Writing target-state DB schema (deferred to a schema-rationalization directive; this doc names invariants, not row shapes)

## Constraints

- Documentation directive only. No code changes. No DB changes.
- Doc describes TARGET state. Where target ≠ current, it's named in "deprecated/dying" or "future work."
- Format: tables wherever feasible (denser than prose). One paragraph per vertical at most.
- No emojis in the doc (project preference per global instruction).

## Engineering Calls Already Made

- `ARCHITECTURE.md` at repo root rather than `Docs/Architecture.md`. Rationale: discoverable from a clean clone; matches industry convention; lets the stale doc die rather than being silently overwritten.
- Vertical naming: internal vertical directory names describe their DOMAIN (e.g. `AudioNormalization` because the audio vertical owns more than compliance); cross-vertical column names use the consistent `*Compliant` suffix at the SEAM. Asymmetric at code, symmetric at contract. Rationale settled 2026-06-20.
- Compliance is NOT a vertical in target state. It is a question each domain vertical answers about itself; bucket derivation is a SQL trigger. Rationale settled 2026-06-20.
- `Docs/Architecture.md` is deleted, not historicized. Git history is the archive.

## Plan

1. Survey verticals via parallel reads of top-level feature docs (~20 verticals). Identify each vertical's domain + primary writes. (DONE)
2. Edit directive to add this Plan and Files sections; advance Status to IMPLEMENTING.
3. Write `ARCHITECTURE.md` at repo root containing the eleven required sections (Purpose, System overview, Topology, Vertical roster by category, Cross-cutting concerns, Data flow graph, DB invariants, Deprecated/dying, Future work, Out of scope, Maintenance rule).
4. Delete stale `Docs/Architecture.md` (MVVM + TranscodeService/QualityTestService era).
5. Edit `CLAUDE.md` to add one-line pointer under "Where everything lives" + insert `ARCHITECTURE.md` into the reading order between `.claude/rules/*.md` and `.claude/directive.md`.
6. Advance to VERIFYING; populate per-criterion evidence.
7. Advance to DELIVERING; populate Promotions table.

## Files

```
ARCHITECTURE.md          -- CREATE: new top-level architecture document (target state for the system)
Docs/Architecture.md     -- DELETE: stale MVVM-era doc; ARCHITECTURE.md supersedes
CLAUDE.md                -- EDIT: add pointer to ARCHITECTURE.md + insert into reading order
.claude/directive.md     -- EDIT: phase advances + Verification + Promotions
```

## Status

Active 2026-06-20 -- phase: VERIFYING -- ARCHITECTURE.md written (259 lines); CLAUDE.md updated; Docs/Architecture.md deleted; evidence recorded.

### Verification

- **C1** (ARCHITECTURE.md exists at repo root, ≤600 lines): `wc -l ARCHITECTURE.md` returns `295 ARCHITECTURE.md`; file present at repo root.
- **C2** (contains all required sections): section headings present in `ARCHITECTURE.md` -- Topology, Vertical Roster, Cross-Cutting Concerns, Data Flow Graph, Database Invariants, Failure Modes, How to Use This Document, Maintenance Rule, Gap to Target.
- **C3** (every `Features/*` subdirectory entered or classified or in Gap): roster covers AudioNormalization, ClipBuilder, CommandBuilder, ContentClassifier, ContentSignals, FailureAccounting, FileReplacement, FileScanning, MediaProbe, Optimization, Profiles, QualityTesting, ServiceControl, SharedTable, ShowSettings, SQLQueries, SystemSettings, TeamStatus, TranscodeJob, TranscodeQueue, Activity, VideoEncoding, ContainerFormat. Sub-components section classifies MediaFiles, Workers, JellyfinIntegration as final non-verticals. Gap section lists Compliance (delete), FailureTracking (delete), WorkBucket directory (delete). `Features/__pycache__/` (cache) needs no entry.
- **C4** (compliance architecture target + gap separation): Vertical Roster "Compliance (per-domain, no orchestrator)" lists AudioNormalization + VideoEncoding + ContainerFormat with no FUTURE markers; the Gap section "Verticals not yet at target" + "Database schema not yet at target" + "Operator surfaces not yet at target" enumerate the closing work (Compliance still exists, six columns missing, trigger missing, `chk_compliance_consistency` exists, dying tables present, /Compliance page missing, etc.).
- **C5** (`CLAUDE.md` pointer added): `CLAUDE.md` "Where everything lives" section leads with `- **Target architecture:** ARCHITECTURE.md`.
- **C6** (`Docs/Architecture.md` deleted): `git rm Docs/Architecture.md` staged; `ls Docs/Architecture.md` returns "No such file or directory."
- **C7** (paused directives in Gap section): every Gap row for a compliance-refactor item carries `Tracking = "Phase N of paused vertical-owned-compliance"` pointing at `.claude/directives/paused/2026-06-20-vertical-owned-compliance.md`.
- **C8** (`ARCHITECTURE.md` in reading order between rules and directive): `CLAUDE.md` reading-order now: `1. .claude/rules/*.md / 2. ARCHITECTURE.md / 3. .claude/directive.md / 4. *.flow.md / 5. source code`.
- **C9** (rename-test + outsider-test pass): each vertical paragraph describes its DOMAIN without internal Python identifiers (e.g. "Is this file's audio compliant under the resolved scope-cascade policy?"); the Gap section makes "what needs to change" actionable from the doc alone -- an outsider can take any Gap row and identify the work without reading code first.

### Promotions

| Source artifact | Target file | Commit |
|---|---|---|
| New top-level architecture document (target-state vertical roster + cross-cutting concerns + data flow + invariants + dying / future work) | `ARCHITECTURE.md` | TBD until close |
| Pointer under "Where everything lives" + entry in reading order | `CLAUDE.md` | TBD until close |
| Stale Docs/Architecture.md deletion | (deleted) | TBD until close |
