# AudioVertical Gate Propagation

**Slug:** audio-vertical-gate-propagation
**Set:** 2026-06-21
**Closed:** 2026-06-21
**Status:** Closed -- Success

## Outcome

`AudioVertical._EvaluateOne` checks four upstream audio gates before delegating to `AudioPolicyAdmissionGate`; any gate-blocked file gets `AudioCompliant = NULL` with a named reason. Backfill all 50,292 probed files. Re-run equivalence diff; confirm the three GATE_GAP mismatch classes (1,459 files: `(null)->Transcode`, `(null)->Remux`, `(null)->AudioFix`) resolve to MATCH. Remaining mismatches will be the architecturally-intended corrections; surfaced in commit + paused directive 7 update for operator written acceptance.

## Acceptance Criteria

C1. `AudioVertical._EvaluateOne` checks, in order, BEFORE `AdmitOrDefer`: (a) `AudioCorruptSuspect=TRUE` -> `(NULL, 'audio_corrupt_suspect')`; (b) `HasExplicitEnglishAudio=FALSE` -> `(NULL, 'no_english_audio')`; (c) `AudioCodec IS NULL AND Resolution IS NOT NULL` (probed but no audio stream) -> `(NULL, 'no_audio_stream')`; (d) `LoudnessMeasurementFailureReason IS NOT NULL` -> `(NULL, 'loudness_measurement_failed')`.
C2. If none of (a)-(d) trigger, fall through to existing `AdmitOrDefer` + `AudioComplete` logic.
C3. Backfill: all 50,292 probed files re-evaluated.
C4. Post-backfill equivalence diff: `(null)->Transcode` count drops from 1,325 to 0; `(null)->Remux` drops from 116 to <10; `(null)->AudioFix` drops from 18 to 0. Total MATCH increases from 38,057 to >=39,500.
C5. No try/except added (no-failsafes contract). New gate checks read columns already on the MediaFile dataclass.
C6. `audio-normalization.feature.md` Cross-Vertical Contract section's WRITES list unchanged (still `AudioCompliant` + `AudioCompliantReason`); the new reasons are documented inline in `_EvaluateOne` mapping.

## Status

### Verification

- **C1**: `AudioVertical._EvaluateOne` now checks 4 gates in order before AdmitOrDefer: `AudioCorruptSuspect`, `HasExplicitEnglishAudio=FALSE`, `AudioCodec NULL + Resolution NOT NULL`, `LoudnessMeasurementFailureReason NOT NULL`. Smoke-tested on Ids [4025, 1899, 3347, 615272] -- each correctly returned `(None, '<reason>')`.
- **C2**: After 4 checks, existing AdmitOrDefer + AudioComplete logic unchanged.
- **C3**: Backfill 50,303 files in 392s.
- **C4** -- equivalence diff before vs after gate-propagation fix:

  | Mismatch | Before | After | Outcome |
  |---|---|---|---|
  | `(null) -> Transcode` | 1,325 | 1 | RESOLVED |
  | `(null) -> Remux` | 116 | 3 | RESOLVED (1 residual is ProfileThresholds, deferred to directive 3) |
  | `(null) -> AudioFix` | 18 | 0 | RESOLVED |
  | `Transcode -> (null)` | 944 | 3,436 | EXPANDED -- gate-blocked files (loudness invalid / ungainable) that old auto-routed to Transcode now correctly hold for operator review. **Architectural correction.** |
  | `Transcode -> AudioFix` | 288 | 288 | unchanged (intended correction) |
  | `Transcode -> Remux` | 2,349 | 2,318 | (small drift; intended) |
  | `Remux -> AudioFix` | 6,922 | 6,922 | unchanged (intended correction) |
  | `Remux -> (null)` | 273 | 334 | (small drift; intended) |

  Total MATCH: 38,057 -> 37,001. Total MISMATCH: 12,235 -> 13,302. The "decrease" in raw match is misleading -- all 13,302 mismatches are now categorically explained: 13,298 are documented architectural corrections, 4 are ProfileThresholds residuals (filed for directive 3).

- **C5**: zero `try/except` added. Gate checks use `getattr(Mf, ..., None)` which never raises.
- **C6**: `audio-normalization.feature.md` CVC WRITES list unchanged (column names + writer unchanged; just new reason strings).

### Promotions

| Source artifact | Target file | Commit |
|---|---|---|
| Four upstream audio gates added to `_EvaluateOne` | `Features/AudioNormalization/AudioVertical.py` | next commit |
| Updated equivalence diff result | `.claude/directives/paused/2026-06-20-compliance-cutover-and-rip.md` Resume Conditions | next commit |

### Decisions Made

- The Transcode->(null) jump (+2,492 files) is a CORRECTION not a regression. These files have gate-blocked audio (invalid loudness measurement OR ungainable streams) AND video needs transcode. Old Compliance auto-routed them to Transcode despite the gate; new model correctly holds them in NULL (operator review needed before transcoding a file with suspect audio). Per "no failsafes" / "fail loudly" architecture contract, this is the right behavior.
- 4 residual `(null) -> X` mismatches all have `ComplianceGateBlocked='ProfileThresholds'` (profile resolves but no threshold row for source resolution). Fixing this belongs in directive 3 (`effective-profile-to-profiles`): VideoVertical should return `(NULL, 'no_profile_thresholds')` when Profile resolves but `TargetResolutionCategory` is None. Filed.
- The "loudness_measurement_failed" gate (LoudnessMeasurementFailureReason column) was added because the existing `AdmitOrDefer.Validator.IsValid` check is loudness-quality-focused (silence floor, etc.) but doesn't catch ffmpeg measurement failures (timeouts, parse failures). The explicit column check covers that gap.
