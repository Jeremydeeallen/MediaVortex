# Directive: video-vertical-codec-match-skip

**Status:** Active -- phase: IMPLEMENTING

**Slug:** video-vertical-codec-match-skip

**Interrupts:** compliance-gate-dialog-boost-signal (Closed).

## Context

Recent cartoon data (Animaniacs, 12 samples) shows we're re-encoding files whose source codec is ALREADY AV1 (Tier 1 target). Sources 183-656 kbps at 28-69 MB. Outputs 6-24 MB. Real 52-83% savings BUT:

1. **Second-generation AV1 compression** -- quality compounds on repeated passes.
2. **Compute cost > storage payoff** -- ~1-3 min/file for ~30 MB per-file savings.
3. **No architectural stop** -- ceiling gate is bitrate-only; nothing checks src_codec vs target_codec.

Operator's ceiling gate was raised to 400 * 4.0 = 1600 for 480p live_action / 350 * 4.0 = 1400 for 480p animation. AV1 sources at 183-656 kbps pass ceiling easily -- but they're already AT the target codec and should never be reencoded.

## Domain policy (locked by operator 2026-08-14)

- **If source codec == target codec, video is compliant.** No re-encode. Period.
- KISS: one predicate. No size floor, no per-minute math. Codec match alone.
- Target codec derived from AssignedProfile's ProfileThresholds row (existing `TierLadderRepository` lookup).

## Acceptance Criteria

- C1: `VideoVertical.Evaluate` returns `(True, 'source_codec_matches_target')` when normalized(`Mf.Codec`) == normalized(target codec from ProfileThresholds for `AssignedProfile` + `ContentClass` + `ResolutionCategory`), ahead of the ceiling check. Ceiling check runs only when codecs differ.
- C2: Existing ceiling behavior unchanged when codecs differ (e.g. h264 source targeting AV1 still gates on 400*multiplier).
- C3: Recompute across full library flips MV-output files (`-mv.mp4` = av1 source, av1 target) to `VideoCompliant=TRUE, VideoCompliantReason='source_codec_matches_target'`.
- C4: Contract test `Tests/Contract/TestVideoVerticalCodecMatch.py` covers 4 cases: (a) src=target -> Compliant; (b) src!=target, src<=ceiling -> Compliant; (c) src!=target, src>ceiling -> non-Compliant; (d) src=target but src>ceiling -> Compliant (codec match wins).
- C5: `video-encoding.feature.md` amended: codec-match short-circuit named in Evaluate contract.
- C6: `TierLadderRepository` exposes a `GetProfileCodec(ProfileName)` helper if not already present; else Evaluate reads codec inline from the profile row.

## Call-Graph Audit

1. Multiple flow docs -- clean. VideoVertical is single-purpose.
2. Mode-branching -- clean. Evaluate is mode-agnostic; new predicate is data-driven, not orchestration.
3. Shared output columns -- `VideoCompliant` written by VideoVertical.RecomputeFor only. No sparse population.
4. Config-driven call-graph -- clean. Same functions run regardless of codec.
5. OOS explicit below.

## Out of Scope

- (a) Absolute size floor for Pinky-class small h264 files -- separate concern; operator has not directed a threshold. Filed for follow-up.
- (a) Multi-codec target profiles (Tier 2, Tier 3 h264-family) -- Tier 1 is AV1-only; other tiers if they exist follow the same rule structurally.
- (b) Second-generation encode QUALITY audit of existing MV outputs already re-encoded -- historical damage; not this directive's scope.
- (a) Stale queue-row purge for MV-source Transcode rows -- run post-recompute as part of verification.

## Files

**Edit:**
- `Features/VideoEncoding/VideoVertical.py` (add codec-match early return)
- `Features/Profiles/TierLadderRepository.py` (if `GetProfileCodec` helper doesn't exist yet)
- `Features/VideoEncoding/video-encoding.feature.md` (C1/C2 amendments at DELIVERING)

**Create:**
- `Tests/Contract/TestVideoVerticalCodecMatch.py`

## Status

Phase: NEEDS_STANDARDS_REVIEW
Opened: 2026-08-14
Owner: claude-opus-4-7
