# Vertical-Owned Compliance: rip the compliance vertical, push policy into each vertical

**Slug:** vertical-owned-compliance
**Opened:** 2026-06-19
**Status:** Active -- phase: NEEDS_STANDARDS_REVIEW

## Outcome

Replace `Features/Compliance/` with a three-vertical model. Each vertical (Audio, Video, Container) owns one boolean column on `MediaFiles` that says "this file is compliant according to my rules." `WorkBucket` is materialized by a Postgres trigger from those three booleans via a single CASE expression. The compliance orchestrator, its 4 rule tables, its 9 gates, its 3-layer writeback defense, and the SubtitleFix vertical are all deleted in this directive. No shims, no migration period.

## Why

- Today's `Features/Compliance/` owns 4 rule tables that duplicate policy each operating vertical should hold. Audio policy already lives in `Features/AudioNormalization/` (cross-vertical contract section added 2026-06-19); Video and Container policy do not yet exist as verticals.
- The BUG-0062 three-layer writeback defense (constructor validator + repository validator + SQL CHECK) exists only because the orchestrator emits `ComplianceDecision` tuples that can be inconsistent. A Postgres trigger reading three boolean columns into one CASE cannot be inconsistent.
- SubtitleFix is disabled in production (`subtitlefixrules.enabled=FALSE`) and routes zero files; folding it forward is dead weight.
- The 30 Rock S01E01 routing bug (BPP 0.09 source incorrectly classified Transcode) is the canary for "video policy without BPP-awareness is wrong." This directive folds the IDEAS.md 2026-06-19 `MinSourceBpp` rule into the new Video vertical.

## Non-negotiables (operator-set)

1. **No failsafes.** Zero `try/except` that swallows a vertical's recompute exception. Zero defensive `or 0` defaults. Zero "WARN + continue" in new vertical code. A vertical's `RecomputeFor` that raises propagates to the scanner; the scanner fails the probe-completion handler loudly.
2. **No nondeterminism.** Zero `Enabled` toggles that silently disable a check. Zero `MvTrusted`-style special-case skips. Zero "return defaults when migration not run" repository fallbacks. A rule either applies to every file or it does not exist.
3. **Rip, not migrate.** `Features/Compliance/` is deleted in the same directive that brings up the three verticals. No shim. No compatibility re-export. No "removed YYYY-MM-DD" annotations.
4. **Clean documentation.** `compliance.feature.md` and `compliance.flow.md` are deleted. Each new vertical ships a feature doc with the cross-vertical contract section. `audio-normalization.feature.md` extended to add `AudioOk` to its WRITES list.
5. **Clean running system.** One-shot migration script runs at cutover: creates new columns + trigger, recomputes every MediaFile under the new model, drops old columns / tables / constraints. No long-running mixed-state period.

## Success Criteria

C1. `Features/Compliance/` directory absent. `grep -rn 'Features\.Compliance' Features/ WebService/ Scripts/ Tests/` returns 0 production hits. `compliance.feature.md` and `compliance.flow.md` deleted.

C2. Three boolean columns exist on `MediaFiles`: `AudioOk`, `VideoOk`, `ContainerOk`, each nullable. Each column is exclusively written from inside its owning vertical. `grep -rn 'AudioOk\s*=' --include='*.py'` returns paths only under `Features/AudioNormalization/`; analogous for the other two.

C3. `MediaFiles.WorkBucket` is materialized by a Postgres trigger reading the three boolean columns. No Python writes `MediaFiles.WorkBucket`. Trigger body is one CASE with at most 5 WHEN branches; total trigger function under 15 lines of SQL.

C4. Each vertical exposes ONE public entry point `<Vertical>VerticalRecompute.RecomputeFor(MediaFileIds: List[int]) -> None`. Scanner post-probe handler calls all three (in any order); trigger settles `WorkBucket`. No compliance orchestrator class exists.

C5. Each vertical's `*.feature.md` has a `## Cross-Vertical Contract` section parallel to `audio-normalization.feature.md` lines 236-335: WRITES, READS, public function entry points, HTTP routes, explicit NOT-a-contract items.

C6. Mid-flight DB rule edit observed by next file's recompute (`db-is-authority`). Per-vertical recompute reads rules fresh; no instance caching. `Tests/Contract/TestVerticalAuthority.py` covers Audio + Video + Container.

C7. No failsafes survive. Repo-wide grep returns 0 production hits for: `chk_compliance_consistency`, `ContradictoryDecisionError`, `OperationsNeededCsv`, `ComplianceGateBlocked`, `ComplianceEvaluatedAt`, `AudioFixRules`, `SubtitleFixRules`, `ComplianceGates`, `MvTrusted`. No `except` block in new vertical code catches the verticals' own `RecomputeFor` exceptions.

C8. Fail-loudly contract test: `Tests/Contract/TestFailLoudly.py` constructs a deliberately-broken MediaFile (e.g. probe missing Resolution) and asserts each vertical's `RecomputeFor` RAISES rather than writing NULL-with-a-warning. Scanner post-probe handler propagates the exception (does NOT log + continue).

C9. BPP-aware Video vertical: rules include `MinSourceBpp` (default 0.04). Contract test reproducing the 30 Rock S01E01 case (720p HEVC, BPP 0.09) asserts `VideoOk=TRUE` -- no transcode needed regardless of `EstimatedSavingsMB`.

C10. SubtitleFix is gone. `grep -rn 'SubtitleFix' Features/ WebService/ Scripts/ Templates/` returns 0 production hits. `SubtitleFixRules` table dropped. The 46 files with `HasForcedSubtitles=TRUE` settle into whatever bucket their three booleans yield.

