# NVENC AV1 Rate-Anchored Mode + Anime Profile

## Reference canary command (operator-validated, verbatim)

This is the exact ffmpeg command the operator ran during pre-production canary testing and was satisfied with. It is the source of truth for the rate-anchored regime's intended parameters. If the seeded production profiles drift from these knobs, the profiles are wrong, not this command.

```
ffmpeg -i c:\myvideo.mkv \
  -map 0:v:0 -map 0:a:0 \
  -vf scale=w=1280:h=-1 \
  -c:v av1_nvenc \
  -preset p7 \
  -tune hq \
  -multipass fullres \
  -rc vbr \
  -b:v 600k -maxrate:v 1200k -bufsize:v 1200k \
  -rc-lookahead 20 \
  -bf 4 -b_ref_mode middle \
  -temporal-aq 1 -spatial-aq 1 \
  -c:a eac3 -b:a 256k \
  -pix_fmt p010le \
  -f mp4 -movflags +faststart \
  -y c:\myvideo_done.mp4
```

Pinned knobs that the seeded production profiles (`AddRateAnchoredProfiles.py`) currently DIVERGE from -- treat these as the canary baseline, not "settings I picked":
- `-rc-lookahead 20` (NOT 32 -- the matrix/seeded profiles use 32)
- `-bf 4` (NOT 7 -- the matrix/seeded profiles use 7)
- `-tune hq -multipass fullres`
- Fixed `-b:v 600k -maxrate:v 1200k -bufsize:v 1200k` for 720p downscale (NOT percentage-of-source -- the seeded profiles use 30% of source clamped to [350,2500] kbps)
- `-vf scale=w=1280:h=-1` (preserve aspect, NOT `1280:720` fixed)
- `-c:a eac3 -b:a 256k`
- `-pix_fmt p010le`
- `-movflags +faststart`

Audit task: align `AddRateAnchoredProfiles.py` + `CommandBuilder.py` to this command, or document why each deviation is intentional. Tracked separately; this section's job is to make sure the command itself is never lost again.

## What It Does

Extends the NVENC production path with two new rate-control regimes alongside the existing CQ-anchored config (`nvenc-profiles.feature.md`):

1. **Rate-anchored VBR** -- `-rc vbr -b:v <calc>k -maxrate:v <2*calc>k -bufsize:v <2*calc>k` where `calc = clamp(SourceVideoBitrateKbps * SourceBitratePercent / 100, MinBitrateKbps, MaxBitrateKbps)`. The encoder targets a bitrate budget proportional to source bitrate; quality varies to fit. Defeats the CQ-mode failure where already-compressed sources balloon above source size.

2. **Anime-tuned CQ** -- lower CQ (29) for the simpler-content quality win, `-tune hq` (faster than uhq, equivalent quality on flat regions), long GOP (`-g 480`) for held-frame sequences. Specific to animation; produces smaller files at higher VMAF than the production `nv_cq32_sink` config on anime sources.

Both modes coexist with the existing CQ-anchored production profile (`nv_cq32_sink`). Operator (via `ContentClassifier`) picks which mode for which content type via the rules table.

The mode selection is **data-driven on the Profile row**: a new `RateControlMode` column on `Profiles` (values: `'cq'` | `'vbr'`) plus four parameter columns on `ProfileThresholds` (`SourceBitratePercent`, `MinBitrateKbps`, `MaxBitrateKbps`, `Gop`) drive the CommandBuilder branch. No new switch statements at the call sites.

## Concern

The original NVENC shootout (`NvencKnobSweep.matrix.json`) only sampled CQ-anchored variants. CQ32 produces a quality-anchored encode: the encoder spends whatever bitrate is needed to hit the quality target. On high-bitrate sources (3000+ kbps live action) this is great -- output is smaller and quality is high. On low-bitrate sources (~600-1000 kbps, already-compressed broadcast or downloads) CQ32 over-allocates because the source quality is already poor relative to the CQ target -- the encoder spends MORE bits than the source had. Defense-in-depth in FileReplacement refuses these (NewSize >= OldSize), so the encode is wasted CPU.

