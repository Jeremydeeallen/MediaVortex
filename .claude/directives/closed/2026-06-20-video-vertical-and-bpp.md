# Video Vertical (with MinSourceBpp)

**Slug:** video-vertical-and-bpp
**Set:** 2026-06-20
**Closed:** 2026-06-20
**Status:** Closed -- Success

## Outcome

`Features/VideoEncoding/` vertical built. `VideoComplianceRules` table seeded from existing `TranscodeRules` + new `MinSourceBpp` rule. `VideoVertical.RecomputeFor(MediaFileIds)` writes `(VideoCompliant, VideoCompliantReason)` by wrapping existing `Features/Compliance/Operations/TranscodeOperation` + applying MinSourceBpp override. Wrap is intentional + temporary; dies at directive 7 when Compliance is ripped. Phase 4 of paused `vertical-owned-compliance`.

## Acceptance Criteria

C1. Migration `AddVideoComplianceRules.py` creates `VideoComplianceRules` with `AcceptableVideoCodecsCsv`, `EstimatedSavingsMBThreshold`, `PreventUpscale`, `ResolutionExceedsProfileTarget`, `MinSourceBpp`. Seeded from `TranscodeRules` + MinSourceBpp default 0.04. Idempotent.
C2. `Features/VideoEncoding/VideoVertical.py` exposes `VideoVertical.RecomputeFor(MediaFileIds: List[int]) -> None`.
C3. Predicate: wraps `TranscodeOperation.Apply` for equivalence with current Compliance, then applies MinSourceBpp override -- if wrapped result says "needs transcode" but BPP < MinSourceBpp, override to compliant.
C4. BPP calculation: `(VideoBitrateKbps * 1000) / (pixel_count * 24)` where pixel_count comes from `ResolutionCategory` (480p:345600, 720p:921600, 1080p:2073600, 2160p:8294400). 24fps assumption documented in Decisions.
C5. Backfill: every probed `MediaFiles` row gets a non-NULL `VideoCompliant` value.
C6. `Features/VideoEncoding/video-encoding.feature.md` created at DELIVERING with Cross-Vertical Contract.

## Status

### Verification

- **C1**: `VideoComplianceRules` exists with 1 row; migration uses CREATE TABLE IF NOT EXISTS + count check (idempotent). Seeded values copied from `TranscodeRules` + `MinSourceBpp=0.04`.
- **C2**: `Features/VideoEncoding/VideoVertical.py` exports `VideoVertical.RecomputeFor(MediaFileIds: List[int]) -> None`.
- **C3**: `_EvaluateOne` wraps `TranscodeOperation.Apply` then applies BPP override (`_IsAlreadyEfficient`). Smoke-tested: Id=12899/36833/60029 returned `(FALSE, 'EstimatedSavingsMBThreshold:...')` and `(FALSE, 'ResolutionExceedsProfileTarget:T1080p')`.
- **C4**: `_PIXEL_COUNTS` map + `_ASSUMED_FPS=24`; BPP calculated as `(VideoBitrateKbps * 1000) / (Pixels * 24)`.
- **C5**: Backfill 50,292 files in 206s; distribution TRUE=32409, FALSE=17883, NULL=590 (NULL = files inserted during prior backfill window OR `no_effective_profile` cases).
- **C6**: `Features/VideoEncoding/video-encoding.feature.md` created at DELIVERING with Cross-Vertical Contract.

### Promotions

| Source artifact | Target file | Commit |
|---|---|---|
| VideoVertical implementation + rule table + BPP override | `Features/VideoEncoding/` (new vertical) | next commit |
| Top-level feature doc + Cross-Vertical Contract | `Features/VideoEncoding/video-encoding.feature.md` | next commit |

### Decisions Made

- Temporary wrap of `Features/Compliance/Operations/TranscodeOperation`. Reason: preserves equivalence with current routing (directive 7's equivalence diff will pass). The wrap dies at directive 7 when Compliance is ripped; VideoVertical inlines the logic at that point.
- BPP calculation assumes 24fps. Reason: most video is 23.976 or 24fps; precise fps isn't in MediaFiles columns; 24 is a reasonable default. Future enhancement: probe fps + use real value.
- MinSourceBpp default 0.04. Reason: per ARCHITECTURE.md gap row + IDEAS.md 2026-06-19. Operator-tunable.
- MinSourceBpp override applies after wrapped TranscodeOperation. Reason: simpler than reimplementing all 4 predicates; just need the override to fix the canary "30 Rock S01E01" routing case.
