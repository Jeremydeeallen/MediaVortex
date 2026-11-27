# Profile Tier Ladder

**Slug:** profile-tier-ladder

## What It Does

Replaces per-profile-name proliferation with a 3-axis tuple: `(Family, QualityTier, ContentClass)` at `TargetResolutionCategory`. Family names the encoder + preset (e.g. `NVENC AV1 CANARY`, `QSV AV1 CANARY`). QualityTier ranges 1..5 (small/low-quality -> large/near-source). ContentClass in `{live_action, animation, mixed}`. TargetResolutionCategory reuses the resolution-types tier registry. Every combination = one Profile row. Deleting non-CANARY AV1 profiles kills naming variance that was driving operator confusion.

## Workflows

| # | User action | Surface | Handler | Backing |
|---|---|---|---|---|
| W1 | Operator edits a tier's TargetKbps on /settings Transcoding card | `/settings` bitrate ladder editor | `PUT /api/SystemSettings/Transcoding` | `SystemSettingsController.SaveTranscodingSettings` -> `ProfileThresholds.TargetKbps` UPDATE |
| W2 | ContentClassifier assigns a profile to a new MediaFile; its content class is resolved at read, never stored | (internal) | `ContentClassifierService.ClassifyAndAssign` | writes `MediaFiles.AssignedProfile`; `ContentClassResolver.Resolve` supplies the class to every row lookup (C10) |
| W4 | Operator sets a library's default content class or a genre's class | `/settings` library table "Default content class", genre table class column | `PUT /api/SystemSettings/LibraryTiers` (`DefaultContentClass`), `PUT /api/SystemSettings/GenreTiers` (`ContentClass`) | `LibraryDefaultTierRepository.SetDefaultContentClass`, `GenreQualityTierRepository.SetContentClass`; save re-evaluates the library |
| W3 | Dispatcher escalates on VMAF fail -> next-tier profile | (internal) | `NextTierAdjuster.Get` | `Features/TranscodeJob/Adjustments/NextTierAdjustmentCalculator` |

## Success Criteria

C1. `Profiles` schema adds `Family TEXT NOT NULL`, `QualityTier INT NOT NULL CHECK (QualityTier BETWEEN 1 AND 5)`, `ContentClass TEXT NOT NULL CHECK (ContentClass IN ('live_action','animation','mixed'))`. UNIQUE `(Family, QualityTier, ContentClass, TargetResolutionCategory)`. Verifiable: `\d Profiles` shows the three columns + CHECKs + UNIQUE.

C2. `ProfileThresholds` schema adds `TargetKbps INT NOT NULL`. Dead columns `SourceBitratePercent`, `MinBitrateKbps`, `MaxBitrateKbps` dropped. `IcqQ INT NULL` exists and is editable on `/settings`, but no tier profile encodes by it (C6). Verifiable: `\d ProfileThresholds` matches; grep `SourceBitratePercent` in `Features/**/*.py` returns 0.

C3. Two families kept: `'NVENC AV1 CANARY'` + `'QSV AV1 CANARY'`. Every non-CANARY AV1 profile deleted via `DeleteNonCanaryProfiles_2026_07_04.py`. Orphaned `MediaFiles.AssignedProfile` reassigned via ContentClassifier. Verifiable: `SELECT COUNT(*) FROM Profiles WHERE Codec IN ('av1_nvenc','av1_qsv','libsvtav1') AND Family NOT IN ('NVENC AV1 CANARY','QSV AV1 CANARY')` returns 0.

C4. Backfill populates two families x four resolutions x five tiers x live-action rows. TargetKbps table (live-action calibration): 480p=[400,550,700,900,1200] / 720p=[900,1400,1900,2500,3200] / 1080p=[1800,2400,3200,4200,5500] / 2160p=[4000,6000,8500,12000,18000]. Verifiable: `SELECT * FROM Profiles p JOIN ProfileThresholds pt ON pt.ProfileId=p.Id WHERE p.Family='NVENC AV1 CANARY' AND p.ContentClass='live_action'` returns 20 rows (4 res x 5 tier).

C5. NVENC VBR video slot consumes `TargetKbps` directly. Emits `-b:v <TargetKbps>k -maxrate:v <TargetKbps * MaxBitrateMultiplier>k -bufsize:v <same>k`. No percent-of-source math, no min/max clamps. Verifiable: `Tests/Contract/TestCommandComposer` asserts emitted argv contains the raw TargetKbps value.

C6. Intel QSV workers encode by tier bitrate, the same as NVENC. Every tier profile has `RateControlMode='vbr'`; the QSV video slot emits `-b:v <TargetKbps>k -maxrate:v <TargetKbps * MaxBitrateMultiplier>k -bufsize:v <same>k`. No production encode on any worker selects a quality-level rate control. All five tier profiles carry the Intel-only knobs `QsvExtBrc=1` and `QsvLookaheadDepth=8` (look-ahead depth 40 crashes the encoder -- BUG-0071). Verifiable: `Tests/Contract/TestCommandComposer` asserts a QSV-resolved tier profile emits the raw TargetKbps value; `SELECT DISTINCT RateControlMode FROM Profiles` over the tier profiles returns only `vbr`.

