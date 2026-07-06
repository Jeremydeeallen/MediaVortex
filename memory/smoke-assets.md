# Smoke Assets

Registry of local read-only source files used as smoke-test canaries. Not managed by MediaVortex scans. Not on network shares. Copy to a StorageRoot when needed for a live smoke; refresh from here if the pipeline destroys the disk copy.

## Assets

| Asset | Local read-only path | Container | Duration | Video | Audio | Subs | Purpose |
|---|---|---|---|---|---|---|---|
| Hotel Chevalier (2007) Bluray-1080p | `C:\Users\jerem\Videos\Hotel Chevalier (2007) Bluray-1080p.mkv` | mkv | ~13 min | h264 1080p ~11 Mbps | ac3 5.1 English | subrip English | Reencode + VMAF + Replace + subtitle-preservation smoke. Live-action Bluray with SRT subs. |

## C18 VMAF alignment smoke canaries (Reset 19)

10 shape-diverse sources, each exercising at least one of the 13 VMAF alignment axes. Registered spec; actual source path TBD per canary. Live-run records `attempt id + VMAF + axis-fired assertion` in directive `### Verification` under C18 evidence.

| Smoke | Shape | Axis exercised | Expected fail-loud? | Source |
|---|---|---|---|---|
| (a) | SDR 1080p CFR 24fps live-action | baseline (color triad + fps + no VFR + progressive + 4:2:0 + 8-bit) | no | Hotel Chevalier 1080p master (registered above) |
| (b) | HDR 4K PQ | color triad + 4K model + 10/12-bit + tone-map ref | no | TBD -- need 4K PQ HDR sample |
| (c) | Animation 24p VFR | VFR detect + CFR normalize + motion-zero filter | no | TBD -- anime master with mixed frame timings |
| (d) | Interlaced 1080i broadcast | deinterlace (`yadif=1`) | no | TBD -- broadcast capture with `field_order=tt` or `bb` |
| (e) | Telecined 24p -> 30i film | detelecine (`fieldmatch,decimate`) | no | TBD -- 29.97 fps r + 23.976 avg fps ratio |
| (f) | Letterbox 2.35:1 in 16:9 container | crop detect + normalize | no | TBD -- 1920x1080 with 2.35 letterbox bars |
| (g) | Phone-source 540p vertical | phone model (MaxEdgePx <= 540) | no | TBD -- 540x960 phone capture |
| (h) | Truncated encode (30s missing) | duration parity assert | YES (raise) | Any source + hand-truncated output via `ffmpeg -t <shorter>` |
| (i) | 4:2:2 source encoded to 4:2:0 | chroma pin + no false artifact | no | TBD -- ProRes/DNxHR 4:2:2 master |
| (j) | Unparseable color primaries source | color triad fail-loud | YES (raise) | TBD -- ffprobe returns garbage `color_primaries` |

**Provisioning notes:**
- Truncated (h) can be generated on-demand: `ffmpeg -i <encoded> -t <shorter-than-source> -c copy <encoded_truncated>`.
- Unparseable (j) can be simulated by mocking `MediaProbeAdapter.ProbeStreams` return in a targeted contract test if no real source exists (fail-loud contract already covered by `TestVmafAlignmentProbe` unit).
- HDR 4K (b) + phone (g) + 4:2:2 (i) require operator to identify source files.

## Rules

- **Read-only.** Files have Windows read-only attribute set. Do not clear it.
- **Do not scan.** Directory is not a MediaVortex StorageRoot.
- **Refresh workflow.** Smokes always enqueue against the network StorageRoot copy (`M:\Hotel Chevalier (2007)\...`), NOT the read-only master. Before smoke: if network copy is missing or damaged, copy the master from `C:\Users\jerem\Videos\` to `M:\Hotel Chevalier (2007)\`, refresh MediaFiles row (rescan MFID 620351 OR manual UPDATE of StorageRootId + RelativePath + Codec + Container + SizeMB), then enqueue against MFID 620351. Pipeline mutates the network copy; master stays intact for the next refresh.
- **Add assets by appending to the table.** Each row names the read-only path + shape + smoke purpose.
