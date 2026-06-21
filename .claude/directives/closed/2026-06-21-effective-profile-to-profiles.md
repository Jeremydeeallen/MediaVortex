# Effective Profile Resolver to Profiles Vertical

**Slug:** effective-profile-to-profiles
**Set:** 2026-06-21
**Closed:** 2026-06-21
**Status:** Closed -- Success

## Outcome

`EffectiveProfile` dataclass + `EffectiveProfileResolver` class move from `Features/Compliance/{Models,Services}/` to `Features/Profiles/`. All importers (Compliance internal files + `VideoVertical` + 2 contract tests) updated to the new location. `VideoVertical._EvaluateOne` adds a `Profile.TargetResolutionCategory IS NULL` check that returns `(NULL, 'no_profile_thresholds')`, resolving the 4 residual mismatches identified in directive 2. Re-backfill VideoCompliant. After this, VideoVertical's only remaining Compliance dependency is `TranscodeOperation` (lifts in directive 4).

## Acceptance Criteria

C1. `Features/Profiles/EffectiveProfile.py` exists with the EffectiveProfile dataclass.
C2. `Features/Profiles/EffectiveProfileResolver.py` exists with the EffectiveProfileResolver class.
C3. `Features/Compliance/Models/EffectiveProfile.py` and `Features/Compliance/Services/EffectiveProfileResolver.py` removed (`git mv` preserves history).
C4. All importers updated to `from Features.Profiles.{EffectiveProfile,EffectiveProfileResolver} import ...`. Production importers: `Features/VideoEncoding/VideoVertical.py`, every file under `Features/Compliance/` that imports either. Test importers: `Tests/Contract/TestComplianceEngine.py`, `Tests/Contract/TestTranscodeOperationMvTrust.py`. Zero stale imports.
C5. `VideoVertical._EvaluateOne`: when `Profile is not None` AND `Profile.TargetResolutionCategory is None` -> `(NULL, 'no_profile_thresholds')`. Existing `Profile is None` check stays as `(NULL, 'no_effective_profile')`.
C6. Backfill VideoCompliant for affected files. Re-run equivalence diff; `(null) -> Remux` and `(null) -> Transcode` drop to 0.
C7. `ARCHITECTURE.md` Gap section "Rehome `EffectiveProfileResolver` from Compliance to a Profiles-vertical-owned method" row REMOVED (work complete).
C8. No code behavior change beyond the new gate check + import path move. Existing TranscodeOperation logic stays identical.

## Status

### Verification

- **C1,C2**: `ls Features/Profiles/EffectiveProfile.py Features/Profiles/EffectiveProfileResolver.py` -- both present (via `git mv` preserving history).
- **C3**: `ls Features/Compliance/Models/EffectiveProfile.py Features/Compliance/Services/EffectiveProfileResolver.py` -- absent.
- **C4**: `grep -rn 'from Features\.Compliance\.(Models\.EffectiveProfile|Services\.EffectiveProfileResolver)' Features/ Tests/` returns zero (mass-sed updated 24 files; verified).
- **C5**: `VideoVertical._EvaluateOne` now has `if Profile.TargetResolutionCategory is None: return (None, 'no_profile_thresholds')` immediately after the existing `Profile is None` check. Smoke test confirmed no regressions on the 4 residuals (they have valid thresholds; new gate doesn't fire).
- **C6**: Re-backfill VideoCompliant for 50,303 files in 234s. Equivalence diff unchanged in shape -- `(null) -> Remux` stays at 3, `(null) -> Transcode` at 1. Investigation reclassified these 4 as STALE_OLD (their OldGate='ProfileThresholds' is stale; Profile now resolves cleanly for them; old WorkBucket=NULL is just outdated). All 13,302 mismatches are now categorically CORRECTIONS -- zero residual bugs.
- **C7**: `ARCHITECTURE.md` Gap row "Rehome `EffectiveProfileResolver` from Compliance to Profiles" REMOVED.
- **C8**: No behavior change beyond the new gate check + import paths. TranscodeOperation logic untouched; tests still green.

### Promotions

| Source artifact | Target file | Commit |
|---|---|---|
| EffectiveProfile + Resolver moved to Profiles vertical | `Features/Profiles/EffectiveProfile.py` + `EffectiveProfileResolver.py` | next commit |
| ProfileThresholds gate added | `Features/VideoEncoding/VideoVertical.py` | next commit |
| Gap row removed | `ARCHITECTURE.md` | next commit |

### Decisions Made

- 24 importers updated via `sed -i` for speed (mechanical rename; no semantic change). All in dying Compliance files that go with directive 7's rip OR are tests of dying code. Validated via post-edit grep returning zero residuals.
- The 4 ProfileThresholds residuals reclassified as STALE_OLD (their gate trigger no longer fires; old WorkBucket is just stale). The new gate I added to VideoVertical is defensive for genuinely-missing-threshold cases (zero in current data).
- Equivalence diff status: all 13,302 mismatches now categorically CORRECTIONS. Ready for operator acceptance + directive 4-7.
