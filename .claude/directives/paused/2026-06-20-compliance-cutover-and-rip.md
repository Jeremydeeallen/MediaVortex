# Compliance Cutover + Rip

**Slug:** compliance-cutover-and-rip
**Set:** 2026-06-20
**Status:** PAUSED -- awaiting operator go/no-go on the equivalence diff

## Outcome

Install the SQL trigger that derives `MediaFiles.WorkBucket` from the three per-vertical booleans. Build the `/Compliance` tabbed page (Audio / Video / Container tabs). Delete `Features/Compliance/` entirely; drop the old rule tables, columns, and CHECK constraint; `/api/Compliance/*` routes return 404. Empties ~12 gap rows from `ARCHITECTURE.md` in one shot. **Irreversible cutover.**

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

Three classes of mismatches: (a) architectural corrections (intended), (b) possible bugs (needs investigation), (c) edge cases (small counts). Going past trigger install + Compliance delete is irreversible.

## Resume Conditions

Before resuming, operator should:
1. Confirm the "Remux → AudioFix" reclassification is acceptable. Operator-facing surfaces (`/Compliance`, `/Work/<bucket>`) will route differently.
2. Investigate the "(null) → Transcode" 1,325 cases. Sample some files; verify the new VideoCompliant=FALSE is correct (or fix the predicate).
3. Decide on MinSourceBpp default. If 0.04 is right, the "Transcode → (null/Remux)" cases are correct. If too aggressive, raise the threshold.

## Acceptance Criteria (drafted)

C1. Migration `InstallWorkBucketTrigger.py` creates a Postgres trigger on `MediaFiles` that derives `WorkBucket` from `(VideoCompliant, ContainerCompliant, AudioCompliant)` via the CASE: `!Video -> Transcode`, `!Container -> Remux`, `!Audio -> AudioFix`, else NULL. Idempotent.
C2. After trigger install, `WorkBucket` distribution matches the diff above (within rounding).
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
Scripts/SQLScripts/InstallWorkBucketTrigger.py     -- CREATE: trigger install
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