C7. [BUG-0108] A downscaling tier encode scores the same quality whichever encoder runs it. For the same source and tier, the Intel QSV output's VMAF (scored at the encoded resolution, and again upscaled to the source resolution) is within 2 points of the NVIDIA NVENC output's. Verifiable: encode one film at Tier 1 on a QSV worker and an NVENC worker with the production commands; VMAF both against the source.

C7. `NextTierAdjuster.Get(currentProfile)` returns `Optional[Profile]` by walking the UNIQUE tuple with `QualityTier + 1`. Returns None when ceiling hit (Tier 5). Verifiable: `Tests/Contract/TestNextTierAdjuster.py` covers tier-1 -> tier-5 chain + ceiling terminates.

C8. `DispositionDispatcher._MaybeScheduleRequeue` passes escalated `ProfileId` to `AddJobToQueue` when adjuster returns non-None. Chain terminates at Tier 5 -> Reject/QualityCeilingReached (folds through RetryBudget). Verifiable: dispatcher contract test proves ProfileId in the requeued queue row differs from previous when adjuster escalates.

C9. **One row lookup.** The `ProfileThresholds` row for a file is chosen by `(ProfileName, ContentClass, SourceResolution)` through `TierLadderRepository.GetProfileRow`, and queue admission, the encode command, the size estimate and the video compliance ceiling all read that one row. Admission refuses an upscale only when the source is below that row's `TranscodeDownTo`. Verifiable: `Tests/Contract/TestProfileRowLookup.py` feeds one fixture to all four consumers and asserts the same row; `grep -rn "GetProfileMaxTarget\|GetProfileSettingsForTargetResolution\|GetProfileQualityForTargetResolution\|_ResolveTargetResolution" --include=*.py .` returns 0.

C10. **Content class is operator data, resolved at read.** `ContentClassResolver.Resolve(StorageRootId, MediaFileId)` returns the class of the first genre in `MediaFiles.Genres` that has one in `GenreQualityTiers.ContentClass`, else `StorageRoots.DefaultContentClass`, else `None`. Both columns are nullable with `CHECK IN ('live_action','animation')` and are edited on `/settings` (library table "Default content class", genre table class column); saving either re-evaluates the library. No code supplies a class: `None` surfaces as `missing_input:ContentClass`. Verifiable: `Tests/Contract/TestProfileRowLookup.py` covers genre class, library default and none; `grep -rn "'live_action'" Features/ --include=*.py` returns only CHECK text.

## Seams

| ID | Seam | Producer | Wire shape | Consumer expects | Verification |
|---|---|---|---|---|---|
| S1 | `Profiles UNIQUE tuple` | Backfill migration | `(Family, QualityTier, ContentClass, TargetResolutionCategory)` | ContentClassifier + NextTierAdjuster | `TestProfileTierLadder` |
| S2 | `ProfileThresholds.TargetKbps -> VideoSlot NVENC / QSV VBR` | EncoderKnobRepository row | absolute INT kbps | VideoSlot emits `-b:v <TargetKbps>k` | `TestCommandComposer` |
| S3 | `NextTierAdjuster -> AddJobToQueue` | Dispatcher on Requeue | escalated ProfileId | requeued row uses new profile knobs | `TestNextTierAdjuster` + smoke |
| S4 | `/settings` knobs -> content class | `PUT /api/SystemSettings/LibraryTiers` (`DefaultContentClass`), `PUT /api/SystemSettings/GenreTiers` (`ContentClass`) | `StorageRoots.DefaultContentClass TEXT NULL`, `GenreQualityTiers.ContentClass TEXT NULL`, both CHECK `('live_action','animation')` | `ContentClassResolver` reads both fresh per call | `TestProfileRowLookup` (C10) |
| S5 | `(ProfileName, ContentClass, Resolution) -> ProfileRow` | `TierLadderRepository.GetProfileRow` | one joined `Profiles` + `ProfileThresholds` row (`ProfileRow`) or `None` | `EvaluateQueueAdmission`, `EncoderKnobRepository.GetEncoderKnobsForProfile`, `EffectiveProfileResolver`, `VideoVertical` | `TestProfileRowLookup` (C9) |

## Status

Shipped 2026-07-04 via `transcode-flow-canonical` directive Reset 10 + Reset 14 (promoted from directive parked section at DELIVERING).

## Files

- `Features/Profiles/EncoderKnobRepository.py` -- reads TargetKbps
- `Features/Profiles/TierLadderRepository.py` -- (Family, ContentClass[, Resolution]) x Tier grid queries
- `Features/TranscodeJob/Adjustments/NextTierAdjustmentCalculator.py` -- ceiling-terminating walk
- `Features/TranscodeJob/Emit/Slots/VideoSlot.py` -- consumes TargetKbps
- `Scripts/SQLScripts/AlignProfileTierModel_2026_07_04.py` -- schema
- `Scripts/SQLScripts/BackfillFullCanaryTierLadder_2026_07_04.py` -- data
- `Scripts/SQLScripts/DeleteNonCanaryProfiles_2026_07_04.py` -- cleanup
- `Scripts/SQLScripts/ConsolidateCanaryProfileNames_2026_07_04.py` -- rename sweep
- `Tests/Contract/TestProfileTierLadder.py` -- schema invariants
- `Tests/Contract/TestNextTierAdjuster.py` -- ceiling behavior
