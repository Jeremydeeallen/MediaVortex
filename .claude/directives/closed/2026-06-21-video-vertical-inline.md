# Inline VideoVertical (Drop Compliance Wrap)

**Slug:** video-vertical-inline
**Set:** 2026-06-21
**Closed:** 2026-06-21
**Status:** Closed -- Success

## Outcome

`VideoVertical._EvaluateOne` inlines the four predicates from `Features/Compliance/Operations/TranscodeOperation.Apply` directly. Drops imports of `TranscodeOperation` and `TranscodeRulesModel`. VideoVertical no longer depends on `Features/Compliance/`. Re-backfill VideoCompliant; confirm identical equivalence diff. After this, all three new verticals (Audio, Video, Container) are fully self-contained -- ready for cutover.

## Acceptance Criteria

C1. `Features/VideoEncoding/VideoVertical.py` has zero `from Features.Compliance` imports. `grep 'Features\.Compliance' Features/VideoEncoding/VideoVertical.py` returns 0.
C2. Inline predicates match TranscodeOperation.Apply behavior:
   (a) `PreventUpscale` + src tier < target tier -> return `(True, 'upscale_prevented')` (compliant; no transcode needed -- per current `Applies=False` short-circuit)
   (b) `ResolutionExceedsProfileTarget` + src tier > target tier -> mark not-compliant
   (c) source codec not in `AcceptableVideoCodecsCsv` -> mark not-compliant
   (d) `EstimatedSavingsMB >= EstimatedSavingsMBThreshold` AND NOT `TranscodedByMediaVortex` -> mark not-compliant
   (e) `EstimatedSavingsMB >= threshold` AND `TranscodedByMediaVortex=TRUE` -> skip (don't re-transcode mv-trusted files)
C3. Resolution tier comparison uses `ResolutionTier.Rank` (no string heights; per resolution-types.C5).
C4. EstimatedSavingsMB formula: `(SizeMB) - ((TargetVideoKbps + TargetAudioKbps) * DurationMinutes * 60 / (8 * 1024))`, clamped at 0. `None` when `TargetVideoKbps` is 0/null or `DurationMinutes <= 0`.
C5. MinSourceBpp override unchanged from directive 6: when inline predicates say "needs transcode" but BPP < threshold, override to compliant via `efficient_bpp_override`.
C6. Re-backfill 50,303 files. Equivalence diff unchanged (identical mismatch counts).
C7. `video-encoding.feature.md` "Known Gap to Target" section updated: TranscodeOperation wrap removed; only remaining "known gap" is the 24fps assumption.

## Status

### Verification

- **C1**: `grep 'Features\.Compliance' Features/VideoEncoding/VideoVertical.py` returns zero matches. VideoVertical is now Compliance-free.
- **C2**: Inline `_EvaluateOne` matches TranscodeOperation behavior: PreventUpscale short-circuit, ResolutionExceedsProfileTarget mark, codec NOT IN list mark, savings >= threshold + NOT MvTrusted mark, MvTrusted skip. Verified via per-rule code path in the inlined function.
- **C3**: `SrcTier.Rank` + `TgtTier.Rank` comparisons used; no string heights. ResolutionTierRegistry resolves the source category to a typed Tier.
- **C4**: `_EstimatedSavingsMB` is a faithful copy of TranscodeOperation._EstimatedSavingsMB: returns None on no-TargetVideoKbps or non-positive DurationMinutes, else `(SizeMB) - ((TargetVk + TargetAk) * Dur * 60 / 8192)` clamped at 0.
- **C5**: `_IsAlreadyEfficient` and the override logic unchanged from directive 6.
- **C6**: Backfill 50,305 files in 203s. Post-backfill equivalence: MATCH counts identical to directive 3 close (the +2 in `Transcode -> (null)` is new MediaFiles added during the brief window between backfills). Inlining produced identical behavior.
- **C7**: `video-encoding.feature.md` "Known Gap to Target" section dropped the Compliance-dependency line; only the 24fps assumption remains.

### Promotions

| Source artifact | Target file | Commit |
|---|---|---|
| Inline predicates (drop TranscodeOperation wrap) | `Features/VideoEncoding/VideoVertical.py` | next commit |
| Compliance-dependency known-gap line removed | `Features/VideoEncoding/video-encoding.feature.md` | next commit |

### Decisions Made

- `_EstimatedSavingsMB` lifted as a static method with identical formula and edge cases. Could have factored to a shared helper but inlining keeps VideoVertical self-contained (zero shared private helpers).
- `MvTrusted` skip behavior preserved exactly: when EstSavings exceeds threshold AND TranscodedByMediaVortex=TRUE, the file is treated as already-done (skip the savings predicate, don't re-transcode). Per memory `mv-trust-savings-and-clamp` directive.
- All three new verticals (Audio, Video, Container) are now fully self-contained with zero `Features/Compliance/` imports. Ready for directive 5 (UI) and directive 6 (cutover).
