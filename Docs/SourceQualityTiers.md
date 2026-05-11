# Source Quality Tiers

How to classify a media file's source quality before re-encoding, and what VMAF outcome to expect from each tier.

## TL;DR

A clean source produces VMAF 92-97 trivially. A bloated 1080p H264 source caps around 78-82 regardless of encoder settings. The ceiling is the reference, not the encoder. Tier your sources before tuning thresholds.

The codec name (H264 vs H265 vs AV1) is a weaker signal than people assume. **Bitrate per pixel** and **release tag** carry the actual quality information.

## The Tier Table

| Tier | Release-tag patterns | Typical 1080p bitrate | Bits per pixel | Realistic re-encode VMAF (1080p source) |
|---|---|---|---|---|
| Master | `REMUX`, `UHD REMUX`, `BluRay REMUX` | 25-40 Mbps | > 0.10 | 92-97 |
| Excellent | `BluRay`, `BDRip` (high-bitrate), `1080p BluRay` | 8-15 Mbps | 0.05-0.10 | 88-94 |
| Good | `WEB-DL` from premium platforms (Netflix UHD, Apple TV+, Amazon UHD, Disney+ UHD) | 6-12 Mbps | 0.04-0.08 | 85-92 |
| Mediocre | `WEB-DL` from mid platforms (Hulu, basic Netflix HD, Paramount+ HD) | 3-5 Mbps | 0.02-0.04 | 78-85 |
| Avoid | `WEBRip`, `HDTV`, `HDRip`, `DVDRip`, `CAM`, `TS` | 2-4 Mbps | < 0.02 | < 78 (often much lower) |

Note: 4K (2160p) shifts the bitrate columns up roughly 3-4x. The bpp column is the resolution-independent measure.

## How To Compute Bits Per Pixel

```
bpp = (bitrate_kbps * 1000) / (width * height * fps)
```

Worked example:

| File | Bitrate | Resolution | FPS | bpp | Tier |
|---|---|---|---|---|---|
| New Girl S01E01 1080p H264 | 4600 kbps | 1920x1080 | 23.976 | 0.0926 | Mediocre / Good edge |
| Sister Wives 1080p BluRay | 9800 kbps | 1920x1080 | 23.976 | 0.197 | Excellent |
| 4K UHD master (test source) | 25400 kbps | 3840x2160 | 23.976 | 0.128 | Master |
| Old DVDRip | 1800 kbps | 720x480 | 29.97 | 0.174 | (DVDRip floor — tier by tag, not bpp here) |

For SD content (480p or lower), bpp tiers do not apply cleanly; tier by release tag alone.

## Why Codec Name Is Misleading

Counterintuitive but consistent: **high-bitrate H264 is a better re-encode source than low-bitrate H265.**

H265 and AV1 sources have already had a perceptual encoder squeeze them once. Re-encoding to AV1 cascades two perceptual models on top of each other:

- The first encoder's artifact set gets locked into the new encode (it looks like signal to the second encoder).
- The second encoder has less compression headroom — most of the redundancy the AV1 model would exploit was already removed.
- Subjective quality often LOOKS fine while VMAF scores poorly, because the AV1 encoder is preserving compression noise as "structure."

By contrast, a high-bitrate H264 source is essentially raw video plus mild quantization noise. AV1 has full headroom and can produce dramatic savings with high VMAF.

**Heuristic**: prefer a 12 Mbps H264 BluRay encode over a 3 Mbps H265 WEBRip every time.

## Why The Mediocre Tier Is The Trap

Most "1080p" content in circulation is `WEB-DL` from mid-tier platforms, sitting in the 3-5 Mbps band. These files:

