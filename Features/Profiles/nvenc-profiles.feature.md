# NVENC AV1 Production Profiles

**Slug:** nvenc-profiles

## What It Does

Two operator-selectable profiles that route transcode work to NVENC-capable workers (the I9 host's RTX 4060 Ti) and emit a tuned `av1_nvenc` command. The operator picks one from the same profile dropdown used for SVT-AV1 profiles; queued jobs are gated to NVENC-capable workers automatically by the claim query.

- `NVENC AV1 P7 UHQ CQ32 -480p` -- all sources downscaled to 480p (storage-optimized).
- `NVENC AV1 P7 UHQ CQ32 -720p` -- 1080p/2160p sources downscaled to 720p; 720p stays; 480p stays.

Both use `Profiles.usenvidiahardware=1`. The CommandBuilder NVENC branch hardcodes the rest of the shootout-winner knob set (tune=uhq, multipass=fullres, rc=vbr+cq, spatial-aq=1, temporal-aq=1, aq-strength=15, rc-lookahead=32, bf=7, b_ref_mode=middle, pix_fmt=p010le).

## Surface

- **Profile assignment**: existing folder-assignment UI (Scanning page). NVENC profiles appear in the same dropdown as SVT profiles.
- **Worker routing**: queue claim (`DatabaseManager.ClaimNextPendingTranscodeJob`) gates jobs whose assigned profile has `usenvidiahardware=1` to workers where `Workers.nvenccapable=TRUE`. Non-NVENC profiles are unaffected.
- **Replacement pipeline**: unchanged. NVENC encodes produce `-mv.mp4.inprogress` outputs and flow through the standard FileReplacement + VMAF + disposition path. Source is replaced on disposition=Replace, archived to MediaFilesArchive, MediaFiles re-probed, exactly as with SVT-AV1.
- **Audio**: unchanged. Both encoder branches share `AudioCompletionService.ShouldStreamCopyAudio` + `BuildAudioCodecArgs` + `BuildAudioFilters` (loudnorm, completion gating). NVENC profile is video-only.

## Success Criteria

1. The two new profiles exist in `Profiles` table with `codec='av1_nvenc'`, `preset=7`, `filmgrain=0`, `usenvidiahardware=1`, and 4 `ProfileThresholds` rows each (one per source resolution tier 480p/720p/1080p/2160p) with `quality=32` and the right `transcodedownto` value.
2. `Workers.nvenccapable` column exists (boolean, default FALSE). The I9-2024 worker has `nvenccapable=TRUE`. All other workers have `nvenccapable=FALSE`.
3. `DatabaseManager.ClaimNextPendingTranscodeJob` claims jobs assigned to NVENC profiles only when the calling worker has `nvenccapable=TRUE`. Non-NVENC profiles claim normally on any TranscodeEnabled worker.
4. `Models/CommandBuilder.AddCodecParameters` emits the full NVENC quality knob set when `ProfileSettings.UseNvidiaHardware=1`: `-preset p<N> -tune uhq -multipass fullres -rc vbr -b:v 0 -cq <Q> -spatial-aq 1 -temporal-aq 1 -aq-strength 15 -rc-lookahead 32 -bf 7 -b_ref_mode middle`. Preset and Quality come from the profile; the rest are fixed.
5. `Models/CommandBuilder.AddPixelFormatParameter` emits `-pix_fmt p010le` for NVENC, `-pix_fmt yuv420p10le` for software (existing behavior preserved).
6. NVENC encodes produce outputs at the existing `-mv.mp4.inprogress` path; the FileReplacement vertical replaces the source unchanged.
7. Audio handling is identical to SVT-AV1 profiles: stream-copy when AudioComplete=true, otherwise the standard loudnorm/acompressor chain.
8. Film grain is NOT emitted for NVENC (already gated in `AddFilmGrainParameter` -- NVENC doesn't support it).

## Status

COMPLETE 2026-05-29 (canary-validated on I9 end-to-end, including the input-order VMAF fix discovered during the run). See the Deployment section for the canary outcome and operator usage.

## Variant choice evidence

See `Scripts/Smoke/EncoderShootout.feature.md` for the test methodology and the cross-source rollup. The chosen config (`nv_cq32_sink` in the matrix) was the only NVENC variant that produced **smaller** files than SVT-AV1 P6 FG8 CRF26 (-14% median size) while staying within 1.0 VMAF (median -0.47), at ~1.6x faster wall encode. The full sidecar lives at `Scripts/Smoke/NvencKnobSweep-1080pTo480p-2026-05-28.shootout.json`.

If future NVENC tuning needs to vary per profile (e.g. tune=hq for fast-motion live action vs uhq for animation), the hardcoded knob set in `CommandBuilder.AddCodecParameters` becomes a Profile column. Not needed today -- one config wins across all four content types tested.

## Seams

| Seam | Producer | Wire shape | Consumer expects | Verification |
|---|---|---|---|---|
| `Profiles.usenvidiahardware` → claim gate | `Profiles.usenvidiahardware BIGINT` (1=NVENC, 0/NULL=software) | EXISTS subquery: `p.usenvidiahardware = 1` ANDed with `Workers.nvenccapable = TRUE` in `BuildClaimPredicate` | `DatabaseManager.ClaimNextPendingTranscodeJob` — NVENC jobs claimed only by workers where `Workers.nvenccapable=TRUE` | `py -m pytest Tests/Contract/TestClaimAuthority.py` |
| `Workers.nvenccapable` → claim gate | Migration `AddNvencProfiles.py` sets `nvenccapable=TRUE` for I9-2024; all others FALSE | `Workers.nvenccapable BOOLEAN DEFAULT FALSE` | `BuildClaimPredicate` SQL fragment includes `w.nvenccapable = TRUE` for NVENC profiles | `SELECT workername, nvenccapable FROM Workers ORDER BY workername` |
| `Profiles.usenvidiahardware` → CommandBuilder NVENC branch | `EncoderKnobs.UseNvidiaHardware Optional[int]` (0/1/None) read by `EncoderKnobRepository` | Python int; `CommandBuilder` checks `== 1` (not truthiness) | `CommandBuilder.AddCodecParameters` branches on `ProfileSettings['UseNvidiaHardware'] == 1` → emits `-c:v av1_nvenc` + full shootout-winner knob set | Smoke: output contains `av1_nvenc -preset p7 -tune uhq` for an NVENC profile |
| NVENC encode output → FileReplacement | Worker writes `-mv.mp4.inprogress` path (same convention as SVT) | Standard inprogress file path | FileReplacement vertical consumes path unchanged; no NVENC-specific logic | Canary 2026-05-29: FileReplacement defense-in-depth triggered correctly (NewSize >= OldSize refused) |

## Scope

```
Scripts/SQLScripts/AddNvencProfiles.py     -- migration (idempotent)
Models/CommandBuilder.py                   -- NVENC branch in AddCodecParameters + AddPixelFormatParameter
Repositories/DatabaseManager.py            -- ClaimNextPendingTranscodeJob NVENC capability gate
Features/Profiles/nvenc-profiles.feature.md -- this file
```

## Files

| File | Role |
|------|------|
| `Scripts/SQLScripts/AddNvencProfiles.py` | One-shot migration: adds Workers.nvenccapable + 2 Profiles + ProfileThresholds + sets I9-2024 capable |
| `Models/CommandBuilder.py` | NVENC command emission (shootout-winner knob set hardcoded) |
| `Repositories/DatabaseManager.py` | Queue claim gate: NVENC jobs routed to nvenccapable workers only |

## Deployment

Migration ran 2026-05-28. Code changes (CommandBuilder NVENC branch + queue claim NVENC capability filter + VMAF chain fixes) deployed and canary-validated on I9 2026-05-29.

### Canary run 2026-05-29 (Cheers S03E03)

End-to-end production pipeline verified on a real source:

| Step | Outcome |
|---|---|
| Worker capability routing | I9-2024 claimed the job; no other worker attempted it |
| CommandBuilder NVENC emission | Full knob set verified in `TranscodeAttempts.FfpmpegCommand`: `av1_nvenc -preset p7 -tune uhq -multipass fullres -rc vbr -b:v 0 -cq 32 -spatial-aq 1 -temporal-aq 1 -aq-strength 15 -rc-lookahead 32 -bf 7 -b_ref_mode middle -pix_fmt p010le` |
| Encode | 93.1 sec wall, output 150 MB |
| VMAF (new chain) | 95.70 |
| Disposition | Would-have-Replace (VMAF > 88 threshold) |
| FileReplacement defense-in-depth | Correctly refused: NewSize (150 MB) >= OldSize (124 MB). Source preserved. |

Bad-candidate content -- the Cheers source was already heavily compressed (~600 kbps), so NVENC quality-anchored CQ32 needed more bits to hit its target than the source carried. Correct behavior; the pipeline's safety gate caught it. For typical 1080p sources at production-normal bitrates, the shootout-measured ~14% size reduction holds.

### Discoveries during canary that became permanent fixes

1. **VMAF input order was swapped in production.** `BuildVMAFCommand` had `-i original -i transcoded` with the filter chain mapping `[0:v]->[dist]` and `[1:v]->[ref]`. libvmaf reads inputs positionally as (distorted, reference), so production was treating the ORIGINAL as distorted and TRANSCODED as reference -- backwards. The fix swapped inputs to `-i transcoded -i original`. Verified by re-running VMAF on the same encoded file: wrong direction gave 67.40, correct direction gave 95.70. All historical VMAF scores are inverted-direction measurements (still valid for relative comparisons but not the libvmaf-standard absolute number). Documented in `Features/QualityTesting/QualityTesting.feature.md` criterion 11c and `memory/KNOWN-ISSUES.md` BUG-0022.

2. **CodecFlags + CodecParameters rows for av1_nvenc were missing.** `ProcessTranscodeQueueService.GetTranscodingSettings` returns None if no CodecFlags row exists for the profile's codec name, OR no CodecParameters rows tied to it. Migration script extended to upsert both. Without this, the worker fails with "Failed to get transcoding settings" before reaching the CommandBuilder.

3. **Queue claim query needed `FOR UPDATE OF tq SKIP LOCKED`** (not bare `FOR UPDATE`) once LEFT JOIN to Profiles was added -- PostgreSQL forbids `FOR UPDATE` on the nullable side of an outer join. Without the scope-to-table fix, the worker errors out on every claim attempt.

### Operator usage now

1. Pick a folder on the Scanning page.
2. Assign `NVENC AV1 P7 UHQ CQ32 -480p` or `...-720p` from the dropdown.
3. Populate the queue and start WorkerService -- jobs route to I9 automatically.

### Adding more NVENC-capable workers

```sql
UPDATE Workers SET nvenccapable = TRUE WHERE workername = '<host with NVENC GPU>';
```

The worker must have an NVENC-capable NVIDIA GPU (Ada or later for AV1 NVENC) and the `av1_nvenc` encoder in its FFmpeg build. No code change required.
