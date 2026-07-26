# Current Directive

**Set:** 2026-07-03
**Status:** Active -- phase: IMPLEMENTING
**Slug:** transcode-flow-canonical
**Inherits:** 5 LIVE PENDING criteria from `transcode-worker-unification` (see .claude/directives/closed/2026-07-03-transcode-worker-unification.md close note)

## Outcome

MediaVortex has ONE canonical pipeline for every FFmpeg-driven media-transformation job (re-encode, stream-copy/remux, audio-only-fix, container-only-fix). One flow doc, one JobProcessor class, one claim query, one output row shape, one Verify seam. Variance lives in Plan (`VideoOp`/`AudioOp`/`SubtitleOp`/`ContainerOp`) and in Strategy at ST5 (encode) + ST8 (verify). Applies DDD + SOLID + DRY throughout. Documentation-first: doc surgery precedes code. Fail loudly: no fallbacks. Docs describing violated behavior are deleted, not annotated.


## Call-Graph Audit

Closed 2026-07-03 at NEEDS_STANDARDS_REVIEW. Full 5-signal audit (Signals 1-5 + evidence) archived at `.claude/directives/closed/2026-07-03-transcode-flow-canonical-archive.md`.

## Acceptance Criteria

Each passes the five litmus tests in `.claude/rules/feature-criteria.md`. All grep patterns / SQL queries listed are the verification tests.

**C0. Architectural baseline documents at MAP tier.**
- C0a. `ARCHITECTURE.md` shrunk to MAP tier (<= 130 lines). Column-list and class-name bleed migrated to owning feature docs via Promotions. New `## Job Types` section with three rows (Transcode / QualityTest / Scan) each with capability flag + claim helper + link to flow doc. `Transcode / Remux` two-shape references rewritten. `## Gap to Target` re-audited against reality (currently claims EMPTY 2026-06-21 but Signal 3 shows AudioPolicyResolved 0% populated).
- C0b. `GLOSSARY.md` created at repo root, referenced from `CLAUDE.md`. Four buckets: Project vocabulary, Media/encoding, Job model, Infrastructure. Entries alphabetical per bucket. Every entry names an authoritative source. Deprecated terms carry replacement pointer. Named as durable-doc tier in `.claude/rules/doc-layering.md`.

**C1. One pipeline shape per job type.** Three flow docs for FFmpeg-driven job types: `transcode.flow.md`, `quality-test.flow.md` (create), `Features/FileScanning/FileScanning.flow.md` (verify canonical). No `remux.flow.md` (already deleted; verify still gone). `transcode.flow.md` describes 10-stage shape: Enqueue -> Claim -> Probe -> Plan -> Encode(Strategy) -> Audio -> Subs -> Verify(Strategy) -> Replace -> Reprobe+Notify. New rule `.claude/rules/flow-docs.md` gains "one flow per pipeline shape" invariant. `audio-normalization.flow.md` decision (sub-flow vs stage-detail fold) recorded in ### Decisions Made. Verification: `Get-ChildItem -Recurse *.flow.md | Select-String "^# .*[Rr]emux"` returns zero; grep `class .*JobProcessor` in `Features/TranscodeJob/Worker/` returns one base + Strategy subclasses.

**C2. Enqueue routes converge on one contract.** All producers (web GUI, scanner, requeue, canary, smoke-test) write to `TranscodeQueue` via one entry point (`AddJobToQueue`). BUG-0078 fixed as instance: `ForceAdd=True` on VMAF>=80 candidate inserts a row and returns `Success=True, Skipped=False`; log line reflects actual insert vs skip. Verification: contract test `Tests/Contract/TestEnqueueContract.py` asserts every producer path produces rows with identical non-null column set; SQL audit `SELECT COUNT(DISTINCT (audiopolicyjson IS NOT NULL, storagerootid IS NOT NULL, relativepath IS NOT NULL)) FROM transcodequeue WHERE createdat > <cutover>` returns 1.

**C3. Claim path is single-source.** All claim queries (`ClaimNextPendingJob`, `ClaimQualityTestJob`, scan claim) route through `Core.Database.WorkerCapabilityPredicate.BuildClaimPredicate`. `Tests/Contract/TestClaimAuthority.py` full-green with zero pre-existing sentinel failures (inherits and resolves transcode-worker-unification C9). Verification: grep `WHERE.*Enabled\s*=\s*TRUE` in `Features/*/Repositories/*.py` and `Repositories/*.py` outside `WorkerCapabilityPredicate.py` returns 0.

**C4. Orchestration is mode-blind.** Grep `(Mode|ProcessingMode|EffectiveMode)\s*(==|!=|in\s*\()\s*['"](Remux|Transcode|AudioFix|SubtitleFix|Quick)` in production code under `Features/TranscodeJob/`, `Features/TranscodeQueue/`, `Features/FileReplacement/`, `Features/Activity/` outside `*Strategy*.py` and `Models/*.py` returns **0** (Signal 2 found 9+ today). Strategy carries all variance. Inherits transcode-worker-unification C26 (call-graph shape invariance under feature-flag toggles); live verified per C9 smoke.

**C5. Shared output columns populated by every strategy.** For last 30 days post-cutover, SQL `SELECT profilename, COUNT(*) as n, COUNT(audiopolicyresolved) as apr, COUNT(audiopolicyjson) as apj, COUNT(audiotracksemittedjson) as atej FROM transcodeattempts WHERE completeddate > <cutover> GROUP BY profilename` returns `apr = n AND apj = n AND atej = n` for every profile family. Signal 3 baseline: `AudioPolicyResolved` = 0/1121 today. Target: 100% per strategy after cutover. Inherits transcode-worker-unification C4. `Vmaf` populated per C6.

**C6. Compliance gate is not bypassable.** `Disposition='BypassReplace'` retired. Signal 3 baseline: 981/1121 (88%). StreamCopy strategy emits checksum verification (video stream bit-identical). Re-encode strategy emits VMAF. Both write `Disposition IN ('Replace','Reject','Requeue')`. BUG-0079 fixed as instance: `Disposition='Requeue'` inserts a new `TranscodeQueue` row via C2's canonical admission. Verification: SQL `SELECT DISTINCT disposition FROM transcodeattempts WHERE completeddate > <cutover>` returns subset of `{Replace, Reject, Requeue}`; SQL `SELECT COUNT(*) FROM transcodeattempts WHERE disposition IN ('Requeue') AND completeddate > <cutover> AND NOT EXISTS (SELECT 1 FROM transcodequeue tq WHERE tq.mediafileid = transcodeattempts.mediafileid AND tq.createdat >= transcodeattempts.completeddate)` returns 0.

**C7. Fail loudly. No fallbacks.** New rule `.claude/rules/fail-loud.md` created BEFORE code sweep (reset step 4). Anti-patterns removed:
- Bare `except:` and `except Exception:` without raise
- `... or 0`, `... or ''`, `... or <default>` on decision inputs (config reads, DB reads, contract args)
- `if X is None: X = <default>` on decision inputs
- Silent try/except around DB writes

Contract test `Tests/Contract/TestFailLoud.py` greps for anti-patterns in production paths (`Features/`, `Workers/`, `WorkerService/`, `WebService/`, `Repositories/`, `Core/`); count == 0 outside explicitly whitelisted paths recorded in the test itself. BUG-0075 (partial): `StuckJobDetectionService.py:472,1029` already writes `Success=FALSE` (verified 2026-07-03). Remaining C7 scope: QT admission refuses freeze-marker rows so downstream QT doesn't claim orphan work.

**C8. Docs describing violated behavior are deleted, not annotated.** Every `*.feature.md` / `*.flow.md` / `ARCHITECTURE.md` section describing a removed route is deleted in the same commit as the code. Verification: grep `deprecated|superseded|legacy|removed 20|no longer used|previously|formerly` in `**/*.feature.md`, `**/*.flow.md`, `ARCHITECTURE.md` returns 0 outside `GLOSSARY.md`. R14 hook already enforces at edit-time.

**C9. Four live smokes end-to-end.** Each smoke: TranscodeAttempts row with `completeddate > <cutover>` and `disposition=Replace`, recorded in `### Verification` with mediafileid + strategy + timestamp + audio-emit check.
- (a) web GUI enqueue -> Reencode -> VMAF pass -> Replace
- (b) web GUI enqueue on container-fix candidate -> StreamCopy -> checksum pass -> Replace
- (c) scanner auto-enqueue -> full pipeline -> Replace
- (d) Requeue disposition (BUG-0079 verification) -> new queue row inserted -> claimed -> completed -> Replace

**Per-smoke audio-emit check** (verifies audio pipeline ST6/ST7 for every strategy since audio path is universal): `ffprobe -show_streams -select_streams a` on the emitted output asserts:
- Two audio tracks (Track 0 Original + Track 1 Dialog Boost)
- `Track 0.channels` = source channels (5.1 stays 5.1; stereo stays stereo)
- `Track 1.channels` = 2 (forced stereo downmix)
- `Track 0.disposition.default` = 0; `Track 1.disposition.default` = 1
- Track 0 integrated LUFS within +/-1 LU of `TargetIntegratedLufs`

Any smoke where audio-emit check fails = C9 fails. Covers AudioFix workflow verification structurally (AudioFix bucket = plan variant `VideoOp=Copy + AudioOp=Reencode`, exercised via smoke (b) or (c) if candidate file has AudioFix bucket).

Inherits transcode-worker-unification C5 (MediaFileId=621412 replay -- becomes any Reencode-strategy smoke) + C8 (no regression baseline vs post) + audio-dialog-boost-real G1/G2/G3/G4 verification pattern.

**C10. Directive doc size guard at DELIVERING.** Directive doc size <= 110% of snapshot taken at IMPLEMENTING -> DELIVERING transition. `### Promotions` populated incrementally per step per memory rule `feedback_promotions_grow_incrementally`, not batched.

**C11. Compliance-gate MaxAudioChannels must not fire against Track-0-preserves-source outputs.** `audio-dialog-boost-real` shipped a 2-track pipeline (Track 0 preserves source layout up to 7.1; Track 1 forced stereo Dialog Boost) but did NOT sweep the `compliance-symmetry` (closed 2026-06-22 C9) `MaxAudioChannels=2` cap in `AudioPolicyAdmissionGate.AdmitOrDefer`. Result: every 5.1+ source triggers `DispositionReason=ComplianceGateFailed:channels_exceed_max:6>2` post-encode, `.inprogress` deleted, no `Replace`. Reset 7 NVENC smoke on 688909 hit this. **Owning docs:** `Features/AudioNormalization/audio-normalization.feature.md` (2-track contract SOT) + `Features/AudioNormalization/audio-normalization.flow.md`. **Fix:** the source-vs-cap check in `AudioPolicyAdmissionGate.py:127-134` is dead under the 2-track contract (Track 0 always preserves source, Track 1 always 2ch); delete the check; leave `MaxAudioChannels` column intact for potential future per-track caps (documented as inactive in audio-normalization.feature.md). Also unblocks Reset 7 smoke (a). Verification: re-run NVENC smoke on MediaFileId=688909 -> `Disposition=Replace`, `FileReplaced=TRUE`; audio-emit check (per C9) passes.

**C12. Profile tier-ladder model.** `Profiles` gains `Family TEXT NOT NULL` + `QualityTier INT NOT NULL CHECK (QualityTier BETWEEN 1 AND 5)` + `ContentClass TEXT NOT NULL CHECK (ContentClass IN ('live_action','animation','mixed'))`. UNIQUE `(Family, QualityTier, ContentClass, TargetResolutionCategory)`. Two families kept: `'NVENC AV1 CANARY'` (VBR, av1_nvenc, p7 preset — p6 for 4K) and `'QSV AV1 CANARY'` (ICQ, av1_qsv, p1 preset). `ProfileThresholds.TargetKbps` INT NOT NULL added — absolute target per (Profile, Resolution). Dead columns retired via `AlignProfileTierModel_2026_07_XX.py` migration: `SourceBitratePercent`, `MinBitrateKbps`, `MaxBitrateKbps`, `Quality` (moved into `ProfileThresholds.IcqQ` when RateControlMode='icq'). `NvencEncoderArgsStrategy` + `QsvEncoderArgsStrategy` rewritten to consume `TargetKbps` (VBR) or `IcqQ` (ICQ) directly. Every non-CANARY AV1 profile deleted; orphaned `MediaFiles.AssignedProfile` re-classified via ContentClassifier. Bitrate table live-action calibration (per Q1 2026-07-03 operator design):

| Resolution | Codec | Tier 1 | Tier 2 | Tier 3 | Tier 4 | Tier 5 |
|---|---|---|---|---|---|---|
| 480p | AV1 | 400 | 550 | 700 | 900 | 1200 |
| 720p | AV1 | 900 | 1400 | 1900 | 2500 | 3200 |
| 1080p | AV1 | 1800 | 2400 | 3200 | 4200 | 5500 |
| 2160p | AV1 | 4000 | 6000 | 8500 | 12000 | 18000 |

Animation-class rows may drop 30% (live-action first per Reset 10 backend; animation dimension exercised via smoke). ICQ ladder: q34/q30/q28/q26/q22 across tiers 1-5. Verification: `Tests/Contract/TestProfileTierLadder.py` proves (Family, ContentClass, Resolution) -> Tier 1..5 rows present; encoder-args tests assert absolute -b:v / -global_quality flow from TargetKbps / IcqQ columns; grep `SourceBitratePercent` in `Features/**/*.py` returns 0.

**C13. Admission-adequacy gate.** New service `Features/TranscodeQueue/AdequacyGate.Evaluate(MediaFile)`. Computes `SourceKbps` at admission; if `SourceKbps <= Tier1TargetKbps` for `(Family=AssignedProfile.Family, ContentClass=..., ResolutionCategory=SourceResolutionTier)`, admission short-circuits: no re-encode enqueued. Container/audio still eligible for StreamCopy (Remux / AudioFix) if their compliance columns fail. Otherwise `MediaFile.WorkBucket -> NULL` (already compact enough). Emits `MediaFiles.AdequacyDecision TEXT` + `AdequacyDecisionAt TIMESTAMP` for audit. Verification: `Tests/Contract/TestAdequacyGate.py` -- source at Tier1-1kbps admitted, source at Tier1+1kbps excluded; live smoke on a 700 kbps 720p live-action source proves exclusion + no queue row.

**C14. Smart VMAF sampling (statistical confidence skip).** New table `VmafConfidenceStats(ProfileId, SourceCodec, SourceResolutionTier, BitratePerPixelBucket, ContentClass, SampleCount, VmafMean, VmafStdDev, PassRate, LastUpdated)` UNIQUE per bucket. `PostTranscodeGateConfig` gains `MinConfidenceSampleCount INT DEFAULT 10`, `MinConfidencePassRate NUMERIC DEFAULT 0.95`, `SigmaMargin NUMERIC DEFAULT 2.0`. Decider gains `SmartConfidenceSkip` branch: when `bucket.SampleCount >= MinConfidenceSampleCount AND bucket.PassRate >= MinConfidencePassRate AND (bucket.VmafMean - SigmaMargin*bucket.VmafStdDev) >= VmafAutoReplaceMinThreshold` -> `Replace/QualityTestConfident` (skips VMAF, deterministically). Every VMAF completion writes result back into the matching bucket via `VmafConfidenceStatsRepository.RecordResult`. Rolling window trims oldest samples at N=100. Bootstrap: new bucket at SampleCount=0 forces VMAF. Drift detection: PassRate drops naturally -> VMAF resumes. Verification: `Tests/Contract/TestSmartConfidenceSkip.py` -- bootstrap forces VMAF, N clean passes flips skip, one fail drops pass rate below threshold, VMAF resumes; live smoke: run 10 CANARY tier 2 encodes of same source-class, observe 11th attempt skips VMAF.

**C15. GUI /settings transcoding card.** `/settings` gains a "Transcoding" card (sibling to "Post-Transcode"). Fields: (a) bitrate ladder editor per `(Family, ContentClass, Resolution)` -> tier 1..5 grid, save writes `ProfileThresholds.TargetKbps` rows. (b) ICQ ladder (per Family) tier 1..5 -> `IcqQ`. (c) adequacy-gate section: Tier1 exclusion enabled toggle + margin (%). (d) VMAF confidence: `MinConfidenceSampleCount`, `MinConfidencePassRate`, `SigmaMargin`. (e) Global `QualityTestEnabled` checkbox (writes `PostTranscodeGateConfig.QualityTestEnabled`). (f) `VmafConfidenceStats` review table: read-only per-bucket display (ProfileId + bucket key -> SampleCount / PassRate / VmafMean / VmafStdDev / LastUpdated). Endpoints `GET/PUT /api/SystemSettings/Transcoding`. Verification: UI form submits round-trip; live edit reflects on next Decider call (no restart).

**C16. Restore global `QualityTestEnabled=false -> auto-Replace`.** Reset 9 folded this to `Pending/AwaitingVmaf` per qt-queue-visibility-and-override C7. Per 2026-07-03 operator decision (Q4), restore auto-Replace semantic. `PostTranscodeDispositionDecider.Decide` re-adds branch: `if not GateConfig.QualityTestEnabled: return Disposition(Action='Replace', Reason='QualityTestingGloballyDisabled')`. `qt-queue-visibility-and-override.feature.md` C1 wording tightens: "always enqueue when VMAF required AND QualityTestEnabled=true"; C7 rewritten to acknowledge global-off as legitimate auto-replace. Verification: `Tests/Contract/TestDispositionDecider.py` gains `test_global_off_returns_replace_qualitytestinggloballydisabled`; live smoke: flip `PostTranscodeGateConfig.QualityTestEnabled=false`, enqueue a Transcode job, observe `Disposition=Replace/QualityTestingGloballyDisabled`, restore flag before commit.

**C17. Collapse Emit-layer ProcessingMode branching into a slot-composed CommandComposer + fix subtitle-drop bug (BUG-0083).** Operator 2026-07-04 identified that Reset 7 mode-blind orchestration (C4) stopped at the orchestration layer -- `Features/TranscodeJob/Emit/EncodeShapeRegistry` still keys by `ProcessingMode ('Transcode' | 'Remux' | 'SubtitleFix' | ...)` and dispatches to `TranscodeShape` / `RemuxShape` / `SubtitleFixShape`. Every non-SubtitleFix shape omits `-map 0:s`, silently dropping subtitle streams on every Replace (~27127 files auto-replaced all-time; Hotel Chevalier smoke exposed it). New single composer:

`Features/TranscodeJob/Emit/CommandComposer.Build(Job, MediaFile, Plan) -> ffmpeg argv` composes 4 slots per Plan:
- `VideoSlot.Emit(Plan.VideoOp, ...)` -- Reencode (NVENC VBR / QSV ICQ per Family) or StreamCopy
- `AudioSlot.Emit(Plan.AudioOp, ...)` -- 2-track pipeline (Original preserved + Dialog Boost) always; StreamCopy variant when AudioOp='Copy'
- `SubtitleSlot.Emit(Plan.SubtitleOp, ...)` -- **ALWAYS fires**; container-appropriate codec: MP4 target -> `-map 0:s? -c:s mov_text`; MKV target -> `-map 0:s? -c:s copy`; image-based subs (PGS/DVB) targeted to MP4 -> WARN + drop (needs OCR pass, deferred)
- `ContainerSlot.Emit(Plan.ContainerOp, ...)` -- container-format change or preserve

`Plan` is the tuple `{VideoOp, AudioOp, SubtitleOp, ContainerOp}` derived from `MediaFile.WorkBucket` + AssignedProfile at admission. ProcessingMode retires at Emit layer: `EncodeShapeRegistry`, `TranscodeShape`, `RemuxShape`, `SubtitleFixShape` DELETED (code + `Features/TranscodeJob/Emit/*Shape*.feature.md` + doc references). `NvencEncoderArgsStrategy` + `QsvEncoderArgsStrategy` collapse into VideoSlot Reencode implementations (Family + RateControlMode data-driven).

Verification:
- `Tests/Contract/TestCommandComposer.py` CREATE -- covers every Plan combination; asserts SubtitleSlot fires on every path; MP4 target emits mov_text, MKV target emits copy.
- `Tests/Contract/TestNoLegacyResidue.py` extended -- grep `EncodeShapeRegistry`, `TranscodeShape(`, `RemuxShape(`, `SubtitleFixShape(`, `class.*Shape.*:` under `Features/TranscodeJob/Emit/` = 0 outside CommandComposer/Slot files + tests + migration.
- Grep `-map 0:s` count in `Features/TranscodeJob/Emit/` >= 1 (present in SubtitleSlot); grep of any shape file returns "not found" (deleted).
- Live smokes: (a) Reencode with source that has English + French text subs -> emitted `-mv.mp4` retains both subs with `mov_text` codec + language metadata; (b) StreamCopy Remux on mkv source with SRT subs -> emitted `-mv.mp4` retains subs converted to mov_text; (c) Reencode on source with PGS image subs -> emitted `-mv.mp4` has no subs + WARN log naming the dropped codec.

BUG-0083 filed. Un-pause `Workers.TranscodeEnabled=TRUE` gated on C17 live smokes passing.

**C18. VMAF alignment + model matching (canonical measurement pipeline).** VMAF today is systematically wrong for diverse media because reference and distorted feeds are not aligned on 13 axes. Score noise dominates real quality signal; every disposition decision downstream (Replace / Requeue / Reject) is suspect. This criterion delivers a canonical measurement pipeline mirroring the encode-side pattern (Plan-derived composer) but shaped for VMAF's LINEAR filter chain domain.

New verticals under `Features/QualityTesting/Vmaf/`:
- **`AlignmentSpec`** value object. Immutable, invariants in ctor (raises on unparseable color primaries / fps / duration-delta > 1 frame). Fields: `ColorPrimaries`, `TransferFunction`, `ColorMatrix`, `ColorRange`, `SourceFps`, `TargetFps`, `VfrDetected`, `TargetResolution`, `SourceCrop`, `EncodedCrop`, `DeinterlaceNeeded`, `DetelecineNeeded`, `SourceBitDepth`, `TargetBitDepth`, `ChromaSubsampling`, `HdrDetected`, `MaxEdgePx`.
- **`VmafAlignmentProbe`** domain service. `Probe(SourcePath, EncodedPath) -> AlignmentSpec`. Reads via shared `MediaProbeAdapter`; asserts duration parity; resolves reference-transformation strategy when source shape != encoded shape (tone-map HDR ref → SDR bt709 when encoded is SDR; NEVER transform distorted).
- **`VmafModelSelector`** strategy (pure fn). `Select(spec) -> VmafModel` per rules: max-edge >= 1440 → `vmaf_4k_v0.6.1`; max-edge <= 540 → `vmaf_v0.6.1_phone`; HDR flag → `vmaf_v0.6.1neg`; else default `vmaf_v0.6.1`.
- **`VmafFilterChainBuilder`** pure-function composition. `Build(spec) -> str`. Stages composed in fixed order: `setpts → deinterlace → detelecine → fps → colorspace → crop → scale → chroma → libvmaf(model)`. Each stage = pure fn `(spec, partial_chain) -> extended_chain`. No injection, no classes.
- **`VmafCommandComposer`** thin shell. `Build(Attempt, spec) -> argv`. Owns: `-i <dist> -i <ref>` order, optional `-ss`, `-lavfi` injection, `-f null`, XML log path, `libvmaf` n_threads. Delegates chain to Builder + model to Selector.
- **`ColorSpaceService`** cross-cutting. Centralizes color-triad parsing (primaries + transfer + matrix + range) with fail-loud on unparseable. Encode side migrates to consume it in follow-up directive.

`QualityTestingBusinessService.BuildVMAFCommand` retires; replaced by call into `VmafCommandComposer`. `_BuildVmafFilterChain` retires (folded into `VmafFilterChainBuilder`). 24-fps silent fallback deleted.

13 axes covered:
1. Color primaries pin
2. Transfer function pin (SDR gamma / PQ / HLG)
3. Color matrix pin (bt709 / bt2020nc)
4. Color range pin (TV / full, detected not hard-coded)
5. Framerate pin + fail-loud parse (no 24 fps fallback)
6. VFR → CFR detection + normalization
7. VMAF model select (4K / phone / neg / default)
8. Deinterlace detect + apply
9. Detelecine detect + apply
10. Crop / letterbox detect + normalize on both feeds
11. Chroma subsampling pin (match source or downsample to 4:2:0 consistently on both)
12. Duration parity assertion (delta ≤ 1 frame or fail-loud raise)
13. Bit depth pin (match source; libvmaf 10-bit precision retained)

**Live smoke matrix (10 smokes; each proves at least one axis):**
- (a) SDR 1080p CFR 24fps live-action — baseline; score close to prior for this shape.
- (b) HDR 4K PQ — color triad + 4K model + bit-depth.
- (c) Animation 24p VFR — VFR detect + CFR normalize + motion=0 still applies.
- (d) Interlaced 1080i broadcast — deinterlace applied; VMAF non-garbage.
- (e) Telecined 24p → 30i film — detelecine applied.
- (f) Letterbox 2.35:1 in 16:9 container — crop detect + apply on both feeds.
- (g) Phone-source 540p vertical — phone model selected.
- (h) Truncated encode (30s missing) — duration parity fail-loud.
- (i) 4:2:2 source encoded to 4:2:0 — chroma pin + no false artifact scoring.
- (j) Unparseable color primaries source — fail-loud raise, no fallback.

Verification: `Tests/Contract/TestAlignmentSpec.py` (invariants + fail-loud), `TestVmafAlignmentProbe.py` (shape derivation), `TestVmafModelSelector.py` (model rules), `TestVmafFilterChainBuilder.py` (stage composition), `TestVmafCommandComposer.py` (end-to-end argv), `TestColorSpaceService.py`; 10 live smokes documented in `### Verification` with attempt id + VMAF score + axis-fired assertion.

**C19. Deploy hardening (retires BUG-0085 hazard).** Every future Linux worker re-deploy is deterministic — no stale-pyc leak.
- **`deploy/Dockerfile`** adds `RUN find /opt/mediavortex -name __pycache__ -type d -exec rm -rf {} +` after source COPY, before ENTRYPOINT. Ensures no cached-layer .pyc survives the source copy.
- **`deploy/deploy-linux-worker.py`** post-deploy probe: for each container, run `docker exec worker-N python3 -c "import Features.QualityTesting.Disposition.PostTranscodeDispositionDecider as m; import inspect; import os; p=inspect.getsourcefile(m); assert os.stat(p).st_mtime >= os.stat(p.replace('.py', '.pyc') if os.path.exists(p.replace('.py', '.pyc')) else p).st_mtime, 'stale-pyc detected'"`. Fail loudly with host + container + file on assertion violation. Deploy aborts.
- **Live smoke:** re-deploy all 12 Linux workers (dot/wakko/larry × 4). Verify zero stale-pyc post-deploy. Activate BUG-0086 fix cleanly (Wakko attestation lands on fresh QSV Requeue).

Verification: `Tests/Deploy/TestDeployStalePycProbe.py` (post-deploy probe returns non-zero on synthetic stale-pyc); live re-deploy log documented; sample fresh Wakko QSV Requeue attempt has all three attestation columns populated by Probe (not backfill).

**C20. WorkerContext thread-local binding (retires BUG-0086 deep cause).** `WorkerContext.Current()` returned None-or-degenerate for the JobProcessor thread on Linux workers, causing PostEncodeMeasurement.Probe to short-circuit. BUG-0086 fix at Reset 14 papered over the symptom (attest anyway); the binding gap persists and threatens every future code path that reads `WorkerContext.Current()`.

