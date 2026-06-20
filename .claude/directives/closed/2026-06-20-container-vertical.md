# Container Vertical

**Slug:** container-vertical
**Set:** 2026-06-20
**Closed:** 2026-06-20
**Status:** Closed -- Success

## Outcome

`Features/ContainerFormat/` vertical built. New `ContainerComplianceRules` table seeded from existing `RemuxRules`. `ContainerVertical.RecomputeFor(MediaFileIds)` writes `(ContainerCompliant, ContainerCompliantReason)`. Backfill across all probed files. No dependency on dying `Features/Compliance/`. Phase 3 of paused `vertical-owned-compliance`.

## Acceptance Criteria

C1. `Scripts/SQLScripts/AddContainerComplianceRules.py` creates `ContainerComplianceRules` table with columns `Id`, `AcceptableContainersCsv`, `AcceptableAudioCodecsCsv`, `LastUpdated`. Idempotent (`CREATE TABLE IF NOT EXISTS`). Seeds one row from current `RemuxRules` (`mp4,mov,m4v` / `aac,ac3,eac3,mp3`).
C2. `Features/ContainerFormat/ContainerVertical.py` exposes `ContainerVertical` class with `RecomputeFor(MediaFileIds: List[int]) -> None`.
C3. Container compliance predicate (matches today's `Features/Compliance/Operations/RemuxOperation.Apply` predicates 1 + 2 for equivalence): `ContainerCompliant = TRUE` iff container is in `AcceptableContainersCsv` AND audio codec is in `AcceptableAudioCodecsCsv`. Otherwise `FALSE` with reason naming the failing rule.
C4. `ContainerVertical` reads `ContainerComplianceRules` fresh per call (`db-is-authority`); no `self._cached_*`.
C5. No dependency on `Features/Compliance/` -- `grep 'Features.Compliance' Features/ContainerFormat/` returns 0.
C6. Backfill: every probed `MediaFiles` row gets a non-NULL `ContainerCompliant` value post-backfill.
C7. `Features/ContainerFormat/container-format.feature.md` created at DELIVERING with slug + Workflows + Criteria + Seams + Cross-Vertical Contract.

## Status

### Verification

- **C1**: `ContainerComplianceRules` exists with 1 row (`mp4,mov,m4v` / `aac,ac3,eac3,mp3`); migration re-runs as no-op (CREATE TABLE IF NOT EXISTS + count check).
- **C2**: `Features/ContainerFormat/ContainerVertical.py` exports `ContainerVertical.RecomputeFor(MediaFileIds: List[int]) -> None`.
- **C3**: predicate fires container-not-in-set OR audio-codec-not-in-set per `_EvaluateOne`. Smoke-tested on Ids [12899, 36833, 60029] -> all TRUE (mov,mp4-family containers + eac3/aac).
- **C4**: `_LoadRules` queries `ContainerComplianceRules` each `RecomputeFor` call; no `self._cached_*` in `__init__`.
- **C5**: `grep 'Features.Compliance' Features/ContainerFormat/` -- 0 hits.
- **C6**: Backfill 50,292 files in 170s. Post-state `ContainerCompliant`: TRUE=35564, FALSE=14728, NULL=590. (590 NULL are MediaFiles inserted during backfill -- next probe completion will populate.)
- **C7**: `Features/ContainerFormat/container-format.feature.md` created at DELIVERING.

### Promotions

| Source artifact | Target file | Commit |
|---|---|---|
| ContainerVertical implementation + rule table | `Features/ContainerFormat/` (new vertical) | next commit |
| Top-level feature doc + Cross-Vertical Contract | `Features/ContainerFormat/container-format.feature.md` | next commit |
| Gap row closes | `ARCHITECTURE.md` (in next pass) | next commit |

### Decisions Made

- Predicate scope: only container + audio-codec-vs-container. Excluded RequireAudioNormalized (audio domain, handled by AudioVertical).
- Container vertical owns its own `ContainerComplianceRules` table, not `RemuxRules`. RemuxRules dies with Compliance at directive 7.
- AcceptableAudioCodecsCsv (renamed from `AcceptableAudioCodecsMp4Csv`) -- the old name was misleading; rule applies regardless of container-mp4-ness.