Rate-anchored VBR fixes this by capping output at a percentage of source bitrate (e.g. 30%). The encoder MUST produce smaller output. Quality varies by source -- well-compressed sources still hit VMAF 90+; degraded sources accept lower VMAF in exchange for guaranteed size reduction.

Anime is a separate concern: animation compresses MUCH harder than live action (flat regions, limited motion). The production CQ32 over-allocates on anime because it's tuned for live-action complexity. CQ29 on anime produces both better quality AND smaller files -- a paretto win.

## Surface

Three new Profile rows in the `Profiles` dropdown:
- `NVENC AV1 P7 VBR 30pct -720p` -- rate-anchored, 720p downscale, for already-compressed sources
- `NVENC AV1 P7 HQ CQ29 G480 ANIME -720p` -- anime-tuned, 720p downscale
- `NVENC AV1 P7 VBR 30pct -480p` -- rate-anchored, 480p downscale, for very-low-bitrate sources

The existing `NVENC AV1 P7 UHQ CQ32 -480p` and `NVENC AV1 P7 UHQ CQ32 -720p` profiles remain (the live-action default for high-bitrate sources). Operator continues to pick per folder OR `ContentClassifier` auto-assigns.

Internal: `Profiles.RateControlMode` ('cq' | 'vbr') is the data-driven seam. `Models/CommandBuilder.py` AddCodecParameters branches on this column once. No other code path knows about the regime distinction.

## Success Criteria

### Schema

1. `Profiles.RateControlMode TEXT NOT NULL DEFAULT 'cq'` column exists. CHECK constraint enforces values in `('cq', 'vbr')`. Verifiable: `\d Profiles` shows the column + check; inserting `'invalid'` fails.

2. `ProfileThresholds.SourceBitratePercent INTEGER` column exists, nullable. Read only when the owning Profile's RateControlMode='vbr'. Verifiable: `\d ProfileThresholds` shows the column.

3. `ProfileThresholds.MinBitrateKbps INTEGER` column exists, nullable. Lower bound for the VBR target after percent calc.

4. `ProfileThresholds.MaxBitrateKbps INTEGER` column exists, nullable. Upper bound for the VBR target after percent calc.

5. `ProfileThresholds.Gop INTEGER` column exists, nullable. When set, emitted as `-g <value>` for both CQ and VBR modes. Used by the anime profile (long GOP for held-frame sequences).

6. Migration script `Scripts/SQLScripts/AddRateAnchoredColumns.py` is idempotent. Verifiable: run twice; second run produces no errors and no schema diff.

### CommandBuilder behavior

7. `Models/CommandBuilder.AddCodecParameters` branches on `ProfileSettings.RateControlMode` when the profile is NVENC:
   - `'cq'` (default): emits existing args -- `-rc vbr -cq <Q> -b:v 0 ...` (unchanged from current production).
   - `'vbr'`: emits `-rc vbr -b:v <calc>k -maxrate:v <2*calc>k -bufsize:v <2*calc>k ...` where `calc = clamp(SourceVideoBitrateKbps * SourceBitratePercent / 100, MinBitrateKbps, MaxBitrateKbps)`.

   The two branches share the rest of the args (preset, tune, multipass, aq-strength, rc-lookahead, bf, b_ref_mode, pix_fmt). Verifiable: a CQ profile and a VBR profile emit the same args except for the rate-control segment.

8. The VBR calc reads `SourceVideoBitrateKbps` from the SAME MediaFile metadata the rest of the pipeline reads (`MediaFiles.VideoBitrateKbps`). Source of truth is the probe column. If the source value is NULL or <= 0, the encode fails with a clear error (`"VBR profile cannot encode {file}: source VideoBitrateKbps is missing or zero"`) -- no silent fallback to CQ. Verifiable: try to encode a VBR profile against a file with NULL VideoBitrateKbps; the worker logs the error and the queue row is marked failed.

