# Effective Profile to Profiles

**Slug:** effective-profile-to-profiles
**Set:** 2026-06-24
**Status:** Drafted (backlog) -- prerequisite for resuming `compliance-cutover-and-rip`
**Position in chain:** Step 1 of 3 prerequisites named in `compliance-cutover-and-rip.md` Resume Conditions

## Outcome

`VideoVertical.RecomputeFor` handles `Profile.TargetResolutionCategory IS NULL` explicitly. It returns `(VideoOk=NULL, Reason='no_profile_thresholds')` rather than raising / falling through. `EffectiveProfileResolver` moves from `Features/Compliance/Services/` to `Features/Profiles/` so the resolver no longer lives inside a vertical scheduled for deletion. Resolves the 4 `ProfileThresholds residual` mismatches surfaced by `compliance-cutover-and-rip` equivalence diff (3 `(null) -> Remux` + 1 `(null) -> Transcode`).

## Why

After the `audio-vertical-gate-propagation` directive closed (2026-06-21), the equivalence diff between the new derived `WorkBucket` and old `WorkBucket` had 13,302 mismatches. 13,298 were categorically explained as architectural corrections. The remaining 4 traced to `VideoVertical` not handling the case where a profile has no resolution thresholds defined (`Profile.TargetResolutionCategory IS NULL`). The vertical was implicitly assuming every profile has thresholds. When the assumption breaks, the vertical produces a non-deterministic `VideoOk` value that disagrees with what old Compliance returned for the same row.

The fix is small: typed return `(NULL, 'no_profile_thresholds')` when the profile lacks thresholds. Closes 4 residuals to take the diff to 100% explained.

## SOLID + DDD Shape

**Domain rule (DDD):** `VideoVertical` returns one of three explicit verdicts: `Compliant`, `NotCompliant(Reason)`, or `Indeterminate(Reason)`. The third bucket exists for the "policy cannot decide" case -- `IsCompliant=NULL` is a valid domain state with a recorded reason.

**SRP:** `EffectiveProfileResolver` does one thing -- resolves `(MediaFileId, ProfileName) -> EffectiveProfile`. It moves to `Features/Profiles/` because the Profile vertical is its rightful owner.

**DIP:** `VideoVertical` consumes `IEffectiveProfileResolver` interface; the resolver concrete is constructor-injected. No `Features/Compliance/` import survives in `VideoVertical` after this directive.

## Acceptance Criteria

C1. `EffectiveProfileResolver` lives at `Features/Profiles/EffectiveProfileResolver.py`. `grep -rn 'from Features.Compliance.Services.EffectiveProfileResolver' --include='*.py'` returns 0 hits.
C2. `VideoVertical.RecomputeFor` handles `Profile.TargetResolutionCategory IS NULL` -- returns `VideoVerdict.Indeterminate('no_profile_thresholds')`. No fall-through, no implicit `False`, no raise.
C3. Contract test `TestVideoVerticalNoProfileThresholds.py` constructs a MediaFile assigned to a profile with `TargetResolutionCategory=NULL` and asserts `VideoOk` lands as NULL with the reason recorded.
C4. Equivalence diff residuals: re-run the `compliance-cutover-and-rip` diff query post-fix; the 4 residual rows resolve to either MATCH or are explained as an architectural correction with operator acceptance.

## Files (planned)

| File | Role |
|---|---|
| `Features/Profiles/EffectiveProfileResolver.py` | NEW (moved from `Features/Compliance/Services/EffectiveProfileResolver.py`). |
| `Features/Compliance/Services/EffectiveProfileResolver.py` | DELETE after consumers updated. |
| `Features/VideoEncoding/VideoVertical.py` | EDIT. Handle `TargetResolutionCategory IS NULL` -> `Indeterminate('no_profile_thresholds')`. Update import path. |
| `Features/VideoEncoding/VideoVerdict.py` | NEW or EDIT. Typed `Compliant` / `NotCompliant(reason)` / `Indeterminate(reason)` value object if not already present. |
| `Tests/Contract/TestVideoVerticalNoProfileThresholds.py` | NEW. C3 contract test. |
| `Features/VideoEncoding/video-encoding.feature.md` | EDIT at DELIVERING. Add criterion covering `Indeterminate` verdict + reason recording. |

## Out of Scope

- Filling in actual resolution thresholds for profiles that lack them. That's an operator data task, not an engineering fix.
- Refactoring `VideoVertical` beyond the `TargetResolutionCategory IS NULL` branch.

## Status

(Populated at IMPLEMENTING.)

## Activation Protocol

```powershell
git mv .claude/directives/backlog/effective-profile-to-profiles.md .claude/directive.md
# Edit Status: Active -- phase: NEEDS_STANDARDS_REVIEW
```
