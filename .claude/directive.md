# Current Directive

**Set:** 2026-07-26
**Status:** Active -- phase: NEEDS_PLAN
**Slug:** video-compliance-multiplier

## Outcome

Video compliance decision is bitrate-driven per DOMAIN.md 2026-07-26 "Video compliance is bitrate-driven (codec allowlist retired)". Per-resolution multiplier over Tier 1 target is the sole video-compliance signal. Operator tunes multipliers via `/settings` GUI without SQL or code. Codec allowlist retired.

## Acceptance Criteria

**C1. Video compliance is bitrate-driven (per-resolution multiplier over Tier 1); codec allowlist retired.** Implements DOMAIN.md 2026-07-26 "Video compliance is bitrate-driven (codec allowlist retired)" + operator-tunable multipliers via `/settings` GUI.

**Blocked until Q1-Q4 in `DOMAIN.md#open-domain-questions-2026-07-26` answered.** Do not start implementation until those four answers are recorded in DOMAIN.md. Session hand-off point: operator answers -> record in DOMAIN.md -> proceed to Files.

**Shape (post-Q-answers):**
- New table `VideoComplianceThresholds(Id SERIAL PK, ResolutionCategory TEXT UNIQUE, Tier1Multiplier NUMERIC(4,2) NOT NULL CHECK > 0, LastUpdated TIMESTAMP DEFAULT NOW())`.
- Seed 4 rows: `('480p', 1.5)`, `('720p', 2.0)`, `('1080p', 2.0)`, `('2160p', 3.0)`.
- `VideoVertical.Evaluate` reads multiplier fresh per call, applies `SourceKbps > Tier1TargetKbps * Multiplier` as the sole video-compliance signal. Codec check retired.
- `VideoComplianceRules.acceptablevideocodecscsv` column dropped from schema + all read sites deleted (Q1 may add a small `UnsupportedVideoCodecs` blocklist if operator chooses option (b)).
- `/settings` Transcoding card gains "Video Compliance" subsection: 4-row grid (Resolution | Multiplier | Effective floor auto-computed). PUT persists via existing `/api/SystemSettings/Transcoding`.
- Reclassify path per Q3 answer.

**Files (line-level filled at NEEDS_DOC_PREREAD after Q-answers):**
```
Scripts/SQLScripts/AddVideoComplianceThresholds_2026_07_26.py            -- CREATE (table + seed)
Scripts/SQLScripts/DropAcceptableVideoCodecsCsv_2026_07_26.py            -- CREATE (drops old singleton column)
Features/VideoEncoding/VideoComplianceThresholdsRepository.py            -- CREATE (GetMultiplier + UpdateMultiplier; fail-loud on missing row)
Features/VideoEncoding/VideoVertical.py                                  -- EDIT (multiplier applied; codec check removed)
Features/VideoEncoding/video-encoding.feature.md                         -- EDIT (compliance narrative rewritten; codec-allowlist removed; multiplier documented)
Features/SystemSettings/SystemSettingsController.py                      -- EDIT (GET/PUT extended with multipliers section)
Templates/Settings.html                                                  -- EDIT (Video Compliance subsection)
Static/settings.js                                                       -- EDIT (form handler)
Tests/Contract/TestVideoComplianceMultiplier.py                          -- CREATE (boundary tests: 1.4x compliant, 1.6x non-compliant @480p multiplier=1.5)
Tests/Contract/TestTranscodingSettingsRoundTrip.py                       -- EDIT (round-trip multipliers section)
Tests/Contract/TestNoLegacyResidue.py                                    -- EDIT (grep-fence acceptablevideocodecscsv = 0)
Scripts/RecomputeWorkBuckets.py                                          -- CREATE OR SKIP depending on Q3 answer (a/b/c)
Features/WorkBucket/work-bucket.feature.md                               -- EDIT (compliance-multiplier reference)
```

**Verification:**
- Contract tests green (TestVideoComplianceMultiplier + TestTranscodingSettingsRoundTrip + TestNoLegacyResidue).
- Grep `acceptablevideocodecscsv` in production tree = 0.
- Live: `SELECT WorkBucket, COUNT(*) FROM MediaFiles GROUP BY WorkBucket` shows `Transcode` count dropped significantly (1,922 mpeg4 files + N small-source files); `Remux` + `AudioFix` counts grew correspondingly.
- Operator sees `/Work/Transcode` shrink, `/Work/Remux` + `/Work/Audio` grow, `/settings` shows the 4-row multiplier grid.
- Round-trip edit test: change 480p multiplier from 1.5 to 1.6 via GUI PUT; next classifier call uses 1.6 immediately (db-authority).

## Status

### Progress

- [ ] NEEDS_PLAN: operator answers Q1-Q4 in DOMAIN.md; then advance phase.

### Resume Marker

**Next step:** operator answers Q1-Q4 in `DOMAIN.md#open-domain-questions-2026-07-26`. Once recorded, advance to NEEDS_DOC_PREREAD -> IMPLEMENTING.

**Phase:** NEEDS_PLAN

**Prior directive** (closed 2026-07-26): `.claude/directives/closed/2026-07-26-transcode-flow-canonical-closed.md` (transcode-flow-canonical, C0-C41; C41 IMPLEMENTED end of that directive). Everything else there is history; do not re-open unless explicitly requested.
