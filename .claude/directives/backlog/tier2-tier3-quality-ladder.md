# Tier 2 / Tier 3 quality ladder test

Written 2026-10-14 at operator request. Measurement only: nothing in production changes until the operator picks new cells from the results. Backlog row 42 in `_bucket-rules-phase-2.md`.

## Questions the test answers

1. **Bitrate per cell.** For each Tier 2 and Tier 3 cell, the lowest bitrate that still meets that tier's quality bar.
2. **Output resolution for 1080p sources.** At the same bitrate, does a 1080p encode or a 720p encode look better on a 1080p-or-larger screen? Today Tier 1 drops 1080p to 720p and Tiers 2-3 keep 1080p. The answer decides each tier's output resolution (`TranscodeDownTo`), not whether we need more tiers.
3. **Content class.** Whether animation needs different cells from live action (today they are identical).

On "Tier 2 1080p / Tier 2 720p": no new tiers. Each tier already has one cell per source resolution plus an output resolution. The test fills in those cells with measured numbers. A split only becomes a question if one bitrate cannot serve a whole tier (for example dark grainy films need far more than clean digital ones); the per-clip results show that.

## What today's cells are

| Tier | 480p | 720p | 1080p | 2160p |
|---|---|---|---|---|
| 2 | 525 | 1,250 | 2,200 (stays 1080p) | 5,500 (stays 2160p) |
| 3 | 650 | 1,700 | 3,000 (stays 1080p) | 8,000 (stays 2160p) |

Files not yet encoded that these cells will decide (2026-10-14): Movies Tier 2: 225 at 720p, 52 at 1080p, 35 at 480p. Movies Tier 3: 584 at 720p, 69 at 1080p, 49 at 480p. XXX: 198 at 2160p (Tier 2), 190 at 1080p (Tier 3). 720p sources are the majority, so the 720p cells matter most.

## Test set

Eight 2-minute clips, cut by stream copy from original (not MediaVortex) sources, each from a different film:

| # | Content | Why |
|---|---|---|
| 1 | Fast action, digital (e.g. Spider-Man Brand New Day 1080p) | motion stresses bitrate |
| 2 | Effects-heavy: explosions, water, particles | hardest content for AV1 |
| 3 | Dark / low-light scene | banding and crushed blacks |
| 4 | Grainy film-era Blu-ray | grain is where low bitrate goes waxy (seen in the Tier 1 test) |
| 5 | Dialogue, clean digital (comedy or drama) | easy content; shows how low a cell could go |
| 6 | Animation | content-class question |
| 7 | 720p source, action | the 720p cell |
| 8 | 720p source, dialogue | the 720p cell |

Plus one 2160p clip and one 480p clip if the 2160p / 480p cells are in scope for the run.

## Encode grid

Encoder: NVENC on I9 with the production command, changing only bitrate (`-b:v`, `-maxrate:v` = 2x, `-bufsize:v` = 2x) and scale. Intel is excluded until BUG-0108 is fixed.

| Source | Output | Bitrates (kbps) |
|---|---|---|
| 1080p | 1080p | 1,200 / 1,500 / 1,800 / 2,200 / 2,600 / 3,000 / 3,600 |
| 1080p | 720p | 800 / 1,000 / 1,250 / 1,500 / 1,800 |
| 720p | 720p | 600 / 800 / 1,000 / 1,250 / 1,700 / 2,200 |
| 2160p (optional) | 2160p | 4,000 / 5,500 / 8,000 |
| 480p (optional) | 480p | 400 / 525 / 650 / 900 |

About 150 encodes of 2 minutes each; minutes on the GPU. VMAF on I9's CPU is the long part, about 2-3 hours for all of them.

## Scoring

- VMAF model `vmaf_v0.6.1`, every frame, same alignment steps as production (`VmafFilterChainBuilder`: setpts, fps, range, format).
- **Screen view (primary):** every output scaled to 1920x1080 with lanczos and compared with the source scaled to 1920x1080. This puts 1080p and 720p outputs on the same footing and counts what a downscale loses, which production VMAF does not (it scores at the encoded resolution).
- **Encoded view (secondary):** both scaled to the output resolution, as production scores. Recorded so the results map onto quality-gate numbers.
- Per encode: mean, worst 1% of frames, worst 5%, frames under 80, MB per minute.

## Quality bar (proposed; operator sets the final numbers)

Measured in screen view, and met by the worst clip, not the average of clips:

| Tier | Mean | Worst 1% of frames |
|---|---|---|
| 3 "Better" | >= 95 | >= 90 |
| 2 "Good" | >= 93 | >= 85 |

Reference point: Tier 1 on Spider-Man scored 92.9 mean / 78.1 worst 1% in screen view (2026-10-14).

## Decision rule

1. Per tier and source resolution, pick the (output resolution, bitrate) with the lowest bitrate that meets the bar on every clip. Round up to the next 100 kbps.
2. If one clip type alone forces a cell far above the others (more than 30%), report it; that is the case where a content split could be worth discussing.
3. Operator eye check before adopting: the chosen setting and the next lower one, on the two worst clips, side by side, plus stills of the lowest-scoring frames.

## Before applying new cells

- A lower cell lowers that tier's ceiling (cell x multiplier), so some files move into Transcode. Project bucket moves for TV, Movies and XXX first.
- Ladder edits leave no audit trail and do not re-evaluate files today (backlog row 8, `tier-ladder-truth`); apply through `/settings` and re-evaluate the affected libraries.
- Already-encoded files are not re-encoded (D7).

## Deliverable

One table per tier: chosen cell, today's cell, scores (both views), size change per hour of video, and projected bucket moves. Raw logs and clips kept under `C:\MediaVortex\tier_ladder_test\`.
