# Video Vertical Inline

**Slug:** video-vertical-inline
**Set:** 2026-06-24
**Status:** Drafted (backlog) -- prerequisite for resuming `compliance-cutover-and-rip`
**Position in chain:** Step 2 of 3 prerequisites named in `compliance-cutover-and-rip.md` Resume Conditions
**Sequencing:** depends on `effective-profile-to-profiles` closing first.

## Outcome

`VideoVertical.RecomputeFor` no longer depends on `Features/Compliance/`. The current implementation wraps `Features/Compliance/Operations/TranscodeOperation` to derive `VideoOk`. The wrap is inlined directly into `VideoVertical` so the vertical owns its own decision logic. After this directive, `grep -rn 'from Features.Compliance' Features/VideoEncoding/` returns 0 hits. Unblocks the `Features/Compliance/` deletion in `compliance-cutover-and-rip`.

## Why

`vertical-owned-compliance.md` non-negotiable 3 ("Rip, not migrate") forbids a long-running mixed-state period. `compliance-cutover-and-rip.md` plans to delete `Features/Compliance/` entirely. That deletion is blocked while `VideoVertical` still imports `TranscodeOperation` from it. Inlining the wrapped logic is the one-edit unblock.

The wrap was an interim step during `video-vertical-and-bpp` (closed) to ship the boolean column without rewriting the decision logic in one move. The interim is now load-bearing for the rip; this directive removes it.

## SOLID + DDD Shape

**SRP:** the inlined `VideoVertical` is the sole owner of "is this MediaFile's video compliant?" decision. No external operation class wraps it.

**DIP:** `VideoVertical` depends on:
- `IEffectiveProfileResolver` (now in `Features/Profiles/` per `effective-profile-to-profiles`)
- `IResolutionTierRegistry` (existing, in `Core/Resolution/`)
- `IBppCalculator` (existing or new)
- No dependency on `Features/Compliance/` after this directive.

**Behavior preservation:** the inlined logic must produce identical `VideoOk` values to the wrapped version for every MediaFile. Verified via diff query before/after.

## Acceptance Criteria

C1. `grep -rn 'from Features.Compliance' Features/VideoEncoding/ --include='*.py'` returns 0 hits.
C2. `Features/Compliance/Operations/TranscodeOperation.py` no longer imported by any file in `Features/VideoEncoding/` or `Features/FileScanning/` (`grep -rn 'TranscodeOperation' Features/ --include='*.py'` returns only its own definition + tests under `Tests/`).
C3. Behavior-preservation diff: pre-inline `VideoOk` values vs post-inline `VideoOk` values for every MediaFile are identical (`SELECT COUNT(*) FROM MediaFiles WHERE pre.VideoOk IS DISTINCT FROM post.VideoOk = 0`). One-shot script `Scripts/SQLScripts/CompareVideoVerticalInlineDiff.py` runs the comparison.
C4. Contract test `TestVideoVerticalSelfContained.py` instantiates `VideoVertical` with only Profiles + Resolution + BPP dependencies and asserts `RecomputeFor` produces verdicts without any `Features.Compliance` import path.

## Files (planned)

| File | Role |
|---|---|
| `Features/VideoEncoding/VideoVertical.py` | EDIT. Inline `TranscodeOperation.Evaluate` logic. Drop `Features.Compliance` import. |
| `Features/Compliance/Operations/TranscodeOperation.py` | LEAVE (still consumed by old Compliance orchestrator; deleted by `compliance-cutover-and-rip` directive in the chain step that follows this one). |
| `Scripts/SQLScripts/CompareVideoVerticalInlineDiff.py` | NEW. Behavior-preservation diff (C3). |
| `Tests/Contract/TestVideoVerticalSelfContained.py` | NEW. C4 contract test. |
| `Features/VideoEncoding/video-encoding.feature.md` | EDIT at DELIVERING. Promote inlined decision logic + dependency list. |

## Out of Scope

- Deleting `Features/Compliance/Operations/TranscodeOperation.py` -- that happens in `compliance-cutover-and-rip` after this and `compliance-tabbed-ui` close.
- Refactoring the inlined logic beyond mechanical extraction.

## Status

(Populated at IMPLEMENTING.)

## Activation Protocol

```powershell
git mv .claude/directives/backlog/video-vertical-inline.md .claude/directive.md
# Edit Status: Active -- phase: NEEDS_STANDARDS_REVIEW
```
