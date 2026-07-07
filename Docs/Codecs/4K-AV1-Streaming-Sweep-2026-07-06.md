# 4K AV1 Streaming Bitrate Sweep

Date: 2026-07-06
Purpose: Find low-end 4K AV1 streaming bitrate sweet spot on real production content.

## Source

- Path: `X:\Videos\_uncategorized\C1BrazzersExxtra.26.07.04.Jewelz.Blu.This.Ass.Your.Phone.You.Choose.XXX.2160p.MP4-WRB.mp4`
- Codec: h264 3840x2160 @ 23.976 fps, yuv420p, bt709 SDR 8-bit
- Bitrate: 27357 kbps
- Duration: 31:42 (1902.11s)
- Size: 6504 MB
- Audio: AAC 109 kbps stereo (copied through untouched on all encodes)

## Sweep matrix (9 encodes)

| # | Encoder | Setting | Kbps actual | Size MB | Shrink vs src | VMAF (vmaf_4k_v0.6.1) | Encode wall | VMAF wall |
|---|---|---|---|---|---|---|---|---|
| 1 | av1_qsv | q38 ICQ | 928 | 221 | 97% | 81.56 | 26:50 | 1:34:21 |
| 2 | av1_qsv | q36 ICQ | 1163 | 277 | 96% | 85.38 | 20:21 | 1:34:18 |
| 3 | av1_qsv | q34 ICQ | 1438 | 342 | 95% | 88.44 | 17:37 | 1:51:54 |
| 4 | av1_nvenc | -b:v 1500k VBR (maxrate 3000k) | 1917 | 456 | 93% | 91.84 | 12:36 | 1:03:55 |
| 5 | av1_qsv | q30 ICQ | 2380 | 566 | 91% | 93.35 | 17:38 | 1:52:00 |
| 6 | av1_nvenc | -b:v 2250k VBR (maxrate 4500k) | 2698 | 641 | 90% | 94.67 | 8:32 | 38:09 |
| 7 | av1_nvenc | -b:v 3000k VBR (maxrate 6000k) | 3444 | 819 | 88% | 96.08 | 8:33 | 40:33 |
| 8 | av1_nvenc | -b:v 6000k VBR (maxrate 12000k) | 6481 | 1541 | 77% | 98.35 | 8:35 | 1:03:40 |
| 9 | av1_nvenc | -b:v 10000k VBR (maxrate 20000k) | 10505 | 2499 | 62% | 99.31 | 12:32 | 1:02:13 |

## Common encode flags

- All av1_nvenc: `-preset p6 -rc vbr -pix_fmt p010le -c:a copy -movflags +faststart`
- All av1_qsv: `-preset 1 -global_quality:v <Q> -pix_fmt p010le -c:a copy -movflags +faststart`
- All VMAF: composer chain `[0:v]setpts=PTS-STARTPTS,fps=23.976,scale=in_range=auto:out_range=tv,scale=3840:2160:flags=lanczos,format=yuv420p10le[dist];[1:v]<same>[ref];[dist][ref]libvmaf=model=version=vmaf_4k_v0.6.1:log_fmt=xml:n_threads=4-8`
- Model auto-selected `vmaf_4k_v0.6.1` because MaxEdgePx=3840 (>= 1440 threshold)

## Cross-encoder finding

**NVENC AV1 p6 beats QSV AV1 p1 by ~1-4 VMAF at similar bitrate on this content shape.**

| Bitrate band | NVENC | QSV | Delta |
|---|---|---|---|
| ~1500 kbps | 91.84 (1917 kbps) | 88.44 (1438 kbps) | NVENC +3.4 (with 33% more kbps) |
| ~2400 kbps | 94.67 (2698 kbps) | 93.35 (2380 kbps) | NVENC +1.3 (with 13% more kbps) |

QSV curve steeper (65% bitrate delta -> +5 VMAF) than NVENC (50% bitrate delta -> +3 VMAF).

## VMAF percentile distribution per NVENC point

Full distribution from per-frame `integer_motion` + `vmaf` XML values. All 45603 frames.