- Look fine at viewing distance on a TV (the platform's encoder is competent).
- Have visible artifacts under a slider comparison at desk-distance (mild banding, edge ringing, mosquito noise around motion).
- Cap VMAF around 78-82 when re-encoded, because AV1 either preserves the artifacts (low subjective gain) or smooths them (low VMAF score).

**Operator implication**: a VMAF auto-replace threshold of 80 will reject most re-encodes of mediocre-tier sources. This is not a bug in the encoder. It is the metric correctly reporting that the new encode is not a "perfect match" of a flawed reference. Subjectively the encode is often fine.

The fix is per-tier thresholds, not a flat global threshold (see Recommended Use below).

## Why VMAF Penalizes Cleanup

VMAF compares two pictures. When AV1 smooths H264 compression banding, VMAF reads that as "the encode is missing structure that was in the reference" and docks points. The missing "structure" was ugly artifacts. The encode is subjectively cleaner; the metric records it as worse.

This is the core source-vs-encoder-quality interaction. The way out is either:

1. Source-aware thresholds (this doc's main recommendation), or
2. A two-stage process: pre-filter the source to denoise before encoding so the reference is itself cleaner. Adds CPU cost and another tuning dimension; not currently used by MediaVortex.

## How Source Tier Affects Encoder Settings

The same SVT-AV1 recipe behaves differently per tier:

| Tier | Suggested CRF (SVT-AV1 preset 4, FG 0) | Why |
|---|---|---|
| Master | 28-32 | Source can absorb aggressive compression with minimal subjective loss. |
| Excellent | 25-30 | Mild headroom; CRF 28 is a safe default. |
| Good | 23-28 | Avoid pushing CRF above 28 — visible quality loss on streaming-tier source. |
| Mediocre | 22-26 | Less aggressive CRF; the source is the bottleneck, not the encoder budget. |
| Avoid | (do not re-encode) | The source quality cap is below replacement threshold. Re-encoding amplifies artifacts. |

Film-grain synthesis (`film-grain=0..50`) is orthogonal to tier — set by content type (live action with grain: 4-8; animation/CGI: 0; sports/clean digital: 0-2).

## Cascade Compression Caveat

Re-encoding a file twice (AV1 → AV1) compounds the problem regardless of tier. Treat any file already tagged `MediaVortex` in metadata as ineligible for re-encoding without an explicit override. The `TranscodedByMediaVortex` flag on `MediaFiles` exists for this guard.

## Recommended Use In MediaVortex

The following are NOT YET IMPLEMENTED. This doc is the design reference for them.

### Capture at scan time

Extend `MediaFiles` with:

| Column | Source | Computed |
|---|---|---|
| `SourceBitsPerPixel` | FFprobe (`format.bit_rate`, `streams[0].width/height/avg_frame_rate`) | At probe time. |
| `SourceReleaseTier` | Filename regex against the tag patterns in the tier table | At scan time; recompute on rename. |

Migration is additive (`ADD COLUMN IF NOT EXISTS`, nullable). Backfill from existing rows is a one-pass UPDATE over MediaFiles joined to TranscodeAttempts where we already have bitrate.

### Tier inputs to transcode decisions

`ProfileThresholds` (or a new per-tier overlay table) gains per-tier rows so threshold lookups are keyed by `(profile, resolution_category, source_tier)` instead of `(profile, resolution_category)` alone. Specifically:

- `VmafAutoReplaceMinThreshold` becomes tier-aware: Master 88, Excellent 85, Good 82, Mediocre 78, Avoid (filtered out before queue).
- `CRF` becomes tier-aware per the CRF table above.

### Surface in the UI

The TranscodeQueue and Activity views display the source tier badge next to each row. The VMAF compare slider (`/VmafCompare`) shows tier inline so the operator interprets scores in context.

The single user-facing number remains the threshold for the file being viewed. The complexity (per-tier table) stays in the data; the UI shows one number with one sentence of context.

## Known Failure Modes Of This Classification

- **Filename lying about tier.** Some `BluRay`-tagged rips are actually re-encodes of WEB-DL. Mitigation: bpp dominates the classification when bpp and tag disagree by more than one tier.
- **HDR-tonemap WEBRips.** SDR-tonemap of an HDR master can produce a 1080p file with master-tier bpp but mediocre-tier subjective quality (banding from tonemap). Mitigation: future column for HDR-derived flag; for now, accept the rare misclassification.
- **Re-muxed re-encodes.** A `REMUX` of a re-encoded source is a re-encode, not a remux. Mitigation: bpp catches this — true REMUX runs 25+ Mbps; re-encoded-and-remuxed runs the underlying encode's bitrate.
- **Anime tag conventions diverge.** Anime `WEB` releases from CR/Funimation often run 4-8 Mbps but with content (large flat regions) that compresses efficiently and produces clean re-encode VMAF. Mitigation: anime is best handled by a content-type override that supersedes the tier-derived threshold.

## Where This Lives

This doc is the source of truth for source-quality classification. Code references this classification via filename-regex constants and the bpp computation above; both live near `Features/MediaProbe/` once implemented. The doc updates when tiers are added or threshold ranges shift after empirical data accumulates.

## Related

- `docs/FFMPEGAndVMAFDetails.md` — VMAF measurement details and model versions.
- `docs/AudioStrategy.md` — audio policy (separate from source-tier classification).
- `transcode.flow.md` — where source-tier inputs feed into the queue-population stage.
