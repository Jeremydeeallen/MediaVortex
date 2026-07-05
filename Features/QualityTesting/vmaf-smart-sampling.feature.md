# VMAF Smart Sampling

**Slug:** vmaf-smart-sampling

## What It Does

Skips VMAF for source+profile combinations that have accumulated statistical confidence over prior successful runs. Groups sources into buckets by `(ProfileId, SourceCodec, SourceResolutionTier, BitratePerPixelBucket, ContentClass)`. Tracks rolling pass-rate + mean/stddev per bucket. When a bucket has enough samples AND high pass rate AND mean minus N-sigma exceeds the auto-replace threshold, VMAF is skipped and the disposition returns `Replace/QualityTestConfident`. New buckets bootstrap at SampleCount=0 and force VMAF until confidence builds. Drift automatic: pass-rate drops -> VMAF resumes.

## Workflows

| # | User action | Surface | Handler | Backing |
|---|---|---|---|---|
| W1 | Attempt lands with a bucket that already has confidence | (internal) | Decider.Decide | SmartConfidenceSkip branch -> Replace/QualityTestConfident |
| W2 | VMAF completes on a Pending attempt | (internal) | QualityTestingBusinessService | VmafConfidenceStatsRepository.RecordResult updates bucket stats |
| W3 | Operator tunes confidence knobs on /settings | `/settings` VMAF section | PUT /api/SystemSettings/Transcoding | PostTranscodeGateConfig update |
| W4 | Operator reviews per-bucket stats | `/settings` review panel | GET /api/SystemSettings/Transcoding | VmafConfidenceStatsRepository.GetAllForReview |

## Success Criteria

C1. New table `VmafConfidenceStats` with columns `(Id BIGSERIAL PK, ProfileId BIGINT REFERENCES Profiles(Id), SourceCodec TEXT NOT NULL, SourceResolutionTier TEXT NOT NULL, BitratePerPixelBucket INT NOT NULL, ContentClass TEXT NOT NULL, SampleCount INT NOT NULL DEFAULT 0, VmafMean NUMERIC(5,2), VmafStdDev NUMERIC(5,2), PassRate NUMERIC(5,4), SamplesJson JSONB, LastUpdated TIMESTAMP DEFAULT NOW())`. UNIQUE `(ProfileId, SourceCodec, SourceResolutionTier, BitratePerPixelBucket, ContentClass)`. Verifiable: `\d VmafConfidenceStats`.

C2. `PostTranscodeGateConfig` gains `MinConfidenceSampleCount INT NOT NULL DEFAULT 10`, `MinConfidencePassRate NUMERIC NOT NULL DEFAULT 0.95`, `SigmaMargin NUMERIC NOT NULL DEFAULT 2.0`. Verifiable: `\d PostTranscodeGateConfig`.

C3. `VmafConfidenceStatsRepository.LookupBucket(ProfileId, SourceCodec, SourceResolutionTier, BitratePerPixelBucket, ContentClass)` reads DB fresh per call (db-is-authority). Returns None when bucket has no row. Verifiable: `Tests/Contract/TestVmafConfidenceStatsRepository.py`.

C4. `VmafConfidenceStatsRepository.RecordResult(bucket_key, vmaf_score, passed)` INSERTs on first sample OR UPDATEs an existing row via a rolling-window recompute (N=100 via `SamplesJson` trim): SampleCount += 1 (capped), VmafMean/StdDev recomputed over the retained window, PassRate = passed_count / retained_count. Idempotent within a single VMAF completion. Verifiable: unit test.

C5. `PostTranscodeDispositionDecider.Decide` adds `SmartConfidenceSkip` branch between the QualityTestNotRequired short-circuit and the VMAF-NULL Pending short-circuit. Logic: `if stats.SampleCount >= MinConfidenceSampleCount AND stats.PassRate >= MinConfidencePassRate AND (stats.VmafMean - SigmaMargin * stats.VmafStdDev) >= VmafAutoReplaceMinThreshold: return Disposition('Replace', 'QualityTestConfident')`. Verifiable: `Tests/Contract/TestSmartConfidenceSkip.py` covers bootstrap (SampleCount=0 forces VMAF), confidence-built (N pass -> skip), drift (one fail drops PassRate below threshold -> VMAF resumes).

C6. `BitratePerPixelBucket` computed as INT bucket (1..5) over `(SourceKbps * 1000) / (Width * Height * (fps/24.0))` with quintile boundaries persisted in `SystemSettings.BitratePerPixelBoundaries` (JSON array). Bucket 1 = lowest, Bucket 5 = highest. Verifiable: `Tests/Contract/TestSmartConfidenceSkip.py::test_bucket_computation`.

C7. Reason vocabulary gains `QualityTestConfident`. `SELECT DISTINCT DispositionReason FROM TranscodeAttempts` still returns only closed-list values. Verifiable: audit query.

## Seams

| ID | Seam | Producer | Wire shape | Consumer expects | Verification |
|---|---|---|---|---|---|
| S1 | `Decider -> VmafConfidenceStatsRepository.LookupBucket` | Decider computes bucket key | `(ProfileId, SourceCodec, SourceResolutionTier, BitratePerPixelBucket, ContentClass)` | `Stats(SampleCount, VmafMean, VmafStdDev, PassRate)` or None | `TestSmartConfidenceSkip` |
| S2 | `QualityTestingBusinessService -> VmafConfidenceStatsRepository.RecordResult` | On VMAF completion | `(bucket_key, VmafScore, Passed: bool)` | rolling-window update commits | `TestSmartConfidenceSkip` roundtrip |
| S3 | `PostTranscodeGateConfig confidence knobs` | operator via /settings | `MinConfidenceSampleCount / MinConfidencePassRate / SigmaMargin` | Decider reads fresh per call | UI form save + Decider unit test |

## Status

Shipped 2026-07-04 via `transcode-flow-canonical` directive Reset 10 (backend + Decider branch) + Reset 11 (SystemSettings review panel) + Reset 14 (promoted at DELIVERING).

## Files

- `Features/QualityTesting/VmafConfidenceStatsRepository.py`
- `Features/QualityTesting/Disposition/PostTranscodeDispositionDecider.py` -- SmartConfidenceSkip branch + bucket key builder
- `Features/QualityTesting/QualityTestingBusinessService.py` -- `_RecordVmafConfidenceStats` write-back
- `Scripts/SQLScripts/AlignProfileTierModel_2026_07_04.py` -- schema (VmafConfidenceStats + PostTranscodeGateConfig knobs)
- `Scripts/SQLScripts/AddVmafConfidenceStatsSamplesJson_2026_07_04.py` -- rolling window column
- `Tests/Contract/TestSmartConfidenceSkip.py` -- 8 tests
- `Tests/Contract/TestVmafConfidenceStatsRepository.py` -- 6 tests
