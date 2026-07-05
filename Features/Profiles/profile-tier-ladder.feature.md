# Profile Tier Ladder

**Slug:** profile-tier-ladder

## What It Does

Replaces per-profile-name proliferation with a 3-axis tuple: `(Family, QualityTier, ContentClass)` at `TargetResolutionCategory`. Family names the encoder + preset (e.g. `NVENC AV1 CANARY`, `QSV AV1 CANARY`). QualityTier ranges 1..5 (small/low-quality -> large/near-source). ContentClass in `{live_action, animation, mixed}`. TargetResolutionCategory reuses the resolution-types tier registry. Every combination = one Profile row. Deleting non-CANARY AV1 profiles kills naming variance that was driving operator confusion.

## Workflows

| # | User action | Surface | Handler | Backing |
|---|---|---|---|---|
| W1 | Operator edits a tier's TargetKbps on /settings Transcoding card | `/settings` bitrate ladder editor | `PUT /api/SystemSettings/Transcoding` | `SystemSettingsController.SaveTranscodingSettings` -> `ProfileThresholds.TargetKbps` UPDATE |
| W2 | ContentClassifier auto-assigns a Family + Tier + ContentClass to a new MediaFile | (internal) | ContentClassifier.Classify | `ContentClassifier.Classify` -> writes `MediaFiles.AssignedProfile` (by tuple lookup) |
| W3 | Dispatcher escalates on VMAF fail -> next-tier profile | (internal) | `NextTierAdjuster.Get` | `Features/TranscodeJob/Adjustments/NextTierAdjustmentCalculator` |

## Success Criteria

C1. `Profiles` schema adds `Family TEXT NOT NULL`, `QualityTier INT NOT NULL CHECK (QualityTier BETWEEN 1 AND 5)`, `ContentClass TEXT NOT NULL CHECK (ContentClass IN ('live_action','animation','mixed'))`. UNIQUE `(Family, QualityTier, ContentClass, TargetResolutionCategory)`. Verifiable: `\d Profiles` shows the three columns + CHECKs + UNIQUE.

C2. `ProfileThresholds` schema adds `TargetKbps INT NOT NULL`. Dead columns `SourceBitratePercent`, `MinBitrateKbps`, `MaxBitrateKbps` dropped. `IcqQ INT NULL` added (populated for ICQ profiles). Verifiable: `\d ProfileThresholds` matches; grep `SourceBitratePercent` in `Features/**/*.py` returns 0.

C3. Two families kept: `'NVENC AV1 CANARY'` + `'QSV AV1 CANARY'`. Every non-CANARY AV1 profile deleted via `DeleteNonCanaryProfiles_2026_07_04.py`. Orphaned `MediaFiles.AssignedProfile` reassigned via ContentClassifier. Verifiable: `SELECT COUNT(*) FROM Profiles WHERE Codec IN ('av1_nvenc','av1_qsv','libsvtav1') AND Family NOT IN ('NVENC AV1 CANARY','QSV AV1 CANARY')` returns 0.

C4. Backfill populates two families x four resolutions x five tiers x live-action rows. TargetKbps table (live-action calibration): 480p=[400,550,700,900,1200] / 720p=[900,1400,1900,2500,3200] / 1080p=[1800,2400,3200,4200,5500] / 2160p=[4000,6000,8500,12000,18000]. ICQ ladder q34/q30/q28/q26/q22 per QSV rows. Verifiable: `SELECT * FROM Profiles p JOIN ProfileThresholds pt ON pt.ProfileId=p.Id WHERE p.Family='NVENC AV1 CANARY' AND p.ContentClass='live_action'` returns 20 rows (4 res x 5 tier).

C5. NVENC VBR video slot consumes `TargetKbps` directly. Emits `-b:v <TargetKbps>k -maxrate:v <TargetKbps * MaxBitrateMultiplier>k -bufsize:v <same>k`. No percent-of-source math, no min/max clamps. Verifiable: `Tests/Contract/TestCommandComposer` asserts emitted argv contains the raw TargetKbps value.

C6. QSV ICQ video slot consumes `IcqQ` directly. Emits `-global_quality <IcqQ>`. No percent-of-source. Verifiable: `Tests/Contract/TestCommandComposer` asserts emitted argv contains the raw IcqQ value.

C7. `NextTierAdjuster.Get(currentProfile)` returns `Optional[Profile]` by walking the UNIQUE tuple with `QualityTier + 1`. Returns None when ceiling hit (Tier 5). Verifiable: `Tests/Contract/TestNextTierAdjuster.py` covers tier-1 -> tier-5 chain + ceiling terminates.

C8. `DispositionDispatcher._MaybeScheduleRequeue` passes escalated `ProfileId` to `AddJobToQueue` when adjuster returns non-None. Chain terminates at Tier 5 -> Reject/QualityCeilingReached (folds through RetryBudget). Verifiable: dispatcher contract test proves ProfileId in the requeued queue row differs from previous when adjuster escalates.

## Seams

| ID | Seam | Producer | Wire shape | Consumer expects | Verification |
|---|---|---|---|---|---|
| S1 | `Profiles UNIQUE tuple` | Backfill migration | `(Family, QualityTier, ContentClass, TargetResolutionCategory)` | ContentClassifier + NextTierAdjuster | `TestProfileTierLadder` |
| S2 | `ProfileThresholds.TargetKbps -> VideoSlot NVENC VBR` | EncoderKnobRepository row | absolute INT kbps | VideoSlot emits `-b:v <TargetKbps>k` | `TestCommandComposer` |
| S3 | `NextTierAdjuster -> AddJobToQueue` | Dispatcher on Requeue | escalated ProfileId | requeued row uses new profile knobs | `TestNextTierAdjuster` + smoke |

## Status

Shipped 2026-07-04 via `transcode-flow-canonical` directive Reset 10 + Reset 14 (promoted from directive parked section at DELIVERING).

## Files

- `Features/Profiles/EncoderKnobRepository.py` -- reads TargetKbps + IcqQ
- `Features/Profiles/TierLadderRepository.py` -- (Family, ContentClass[, Resolution]) x Tier grid queries
- `Features/TranscodeJob/Adjustments/NextTierAdjustmentCalculator.py` -- ceiling-terminating walk
- `Features/TranscodeJob/Emit/Slots/VideoSlot.py` -- consumes TargetKbps / IcqQ
- `Scripts/SQLScripts/AlignProfileTierModel_2026_07_04.py` -- schema
- `Scripts/SQLScripts/BackfillFullCanaryTierLadder_2026_07_04.py` -- data
- `Scripts/SQLScripts/DeleteNonCanaryProfiles_2026_07_04.py` -- cleanup
- `Scripts/SQLScripts/ConsolidateCanaryProfileNames_2026_07_04.py` -- rename sweep
- `Tests/Contract/TestProfileTierLadder.py` -- schema invariants
- `Tests/Contract/TestNextTierAdjuster.py` -- ceiling behavior
