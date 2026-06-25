# BUG-0062 Resolution Path

**Set:** 2026-06-24
**Status:** Reference index (not a directive)

## What this is

A one-page pointer at the SOLID + DDD fix already planned for `BUG-0062` (Compliance writeback invariant CLUSTER). The fix is a chain of paused / closed / unbuilt directives, not a single new directive.

## The architectural fix (already designed)

`BUG-0062` exists because the current `Features/Compliance/` orchestrator emits `ComplianceDecision` tuples that can be internally inconsistent -- the symptom that drove the three-layer writeback defense (constructor validator + repository validator + SQL CHECK).

The SOLID + DDD fix is to make inconsistent state **structurally impossible** rather than defend against it after emit. Replace the orchestrator with three vertical-owned boolean columns (`AudioOk`, `VideoOk`, `ContainerOk`) and a Postgres trigger that materializes `WorkBucket` from a single CASE expression. A trigger reading three booleans into one CASE cannot be inconsistent.

This is the plan in `.claude/directives/paused/2026-06-20-vertical-owned-compliance.md` and `.claude/directives/paused/2026-06-20-compliance-cutover-and-rip.md`.

## Chain state (2026-06-24)

| Directive | Status | Location |
|---|---|---|
| architecture-document | CLOSED | `.claude/directives/closed/` |
| orphan-and-stale-cleanup | CLOSED | `.claude/directives/closed/` |
| media-probe-and-activity-docs | CLOSED | `.claude/directives/closed/` |
| compliance-schema-and-audio | CLOSED | `.claude/directives/closed/` |
| container-vertical | CLOSED | `.claude/directives/closed/` |
| video-vertical-and-bpp | CLOSED | `.claude/directives/closed/` |
| vertical-owned-compliance | PAUSED (NEEDS_STANDARDS_REVIEW) | `.claude/directives/paused/2026-06-20-vertical-owned-compliance.md` |
| **effective-profile-to-profiles** | DRAFTED (backlog) | `.claude/directives/backlog/effective-profile-to-profiles.md` (scaffolded 2026-06-24) |
| **video-vertical-inline** | DRAFTED (backlog) | `.claude/directives/backlog/video-vertical-inline.md` (scaffolded 2026-06-24) |
| **compliance-tabbed-ui** | DRAFTED (backlog) | `.claude/directives/backlog/compliance-tabbed-ui.md` (scaffolded 2026-06-24) |
| compliance-cutover-and-rip | PAUSED (awaiting prerequisites) | `.claude/directives/paused/2026-06-20-compliance-cutover-and-rip.md` |

Resume conditions are documented in detail in `compliance-cutover-and-rip.md` `## Resume Conditions`.

## Recommended next action

When `worker-runtime-state` closes and the audio cluster (`audio-pipeline-fail-loud`) closes, activate the compliance chain in this order:

1. Scaffold `effective-profile-to-profiles.md` -- VideoVertical handles `Profile.TargetResolutionCategory IS NULL` -> `(NULL, 'no_profile_thresholds')`. Resolves 4 residual mismatches.
2. Scaffold `video-vertical-inline.md` -- inline the `TranscodeOperation` wrap so `VideoVertical` no longer depends on dying `Features/Compliance/`.
3. Scaffold `compliance-tabbed-ui.md` -- build `/Compliance` shell with three per-vertical settings tabs.
4. Operator written acceptance of the 13,298 architectural corrections (commit message at directive 3 close suffices per `compliance-cutover-and-rip.md` resume condition 4).
5. `git mv .claude/directives/paused/2026-06-20-vertical-owned-compliance.md .claude/directive.md` -- activate the master plan; advance phases per the directive's own ## Plan table.
6. After vertical-owned-compliance closes, activate `compliance-cutover-and-rip.md` for the final cutover.

## Why not a new BUG-0062 directive

A focused "ComplianceDecision self-validates + SQL CHECK + contract test" directive would ship faster but it would shore up the classes that the chain plans to DELETE. Wasted work. The chain's three-vertical model is the SOLID + DDD-clean answer (one bounded context per concern; aggregate consistency via trigger, not validator); the writeback-defense directive would be a band-aid on code marked for removal.

Operator confirmed this path 2026-06-24.
