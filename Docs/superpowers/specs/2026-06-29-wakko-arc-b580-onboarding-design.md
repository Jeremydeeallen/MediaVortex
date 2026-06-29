# Wakko Arc B580 Onboarding — Design

**Date:** 2026-06-29
**Slug:** wakko-arc-b580-onboarding
**Status:** Draft, awaiting directive open (blocked by active `transcode-worker-unification` IMPLEMENTING)

## Outcome

Wakko (`client-b450m-01`, Ryzen 7 3700X 8C/16T, Arc B580 Battlemage, Ubuntu 24.04, 4 docker workers) becomes a productive AV1 QSV encoder for -720p output. Two new production profiles ship:

- **`QSV AV1 CANARY VBR -720p`** — filesize parity ±5% with `NVENC AV1 P7 CANARY VBR -720p`, VMAF Mean ≥ NVENC +2.0
- **`QSV AV1 CANARY VBR -720p HQ`** — filesize parity ±5% with `NVENC AV1 P6 CANARY VBR -720p HQ`, VMAF Mean ≥ NVENC parity-or-better

NVENC paths on I9 untouched. Workers can hold both `nvenccapable` and `qsvcapable` independently (capabilities stack); a single profile picks one encoder via `codec` field and the per-profile flags `usenvidiahardware` / `useintelhardware` (mutually exclusive via CHECK constraint).

## Pre-Audit (Host state captured 2026-06-29)

Verified on `ssh root@wakko`:

- Kernel 6.14.0-37-generic, Linux Mint 22.3 Zena (Ubuntu 24.04 base)
- GPU `[8086:e20b]` = Intel Battlemage (Arc B580)
- `/dev/dri/{card1,renderD128}` present on host (render group GID 992, video group GID 44)
- Host ffmpeg 6.1.1-3ubuntu5 (Ubuntu stock, too old for Battlemage QSV) — replaced/supplemented with modern build during onboarding
- VA-API 1.23 + iHD driver 26.2.2; `VAProfileAV1Profile0 : VAEntrypointEncSlice` confirmed
- 4 containers (`mediavortex-worker-N-1`) running, image `mediavortex-worker:latest`
- Container ffmpeg (build `N-124437-gd01d18ad71-20260512`, BtbN-style static, `--enable-libvpl --enable-libvmaf --enable-vaapi`) has `av1_qsv` encoder

## Infrastructure setup performed on wakko (2026-06-29)

Captured here so the future directive can re-execute or audit. All actions ran via `ssh root@wakko`.

### 1. Docker compose patch (`/opt/mediavortex/docker-compose.yml`)

Added GPU passthrough to the shared `x-worker` anchor:

```yaml
x-worker: &worker-base
  image: mediavortex-worker:latest
  restart: unless-stopped
  stop_grace_period: 30m
  devices:
    - /dev/dri:/dev/dri          # NEW: Arc B580 device passthrough
  group_add:
    - 992                         # NEW: render group (matches host /dev/dri/renderD128 GID)
    - 44                          # NEW: video group (matches host /dev/dri/card1 GID)
  # ... rest unchanged
```

Backup preserved at `/opt/mediavortex/docker-compose.yml.bak.20260629`. Containers recreated with `docker compose down && docker compose up -d`. `docker exec mediavortex-worker-1-1 ls /dev/dri/` confirms renderD128 visible to container user (uid 0, groups 44+992).

### 2. Host package: `libmfx-gen1.2` (Intel oneVPL GPU Runtime)

**The missing piece.** Without this, `vpl-inspect` reports only legacy Intel Media SDK 1.35 (libmfxhw64) which lists `mfxEncoderDescription Version: 0.0` — i.e. no encoders exposed. With it, `vpl-inspect` reports a second implementation `mfx-gen` ApiVersion 2.16, DeviceID `e20b/0` (Arc B580), `MediaAdapterType: MFX_MEDIA_DISCRETE`. This is the modern oneVPL 2.x backend required for Battlemage AV1.

Install:
```bash
ssh root@wakko apt install -y libmfx-gen1.2
```

