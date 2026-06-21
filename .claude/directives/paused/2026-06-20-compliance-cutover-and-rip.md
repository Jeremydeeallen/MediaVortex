# Compliance Cutover + Rip

**Slug:** compliance-cutover-and-rip
**Set:** 2026-06-20
**Status:** PAUSED -- awaiting operator go/no-go on the equivalence diff

## Outcome

Convert `MediaFiles.WorkBucket` to a `GENERATED ALWAYS AS (CASE ...) STORED` column that derives from the three per-vertical booleans. Build the `/Compliance` tabbed page (Audio / Video / Container tabs). Delete `Features/Compliance/` entirely; drop the old rule tables, columns, and CHECK constraint; `/api/Compliance/*` routes return 404. Empties ~12 gap rows from `ARCHITECTURE.md` in one shot. **Cutover is reversible with pg_dump backup + RENAME (instead of DROP) of dying tables.**

## Why Paused

Equivalence diff at 2026-06-20 showed 76% match (target was ≥99%) between new derived bucket and current `MediaFiles.WorkBucket`:

| Old → New | Count | Read |
|---|---|---|
| Remux → AudioFix | 6,922 | Old Compliance grouped "audio not normalized" with Remux; new model correctly buckets as AudioFix. **Architectural correction.** |
| Transcode → Remux | 2,349 | New VideoVertical's MinSourceBpp override marks "already efficient" sources compliant; they fall through. **Includes 30 Rock S01E01 canary fix.** |
| (null) → Transcode | 1,325 | Files old-compliant, new video-incompliant. Investigate before cutover. |
| Transcode → (null) | 944 | Files old-needs-transcode, now fully compliant. Likely BPP override. |
| Transcode → AudioFix | 288 | Old said video, new says audio. |
| Remux → (null) | 273 | Now fully compliant. |
| (null) → Remux | 116 | New container-incompliant. |
| (null) → AudioFix | 18 | New audio-incompliant. |

Three classes of mismatches: (a) architectural corrections (intended), (b) possible bugs (needs investigation), (c) edge cases (small counts). Going past generated-column install + Compliance delete is reversible via pg_dump backup + RENAME-not-DROP for the dying tables.

## Resume Conditions

Investigation directive `mismatch-investigation` (2026-06-21) classified the 6 mismatch classes as follows:

| Class | Count | Verdict | Action |
|---|---|---|---|
| `(null) → Transcode` | 1,325 | GATE_GAP | Fix in next directive: AudioVertical propagates audio gates via AudioCompliant=NULL |
| `Transcode → (null)` | 944 | CORRECTION | Accept (MinSourceBpp override; 30 Rock pattern) |
| `Transcode → AudioFix` | 288 | CORRECTION | Accept (per-domain bucketing) |
| `Remux → (null)` | 273 | STALE_OLD | Accept (old WorkBucket was stale; new reflects current row state) |
| `(null) → Remux` | 116 | MIXED | Same fix as Class 1 (audio gate propagation; container issue resurfaces post-fix) |
| `(null) → AudioFix` | 18 | GATE_GAP | Same fix as Class 1 |

**Before resuming:**
1. Land the AudioVertical gate-propagation fix (next directive: `audio-vertical-gate-propagation`). Resolves 1,459 mismatches. Post-fix equivalence: 78.6% MATCH / 21.4% MISMATCH (with the remaining 21.4% all intentional architectural corrections).
2. Re-run equivalence diff. Confirm the GATE_GAP classes drop to zero.
3. Operator signs off in writing (commit message OK) accepting the ~10,776 intentional corrections: per-domain bucketing (Remux→AudioFix), MinSourceBpp override (Transcode→Remux/null/AudioFix), and stale-data refreshes (Remux→null).
4. Then resume directive 6 (this one): pg_dump backup → GENERATED column install → disable old Compliance → smoke → 48h observation → rip.

## Acceptance Criteria (drafted)

C1. Migration `ConvertWorkBucketToGenerated.py` (a) `pg_dump` the live DB to a timestamped file under `Scripts/SQLScripts/backups/`, (b) DROP existing `MediaFiles.WorkBucket` column, (c) ADD COLUMN `WorkBucket TEXT GENERATED ALWAYS AS (CASE WHEN VideoCompliant IS NULL OR ContainerCompliant IS NULL OR AudioCompliant IS NULL THEN NULL WHEN NOT VideoCompliant THEN 'Transcode' WHEN NOT ContainerCompliant THEN 'Remux' WHEN NOT AudioCompliant THEN 'AudioFix' ELSE NULL END) STORED`, (d) CREATE INDEX on the new column. Idempotent (skips if `WorkBucket` is already generated; detected via `information_schema.columns.is_generated`).
C2. After conversion, `WorkBucket` distribution matches the diff above (within rounding). Postgres refuses any Python attempt to INSERT/UPDATE `WorkBucket` directly (`cannot assign to generated column`).
C3. `/Compliance` tabbed page exists at `Templates/Compliance.html` with three tabs (Audio / Video / Container) served by per-vertical controllers.
C4. `Features/Compliance/` directory deleted in its entirety.
C5. Drop tables: `TranscodeRules`, `RemuxRules`, `AudioFixRules`, `SubtitleFixRules`, `ComplianceGates`.
C6. Drop columns: `MediaFiles.OperationsNeededCsv`, `ComplianceGateBlocked`, `ComplianceEvaluatedAt`.
C7. Drop constraint `chk_compliance_consistency`.
C8. `/api/Compliance/*` routes return 404.
C9. `compliance.feature.md` + `compliance.flow.md` deleted.
C10. VideoVertical inlines its logic (no longer wraps `Features/Compliance/Operations/TranscodeOperation`).
C11. EffectiveProfileResolver moves from `Features/Compliance/Services/` to `Features/Profiles/`.

## Files (drafted)

```
Scripts/SQLScripts/ConvertWorkBucketToGenerated.py -- CREATE: pg_dump backup + DROP/ADD column as GENERATED
Scripts/SQLScripts/DropComplianceArtifacts.py      -- CREATE: drop tables/columns/CHECK
Templates/Compliance.html                          -- CREATE: tabbed shell
Features/AudioNormalization/AudioNormalizationController.py -- EDIT: add /Compliance Audio tab endpoint
Features/ContainerFormat/ContainerFormatController.py       -- CREATE: /Compliance Container tab endpoint
Features/VideoEncoding/VideoEncodingController.py           -- CREATE: /Compliance Video tab endpoint
Features/Profiles/EffectiveProfileResolver.py     -- CREATE: move from Compliance
Features/VideoEncoding/VideoVertical.py           -- EDIT: inline logic, drop Compliance import
Features/Compliance/                              -- DELETE: entire directory
Features/Compliance/compliance.feature.md         -- DELETE
Features/Compliance/compliance.flow.md            -- DELETE
ARCHITECTURE.md                                   -- EDIT: empty most of Gap section
WebService/Main.py                                -- EDIT: remove ComplianceBlueprint registration
```

## Status (state when paused)

- Paused 2026-06-20. Six prior directives in the sequence are closed (architecture-document, orphan-and-stale-cleanup, media-probe-and-activity-docs, compliance-schema-and-audio, container-vertical, video-vertical-and-bpp). All three booleans populated on every probed file.
- Equivalence diff documented above.
- Next directive (if operator confirms cutover acceptable): unpause this file via `git mv .claude/directives/paused/2026-06-20-compliance-cutover-and-rip.md .claude/directive.md` and execute Phases.
