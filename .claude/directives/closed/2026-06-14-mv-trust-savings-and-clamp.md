# MV-Trust on Compliance Savings Rule + Resolver Clamp

**Set:** 2026-06-14
**Status:** Active -- phase: IMPLEMENTING
**Slug:** mv-trust-savings-and-clamp

## Outcome

Files already transcoded by MediaVortex with an acceptable codec stop being re-bucketed for size. Resolver respects the operator-configured `MinBitrateKbps` / `MaxBitrateKbps` floor/ceiling on the VBR (`SourceBitratePercent`) strategy. The Activity dashboard's "compliant" count flips upward as recently-transcoded files settle into `IsCompliant=TRUE`.

## Why

Operator dogfood 2026-06-14: 545 of 693 (78%) successful transcodes in the last 24h were still showing `IsCompliant=False, WorkBucket='Transcode'`. Root causes:
1. **Engine doesn't see `TranscodedByMediaVortex`** -- `_RowToMediaFileForCompliance` + `RecomputeForFiles` SELECT + `ComplianceRecomputeService.Recompute` SELECT all omit it.
2. **Resolver ignores `MinBitrateKbps` / `MaxBitrateKbps` clamps** -- `_LookupThresholdsRow` doesn't SELECT them; `_ResolveTargetVideoKbps` VBR branch returns raw `source * percent / 100` even when the profile configures a 350 kbps floor (so a 607-kbps AV1 480p source gets a 182 kbps target -> savings estimate wildly inflated -> Transcode op fires).

Result: the `EstimatedSavingsMBThreshold` rule fires on already-AV1-at-target-tier files. They cannot re-queue (TranscodeQueue.feature.md C3 blocks `TranscodedByMediaVortex=TRUE`) so they sit in limbo: non-compliant per the engine, un-queueable per admission. Compliant count never moves.

## Acceptance Criteria

1. **MV-trust on savings rule.** `TranscodeOperation.Apply` does NOT fire the `EstimatedSavingsMBThreshold` rule when `Mf.TranscodedByMediaVortex == True`. Codec / resolution / upscale rules still fire -- those catch correctness mismatches. Verifiable: synthetic MediaFile with `TranscodedByMediaVortex=True, Codec='av1', ResolutionCategory='480p'` + profile NVENC AV1 -720p -> `Decision.IsCompliant=True, WorkBucket=None`. Same file with `TranscodedByMediaVortex=False` (or NULL) -> savings rule fires as before.

2. **Resolver clamp on VBR strategy.** `_LookupThresholdsRow` SELECTs `MinBitrateKbps` + `MaxBitrateKbps`; `_ResolveTargetVideoKbps` VBR branch returns `max(MinBitrateKbps or 0, min(MaxBitrateKbps or +inf, computed))`. Verifiable: row with `SourceBitratePercent=30, MinBitrateKbps=350, MaxBitrateKbps=600, source=607` returns 350 (not 182). Row with `source=2400` returns 600 (clamped to ceiling).

3. **Wiring complete.** `TranscodedByMediaVortex` flows from DB row -> `_RowToMediaFileForCompliance` -> `MediaFileModel` -> `TranscodeOperation.Apply`. Same path via `ComplianceRecomputeService.Recompute`. Verifiable: forcing `RecomputeForFiles([MfId])` on a previously-stuck row makes it `IsCompliant=True`.

4. **Live remediation.** After deploy + recompute, the count of `IsCompliant=False AND WorkBucket='Transcode' AND TranscodedByMediaVortex=True AND ResolutionCategory IN ('480p','720p') AND Codec IN ('av1','hevc','h264')` drops by >=400 rows (from the ~482 current). Verifiable: live SQL diff before/after.

5. **CI invariant tests.** `Tests/Contract/TestTranscodeOperationMvTrust.py` covers AC1 + AC2 with mocked dependencies. Existing `TestComplianceEngine.py` still green.

## Files

```
Features/Compliance/Services/EffectiveProfileResolver.py   -- AC2 clamp
Features/Compliance/Operations/TranscodeOperation.py       -- AC1 skip
Features/Compliance/Services/ComplianceRecomputeService.py -- AC3 wiring
Features/TranscodeQueue/QueueManagementBusinessService.py  -- AC3 wiring
Tests/Contract/TestTranscodeOperationMvTrust.py            -- AC5 NEW
```