| Point | Mean | P1 | P5 | P25 | Min | StdDev | Frames <80 |
|---|---|---|---|---|---|---|---|
| 1500 | 91.84 | 83.26 | 85.75 | 89.91 | 74.96 | 3.29 | 47 (0.1%) |
| 3000 | 96.08 | 91.03 | 92.41 | 94.80 | 83.71 | 2.04 | 0 |
| 6000 | 98.35 | 94.66 | 95.78 | 97.53 | 84.79 | 1.37 | 0 |
| 10000 | 99.31 | 96.43 | 97.43 | 98.88 | 88.04 | 0.91 | 0 |

Motion=0 fraction 0.8% across all points (no held-frame distortion; content is genuinely motion-rich).

## Streaming recommendation

- **Premium 4K tier: NVENC AV1 3000 kbps VBR** -- VMAF 96.08 above transparency threshold (93), 88% shrink from source, 3-Mbps stream matches free-tier industry norm at h265 5-6 Mbps quality-equivalent.
- **Standard 4K tier: NVENC AV1 2250 kbps VBR** -- VMAF 94.67, 90% shrink, streaming-friendly bitrate for mid-tier bandwidth.
- **Aggressive / mobile: NVENC AV1 1500 kbps VBR** -- VMAF 91.84, 93% shrink, watchable-with-mild-softness. Below industry 4K floor but AV1 delivers.
- **Skip above 6000 kbps for streaming.** Diminishing returns (6000 -> 10000 costs 65% more bitrate for +0.96 VMAF).
- **Prefer NVENC over QSV for quality-critical 4K.** QSV useful for high-throughput batch on wakko when quality budget is looser.

## Industry cross-reference (adult streaming 4K)

- Pornhub Premium: 6-12 Mbps h265
- Pornhub free 4K (rare): 3-6 Mbps h264
- OnlyFans upload cap: h264 15 Mbps
- ManyVids "Ultra HD": 6-10 Mbps h264/h265
- Xvideos / Redtube: cap at 1080p

AV1 3000 kbps ~= h265 5000-5500 kbps quality-equivalent (approx `av1_kbps * 1.8`).

## Encoder wall-time summary

- NVENC 4K solo encode: 8:30-12:30 wall on i9 (average 10 min). Bitrate-independent within 3.6x-realtime band. Lower target bitrates take slightly longer due to more rate-target work.
- QSV 4K encode on wakko Arc B580: 17:30-26:50 (average 21 min). Higher `q` = slower (more per-frame decisions).
- Solo VMAF on i9 (n_threads=8): ~40 min.
- 3-parallel VMAF on i9: ~1 hour each (memory-bandwidth-bound).
- 2-parallel VMAF on wakko (n_threads=4 each): ~1:34 each.
- Full 9-point sweep wall: ~4:30 with parallelism vs ~14 hours pure sequential.

## Artifacts

Preserved for inspection:
- `C:\4K-Probe\jewelz_nvenc_{1500,2250,3000,6000,10000}k.mp4` -- encoded outputs
- `C:\4K-Probe\jewelz_qsv_q{30,34,36,38}.mp4` -- encoded outputs (copied back from wakko)
- `C:\4K-Probe\vmaf_{1500,2250,3000,6000,10000}k.xml` -- per-frame VMAF + motion XML
- `C:\4K-Probe\vmaf_q{30,34,36,38}.xml` -- per-frame VMAF + motion XML
- `C:\4K-Probe\jewelz_nvenc_*.log` + `vmaf_*_stderr.log` -- ffmpeg stderr traces
- Wakko `/tmp/4k-probe/` mirror (delete after review)

## Caveats

- Single content shape (live-action, low-motion, high-fidelity master). Anime / high-motion sports / HDR / animation likely score differently.
- VMAF 4K model trained on broadcast; can over-rate soft skin-tone content vs sharp broadcast. Eye-test on hardest scene before committing 1500 kbps to production.
- Run the 4K sweep on 1-2 additional content shapes before promoting these thresholds to CANARY tier ladder.
