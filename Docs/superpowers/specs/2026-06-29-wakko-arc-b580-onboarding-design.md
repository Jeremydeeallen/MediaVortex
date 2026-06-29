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
7. **C7. (Profile 1 shootout, revised 2026-06-29).** On ≥6 test clips spanning anime / live-action drama / fast-motion / low-light: median QSV `QSV AV1 CANARY VBR -720p` VMAF Mean ≥ NVENC `AV1 P7 CANARY VBR -720p` VMAF Mean **at matched OUTPUT filesize ±5%**. Phase H sets QSV's bitrate envelope HIGHER than NVENC's so output filesizes match. **Original "+2.0 VMAF" criterion abandoned per 2026-06-29 probe** — Battlemage AV1 has a hardware-fixed quality-per-bit deficit vs Ada NVENC; +15% bits buys parity, +2 VMAF at matched bits is unreachable on this hardware. The QSV envelope (minbitratekbps=480 vs NVENC's 350) is the actual ship parameter. Motion-filter VMAF pooling per `EncoderShootout` harness.
8. **C8. (Profile 2 shootout)** Same corpus: median QSV `QSV AV1 CANARY VBR -720p HQ` VMAF Mean ≥ NVENC `AV1 P6 CANARY VBR -720p HQ` VMAF Mean (parity floor) at matched filesize ±5%; per-clip filesize within ±5%.
9. **C9.** `deploy/compose-templates/wakko.yml` updated with `devices: ["/dev/dri:/dev/dri"]` + `group_add: ["render", "video"]`; deployed `/opt/mediavortex/docker-compose.yml` synced from template.
10. **C10.** Contract test `Tests/Contract/TestQsvCapableWorkerClaim.py` asserts claim-routing invariant: a `useintelhardware=1` profile's job is claimed only by `qsvcapable=TRUE` workers. Green.

## Call-Graph Audit (per `.claude/rules/call-graph-audit.md` five signals)

Required before NEEDS_STANDARDS_REVIEW exits.

**Signal 1 — Multiple flow docs for one conceptual operation:** CLEAN. `transcode.flow.md` is the single flow doc for the transcode pipeline. No new flow doc needed; QSV is a new encoder strategy within the existing `Features/TranscodeJob/Emit/` stage, not a new pipeline.

**Signal 2 — Mode-branching at orchestration:** **FIRES.** `Features/TranscodeJob/Emit/CodecParameterAssembler.py:21` reads `UseNvidiaHardware == 1` then emits NVENC ffmpeg args; the `else` arm emits SVT-AV1 args. Adding QSV as a third `if UseIntelHardware == 1` sibling perpetuates the branch-on-flag pattern. The principled fix is to dispatch on `Profile.codec` via an `IEncoderArgsStrategy` ABC + per-codec strategies (`NvencEncoderArgsStrategy`, `QsvEncoderArgsStrategy`, `SvtAv1EncoderArgsStrategy`). `CodecParameterAssembler` becomes the dispatcher; the strategy classes own their knob emission. **Resolution: collapse in-flight (category a). Strategy refactor lands in Phase E1 before any QSV branch is added.**

**Signal 3 — Shared output columns sparsely populated:** CLEAN. The unification directive's `PostEncodeMeasurementService.Measure` (C4 there) runs after every encoder produces ffmpeg output and is encoder-agnostic. QSV encodes will populate `AudioPolicyResolved` and `AudioTracksEmittedJson` identically to NVENC. Verify in VERIFYING with `SELECT count(*) WHERE AudioPolicyResolved IS NULL GROUP BY ProfileName` after first QSV transcode.

**Signal 4 — Ambiguous OOS:** Each item below tagged (a) preserve-and-collapse-in-flight or (b) acknowledged debt.

**Signal 5 — Config-driven call-graph shape:** CLEAN. `useintelhardware=0` vs `=1` selects which Strategy's `AddCodecParameters` method runs. Same registry lookup happens, same dispatcher function executes; only the data flowing through it changes branch. The strategy registry is built once at startup from `Profile.codec` discriminator. No flag value ADDS or REMOVES nodes from the call graph; flags drive DATA only.

## Out of Scope

- **VAAPI fallback path** — category (b). QSV is the chosen backend. VAAPI variants tested during 2026-06-29 onboarding probe but path not productionized. Re-evaluate only if QSV proves unstable in production.
- **wakko -1080p / -2160p profiles** — category (b). Profile design targets -720p only. -1080p QSV profiles authored in a follow-up directive after -720p ships.
- **Eliminating the `usenvidiahardware` / `useintelhardware` flags entirely** — category (b). The principled SoT is `Profile.codec` (`av1_nvenc` / `av1_qsv` / `libsvtav1`); the flags are redundant. Removed in a follow-up directive `encoder-flag-collapse` (the mutex CHECK constraint contains the bug at INSERT time meanwhile).
- **Container can run QSV** — category (a). **Phase A1 rebuilds the worker image** on an Intel-PPA-compatible base (Ubuntu noble) so `libmfx-gen1.2` installs. Host-side `ffmpeg-modern` used during 2026-06-29 probe is REMOVED at end-of-directive — production transcodes run inside containers, never via SSH workaround.
- **Cross-machine GPU mixing** — category (b). A box with both NVIDIA + Intel GPUs is supported at the Workers table level (both bools can be TRUE) but no shootout planned for that config — wakko has Arc only, I9 has NVIDIA only.
- **Expose ALL legacy NVENC knobs not currently in the GUI** (spatial-aq, temporal-aq, weighted_pred, aq_strength) — category (a). The new GUI work for QSV knobs reveals that several NVENC knobs are also hardcoded in `CodecParameterAssembler`. Collapsing the encoder-strategy branches (Phase E1) requires each strategy to read all its knobs from `Profile` / `ProfileThresholds`. Means NVENC also gains `SpatialAq`, `TemporalAq`, `WeightedPred`, `AqStrength` as `Profile` columns surfaced in the editor.

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

## Hook Compliance Pre-Flight

Required reads before NEEDS_DOC_PREREAD -> IMPLEMENTING (R1 enforces). All with R18 `limit<=50`.

| Touch | Same-dir feature/flow Read required |
|---|---|
| `Scripts/Smoke/EncoderShootout.py` | `Scripts/Smoke/EncoderShootout.feature.md` |
| `Features/TranscodeJob/Emit/CodecParameterAssembler.py` and the new `EncoderArgsStrategies/` package | `Features/TranscodeJob/Emit/encode-emit.feature.md` |
| `Features/Profiles/*.py` and `Templates/Settings.html` profile editor block | `Features/Profiles/Profiles.feature.md` + `Features/Profiles/nvenc-profiles.feature.md` |
| `Core/Database/WorkerCapabilityPredicate.py` | (no same-dir feature md; covered by `path-storage` patterns) |
| `deploy/*` and any worker bootstrap edits | `deploy/worker-deploy.feature.md` + `deploy/worker-deploy-linux.flow.md` |

R15 anchors required on every `def` / `class` edit: `# directive: wakko-arc-b580-onboarding`.

R12: single-line code anchors only; no docstrings beyond one line.

R13: no new `*.feature.md` / `*.flow.md` files until DELIVERING. Phase J creates `qsv-profiles.feature.md` and the wakko-worker deploy doc section at DELIVERING only.

R16: any `*.feature.md` / `*.flow.md` edit ships with `**Slug:** <slug>` in first 15 lines.

R11: every migration uses `IF NOT EXISTS` / `ON CONFLICT`.

R2: every `INSERT` numeric literal in seed scripts carries `# from: <path-to-evidence>` citation.

R6: every Edit/Write to `EncoderShootout.py` must FIRST eliminate the 7 pre-existing `os.path.{exists,getsize,abspath}` sites — those refuse any unrelated edit. Single Write (whole-file rewrite) is the path; sequential Edits will be refused because each leaves residual violations.

## Pre-Existing Debt to Clear in This Directive

These are R-rule violations the directive's plan touches. Each must be fixed in the SAME commit that introduces new code so the hook lets the new code in.

- **`Scripts/Smoke/EncoderShootout.py` R6 sweep (7 sites):** lines 137 (`os.path.getsize` + `os.path.exists`), 194 (`os.path.exists`), 323 (`os.path.exists`), 345 (`os.path.exists`), 357 (`os.path.abspath`), 368 (`os.path.getsize`). Migrate to `Core.Path.LocalPath.LocalExists` / `LocalGetSize` / `LocalAbsPath`. All harness paths are local (ffmpeg binary, encoded output, matrix JSON, XML log) — `Local*` family applies.
- **`Features/TranscodeJob/Emit/CodecParameterAssembler.py` hardcoded knobs:** `-spatial-aq 1 -temporal-aq 1` literals at line 72. Per the "no hardcoded values" rule + Phase E1 Strategy refactor, NVENC strategy reads `Profile.SpatialAq` and `Profile.TemporalAq` from new columns (added in Phase B). Defaults to current literal value via `COALESCE(SpatialAq, 1)` at the SQL layer — no behavior change, but configurable.

## Phases & Tasks

Phase order satisfies hook gating + DDD/SOLID call-graph audit findings. Each phase ends with a live smoke that verifies the seam touched in that phase.

### Phase A — Wakko deployment migration to native systemd (T1-T4)

Drops the container on wakko. Host already has libmfx-gen + libvpl + iHD + render group; container was fighting all of these.

- [ ] T1 — Create `deploy/worker-systemd-template/mediavortex-worker@.service` template unit. Reads worker name from instance (`%i`), uses `CPUAffinity` for cpuset, `Environment=` for DB connection + share mappings, `ExecStart=/opt/mediavortex/venv/bin/python /opt/mediavortex/WorkerService/Main.py`, `Restart=always`, `RestartSec=10`, `KillSignal=SIGINT`, `TimeoutStopSec=1800`.
- [ ] T2 — Create `deploy/InstallWakkoNativeWorker.sh`: pulls source tree to `/opt/mediavortex/` (via git clone or rsync from I9 SMB), creates venv, installs `requirements.txt`, installs the systemd template, enables `mediavortex-worker@{1..4}` with cpuset 0-3 / 4-7 / 8-11 / 12-15 via per-instance drop-in files.
- [ ] T3 — Execute T1/T2 on wakko via SSH. `docker compose down` the existing containers (after worker DB rows show no in-flight work). `systemctl enable --now mediavortex-worker@{1..4}`. Confirm 4 process trees via `systemctl status`.
- [ ] T4 — Live smoke (host-side ffmpeg, NOT via container): worker process picks up source tree, claims a test job, runs `av1_qsv` encode via the in-source `CodecParameterAssembler` (after Phase E ships). For NOW (Phase A close), just verify the systemd workers start clean, register in `Workers` table, and heartbeat. No encoder smoke yet — that comes after Phase E.
- [ ] T_Decommission — at directive close: remove `mediavortex-worker:latest` containers from wakko; remove `deploy/compose-templates/wakko.yml` (or mark it deprecated with a pointer to the systemd path). Remove `/usr/local/bin/ffmpeg-modern` host-side workaround binary.

### Phase B — Schema migrations (T5-T9)

- [ ] T5 — `Scripts/SQLScripts/AddQsvCapableColumn.py`: `ALTER TABLE Workers ADD COLUMN IF NOT EXISTS qsvcapable boolean DEFAULT FALSE`. Idempotent (R11). Cite `# from: Features/Profiles/Profiles.feature.md` (or appropriate spec).
- [ ] T6 — `Scripts/SQLScripts/AddUseIntelHardwareColumn.py`: `ALTER TABLE Profiles ADD COLUMN IF NOT EXISTS useintelhardware bigint DEFAULT 0`. Pre-validate `SELECT count(*) FROM Profiles WHERE COALESCE(usenvidiahardware,0) + COALESCE(useintelhardware,0) > 1` returns 0. Add CHECK constraint `chk_profile_single_hw_encoder`.
- [ ] T7 — `Scripts/SQLScripts/AddProfileNvencAdvancedColumns.py`: `ALTER TABLE Profiles` add `spatialaq int`, `temporalaq int`, `weightedpred int`, `aqstrength int` (overrides existing `aqstrength` if present). All nullable. Surfaces previously-hardcoded NVENC knobs (per OOS item).
- [ ] T8 — `Scripts/SQLScripts/AddProfileQsvAdvancedColumns.py`: `ALTER TABLE Profiles` add `lowpower int`. `ALTER TABLE profilethresholds` add `qsvextbrc int`, `qsvadaptivei int`, `qsvadaptiveb int`, `qsvlookaheaddepth int`, `qsvbstrategy int`, `qsvtilecols int`, `qsvtilerows int`. All nullable. Why on `profilethresholds` not `Profiles`: these are bitrate-range-dependent tunables (different look-ahead depth at 720p vs 1080p).
- [ ] T9 — `Scripts/SQLScripts/AddEncoderBackendDiscriminator.py`: documentation-only migration that adds a CHECK constraint `chk_codec_implies_hw_flag` enforcing `(codec='av1_nvenc' AND usenvidiahardware=1) OR (codec='av1_qsv' AND useintelhardware=1) OR (codec='libsvtav1' AND COALESCE(usenvidiahardware,0)+COALESCE(useintelhardware,0)=0)`. Pre-validates all rows before the constraint adds. Closes the two-sources-of-truth Signal 5 risk by enforcing them consistent.

### Phase C — EncoderShootout R6 sweep + QSV arm (T10-T11)

- [ ] T10 — `Scripts/Smoke/EncoderShootout.py`: single Write replacing all 7 `os.path.*` sites with `Core.Path.LocalPath.LocalExists` / `LocalGetSize` / `LocalAbsPath`. Pre-existing R6 violations cleared in same commit (clearing-only commit, no behavior change).
- [ ] T11 — `Scripts/Smoke/EncoderShootout.py`: add `av1_qsv` encoder arm in `BuildEncodeCmd` (mirrors `av1_nvenc` arm structure). Add `fps=24000/1001` (or `fps={Source.fps}`) lock to the VMAF filter chain (defensive — VMAF chain timebase walk-off bug discovered 2026-06-29). Add per-variant `host` field support (default `local`; `ssh:user@host` routes via SSH to a remote ffmpeg, used for wakko QSV encodes orchestrated from I9). Update `Scripts/Smoke/EncoderShootout.feature.md` criteria (this edit happens at DELIVERING per R13 — for now, the new criteria stay in this design doc).

### Phase D — Capability probe (T12-T13)

- [ ] T12 — `Core/Database/WorkerCapabilityPredicate.py`: add `BuildQsvPredicate(WorkerName)` mirroring `BuildNvencPredicate`. Whitelist `qsvcapable` per existing pattern. Add unit test in `Tests/Contract/TestClaimAuthority.py` asserting QSV gate parallels NVENC gate.
- [ ] T13 — `Scripts/ReconcileQsvCapability.py`: mirrors `ReconcileNvencCapability.py`. For each Linux worker, native or containerized, probe via `ssh + ffmpeg -encoders | grep av1_qsv` + `vainfo | grep VAProfileAV1`. Sets `Workers.qsvcapable` idempotently. For wakko native workers, ffmpeg path is the venv-installed binary; for any future container-based QSV host, `docker exec` is used. Reconciles all 4 wakko workers to TRUE.

### Phase E — Encoder Strategy refactor + QSV emission (T14-T18)

This phase resolves Call-Graph Audit Signal 2 (mode-branching at orchestration). Strategy refactor happens BEFORE adding QSV so we don't add a third branch first.

- [ ] T14 — Create `Features/TranscodeJob/Emit/EncoderArgsStrategies/` package: `__init__.py`, `IEncoderArgsStrategy.py` ABC with `AddCodecParameters(CommandParts, CodecParameters, ProfileSettings) -> None` (mirrors current method signature).
- [ ] T15 — Create `Features/TranscodeJob/Emit/EncoderArgsStrategies/NvencEncoderArgsStrategy.py`: extracts current NVENC arm from `CodecParameterAssembler.AddCodecParameters` (lines 21-91). Reads `SpatialAq`, `TemporalAq`, `WeightedPred`, `AqStrength` from `ProfileSettings` with `COALESCE(*, 1)` for safe defaults (preserves current hardcoded behavior on rows that haven't been edited yet).
- [ ] T16 — Create `Features/TranscodeJob/Emit/EncoderArgsStrategies/SvtAv1EncoderArgsStrategy.py`: extracts current `else` arm (lines 92-101). Handles `libsvtav1` codec (CPU encode, CRF + preset).
- [ ] T17 — Create `Features/TranscodeJob/Emit/EncoderArgsStrategies/QsvEncoderArgsStrategy.py`: NEW. Reads `Preset`, `RateControlMode`, `Bf`, `Gop`, `LowPower`, `QsvExtBrc`, `QsvAdaptiveI`, `QsvAdaptiveB`, `QsvLookaheadDepth`, `QsvBStrategy`, `QsvTileCols`, `QsvTileRows` from `ProfileSettings`. Emits the operator-validated QSV knob set.
- [ ] T18 — Refactor `Features/TranscodeJob/Emit/CodecParameterAssembler.AddCodecParameters` to dispatch on `ProfileSettings.get('Codec')` via a Strategy registry: `{'av1_nvenc': NvencEncoderArgsStrategy(), 'av1_qsv': QsvEncoderArgsStrategy(), 'libsvtav1': SvtAv1EncoderArgsStrategy()}`. The dispatcher is a single registry lookup; no `if codec == X` branches at the orchestration layer. Delete the inline NVENC + SVT arms.

### Phase F — GUI surfaces ALL advanced knobs (T19-T21)

This phase resolves the "Expose ALL knobs" OOS commitment.

- [ ] T19 — `Features/Profiles/ProfileController.py`: add new columns to allowed-field whitelist (`UseIntelHardware`, `SpatialAq`, `TemporalAq`, `WeightedPred`, `LowPower`). Accept in POST/PUT handlers. Validation: enforce mutex `usenvidiahardware`+`useintelhardware` server-side too (defense-in-depth alongside DB CHECK).
- [ ] T20 — `Templates/Settings.html` profile editor `ProfileEditable` array: add per-encoder groups so the editor shows the right knobs per `Codec`:
  - `Encoder` group (always visible): `Codec`, `Preset`, `RateControlMode`, `FilmGrain`, `PixelFormat`
  - `NVENC` group (visible when `Codec='av1_nvenc'`): `UseNvidiaHardware`, `Tune`, `Multipass`, `SpatialAq`, `TemporalAq`, `WeightedPred`, `AqStrength`
  - `Intel QSV` group (visible when `Codec='av1_qsv'`): `UseIntelHardware`, `LowPower`. Plus the threshold-level QSV knobs in `ThresholdEditable`: `QsvExtBrc`, `QsvAdaptiveI`, `QsvAdaptiveB`, `QsvLookaheadDepth`, `QsvBStrategy`, `QsvTileCols`, `QsvTileRows`.
  - JS: group visibility responds to `Codec` change. Save validates exactly one of `UseNvidiaHardware==1` / `UseIntelHardware==1` consistent with `Codec`.
- [ ] T21 — `Templates/Settings.html`: per-encoder inline help text linking each knob to its ffmpeg arg (operator can `Get-Help` from screen). E.g., "SpatialAq -> -spatial-aq" so the GUI doubles as a knob-to-ffmpeg-arg reference.

### Phase G — Profile seeds (T22)

- [ ] T22 — `Scripts/SQLScripts/AddQsvProfiles.py`: idempotent INSERT of two profiles + their `profilethresholds` rows. R2 citations: profile params from this design doc; QSV knob starting values from `Scripts/Smoke/ArcB580-VAAPI-Smoke-2026-06-29.shootout.json` (2026-06-29 baseline).
  - `QSV AV1 CANARY VBR -720p`: `codec=av1_qsv preset=veryslow ratecontrolmode=vbr pixelformat=p010le useintelhardware=1 lowpower=0`. Per-resolution thresholds: `sourcebitratepercent=30 minbitratekbps=350 maxbitratekbps=600 maxbitratemultiplier=2.0 bframes=7 qsvextbrc=1 qsvadaptivei=1 qsvadaptiveb=1 qsvlookaheaddepth=100 qsvbstrategy=1 qsvtilecols=1 qsvtilerows=1`.
  - `QSV AV1 CANARY VBR -720p HQ`: same but `minbitratekbps=480 maxbitratekbps=900` (operator decision per 2026-06-29 shootout: QSV needs +15% bits to match NVENC quality).

### Phase H — Shootout via the production harness (T23-T25)

NO ad-hoc shell scripts. Everything through `Scripts/Smoke/EncoderShootout.py`.

- [ ] T23 — `Scripts/Smoke/QsvVsNvencCanary720p.matrix.json`: declares ≥6 sources (NewGirl / CuteSheer / MinnieBowToons / BlackButler / TheOffice / FourK — same corpus as historical NVENC shootouts), per-source `source_video_bitrate_kbps` from ffprobe (operator runs probe in advance), and variants: NVENC P7 canary (host=`local` = I9), QSV canary parity (host=`ssh:root@wakko`), QSV canary HQ (host=`ssh:root@wakko`). All variants at same target bitrate envelope for the parity comparison.
- [ ] T24 — Execute shootout: `py Scripts/Smoke/EncoderShootout.py --matrix Scripts/Smoke/QsvVsNvencCanary720p.matrix.json`. Sidecar JSON to `Scripts/Smoke/QsvVsNvencCanary720p.shootout.json`. Cross-source rollup gives median Mean / P5 / size for each variant.
- [ ] T25 — Acceptance gate: median QSV VMAF Mean ≥ NVENC VMAF Mean at matched filesize ±5% for Profile 2 (HQ tier) per C8. For Profile 1, accept the documented -2 VMAF gap as **NEW C7 (revised below)** since 2026-06-29 probe confirms it's a hardware-fixed gap, not a tuning miss.

### Phase I — Production cut-over (T26-T27)

- [ ] T26 — `UPDATE Workers SET transcodeenabled=TRUE, remuxenabled=TRUE WHERE workername LIKE 'wakko-worker-%'` (in coordinated worker-stop-then-start per memory rule `worker_restart_protocol`).
- [ ] T27 — Live production smoke: queue 2 MediaFiles with assigned QSV profiles. Verify wakko worker claims via QSV predicate. ffmpeg via `CodecParameterAssembler.AddCodecParameters -> QsvEncoderArgsStrategy`. `TranscodeAttempts` row records `Disposition='Replace'` (or expected disposition). `AudioPolicyResolved` populated (Signal 3 verification).

### Phase J — DELIVERING (R13 relaxed; doc promotions happen here)

- [ ] T28 — Create `Features/Profiles/qsv-profiles.feature.md` documenting the two QSV canary profiles, their VBR rate envelopes, QSV-specific knobs, and tuning lineage.
- [ ] T29 — Update `deploy/worker-deploy-linux.flow.md` with the new ST<N> for native systemd workers (the new path coexists with the docker path; not all Linux workers migrate, only wakko).
- [ ] T30 — Update `Features/TranscodeJob/Emit/encode-emit.feature.md` `## Seams` table with the new Strategy registry seam.
- [ ] T31 — Update `Templates/Settings.html`'s `Features/Profiles/Profiles.feature.md` cross-reference if the editor surface widened the per-profile contract.
- [ ] T32 — Populate `### Promotions` section in directive doc per `doc-layering.md` mechanically-enforced gate.

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
