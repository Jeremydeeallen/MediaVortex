# Directive: video-vertical-codec-match-skip

**Status:** Closed

**Slug:** video-vertical-codec-match-skip

**Interrupts:** compliance-gate-dialog-boost-signal (Closed).

## Files

**Edit:**
- `Features/VideoEncoding/VideoVertical.py`
- `Features/Profiles/TierLadderRepository.py`
- `Features/VideoEncoding/video-encoding.feature.md`

**Create:**
- `Tests/Contract/TestVideoVerticalCodecMatch.py`

### Promotions

- Codec-match short-circuit predicate ahead of ceiling check -> `Features/VideoEncoding/video-encoding.feature.md` C1 rewritten to name (a) codec-match and (b) ceiling branches.
- `TierLadderRepository.GetProfileCodec(ProfileName) -> Optional[str]` helper published; reads `Profiles.Codec` normalized to lowercase.
- Contract test `Tests/Contract/TestVideoVerticalCodecMatch.py` regression guard covers all 4 codec x ceiling permutations.

### Delivery Report

- DIRECTIVE: kill AV1->AV1 second-generation reencodes (Animaniacs-class) by short-circuiting VideoVertical.Evaluate when source codec matches target codec.
- STATUS: Done. Fleet on 6e8af990.
- WHAT SHIPPED: 2 code edits + 1 helper + 1 contract test + feature-doc C1 rewrite. 138 files flipped VideoCompliant=TRUE via recompute. Post-deploy encodes write new reason 'source_codec_matches_target:<codec>' via writer-owns-cascade (139 rows observed with new reason).
- HOW TO USE IT: no operator action. Any AV1 source assigned to an AV1 profile now returns Compliant regardless of source bitrate. Skips Transcode bucket, skips re-encode cycle.
- WHAT YOU NEED TO EXECUTE: nothing. Deploy already applied. Optional cosmetic: run VideoVertical.RecomputeFor on all AV1-source rows to normalize reason strings; state already correct so purely cosmetic.
- CRITERIA VERIFICATION:
  - C1 verified: `py -c 'V.RecomputeFor([31868])'` -> reason `source_codec_matches_target:av1(profile=AV1 Tier 1 Efficient)`.
  - C2 verified via TestVideoVerticalCodecMatch::test_src_differs_below_ceiling_is_compliant + test_src_differs_above_ceiling_is_noncompliant (pass).
  - C3 verified: 138 files with codec-match + previously-non-compliant flipped to VideoCompliant=TRUE.
  - C4 4/4 contract test green.
  - C5 video-encoding.feature.md C1 rewritten.
  - C6 GetProfileCodec helper shipped.
- DECISIONS I MADE:
  - Codec normalization: LOWER(codec) match. Avoided elaborate encoder-family mapping (libsvtav1 -> av1) because Profiles.Codec is already stored as 'av1' for Tier 1..5 rows. Case-insensitive match handles the observed data cleanly.
  - Recompute scope: 138 flippers (codec-match + currently non-compliant). Cosmetic-only reason-string backfill deferred (writer-owns-cascade handles going forward).
  - Codec-match wins over ceiling: even if source > ceiling, codec match returns Compliant. Reason: no upside to re-encoding same codec regardless of bitrate; per-codec artifact accumulation dominates the ceiling concern.
- KNOWN GAPS / DEFERRED:
  - Absolute size floor for Pinky-class small h264 files -- separate concern, no operator threshold set yet.
  - Cosmetic reason-string backfill for codec-match files already Compliant -- state correct, reason strings will drift to codec-match naturally as attempts land or via targeted recompute.