Pre-installed prerequisites confirmed present (from Intel `kobuk-team/intel-graphics` PPA, which Linux Mint pulls via the Ubuntu noble PPA repo):
- `intel-media-va-driver-non-free` 26.2.2 (iHD VA-API driver)
- `libva2`, `libva-drm2`, `libva-x11-2` 2.23.0
- `libvpl2` 2.16.0 (oneVPL dispatcher)
- `libmfx1` 22.5.4 (legacy MSDK 1.x — kept for backward compat, ignored by oneVPL 2.x path)
- `onevpl-tools` (provides `vpl-inspect` diagnostic)

Apt repo source on wakko host:
```
deb [signed-by=/etc/apt/keyrings/kobuk-team-intel-graphics-noble.gpg] \
  https://ppa.launchpadcontent.net/kobuk-team/intel-graphics/ubuntu noble main
```

### 3. Modern ffmpeg on host: `/usr/local/bin/ffmpeg-modern`

Ubuntu stock `/usr/bin/ffmpeg` 6.1.1 (2023-era) is **too old** to negotiate with libmfx-gen 26.2.2 — its av1_qsv path returns `Failed to create a VAAPI device` / `Generic error in an external library` even after libmfx-gen is installed.

Workaround: copied the container's BtbN-style static ffmpeg out of the worker image:
```bash
docker cp mediavortex-worker-1-1:/usr/local/bin/ffmpeg /usr/local/bin/ffmpeg-modern
chmod +x /usr/local/bin/ffmpeg-modern
```

This binary is `ffmpeg N-124437-gd01d18ad71-20260512`, built 2026-05-12 with libvpl + libvmaf + vaapi enabled. Works with operator's full QSV knob set (preset veryslow, rc icq, look_ahead, adaptive_i/_b, bf, async_depth).

The CONTAINER ffmpeg cannot be used directly for QSV encoding because the container is Debian 13 trixie base and lacks `libmfx-gen1.2` (Intel kobuk PPA targets Ubuntu noble, not Debian trixie). All QSV transcodes must run **from the host** until the worker image is rebuilt with the proper Intel media stack on a Debian-compatible PPA OR rebased on Ubuntu noble.

### 4. Database flips (`Workers` table)

```sql
UPDATE Workers SET qualitytestenabled = TRUE
  WHERE workername LIKE 'wakko-worker-%';
```

All 4 wakko workers (-1..-4) now eligible to run VMAF measurements.