- **`Core/WorkerContext.py`** switches to `threading.local()` backing when currently backed by process-global; `Bind(WorkerName, FFmpegPath, FFprobePath, ...)` sets the thread-local. Worker main thread binds at boot; each spawned processing thread inherits via explicit `WorkerContext.Bind(...)` at entry.
- **`JobProcessor.Process`** re-binds WorkerContext to its running thread before any downstream call reads `Current()`. Same for `ProcessQualityTestQueueService.ProcessQueueLoop` daemon-thread `ProcessJob`.
- **Fail-loud:** `Current()` raises `WorkerContextNotBoundError` when called on a thread without a Bind. NO silent None-return. `PostEncodeMeasurementService.Probe` reverts to strict-mode: raise if binaries None (BUG-0086 fix's defensive DB attestation remains as belt-and-suspenders but should never fire again).

Verification: `Tests/Contract/TestWorkerContextThreadLocal.py` (bind + read on 2 threads returns different bindings; unbound Current() raises); `TestProbeStrictModeWhenContextBound.py` (fresh WorkerContext + Probe writes all three columns from ffprobe, not sentinel). Live smoke: Wakko QSV Requeue post-Reset-16 populates apr='resolved' + apj-from-queue + atej-from-ffprobe (real measurements), not 'unresolved' sentinel.

**C22. Fresh source-loudness measurement + LoudnessTolerance tighten 4.0 -> 3.0.** `PreEncodeAudioPipeline.Run` gains a source-loudness measurement step (ffmpeg loudnorm summary pass on source Track 0), returns `SourceMeasuredI/Lra/Tp/Thresh` in Run dict. Caller (`JobProcessor._RunPreEncodeAudio`) UPDATEs `MediaFiles.SourceIntegratedLufs/SourceLoudnessRangeLU/SourceTruePeakDbtp/SourceIntegratedThresholdLufs, LoudnessMeasuredAt=NOW()` per MediaFileId so `_BuildTrack0Chain` sees fresh values. Track 0 becomes cache-independent -- like Track 1 already is. Motivating incident: MFID 620351 Hotel Chevalier attempt 41214 landed Track 0 at -26.9 LUFS vs target -23 (3.9 LU under) due to stale `SourceIntegratedLufs=-19.4` (real -23.3) cached from 2026-05-24. `LoudnessTolerance` DB DEFAULT tightened from 4.0 to 3.0 via migration `TightenLoudnessTolerance_2026_07_07.py`. Rationale sweep in `Features/AudioNormalization/audio-normalization.feature.md`: prior "worst-case 'reach for the remote' at +/-4 LU" wording documented reason 4.0 tolerance was set to absorb single-pass loudnorm drift; fresh measurement obviates that slack (proven convergence: single-pass with correct measured_I hits Output=-23.0 offset 0.0). 3.0 sits between EBU R128 uniform-band goal (2 LU) and streaming platform norm (1 LU), preserving `adaptive` UngainablePolicy clipping-avoidance. Contract test `Tests/Contract/TestPreEncodeSourceLoudness.py` CREATE: proves Run returns source measurements + JobProcessor persists to DB + Track 0 emits with fresh values. Live smoke re-run MFID 620351 -> Track 0 AchievedIntegratedLufs within +/-1 LU of target.

**C21. Phase-aware stuck-job detection (retires Tier 2 / Tier 3 conflation).** `StuckJobDetectionService` today runs Tier 2 (frame-advance stale) + Tier 3 (FFmpegPid liveness) against every job whose `TranscodeQueue.Status='Running'`, but `Running` overloads four disjoint phases: Setup (path resolve + audio pre-pass demucs) / Encoding (main ffmpeg subprocess) / PostEncode (VMAF / Disposition / Replace / Reprobe) / Verifying (QT queue). Each phase has different valid signals (Setup: elapsed vs setup-timeout; Encoding: frame-advance vs threshold; PostEncode / Verifying: elapsed vs per-phase timeout). Result: false-positive kills (Reset 15 Wakko cycle: attempts 41147/41151 both killed by wrong-phase detector).

Domain: `Features/ServiceControl/JobPhase.py` -- `JobPhase` enum (`Setup`, `Encoding`, `PostEncode`, `Verifying`). `ActiveJobs.Phase TEXT` + `PhaseTransitionedAt TIMESTAMP` columns via `Scripts/SQLScripts/AddActiveJobsPhaseColumn_2026_07_05.py` (idempotent, backfills existing rows to `Encoding`).

Repository: `Features/ServiceControl/JobPhaseRepository.py` -- `SetPhase(ActiveJobId, JobPhase)` writes column + updates `PhaseTransitionedAt=NOW()`. `GetPhase(ActiveJobId)` reads fresh (no cache; db-authority).

Phase transitions written by phase-owning components (SRP):
- Claim -> `Setup` (`TranscodeQueueRepository.ClaimNextPendingJob` after ActiveJob creation).
- `Setup` -> `Encoding` (`VideoTranscodingService.TranscodeVideo` before `subprocess.Popen`).
- `Encoding` -> `PostEncode` (`VideoTranscodingService.TranscodeVideo` after `Process.wait()` returns).
- `PostEncode` -> `Verifying` (`QualityTestingBusinessService` at QT claim / Disposition start).

Strategy pattern: `IPhaseDetector` interface (`Detect(Job, ActiveJob) -> (bool, str)`). Four impls under `Features/ServiceControl/PhaseDetectors/`:
- `SetupPhaseDetector`: elapsed since `PhaseTransitionedAt` > `SetupPhaseTimeoutMin` (SystemSettings, default 30 min -- covers longest demucs run).
- `EncodingPhaseDetector`: `_IsJobFrozen` logic folded here -- frame-advance stale > `FrozenProgressThresholdMin` (default 5). Adds FFmpegPid liveness: if FFmpegPid recorded AND local host AND process gone / not ffmpeg-named -> stuck.
- `PostEncodePhaseDetector`: elapsed since `PhaseTransitionedAt` > `PostEncodePhaseTimeoutMin` (SystemSettings, default 15 min).
- `VerifyingPhaseDetector`: elapsed since `PhaseTransitionedAt` > `VerifyingPhaseTimeoutMin` (SystemSettings, default 30 min).

Registry: `Features/ServiceControl/PhaseDetectorRegistry.py` -- static `dict[JobPhase, IPhaseDetector]`. Open/Closed: new phase = new detector + dict row. Zero touch to caller.

`StuckJobDetectionService.IsJobStuck` refactored: reads `ActiveJob.Phase` via repo, dispatches to registry. `_IsJobFrozen` DELETED (folded). Tier 3 PID liveness DELETED (folded into `EncodingPhaseDetector`). Tier 1 (worker offline heartbeat) survives unchanged.

FFmpegPid column retained as kill-target for `Encoding` phase. Cleared automatically at Encoding->PostEncode transition. Kill target lookup only queries FFmpegPid when Phase='Encoding'.

Verification: `Tests/Contract/TestJobPhaseTransitions.py` (each transition writes column + timestamp); `TestPhaseDetectors.py` (per-phase timeout + false-positive-guard); `TestStuckJobDetectionPhaseAware.py` (registry dispatch by phase). Live smoke: Wakko QSV Transcode of MFID 8653 -- claim writes Setup, demucs runs 10+ min without stuck-detector firing, Encoding phase enters when Popen spawns, PostEncode enters when ffmpeg completes, Verifying enters at QT claim, attempt lands `Success=TRUE` with `AudioPolicyResolved='resolved'` + real `AudioPolicyJson` + `AudioTracksEmittedJson` (activates C19+C20 fresh-code proof on QSV path).

**C25 IMPLEMENTATION EVIDENCE (2026-07-09).** Migration `Scripts/SQLScripts/CollapseProfilesToTierLadder_2026_07_09.py` executed LIVE: 5 snapshot tables created (populated for rollback: `profiles_snapshot_20260709`=44 rows, `profilethresholds_snapshot_20260709`=164, `mediafiles_snapshot_20260709`=51834, `transcodeattempts_snapshot_20260709`=32731, `transcodequeue_snapshot_20260709`=0); `profiles.qualitylabel` + `profilethresholds.contentclass` columns added; 5 tier profiles inserted (`AV1 CANARY Tier N Efficient/Good/Better/Best/Reference`, family='ANY', codec='av1', usenvidiahardware=0, useintelhardware=0); 20 threshold rows per approved ladder (4 res x 5 tier, TargetKbps 400/900/1800/4000 -> 1200/3200/5500/18000, IcqQ q34/q30/q28/q26/q22); 40 old CANARY per-Family profiles deleted; 160 old thresholds deleted; UNIQUE (profileid, resolution) replaced with UNIQUE (profileid, contentclass, resolution); UNIQUE (qualitylabel) added; FK rewrites: ~51100 `mediafiles.assignedprofile` remapped by qualitytier. Post-migration MediaFiles distribution: `Tier 2 Good`=50458, `Tier 1 Efficient`=448, `Tier 4 Best`=241, `Tier 3 Better`=36, `Tier 5 Reference`=1. `Features/TranscodeJob/Worker/WorkerEncoderResolver.py` CREATED: reads `Workers.nvenccapable`+`qsvcapable` fresh per call; NVENC preferred when both; larry (no encoder) raises `WorkerEncoderResolverError` fail-loud. NVENC overrides: p7+uhq+fullres+vbr+SpatialAq/TemporalAq/AqStrength/RcLookahead. QSV overrides: p1+icq+ExtBrc+AdaptiveI/B+LookaheadDepth+TileCols/Rows. `ProcessTranscodeQueueService.GetTranscodingSettings` gains resolver-injection: when `ProfileSettings.Codec == 'av1'`, invokes `WorkerEncoderResolver.ApplyOverrides(self.WorkerName, ProfileSettings)` -- mutates dict BEFORE `CodecFlagsRepository.GetCodecFlagsByCodecName` lookup. `TranscodeQueueRepository.ClaimNextPendingJob` claim query gains outer guard: `AND (COALESCE(p.codec,'') <> 'av1' OR w.nvenccapable = TRUE OR w.qsvcapable = TRUE)` -- CPU-only workers refused for family-agnostic profiles. **End-to-end verified live:** MFID 691670 (Tier 1 Efficient @ 1280x720) -> EncoderKnobRepository returns Codec='av1' + TargetKbps=900 + IcqQ=34; resolver on I9-2024 produces argv `-c:v av1_nvenc -preset p7 -tune uhq -multipass fullres -rc vbr -b:v 900k -maxrate:v 1800k -bufsize:v 1800k -spatial-aq 1 -temporal-aq 1 ...`; resolver on wakko-worker-1 produces argv `-c:v av1_qsv -preset 1 -rc icq -global_quality:v 34 -low_power 0 -extbrc 1 -tile_cols 2 -tile_rows 2 ...`. Same profile, two encoders, both valid ffmpeg. **Deferred to follow-up:** GUI /settings Transcoding card refresh; enqueue-by-quality query-param endpoint (`?quality=Efficient`); least-loaded ORDER BY in claim; ContentClassifier Family retirement (currently benign -- still writes AssignedProfile string); animation ContentClass rows; Linux fleet redeploy for dot+wakko workers to pick up code (I9 restart picks up source); live smoke of 61 Love Island files (requires operator un-pause of dot+wakko + WebService restart to activate new claim + resolver path).

**C25 CONTRACT TESTS LANDED (2026-07-09).** 4 test files under `Tests/Contract/` for the 4 Reset-25 spec entries. `TestFamilyAgnosticProfile.py` (11 tests): profiles.qualitylabel + profilethresholds.contentclass columns present; profiles_qualitylabel_unique + profilethresholds_profile_content_res_unique constraints present; exactly 5 family='ANY' + codec='av1' + usenvidiahardware=0 + useintelhardware=0 tier profiles; labels {Efficient, Good, Better, Best, Reference}; 20 threshold rows (5 tiers x 4 resolutions {480p, 720p, 1080p, 2160p}); TargetKbps + IcqQ populated for every row; legacy CANARY families deleted. `TestAnyCapableWorkerClaimsFamilyAgnostic.py` (6 tests): claim SQL source-grep for the encoder-agnostic av1 guard (`COALESCE(p.codec,'') <> 'av1' OR w.nvenccapable=TRUE OR w.qsvcapable=TRUE`); LEFT JOIN Profiles present; no re-introduction of NVENC-CANARY/QSV-CANARY family literals; `_ALLOWED_CAPABILITIES` whitelist includes both nvenccapable + qsvcapable. `TestWorkerEncoderResolver.py` (11 tests, mock-DB): NVENC-only worker -> ('NVENC', av1_nvenc); QSV-only -> ('QSV', av1_qsv); dual-capable prefers NVENC; no-encoder raises WorkerEncoderResolverError; missing worker raises; ApplyOverrides mutates dict in place + returns family + preserves unrelated keys; NVENC_OVERRIDES carries p7/hq/fullres/vbr/SpatialAq/TemporalAq; QSV_OVERRIDES carries p1/icq; fresh DB read per call (no cache); overrides are per-call copies (not shared aliases). `TestEnqueueByQualityLabel.py` (4 preconditions + 3 skips): each expected label uniquely identifies one family-agnostic av1 profile; no duplicate labels; tier-to-label bijection {1:Efficient, 2:Good, 3:Better, 4:Best, 5:Reference}; profiles_qualitylabel_unique is a UNIQUE (backs O(1) label lookup); 3 skipped tests document endpoint deferral (`?quality=<label>` + `?tier=<n>` + AddJobToQueue label->ProfileId resolver). Full run: **32 pass + 3 skipped in 0.34s**.

**C25. Family-agnostic Profile model + human-labeled quality tiers + any-worker claim.** Today's Profile is keyed on `(Family='NVENC AV1 CANARY'|'QSV AV1 CANARY', QualityTier 1..5, ContentClass, TargetResolutionCategory)` -- 40 CANARY rows (2 Family x 4 res x 5 tier). Queue row carries `ProfileId` -> pins a specific Family at admission. Claim gates on matching capability (`nvenccapable` for NVENC-Family rows / `qsvcapable` for QSV-Family rows). Consequence: whichever encoder Family ContentClassifier assigns first, ONLY that half of the fleet can claim -- the other half sits idle. To fanout a series across NVENC + QSV, operator must manually alternate ProfileId per file. Not dynamic. Operator ask (2026-07-09): "I want to set a quality [and] any worker should be able to pick it up." Also: 40-row profile catalog is oversized; reduce to Family-agnostic Tier ladder + rename tiers to human-legible labels.

Domain rewrite:
- **Profile.Family + Profile.ContentClass + Profile.TargetResolutionCategory all retired from the Profile row.** UNIQUE key collapses to `(QualityTier)` alone. Row count: 40 -> **5** (one per tier). Profile catalog IS the tier ladder; nothing else.
- **New column `Profile.QualityLabel TEXT NOT NULL UNIQUE`** with human-legible name per tier (approved 2026-07-09): Tier 1 `Efficient`, Tier 2 `Good`, Tier 3 `Better`, Tier 4 `Best`, Tier 5 `Reference`. Labels are DATA (per `feedback_no_hardcoded_values.md`) -- adding a sixth tier is one INSERT into Profiles + N INSERTs into ProfileThresholds.
- **`ProfileThresholds` UNIQUE key becomes `(ProfileId, ContentClass, TargetResolutionCategory)`.** All per-resolution + per-content-class variance moves to this table. Both `TargetKbps` (NVENC VBR) + `IcqQ` (QSV ICQ) columns live per row. Initial row count: 5 tier x 4 res x 1 content class = 20 threshold rows (was 40 profiles + 20 threshold rows). Animation adds thresholds, not profiles.
- **Encoder selection moves from ADMISSION to CLAIM.** `TranscodeQueue.INSERT` writes `ProfileId` (Family-agnostic; also Resolution/ContentClass-agnostic since Profile no longer carries either). `TranscodeQueueRepository.ClaimNextPendingTranscodeJob` drops the Family predicate; claim predicate becomes `TranscodeEnabled=TRUE AND Status='Online' AND (nvenccapable=TRUE OR qsvcapable=TRUE)`. Worker resolves its own encoder at claim: `WorkerEncoderResolver.Resolve(Worker) -> EncoderFamily` reads capability. **Least-loaded worker policy (approved 2026-07-09):** at admission the ordering hint favors the claim-eligible worker with fewest concurrent ActiveJobs; at Worker-side EncoderFamily resolution, both-capable workers pick NVENC when both are available and their current NVENC slot < MaxConcurrentTranscodeJobs, else QSV. Fleet-level balancing lives in the queue-claim ORDER BY (not in individual worker greed).
- **Threshold lookup is now a JOIN, not a Profile field.** `EncoderKnobRepository.GetKnobs(ProfileId, MediaFile) -> (TargetKbps, IcqQ)` reads `ProfileThresholds` for `(ProfileId, MediaFile.ContentClass, MediaFile.ResolutionCategory)`. Missing row = fail-loud raise (per `.claude/rules/fail-loud.md`; no default). New content-class or new resolution = ADD threshold rows, no Profile change.
- **`CommandComposer.Build(Job, MediaFile, Plan, EncoderFamily)`** gains `EncoderFamily` param. `VideoSlot.EmitReencode` branches on EncoderFamily: NVENC path reads `ProfileThresholds.TargetKbps` + emits `av1_nvenc -b:v`; QSV path reads `IcqQ` + emits `av1_qsv -global_quality`. Strategy still lives in Slot -- orchestration remains mode-blind (satisfies C4).
- **ContentClassifier drops Family assignment.** Assigns `TargetTier=Efficient` per MediaFile (or per operator override). Content class + resolution live on MediaFile and drive threshold lookup at claim time; they are no longer Profile-row axes. NextTierAdjuster walks Profile.QualityTier upward on VMAF fail -- one dimension.
- **`AdequacyGate.Evaluate`** reads Tier 1 threshold via `EncoderKnobRepository.GetKnobs(Tier1ProfileId, MediaFile).TargetKbps`. Adequacy is bit-rate-adequacy across encoders (NVENC-side kbps is the anchor). Contract preserved.
- **GUI /queue enqueue-by-quality endpoint.** `POST /api/Work/Transcode/Queue/<mfid>?quality=<QualityLabel>` accepts human label (e.g. `?quality=Efficient`) OR numeric tier (`?tier=1`). Handler resolves `(QualityLabel|Tier, MediaFile.ContentClass, ResolutionCategory)` -> ProfileId, enqueues. Any capable worker claims.
- **Migration** `CollapseProfilesToTierLadder_2026_07_XX.py` (idempotent): (i) INSERT 5 new tier-only Profile rows with QualityLabel per approved vocab; (ii) MOVE ProfileThresholds rows from each old per-Family profile onto the corresponding new tier profile, folding NVENC-Family TargetKbps + QSV-Family IcqQ into single row per (NewProfileId, ContentClass, Resolution); (iii) UPDATE MediaFiles.AssignedProfile + TranscodeQueue.ProfileId + TranscodeAttempts.ProfileId to point at new tier ProfileId (map by old-Family-row's QualityTier); (iv) DELETE 40 old per-Family Profile rows; (v) DROP UNIQUE (Family, Tier, ContentClass, Resolution); ADD UNIQUE (QualityTier); ADD UNIQUE (QualityLabel); (vi) DROP columns Profiles.Family, Profiles.ContentClass, Profiles.TargetResolutionCategory; (vii) ADD UNIQUE (ProfileId, ContentClass, Resolution) on ProfileThresholds.

Verification:
- Contract test `Tests/Contract/TestFamilyAgnosticProfile.py` -- asserts `SELECT COUNT(DISTINCT (QualityTier, ContentClass, TargetResolutionCategory)) FROM Profiles WHERE ProfileName LIKE '%CANARY%'` == COUNT(*) (one row per tuple, no Family duplicates); asserts `Family` column absent; asserts `QualityLabel IN ('Efficient','Good','Better','Best','Reference')`.
- Contract test `Tests/Contract/TestAnyCapableWorkerClaimsFamilyAgnostic.py` -- claim predicate matches NVENC-capable AND QSV-capable workers on the same Pending row; two workers race, deterministic loser blocks per row-level lock.
- Contract test `Tests/Contract/TestWorkerEncoderResolver.py` -- Worker with `nvenccapable=True AND qsvcapable=True` resolves to NVENC (preferred); NVENC-only resolves to NVENC; QSV-only resolves to QSV; neither raises.
- Contract test `Tests/Contract/TestEnqueueByQualityLabel.py` -- `POST /api/Work/Transcode/Queue/<mfid>?quality=Good` inserts row with correct ProfileId; unknown label returns 400; numeric tier alias works.
- Live smoke: enqueue 61 Love Island episodes at `?quality=Efficient`; observe dot NVENC + wakko QSV workers pull concurrently from same queue (no manual ProfileId alternation); attempt rows land with Success=TRUE + real Attestation on both encoder paths.

**C23. Phantom QT ActiveJobs rows retired (BUG-0087).** Operator observed a stuck "TranscodeAttempt_None -- Worker I9-2024" tile in the QT dashboard 2026-07-08. Three defects stack: (1) `QualityTestRepository.GetRunningQualityTestProgress` at :432 SELECTs `WHERE aj.ServiceName='QualityTestService'` with NO status filter -- Completed ActiveJobs rows surface forever, LEFT JOIN misses on deleted QueueId, fallback label formats `TranscodeAttempt_{None}` at :440; sibling `GetActiveQualityTestJob` at :639 correctly gates `AND aj.Status='Running'`. (2) `OrphanCleanupService._SweepActiveJobs` invocation at :37 passes `ServiceName='QualityTestingService'` (with "ing") but every QT insert writes `'QualityTestService'` (no "ing") -- see `QualityTestingBusinessService.py:242`, `DatabaseCleanupService.py:43,54,122`, `CrashRecoveryService.py:129,172`. Orphan sweep matches zero QT rows forever. `orphan-cleanup.flow.md` ST3 documents the WRONG canonical string. (3) `StuckJobDetectionService._CleanupStuckQualityTestJob` at :755 matches on `ServiceName='QualityTest'` (third variant) -- also never matches. Stale ActiveJob 70332 (Completed 2026-07-03 during Reset 9 cleanup, QueueId=2070 since deleted from QualityTestingQueue) is the concrete row surfacing today.

Fix: (a) `QualityTestRepository.GetRunningQualityTestProgress` gains `AND aj.Status IN ('Running','Claimed')` to mirror sibling `GetActiveQualityTestJob`. (b) `OrphanCleanupService.SweepOrphans` invocation at :37 corrects to `ServiceName='QualityTestService'`; `orphan-cleanup.flow.md` ST3 doc row updates to match. (c) `StuckJobDetectionService._CleanupStuckQualityTestJob` at :755 corrects `WHERE ServiceName='QualityTest'` to `'QualityTestService'`. (d) One-shot DELETE of ActiveJob 70332. Verification: contract test `Tests/Contract/TestQualityTestServiceNameConsistency.py` asserts (i) every production-code literal referencing QT ActiveJobs uses exactly `'QualityTestService'` (grep-based; whitelist for legit non-ActiveJobs contexts like `ServiceStatus` table); (ii) `GetRunningQualityTestProgress` returns zero rows when only Completed ActiveJobs exist for QT (fixture-driven). Live smoke: after fixes deployed, `SELECT * FROM ActiveJobs WHERE ServiceName='QualityTestService' AND Status='Completed'` returns zero (row 70332 deleted); dashboard shows no "TranscodeAttempt_None" tile.

**C26. /Operations page reorders Failures above Successes with full diagnostic surface + collapsible rows.** Today `Templates/Operations.html` renders `Recent Successes` (left) and `Recent Failures` (right) as two side-by-side cards, each showing an abbreviated row set (a failure row hides FailureReason detail, ffmpeg command, worker context, disposition). Operator ask (2026-07-09): failures move above successes as full-width sections; each failure row exposes every pertinent field on demand; the row shape is collapsible so the page is scannable at rest but drills to full diagnostic on click.

Layout: `Recent Failures` card renders full-width above `Recent Successes` (also full-width). Side-by-side layout retired. `Recent Scans` position unchanged.

Failure row collapsed shape (single line, always visible): `AttemptDate | Worker | MediaFile basename | ProfileName | FailureReason (truncated to 80 chars) | expand-chevron`. Success row collapsed shape unchanged from current, plus expand-chevron.

Failure row expanded shape (revealed on click): full MediaFile path + StorageRootId + MediaFileId; full FailureReason (untruncated); `DispositionReason` + `Disposition`; `FfpmpegCommand` (existing typo column) in `<pre>` block; TranscodeDurationSeconds; PhaseTransitionedAt final phase; `Vmaf` if present; `AudioPolicyResolved` + `AudioPolicyJson` + `AudioTracksEmittedJson` if present; `SizeReductionBytes/Percent` if present; link to `/Activity?mediafileid=<id>` and `/Queue?mediafileid=<id>`. All pulled from the same `TranscodeAttempts` row -- no new backend query shape needed beyond the additional SELECT columns.

Collapse mechanism: native `<details><summary>` (no JS state, no accordion library). Multiple rows may be open simultaneously. Default state: all collapsed. Chevron rotates via CSS on `[open]`. Applies to both Failures and Successes.

Backend: `Features/Activity/Services/RecentActivityService.GetRecentFailures` (or equivalent -- verify at IMPLEMENTING) SELECT column list extended to include every field listed above. If the current endpoint returns only the collapsed-shape fields, extend it -- do NOT add a second endpoint. One row shape per operation. Success endpoint gets the same treatment for parity.

Verification: (i) manual browser check on `http://10.0.0.7:5000/Operations`: Failures section above Successes, both full-width; every failure row's `<details>` expands to reveal the fields enumerated above; every success row's `<details>` expands identically. (ii) `curl http://10.0.0.7:5000/api/<recent-failures-endpoint>` returns JSON containing `FailureReason`, `DispositionReason`, `Disposition`, `FfpmpegCommand`, `AudioPolicyResolved`, `AudioPolicyJson`, `AudioTracksEmittedJson` in every failure row. (iii) contract test `Tests/Contract/TestRecentActivityEndpointShape.py` asserts the enumerated field set is present in the response schema.

**C27. ActiveJobs badge count reflects live work + Failed rows do not persist.** Two stacked defects surfaced 2026-07-09 by operator: `/Activity` NavBadges shows `ActiveJobsCount=7` while queue is empty and only one Transcode ActiveJob is in `Status='Running'`. Root-cause audit: (1) `Features/Activity/ActivityController.NavBadges` at :92 executes `SELECT COUNT(*)::int AS n FROM ActiveJobs` with NO status filter — Failed / Completed rows leak into the badge. Same defect class as C23 (`GetRunningQualityTestProgress` no-status-filter). (2) Six `Status='Failed'` rows survive from 2026-07-09 19:29 through 19:47 (1 TranscodeService QueueId=144956; 5 QualityTestService QueueIds 2169-2173 across dot/wakko/I9) — no code path DELETEs ActiveJobs rows on Failed-state entry. Whoever writes `Status='Failed'` (Grep audit `UPDATE.*activejobs.*Status.*Failed` in `Features/**/*.py` at IMPLEMENTING) either transitions Failed as a terminal state without DELETE, OR OrphanCleanupService's `QueueId NOT IN` predicate misses these rows because their queue rows still exist. Neither prior directive (`transcode-worker-unification` C7 landed the NavBadges endpoint; `worker-runtime-state` shipped hung-encode DELETE-on-detect; `orphan-and-stale-cleanup` shipped the polymorphic-QueueId sweep; C23 in this directive fixed the sibling literal-drift) covered the Failed-state row lifecycle.

Fix: (a) `Features/Activity/ActivityController.NavBadges` at :92 SQL becomes `SELECT COUNT(*)::int AS n FROM ActiveJobs WHERE Status IN ('Running','Claimed')` — mirrors C23's C23 pattern (Status filter matches sibling `GetActiveQualityTestJob` shape). (b) IMPLEMENTING-time audit: grep every production-code path that writes `ActiveJobs.Status='Failed'` and add a `DELETE FROM ActiveJobs WHERE Id=%s` immediately after the terminal Failed write (or convert the write to a DELETE if no consumer reads the Failed state — audit consumers first). (c) OrphanCleanupService gains a supplementary sweep at `Features/ServiceControl/OrphanCleanupService.py`: `DELETE FROM ActiveJobs WHERE Status='Failed' AND StartedAt < NOW() - INTERVAL '5 minutes'` covers any orphan that escapes the terminal-write DELETE (belt-and-suspenders; StartedAt guard prevents race with in-flight Failed transitions). WARN-per-removal logging per orphan-cleanup convention. `orphan-cleanup.flow.md` ST4 row added documenting the Failed-lifetime sweep. (d) One-shot DELETE of the six leaked rows (70466, 70467, 70468, 70470, 70473, 70475) if still present at IMPLEMENTING.

Verification: (i) contract test `Tests/Contract/TestActiveJobsBadgeStatusFilter.py` asserts NavBadges endpoint body regex-contains `Status IN ('Running'` (mirrors C23's regex-assert pattern). (ii) contract test `Tests/Contract/TestActiveJobsFailedRowLifecycle.py` asserts (writer-side) grep of `UPDATE.*ActiveJobs.*Status.*'Failed'` in production tree is followed within 5 lines by `DELETE FROM ActiveJobs` on the same Id; (sweeper-side) `OrphanCleanupService.SweepOrphans` returns non-zero `ActiveJobsFailedSwept` counter on fixture with Status='Failed' + StartedAt < NOW()-6min. (iii) live verification: after fixes deployed, SQL `SELECT COUNT(*) FROM ActiveJobs WHERE Status='Failed'` returns 0 within one cleanup cycle; `curl http://10.0.0.7:5000/api/Activity/NavBadges` returns `ActiveJobsCount` matching `SELECT COUNT(*) FROM ActiveJobs WHERE Status IN ('Running','Claimed')`.

**C33. Classification completeness -- profile-independent compliance + two new buckets + self-heal subsystem retired.** Live gap surfaced 2026-07-22: 30,994 MediaFiles have `WorkBucket IS NULL`; 2,991 are stuck on `VideoCompliantReason='no_effective_profile'` because the classifier writes `AssignedProfile` AFTER `MediaProbeBusinessService:192` fires `RecomputeForFiles`. Chicken-and-egg: no profile -> no compliance -> no bucket -> invisible in WorkBucket UI -> operator cannot set profile. Heroes S01E08-E23 concrete instance. Self-heal (`AudioVerticalHealthLoop`) also disabled (`Scanners.AudioVerticalHealth.Enabled=FALSE`); even enabled, `NullComplianceRow.DETECT_SQL` requires `VideoCompliantReason IS NULL` and skips the `no_effective_profile` rows -- write-once trap. Root cause: `VideoVertical.Evaluate` reads `EffectiveProfileResolver.Resolve` to compare source against a TARGET profile; compliance is a BASELINE question, not a target question. Two bounded contexts wrongly coupled.

Domain decisions (2026-07-22):

- **Compliance is baseline-only.** "Meets library baseline" = codec in `VideoComplianceRules.AcceptableVideoCodecsCsv` + bpp under `VideoComplianceRules.BppTranscodeThreshold` (video); codec in `AudioComplianceRules.AcceptableAudioCodecsCsv` + loudness within `TargetIntegratedLufs +/- LoudnessTolerance` (audio); container in `ContainerComplianceRules.AcceptableContainersCsv` (container). `EffectiveProfileResolver` is NOT read at compliance time.
- **Adequacy is a separate, enqueue-time gate.** `AdequacyGate` already refuses re-encodes of compact sources at admission. Untouched by C33.
- **Recompression target is enqueue-time operator choice.** Quality tier (`?quality=Efficient|Good|Better|Best|Reference` or `?tier=<n>`) is chosen when operator ADMITS a file, not when compliance evaluates it. Aligns with C25 "any capable worker claims a Family-agnostic profile."
- **Classifier is retained.** `ContentClassifier` still writes `AssignedProfile` as a HINT for operator-blind auto-enqueue paths (scanner auto-enqueue, backfill). AssignedProfile is not a compliance input.
- **Self-heal deleted.** Correct pipeline needs no sweeper. Every scanned file exits with `IsCompliant IS NOT NULL`; `WorkBucket` is `Unclassified` only until the probe hook completes. No write-once trap can exist.

Two new WorkBucket registrations:

| Bucket | Predicate | Purpose |
|---|---|---|
| **Compliant** | `IsCompliant IS TRUE` | Browse/audit clean files; no admit action (operator override enqueue path still works) |
| **Unclassified** | `IsCompliant IS NULL` (any of the three compliant columns null) | Visibility into in-flight OR permanently-deferred (`audio_corrupt_suspect`, `no_audio_stream`); force-decide action |

Generated column `MediaFiles.WorkBucket` rewritten (migration):

```
CASE
  WHEN VideoCompliant IS NULL OR ContainerCompliant IS NULL OR AudioCompliant IS NULL THEN 'Unclassified'
  WHEN VideoCompliant AND ContainerCompliant AND AudioCompliant THEN 'Compliant'
  WHEN NOT VideoCompliant THEN 'Transcode'
  WHEN NOT ContainerCompliant THEN 'Remux'
  ELSE 'AudioFix'
END
```

Self-heal subsystem DELETED:
- `Features/AudioNormalization/SelfHealing/` tree removed (invariants + remediations + composition + health-service + IAudioVerticalInvariant contract).
- `WebService/Main.py.PrivateAudioVerticalHealthLoop` + `PrivateStartAudioVerticalHealth` deleted.
- Migration drops `Scanners` row `ScannerName='AudioVerticalHealth'`.
- Contract tests referencing SelfHealing (`TestAudioInvariants`, `TestAudioVerticalHealthService`, `TestPreVerticalReNormalizePolicy`, `TestH1FixtureDryRun`) deleted.
- ARCHITECTURE.md self-heal references purged.
- Every `*.feature.md` / `*.flow.md` section describing self-heal deleted (not annotated -- per C8 + R14).
- Every closed directive's Promotions section referencing SelfHealing purged (2026-06-19-audio-vertical-phase-1-completion + 2026-06-16-audio-vertical-compliance-and-activity + 2026-06-18-audio-vertical-end-to-end-verification).

Docs updated (SoT hierarchy):
- `Features/FileScanning/FileScanning.flow.md` -- entry-point flow for scan lifecycle. References classifier + signals + compliance as downstream flows (kept separate per operator decision 2026-07-22).
- `Features/ContentClassifier/content-classifier.flow.md` -- KEPT SEPARATE; documents classifier as a HINT writer, no longer a compliance prerequisite.
- `Features/ContentSignals/content-signals.flow.md` -- KEPT SEPARATE; unchanged shape.
- `Features/VideoEncoding/video-vertical.feature.md` (create if absent) -- documents profile-independent baseline compliance contract; delete every legacy paragraph mentioning profile-dependency.
- `Features/AudioNormalization/audio-normalization.feature.md` -- verify already profile-independent; delete any lingering profile-dependency prose.
- `Features/ContainerFormat/container-format.feature.md` (create if absent) -- documents profile-independent baseline compliance contract.
- `Features/WorkBucket/work-bucket.feature.md` -- add Compliant + Unclassified sections.
- `Features/WorkBucket/work-bucket.flow.md` -- update ST3 filter table.
- `GLOSSARY.md` -- add Compliant + Unclassified bucket definitions.
- `ARCHITECTURE.md` -- update Job Types + Cross-cutting concerns if self-heal listed.

Success criteria (verification). Every criterion is verified BEFORE C33 is marked IMPLEMENTED. Bar: zero residue from the pre-C33 domain across active docs + code:

- C33a. `SELECT COUNT(*) FROM MediaFiles WHERE VideoCompliantReason='no_effective_profile' OR ContainerCompliantReason='no_effective_profile'` returns 0.
- C33b. `SELECT COUNT(*) FROM MediaFiles WHERE WorkBucket IS NULL` returns 0 (every probe-complete row is bucketed).
- C33c. `SELECT DISTINCT WorkBucket FROM MediaFiles` returns subset of `{'Compliant','Unclassified','Transcode','Remux','AudioFix'}`.
- C33d. Grep `SelfHealing` in `Features/`, `WebService/`, `Scripts/`, `Tests/` (excluding directive/rules/directives-closed) returns 0.
- C33e. Grep `no_effective_profile` in production tree (`Features/`, `Scripts/`, `WebService/`, `Tests/`, plus every `*.feature.md` and `*.flow.md`) excluding the current directive + closed directives + rules-details returns 0.
- C33f. Grep `EffectiveProfileResolver` in the three vertical .py files (`Features/VideoEncoding/VideoVertical.py`, `Features/ContainerFormat/ContainerVertical.py`, `Features/AudioNormalization/AudioVertical.py`) returns 0.
- C33g. **Active-doc narrative sweep.** Every active `*.feature.md` + `*.flow.md` that describes a compliance vertical or the WorkBucket taxonomy is audited. No line claims the verticals read `AssignedProfile` / `EffectiveProfileResolver` / `Profile.TargetVideoKbps` / `no_effective_profile` at compliance time. No line lists the buckets as three-only (`Transcode` / `Remux` / `AudioFix`). Cross-vertical contract sections in `Features/Profiles/Profiles.feature.md`, `compliance-gated-rename.feature.md`, `transcode.flow.md`, `Features/Admin/Compliance/admin-compliance.feature.md` all reflect the C33 shape. Verifiable by grep + operator read-through.
- C33h. **Closed-directive anchor sweep in code.** Grep `# directive: compliance-symmetry\b|# directive: compliance-solid-refactor\b|# directive: vertical-owned-compliance\b|# directive: compliance-recompute-tools\b|# directive: video-vertical-and-bpp\b|# directive: effective-profile-to-profiles\b` in `Features/VideoEncoding/`, `Features/ContainerFormat/`, `Features/AudioNormalization/`, `Features/MediaFile/`, `Features/WorkBucket/` returns 0. Every anchor in touched-by-C33 files points to `transcode-flow-canonical` or an unrelated LIVE directive.
- C33i. **Dead-code sweep in touched files.** Every module edited by C33 is reviewed for orphaned constants, dead helpers, unused imports. Concrete pass list documented per file: `AudioVertical.py` (`_BITRATE_ROUNDING_TOLERANCE` removed if unreferenced), `VideoVertical.py`, `ContainerVertical.py`, `ComplianceSummaryController.py`, `QueueManagementBusinessService.py` (dead `_LegacyRefusalReasonFromDecision` retired), `WorkBucketController.py`, `BucketKey.py`.
- C33j. **Bucket registration correctness.** `BucketKey` registry entries for `Compliant` + `Unclassified` carry a valid `ProcessingMode` value (not `'None'`) so any admission path lands a valid `TranscodeQueue.ProcessingMode`. Verifiable: `BucketKey.FromUrlKey('Compliant').ProcessingMode in ('Transcode','Remux','AudioFix')`.
- C33k. **UI adapter coverage.** `ComplianceSummaryController._PlannedOps` handles all 5 bucket branches (Compliant + Unclassified return empty planned-ops without falling through to the mode-branches). Verifiable: unit test asserts each of the 5 buckets returns the expected ops.
- C33l. Live smoke -- new file scan: a MediaFile with `WorkBucket=NULL` (there should be none post-C33; select an Unclassified row instead) rescan (`POST /api/FileScanning/Scan/Start` on its rootfolder OR direct probe recompute); verify `WorkBucket` transitions to a valid bucket within one probe cycle. Log evidence row.
- C33m. Live smoke -- Heroes S01E08-E23 verification: `SELECT Id, RelativePath, WorkBucket FROM MediaFiles WHERE Id BETWEEN 694531 AND 694546` shows every row `WorkBucket='Transcode'`.
- C33n. Contract test `Tests/Contract/TestVerticalsAreProfileIndependent.py` asserts `VideoVertical.Evaluate`, `ContainerVertical.Evaluate`, `AudioVertical.Evaluate` accept a MediaFile with `AssignedProfile=NULL` and return `(bool/None, str/None)` without raising; grep-fence asserts source of each vertical does NOT reference `EffectiveProfileResolver`.
- C33o. Contract test `Tests/Contract/TestWorkBucketGeneratedColumn.py` asserts the DB CASE matches the C33 5-branch shape AND all 5 UrlKeys resolve via `BucketKey.FromUrlKey` AND every `MediaFiles.WorkBucket` value is in the allowed set AND `Compliant.ProcessingMode` / `Unclassified.ProcessingMode` are valid queue modes.
- C33p. Contract test `Tests/Contract/TestSelfHealingPurged.py` asserts `Features/AudioNormalization/SelfHealing/` does not exist AND `WebService/Main.py` does not import or reference `PrivateStartAudioVerticalHealth` / `PrivateAudioVerticalHealthLoop` / `AudioVerticalHealthComposition` AND `Features/Activity/ActivityRepository.py` does not carry `GetAudioVerticalHealth`.
- C33q. WebService live-restart verified — no `AudioVerticalHealth` log line at startup; `/api/Work/Compliant`, `/api/Work/Unclassified`, `/api/Work/Transcode`, `/api/Work/Remux`, `/api/Work/Audio` all return HTTP 200.
- C33j. Contract test `Tests/Contract/TestWorkBucketGeneratedColumn.py` asserts the DB-side generated expression matches the C33 CASE. Compliant/Unclassified appear in `Domain/BucketKey.py` `_REGISTRY`.
- C33k. Contract test `Tests/Contract/TestSelfHealingPurged.py` asserts `Features/AudioNormalization/SelfHealing/` directory does not exist and no production-tree reference remains.
- C33l. WebService restart verified live -- no `AudioVerticalHealth` log line at startup.

**C34. Non-video containers never enter Transcode work.** WorkBucket classifier + admission gate refuse to route audio-only containers into `WorkBucket IN ('Transcode','Remux','AudioFix')`. Rule: files where `ContainerFormat IN ('mp3','flac','ogg','wav','aac','m4a','opus','dsf','dff','ape','wma')` OR (`Codec='mjpeg' AND AudioCodec IS NOT NULL AND ContainerFormat NOT IN ('matroska,webm','mov,mp4,m4a,3gp,3g2,mj2','avi'...)`) are classified `Unclassified` with `AdmissionDeferReason='non_video_container'`. Deleted, not annotated: any code branch that treats attached-picture `mjpeg` streams as video work. CommandBuilder raises `NonVideoSourceError` (fail-loud) if it receives such a MediaFile -- no defensive short-circuit. Retirement: existing 251 `WorkBucket='Transcode'` mp3 rows re-classified in the same commit as the classifier fix. Verification: `SELECT COUNT(*) FROM MediaFiles WHERE ContainerFormat IN ('mp3','flac','ogg','wav','aac','m4a','opus','dsf','dff') AND WorkBucket IN ('Transcode','Remux','AudioFix')` returns 0. Contract test `Tests/Contract/TestNonVideoContainersExcluded.py`. Live smoke: rescan the Crazy-Ex-Girlfriend soundtrack `Extras/Soundtrack/**/*.mp3` root -- every row lands `WorkBucket <> 'Transcode'` on first classification. Root failures retired: A1 (`Could not find tag for codec av1` NVENC, 183 attempts), A2 (`Current frame rate is unsupported` QSV, 68 attempts).

**C35. TranscodeAttempts.MediaFileId is immutable post-INSERT.** Once a `TranscodeAttempts` row is written, its `MediaFileId` column may never be UPDATE'd. Post-encode replacement (`transcode.flow.md ST8/ST9 ProcessFileReplacement`) writes a NEW MediaFile row for the transcoded output; historical attempt rows on the source's MediaFileId are preserved as-is because the source row transitions via `MediaFilesArchive`, not via mutation. Migration `Scripts/SQLScripts/EnforceTranscodeAttemptMediaFileIdImmutable_2026_07_23.py` adds BEFORE UPDATE trigger raising `EXCEPTION 'TranscodeAttempts.MediaFileId immutable'` if `NEW.MediaFileId IS DISTINCT FROM OLD.MediaFileId`. No `# fail-loud-ok:` override. Root-cause null-write path (site that produced attempt 47505 -- `null value in column "mediafileid" of relation "transcodeattempts"`) DELETED, not caught. Contract test `Tests/Contract/TestTranscodeAttemptMediaFileIdImmutable.py`: INSERT ok, UPDATE to NULL raises, UPDATE to different value raises. Live smoke: replay one replacement transcode (Heroes S01E03 = MediaFileId 694374) end-to-end; verify Success=TRUE + no trigger violation.

**C36. Every Success=FALSE attempt carries a captured ffmpeg tail.** `TranscodeAttempts.ErrorMessage` is NOT NULL for `Success=FALSE` rows via CHECK constraint added by migration `Scripts/SQLScripts/EnforceFailureHasErrorMessage_2026_07_23.py` (`CHECK (Success IS NOT FALSE OR (ErrorMessage IS NOT NULL AND length(ErrorMessage) >= 200))`). Worker captures ffmpeg stderr through a streaming rolling buffer (`collections.deque(maxlen=N)`) sized for the last ≥50 lines, and dumps the buffer verbatim into ErrorMessage on any non-zero exit. Empty-tail write path (root cause of return-code-222 attempts, 16 rows) deleted. No `try/except` around the write suppresses the CHECK violation -- it fail-louds up to the worker main loop. Contract test `Tests/Contract/TestFailedAttemptsCarryTail.py` asserts `SELECT COUNT(*) FROM TranscodeAttempts WHERE Success=FALSE AND (ErrorMessage IS NULL OR length(ErrorMessage) < 200)` returns 0 for rows written after cutover. Backfill script marks pre-cutover empty-tail rows as `capture_missing` disposition, one-shot.

**C37. Admission-time probe covers every stream.** No file is written to any Transcode/Remux/AudioFix `WorkBucket` if `ffprobe` reports `Could not find codec parameters` on ANY declared stream, or if any stream lacks a resolvable `codec_type`/`codec_name`. Admission-time probe (`Features/FileScanning/ProbeService`) reads every stream index; the count matches `nb_streams`. Unprobable file → `WorkBucket='Unclassified'` with `AdmissionDeferReason='probe_incomplete'` and the stream index recorded. Downstream (CommandBuilder, transcode workers) may assume all referenced streams are fully probed and refuse (`AssertionError`) if any assumption is violated. Retirement of return-code-4294967262 class (attempt 47010 = 5 hdmv_pgs_subtitle streams with `unspecified size`). Contract test `Tests/Contract/TestAdmissionProbeExhaustive.py` synthesizes an mkv with an unprobable pgs subtitle stream, feeds to admission, asserts `WorkBucket='Unclassified'`.

**C38. CommandBuilder raises typed structured exceptions with the missing input.** All build-command failure paths in `Features/TranscodeJob/CommandBuilder/**/*.py` raise typed exceptions (`ProfileFieldMissingError('AudioBitrate')`, `StreamMapEmptyError`, `MediaFileFieldMissingError('Codec')`, ...) whose `str()` includes: the missing field name, the MediaFileId, the ProcessingMode, and the Plan step the build was on. The generic string `Failed to build Transcode command` is deleted from every write site + every log call. Worker error handler serializes the exception message + traceback verbatim into ErrorMessage (C36 CHECK forces non-empty). Contract test `Tests/Contract/TestCommandBuilderExceptionShape.py` asserts every raise in the CommandBuilder package uses one of the typed classes AND grep `Failed to build Transcode command` in the production tree returns 0.

**C39. Worker drain-before-stop is the only graceful exit path.** `WorkerService/Main.py` SIGTERM/SIGINT handler flips `Workers.Status='Paused'` (DB, per `db-is-authority.md`), then blocks on `ActiveJobs` for that WorkerName until the in-flight transcode reaches its natural end (Success=TRUE or Success=FALSE with real ffmpeg tail), then exits with code 0. Interrupted attempts do NOT get `Success=FALSE` written by the exiting worker -- if the ffmpeg process is still running, the worker waits; if the worker was force-killed by the OS, heartbeat expiry via `AttemptAbandonmentSweeper` writes `owner_abandoned` per `.claude/rules/claim-authority.md`. The string `worker crashed/restarted` is deleted from every production-tree write site (22 attempts under this banner in last 7 days -- root cause was mid-encode Stop-Process bypassing drain, per memory rule `feedback_worker_restart_protocol`). Contract test `Tests/Contract/TestNoCrashRestartWrite.py` greps production tree for the literal `worker crashed/restarted` and asserts 0 matches. Live smoke: attempt-in-flight → `Stop-Process` on worker parent -> sweeper marks `owner_abandoned` after heartbeat window (5min), never `worker crashed/restarted`.

**C41. Deterministic worker identity + DB-authoritative per-worker concurrency.** Two-part fix for the recurring "N processes claim same WorkerName → N-way MaxConcurrentJobs violation" class:

**Part A -- Deterministic identity.** WorkerName is deploy-assigned via `MEDIAVORTEX_WORKER_NAME` env var, sourced from systemd `EnvironmentFile=/etc/mediavortex/instance-%i.env` per bare-metal instance OR docker compose per service. No runtime slot-claim. No advisory locks. No heartbeat-staleness reclaim. No prefix. No hostname fallback. `_GetWorkerName` fail-louds if `MEDIAVORTEX_WORKER_NAME` unset. Deleted: `_ClaimPrefixedWorkerName` (WorkerService/Main.py), `MEDIAVORTEX_WORKER_PREFIX` env, `/etc/mediavortex/worker-prefix.env`, `StepAgeSlotHeartbeats`, `StepStartInstances` sleep-3 serialization dance, `socket.gethostname()` fallback.

**Part B -- DB-authoritative concurrency.** Claim SQL refuses when worker already holds `>= MaxConcurrentJobs` in-flight rows. New helper `Core.Database.WorkerCapabilityPredicate.BuildInflightCapPredicate(WorkerName, JobType)` emits the guard. Transcode: `TranscodeAttempts WHERE Success IS NULL AND WorkerName=?`, cap `Workers.MaxConcurrentJobs`. QT: `QualityTestingQueue WHERE Status='Running' AND ClaimedBy=?`, cap `Workers.MaxConcurrentQualityTestJobs`. Client-side `BoundedSemaphore` in `WorkerLoopService` retained as belt-and-suspenders rate-limiter (prevents thread explosion when DB says no); DB is the authority.

**Files:**
- `WorkerService/Main.py` -- EDIT (delete `_ClaimPrefixedWorkerName`, simplify `_ResolveWorkerName` to fail-loud on missing env; drop `EscapeLikePattern` + advisory-lock imports)
- `Core/Database/WorkerCapabilityPredicate.py` -- EDIT (add `BuildInflightCapPredicate`)
- `Features/TranscodeQueue/TranscodeQueueRepository.py` -- EDIT (`ClaimNextPendingJob` adds `BuildInflightCapPredicate`)
- `Features/QualityTesting/QualityTestRepository.py` -- EDIT (`ClaimQualityTestJob` adds `BuildInflightCapPredicate`)
- `deploy/baremetal/mediavortex-worker@.service` -- EDIT (`EnvironmentFile=/etc/mediavortex/instance-%i.env`; drop worker-prefix.env)
- `deploy/deploy-baremetal-worker.py` -- EDIT (`StepInstallSystemdUnit` writes per-instance env files; DELETE `StepAgeSlotHeartbeats`; `StepStartInstances` drops sleep-3; add cleanup `rm -f /etc/mediavortex/worker-prefix.env`; renumber steps)
- `deploy/compose-templates/larry.yml` -- EDIT (`MEDIAVORTEX_WORKER_NAME: <name>` per service)
- `.claude/rules/claim-authority.md` -- EDIT (add worker-identity section + per-worker concurrency invariant)
- `deploy/worker-deploy.feature.md` -- EDIT (add criterion for deterministic identity + DB-authoritative concurrency)
- `deploy/worker-deploy-baremetal.flow.md` -- EDIT (rewrite identity narrative; drop prefix-claim prose)
- `Tests/Contract/TestClaimAuthority.py` -- EDIT (add per-worker concurrency test)
- `Tests/Contract/TestDeployIdempotenceInvariants.py` -- EDIT (grep-fence: no `_ClaimPrefixedWorkerName`, no `MEDIAVORTEX_WORKER_PREFIX`, no `worker-prefix.env`, no `socket.gethostname()` in WorkerService, no `StepAgeSlotHeartbeats`)

**Verification:**
- Contract tests green.
- Grep `_ClaimPrefixedWorkerName|MEDIAVORTEX_WORKER_PREFIX|worker-prefix\.env|StepAgeSlotHeartbeats` in production tree returns 0.
- Live: redeploy dot + wakko. Verify `SELECT COUNT(DISTINCT ProcessId) FROM ActiveJobs WHERE WorkerName=? AND Status='Running'` = 1 per WorkerName. Verify `SELECT COUNT(*) FROM TranscodeAttempts WHERE WorkerName=? AND Success IS NULL` <= `Workers.MaxConcurrentJobs` for every worker.
- Regression: `Tests/Contract/TestClaimAuthority.py` + `TestAbandonmentSweeper.py` + `TestDeployIdempotenceInvariants.py` all PASS.

**C40. Domain + feature-flow docs, comments, and unused code purged.** Sweep across the entire `Features/*/Domain/` tree AND every colocated `*.feature.md` + `*.flow.md`:
- Every module docstring, class docstring, function docstring deleted from `Features/*/Domain/**/*.py`. Domain code carries no explanatory prose -- identifiers do the talking.
- Every `#` inline comment deleted UNLESS it names a non-obvious WHY (hidden constraint / subtle invariant / external-quirk workaround). Comments that restate WHAT the code does = deleted.
- Every unreferenced import, unreferenced constant, orphan helper, dead branch removed from `Features/*/Domain/**/*.py`. Verified via `vulture Features/*/Domain --min-confidence 100` returning empty.
- Every `*.feature.md` + `*.flow.md` reviewed for annotation lines (`historical`, `formerly`, `legacy`, `previously`, `superseded`, `deprecated`, `removed 20`, `no longer used`); annotations deleted (not the surrounding content -- if the surrounding content is stale, delete THAT and let the doc get shorter). R14 hook already enforces going forward; C40 makes the tree conform NOW.

Verification:
- Contract test `Tests/Contract/TestDomainNoDocstrings.py` greps every `Features/*/Domain/**/*.py` file for `"""` and `'''`; asserts count == 0.
- Contract test `Tests/Contract/TestFeatureFlowNoAnnotations.py` greps every `Features/**/*.feature.md` + `Features/**/*.flow.md` + `**/*.flow.md` at repo root for the annotation vocabulary; asserts count == 0 outside `GLOSSARY.md`.
- `vulture Features/*/Domain --min-confidence 100` returns empty.
- Byte-count delta reported per touched file in `### Verification`.

Constraint: this criterion is a sweep, not a refactor. Zero behavior change -- identifiers, function bodies, class shapes preserved. Only docs/comments/unused-symbols removed.

**C42. Video compliance is bitrate-driven (per-resolution multiplier over Tier 1); codec allowlist retired.** Implements DOMAIN.md 2026-07-26 "Video compliance is bitrate-driven (codec allowlist retired)" + operator-tunable multipliers via `/settings` GUI.

**Blocked until Q1-Q4 in `DOMAIN.md#open-domain-questions-2026-07-26` answered.** Do not start implementation until those four answers are recorded in DOMAIN.md. Session hand-off point: operator answers -> record in DOMAIN.md -> proceed to Files.

**Shape (post-Q-answers):**
- New table `VideoComplianceThresholds(Id SERIAL PK, ResolutionCategory TEXT UNIQUE, Tier1Multiplier NUMERIC(4,2) NOT NULL CHECK > 0, LastUpdated TIMESTAMP DEFAULT NOW())`.
- Seed 4 rows: `('480p', 1.5)`, `('720p', 2.0)`, `('1080p', 2.0)`, `('2160p', 3.0)`.
- `VideoVertical.Evaluate` reads multiplier fresh per call, applies `SourceKbps > Tier1TargetKbps * Multiplier` as the sole video-compliance signal. Codec check retired.
- `VideoComplianceRules.acceptablevideocodecscsv` column dropped from schema + all read sites deleted (Q1 may add a small `UnsupportedVideoCodecs` blocklist if operator chooses option (b)).
- `/settings` Transcoding card gains "Video Compliance" subsection: 4-row grid (Resolution | Multiplier | Effective floor auto-computed). PUT persists via existing `/api/SystemSettings/Transcoding`.
- Reclassify path per Q3 answer.

**Files (line-level filled at NEEDS_DOC_PREREAD after Q-answers):**
```
Scripts/SQLScripts/AddVideoComplianceThresholds_2026_07_26.py            -- CREATE (table + seed)
Scripts/SQLScripts/DropAcceptableVideoCodecsCsv_2026_07_26.py            -- CREATE (drops old singleton column)
Features/VideoEncoding/VideoComplianceThresholdsRepository.py            -- CREATE (GetMultiplier + UpdateMultiplier; fail-loud on missing row)
Features/VideoEncoding/VideoVertical.py                                  -- EDIT (multiplier applied; codec check removed)
Features/VideoEncoding/video-encoding.feature.md                         -- EDIT (compliance narrative rewritten; codec-allowlist removed; multiplier documented)
Features/SystemSettings/SystemSettingsController.py                      -- EDIT (GET/PUT extended with multipliers section)
Templates/Settings.html                                                  -- EDIT (Video Compliance subsection)
Static/settings.js                                                       -- EDIT (form handler)
Tests/Contract/TestVideoComplianceMultiplier.py                          -- CREATE (boundary tests: 1.4x compliant, 1.6x non-compliant @480p multiplier=1.5)
Tests/Contract/TestTranscodingSettingsRoundTrip.py                       -- EDIT (round-trip multipliers section)
Tests/Contract/TestNoLegacyResidue.py                                    -- EDIT (grep-fence acceptablevideocodecscsv = 0)
Scripts/RecomputeWorkBuckets.py                                          -- CREATE OR SKIP depending on Q3 answer (a/b/c)
Features/WorkBucket/work-bucket.feature.md                               -- EDIT (compliance-multiplier reference)
```

**Verification:**
- Contract tests green (TestVideoComplianceMultiplier + TestTranscodingSettingsRoundTrip + TestNoLegacyResidue).
- Grep `acceptablevideocodecscsv` in production tree = 0.
- Live: `SELECT WorkBucket, COUNT(*) FROM MediaFiles GROUP BY WorkBucket` shows `Transcode` count dropped significantly (1,922 mpeg4 files + N small-source files); `Remux` + `AudioFix` counts grew correspondingly.
- Operator sees `/Work/Transcode` shrink, `/Work/Remux` + `/Work/Audio` grow, `/settings` shows the 4-row multiplier grid.
- Round-trip edit test: change 480p multiplier from 1.5 to 1.6 via GUI PUT; next classifier call uses 1.6 immediately (db-authority).

## Out of Scope

Every item tagged (a) or (b) per `call-graph-audit.md` Signal 4. Default (a) = behavior preserved + duplication collapsed in-flight.

- **(a) TranscodeJob -> MediaJob umbrella rename** -- logged as idea `IDEAS.md:8` (2026-07-03). Umbrella name stays `Transcode*` for this directive. Two-sense ambiguity documented in `GLOSSARY.md` (C0b) as transition cost until the rename directive lands. Not silent debt: ambiguity is named + follow-up path exists.
- **(a) VMAF-skip Verification Policy sub-vertical** -- follow-up directive after canonical closes. Adding it now would fold a new feature into a structural directive.
- **(a) Canary profile renames** -- data cleanup on `Profiles` rows. Follow-up directive.
- **(a) BUG-0072 / BUG-0070 audio-bitrate damage backfill** -- historical file recovery, separate directive.
- **(a) audio-normalization.flow.md sub-flow-vs-fold decision** -- keeps as sub-flow if decision resolves that way at reset step 5. If folded into transcode.flow.md, the fold is part of this directive.
- **(b) Historical `TranscodeAttempts` migration** -- pre-cutover rows keep NULL values for columns that were never populated. Only new attempts get the populated shape. C5's SQL audit is scoped `WHERE completeddate > <cutover>` for this reason. Duplication of old attempt shape survives.
- **(b) Scanner auto-enqueue scheduling redesign** -- scanner's higher-level scheduling / prioritization is untouched. C2 requires scanner to write the same column set at admission, not to change how it decides what to scan.

## Constraints

- Template Method + Strategy throughout. One `JobProcessor` base owns orchestration; strategies own encode + verify.
- Behavior-preserving where possible. New behavior only where a criterion explicitly requires (C6 no-bypass, C7 fail-loud, BUG fixes).
- Schema migrations: rename-then-drop pattern per closed transcode-worker-unification convention.
- Push every commit on main (memory rule `feedback_push_after_commit`).
- Live smoke per code step per memory rule `feedback_smoke_test_per_step_not_at_end`. Not "tests green" -- live verification on target hardware.
- R12: single-line comments/docstrings only.
- R14: cross-vertical doc sweep deletes obsolete references, no annotation lines.
- `.claude/rules/fail-loud.md` lands as pre-step (reset 4) BEFORE the code sweep so grep-based enforcement exists.
- **No-legacy invariant (all resets 10+):** every reset that replaces behavior deletes the code AND documentation of the prior behavior in the same commit. No commented-out old code. No "removed YYYY-MM-DD" / "deprecated" / "legacy" / "previously" annotations. No dormant helper functions that no caller invokes. No feature-doc paragraphs describing behavior the code no longer performs. Enforcement: contract test `Tests/Contract/TestNoLegacyResidue.py` (Reset 10 CREATE, extended each reset) greps production code + active docs for the retired symbols/columns/reasons the reset removes; count > 0 outside migration + tests + KNOWN-ISSUES-ARCHIVE = fail. Applies to columns `SourceBitratePercent` / `MinBitrateKbps` / `MaxBitrateKbps` (Reset 10), disposition literals `NoReplace` / `Discard` (already enforced by TestDispositionEnumClosed), profile-name string prefixes for deleted non-CANARY profiles (Reset 10), etc. Each reset extends the grep list before merge.

## Escalation Defaults

- Tradeoff between behavior-preserving rigor and architectural cleanliness -> cleanliness, provided four live smokes (C9) pass.
- Risk tolerance: low. Pipeline is operator-critical; regressions block production.
- Worker restart authority: full on I9 per memory (`feedback_i9_worker_is_active_codebase` + `feedback_worker_restart_protocol`).
- Schema DROP authority: operator owns destructive DROP; directive authors migrations but does not run destructive phase.

## Engineering Calls Already Made

- Slug `transcode-flow-canonical` (operator-locked).
- Umbrella name stays `Transcode*`; MediaJob rename deferred (IDEAS.md).
- StreamCopy strategy's Verify returns a checksum result (video stream bit-identical). No new `VerifyMethod` column added -- keep `Vmaf` semantically overloaded (StreamCopy writes `100.0` on match, `Vmaf` semantically-verify-score). Alternative deferred to VMAF-skip follow-up directive.
- Session reset is discipline, not mechanism: commit + push + Resume Marker + `/clear` between numbered steps.
- **Audio-normalization.flow.md CONFIRMED as legitimate carve-out** (preread synthesis 2026-07-03). Every ProcessingMode (Transcode/Remux/AudioFix/Quick/SubtitleFix/TestVariant) converges on its ST1-ST7 audio pipeline. NOT folded into transcode.flow.md. Reset 5 preserves it.
- **transcode.flow.md ST1-ST9 numbering preserved** (preread synthesis). Existing 9 stages (`SCAN->PROBE->ASSIGN->RECOMPUTE->QUEUE->TRANSCODE->DISPOSITION->VMAF->ACTION`) are stable per `.claude/rules/flow-docs.md`. Reset 5 adds Strategy-variant subsections at ST6+ST7 instead of renumbering to 10-stage.
- **Strategies + JobProcessorRegistry already exist** at `Features/TranscodeJob/Worker/Strategies/` (5 strategies + interface + registry per transcode-worker-unification). C1 structural landed prior. Remaining C4 work = delete surviving 9+ mode-branches Signal 2 named + wire StreamCopy verify hook.
- **BUG-0075 partial**: `Success=FALSE` on freeze already fixed in code at `StuckJobDetectionService.py:472,1029`. C7 remaining scope = QT admission refuses freeze-marker rows.

## Reset Plan

| # | Step | Exit gate | Reset |
|---|---|---|---|
| 0 | NEEDS_STANDARDS_REVIEW: read every rule; run 5-signal Call-Graph Audit. **DONE** (see above). | Audit sections populated. | **DONE** |
| 1 | NEEDS_PLAN: criteria + Files + Reset Plan + Constraints + OOS drafted; operator approval required before advance. | Sections populated. Operator approves criteria. | **RESET 1** (this reset) |
| 2 | NEEDS_DOC_PREREAD: Read every colocated `*.feature.md` / `*.flow.md` for files in `### Files`. Then advance to IMPLEMENTING. | All doc-prereads done per R1. | (no reset -- transition to IMPLEMENTING) |
| 3 | C0a: shrink ARCHITECTURE.md to MAP tier. Column-list bleed migrated (opportunistic on files this directive touches). Add `## Job Types` section. Rewrite Transcode/Remux mentions. Re-audit `## Gap to Target`. Promotions rows added incrementally. | `wc -l ARCHITECTURE.md` <= 130; Job Types section present. | **RESET 2** |
| 4 | C0b: create GLOSSARY.md; populate four buckets; reference from CLAUDE.md; add tier entry to `.claude/rules/doc-layering.md`. | GLOSSARY.md exists; alphabetical per bucket. | **RESET 3** |
| 5 | C7 pre-step: create `.claude/rules/fail-loud.md` + `.claude/rules-details/fail-loud.md`. | Rule file present. | **RESET 4** |
| 6 | C1 + C8 doc surgery: rewrite `transcode.flow.md` to 10-stage + Strategy shape. Decide audio-normalization.flow.md sub-flow-vs-fold and act. Create `quality-test.flow.md`. Add "one flow per pipeline shape" invariant to `.claude/rules/flow-docs.md`. Delete violated sections (no annotations). | Flow docs match target; new invariant present. | **RESET 5** |
| 7 | C2 code: collapse enqueue routes; fix BUG-0078 (ForceAdd insert on VMAF>=80). Contract test green. Live smoke (a) web GUI enqueue -> Reencode -> Replace. | Contract test green; smoke (a) TranscodeAttempts row recorded. | **RESET 6** |
| 8 | C3 + C4 code: collapse claim + orchestration. Route through Strategy. Delete the 9+ mode-branches Signal 2 named. Live smoke (b) web GUI enqueue -> StreamCopy -> Replace. | `TestClaimAuthority` full-green; mode-branch grep = 0; smoke (b) recorded. | **RESET 7** |
| 9 | C5 code: populate shared columns for every strategy. Extend `PostEncodeMeasurementService` for StreamCopy path. Live smoke (c) scanner auto-enqueue -> Replace. | Shared-columns SQL audit green (100% per column per strategy for new rows); smoke (c) recorded. | **RESET 8** |
| 10 | C6 code: delete BypassReplace. StreamCopy emits checksum. Fix BUG-0079 (Requeue inserts new queue row). Live smoke (d) Requeue -> new row -> Replace. | `SELECT DISTINCT disposition` returns subset {Replace,Reject,Requeue}; smoke (d) recorded. | **RESET 9** |
| 11 | C12 + C13 + C14 + C16 + C17 backend: Profile tier-ladder schema + migrate + delete non-CANARY profiles + collapse Emit layer into CommandComposer + 4 slots (VideoSlot/AudioSlot/SubtitleSlot/ContainerSlot) + delete EncodeShapeRegistry + 3 Shape classes + rewrite encoder-args strategies as VideoSlot Reencode variants + admission-adequacy gate + smart VMAF sampling + global-off restore. **No-legacy sweep:** delete `SourceBitratePercent` / `MinBitrateKbps` / `MaxBitrateKbps` from Profiles code AND doc references; delete `TranscodeShape.py` / `RemuxShape.py` / `SubtitleFixShape.py` / `EncodeShape.py` / `EncodeShapeRegistry.py` + doc references + tests referencing them; delete legacy `RateControlMode`-branched AdjustmentRegistry code + doc mentions; delete old profile-name literals from tests + scripts. `TestNoLegacyResidue.py` CREATE. Contract tests + live smokes: (a) compact-source excluded, (b) tier escalation on VMAF-fail terminates, (c) smart-skip after N passes, (d) global-off auto-Replace, (e) Reencode subtitle preservation (text subs -> mov_text), (f) StreamCopy subtitle preservation, (g) image-sub drop-with-WARN. | Schema migration executed; TestProfileTierLadder + TestAdequacyGate + TestSmartConfidenceSkip + TestCommandComposer + TestNoLegacyResidue green; seven backend smokes recorded; grep of retired symbols (SourceBitratePercent, EncodeShapeRegistry, `Shape\(`, MinBitrateKbps, MaxBitrateKbps) in production tree = 0; Workers.TranscodeEnabled un-paused only after subtitle-preservation smokes pass. | **RESET 10** |
| 12 | C15 GUI: `/settings` Transcoding card wiring bitrate ladder + ICQ ladder + adequacy toggle + VMAF confidence knobs + global QualityTestEnabled + VmafConfidenceStats review. `GET/PUT /api/SystemSettings/Transcoding`. Form-submit round-trip test. Live edit -> next Decider call reflects change. **No-legacy sweep:** delete any deprecated `/settings` field bindings + old form JS + legacy endpoint routes + docs of prior /settings shape. `TestNoLegacyResidue.py` extended with GUI patterns. | UI form saves persist round-trip; live-edit test green; TestNoLegacyResidue green. | **RESET 11** |
| 13 | C7 sweep: grep audit; remove silent fallbacks. Contract test `TestFailLoud` green. Fix BUG-0077 as instance (freeze -> Success=FALSE). **No-legacy sweep:** delete every `except: pass` / `or 0` / `or ''` / `if X is None: X = ...` pattern the audit surfaces AND their justifying comments; delete `# fail-loud-ok:` markers whose covered patterns were removed; delete doc paragraphs describing silent-fallback tolerances. | `TestFailLoud` + `TestNoLegacyResidue` green. | **RESET 12** |
| 14 | VERIFYING: run every criterion's verification, record evidence in `### Verification`. Four live smokes documented. Directive size snapshot. | Criteria all IMPLEMENTED with evidence; snapshot recorded. | **RESET 13** |
| 15 | DELIVERING draft 1: `### Promotions` populated; 5 parked feature/flow files created; delivery report drafted; BUG-0085 filed; row 41107 + 41124 + 41125 backfilled; BUG-0086 fix landed inline. Directive REOPENED at operator direction 2026-07-05 -- outcome not met while VMAF systematically wrong. | Draft delivery report present; directive stays open. | **RESET 14** |
| 16 | C19 deploy hardening: Dockerfile `__pycache__` purge + `deploy-linux-worker.py` post-deploy stale-pyc probe. Live smoke: re-deploy all 12 Linux workers. Activates BUG-0086 fix cleanly. | `TestDeployStalePycProbe` green; live re-deploy log; fresh Wakko attempt has probe-populated attestation columns (not backfill). | **RESET 15** |
| 17 | C20 WorkerContext thread-local binding: `Core/WorkerContext.py` rewrite + `Bind()` at every processing-thread entry (JobProcessor + ProcessQualityTestQueueService); `Current()` raises `WorkerContextNotBoundError` on unbound. `PostEncodeMeasurementService.Probe` reverts to strict-mode (defensive backfill remains as belt-and-suspenders). | `TestWorkerContextThreadLocal` + `TestProbeStrictModeWhenContextBound` green; live Wakko QSV Requeue attempt has apr='resolved' (not 'unresolved'). | **RESET 16** |
| 18 | C18 core: `AlignmentSpec` VO + `VmafAlignmentProbe` domain service + `ColorSpaceService` cross-cutting. Unit tests: invariants + fail-loud on unparseable primaries / fps / duration-delta > 1 frame. | `TestAlignmentSpec` + `TestVmafAlignmentProbe` + `TestColorSpaceService` green. | **RESET 17** |
| 19 | C18 chain: `VmafFilterChainBuilder` (pure-fn stage composition) + `VmafModelSelector` (strategy) + `VmafCommandComposer` (thin shell). `QualityTestingBusinessService.BuildVMAFCommand` retires. `_BuildVmafFilterChain` folded into Builder. | `TestVmafFilterChainBuilder` + `TestVmafModelSelector` + `TestVmafCommandComposer` green. | **RESET 18** |
| 20 | C18 live smokes (a-j): 10 shape-diverse sources; each smoke records attempt id + VMAF score + axis-fired assertion. Fail-loud raises on unparseable / truncated / VFR-timeout. | All 10 smokes recorded in `### Verification`; axes 1-13 covered; no fallbacks fire. | **RESET 19** |
| 21 | VERIFYING re-run: 20 criteria (C0-C17 + C18/C19/C20) all IMPLEMENTED with evidence. Fresh directive size snapshot at re-entry to IMPLEMENTING (2026-07-05) becomes the C10 anchor for final ceiling check. | Every criterion IMPLEMENTED + evidence recorded. | **RESET 20** |
| 22 | DELIVERING final: `### Promotions` grown for C18/C19/C20 (new feature/flow docs promoted). Directive size ≤ 110% of Reset 15+ snapshot. Delivery report re-drafted with all 20 criteria + 10 VMAF smokes + deploy hardening + WorkerContext binding. Operator close. | Operator agrees closed. Directive file moved to `.claude/directives/closed/2026-07-XX-transcode-flow-canonical.md`. | **RESET 21** |

## Status

### Progress

- [x] NEEDS_STANDARDS_REVIEW: 5-signal audit run + populated
- [x] NEEDS_PLAN: criteria + Files + Reset Plan drafted; operator approved
- [x] NEEDS_DOC_PREREAD: pre-read all colocated docs for files in `### Files`
- [x] IMPLEMENTING: per-reset code work
- [x] VERIFYING: evidence-recording (Reset 13 stamp)
- [~] DELIVERING: initial draft landed Reset 14; REOPENED 2026-07-05 to absorb C18/C19/C20 (VMAF alignment + deploy hardening + WorkerContext binding) -- outcome not met without them (VMAF systematically wrong = pipeline decisions garbage; disposition trust broken; system useless per operator)
- [ ] REOPENED IMPLEMENTING: Reset 15+
- [x] REOPENED IMPLEMENTING: Reset 23 (C23 phantom QT ActiveJobs -- BUG-0087)
- [x] VERIFYING: Reset 23 evidence recorded
- [x] DELIVERING: Reset 23 Promotions row landed (2026-07-08)
- [x] DELIVERING: Reset 24 C24 deploy-time capability probe landed (2026-07-09)
- [ ] REOPENED IMPLEMENTING: Reset 25 (C25 Family-agnostic Profile + quality-label enqueue -- SPEC LANDED, implementation pending)
- [x] REOPENED IMPLEMENTING: Reset 25 core (migration LIVE + WorkerEncoderResolver + ClaimNext guard + ProcessTranscodeQueueService override wired)
- [x] REOPENED IMPLEMENTING: Reset 25 contract test suite (4 test files, 32 pass / 3 skipped for deferred endpoint)
- [x] REOPENED IMPLEMENTING: Reset 25 remainder (endpoint + GUI + classifier remap + animation rows + Linux redeploy + fanout smoke) -- 37 pass, 0 skip
- [x] REOPENED IMPLEMENTING: Reset 26 (C27 fail-loud Worker.Current + capability-thread Bind + defer QT/FileReplacement Worker capture -- BUG-0088)
- [x] VERIFYING: Reset 26 live smoke -- Wakko bare-metal VMAF end-to-end -- attempt 41322 Success=True Disposition=Replace VMAF=89.94 QTR 1406 Status=Success on wakko-worker-1 (av1_qsv + Demucs on Arc XPU + libopus 2-track + VMAF ffmpeg self-hosted). Pre-fix state (attempt 41316, QT queue row 2189) failed at `Resolve: no active StorageRoot for Id=1 on worker='client-b450m-01'`. Post-fix same file lands VMAF cleanly from wakko-worker-1.
- [x] DELIVERING: Reset 26 Promotions row landed (fail-loud Worker.Current + capability-poller Bind + naive-UTC advisory-claim TZ fix)
- [x] REOPENED IMPLEMENTING: Reset 27 (canonical claim: attempt row is the claim; DB UNIQUE partial index enforces one-in-flight-per-MediaFileId; single-TX atomic claim; owner-only writes; AttemptAbandonmentSweeper is the only cross-worker terminal path; cross-host stuck-detect deleted; doc surgery locks the shape)
- [x] VERIFYING: Reset 27 -- migration executed live (`ta_one_inflight_per_mfid` partial UNIQUE index present); 5/5 Reset 27 contract tests PASS; 26/26 regression PASS (TestClaimAuthority + TestWorkerContextThreadLocal); sweeper live-observed on I9 + wakko OrphanCleanup ticks; owner-scoped stuck-detect verified by SELECT-layer filter on `WorkerName`; cross-host guard branches deleted (moot after SELECT-layer filter)
- [x] DELIVERING: Reset 27 Promotions row landed (canonical claim rule + attempt-authoritative flow-doc surgery + sweeper + owner-scoped stuck-detect)
- [x] REOPENED IMPLEMENTING: Reset 33 (C33 classification completeness -- profile-independent verticals + Compliant/Unclassified buckets + self-heal subsystem deleted; docs-first per operator mandate)
- [ ] VERIFYING: Reset 33 -- core criteria (a-f, l-q) shipped in commit 9adcf50e; operator flagged criteria gap 2026-07-22 (cross-vertical doc claims + closed-directive anchor sweep + dead-code sweep + bucket ProcessingMode validity + UI adapter 5-branch coverage). Sharpened C33g-C33k added. Sweep in progress.
- [x] REOPENED IMPLEMENTING: Reset 34 (C34 non-video containers never enter Transcode -- audio-only scope predicate + vertical short-circuits + CommandComposer NonVideoSourceError guard + reclassify 251 mp3 rows).
- [x] REOPENED IMPLEMENTING: Reset 35 (C41 deterministic worker identity + DB-authoritative concurrency + git-preflight gate on deploy-fleet).
- [x] VERIFYING: Reset 35 -- commit b5b9a3a6 (C41 core) + 356943c5 (DOMAIN gates) + bc0d4ee5 (gitignore cleanup) pushed. TestClaimAuthority 22/22 + TestDeployIdempotenceInvariants 12/12 green. Live: `py deploy/deploy-fleet.py --hosts dot,wakko --no-drain --skip-local` succeeded; dot-1..4 + wakko-1..4 all on Version=bc0d4ee5, fresh HBs; I9-2024 restarted on bc0d4ee5. Zero duplicate ProcessIds per WorkerName. 4 DOMAIN.md entries recorded (identity deploy-assigned + per-worker concurrency DB-authoritative + fleet on HEAD + deploy requires committed+pushed).


### Reset 35 -- C41 deterministic worker identity + DB-authoritative concurrency

**Origin:** 2026-07-25 recurring "N processes claim same WorkerName -> N-way MaxConcurrentJobs violation" incident. Root cause: runtime slot-race in retired `_ClaimPrefixedWorkerName`. Post-Deco-DHCP reboot, 4 wakko processes read stale heartbeats within the advisory-lock window and all returned slot 1. `Workers.MaxConcurrentJobs=1` violated N-way per host. Prior patches (f67536b1 atomic INSERT-inside-lock, Reset 26 naive-UTC TZ fix, deploy-side aging + serialization) treated symptoms; identity was still computed at runtime.

**Shape.** Identity is deploy-assigned via `MEDIAVORTEX_WORKER_NAME`. Systemd `EnvironmentFile=/etc/mediavortex/instance-%i.env` (one file per instance, written by deploy) selects per systemd instance. Docker compose sets it per service. `_ResolveWorkerName` fail-louds if unset -- no prefix, no advisory-lock slot claim, no hostname fallback. Per-worker concurrency (`Workers.MaxConcurrentJobs`) lives in the DB via `BuildInflightCapPredicate` -- claim SQL refuses when in-flight count == cap. Client-side semaphore remains as rate-limit only.

**Files touched.**
- `WorkerService/Main.py` -- delete `_ClaimPrefixedWorkerName` + `EscapeLikePattern` + `socket` imports; `_ResolveWorkerName` becomes fail-loud env read.
- `Core/Database/WorkerCapabilityPredicate.py` -- add `BuildInflightCapPredicate(WorkerName, JobType)` + `_INFLIGHT_SHAPE` whitelist.
- `Features/TranscodeQueue/TranscodeQueueRepository.py` -- `ClaimNextPendingJob` adds InflightFragment.
- `Features/QualityTesting/QualityTestRepository.py` -- `ClaimQualityTestJob` adds InflightFragment.
- `deploy/baremetal/mediavortex-worker@.service` -- EnvironmentFile now instance-%i.env.
- `deploy/deploy-baremetal-worker.py` -- `StepInstallSystemdUnit` writes per-instance env files; `StepAgeSlotHeartbeats` DELETED; `StepStartInstances` drops sleep-3.
- `deploy/compose-templates/larry.yml` -- MEDIAVORTEX_WORKER_NAME per service.
- `deploy/deploy-fleet.py` -- pre-deploy gate refuses dirty tree or HEAD != origin/main.
- `StartParallelWorkers.py` -- launches each child with explicit MEDIAVORTEX_WORKER_NAME.
- `.claude/rules/claim-authority.md` -- adds worker-identity + per-worker concurrency sections.
- `deploy/worker-deploy.feature.md` C17 -- rewritten.
- `deploy/worker-deploy-baremetal.flow.md` ST4 -- rewritten.
- `DOMAIN.md` -- 4 entries (identity, concurrency, fleet-on-HEAD, deploy requires clean+pushed).
- `.gitignore` -- untrack startup.log.out + ignore root-level screenshots.
- `Tests/Contract/TestClaimAuthority.py` -- TestInflightCapPredicateHelper (3 tests) + TestTranscodeConcurrencyCapLive (live-DB refusal at cap boundary).
- `Tests/Contract/TestDeployIdempotenceInvariants.py` -- old atomic-reserve test REPLACED with TestDeterministicWorkerIdentity (grep-fences).

**Exit gate:** contract tests green; grep of retired symbols in production tree = 0; live deploy of dot + wakko lands both fleets on HEAD SHA; `SELECT COUNT(DISTINCT ProcessId)` per WorkerName = 1 post-restart under load.

### Reset 34 -- C34 non-video containers excluded

**Origin:** 2026-07-22 failure sweep: 183 NVENC + 68 QSV attempt-failures on 13 mp3-with-mjpeg-cover-art files across all three encoder families. 251 mp3 files sit in `WorkBucket='Transcode'` today because VideoVertical treats `Codec='mjpeg'` (attached picture stream) as a video codec and marks VideoCompliant=FALSE.

**Shape.** Positive scope predicate lives at `Features/MediaFile/Domain/MediaFileScope.py` -- `AUDIO_ONLY_CONTAINERS` frozenset + `IsAudioOnlyContainer(Mf)`. Three verticals short-circuit to `(None, 'non_video_scope')` before any rule load when the predicate fires. `CommandComposer.Build` raises `NonVideoSourceError` (subclass of `ValueError`) BEFORE its existing try block if a non-video MediaFile reaches it -- belt-and-suspenders behind the classifier gate. WorkBucket GENERATED column derives 'Unclassified' from NULL VideoCompliant, so no additional migration is needed.

**Files touched.**
- `Features/MediaFile/Domain/__init__.py` (new package)
- `Features/MediaFile/Domain/MediaFileScope.py` (new -- `AUDIO_ONLY_CONTAINERS` + `IsAudioOnlyContainer`)
- `Features/VideoEncoding/VideoVertical.py` (early return for audio-only)
- `Features/ContainerFormat/ContainerVertical.py` (early return for audio-only)
- `Features/AudioNormalization/AudioVertical.py` (early return for audio-only)
- `Features/TranscodeJob/Emit/CommandComposer.py` (`NonVideoSourceError` + pre-try guard)
- `Tests/Contract/TestNonVideoContainersExcluded.py` (new -- 8 tests, all green)
- `Scripts/SQLScripts/ReclassifyAudioOnlyContainers_2026_07_23.py` (new -- one-shot data-cleanup, sets three compliance columns NULL + reason='non_video_scope' where ContainerFormat in AUDIO_ONLY_CONTAINERS; prints before/after counts)


### Reset execution history (closed)

Reset 26 (C27 fail-loud Worker.Current + capability-thread Bind) + Reset 27 (C28 canonical claim -- attempt-authoritative + partial UNIQUE index + AttemptAbandonmentSweeper + owner-scoped stuck-detect) execution details archived at `.claude/directives/closed/2026-07-03-transcode-flow-canonical-archive.md`. See archive for root-cause narrative, file lists, and exit-gate evidence.

### R18 overrides

- deploy/worker-deploy.feature.md
- deploy/worker-deploy-linux.flow.md
- Features/TeamStatus/worker-versioning.feature.md
- Features/ServiceControl/graceful-drain.feature.md
- Features/TranscodeJob/local-staging.feature.md
- Features/TranscodeQueue/worker-routing.feature.md
- Features/FileScanning/FileScanning.feature.md
- Features/TeamStatus/worker-status-model.feature.md

### Files

Scoped per Reset Plan step. Deep file list (line-level) populated during NEEDS_DOC_PREREAD after reading colocated docs.

```
# Reset 2 -- ARCHITECTURE.md shrink
ARCHITECTURE.md                                                             -- EDIT (shrink to MAP tier + add Job Types section)
<vertical-feature-docs receiving Promoted column-list bleed>                 -- EDIT (opportunistic; per-vertical, filled at NEEDS_DOC_PREREAD)

# Reset 3 -- GLOSSARY.md
GLOSSARY.md                                                                 -- CREATE
CLAUDE.md                                                                   -- EDIT (add GLOSSARY.md to "Where everything lives")
.claude/rules/doc-layering.md                                               -- EDIT (add GLOSSARY tier row)

# Reset 4 -- fail-loud rule
.claude/rules/fail-loud.md                                                  -- CREATE
.claude/rules-details/fail-loud.md                                          -- CREATE

# Reset 5 -- flow-doc surgery
transcode.flow.md                                                           -- EDIT (rewrite to 10-stage + Strategy at ST5/ST8)
Features/QualityTesting/quality-test.flow.md                                -- CREATE
Features/FileScanning/FileScanning.flow.md                                  -- EDIT (verify canonical name; slug already scanning-related)
Features/AudioNormalization/audio-normalization.flow.md                     -- EDIT or DELETE (sub-flow vs fold decision)
.claude/rules/flow-docs.md                                                  -- EDIT (add "one flow per pipeline shape" invariant)
<feature docs with violated sections>                                       -- EDIT (delete violated sections; filled at NEEDS_DOC_PREREAD)

# Reset 6 -- C2 enqueue contract
Features/TranscodeQueue/QueueManagementBusinessService.py                   -- EDIT (single admission entry; ForceAdd fix)
Features/WorkBucket/Services/QueueAdmissionAppService.py                    -- EDIT (delegate through canonical path)
Features/TranscodeQueue/TranscodeQueueRepository.py                         -- EDIT (contract enforcement at INSERT)
Tests/Contract/TestEnqueueContract.py                                       -- CREATE
Features/TranscodeQueue/TranscodeQueue.feature.md                           -- EDIT (contract described)

# Reset 7 -- C3 + C4 claim + orchestration
Features/TranscodeJob/Worker/JobProcessor.py                                -- EDIT (Template Method, remove Mode == 'Transcode' at :110)
Features/TranscodeJob/Worker/Strategies/*.py                                -- EDIT (per-strategy hooks)
Features/TranscodeQueue/TranscodeQueueRepository.py                         -- EDIT (unified claim if not already)
Features/FileReplacement/TranscodedOutputPlacement.py                      -- EDIT (remove Mode == 'Transcode' at :83)
Features/Activity/Services/DashboardSnapshotService.py                     -- EDIT (remove ProcessingMode != 'Transcode' at :14)
Features/TranscodeQueue/QueueManagementBusinessService.py                   -- EDIT (remove 8 mode branches at :321-1969)
Core/Database/WorkerCapabilityPredicate.py                                  -- EDIT (only place with capability SQL)
Tests/Contract/TestNoModeBranchingAtOrchestration.py                        -- CREATE

# Reset 8 -- C5 shared columns
Features/TranscodeJob/Worker/JobProcessor.py                                -- EDIT (call PostEncodeMeasurementService per strategy)
Features/AudioNormalization/Services/PostEncodeMeasurementService.py       -- EDIT (extend to cover StreamCopy path)
Features/TranscodeJob/Worker/Strategies/*.py                                -- EDIT (each strategy writes AudioPolicyResolved + AudioPolicyJson)
Tests/Contract/TestSharedColumnsPopulated.py                                -- CREATE

# Reset 9 -- C6 no bypass + BUG-0079
Features/QualityTesting/Disposition/*.py                                    -- EDIT (StreamCopy -> checksum; remove BypassReplace path)
Features/TranscodeQueue/QueueManagementBusinessService.py                   -- EDIT (Requeue disposition inserts new queue row)
Scripts/SQLScripts/DropBypassReplaceDisposition_2026_07_XX.py               -- CREATE (migration; retire enum value)
Tests/Contract/TestNoBypassReplace.py                                       -- CREATE

# Reset 10 -- C12 + C13 + C14 + C16 + C17 profile tier ladder + adequacy + smart sampling + global-off restore + Emit slot collapse + subtitle preservation (BUG-0083)
Scripts/SQLScripts/AlignProfileTierModel_2026_07_XX.py                      -- CREATE (schema: Profiles.Family/QualityTier/ContentClass; ProfileThresholds.TargetKbps/IcqQ; drop SourceBitratePercent/MinBitrateKbps/MaxBitrateKbps; VmafConfidenceStats table; PostTranscodeGateConfig new cols)
Scripts/SQLScripts/BackfillCanaryTierLadder_2026_07_XX.py                   -- CREATE (populate two families x 4 resolutions x 5 tiers x live-action rows; ProfileThresholds.TargetKbps + IcqQ)
Scripts/SQLScripts/DeleteNonCanaryProfiles_2026_07_XX.py                    -- CREATE (delete AV1 profiles outside CANARY families; reassign MediaFiles.AssignedProfile via ContentClassifier)
Features/Profiles/EncoderKnobRepository.py                                  -- EDIT (return TargetKbps + IcqQ; drop dead-column pass-through)
Features/TranscodeJob/Emit/CommandComposer.py                              -- CREATE (single Build(Job, MediaFile, Plan) -> ffmpeg argv; composes 4 slots)
Features/TranscodeJob/Emit/Slots/VideoSlot.py                              -- CREATE (Reencode variants per Family: NvencVbr, QsvIcq; StreamCopy variant)
Features/TranscodeJob/Emit/Slots/AudioSlot.py                              -- CREATE (2-track Original + DialogBoost; StreamCopy variant)
Features/TranscodeJob/Emit/Slots/SubtitleSlot.py                           -- CREATE (ALWAYS fires: MP4 target -> `-map 0:s? -c:s mov_text`; MKV target -> `-map 0:s? -c:s copy`; PGS/DVB -> WARN drop; fixes BUG-0083)
Features/TranscodeJob/Emit/Slots/ContainerSlot.py                          -- CREATE (container-format change/preserve)
Features/TranscodeJob/Emit/TranscodeShape.py                               -- DELETE (folded into CommandComposer)
Features/TranscodeJob/Emit/RemuxShape.py                                   -- DELETE
Features/TranscodeJob/Emit/SubtitleFixShape.py                             -- DELETE
Features/TranscodeJob/Emit/EncodeShape.py                                  -- DELETE (abstract base retired)
Features/TranscodeJob/Emit/EncodeShapeRegistry.py                          -- DELETE (mode-branching registry retired)
Features/TranscodeJob/Emit/EncoderArgsStrategies/NvencEncoderArgsStrategy.py -- DELETE (folded into VideoSlot.NvencVbrImpl)
Features/TranscodeJob/Emit/EncoderArgsStrategies/QsvEncoderArgsStrategy.py  -- DELETE (folded into VideoSlot.QsvIcqImpl)
Features/TranscodeJob/Worker/Strategies/*.py                              -- EDIT (BuildCommand delegates to CommandComposer; drops ProcessingMode-keyed Registry lookup)
Features/TranscodeQueue/AdequacyGate.py                                     -- CREATE (SourceKbps <= Tier1TargetKbps -> exclude; writes MediaFiles.AdequacyDecision)
Features/TranscodeQueue/QueueManagementBusinessService.py                   -- EDIT (call AdequacyGate at admission; short-circuit when excluded)
Features/QualityTesting/VmafConfidenceStatsRepository.py                    -- CREATE (bucket read/write; rolling window trim)
Features/QualityTesting/Disposition/PostTranscodeDispositionDecider.py     -- EDIT (add global-off short-circuit; add SmartConfidenceSkip branch)
Features/QualityTesting/QualityTestingBusinessService.py                   -- EDIT (call VmafConfidenceStatsRepository.RecordResult on VMAF completion)
Features/TranscodeJob/Adjustments/NextTierAdjustmentCalculator.py          -- CREATE (Profile -> next-tier Profile via UNIQUE tuple; None at ceiling)
Features/TranscodeJob/Adjustments/AdjustmentRegistry.py                    -- EDIT (single NextTierAdjuster; retire per-RateControlMode branch)
Features/ContentClassifier/*.py                                            -- EDIT (assign Family + ContentClass + Plan tuple on classification; use new UNIQUE tuple)
Tests/Contract/TestProfileTierLadder.py                                    -- CREATE
Tests/Contract/TestAdequacyGate.py                                         -- CREATE
Tests/Contract/TestSmartConfidenceSkip.py                                  -- CREATE
Tests/Contract/TestNextTierAdjuster.py                                     -- CREATE
Tests/Contract/TestCommandComposer.py                                     -- CREATE (all Plan combos; SubtitleSlot always fires; container-appropriate codec; image-sub drop-with-WARN)
Tests/Contract/TestNoLegacyResidue.py                                     -- CREATE (grep for retired symbols: SourceBitratePercent, EncodeShapeRegistry, TranscodeShape/RemuxShape/SubtitleFixShape/EncodeShape/NvencEncoderArgsStrategy/QsvEncoderArgsStrategy, MinBitrateKbps, MaxBitrateKbps)
Tests/Contract/TestDispositionDecider.py                                   -- EDIT (add test_global_off_returns_replace_qualitytestinggloballydisabled)

# Reset 11 -- C15 GUI transcoding card
Features/SystemSettings/SystemSettingsController.py                        -- EDIT (GET/PUT /api/SystemSettings/Transcoding)
Features/SystemSettings/Templates/settings.html                            -- EDIT (Transcoding card partial)
Features/SystemSettings/Static/settings.js                                 -- EDIT (form save + live-refresh probe)
Tests/Contract/TestTranscodingSettingsRoundTrip.py                         -- CREATE

# Reset 12 -- C7 sweep + BUG-0077
<production files with silent fallbacks>                                    -- EDIT (grep-driven; filled at IMPLEMENTING)
Features/ServiceControl/StuckJobDetectionService.py                         -- EDIT (Success=FALSE on freeze)
Features/QualityTesting/ProcessQualityTestQueueService.py                  -- EDIT (refuse freeze-marker admission)
Tests/Contract/TestFailLoud.py                                              -- CREATE

# ARCHITECTURE.md
ARCHITECTURE.md                                                             -- EDIT (already listed above at Reset 2; noted here for completeness)

# Reset 15 -- C19 deploy hardening (BUG-0085)
deploy/Dockerfile                                                           -- EDIT (add `RUN find /opt/mediavortex -name __pycache__ -type d -exec rm -rf {} +` post-COPY)
deploy/deploy-linux-worker.py                                               -- EDIT (post-deploy stale-pyc probe; fail-loud abort)
Tests/Contract/TestDeployStalePycProbe.py                                   -- CREATE (relocated from Tests/Deploy/ per R8)
# Reset 15 -- C21 phase-aware stuck-job detection
Features/ServiceControl/JobPhase.py                                         -- CREATE (JobPhase enum: Setup/Encoding/PostEncode/Verifying)
Scripts/SQLScripts/AddActiveJobsPhaseColumn_2026_07_05.py                   -- CREATE (idempotent migration; backfill Running rows to Encoding)
Features/ServiceControl/PhaseDetectors/IPhaseDetector.py                    -- CREATE (Detect(Job, ActiveJob) contract)
Features/ServiceControl/PhaseDetectors/SetupPhaseDetector.py                -- CREATE (elapsed vs SetupPhaseTimeoutMin default 30)
Features/ServiceControl/PhaseDetectors/EncodingPhaseDetector.py             -- CREATE (folds _IsJobFrozen + Tier 3 PID liveness)
Features/ServiceControl/PhaseDetectors/PostEncodePhaseDetector.py           -- CREATE (elapsed vs PostEncodePhaseTimeoutMin default 15)
Features/ServiceControl/PhaseDetectors/VerifyingPhaseDetector.py            -- CREATE (elapsed vs VerifyingPhaseTimeoutMin default 30)
Features/ServiceControl/PhaseDetectorRegistry.py                            -- CREATE (dict[JobPhase, IPhaseDetector] dispatch)
Features/ServiceControl/StuckJobDetectionService.py                         -- EDIT (IsJobStuck dispatches via registry; DELETE _IsJobFrozen + Tier 3 PID block)
Features/ServiceControl/ActiveJobRepository.py                              -- EDIT (SetActiveJobFFmpegPid Optional[int]; SetJobPhase / GetJobPhase; CreateActiveJob writes Phase='Setup')
Features/ServiceControl/ProcessInspector.py                                 -- CREATE (GetProcessName + IsFFmpegProcessName; used by EncodingPhaseDetector + cleanup)
Features/TranscodeJob/VideoTranscodingService.py                            -- EDIT (SetPhase Encoding before Popen, PostEncode after wait)
Features/TranscodeQueue/TranscodeQueueRepository.py                         -- EDIT (write Phase='Setup' at ActiveJob creation post-claim)
Features/QualityTesting/QualityTestingBusinessService.py                    -- EDIT (write Phase='Verifying' at QT claim)
Tests/Contract/TestJobPhaseTransitions.py                                   -- CREATE (each transition writes column + timestamp)
Tests/Contract/TestPhaseDetectors.py                                        -- CREATE (per-phase timeout + false-positive-guard)
Tests/Contract/TestStuckJobDetectionPhaseAware.py                           -- CREATE (registry dispatch by phase)
Features/TranscodeJob/Emit/Slots/VideoSlot.py                               -- EDIT (scope -global_quality to :v; libopus rejected unscoped)
Tests/Contract/TestStuckJobFrozenSetupPhase.py                              -- DELETE (bandaid superseded by phase model)

# Reset 16 -- C20 WorkerContext thread-local binding (BUG-0086 deep cause)
Core/WorkerContext.py                                                       -- EDIT (threading.local() backing; Bind + Current; raises WorkerContextNotBoundError)
Features/TranscodeJob/Worker/JobProcessor.py                                -- EDIT (Bind at processing-thread entry in Process())
Features/QualityTesting/ProcessQualityTestQueueService.py                   -- EDIT (Bind at daemon-thread entry in ProcessJob)
Features/AudioNormalization/Services/PostEncodeMeasurementService.py       -- EDIT (revert Probe to strict-mode; defensive DB attestation kept as belt-and-suspenders)
Tests/Contract/TestWorkerContextThreadLocal.py                              -- CREATE
Tests/Contract/TestProbeStrictModeWhenContextBound.py                       -- CREATE
Tests/Contract/TestPostEncodeMeasurementService.py                          -- EDIT (contract flips back: strict-mode assertions + defensive-write assertions coexist)

# Reset 17 -- C18 core (AlignmentSpec + Probe + ColorSpaceService)
Features/QualityTesting/Vmaf/AlignmentSpec.py                              -- CREATE (immutable VO; invariants raise on unparseable primaries / fps / duration-delta > 1 frame)
Features/QualityTesting/Vmaf/VmafAlignmentProbe.py                         -- CREATE (Probe(SourcePath, EncodedPath) -> AlignmentSpec)
Core/Media/ColorSpaceService.py                                            -- CREATE (color-triad + range + HDR detect + tone-map graph; fail-loud on unparseable)
Features/TranscodeJob/Emit/MediaProbeAdapter.py                            -- EDIT (extend for color-triad + fps + duration + chroma + bit depth reads)
Tests/Contract/TestAlignmentSpec.py                                        -- CREATE
Tests/Contract/TestVmafAlignmentProbe.py                                   -- CREATE
Tests/Contract/TestColorSpaceService.py                                    -- CREATE

# Reset 18 -- C18 chain (FilterChainBuilder + ModelSelector + Composer)
Features/QualityTesting/Vmaf/VmafFilterChainBuilder.py                     -- CREATE (9-stage pure-fn composition: setpts/deint/detelecine/fps/colorspace/crop/scale/chroma/libvmaf)
Features/QualityTesting/Vmaf/VmafModelSelector.py                          -- CREATE (VmafModel enum + Select(spec) -> VmafModel)
Features/QualityTesting/Vmaf/VmafCommandComposer.py                        -- CREATE (thin shell; -i pair + -ss + -lavfi injection + -f null + XML log path)
Features/QualityTesting/QualityTestingBusinessService.py                   -- EDIT (BuildVMAFCommand retires; delegates to VmafCommandComposer; RunVmaf orchestrates Probe -> Selector -> Builder -> Composer)
Features/QualityTesting/QualityTesting.feature.md                          -- EDIT (VMAF filter chain contract migrates from feature-doc invariant to VmafFilterChainBuilder tests; delete old ffprobe fallback wording)
Tests/Contract/TestVmafFilterChainBuilder.py                               -- CREATE
Tests/Contract/TestVmafModelSelector.py                                    -- CREATE
Tests/Contract/TestVmafCommandComposer.py                                  -- CREATE

# Reset 19 -- C18 live smokes (10 shape-diverse sources)
memory/smoke-assets.md                                                     -- EDIT (register 10 VMAF alignment smoke canaries: HDR 4K PQ, animation VFR, interlaced 1080i, telecined 24p, letterbox 2.35, phone 540p, truncated 30s, 4:2:2 source, unparseable primaries)
# Live-DB evidence only -- no code edits at Reset 19; directive Verification block accretes per-smoke rows.

# Reset 20+21 -- VERIFYING re-run + DELIVERING final -- directive doc only.

# Reset 23 -- C23 phantom QT ActiveJobs rows (BUG-0087)
Features/QualityTesting/QualityTestRepository.py                            -- EDIT (GetRunningQualityTestProgress add Status filter)
Features/QualityTesting/QualityTestController.py                            -- EDIT (BuildActiveJobsQuery arg QualityTest -> QualityTestService)
Features/ServiceControl/OrphanCleanupService.py                             -- EDIT (fix ServiceName literal QualityTestingService -> QualityTestService)
Features/ServiceControl/orphan-cleanup.flow.md                              -- EDIT (ST3 canonical ServiceName correction)
Features/ServiceControl/StuckJobDetectionService.py                         -- EDIT (fix ServiceName literal QualityTest -> QualityTestService; UPDATE SQL implicit-concat)
Tests/Contract/TestQualityTestServiceNameConsistency.py                     -- CREATE

# Reset 24 -- C24 deploy-time capability probe (redeploy no longer nukes Workers.nvenccapable/qsvcapable)
deploy/deploy-linux-worker.py                                               -- EDIT (StepReconcileCapabilities wired between stale-pyc probe and cleanup; Total 9 -> 10)

# Reset 25 -- C25 Family-agnostic Profile + quality-label enqueue + any-worker claim (SPEC ONLY; deep implementation follows)
Scripts/SQLScripts/CollapseProfilesToTierLadder_2026_07_XX.py               -- CREATE (5-row tier ladder; drop Family/ContentClass/Resolution from Profiles; fold thresholds; UPDATE all FKs)
Features/Profiles/*.py                                                      -- EDIT (Family drop; QualityLabel add; ProfileRepository new lookup by (Tier|Label, ContentClass, Resolution))
Features/TranscodeQueue/TranscodeQueueRepository.py                         -- EDIT (ClaimNextPendingTranscodeJob drops Family predicate)
Core/Database/WorkerCapabilityPredicate.py                                  -- EDIT (encode-capable = nvenccapable OR qsvcapable for transcode claim)
Features/TranscodeJob/Worker/WorkerEncoderResolver.py                       -- CREATE (Resolve(Worker) -> EncoderFamily; NVENC preferred)
Features/TranscodeJob/Emit/CommandComposer.py                               -- EDIT (Build gains EncoderFamily param; VideoSlot branches on it)
Features/TranscodeJob/Emit/Slots/VideoSlot.py                               -- EDIT (Reencode path per EncoderFamily; drop per-Profile Family lookup)
Features/ContentClassifier/*.py                                             -- EDIT (drop Family from tuple; classify by (ContentClass, Resolution, TargetTier))
Features/TranscodeQueue/AdequacyGate.py                                     -- EDIT (Tier1TargetKbps read is Family-agnostic)
Features/TranscodeJob/Adjustments/NextTierAdjustmentCalculator.py           -- EDIT (walk by Tier only, no Family)
Features/TranscodeQueue/QueueManagementBusinessService.py                   -- EDIT (AddJobToQuality signature; label|tier -> ProfileId resolver)
WebService/Routes/WorkTranscodeRoutes.py                                    -- EDIT (POST /Queue/<mfid>?quality=<label>|?tier=<n>)
Features/SystemSettings/Templates/settings.html + Static/settings.js       -- EDIT (Transcoding card ladder table drops Family column; QualityLabel visible)
Tests/Contract/TestFamilyAgnosticProfile.py                                 -- CREATE
Tests/Contract/TestAnyCapableWorkerClaimsFamilyAgnostic.py                  -- CREATE
Tests/Contract/TestWorkerEncoderResolver.py                                 -- CREATE
Tests/Contract/TestEnqueueByQualityLabel.py                                 -- CREATE
```

### Seams

Persistent seam SOT lives in flow docs (`.claude/rules/seam-verification.md`). Directive enumerates only seams the directive ADDS or CHANGES; existing seams referenced by `<flow-slug>.S<N>`.

| Seam | Producer | Wire shape | Consumer expects | Verification |
|---|---|---|---|---|
| S1 (new) `transcode.ST5 Strategy -> ST6 Audio` (any strategy) | Strategy `Encode()` returns Result{OutputPath, StreamCopy: bool} | `Result` dataclass | ST6 conditional on StreamCopy flag | Contract test + smoke (a)/(b) |
| S2 (new) `transcode.ST8 Strategy Verify` | Strategy `Verify()` returns Result{Score, Method} | `Result` dataclass with Method IN {'VMAF','Checksum'} | Disposition decider reads Method + Score | Contract test + smokes |
| S3 (change) `TranscodeQueue.INSERT contract` | All admission producers | Non-null: audiopolicyjson, storagerootid, relativepath, processingmode | Claim query + JobProcessor read as guaranteed non-null | Contract test `TestEnqueueContract` |
| S4 (change) `TranscodeAttempts shared-column write` | Every strategy | AudioPolicyResolved, AudioPolicyJson, AudioTracksEmittedJson all non-null | Compliance + dashboards read as guaranteed non-null | SQL audit + smoke |
| S5 (change) `Requeue disposition -> new TranscodeQueue row` | `DispositionDispatcher.Requeue` | `INSERT INTO transcodequeue ...` via `AddJobToQueue` | Next claim finds the requeued row | Smoke (d) + BUG-0079 |
| S6 (new) `Profile tuple identity` | `Profiles.(Family, QualityTier, ContentClass, TargetResolutionCategory)` | UNIQUE tuple; `NextTierAdjuster.Get(currentProfile)` walks `QualityTier + 1` | Escalation deterministic; `None` at ceiling; RetryBudget still caps | `TestProfileTierLadder` + `TestNextTierAdjuster` |
| S7 (new) `ProfileThresholds.TargetKbps / IcqQ` | `ProfileThresholds` per (ProfileId, Resolution) | absolute INT kbps for VBR profiles; INT q for ICQ profiles | `NvencEncoderArgsStrategy` emits `-b:v <TargetKbps>k`; `QsvEncoderArgsStrategy` emits `-global_quality <IcqQ>` | encoder-args unit tests |
| S8 (new) `AdequacyGate seam at admission` | `QueueManagementBusinessService.AddJobToQueue -> AdequacyGate.Evaluate(MediaFile)` | `AdequacyDecision {Excluded, Admitted, RouteToStreamCopy}` + reason | Admission short-circuits on Excluded; writes `MediaFiles.AdequacyDecision` audit | `TestAdequacyGate` + smoke |
| S9 (new) `Decider -> VmafConfidenceStatsRepository (read)` | `PostTranscodeDispositionDecider.Decide` computes bucket, calls Repository.LookupBucket | `Bucket key` -> `Stats(SampleCount, VmafMean, VmafStdDev, PassRate)` | `SmartConfidenceSkip` branch reads Stats fresh per call; DB-authority | `TestSmartConfidenceSkip` |
| S10 (new) `QualityTestingBusinessService -> VmafConfidenceStatsRepository (write)` | On VMAF completion, worker calls `Repository.RecordResult(bucket, score, passed)` | `RecordResult` updates SampleCount + rolling window + VmafMean/StdDev/PassRate | Next Decider call reads updated stats | `TestSmartConfidenceSkip` roundtrip |
| S11 (new) `Global QualityTestEnabled short-circuit` | `PostTranscodeDispositionDecider.Decide` reads GateConfig | `GateConfig.QualityTestEnabled=false` -> `Replace/QualityTestingGloballyDisabled` | Restored per Reset 10 C16; overrides all other branches except TranscodeFailed/NoSavings | `TestDispositionDecider.test_global_off_returns_replace_qualitytestinggloballydisabled` |
| S12 (new) `GUI /settings Transcoding card seam` | `PUT /api/SystemSettings/Transcoding` | JSON body per section (bitrate ladder rows, ICQ ladder rows, adequacy toggle, confidence knobs, global-off, review-panel filter) | Persists to `ProfileThresholds` (TargetKbps/IcqQ) + `PostTranscodeGateConfig` (new cols) + reads `VmafConfidenceStats` for review panel | `TestTranscodingSettingsRoundTrip` |
| S13 (new) `CommandComposer -> ffmpeg argv` | `Features/TranscodeJob/Emit/CommandComposer.Build(Job, MediaFile, Plan)` composes VideoSlot + AudioSlot + SubtitleSlot + ContainerSlot | Plan tuple `{VideoOp, AudioOp, SubtitleOp, ContainerOp}` -> ffmpeg argv list | Strategy.BuildCommand consumes; no ProcessingMode-keyed Registry lookup | `TestCommandComposer` all Plan combos + smoke |
| S14 (new) `SubtitleSlot always fires` | `SubtitleSlot.Emit(Plan.SubtitleOp, TargetContainer, MediaFile)` | MP4 target -> `-map 0:s? -c:s mov_text`; MKV target -> `-map 0:s? -c:s copy`; PGS/DVB image subs targeted to MP4 -> `[]` + WARN log naming dropped codec | Every Plan path retains text subs; image-sub drop is explicit + logged | `TestCommandComposer::test_subtitle_slot_always_fires` + BUG-0083 smokes (e/f/g) |
| S15 (new C18) `VmafAlignmentProbe -> AlignmentSpec` | `Probe(SourcePath, EncodedPath)` reads via MediaProbeAdapter + ColorSpaceService | Immutable VO with 17 fields (color triad + fps/VFR + resolution + crop + deint/detelecine + bit depth + chroma + HDR flag + duration parity assert) | `VmafFilterChainBuilder.Build(spec)` composes filter chain; `VmafModelSelector.Select(spec)` picks model | `TestVmafAlignmentProbe` + `TestAlignmentSpec` invariants + 10 live smokes |
| S16 (new C18) `VmafFilterChainBuilder stages` | 9 pure functions composed in fixed order (setpts / deinterlace / detelecine / fps / colorspace / crop / scale / chroma / libvmaf) | `AlignmentSpec` -> str filter chain | `VmafCommandComposer` injects via `-lavfi` | `TestVmafFilterChainBuilder` per-stage + composition tests |
| S17 (new C18) `VmafModelSelector.Select` | pure fn `(spec) -> VmafModel` | VmafModel enum `{Default, Model4K, Phone, Neg}` | libvmaf argv references model path | `TestVmafModelSelector` rule table |
| S18 (new C18) `VmafCommandComposer -> argv` | replaces `QualityTestingBusinessService.BuildVMAFCommand` | `AlignmentSpec + Attempt` -> ffmpeg argv | `QualityTestingBusinessService.RunVmaf` invokes composer | `TestVmafCommandComposer` end-to-end argv + 10 live smokes |
| S19 (new C19) `Deploy stale-pyc probe` | `deploy/deploy-linux-worker.py` post-COPY probe via `docker exec` | mtime comparison between .py and .pyc siblings | Deploy aborts + logs host + container + file on stale-pyc detected | `TestDeployStalePycProbe` + live re-deploy log |
| S20 (new C20) `WorkerContext.Bind + Current` (thread-local) | `Core/WorkerContext.py` `threading.local()` backing + `Bind(...)` at each processing-thread entry | `Current() -> WorkerContext`; raises `WorkerContextNotBoundError` on unbound thread | `PostEncodeMeasurementService.Probe` (strict-mode) + every `Current()` caller | `TestWorkerContextThreadLocal` + `TestProbeStrictModeWhenContextBound` + live Wakko QSV Requeue apr='resolved' |

### Promotions

Populated incrementally per step.

| Source (directive) | Target | Commit |
|---|---|---|
| Job Types section spec (C0a) | `ARCHITECTURE.md` `## Job Types` | (Reset 2 commit) |
| Gap to Target re-audit (Signal 3 findings + missing artifacts) | `ARCHITECTURE.md` `## Gap to Target` | (Reset 2 commit) |
| Glossary tier definition (C0b) | `GLOSSARY.md` created; `.claude/rules/doc-layering.md` tier row added | (Reset 3 commit) |
| Deprecated-term inventory (Remux / BypassReplace / ProcessingMode / Transcode ambiguity / AudioFix / SubtitleFix / Quick) | `GLOSSARY.md` Media-encoding + Job-model buckets | (Reset 3 commit) |
| "One flow per pipeline shape" invariant (C1) | `.claude/rules/flow-docs.md` | (Reset 5 commit) |
| Strategy variants at ST8 Verify (C1) | `transcode.flow.md` `### ST8 Strategy variants` | (Reset 5 commit) |
| VMAF -> VERIFY stage rename (C1) | `transcode.flow.md` Stage Overview + Seams S3/S4 + Stage 7 heading | (Reset 5 commit) |
| Stale `remux.flow.md` parenthetical deletion (C8) | `transcode.flow.md` ST6 audio-policy attestation + same-slot rename safety paragraphs | (Reset 5 commit) |
| Parked `quality-test.flow.md` full content (C1) | `Features/QualityTesting/quality-test.flow.md` CREATED | (Reset 14 DELIVERING commit) |
| Parked `profile-tier-ladder.feature.md` full content (C12) | `Features/Profiles/profile-tier-ladder.feature.md` CREATED | (Reset 14 DELIVERING commit) |
| Parked `admission-adequacy-gate.feature.md` full content (C13) | `Features/TranscodeQueue/admission-adequacy-gate.feature.md` CREATED | (Reset 14 DELIVERING commit) |
| Parked `vmaf-smart-sampling.feature.md` full content (C14) | `Features/QualityTesting/vmaf-smart-sampling.feature.md` CREATED | (Reset 14 DELIVERING commit) |
| Parked `command-composer.feature.md` full content (C17) | `Features/TranscodeJob/Emit/command-composer.feature.md` CREATED | (Reset 14 DELIVERING commit) |
| BUG-0085 stale-pyc filed in KNOWN-ISSUES (supersedes BUG-0084) | `memory/KNOWN-ISSUES.md` | (Reset 14 DELIVERING commit) |
| Row 41107 + 41124 + 41125 stranded rows backfilled from siblings (BUG-0085 residue) | DB UPDATE against `transcodeattempts` | (Reset 14 DELIVERING DB write) |
| Violated-section sweep results (C8) | `WorkerService/WorkerService.feature.md` L43-46 delete; `Features/TranscodeQueue/media-tabs.flow.md` L126 parenthetical delete; `Features/TranscodeQueue/transcode-vs-remux-routing.feature.md` L48 wording | (Reset 5 commit) |
| Enqueue non-null contract description (C2 / S3) | `Features/TranscodeQueue/TranscodeQueue.feature.md` new criterion 12 | (Reset 6 commit) |
| BypassReplace retired -- decision table + outcome table + operator override wording (C6/C8) | `transcode.flow.md` ST7 decision table, ST9 outcome table, WebService override sub-path, Phase 7 heading | (Reset 9 commit) |
| Reject added as terminal-verify-fail; Requeue = new-queue-row via BUG-0079 wiring (C6) | `transcode.flow.md` ST9 outcome table + Requeue/Reject/NoReplace subsections | (Reset 9 commit) |
| StreamCopy checksum verify contract (C6) | `transcode.flow.md` ST8 Strategy variants -- checksum row + Vmaf overload note (already promoted Reset 5) | (Reset 9 commit reaffirms) |
| Decider decision table + operator master switch rewrite (C6) | `Features/QualityTesting/post-transcode-disposition.feature.md` criteria 3, 7, 26, 30 + S1 seam wording | (Reset 9 commit) |
| Terminal-cleanup dispositions include Reject (C6) | `Features/QualityTesting/Disposition/disposition.feature.md` C7 | (Reset 9 commit) |
| Operator override endpoint writes Replace/Discard, not BypassReplace (C6) | `Features/QualityTesting/qt-queue-visibility-and-override.feature.md` C5 + `Features/QualityTesting/manual-override-replace.feature.md` What-It-Does / criterion 2 / criterion 3 | (Reset 9 commit) |
| Post-transcode-pipeline TFP cleanup covers Reject too (C6) | `Features/FileReplacement/post-transcode-pipeline.feature.md` criterion 15 + Notes | (Reset 9 commit) |
| Compliance-gate-failure flip references only Replace (C6) | `compliance-gated-rename.feature.md` Notes | (Reset 9 commit) |
| Gap-to-Target -- Compliance-bypass row deleted (gap closed by C6) | `ARCHITECTURE.md` `## Gap to Target` | (Reset 9 commit) |
| Analyze-transcode command interpretation updated for retired BypassReplace (C6/C8) | `.claude/commands/mediavortex-analyze-transcode.md` | (Reset 9 commit) |
| Disposition enum tightened to `{Pending, Replace, Reject, Requeue}` (C6) | `transcode.flow.md` decision + outcome tables + Phase 5.4 / 7 wording | (Reset 9 catch-up commit) |
| RetainInprogressPolicy service + policy-driven artifact cleanup (C6) | `Features/QualityTesting/Disposition/disposition.feature.md` C7 / W4 / S4 | (Reset 9 catch-up commit) |
| Enum + CHECK constraint retirement of NoReplace + Discard (C6) | `Features/QualityTesting/post-transcode-disposition.feature.md` criteria 7, 9, 11, 16, Status | (Reset 9 catch-up commit) |
| Operator override endpoint accepts Replace|Reject (C6) | `Features/QualityTesting/qt-queue-visibility-and-override.feature.md` C3, C5, C7 + manual-override-replace.feature.md What-It-Does / C2 / C3 | (Reset 9 catch-up commit) |
| ComplianceFailureRecorder writes Reject/ComplianceGateFailed (C6) | `compliance-gated-rename.feature.md` Notes | (Reset 9 catch-up commit) |
| Gap-to-Target re-audited: closed rows for AudioPolicy* + VMAF-3.6% + Mode-branches + GLOSSARY + fail-loud (all closed prior resets) | `ARCHITECTURE.md` `## Gap to Target` | (Reset 9 catch-up commit) |
| CommandComposer + 4-Slot architecture SOT (C17) | `Features/TranscodeJob/Emit/encode-emit.feature.md` What-It-Does + W1-W5 + C1-C12 + S1-S7 + Files table | (Reset 10 T5+T6+T15 commit) |
| Plan tuple + PlanFactory contract (C17) | `Features/TranscodeJob/Emit/encode-emit.feature.md` C9 | (Reset 10 T5+T6+T15 commit) |
| Mode-coverage matrix rewritten to Plan tuples (C17) | `Features/AudioNormalization/audio-normalization.flow.md` `## Mode coverage matrix` | (Reset 10 T5+T6+T15 commit) |
| Audio no-fallback invariant relocated to `AudioSlot._EmitReencode` (C17/C26) | `Features/AudioNormalization/audio-normalization.feature.md` C14, C26, C36, C37, S3 | (Reset 10 T5+T6+T15 commit) |
| Strategy table's BuildCommand column rewritten to Plan (C17) | `transcode.flow.md` Stage 6 strategy table | (Reset 10 T5+T6+T15 commit) |
| GET/PUT `/api/SystemSettings/Transcoding` composite endpoint (C15) | `Features/SystemSettings/SystemSettings.feature.md` HTTP API surface | (Reset 11 commit) |
| Transcoding card carries QualityTestEnabled master switch; PostTranscodeSection surface trimmed to VMAF thresholds + WhenVmafUnavailable (C15 one-editor rule) | `Features/QualityTesting/post-transcode-disposition.feature.md` C26 | (Reset 11 commit) |
| AdequacyGate honors SystemSettings `AdequacyGateEnabled` + `AdequacyGateMarginPercent` (C13/C15) | `Features/TranscodeQueue/TranscodeQueue.feature.md` AdequacyGate seam | (Reset 11 commit) |
| TierLadderRepository new home for (Family, ContentClass, Resolution) x Tier grid queries (C12/C15) | `Features/Profiles/Profiles.feature.md` Files table | (Reset 11 commit) |
| VmafConfidenceStatsRepository.GetAllForReview surfaces review-panel rows (C14/C15) | `Features/QualityTesting/post-transcode-disposition.feature.md` C14 | (Reset 11 commit) |
| C18 VMAF alignment chain layer SOT | `Features/QualityTesting/Vmaf/` module: `AlignmentSpec.py`, `VmafAlignmentProbe.py`, `VmafModelSelector.py`, `VmafFilterChainBuilder.py`, `VmafCommandComposer.py` (colocated; no separate feature.md yet since Vmaf/ is a submodule of QualityTesting.feature.md) | (Reset 17-19 commits: 78e0a3f, 7ad5ee4, 0c32469, 1b433bb) |
| C19 deploy hardening + BUG-0085 retirement | `deploy/Dockerfile` `__pycache__` purge + `deploy/deploy-linux-worker.py` post-COPY stale-pyc probe; `Tests/Contract/TestDeployStalePycProbe.py`; live re-deploy log in `### Resume Marker` | (Reset 15 commit b31e12e) |
| C20 WorkerContext thread-local binding | `Core/WorkerContext.py` `threading.local()` + `Bind()` at every processing-thread entry; `Features/AudioNormalization/Services/PostEncodeMeasurementService.py` strict-mode revert | (Reset 16 commit 5b43f34) |
| C21 phase-aware stuck-job detection | `Features/ServiceControl/JobPhase.py` enum + `PhaseDetectors/*.py` strategy + `PhaseDetectorRegistry.py` + `StuckJobDetectionService` refactor | (Reset 15 commit e846f35) |
| 4K streaming Profile rows (STREAMING NVENC + STREAMING QSV Default/HQ) | `Scripts/SQLScripts/Add4KStreamingProfiles_2026_07_07.py` executed; Profile ids 468-471 landed with ProfileThresholds at 2160p (NVENC 1500/2250 kbps VBR + QSV q34/q30 ICQ) sourced from `Docs/Codecs/4K-AV1-Streaming-Sweep-2026-07-06.md` | (Reset 21 commit) |
| 4K AV1 sweep methodology + data | `Docs/Codecs/4K-AV1-Streaming-Sweep-2026-07-06.md` created; per-encoder VBR/ICQ matrix + VMAF distribution + industry cross-reference | (Reset 21 commit c8412cc) |
| C23 canonical QT ServiceName correction | `Features/ServiceControl/orphan-cleanup.flow.md` ST3 row rewritten to `'QualityTestService'` (was `'QualityTestingService'`); code call sites in `QualityTestRepository`, `QualityTestController`, `OrphanCleanupService`, `StuckJobDetectionService` aligned to same literal; contract-test grep fence at `Tests/Contract/TestQualityTestServiceNameConsistency.py` prevents regression | (Reset 23 commit) |
| C24 deploy-time capability probe wired | `deploy/deploy-linux-worker.py` `StepReconcileCapabilities` shells out to `Scripts/ReconcileNvencCapability.py` + `Scripts/ReconcileQsvCapability.py` after compose-up; every redeploy now re-stamps `Workers.nvenccapable/qsvcapable` per running container; live-fix run 2026-07-09 restored 4 dot NVENC rows + 3 wakko QSV rows post-2026-07-02-redeploy regression | (Reset 24 commit) |
| C25 Family-agnostic Profile catalog | `Scripts/SQLScripts/CollapseProfilesToTierLadder_2026_07_09.py` executed live -- 5 family='ANY' tier profiles + 20 threshold rows + `qualitylabel` UNIQUE + `profilethresholds_profile_content_res_unique` UNIQUE; `Features/TranscodeJob/Worker/WorkerEncoderResolver.py` reads `Workers.nvenccapable`+`qsvcapable` fresh per call, NVENC-preferred, fail-loud on no encoder; `TranscodeQueueRepository.ClaimNextPendingJob` guard `AND (COALESCE(p.codec,'') <> 'av1' OR w.nvenccapable=TRUE OR w.qsvcapable=TRUE)` | (Reset 25 core commit) |
| C25 contract test suite | `Tests/Contract/TestFamilyAgnosticProfile.py` (11) + `TestAnyCapableWorkerClaimsFamilyAgnostic.py` (6) + `TestWorkerEncoderResolver.py` (11) + `TestEnqueueByQualityLabel.py` (9); 37 pass, 0 skip | (Reset 25 tests commit `8aed95c`) |
| C25 enqueue-by-quality endpoint | `POST /api/Work/Transcode/Queue/<mfid>?quality=<label>|?tier=<n>` reads query params in `WorkBucketController.queue_one`; `QueueAdmissionAppService.AdmitOne` + `QueueManagementBusinessService.AddJobToQueue` accept `QualityLabel` + `QualityTier` kwargs; `ProfileRepository.GetProfileIdByQualityLabel` / `GetProfileIdByQualityTier` resolve to `ProfileId` | (Reset 25 remainder commit `ceabc8a`) |
| C25 /settings Transcoding card refresh | `TierLadderRepository.GetTierLabelMap` surfaces `{tier -> label}` map; `SystemSettingsController.GetTranscodingSettings` returns `TierLabels`; `Templates/Settings.html` drops Family blocks, renders one row per resolution with `Efficient / Good / Better / Best / Reference` column headers under the tier number | (Reset 25 remainder commit `ceabc8a`) |
| C25 Family retirement + animation rows | `Scripts/SQLScripts/RemapClassifierRulesToFamilyAgnosticTiers_2026_07_09.py` rewrites 5 `ContentClassificationRules` rows from legacy NVENC-CANARY names to `AV1 Tier N Label`; `Scripts/SQLScripts/AddAnimationContentClassThresholds_2026_07_09.py` seeds 20 animation-class threshold rows (5 tiers x 4 resolutions) with own kbps ladder; `SystemSettings.feature.md` C10 rewritten to describe family-agnostic Transcoding card | (Reset 25 remainder commit `ceabc8a`) |
| C27 fail-loud Worker.Current (no hostname fallback) | `Core/Path/Worker.py` `Current()` raises `WorkerContextNotBoundError` when TryCurrent is None; no `socket.gethostname()` fallback. Callers on unbound threads fail loudly instead of masquerading as OS hostname. Wakko bare-metal (hostname `client-b450m-01` != WorkerName `wakko-worker-1`) exposed the fleet-wide latent defect masked by docker `hostname: <workername>` + I9 OS hostname coincidence | (Reset 26 commit) |
| C27 capability-poller thread Bind | `WorkerService/Main.py:_CapabilityPollingLoop` calls `WorkerContext.Bind()` at loop entry so services lazy-instantiated on this thread (ProcessQualityTestQueueService -> QualityTestingBusinessService) inherit the process WorkerContext template instead of an unbound thread-local | (Reset 26 commit) |
| C27 defer Worker.Current to per-call in QT + FileReplacement | `Features/QualityTesting/QualityTestingBusinessService.py`, `Services/QualityTestQueueService.py`, `Features/FileReplacement/FileReplacementBusinessService.py`, `Features/FileReplacement/TranscodedOutputPlacement.py` -- `__init__` no longer captures `Worker.Current()` eagerly; `_GetWorker()` lazy-loads on first call from the bound processing thread (matches path.C21). Frozen-Worker-at-construction pattern retired | (Reset 26 commit) |
| C27 ContinuousScanService fail-loud + thread Bind | `Features/FileScanning/ContinuousScanService.py:_ScanLoop` calls `WorkerContext.Bind()` at loop entry; `_ExecuteScan` `ThisWorkerName` reads `WorkerContext.Current().WorkerName` (was silent `socket.gethostname()` fallback) | (Reset 26 commit) |
| C27 advisory-claim TZ fix | `WorkerService/Main.py:_ClaimPrefixedWorkerName` computes `StaleThreshold` as naive-UTC (`datetime.now(tz=timezone.utc).replace(tzinfo=None)`) to match DB `timestamp_without_timezone` semantics. Prior TZ-naive local comparison saw UTC-stored heartbeats 6 hours in the future on MDT wakko and never reclaimed the stale slot -- reboot loops climbed `-1` -> `-2` -> ... -> `-N` forever | (Reset 26 commit) |
| C27 hostname-fallback test replaced with fail-loud test | `Tests/Unit/test_path_worker.py::test_from_worker_context_falls_back_to_hostname_when_uninitialized` deleted; `test_from_worker_context_raises_when_uninitialized` added -- asserts `Worker.Current()` on Reset context raises `WorkerContextNotBoundError` | (Reset 26 commit) |
| C27 live smoke evidence | Wakko bare-metal VMAF end-to-end -- attempt 41322 Success=True Disposition=Replace VMAF=89.94 (Min=58.56 P5=82.00 P25=88.42 HarmonicMean=89.71) via wakko-worker-1 (av1_qsv encode + Demucs pre-pass on Arc XPU + libopus 2-track + VMAF ffmpeg self-hosted). QTR row 1406 Status=Success | (Reset 26 verification) |
| C28 partial UNIQUE index invariant | `Scripts/SQLScripts/AddSingleInflightAttemptInvariant_2026_07_11.py` executed live; `pg_indexes` confirms `ta_one_inflight_per_mfid` present on `TranscodeAttempts (MediaFileId) WHERE Success IS NULL`. Two workers cannot land in-flight attempts for the same MediaFileId; DB refuses at INSERT | (Reset 27 commit) |
| C28 AttemptAbandonmentSweeper | `Features/ServiceControl/AttemptAbandonmentSweeper.py` CREATE; wired into `WorkerService/Main.py:_OrphanCleanupLoop` alongside `OrphanCleanupService`; single sanctioned cross-worker terminal write path. Idempotent. Live-observed at 2026-07-11 22:38:21 (2 tick log lines, 1 release each) | (Reset 27 commit) |
| C28 owner-scoped stuck-detect | `Features/ServiceControl/StuckJobDetectionService.py` -- `DetectAndCleanStuckTranscodeJobs`, `DetectAndCleanHungEncodes`, `DetectAndCleanStuckQualityTestJobs` filter at SELECT layer to `WorkerName = WorkerContext.Current().WorkerName`. Remote-owned jobs never inspected + never written. Reset 26 remote-owned guard block deleted from `CleanupStuckJob` as unreachable dead code | (Reset 27 commit) |
| C28 canonical claim rule | `.claude/rules/claim-authority.md` CREATE -- one invariant, one claim SQL, one sweeper. Referenced from `.claude/rules/db-is-authority.md`. `transcode.flow.md` "Job Claiming Mechanism" section rewritten to describe the DB invariant + owner authority + sweeper (previous prose described SELECT-then-UPDATE + cross-host stuck-detect DB writes; deleted) | (Reset 27 commit) |
| C28 contract tests | `Tests/Contract/TestAbandonmentSweeper.py` CREATE: `test_only_stale_and_offline_owner_attempts_released` + `test_idempotent_second_sweep_no_op_for_already_abandoned` + `test_online_owner_never_swept_even_when_heartbeat_stale` + `test_second_inflight_attempt_refused_by_db` + `test_terminal_attempt_frees_the_slot`. 5/5 PASS. Regression: 26/26 PASS on `TestClaimAuthority.py` + `TestWorkerContextThreadLocal.py` | (Reset 27 commit) |
| C29 QT partial UNIQUE invariant | `Scripts/SQLScripts/AddSingleRunningQtResultInvariant_2026_07_11.py` executed live; `qtr_one_running_per_attempt` partial UNIQUE index on `QualityTestResults (TranscodeAttemptId) WHERE Status='Running'` present. Two workers cannot land Running QT rows for the same TranscodeAttemptId | (Reset 27 followup commit) |
| C29 SaveTranscodeAttempt IntegrityError handling | `Features/TranscodeJob/TranscodeJobRepository.SaveTranscodeAttempt` INSERT branch catches `psycopg2.errors.UniqueViolation`, logs WARN, resets TranscodeQueue row Status='Pending' + ClaimedBy=NULL for this MediaFileId + this worker, returns None. Caller checks None + aborts encode cleanly. Closes the "claim TX doesn't INSERT attempt" gap gracefully -- the DB race is resolved without a raise-then-catch storm | (Reset 27 followup commit) |
| C29 Owner-only UPDATE guard on TranscodeAttempts | `UpdateTranscodeAttempt` gates general UPDATEs by `AND WorkerName = WorkerContext.Current().WorkerName`. VMAF-finalization scope (Updates keys subset of {VMAF, QualityTestCompleted, StorageRootId, RelativePath, WorkerName} AND VMAF in keys) is exempt so cross-worker VMAF finalization writes are permitted per the domain contract. 3 contract tests cover: refuse-general-cross-worker, permit-general-owner-write, permit-VMAF-cross-worker | (Reset 27 followup commit) |
| C29 fleet deploy to Reset 27 code | `deploy-linux-worker.py dot` + `larry` executed; 4 dot containers + 4 larry containers + wakko + I9 all running `9e4153b`+ code (13 total workers, fresh heartbeats). 10/10 Reset 27 contract tests PASS. 26/26 regression PASS | (Reset 27 followup commit) |


### Verification

Closed-criteria evidence (C0a, C0b, C1-C20, C22, C23, C24, C25, C27, C28 -- all IMPLEMENTED) archived at `.claude/directives/closed/2026-07-03-transcode-flow-canonical-archive.md`. Contract-test regression totals + follow-ups filed at VERIFYING also archived.

- **C41. Deterministic worker identity + DB-authoritative per-worker concurrency. IMPLEMENTED (2026-07-25).**
  - **Part A (identity):** `_ClaimPrefixedWorkerName` retired from `WorkerService/Main.py`. `_ResolveWorkerName` fail-louds on missing `MEDIAVORTEX_WORKER_NAME`. Bare-metal systemd unit uses `EnvironmentFile=/etc/mediavortex/instance-%i.env` (deploy writes one file per instance). Docker `larry.yml` sets env per service. `StartMediaVortex.py` + `StartWorker.py` set env from `COMPUTERNAME` when unset (Windows convention). `StartParallelWorkers.py` composes explicit `MEDIAVORTEX_WORKER_NAME=<prefix>-worker-<N>` per child. `deploy/baremetal/mediavortex-worker@.service` + `deploy/deploy-baremetal-worker.py` StepInstallSystemdUnit rewritten (per-instance env files). `StepAgeSlotHeartbeats` DELETED. `StepStartInstances` sleep-3 serialization DELETED.
  - **Part B (concurrency):** `Core/Database/WorkerCapabilityPredicate.BuildInflightCapPredicate(WorkerName, JobType)` shipped. `TranscodeQueueRepository.ClaimNextPendingJob` + `QualityTestRepository.ClaimQualityTestJob` gate on it.
  - **DOMAIN.md:** 4 entries recorded 2026-07-25 (identity deploy-assigned + per-worker concurrency DB-authoritative + fleet on HEAD + deploy requires committed+pushed).
  - **Enforcement gate:** `deploy/deploy-fleet.py` refuses when `git status --porcelain` non-empty OR `HEAD != origin/main`. No override.
  - **Tests:** `TestClaimAuthority.py::TestInflightCapPredicateHelper` (3) + `TestTranscodeConcurrencyCapLive` (1) PASS. `TestDeployIdempotenceInvariants.py::TestDeterministicWorkerIdentity` (6 grep-fences: `_ClaimPrefixedWorkerName` retired, `MEDIAVORTEX_WORKER_PREFIX` retired, `worker-prefix.env` writes retired, `StepAgeSlotHeartbeats` retired, `socket.gethostname()` gone from WorkerService, systemd unit references per-instance env file) PASS. Combined: 22 + 12 = 34/34.
  - **Live smoke:** `py deploy/deploy-fleet.py --hosts dot,wakko --no-drain --skip-local` on 2026-07-25. Both fleets landed on Version=bc0d4ee5. Zero duplicate ProcessIds per WorkerName. Fleet-script's polling scope for `--hosts` filter reports spurious TIMEOUT on larry-1..4 (they weren't targeted) -- follow-up bug, not a C41 regression. Wait for user to un-pause worker-1s to see concurrency-cap under load.

**Pending verification (open):**

- **C33 sharpened.** Core (C33a-C33f, C33l-C33q) IMPLEMENTED per commit 9adcf50e (see archive). C33g-C33k (cross-vertical doc claims + closed-directive anchor sweep + dead-code sweep + bucket ProcessingMode validity + UI adapter 5-branch coverage) IN PROGRESS post-2026-07-22.
- **C34.** Non-video containers excluded. Reset 34 IMPLEMENTING. Verification: reclassify migration executed + `SELECT COUNT(*) FROM MediaFiles WHERE ContainerFormat IN (...) AND WorkBucket IN ('Transcode','Remux','AudioFix')` returns 0; live rescan smoke pending.
- **C35-C40.** No implementation started (C35 TA MediaFileId immutable trigger; C36 CHECK constraint + rolling stderr buffer; C37 exhaustive admission probe; C38 typed CommandBuilder exceptions; C39 drain-only exit + retire `worker crashed/restarted`; C40 domain doc + comment + unused-code purge).

### Resume Marker

Full Resume Marker (Reset 9 code + catch-up through Reset 22 evidence, 2026-07-04 through 2026-07-07 execution log) archived at `.claude/directives/closed/2026-07-03-transcode-flow-canonical-archive.md`.

**Current step:** Reset 33 VERIFYING (C33g-k sweep) + Reset 34 IMPLEMENTING (C34 non-video exclusion). C35-C40 pending.

**Phase:** IMPLEMENTING

**Last commit at archive cut:** `7c984df2 fix(admin-workers): render QSV badge for Intel-capable workers`

---

### Parked -- quality-test.flow.md

R13 refuses new `*.flow.md` outside DELIVERING. Content below is parked for Promotion at DELIVERING (see Promotions row). Target path: `Features/QualityTesting/quality-test.flow.md`.

```markdown
# Quality Test Flow

**Slug:** quality-test

Entry point: `Features/QualityTesting/ProcessQualityTestQueueService.py` (worker loop started by `WorkerService/Main.py._StartQualityTestCapability` when `Workers.QualityTestEnabled=TRUE`).

Quality Test is a sub-flow of `transcode.flow.md`. Admission is `transcode.ST7` (DISPOSITION) when `PostTranscodeDispositionDecider.Decide` returns `'Pending'` (`VMAF IS NULL` AND `QualityTestRequired=TRUE`). Completion re-enters `DispositionDispatcher.Dispatch` inside the same worker process; the second dispatch resolves to `Replace` / `BypassReplace` / `NoReplace` / `Requeue` per the VMAF score against `PostTranscodeGateConfig` thresholds.

## Stage Overview

```
ADMIT -> CLAIM -> PROBE -> RUN_VMAF -> WRITE_VMAF -> REDISPATCH
 ST1     ST2      ST3       ST4        ST5           ST6
```

`ST1` is the boundary crossing FROM `transcode.ST7`. `ST6` is the boundary crossing BACK INTO `transcode.ST7` for terminal disposition. Everything between runs on a single WorkerService thread claimed by `ClaimQualityTestJob`.

---

## Seams

Stage-transition data contracts. Intra-feature seams live in `Features/QualityTesting/QualityTesting.feature.md`. The admission seam (S1) and the return seam (S6) are the two boundaries with `transcode.flow.md`.

| ID | Transition | Producer (writer) | Wire shape | Consumer (reader) expects | Verification |
|---|---|---|---|---|---|
| S1 | `transcode.ST7 -> quality-test.ST1` (ADMIT) | `DispositionDispatcher.Dispatch` -> `ProcessTranscodeQueueService.DispatchDisposition` -> `QualityTestQueueService.AddToQualityTestQueue` | `QualityTestingQueue.(Id BIGINT, TranscodeAttemptId BIGINT NOT NULL, OriginalFilePath TEXT, LocalSourcePath TEXT, TranscodedFilePath TEXT, Status='Pending', ForceDisposition IS NULL, DateAdded=NOW(), DateStarted IS NULL, ClaimedBy IS NULL)`; requires `TemporaryFilePaths` row with typed-pair `(SourceStorageRootId, SourceRelativePath, OutputStorageRootId, OutputRelativePath)` already written by ST6 | `QualityTestRepository.ClaimQualityTestJob` polls this row via the shared `BuildClaimPredicate` gate | `SELECT COUNT(*) FROM QualityTestingQueue WHERE Status='Pending'` increments by 1 per admission; `Tests/Contract/TestClaimAuthority.py::TestQualityTestClaimAuthority` |
| S2 | `ST1 -> ST2` (ADMIT -> CLAIM) | `ProcessQualityTestQueueService.ProcessQueueLoop` (polls every 2s) | `WorkerContext.Current().WorkerName` passed to `ClaimQualityTestJob` | `QualityTestRepository.ClaimQualityTestJob` atomically SELECT-then-UPDATE gated by `Workers.Status='Online' AND Workers.QualityTestEnabled=TRUE AND QualityTestingQueue.ForceDisposition IS NULL AND DateStarted IS NULL`; also checked against `FailureBudgetPredicate.BuildCapPredicate` on `ta.MediaFileId` | UPDATE sets `Status='Running', DateStarted=NOW(), ClaimedBy=<WorkerName>`; `Tests/Contract/TestClaimAuthority.py::test_paused_worker_refused / test_capability_false_refused / test_midflight_flip_honored_on_next_claim / test_force_disposition_row_invisible` |
| S3 | `ST2 -> ST3` (CLAIM -> PROBE) | `QualityTestingBusinessService.StartQualityTest` opens tracking rows: `QualityTestResults.(Status='Running', VMAFScore=0.0)`, `ActiveJobs.(ServiceName='QualityTestService', JobType='QualityTest', QueueId, ProcessId, ThreadId, WorkerName)`, `QualityTestProgress.(Status='Processing')` | `TemporaryFilePaths` typed pair `(SourceStorageRootId, SourceRelativePath, OutputStorageRootId, OutputRelativePath)` for the same `TranscodeAttemptId` | `QualityTestingBusinessService.BuildVMAFCommand` reads TFP row, projects to `Path.FromRow` with `Prefix="Source"` / `"Output"`, `Path.Resolve(Worker)` to worker-local absolute paths, `PathFs.Exists` gates both sides | `Tests/Contract/TestQualityTestPath.py` (path projection round-trip); `SELECT COUNT(*) FROM ActiveJobs WHERE ServiceName='QualityTestService' AND Status='Running'` matches worker's in-flight count |
| S4 | `ST3 -> ST4` (PROBE -> RUN_VMAF) | `QualityTestingBusinessService.BuildVMAFCommand` after `GetVideoResolution` on both files + `DetermineVMAFTargetResolution` + `_BuildVmafFilterChain` | ffmpeg argv string: `-i "<transcoded>" -i "<original>" -lavfi "<vmaf_filter with fps lock, PTS reset, lanczos scale, TV color range, 10-bit precision, libvmaf n_threads>" -f null -`; XML log path pinned to `vmaf_output.xml` | `QualityTestingBusinessService.ExecuteFFmpegWithProgress` spawns ffmpeg; `MonitorVMAFProgress` thread updates `QualityTestProgress.(CurrentFps, AverageFps, EtaSeconds, ProgressPercentage)` from stderr frame lines | `QualityTestResults.FFmpegCommand` populated pre-run for audit; process return code drives the branch |
| S5 | `ST4 -> ST5` (RUN_VMAF -> WRITE_VMAF) | ffmpeg process on rc==0 writes `vmaf_output.xml` | libvmaf XML with per-frame `metrics.vmaf` + `metrics.motion` values | `QualityTestingBusinessService.ParseVMAFMetrics` reads `Summary:` block, applies animation-aware motion=0 filter (see `memory/KNOWN-ISSUES.md` VMAF distribution), returns dict `{Mean, Min, Max, HarmonicMean, StdDev, P1, P5, P10, P25}` | `QualityTestingBusinessService.UpdateQualityTestResultsWithScore` writes `QualityTestResults.(VMAFScore, VMAFMin, VMAFMax, VMAFHarmonicMean, VMAFStdDev, VMAFP1..P25, PassesThreshold, Status='Success')`; `DatabaseManager.UpdateTranscodeAttempt` writes `TranscodeAttempts.(VMAF=<mean>, QualityTestCompleted=TRUE)`; `ActiveJobRepository.CompleteActiveJob(True)`; `QualityTestRepository.DeleteQualityTestQueueItem` removes the queue row |
| S6 | `ST5 -> transcode.ST7` (WRITE_VMAF -> REDISPATCH) | `QualityTestingBusinessService.BuildVMAFCommand` calls `self._BuildDispositionDispatcher().Dispatch(TranscodeAttemptId)` after VMAF write | `TranscodeAttempts.(VMAF DOUBLE PRECISION NOT NULL, QualityTestCompleted=TRUE, Disposition='Pending')` -- same row shape `transcode.S4` expects | `DispositionDispatcher.Dispatch` re-reads the row; `PostTranscodeDispositionDecider.Decide` now sees `VmafScore IS NOT NULL` and returns `Replace` when `VMAF >= VmafAutoReplaceMinThreshold`, `Requeue` when below, `NoReplace` on out-of-band cases. On `Replace`/`BypassReplace` the same code path invokes `FileReplacementBusinessService(...).ProcessFileReplacement`; on `Requeue` it invokes `QualityTestingBusinessService._HandleRequeueDisposition` (delete staged `.inprogress`, `AddProblemFile('VmafBelowMin')`, delete TFP row) | Idempotent -- `DispositionDispatcher._CheckCachedDisposition` short-circuits if `Disposition` was already committed non-Pending; `Tests/Contract/TestDispositionDispatcher.py`; `SELECT COUNT(*) FROM TranscodeAttempts WHERE QualityTestCompleted=TRUE AND VMAF IS NULL` -> 0 |

---

## Stage 1: ADMIT -- Enqueue Pending Attempt (`ST1`)

**Trigger:** `transcode.ST7` (`DispositionDispatcher.Dispatch`) commits `Disposition='Pending'` for an attempt where `VMAF IS NULL AND QualityTestRequired=TRUE`.

**Code path:**
- `Features/TranscodeJob/ProcessTranscodeQueueService.DispatchDisposition` inspects the DispositionResult; on `Pending` it constructs `QualityTestQueueService(self.DatabaseManager)` and calls `AddToQualityTestQueue(TranscodeAttemptId)`.
- `Services/QualityTestQueueService.AddToQualityTestQueue`:
  1. `DatabaseManager.GetTranscodeAttemptById` -- refuses if attempt not `Success=TRUE`.
  2. `DatabaseManager.GetQualityTestQueue` in-memory filter for duplicate `TranscodeAttemptId` -- returns existing JobId if present.
  3. `DatabaseManager.GetTemporaryFilePath(TranscodeAttemptId)` -- refuses if no TFP row exists.
  4. `Path.FromRow(Prefix='Source' | 'Output')` -> `SourcePath.CanonicalDisplay(PrefixMap)` for `OriginalFilePath`, `SourcePath.Resolve(Worker)` for `LocalSourcePath`, `OutputPath.Resolve(Worker)` for `TranscodedFilePath`.
  5. `QualityTestRepository.CreateQualityTestQueueEntry` inserts the row with `Status='Pending', DateAdded=NOW(), DateStarted=NULL, DateCompleted=NULL`.

**Tables written:** `QualityTestingQueue` (one row per admitted attempt).

**Failure modes:** attempt not Success, TFP row missing, path resolution error -- all short-circuit with logged error; no queue row created. `DispositionDispatcher` had already committed `Disposition='Pending'` -- the attempt is invisible to Stage 7 downstream until an operator override lands on the (missing) queue row or `Scripts/AddLastTranscodeAttemptToQualityQueue.py` re-injects it.

---

## Stage 2: CLAIM -- Poll And Reserve (`ST2`)

**Trigger:** `ProcessQualityTestQueueService.ProcessQueueLoop` polls every 2s while `IsProcessing AND NOT StopRequested`.

**Code path:**
- `ClaimNextJob` reads `WorkerContext.Current().WorkerName` (refuses claim if unregistered).
- `QualityTestRepository.ClaimQualityTestJob(WorkerName)` builds two SQL fragments:
  - `WorkerCapabilityPredicate.BuildClaimPredicate(WorkerName, 'QualityTestEnabled')` -- gates on `Workers.Status='Online' AND Workers.QualityTestEnabled=TRUE`.
  - `FailureBudgetPredicate.BuildCapPredicate('ta.MediaFileId')` -- gates on the MediaFile's failure budget.
- SELECT joins `QualityTestingQueue` to `TranscodeAttempts`, filters `Status='Pending' AND ForceDisposition IS NULL AND DateStarted IS NULL` plus both predicates, `ORDER BY DateAdded ASC LIMIT 1`.
- Atomic UPDATE re-applies the capability predicate inside the WHERE so a mid-flight `QualityTestEnabled=FALSE` flip refuses the claim: `SET DateStarted=NOW(), Status='Running', ClaimedBy=<WorkerName>`.

**DB is authority:** the SQL fragment is the single control plane -- no cached capability state in `ProcessQualityTestQueueService`. See `.claude/rules/db-is-authority.md`.

**Tables written:** `QualityTestingQueue.(DateStarted, Status='Running', ClaimedBy)`.

---

## Stage 3: PROBE -- Open Tracking + Resolve Paths (`ST3`)

**Trigger:** `ClaimNextJob` returned a job dict; `ProcessQueueLoop` spawns `ProcessJob(job)` in a daemon thread, which calls `QualityTestingBusinessService.ProcessClaimedJob` -> `StartQualityTest(JobId)`.

**Code path:**
- `StartQualityTest`:
  1. `DatabaseManager.CreateQualityTestResult(TranscodeAttemptId, Status='Running')` -> row in `QualityTestResults` with `VMAFScore=0.0` placeholder.
  2. `ActiveJobRepository.CreateActiveJob(ServiceName='QualityTestService', JobType='QualityTest', QueueId=JobId, ProcessId, ThreadId, WorkerName)` -> row in `ActiveJobs` for operator visibility.
  3. `CreateProgressRecord(JobId, job_details)` -> row in `QualityTestProgress`.
- `BuildVMAFCommand`:
  - Reads `TemporaryFilePaths` typed-pair columns for the `TranscodeAttemptId`.
  - `Path.FromRow` + `Path.Resolve(Worker)` translate canonical to worker-local absolute paths; `PathFs.Exists` refuses if either side is missing.
  - `WorkerContext.Current().FFmpegPath` supplies the ffmpeg binary; refused if unset.
  - `GetVideoResolution(original)` and `GetVideoResolution(transcoded)` via ffprobe.

**Tables written:** `QualityTestResults` (Running placeholder), `ActiveJobs`, `QualityTestProgress`.

---

## Stage 4: RUN_VMAF -- Execute libvmaf (`ST4`)

**Trigger:** `BuildVMAFCommand` finished command assembly.

**Code path:**
- `DetermineVMAFTargetResolution(original, transcoded)` -- compares max-edge, picks the smaller side; both feeds are scaled to that target via lanczos.
- ffprobe reads `stream=avg_frame_rate` on the source; falls back to 24 fps on parse failure.
- `_BuildVmafFilterChain(SourceFps, TargetWidth, TargetHeight, 'vmaf_output.xml', NThreads=4)` -- single source of truth for the libvmaf filter chain, shared with `RunLocalVmafForAttempt` (Mode A). Layout: fps lock, PTS reset, lanczos scale, TV color range pin, 10-bit precision, libvmaf `n_threads=4`.
- Input order pinned: `-i "<transcoded>" -i "<original>"` -- transcoded becomes `[0:v]->[dist]`, original becomes `[1:v]->[ref]`. See `QualityTesting.feature.md` C11c.
- Optional `-ss <StartTime>` from `TranscodeAttempts.StartTime`.
- `QualityTestResults.FFmpegCommand` populated pre-run for audit.
- `ExecuteFFmpegWithProgress(command, ProgressId, JobDetails)` spawns ffmpeg; `MonitorVMAFProgress` thread parses stderr `frame=` lines and updates `QualityTestProgress.(CurrentFps, AverageFps, EtaSeconds, ProgressPercentage, CurrentStep)`.

**Tables written:** `QualityTestResults.FFmpegCommand`, continuous `QualityTestProgress` updates.

---

## Stage 5: WRITE_VMAF -- Parse XML And Persist Score (`ST5`)

**Trigger:** ffmpeg exits with `returncode == 0`.

**Code path:**
- `ParseVMAFMetrics('vmaf_output.xml')`:
  - `rfind('Summary:')` anchors parsing to the Summary block (avoids catching the silence-floor progress lines).
  - Reads per-frame `metrics.vmaf` + `metrics.motion`; drops frames where `motion == 0` (animation duplicate-frame masking). See `memory/KNOWN-ISSUES.md` "VMAF distribution".
  - Returns dict `{Mean, Min, Max, HarmonicMean, StdDev, P1, P5, P10, P25}`; Mean falls back to 0.0 on parse failure.
- `UpdateQualityTestResultsWithScore(result_id, vmaf_score, ffmpeg_result, metrics)`:
  - `PassesThreshold = (VmafAutoReplaceMinThreshold <= VMAFScore <= VmafAutoReplaceMaxThreshold)`.
  - UPDATE `QualityTestResults.(VMAFScore, VMAFMin, VMAFMax, VMAFHarmonicMean, VMAFStdDev, VMAFP1..P25, PassesThreshold, Status='Success', TestDuration)`.
- `DatabaseManager.UpdateTranscodeAttempt(ta_id, {VMAF: vmaf_score, QualityTestCompleted: True})`.
- `_AutoCaptureStillsIfPolicyFires(ta_id)` -- opportunistic still capture on policy match (non-fatal on failure).
- `ActiveJobRepository.CompleteActiveJob(active_job_id, True)`.
- `finally:` `DatabaseManager.DeleteQualityTestQueueItem(JobId)` -- the QT queue row is a revolving door; success or failure, the row is deleted here.

On ffmpeg `returncode != 0` or exception: `UpdateQualityTestResultFailure(result_id, error)`, `UpdateProgressRecord(Failed)`, `ActiveJobRepository.CompleteActiveJob(False, error)`, `_CleanupTemporaryFilePathsForVmafFailure(ta_id)`, `DeleteQualityTestQueueItem` in `finally`. No redispatch fires on failure -- `TranscodeAttempts.Disposition` stays `'Pending'` and the attempt is orphaned until an operator or `GetMissedQualityTests` re-injects it.

**Tables written:** `QualityTestResults` (final row), `TranscodeAttempts.(VMAF, QualityTestCompleted)`, `ActiveJobs.Status='Completed'`, `QualityTestingQueue` (row deleted).

---

## Stage 6: REDISPATCH -- Return To Transcode Disposition (`ST6`)

**Trigger:** `BuildVMAFCommand` on ffmpeg success, after `UpdateTranscodeAttempt` writes the score.

**Code path:**
- `self._BuildDispositionDispatcher().Dispatch(ta_id)` -- constructs a fresh `DispositionDispatcher` with default deps and re-enters `transcode.ST7`.
- `DispositionDispatcher._CheckCachedDisposition` sees `Disposition='Pending'` (not committed as a terminal), proceeds to `_BuildDeciderInput` + `_BuildGateInput`.
- `PostTranscodeDispositionDecider.Decide` now has `VmafScore IS NOT NULL`:
  - `VMAF >= VmafAutoReplaceMinThreshold AND VMAF <= VmafAutoReplaceMaxThreshold` -> `Replace`.
  - `VMAF < VmafAutoReplaceMinThreshold` -> `Requeue`.
  - Out-of-band cases (e.g. compliance fail, size regression) -> `NoReplace` / `Discard` per the gate table.
- `_CommitDisposition` writes `TranscodeAttempts.(Disposition, DispositionReason, DispositionDecidedAt)`.
- `BuildVMAFCommand` branches on the returned `DispositionResult.Disposition`:
  - `Replace` / `BypassReplace` -> `FileReplacementBusinessService(...).ProcessFileReplacement(ta_id)` synchronously (`AutoReplaceTriggered=True`).
  - `Requeue` -> `_HandleRequeueDisposition(ta_id, AuditPayload)`: delete the staged `.inprogress` via `Path.FromLegacyString.Resolve(Worker)`, `AddProblemFile('VmafBelowMin', ...)`, DELETE the `TemporaryFilePaths` row.
  - `NoReplace` / `Discard` -> no filesystem action; `.inprogress` sits until operator clears it (NoReplace) or Stage 9 cleanup runs (Discard).

**Idempotency:** re-entering `Dispatch` on a row that already has a non-Pending Disposition returns the cached result and does nothing else. See `DispositionDispatcher._CheckCachedDisposition`.

**Tables written:** `TranscodeAttempts.(Disposition, DispositionReason, DispositionDecidedAt)`; downstream side effects belong to `transcode.ST9`.

---

## Operator override sub-path

Operator can bypass this flow entirely via `POST /api/QualityTest/Override` (see `Features/QualityTesting/qt-queue-visibility-and-override.feature.md` C4 + `transcode.flow.md ST8`). The WebService sets `QualityTestingQueue.ForceDisposition IN ('Replace', 'Discard')` and drives disposition + FileReplacement synchronously. `ClaimQualityTestJob` filters `ForceDisposition IS NULL`, so a worker cannot race an override row.

## Related contracts

- `.claude/rules/db-is-authority.md` -- `ClaimQualityTestJob` invariant.
- `.claude/rules/flow-docs.md` -- this doc's shape.
- `transcode.flow.md` -- ST7 (admission), ST9 (post-redispatch action), S3/S4 seams.
- `Features/QualityTesting/QualityTesting.feature.md` -- intra-feature seams (filter chain, resolution policy, still capture).
- `Features/QualityTesting/post-transcode-disposition.feature.md` -- Decider + Dispatcher contract.
- `Features/QualityTesting/qt-queue-visibility-and-override.feature.md` -- operator override + queue visibility.
```

---

### Parked -- profile-tier-ladder.feature.md

R13 refuses new `*.feature.md` outside DELIVERING. Content below parked for Promotion at DELIVERING. Target path: `Features/Profiles/profile-tier-ladder.feature.md`.

```markdown
# Profile Tier Ladder

**Slug:** profile-tier-ladder

## What It Does

Replaces per-profile-name proliferation with a 3-axis tuple: `(Family, QualityTier, ContentClass)` at `TargetResolutionCategory`. Family names the encoder + preset (e.g. `NVENC AV1 CANARY`, `QSV AV1 CANARY`). QualityTier ranges 1..5 (small/low-quality -> large/near-source). ContentClass ∈ `{live_action, animation, mixed}`. TargetResolutionCategory reuses the resolution-types tier registry. Every combination = one Profile row. Deleting non-CANARY AV1 profiles kills naming variance that was driving operator confusion.

## Workflows

| # | User action | Surface | Handler | Backing |
|---|---|---|---|---|
| W1 | Operator edits a tier's TargetKbps on /settings Transcoding card | `/settings` bitrate ladder editor | `PUT /api/SystemSettings/Transcoding` | `SystemSettingsController.SaveTranscodingSettings` -> `ProfileThresholds.TargetKbps` UPDATE |
| W2 | ContentClassifier auto-assigns a Family + Tier + ContentClass to a new MediaFile | (internal) | ContentClassifier.Classify | `ContentClassifier.Classify` -> writes `MediaFiles.AssignedProfile` (by tuple lookup) |
| W3 | Dispatcher escalates on VMAF fail -> next-tier profile | (internal) | `NextTierAdjuster.Get` | `Features/TranscodeJob/Adjustments/NextTierAdjustmentCalculator` |

## Success Criteria

C1. `Profiles` schema adds `Family TEXT NOT NULL`, `QualityTier INT NOT NULL CHECK (QualityTier BETWEEN 1 AND 5)`, `ContentClass TEXT NOT NULL CHECK (ContentClass IN ('live_action','animation','mixed'))`. UNIQUE `(Family, QualityTier, ContentClass, TargetResolutionCategory)`. Verifiable: `\d Profiles` shows the three columns + CHECKs + UNIQUE.

C2. `ProfileThresholds` schema adds `TargetKbps INT NOT NULL`. Dead columns `SourceBitratePercent`, `MinBitrateKbps`, `MaxBitrateKbps` dropped. `IcqQ INT NULL` added (populated for ICQ profiles). Verifiable: `\d ProfileThresholds` matches; grep `SourceBitratePercent` in `Features/**/*.py` returns 0.

C3. Two families kept: `'NVENC AV1 CANARY'` + `'QSV AV1 CANARY'`. Every non-CANARY AV1 profile deleted via `DeleteNonCanaryProfiles_2026_07_XX.py`. Orphaned `MediaFiles.AssignedProfile` reassigned via ContentClassifier. Verifiable: `SELECT COUNT(*) FROM Profiles WHERE Codec IN ('av1_nvenc','av1_qsv','libsvtav1') AND Family NOT IN ('NVENC AV1 CANARY','QSV AV1 CANARY')` returns 0.

C4. Backfill populates two families x four resolutions x five tiers x live-action rows. TargetKbps table (live-action calibration, values from directive C12): 480p=[400,550,700,900,1200] / 720p=[900,1400,1900,2500,3200] / 1080p=[1800,2400,3200,4200,5500] / 2160p=[4000,6000,8500,12000,18000]. ICQ ladder q34/q30/q28/q26/q22 per QSV rows. Verifiable: `SELECT * FROM Profiles p JOIN ProfileThresholds pt ON pt.ProfileId=p.Id WHERE p.Family='NVENC AV1 CANARY' AND p.ContentClass='live_action'` returns 20 rows (4 res x 5 tier).

C5. `NvencEncoderArgsStrategy` consumes `TargetKbps` directly. Emits `-b:v <TargetKbps>k -maxrate:v <TargetKbps * MaxBitrateMultiplier>k -bufsize:v <same>k`. No percent-of-source math, no min/max clamps. Verifiable: unit test asserts emitted argv contains the raw TargetKbps value.

C6. `QsvEncoderArgsStrategy` consumes `IcqQ` directly. Emits `-global_quality <IcqQ>` (or ICQ-specific flag). No percent-of-source. Verifiable: unit test asserts emitted argv contains the raw IcqQ value.

C7. `NextTierAdjuster.Get(currentProfile)` returns `Optional[Profile]` by walking the UNIQUE tuple with `QualityTier + 1`. Returns None when ceiling hit (Tier 5). Verifiable: `Tests/Contract/TestNextTierAdjuster.py` covers tier-1 -> tier-5 chain + ceiling terminates.

C8. `DispositionDispatcher._MaybeScheduleRequeue` passes escalated `ProfileId` to `AddJobToQueue` when adjuster returns non-None. Chain terminates at Tier 5 -> Reject/QualityCeilingReached (folds through RetryBudget). Verifiable: dispatcher contract test proves ProfileId in the requeued queue row differs from previous when adjuster escalates.

## Seams

| ID | Seam | Producer | Wire shape | Consumer expects | Verification |
|---|---|---|---|---|---|
| S1 | `Profiles UNIQUE tuple` | Backfill migration | `(Family, QualityTier, ContentClass, TargetResolutionCategory)` | ContentClassifier + NextTierAdjuster | `TestProfileTierLadder` |
| S2 | `ProfileThresholds.TargetKbps -> NvencEncoderArgsStrategy` | EncoderKnobRepository row | absolute INT kbps | encoder argv contains `-b:v <TargetKbps>k` | unit test |
| S3 | `NextTierAdjuster -> AddJobToQueue` | Dispatcher on Requeue | escalated ProfileId | requeued row uses new profile knobs | `TestNextTierAdjuster` + smoke |

## Status

Draft parked in `transcode-flow-canonical` directive. Promotes at DELIVERING per R13.
```

---

### Parked -- admission-adequacy-gate.feature.md

R13 refuses new `*.feature.md` outside DELIVERING. Content below parked for Promotion at DELIVERING. Target path: `Features/TranscodeQueue/admission-adequacy-gate.feature.md`.

```markdown
# Admission Adequacy Gate

**Slug:** admission-adequacy-gate

## What It Does

Refuses to enqueue re-encode work when the source is already at or below the lowest tier's target bitrate for its resolution. Prevents wasted CPU on already-compact sources and prevents doomed VMAF chases on sources whose bitrate is fundamentally below what the profile targets. Container/audio compliance issues still route to StreamCopy (Remux/AudioFix) -- adequacy only refuses full re-encode admission.

## Workflows

| # | User action | Surface | Handler | Backing |
|---|---|---|---|---|
| W1 | Operator adds a MediaFile via WorkBucket that turns out to already be compact | `/api/Work/<Bucket>/Queue/<mfid>` POST | WorkBucketController.queue_one -> QueueAdmissionAppService.AdmitOne -> AddJobToQueue | AdequacyGate.Evaluate short-circuits before INSERT; response Status='skipped', reason='AlreadyCompact' |
| W2 | Scanner surfaces an eligible MediaFile that AdequacyGate excludes | (internal PopulateQueueFromMediaFiles) | scanner -> AddJobToQueue | AdequacyGate.Evaluate short-circuits; MediaFile.AdequacyDecision written for audit |

## Success Criteria

C1. `Features/TranscodeQueue/AdequacyGate.py` exists with public method `Evaluate(MediaFile) -> AdequacyDecision`. `AdequacyDecision` is a dataclass `{Action: str in ('Admit','Exclude','RouteToStreamCopy'), Reason: str, Notes: dict}`. Verifiable: import + call.

C2. `SourceKbps` computed at admission from `MediaFile.VideoBitrateKbps`. If `MediaFile.AssignedProfile` is a Reencode family (VBR or ICQ):
   - Look up Tier 1 TargetKbps for `(AssignedProfile.Family, ContentClass, SourceResolutionTier)`.
   - If `SourceKbps <= Tier1TargetKbps` -> `Exclude(reason='AlreadyCompact', Notes={SourceKbps, Tier1TargetKbps})`.
   - Else `Admit`.
   Verifiable: unit test with mocked ProfileThresholds proves the boundary.

C3. Container / audio compliance columns still consulted after adequacy: if `MediaFile.WorkBucket IN ('Remux','AudioFix')`, adequacy is skipped and StreamCopy admission proceeds (no video re-encode, but container/audio work still needed). Verifiable: unit test.

C4. `MediaFiles` schema adds `AdequacyDecision TEXT NULL`, `AdequacyDecisionAt TIMESTAMP NULL`. Every Evaluate() call that returns Exclude writes the row (through MediaFilesRepository). Admit does not write (no state change needed). Verifiable: SQL audit `SELECT COUNT(*) FROM MediaFiles WHERE AdequacyDecision IS NOT NULL AND AdequacyDecisionAt > <cutover>`.

C5. `QueueManagementBusinessService.AddJobToQueue` calls AdequacyGate.Evaluate at the start of the Reencode admission path. On Exclude, returns `{Success=True, Skipped=True, ErrorMessage='AlreadyCompact: <SourceKbps> <= <Tier1TargetKbps>'}`. Verifiable: contract test.

## Seams

| ID | Seam | Producer | Wire shape | Consumer expects | Verification |
|---|---|---|---|---|---|
| S1 | `AddJobToQueue -> AdequacyGate.Evaluate` | admission entry | `(MediaFile)` | `AdequacyDecision` VO | `TestAdequacyGate` |
| S2 | `AdequacyGate -> ProfileThresholds` | Repository lookup | `(Family, ContentClass, ResolutionTier)` | Tier 1 TargetKbps INT | unit test |
| S3 | `MediaFiles.AdequacyDecision audit` | AdequacyGate writes on Exclude | `TEXT + TIMESTAMP` | operator SQL query | SQL audit |

## Status

Draft parked. Promotes at DELIVERING.
```

---

### Parked -- vmaf-smart-sampling.feature.md

R13 refuses new `*.feature.md` outside DELIVERING. Content below parked for Promotion at DELIVERING. Target path: `Features/QualityTesting/vmaf-smart-sampling.feature.md`.

```markdown
# VMAF Smart Sampling

**Slug:** vmaf-smart-sampling

## What It Does

Skips VMAF for source+profile combinations that have accumulated statistical confidence over prior successful runs. Groups sources into buckets by `(ProfileId, SourceCodec, SourceResolutionTier, BitratePerPixelBucket, ContentClass)`. Tracks rolling pass-rate + mean/stddev per bucket. When a bucket has enough samples AND high pass rate AND mean minus N-sigma exceeds the auto-replace threshold, VMAF is skipped and the disposition returns `Replace/QualityTestConfident`. New buckets bootstrap at SampleCount=0 and force VMAF until confidence builds. Drift automatic: pass-rate drops -> VMAF resumes.

## Workflows

| # | User action | Surface | Handler | Backing |
|---|---|---|---|---|
| W1 | Attempt lands with a bucket that already has confidence | (internal) | Decider.Decide | SmartConfidenceSkip branch -> Replace/QualityTestConfident |
| W2 | VMAF completes on a Pending attempt | (internal) | QualityTestingBusinessService | VmafConfidenceStatsRepository.RecordResult updates bucket stats |
| W3 | Operator tunes confidence knobs on /settings | `/settings` VMAF section | PUT /api/SystemSettings/Transcoding | PostTranscodeGateConfig update |
| W4 | Operator reviews per-bucket stats | `/settings` review panel | GET /api/SystemSettings/Transcoding | VmafConfidenceStatsRepository.ListStats |

## Success Criteria

C1. New table `VmafConfidenceStats` with columns `(Id BIGSERIAL PK, ProfileId BIGINT REFERENCES Profiles(Id), SourceCodec TEXT NOT NULL, SourceResolutionTier TEXT NOT NULL, BitratePerPixelBucket INT NOT NULL, ContentClass TEXT NOT NULL, SampleCount INT NOT NULL DEFAULT 0, VmafMean NUMERIC(5,2), VmafStdDev NUMERIC(5,2), PassRate NUMERIC(5,4), LastUpdated TIMESTAMP DEFAULT NOW())`. UNIQUE `(ProfileId, SourceCodec, SourceResolutionTier, BitratePerPixelBucket, ContentClass)`. Verifiable: `\d VmafConfidenceStats`.

C2. `PostTranscodeGateConfig` gains `MinConfidenceSampleCount INT NOT NULL DEFAULT 10`, `MinConfidencePassRate NUMERIC NOT NULL DEFAULT 0.95`, `SigmaMargin NUMERIC NOT NULL DEFAULT 2.0`. Verifiable: `\d PostTranscodeGateConfig`.

C3. `VmafConfidenceStatsRepository.LookupBucket(ProfileId, SourceCodec, SourceResolutionTier, BitratePerPixelBucket, ContentClass)` reads DB fresh per call (db-is-authority). Returns None when bucket has no row. Verifiable: unit test.

C4. `VmafConfidenceStatsRepository.RecordResult(bucket_key, vmaf_score, passed)` INSERTs on first sample OR UPDATEs an existing row via a rolling-window recompute: SampleCount += 1 (capped at 100 via trim), VmafMean/StdDev recomputed over the retained window, PassRate = passed_count / retained_count. Idempotent within a single VMAF completion. Verifiable: unit test.

C5. `PostTranscodeDispositionDecider.Decide` adds `SmartConfidenceSkip` branch between the QualityTestNotRequired short-circuit and the VMAF-NULL Pending short-circuit. Logic: `if stats.SampleCount >= MinConfidenceSampleCount AND stats.PassRate >= MinConfidencePassRate AND (stats.VmafMean - SigmaMargin * stats.VmafStdDev) >= VmafAutoReplaceMinThreshold: return Disposition('Replace', 'QualityTestConfident')`. Verifiable: `Tests/Contract/TestSmartConfidenceSkip.py` covers bootstrap (SampleCount=0 forces VMAF), confidence-built (N pass -> skip), drift (one fail drops PassRate below threshold -> VMAF resumes).

C6. `BitratePerPixelBucket` computed as INT bucket over `(SourceKbps * 1000) / (Width * Height * (fps/24.0))` with 5 quintile boundaries persisted in `SystemSettings.BitratePerPixelBoundaries` (JSON array). Bucket 1 = lowest, Bucket 5 = highest. Verifiable: unit test asserts boundary math + bucket assignment.

C7. Reason vocabulary gains `QualityTestConfident`. `SELECT DISTINCT DispositionReason FROM TranscodeAttempts` still returns only closed-list values. Verifiable: audit query.

## Seams

| ID | Seam | Producer | Wire shape | Consumer expects | Verification |
|---|---|---|---|---|---|
| S1 | `Decider -> VmafConfidenceStatsRepository.LookupBucket` | Decider computes bucket key | `(ProfileId, SourceCodec, SourceResolutionTier, BitratePerPixelBucket, ContentClass)` | `Stats(SampleCount, VmafMean, VmafStdDev, PassRate)` or None | `TestSmartConfidenceSkip` |
| S2 | `QualityTestingBusinessService -> VmafConfidenceStatsRepository.RecordResult` | On VMAF completion | `(bucket_key, VmafScore, Passed: bool)` | rolling-window update commits | `TestSmartConfidenceSkip` roundtrip |
| S3 | `PostTranscodeGateConfig confidence knobs` | operator via /settings | `MinConfidenceSampleCount / MinConfidencePassRate / SigmaMargin` | Decider reads fresh per call | UI form save + Decider unit test |

## Status

Draft parked. Promotes at DELIVERING.
```

---

### Parked -- command-composer.feature.md

R13 refuses new `*.feature.md` outside DELIVERING. Content below parked for Promotion at DELIVERING. Target path: `Features/TranscodeJob/Emit/command-composer.feature.md`.

```markdown
# Command Composer

**Slug:** command-composer

## What It Does

Retires the ProcessingMode-keyed `EncodeShapeRegistry` + three separate `Shape` classes (`TranscodeShape`, `RemuxShape`, `SubtitleFixShape`) that duplicated ffmpeg-argv construction across Reencode / StreamCopy / SubtitleFix paths. Replaces with one composer function that takes a `Plan` tuple (`{VideoOp, AudioOp, SubtitleOp, ContainerOp}`) and composes four SRP-clean Slot services in a fixed order. Every path goes through the same 4 slots. Fixes BUG-0083 (subtitle-drop across all non-SubtitleFix paths -- ~27127 files) because `SubtitleSlot` always fires with container-appropriate codec.

## Workflows

| # | User action | Surface | Handler | Backing |
|---|---|---|---|---|
| W1 | Worker claims a queued job and builds ffmpeg argv | (internal) | `ITranscodeJobStrategy.BuildCommand` -> `CommandComposer.Build` | `Features/TranscodeJob/Emit/CommandComposer.Build` |

## Success Criteria

C1. `Features/TranscodeJob/Emit/CommandComposer.py` exists. Public method `Build(Job, MediaFile, Plan) -> CommandSpec` composes 4 slots in fixed order: input(s) + VideoSlot + AudioSlot + SubtitleSlot + ContainerSlot + output. Slot services are DIP-injected. Verifiable: import + call + argv shape.

C2. `Features/TranscodeJob/Emit/Slots/VideoSlot.py` exposes Reencode + StreamCopy implementations. Reencode dispatches by Family (NvencVbrImpl / QsvIcqImpl) reading Family from Profile row. Absolute knobs from `ProfileThresholds.TargetKbps` / `IcqQ` (per `profile-tier-ladder.feature.md`). StreamCopy emits `-c:v copy`. Verifiable: unit tests per Op.

C3. `Features/TranscodeJob/Emit/Slots/AudioSlot.py` emits the 2-track pipeline (Original preserved up to 7.1 + Dialog Boost forced stereo) for AudioOp='Reencode'. For AudioOp='Copy' emits `-c:a copy` on all source audio streams. Verifiable: unit tests per Op + audio-emit ffprobe on smoke output.

C4. **`Features/TranscodeJob/Emit/Slots/SubtitleSlot.py` ALWAYS fires.** MP4 target -> `-map 0:s? -c:s mov_text`; MKV target -> `-map 0:s? -c:s copy`; source contains image-based subs (PGS `hdmv_pgs_subtitle`, DVB `dvbsub`, HDMV `hdmv_text_subtitle`) targeted to MP4 -> emit `[]` for those streams + `LoggingService.LogWarning` naming dropped codec + attempt id. Metadata preserved (`-metadata:s:s:N language=...`). Verifiable: `Tests/Contract/TestCommandComposer.py::test_subtitle_slot_always_fires` + smokes (e/f/g).

C5. `Features/TranscodeJob/Emit/Slots/ContainerSlot.py` emits container-format switches (`.mkv -> .mp4` etc.) or preserves. Reads `Plan.ContainerOp` + `Profile.Container`. Verifiable: unit tests per Op.

C6. Legacy classes DELETED (not deprecated, not archived, not comment-marked):
- `Features/TranscodeJob/Emit/EncodeShapeRegistry.py`
- `Features/TranscodeJob/Emit/EncodeShape.py`
- `Features/TranscodeJob/Emit/TranscodeShape.py`
- `Features/TranscodeJob/Emit/RemuxShape.py`
- `Features/TranscodeJob/Emit/SubtitleFixShape.py`
- `Features/TranscodeJob/Emit/EncoderArgsStrategies/NvencEncoderArgsStrategy.py`
- `Features/TranscodeJob/Emit/EncoderArgsStrategies/QsvEncoderArgsStrategy.py`

Verifiable: `Tests/Contract/TestNoLegacyResidue.py` greps `class TranscodeShape|class RemuxShape|class SubtitleFixShape|class EncodeShape|class EncodeShapeRegistry|class NvencEncoderArgsStrategy|class QsvEncoderArgsStrategy` in `Features/**/*.py` returns 0.

C7. `ITranscodeJobStrategy.BuildCommand` delegates to `CommandComposer.Build`. No Shape-registry lookup by ProcessingMode remains at the Emit layer. Verifiable: `grep 'EncodeShapeRegistry' Features/**/*.py` returns 0.

## Seams

| ID | Seam | Producer | Wire shape | Consumer expects | Verification |
|---|---|---|---|---|---|
| S1 | `Strategy -> CommandComposer.Build` | `ITranscodeJobStrategy.BuildCommand` | `(Job, MediaFile, Plan)` | `CommandSpec {Command, OutputPath}` | `TestCommandComposer` |
| S2 | `CommandComposer -> Slot ordering` | Composer internal | 4-slot fixed order Video + Audio + Subtitle + Container | argv list assembled deterministically | `TestCommandComposer::test_slot_ordering` |
| S3 | `SubtitleSlot -> ffmpeg argv` | Slot emitter | container-appropriate codec + optional map | 0 dropped text-sub streams; image subs dropped with WARN | `TestCommandComposer::test_subtitle_slot_always_fires` + smokes |

## Status

Draft parked. Promotes at DELIVERING.
```

---

### Delivery Report

**DIRECTIVE:** `transcode-flow-canonical` -- ONE canonical FFmpeg pipeline; DDD+SOLID+DRY; documentation-first; fail-loud; delete violated docs (never annotate).

**STATUS:** Done -- awaiting operator close.

**WHAT SHIPPED (21 criteria):**
- C0a MAP-tier ARCHITECTURE.md (123 lines) + Job Types section.
- C0b GLOSSARY.md (4 buckets, alphabetical, sourced).
- C1 One pipeline shape per job type: `transcode.flow.md` (10-stage SOT) + `quality-test.flow.md` + FileScanning.flow.md; `audio-normalization.flow.md` retained as legit sub-flow carve-out; `remux.flow.md` deleted.
- C2 Enqueue routes converge through `AddJobToQueue` (BUG-0078 fix landed).
- C3 Claim path single-source (`WorkerCapabilityPredicate.BuildClaimPredicate`).
- C4 Orchestration mode-blind (9+ mode-branches deleted; grep audit clean).
- C5 Shared attestation columns populated by every strategy after BUG-0086 fix (Probe strict-mode with belt-and-suspenders DB attestation).
- C6 Compliance gate non-bypassable; 27608 legacy BypassReplace migrated to Replace; NoReplace + Discard retired; BUG-0079 Requeue-inserts-new-queue-row shipped.
- C7 Fail-loud rule created; `TestFailLoud` 4/4 PASS; baseline ratchet refuses growth.
- C8 Violated docs deleted (no annotations); R14 hook enforces at edit time.
- C9 Four live smokes end-to-end recorded + three bonus subtitle-preservation smokes + six Reset 10 backend smokes.
- C10 Directive size at DELIVERING = 1322 -> ~1340 lines; ceiling 1454. Within envelope.
- C11 Compliance-gate MaxAudioChannels dead-check deleted.
- C12 Profile tier-ladder (Family/QualityTier/ContentClass x Resolution); 40 CANARY profiles; 51,247 MediaFiles consolidated.
- C13 AdequacyGate refuses compact-source Reencode admission.
- C14 SmartConfidenceSkip branch + `VmafConfidenceStats` rolling window (N=100).
- C15 `/settings` Transcoding card + composite `GET/PUT /api/SystemSettings/Transcoding`.
- C16 Global `QualityTestEnabled=false` -> `Replace/QualityTestingGloballyDisabled` restored.
- C17 Emit-layer CommandComposer + 4-slot collapse; BUG-0083 subtitle-drop CLOSED.
- **C18 VMAF alignment canonical measurement pipeline.** Chain SOT under `Features/QualityTesting/Vmaf/`: AlignmentSpec VO + Probe + ModelSelector + FilterChainBuilder + CommandComposer + ColorSpaceService. `QualityTestingBusinessService.BuildVMAFCommand` + `RunLocalVmafForAttempt` rewired; retired `_BuildVmafFilterChain` + `GetVideoResolution` + `DetermineVMAFTargetResolution`. 89 contract tests green. Live smokes: (a) SDR 1080p Hotel Chevalier VMAF 94.545 via composer path; (h) truncated 43s -> AlignmentSpecError fail-loud; (j) unparseable primaries unit contract. Supplementary 4K sweep 9 encodes (5 NVENC VBR + 4 QSV ICQ) exercising Model4K auto-select at scale. 10-shape formal matrix PARTIAL (3/10; 7 canary shapes pending source provisioning).
- **C19 deploy hardening.** Dockerfile `__pycache__` purge + `deploy/deploy-linux-worker.py` post-COPY stale-pyc probe + `TestDeployStalePycProbe` 3/3 PASS + live 12-worker re-deploy clean. BUG-0085 retired.
- **C20 WorkerContext thread-local binding.** `Core/WorkerContext.py` `threading.local()` + `Bind()` at every processing-thread entry + fail-loud `Current()` + `PostEncodeMeasurementService.Probe` strict-mode revert. Wakko QSV Requeue attempt 41156 populates all three attestation columns live from fresh Probe. BUG-0086 deep cause retired.
- **C21 phase-aware stuck-job detection.** `JobPhase` enum + `PhaseDetectorRegistry` + 4 `IPhaseDetector` impls (Setup/Encoding/PostEncode/Verifying); `_IsJobFrozen` + Tier 3 PID liveness folded; ActiveJobs.Phase column via migration. Wakko QSV 13-min demucs no longer false-positive killed.
- **4K streaming Profile rows landed** (Reset 21): STREAMING NVENC Default (1500 kbps VBR / VMAF 91.84) + HQ (2250 kbps VBR / VMAF 94.67) + STREAMING QSV Default (q34 ICQ / VMAF 88.44) + HQ (q30 ICQ / VMAF 93.35); Profile ids 468-471; migration `Add4KStreamingProfiles_2026_07_07.py`; data-sourced from `Docs/Codecs/4K-AV1-Streaming-Sweep-2026-07-06.md`.

**HOW TO USE IT:**
- New profiles / tiers: SQL UPDATE on `Profiles + ProfileThresholds`. No code change.
- Bitrate / ICQ / adequacy / confidence knobs / global QT-off: `/settings` -> Transcoding card. Live edits observed on next admission / decision (db-authority).
- Adding a new job type: create a new flow doc + Slot; register a strategy; enum ProcessingMode; no orchestration mode-branch to touch.
- Reviewing per-bucket VMAF confidence: `/settings` Transcoding card review panel (backed by `VmafConfidenceStatsRepository.GetAllForReview`).
- Un-blocking a stranded QT queue row: `POST /api/QualityTest/Override` with `ForceDisposition IN ('Replace','Reject')`.

**WHAT YOU NEED TO EXECUTE (operator):**
- Confirm close of directive (`## Status` phase Active -> Closed after review of this report).
- Optional: open follow-up directives for BUG-0085 (deploy stale-pyc hardening), BUG-0086 (QSV Requeue audio-attest gap), vmaf-color-and-model-matching, LUFS tolerance reconciliation, __UNRESOLVED__ ProfileName sentinel, and stuck-detector false-positives.
- Optional: memory rewrite for `reference_worker_host_hardware.md` (dot has av1_nvenc capability, not CPU-only).

**CRITERIA VERIFICATION:** all recorded per criterion in `### Verification` above. Contract regression: 126 root-venv PASS + 1 SKIP + 1 FAIL (TestSharedColumnsPopulated -- 41090 pre-existing + 41122/41123 BUG-0086 residue; write-path mechanism verified). 11/11 WebService-venv PASS. Live smokes (a) Reencode+VMAF+Replace (Animaniacs S01E13 41042), (b) StreamCopy checksum+Replace (Adventure Time S10E11 41066), (c) Scanner admission (structural), (d) Requeue new-row (Love Island 41060), (e) Reencode text-sub mov_text (Hotel Chevalier 41078), (f) StreamCopy mkv+SRT mov_text argv (Phineas 41108/41111), (g) PGS drop-with-WARN (Adventure Time 41110), plus Wakko QSV end-to-end + Dot Remux end-to-end fanout.

**DECISIONS I MADE (material engineering choices without operator consult):**
- BUG-0085 root-cause identification via docker-exec parity check (fresh `python3 -c` vs long-lived worker process); superseded prior BUG-0084 StreamCopy-checksum theory.
- Row 41107 + 41124 + 41125 backfilled from same-MFID sibling rows rather than deleted; Disposition stamped `Reject/StaleCodeResidue` for audit clarity.
- All 12 Linux workers re-deployed to HEAD 5c2540a; stale-pyc remediation shipped inline (`find __pycache__ -delete` + `docker compose restart`) rather than filed as separate follow-up.
- New feature/flow docs created at DELIVERING per R13 relax (5 files); Promotions rows added correspondingly.
- BUG-0086 absorbed + closed in Reset 14: post-VERIFYING investigation identified root cause as `Probe` silent-skip on missing ffmpeg/ffprobe binaries (not QSV-Requeue-branch-specific as first theorized). Fix landed same session -- 3-line change in Probe + 2 test updates + 3-row backfill.

**KNOWN GAPS / DEFERRED (all filed):**
- BUG-0085 CLOSED (Reset 15) -- Dockerfile `__pycache__` purge + post-deploy stale-pyc probe live-verified across 12 workers.
- BUG-0086 CLOSED (Reset 14 papered + Reset 16 root-cause fix) -- WorkerContext thread-local binding via `Bind()` at every processing-thread entry; strict-mode `Current()`; live-verified on Wakko QSV attempt 41156.
- **Reset 28 item 13 10-shape smoke matrix -- 4 more shapes DONE from library sources** (2026-07-13): 4k-10bit 3840x2160 (Animaniacs S08E18) VMAF=90.26 4K-model / 96.34 default; anime-cfr 1920x1080 24000/1001 (Harem 01) VMAF=98.05; letterbox-2.35 1920x800 (Sicario) VMAF=65.51; live-action-1080p (The Flash S06E19 intro Tier 3 NVENC) VMAF=69.23, (same intro Tier 5 NVENC) VMAF=69.74, (same intro Tier 5 QSV ICQ q22) VMAF=68.04, (Flash S06E19 mid-episode SS=600 Tier 5 NVENC VBR 5500k) VMAF=**99.23**, (Flash S06E19 mid-episode Tier 5 QSV ICQ q22 on wakko Arc B580) VMAF=**96.65**. Confirms intro sequences with splash effects tank VMAF ~30 points; mid-episode real content easily above 90 at Tier 5 on either encoder. QSV 62% smaller output at ~-2.6 VMAF vs NVENC on same clip. Future smoke methodology: always `-ss 600+` to skip title sequences. Artifacts + reference clips in c:\MediaVortex\Reset28-Smokes\{shape}\. 5 remaining canary shapes NOT IN LIBRARY (SQL-verified 2026-07-13): HDR 4K PQ (no color_transfer=smpte2084 rows), 1080i broadcast (isinterlaced=1 rows are all -mv outputs, no raw sources), Telecined 24p->30i (no candidates), Phone 540p vertical (no portrait rows), 4:2:2 pix_fmt (SELECT DISTINCT pixelformat returns 0 yuv422p*). Escalate to operator: external source provisioning required for these 5 classes.
- Reset 12 fail-loud baseline deep-sweep (1329 hits) -- ratcheted to current state (Reset 28 item 12); per-file line-by-line conversion is out-of-scope multi-day sub-project. Baseline test guards against growth.
- 4K streaming Profile validation on additional content shapes (anime / high-motion / HDR) before promoting to CANARY tier ladder integration.