C11. Old columns dropped: `MediaFiles.OperationsNeededCsv`, `MediaFiles.ComplianceGateBlocked`, `MediaFiles.ComplianceEvaluatedAt`. Old tables dropped: `SubtitleFixRules`, `ComplianceGates`, `AudioFixRules`. (The Transcode + Remux rule tables are dropped and replaced by per-vertical-owned tables under new names; see operator decision 3.)

C12. UI migration complete. `/api/Compliance/*` routes return 404. `Templates/Settings.html` "Compliance rules" card removed. Each vertical owns its settings UI: `/AudioNormalization` (existing), `/VideoPolicy` (new), `/ContainerPolicy` (new). Naming subject to operator decision 1.

C13. One-shot migration. `Scripts/MigrateToVerticalCompliance.py` runs once at cutover: creates columns + trigger, invokes all three verticals' `RecomputeFor` against every MediaFile, drops old columns/tables/constraint, asserts the new model's distribution. Idempotent on re-run.

C14. Equivalence sanity: at cutover, the new model's `WorkBucket` matches the old model's `WorkBucket` for >=99% of files. Each non-matching file is documented as either an accepted correction (e.g. 30 Rock case now routes elsewhere) or surfaces a vertical bug to fix before cutover lands.

C15. Smoke-test exit gate per phase: every phase that lands code includes a live-restart of WebService + WorkerService on I9 followed by a single end-to-end smoke verifying the affected flow. Unit-test-green is not the gate; live verification is.

## Plan

| Phase | Work | Exit gate |
|---|---|---|
| A | Scaffold three verticals: directory layout, empty feature docs with contract section skeleton, `RecomputeFor` stubs raising `NotImplementedError`, migration script adding `AudioOk` + `VideoOk` + `ContainerOk` columns + the `WorkBucket` trigger. No behavior change. | Migration applies cleanly; trigger fires; all `WorkBucket` are NULL because booleans are NULL. WebService + WorkerService restart clean. |
| B | Implement `RecomputeFor` per vertical. Audio extends existing policy resolution to write `AudioOk`. Video implements current TranscodeOperation logic + `MinSourceBpp`. Container implements current RemuxOperation logic. Each reads rules fresh per call. | Per-vertical contract tests green including mid-flight rule edit. Live smoke per vertical (touch one file, observe column flip). |
| C | Wire scanner post-probe to call all three. Run migration backfill for every MediaFile. Diff new vs old `WorkBucket`; investigate each delta. | >=99% equivalence; deltas categorized accepted-correction vs vertical-bug; latter fixed. |
| D | Rip. Delete `Features/Compliance/` entirely. Drop old columns + tables + CHECK constraint. Delete `compliance.feature.md` + `compliance.flow.md`. Remove "Compliance rules" card; add new vertical UI pages. | `grep -rn 'Compliance' Features/ Templates/ WebService/ Scripts/` returns 0 production hits (closed-directive references excepted). |
| E | Verify against production. Full failure-loudly suite. Restart WebService + WorkerService; rerun every criterion's verification command; record evidence per criterion. | All C1-C15 verified with concrete evidence in the directive's `### Verification` table. |

## Files

Populated incrementally during IMPLEMENTING. Directive anchor list scope: `Features/AudioNormalization/`, `Features/VideoPolicy/`, `Features/ContainerPolicy/` (subject to naming decision), `Features/FileScanning/`, `Features/MediaProbe/`, `Scripts/SQLScripts/`, `Tests/Contract/`, `Templates/`, `WebService/`. The hook accepts `# directive: vertical-owned-compliance` on functions/classes in any file inside the above paths for the duration of this directive.

## Decisions for operator confirmation

I baked these in. Push back on any:

1. **Vertical naming.** Drafted: `Features/VideoPolicy/` + `Features/ContainerPolicy/` (parallels `AudioNormalization` as a policy-owning vertical). Alternatives: shorter (`Features/Video/`, `Features/Container/`) or operation-named (`Features/Transcode/`, `Features/Remux/` -- distinct from existing `Features/TranscodeJob/` / `Features/TranscodeQueue/`).

2. **UI shape.** Drafted: three separate settings pages (parallels three-vertical code). Alternative: one `/Compliance` tabbed page that's a thin shell over three sub-tabs. Recommend three pages -- SRP at the UI layer matches SRP at the code layer.

3. **Column + table naming.** Drafted: `AudioOk`, `VideoOk`, `ContainerOk` for the columns; new rule tables named `AudioComplianceRules`, `VideoComplianceRules`, `ContainerComplianceRules` owned by their vertical (replacing today's `AudioFixRules`, `TranscodeRules`, `RemuxRules` which die). Alternative: `AudioCompliant` / `VideoCompliant` / `ContainerCompliant` for columns (more verbose, matches existing `IsCompliant` terminology).

4. **MinSourceBpp inclusion** (IDEAS.md 2026-06-19). Drafted: INCLUDED in initial Video vertical rule set. Operator may prefer it folds to a follow-up. Recommend include -- the directive's outcome is "perfect," shipping Video without the rule that fixes 30 Rock leaves a known violation.

5. **`IsCompliant` column survival.** Drafted: dropped. `WorkBucket IS NULL` is the test. Alternative: keep as a generated column `IsCompliant = (WorkBucket IS NULL)` for readability of downstream queries. Recommend drop -- one column derived from another is clutter; readers can write `WHERE WorkBucket IS NULL`.

## Promotions

(Empty -- populated at IMPLEMENTING -> DELIVERING. Each row will be `<directive section> -> <target *.feature.md or *.flow.md>`.)