`transcodeenabled` still FALSE pending claim-predicate wiring (`Workers.qsvcapable` + `BuildQsvPredicate` not yet implemented in this directive's Phase D).

### 5. VMAF chain fix (codified for shootout harness)

The standard `setpts=PTS-STARTPTS` + `format=yuv420p10le` chain does **not** correctly align frames between mkv source (1/24000 timebase) and mp4 encoded (1/1000 timebase). Result: VMAF scores ping-pong between high (~95) and low (~0) on alternating frames, dragging Mean and HMean ~30 points below truth.

Fix: prepend `fps=24000/1001` to both `[ref]` and `[enc]` chains. Example working filter:
```
[0:v]fps=24000/1001,setpts=PTS-STARTPTS,scale=1280:720:flags=lanczos,format=yuv420p10le[ref];
[1:v]fps=24000/1001,setpts=PTS-STARTPTS,scale=1280:720:flags=lanczos,format=yuv420p10le[enc];
[enc][ref]libvmaf=n_threads=4:log_fmt=json:log_path=/tmp/vmaf.json
```

`EncoderShootout.py` extension for QSV variants must apply this fps-lock. Existing NVENC/SVT shootouts may have been masked from this bug because Windows ffmpeg defaults differently OR existing matrix JSONs already lock fps.

Identity sanity (clean_src vs clean_src) confirmed VMAF=98.78 with fps-lock; x264 CRF18 (near-lossless ref) confirmed VMAF=95.01. Pipeline now trustworthy.

## QSV smoke results (NewGirl S06E03, 30s clean clip, fps-locked VMAF)

| Variant | Bitrate | Size (bytes) | VMAF Mean | HMean | Min | Speed |
|---|---|---|---|---|---|---|
| x264 CRF18 (near-lossless ref) | 1700k | 7,283,808 | 95.01 | 95.00 | 92.60 | n/a |
| **QSV VBR 390k canary envelope** | 368k | 1,570,642 | **88.22** | 88.12 | 73.26 | 4.1x |
| **QSV ICQ q=23** | 661k | 2,821,756 | **92.41** | 92.39 | 86.94 | 11.1x |
| NVENC AV1 P7 -720p (production avg, 45 attempts) | ~390k | similar | 90.48 | 87.14 | n/a | ~1x |

**Profile 1 (size match to NVENC P7 -720p) gap: -2.26 VMAF.** Closeable by tuning ICQ q + bitrate cap. Pass criterion (NVENC + 2.0 at ±5% size) requires further tuning iteration on the QSV knobs.

**Profile 2 (HQ tier): QSV ICQ q=23 already beats NVENC reference by +1.93 VMAF at 1.7x bitrate.** If HQ tier accepts higher bitrate budget, this profile is already viable.

## Acceptance Criteria

Each passes the five litmus tests in `.claude/rules/feature-criteria.md`.

1. **C1.** Container `/dev/dri` passthrough live. `docker exec mediavortex-worker-1-1 vainfo` succeeds and lists `VAProfileAV1Profile0 : VAEntrypointEncSlice`. Repeatable on all 4 wakko containers.
2. **C2.** `Workers.qsvcapable` boolean column exists (default FALSE). `Scripts/ReconcileQsvCapability.py` probes each worker container by `docker exec ffmpeg -encoders | grep av1_qsv` AND `vainfo | grep VAProfileAV1`, and sets `qsvcapable=TRUE` on all 4 wakko workers.
3. **C3.** `Profiles.useintelhardware` boolean column exists (default 0). DB CHECK constraint enforces `usenvidiahardware + useintelhardware <= 1` per row. Existing rows pre-validated (zero violations) before constraint add.
4. **C4.** Profile editor GUI renders an "Use Intel Hardware (QSV)" checkbox as sibling to the existing NVIDIA checkbox. Checking one auto-unchecks the other (JS-side); save-side validation rejects both set.
5. **C5.** `CodecParameterAssembler.AddCodecParameters` dispatches on `ProfileSettings.get('UseIntelHardware', 0) == 1` to emit QSV-specific ffmpeg args: `-preset <preset> -b:v <kbps> -maxrate:v <max> -bufsize:v <max> -look_ahead 1 -look_ahead_depth <N> -extbrc <0/1> -low_power <0/1> -adaptive_i <0/1> -adaptive_b <0/1> -bf <N> -g <N> -tile_cols <N> -tile_rows <N>`. Branch is sibling to the NVENC branch; no shared mutation.
6. **C6.** `WorkerCapabilityPredicate.BuildQsvPredicate(WorkerName)` exists and mirrors `BuildNvencPredicate`. Claim queries against TranscodeQueue with assigned profile having `useintelhardware=1` filter to workers with `qsvcapable=TRUE` only.
7. **C7. (Profile 1 shootout)** On ≥6 test clips spanning anime / live-action drama / fast-motion / low-light: median QSV `QSV AV1 CANARY VBR -720p` VMAF Mean ≥ NVENC `AV1 P7 CANARY VBR -720p` VMAF Mean + 2.0; per-clip filesize within ±5% of NVENC output filesize. Motion-filter VMAF pooling per `EncoderShootout` spec.
8. **C8. (Profile 2 shootout)** Same corpus: median QSV `QSV AV1 CANARY VBR -720p HQ` VMAF Mean ≥ NVENC `AV1 P6 CANARY VBR -720p HQ` VMAF Mean (parity floor); per-clip filesize within ±5%.
9. **C9.** `deploy/compose-templates/wakko.yml` updated with `devices: ["/dev/dri:/dev/dri"]` + `group_add: ["render", "video"]`; deployed `/opt/mediavortex/docker-compose.yml` synced from template.
10. **C10.** Contract test `Tests/Contract/TestQsvCapableWorkerClaim.py` asserts claim-routing invariant: a `useintelhardware=1` profile's job is claimed only by `qsvcapable=TRUE` workers. Green.

## Out of Scope

Categorized per `.claude/rules/call-graph-audit.md` Signal 4.

- **VAAPI fallback path** — category (b). QSV is the chosen backend (per earlier decision). If QSV ever fails in production we'd reach for VAAPI; that path is documented but not built.
- **wakko transcoding of >720p output** — category (b). Profile design targets -720p only. Operator can author -1080p QSV profiles later with same machinery.
- **Replacing `usenvidiahardware` boolean with a `codec`-derived single source of truth** — category (b). Two-sources-of-truth bug (codec vs usenvidiahardware) acknowledged. Reasoning: NVENC paths in production; refactor cost > benefit during onboarding. The mutex CHECK constraint contains the bug at INSERT time.
- **Cross-machine GPU mixing** — category (b). A box with both NVIDIA + Intel GPUs is supported at the Workers table level (both bools can be TRUE) but no shootout planned for that config — wakko has Arc only, I9 has NVIDIA only.

## Constraints

- Behavior-preserving for all existing NVENC paths. I9 transcodes unchanged. `usenvidiahardware` consumers untouched.
- Two-phase schema migrations: validate existing rows before adding CHECK constraint; rename-then-drop only if a column is later removed (no column removals in this directive).
- Container redeploy uses existing `mediavortex-deploy-worker` skill (per repo convention).
- Push every commit on main.
- R12: no multi-line docstrings.
- Live smoke per phase exit: each major code area (infra / schema / encoder dispatch / claim / profiles) ships with redeploy + one ffmpeg QSV smoke encode + claim routing verification.

## Engineering Calls Already Made

- **Encoder backend = av1_qsv** (oneVPL/libvpl path). Rejected `av1_vaapi` (fewer features, less mature for AV1 on Battlemage). Decision date 2026-06-29.
- **Capability flag model.** `Workers.qsvcapable` bool (parallels nvenccapable; capabilities stack). `Profiles.useintelhardware` bool (parallels usenvidiahardware; one encoder per profile). DB CHECK constraint enforces mutex on Profiles.
- **Codec column = encoder name.** `codec='av1_qsv'` for new profiles; `codec='av1_nvenc'` for existing.
- **Profile naming convention.** `QSV AV1 CANARY VBR -720p` and `QSV AV1 CANARY VBR -720p HQ` — matches existing NVENC naming.
- **QSV knobs parameterized in schema.** New `profilethresholds` columns: `qsvextbrc`, `qsvlowpower`, `qsvadaptivei`, `qsvadaptiveb`, `qsvlookaheaddepth`, `qsvtilecols`, `qsvtilerows`. Reasoning: `.claude/rules` and memory enforce "no hardcoded values when DB-driven is possible". Existing columns reused where they map cleanly: `bframes`→`-bf`, `gop`→`-g`, `rclookahead`→`-look_ahead_depth` semantically but kept separate to allow per-encoder tuning.
- **Pass criteria.** Profile 1: VMAF Mean ≥ NVENC +2.0 at ±5% filesize (visible-quality threshold). Profile 2: parity floor (HQ already aggressive).
- **Test corpus.** Reuse existing `EncoderShootout` corpus (CuteSheer / NewGirl / MinnieBowToons-Animation / BlackButler-Anime / TheOffice-Live / FourK). Same files used to tune NVENC profiles, so size comparison is apples-to-apples.
- **VBR rate envelopes.** Initial QSV profiles use SAME `sourcebitratepercent / minbitratekbps / maxbitratekbps / maxbitratemultiplier` as their NVENC counterparts (P7: 30%, 350-600. P6 HQ: 30%, 450-1200). Filesize match is the goal; matching envelope is the starting point.
- **Container redeploy authority.** Claude executes via `ssh root@wakko` + `docker compose` (per operator grant 2026-06-29).

## Phases & Tasks

### Phase A — Container infra (T1-T3)

- [ ] T1 — Edit `deploy/compose-templates/wakko.yml`: add `devices: ["/dev/dri:/dev/dri"]` and `group_add: ["render", "video"]` to `x-worker` anchor. (Template already has `stop_grace_period: 30m`; deployed compose lacks it — sync at T2.)
- [ ] T2 — Sync deployed `/opt/mediavortex/docker-compose.yml` from template; `docker compose down && up -d`; verify `docker exec mediavortex-worker-1-1 vainfo` succeeds (C1).
- [ ] T3 — Live smoke: encode 5-second test clip via `docker exec mediavortex-worker-1-1 ffmpeg -y -i /mnt/media_tv/<test.mkv> -t 5 -c:v av1_qsv -preset veryslow -b:v 500k -pix_fmt p010le /tmp/qsv_smoke.mp4`. Output exists; ffprobe confirms av1 stream. Discard.

### Phase B — Schema (T4-T6)

- [ ] T4 — `Scripts/SQLScripts/AddQsvCapableColumn.py`: idempotent `ALTER TABLE Workers ADD COLUMN IF NOT EXISTS qsvcapable boolean DEFAULT FALSE`.
- [ ] T5 — `Scripts/SQLScripts/AddUseIntelHardwareColumn.py`: adds `Profiles.useintelhardware bigint DEFAULT 0`; pre-validates `SELECT count(*) FROM Profiles WHERE usenvidiahardware = 1 AND useintelhardware = 1` returns 0; adds CHECK constraint `chk_profile_single_hw_encoder CHECK (COALESCE(usenvidiahardware,0) + COALESCE(useintelhardware,0) <= 1)` (C3).
- [ ] T6 — `Scripts/SQLScripts/AddQsvProfileThresholdColumns.py`: adds `qsvextbrc int`, `qsvlowpower int`, `qsvadaptivei int`, `qsvadaptiveb int`, `qsvlookaheaddepth int`, `qsvtilecols int`, `qsvtilerows int` to `profilethresholds`. All nullable; consumed only when `useintelhardware=1`.

### Phase C — Capability probe (T7)

- [ ] T7 — `Scripts/ReconcileQsvCapability.py`: mirrors `ReconcileNvencCapability.py`. SSH to each Linux host with QSV workers; per-container probe = `docker exec ffmpeg -encoders | grep -q av1_qsv` AND `docker exec vainfo | grep -q VAProfileAV1`. Sets `Workers.qsvcapable` idempotently. Reports stored-vs-detected diff. Marks all 4 wakko workers TRUE (C2).

### Phase D — Claim predicate (T8-T9)

- [ ] T8 — `Core/Database/WorkerCapabilityPredicate.py`: add `BuildQsvPredicate(WorkerName)` mirroring `BuildNvencPredicate`. Whitelist `qsvcapable` per existing pattern (SQL-injection-safe).
- [ ] T9 — `Features/TranscodeQueue/TranscodeQueueRepository.py`: in the unified `ClaimNextPendingJob` (post-unification) OR existing claim queries, add QSV predicate when assigned profile has `useintelhardware=1`. Mirrors NVENC predicate insertion site. (Depends on `transcode-worker-unification` close — if T8/T9 land before that directive closes, integrate into the unified path; otherwise pre-stage and integrate at unification VERIFYING.)

### Phase E — Encoder dispatch (T10)

- [ ] T10 — `Features/TranscodeJob/Emit/CodecParameterAssembler.py`: add `UseIntelHardware == 1` branch (sibling to NVENC branch, lines 21-91). Reads new ProfileSettings keys (`QsvExtBrc`, `QsvLowPower`, `QsvAdaptiveI`, `QsvAdaptiveB`, `QsvLookaheadDepth`, `QsvTileCols`, `QsvTileRows`) from `profilethresholds` JOIN. Mirror NVENC VBR rate-control math.

### Phase F — GUI (T11-T12)

- [ ] T11 — `Features/Profiles/ProfileController.py`: add `useintelhardware` to allowed-field list at line 185 + accept in POST handlers at lines 97, 150, 330.
- [ ] T12 — `Templates/Settings.html` (or profile-editor template — verify path): add "Use Intel Hardware (QSV)" checkbox sibling to NVIDIA checkbox. JS: checking one auto-unchecks the other; save handler rejects both set (defense-in-depth alongside DB CHECK).

### Phase G — Profile seeds (T13)

- [ ] T13 — `Scripts/SQLScripts/AddQsvProfiles.py`: idempotent INSERT of two profiles + their profilethresholds rows (480p/720p/1080p/2160p source bands like NVENC). Starting params:
  - `QSV AV1 CANARY VBR -720p`: codec=`av1_qsv`, preset=`veryslow`, ratecontrolmode=`vbr`, tune=NULL, multipass=NULL, pixelformat=`p010le`, audiocodec=`aac`, audiobitratekbps=128, audiochannels=2, audiofilter=loudnorm linear like NVENC, container=`mp4`, faststart=TRUE, useintelhardware=1, usenvidiahardware=0. Thresholds: sourcebitratepercent=30, min=350, max=600, maxbitratemultiplier=2.0, gop=NULL (encoder default), bframes=4, scaleheight=720, transcodedownto from-1080p+. QSV-knob starting set: qsvextbrc=1, qsvlowpower=0, qsvadaptivei=1, qsvadaptiveb=1, qsvlookaheaddepth=40, qsvtilecols=1, qsvtilerows=1.
  - `QSV AV1 CANARY VBR -720p HQ`: same as above but min=450, max=1200 (mirrors NVENC P6 HQ envelope).

### Phase H — Test harness (T14-T15)

- [ ] T14 — `Scripts/Smoke/EncoderShootout.py`: add `av1_qsv` variant block. Emits `ffmpeg -i <src> -c:v av1_qsv -preset <preset> -b:v <kbps> -maxrate:v <max> -bufsize:v <max> -look_ahead 1 -look_ahead_depth <N> -extbrc 1 -low_power 0 -adaptive_i 1 -adaptive_b 1 -bf <N> -pix_fmt p010le -vf 'scale=-2:<height>:force_original_aspect_ratio=decrease' -an -t <duration> <out.mp4>`. Audio omitted in shootout per existing harness convention.
- [ ] T15 — `Scripts/Smoke/QsvShootout.matrix.json`: declares wakko as the encoding host (SSH-driven shootout — extend harness if needed), 6 source clips (reuse NVENC corpus), 4-6 QSV variant configs sweeping preset (`veryslow` vs `slow`), look_ahead_depth (20/40/60), and tile_rows (1 vs 2) at the P7-equivalent and P6-HQ-equivalent bitrate envelopes.

### Phase I — Shootout iteration (T16-T18)

- [ ] T16 — Execute shootout on wakko. Sidecar JSON to `Scripts/Smoke/QsvShootout-WakkoArcB580-2026-06-29.shootout.json`.
- [ ] T17 — Analyze: for each of the 6 clips, compute QSV-VMAF-Mean vs NVENC-VMAF-Mean and filesize delta. Pick winning variant per profile (Profile 1 + Profile 2). If C7/C8 not met, iterate matrix JSON (adjust look_ahead_depth, preset, tile config) and re-run. Hard stop at 3 iterations — if no win, escalate.
- [ ] T18 — Promote winning params: UPDATE the seeded profilethresholds rows with the QSV-specific knob values from the winning variant. UPDATE Profiles rows with the winning preset.

### Phase J — Production flip (T19-T20)

- [ ] T19 — UPDATE Workers SET transcodeenabled=TRUE, qsvenabled=TRUE (or per-mode flags as established), status='Online' WHERE workername LIKE 'wakko-worker-%'. Restart containers.
- [ ] T20 — End-to-end live smoke: queue 2 production MediaFiles (one with assigned `QSV AV1 CANARY VBR -720p`, one with `QSV AV1 CANARY VBR -720p HQ`). Verify claim by a wakko worker, ffmpeg succeeds, TranscodeAttempts row with VMAF populated, ComplianceGate evaluates against the new profile.

### Phase K — Doc updates (T21-T23)

- [ ] T21 — Update or create `Features/TranscodeJob/Worker/<wakko-worker-or-similar>.feature.md` documenting Arc B580 capability, QSV path, and the two new profiles.
- [ ] T22 — Update `transcode.flow.md` if any stage seam shape changed (likely just CodecParameterAssembler internal — no cross-stage shape change, so probably no flow doc edit needed).
- [ ] T23 — Update `Features/Profiles/nvenc-profiles.feature.md` cross-reference or create `Features/Profiles/qsv-profiles.feature.md` documenting the two new profiles + their tuning history.

### Phase L — Verify + deliver (T24-T26)

- [ ] T24 — Run `Tests/Contract/TestQsvCapableWorkerClaim.py` (new); existing test suite green.
- [ ] T25 — Populate `### Verification` section in directive doc with concrete evidence per C1-C10.
- [ ] T26 — Populate `### Promotions` section: spec sections promoted into `qsv-profiles.feature.md` + wakko worker doc.

## Files Affected (preliminary)

```
# Container infra
deploy/compose-templates/wakko.yml                                          -- EDIT (devices, group_add, stop_grace_period sync)

# Schema migrations
Scripts/SQLScripts/AddQsvCapableColumn.py                                   -- CREATE
Scripts/SQLScripts/AddUseIntelHardwareColumn.py                             -- CREATE
Scripts/SQLScripts/AddQsvProfileThresholdColumns.py                         -- CREATE
Scripts/SQLScripts/AddQsvProfiles.py                                        -- CREATE

# Capability probe
Scripts/ReconcileQsvCapability.py                                           -- CREATE

# Claim predicate
Core/Database/WorkerCapabilityPredicate.py                                  -- EDIT (BuildQsvPredicate)
Features/TranscodeQueue/TranscodeQueueRepository.py                         -- EDIT (claim integration; depends on unification close)

# Encoder dispatch
Features/TranscodeJob/Emit/CodecParameterAssembler.py                       -- EDIT (QSV branch)

# GUI
Features/Profiles/ProfileController.py                                      -- EDIT (allowed-field whitelist + POST handlers)
Templates/Settings.html OR profile-editor template                          -- EDIT (checkbox + JS)

# Test harness
Scripts/Smoke/EncoderShootout.py                                            -- EDIT (av1_qsv variant block)
Scripts/Smoke/QsvShootout.matrix.json                                       -- CREATE

# Contract tests
Tests/Contract/TestQsvCapableWorkerClaim.py                                 -- CREATE

# Docs
Features/Profiles/qsv-profiles.feature.md                                   -- CREATE
Features/TranscodeJob/Worker/wakko.feature.md OR similar                    -- CREATE OR EDIT
Features/Profiles/nvenc-profiles.feature.md                                 -- EDIT (cross-reference)
```

## Open Questions Surfaced During Spec Draft

1. **Worker doc location.** Is there an existing per-host worker feature doc, or are workers documented at the `WorkerService` level? Need to check `Features/TranscodeJob/Worker/` and `deploy/` for the right home for wakko-specific notes.
2. **Profile editor template path.** `Grep` showed `Templates/Settings.html` references `UseNvidiaHardware`; verify whether profile editor lives there or in a separate template before T12 estimate firms up.
3. **Compose redeploy method.** Operator's `mediavortex-deploy-worker` skill exists; verify its scope (does it deploy a single host, or all hosts?). If single-host, T2 uses it directly; if all-hosts, T2 needs scoping.
4. **Audio policy for new profiles.** NVENC canary profiles use loudnorm linear `I=-23:LRA=15:TP=-2`. New profiles should match (audio path is encoder-independent). Verified pre-existing pattern.

## Sequencing Risk

The active `transcode-worker-unification` directive (IMPLEMENTING) is editing `Features/TranscodeQueue/TranscodeQueueRepository.py` and the claim queries. T9 (claim integration) collides with unification's T23. Mitigation: T9 lands AFTER unification closes; T1-T8 + T10-T18 are independent and can proceed before unification close (file collision check needed per-task).
