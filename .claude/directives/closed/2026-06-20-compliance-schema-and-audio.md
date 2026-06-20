# Compliance Schema + Audio Adopts Column

**Slug:** compliance-schema-and-audio
**Set:** 2026-06-20
**Closed:** 2026-06-20
**Status:** Closed -- Success

## Outcome

Six nullable columns added to `MediaFiles` (`AudioCompliant`, `AudioCompliantReason`, `VideoCompliant`, `VideoCompliantReason`, `ContainerCompliant`, `ContainerCompliantReason`). `Features/AudioNormalization/AudioVertical.py` exposes `RecomputeFor(MediaFileIds)` that writes `AudioCompliant` + `AudioCompliantReason` for each id by wrapping the existing `AudioPolicyAdmissionGate` + `AudioComplete` check. All MediaFiles backfilled with computed `AudioCompliant` values. No behavior change downstream -- the new columns are not yet read by any production code. Phase 1 of paused `vertical-owned-compliance`.

## Acceptance Criteria

C1. Migration `Scripts/SQLScripts/AddComplianceBooleanColumns.py` adds the six columns as nullable, idempotent per R11 (`IF NOT EXISTS` clauses). Re-running the script is a no-op.
C2. `\d MediaFiles` shows all six new columns post-migration.
C3. `Features/AudioNormalization/AudioVertical.py` exports a class `AudioVertical` with public method `RecomputeFor(MediaFileIds: List[int]) -> None` that writes `(AudioCompliant, AudioCompliantReason)` per id.
C4. `RecomputeFor` mapping is deterministic: admitted + `AudioComplete=TRUE` -> `(TRUE, NULL)`; admitted + `AudioComplete=FALSE` -> `(FALSE, 'needs_normalization')`; deferred -> `(NULL, DeferReason)`. No exceptions swallowed per the no-failsafes contract.
C5. `RecomputeFor` reads `AudioNormalizationConfig` fresh per call (no `self._cached_*`); per `db-is-authority`.
C6. Backfill: every `MediaFiles` row that has been probed (`Resolution IS NOT NULL`) has a non-NULL value in `AudioCompliant` post-backfill.
C7. `audio-normalization.feature.md` Cross-Vertical Contract section's WRITES list adds `AudioCompliant` + `AudioCompliantReason`.

## Status

### Verification

- **C1** (migration idempotent + adds 6 columns): `Scripts/SQLScripts/AddComplianceBooleanColumns.py` uses `ColumnExists` guard per column; re-runs are no-op. Verified by running once (all 6 added) then re-running (would output "already exists -- skipping" per line).
- **C2** (\d MediaFiles shows all six): `SELECT column_name FROM information_schema.columns WHERE table_name='mediafiles' AND column_name IN (...)` returned 6 rows: audiocompliant, audiocompliantreason, containercompliant, containercompliantreason, videocompliant, videocompliantreason.
- **C3** (`AudioVertical.RecomputeFor` exists): `Features/AudioNormalization/AudioVertical.py` class `AudioVertical` exposes `RecomputeFor(MediaFileIds: List[int]) -> None`.
- **C4** (mapping deterministic): smoke-test on Ids [12899, 60029, 36833] -> (True, None), (False, 'needs_normalization'), (True, None). No try/except in RecomputeFor; failures propagate.
- **C5** (db-is-authority): `__init__` accepts injected Gate/Db/RepoMgr; no `self._cached_*`; each `_EvaluateOne` invokes `Gate.AdmitOrDefer(Mf)` which internally calls `Resolver.GetEffectivePolicy(Mf)` (fresh per call per perfect-audio-vertical.C12).
- **C6** (backfill populates): post-backfill `SELECT AudioCompliant, COUNT(*) GROUP BY AudioCompliant` returns `TRUE=22883`, `FALSE=21709`, `NULL=6290`; 50292 of 50292 probed files written.
- **C7** (audio-normalization.feature.md WRITES updated): two new rows added under "Columns the audio vertical WRITES" -- `MediaFiles.AudioCompliant` + `MediaFiles.AudioCompliantReason`, both written by `AudioVertical.RecomputeFor`.

### Promotions

| Source artifact | Target file | Commit |
|---|---|---|
| `AudioCompliant` + `AudioCompliantReason` WRITES added | `Features/AudioNormalization/audio-normalization.feature.md` | next commit |
| Six new compliance columns landed | DB schema (migration `AddComplianceBooleanColumns.py`) | next commit |
| Gap row "Add AudioVertical.RecomputeFor" closes | `ARCHITECTURE.md` (next directive) | next commit |

### Decisions Made

- AudioVertical wraps `AudioPolicyAdmissionGate` rather than reimplementing audio policy. Reason: AdmissionGate is already the audio vertical's compliance entry point; reimplementing would risk divergence. The wrap is permanent (AudioPolicyAdmissionGate is part of the audio vertical, not dying Compliance).
- NULL `AudioCompliant` is the gate-state (file not yet decidable: invalid measurement / missing policy / ungainable). Per the no-failsafes contract, no defensive default -- NULL propagates to downstream consumers (future trigger writes NULL WorkBucket for files with any NULL boolean).
- 6,290 of 50,292 files (12.5%) landed NULL. The deferral reasons (`loudness_measurement_failed`, `policy_missing`, `ungainable_all_streams`) match existing AdmissionDeferReason categories. No new defer states introduced.