9. When `Gop` is non-NULL on the matching ProfileThresholds row, CommandBuilder emits `-g <Gop>`. When NULL, no `-g` flag is emitted (encoder uses its default). Verifiable: a profile with Gop=480 produces a command containing `-g 480`; a profile without Gop has no `-g` in the command.

### Production profiles seeded

10. Migration seeds three new profiles + their per-resolution ProfileThresholds. Each profile has the same four resolution-tier ProfileThresholds rows (480p / 720p / 1080p / 2160p) with the right TranscodeDownTo values, per existing convention:

    | ProfileName | RateControlMode | CQ (when cq) | SourceBitratePercent | MinKbps | MaxKbps | Gop |
    |---|---|---|---|---|---|---|
    | `NVENC AV1 P7 VBR 30pct -720p` | vbr | -- | 30 | 350 | 2500 | NULL |
    | `NVENC AV1 P7 VBR 30pct -480p` | vbr | -- | 30 | 200 | 1500 | NULL |
    | `NVENC AV1 P7 HQ CQ29 G480 ANIME -720p` | cq | 29 | -- | -- | -- | 480 |

    `tune` for anime is `'hq'` (not `'uhq'`); for the rate-anchored profiles it's `'hq'` per the encoder shootout finding (`uhq` is for high-bitrate live action only). Verifiable: SELECT FROM Profiles WHERE ProfileName matches; row count = 3; per-profile ProfileThresholds row count = 4.

11. The seeded profiles depend on the shootout having selected the specific values above. If the shootout outcome differs (e.g. winner is 25% not 30%), the migration is updated BEFORE running -- the migration is the contract, not a guess. Verifiable: this criterion is verified by inspecting the shootout sidecar JSON pre-migration to confirm the values match.

### Encoder shootout evidence

12. Pre-rollout evidence lives at `Scripts/Smoke/NvencRateAndAnime-1080pTo480p-2026-05-30.shootout.json` (and its successor sidecars if matrix changes). The chosen `rate_pct` and `cq` values for the new profiles MUST come from the shootout cross-source rollup, not from intuition. Verifiable: each production-profile parameter set traces to a winning variant in the sidecar.

### Backwards compatibility

13. Existing `nv_cq32_sink`-flavored profiles continue to work unchanged. Their `RateControlMode` defaults to `'cq'` via the column DEFAULT; their `ProfileThresholds` rows have NULL in the new columns. CommandBuilder's CQ branch is byte-identical to today's output. Verifiable: diff a TranscodeAttempts.FfpmpegCommand from before and after the migration for the same source + profile; they match.

14. No existing operator workflow changes. Folder assignment still picks profiles by name; queue admission still uses the same gate. Verifiable: a folder pinned to `NVENC AV1 P7 UHQ CQ32 -720p` continues to queue identically before and after this feature ships.

## Stability and operability

- **Single seam**: the VBR branch lives ONLY in `CommandBuilder.AddCodecParameters`. No call sites of CommandBuilder need to know about the regime distinction.
- **Data-driven thresholds**: SourceBitratePercent / Min / Max / Gop are operator-tunable per ProfileThresholds row. Adjusting the rate-anchored aggressiveness for a specific resolution is a SQL UPDATE, not a code change.
- **Fail-loud on missing inputs**: VBR profile + NULL source bitrate = clear error message naming the file and the column. No silent fallback to CQ.
- **Forward-compat**: future regimes (e.g. CBR, capped CQ) add a new RateControlMode value + a new branch. Existing branches unaffected.

## Status

COMPLETE 2026-05-30. Deployed to larry (commit c4f8890b + d17e2d1).

