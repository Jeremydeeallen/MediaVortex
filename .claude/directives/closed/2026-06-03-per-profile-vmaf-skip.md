# Current Directive

**Set:** 2026-06-03
**Status:** Closed -- Success
**Closed:** 2026-06-03
**Slug:** per-profile-vmaf-skip
**Replaces:** none (new directive)

## Outcome

`Profiles.QualityTestRequired` becomes the per-profile control over whether a successful encode against that profile gets queued for VMAF. When a `TranscodeAttempt` is created, its `QualityTestRequired` flag is sourced from the assigned profile's column, not hardcoded. The 11 existing NVENC-hardware profiles are set to `QualityTestRequired=FALSE` (trusted; no VMAF needed). The new CPU canary stays TRUE (default; needs VMAF to validate). After this, a queued attempt against an NVENC profile shows `BypassReplace/QualityTestNotRequired` (the dispositioner's existing Row 2 already handles this case correctly); a queued attempt against a non-NVENC profile still gets VMAF when the global gate is on.

## Acceptance Criteria

1. `Profiles.QualityTestRequired BOOLEAN DEFAULT TRUE NOT NULL` column exists. Verifiable: `\d profiles` shows the column with default TRUE.
2. Migration `Scripts/SQLScripts/AddProfileQualityTestRequired.py` is idempotent (`ADD COLUMN IF NOT EXISTS`). Verifiable: running it twice produces no errors and no schema diff after the second run.
3. `ProcessTranscodeQueueService.CreateTranscodeAttempt` reads the value from the assigned profile and sets `TranscodeAttempts.QualityTestRequired` from it (with fallback `TRUE` if profile not found). Verifiable: enqueue against a profile with `QualityTestRequired=FALSE`; assert the created attempt's `QualityTestRequired=False`.
4. All 11 NVENC profiles (`usenvidiahardware=1`) have `QualityTestRequired=FALSE`. Verifiable: `SELECT COUNT(*) FROM profiles WHERE usenvidiahardware=1 AND QualityTestRequired=TRUE` returns 0.
5. The new `SVT-AV1 P3 CPU CANARY VBR -720p` (id=43) stays `QualityTestRequired=TRUE` (default). Verifiable: `SELECT QualityTestRequired FROM profiles WHERE Id=43` returns TRUE.

## Out of Scope

- Per-file `QualityTestOverride` column on MediaFiles. Add later if recurring need surfaces.
- Profile-edit UI changes (operator can edit the column via existing SystemSettings/Profile editor flows; not gating).
- Audit logging of which profile decided "skip VMAF" — disposition trail already records `QualityTestNotRequired` as the reason.

## Constraints

- One commit per criterion when distinct (C1+C2 = migration; C3 = code; C4 = bulk UPDATE).
- No service restart required mid-directive — dispositioner reads the per-attempt flag fresh.
- Default TRUE preserves existing behavior for any profile not explicitly set.

## Engineering Calls Already Made

- Per-profile chosen over per-file as the primary mechanism. "Trust this encoder" is profile-shaped.
- Existing dispositioner Row 2 (`if not QualityTestRequired: return ('BypassReplace', 'QualityTestNotRequired')`) already handles the skip case — no dispositioner code change needed.
- Hardcoded `True` at line 1387 is the only attempt-creation site for transcode jobs; remux already correctly sets False at line 1078.

## Status

Active 2026-06-03 -- phase: IMPLEMENTING.

### Files

```
Scripts/SQLScripts/AddProfileQualityTestRequired.py        -- CREATE: idempotent ADD COLUMN
Features/TranscodeJob/ProcessTranscodeQueueService.py      -- EDIT: source QualityTestRequired from profile (C3)
```

### Promotions

| Source artifact | Target file | Commit |
|---|---|---|
| no promotions | n/a | pure DB+code wiring; contract already documented in post-transcode-disposition.feature.md Row 2 |

### Verification

- C1: `\d profiles` shows `qualitytestrequired` BOOLEAN NOT NULL DEFAULT true.
- C2: migration is idempotent (`ColumnExists` guard + DEFAULT TRUE on existing rows).
- C3: `ProcessTranscodeQueueService.CreateTranscodeAttempt` now reads `qualitytestrequired` from profile (line ~1370); smoke import OK.
- C4: `COUNT(*) WHERE usenvidiahardware=1 AND qualitytestrequired=TRUE` returns 0 (11 NVENC profiles flipped).
- C5: profile id=43 stays TRUE (default).

### Decisions Made

- Dot workers need redeploy to pick up the code change; in-flight canary #2 (attempt against profile 43) was created before the change and still has QualityTestRequired=True correctly (no rerun needed).
- Per-file `QualityTestOverride` deferred until recurring need; per-profile + AssignedProfile pointer is sufficient today.