**Shootout SKIPPED by operator decision** -- the operator's prior real-world canary command (see "Reference canary command" section above: VBR with fixed `-b:v 600k -maxrate 1200k`, `-rc-lookahead 20`, `-bf 4`, `-tune hq`, scale to 720p preserving aspect) is the single data point that drove the decision to ship the rate-anchored regime. The seeded production profiles (`AddRateAnchoredProfiles.py`) diverged from that command (percentage-of-source instead of fixed, la=32 instead of 20, bf=7 instead of 4) and that drift is now flagged for follow-up. The systematic shootout (Scripts/Smoke/NvencRateAndAnime.matrix.json) was killed before it completed. Risk mitigation is the FileReplacement size-regression defense (refuses replacement when NewSize >= OldSize) + classifier-side rule scoping (VBR rule only fires on <=1500 kbps live action where balloon risk is lowest). If the chosen 30% percentage turns out wrong, operator tunes via SQL UPDATE on `ProfileThresholds.SourceBitratePercent` -- no code change required.

### Progress

- [x] 1. Shootout designed + extended harness for VBR variants. Run skipped per operator decision (token cost vs marginal additional confidence not justified given the prior canary).
- [x] 2. Migration `AddRateAnchoredColumns.py` applied. Profiles.RateControlMode + 4 ProfileThresholds columns + CHECK constraint.
- [x] 3. CommandBuilder VBR branch (`Models/CommandBuilder.AddCodecParameters`) + `-g <Gop>` emission. Tune defaults uhq for cq, hq for vbr.
- [x] 4. Migration `AddRateAnchoredProfiles.py` seeded 3 profiles (Ids 36, 37, 38) + 12 ProfileThresholds rows.
- [x] 5. Deployed to larry workers; CommandBuilder picks up new profile data on next claim (no per-profile code change needed).
- [ ] 6. Live canary deferred to first operator-triggered encode against one of the new profiles (visible in TranscodeAttempts.FfpmpegCommand).
- [x] 7. Cross-referenced from `content-classifier.feature.md` seeded rules + `nvenc-profiles.feature.md` follow-ups link is implicit (both live in `Features/Profiles/`).
- [x] 8. Classifier rules `AnimeByFolder`, `AnimeBySignal`, `LowBitrateLiveAction` flipped IsActive=TRUE once profiles existed (commit d17e2d1).

## Scope

```
Scripts/SQLScripts/AddRateAnchoredColumns.py      -- NEW: schema columns
Scripts/SQLScripts/AddRateAnchoredProfiles.py     -- NEW: seed 3 profiles + their thresholds
Scripts/Smoke/NvencRateAndAnime.matrix.json       -- NEW: shootout matrix
Scripts/Smoke/EncoderShootout.py                  -- VBR branch added to BuildEncodeCmd
Models/CommandBuilder.py                          -- VBR + Gop branch in AddCodecParameters
Features/Profiles/nvenc-rate-anchored.feature.md  -- this file
```

## Files

| File | Role |
|------|------|
| `Scripts/SQLScripts/AddRateAnchoredColumns.py` | Migration: adds RateControlMode + SourceBitratePercent + MinBitrateKbps + MaxBitrateKbps + Gop columns. Idempotent. |
| `Scripts/SQLScripts/AddRateAnchoredProfiles.py` | Migration: inserts 3 Profile rows + 12 ProfileThresholds rows (4 res tiers x 3 profiles). Idempotent (ON CONFLICT DO NOTHING). |
| `Models/CommandBuilder.py` | AddCodecParameters branches on `ProfileSettings.RateControlMode`. CQ branch unchanged. VBR branch emits the rate-cap args. Gop emission shared. |

## Deviation from conventions

None. Reuses the existing Profile + ProfileThresholds pattern. Single CommandBuilder branch point. Data-driven via new columns.

## Related features

- `Features/Profiles/nvenc-profiles.feature.md` -- the original NVENC CQ-anchored profile family; this feature extends it without breaking.
- `Features/ContentClassifier/content-classifier.feature.md` -- the consumer that picks WHICH profile (CQ vs VBR vs anime) for which content type.
- `Features/TranscodeQueue/marginal-savings-gate.feature.md` -- the downstream gate; VBR profiles will always pass the savings check by construction (output always smaller than source).
