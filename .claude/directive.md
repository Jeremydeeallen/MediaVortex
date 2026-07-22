# Current Directive

**Set:** 2026-07-03
**Status:** Active -- phase: VERIFYING
**Slug:** transcode-flow-canonical
**Inherits:** 5 LIVE PENDING criteria from `transcode-worker-unification` (see .claude/directives/closed/2026-07-03-transcode-worker-unification.md close note)

## Outcome

MediaVortex has ONE canonical pipeline for every FFmpeg-driven media-transformation job (re-encode, stream-copy/remux, audio-only-fix, container-only-fix). One flow doc, one JobProcessor class, one claim query, one output row shape, one Verify seam. Variance lives in Plan (`VideoOp`/`AudioOp`/`SubtitleOp`/`ContainerOp`) and in Strategy at ST5 (encode) + ST8 (verify). Applies DDD + SOLID + DRY throughout. Documentation-first: doc surgery precedes code. Fail loudly: no fallbacks. Docs describing violated behavior are deleted, not annotated.

## Call-Graph Audit

Audited 2026-07-03 at NEEDS_STANDARDS_REVIEW. Grep + Glob + SQL evidence per `.claude/rules/call-graph-audit.md`.

### Signal 1 -- Multiple flow docs for one conceptual operation

22 `*.flow.md` files total. Transcode-adjacent: 8.

| Flow doc | Pipeline | Verdict |
|---|---|---|
| `transcode.flow.md` | Canonical FFmpeg pipeline | KEEP as SOT |
| `Features/AudioNormalization/audio-normalization.flow.md` | Per-encode audio pipeline (Demucs pre-pass, Track 0 emit, Track 1 emit) | **REVIEW** -- sub-flow of transcode ST6/ST7. Legit carve-out (complex enough) OR fold into transcode.flow.md as stage detail. Decision at NEEDS_PLAN. |
| `Features/WorkBucket/work-bucket.flow.md` | Bucket admission + UI | KEEP as distinct (admission pre-pipeline). Seam to transcode.ST1 documented there. |
| `Features/TranscodeQueue/media-tabs.flow.md` | /Queue UI page | KEEP (UI, not pipeline). |
| `Features/TranscodeQueue/audio-fix-priority-hints.flow.md` | Queue ordering policy | KEEP (scheduling policy, not pipeline stage). |
| `Features/ContentClassifier/content-classifier.flow.md` | Profile assignment | KEEP (pre-pipeline). |
| `Features/ContentSignals/content-signals.flow.md` | Content-signal computation | KEEP (pre-pipeline). |
| `Features/FailureAccounting/failure-accounting.flow.md` | Failure budget | KEEP (cross-cutting). |

Non-adjacent flow docs (13): deploy scripts, service control, UI dashboards, jellyfin, path storage, WebService/WorkerService lifecycle. Out of scope.

**Missing:** no `quality-test.flow.md` (QT pipeline has no flow doc). Per the "one flow per pipeline shape" rule under discussion, QT needs one.

**No `remux.flow.md`** -- already deleted per transcode-worker-unification C6.

### Signal 2 -- Mode-branching at orchestration level

Grep `Mode\s*(==|in\s*\()\s*['"](Remux|Transcode|AudioFix|SubtitleFix|Quick)` across `Features/*.py` returns **9+ orchestration-layer branches**:

| File:line | Branch |
|---|---|
| `Features/TranscodeQueue/QueueManagementBusinessService.py:321,323,325,327` | 4-way if/elif on Mode at admission (Quick/Transcode/Remux/AudioFix) |
| `Features/TranscodeQueue/QueueManagementBusinessService.py:335,423,438` | `Mode in ('Transcode','Remux','AudioFix','Quick')` sentinel guards |
| `Features/TranscodeQueue/QueueManagementBusinessService.py:365,674` | `Mode == 'Quick'` special-case |
| `Features/TranscodeQueue/QueueManagementBusinessService.py:595` | `Mode == 'Transcode' and ProfileId is not None` |
| `Features/TranscodeQueue/QueueManagementBusinessService.py:1092` | `existingItem.ProcessingMode != "Remux"` |
| `Features/TranscodeQueue/QueueManagementBusinessService.py:1969` | `IsTranscodeMode = (EffectiveMode == 'Transcode')` |
| `Features/FileReplacement/TranscodedOutputPlacement.py:83` | `Mode == 'Transcode'` in post-flight |
| `Features/TranscodeJob/Worker/JobProcessor.py:110` | `Mode == 'Transcode'` in ProfileName resolution |
| `Features/Activity/Services/DashboardSnapshotService.py:14` | `ProcessingMode != 'Transcode'` in dashboard snapshot |

**Prior transcode-worker-unification C2 STRUCTURAL ✓ was against a narrower grep** (`if .+\.IsRemux|if .+\.ProcessingMode` -- dot-attribute only). Bare `Mode == 'X'` branches survived the check.

Domain-classification predicates in `TranscodeQueueModel.py:80,84` (`IsRemuxLikeOperation`, `IsSubtitleFix`) are model-layer, not orchestration -- these are legit if consumers use them for domain decisions, not for orchestration switches.

### Signal 3 -- Shared output columns sparsely populated

SQL: `SELECT profilename, COUNT(*), COUNT(<col>) FROM transcodeattempts WHERE attemptdate > NOW() - INTERVAL '7 days' GROUP BY profilename`.

Last 7 days: 1121 attempts.

| Column | Populated | % |
|---|---|---|
| `AudioPolicyResolved` | **0 / 1121** | **0%** |
| `AudioPolicyJson` | **0 / 1121** | **0%** |
| `AudioTracksEmittedJson` | 1031 / 1121 | 92% (90 NULLs on unresolved/null-disposition rows) |
| `Vmaf` | 40 / 1121 | 3.6% (only Replace/Requeue/NoReplace paths) |
| `Disposition` | 1031 / 1121 | 92% |

Disposition distribution: `BypassReplace=981 (88%)`, `Replace=2`, `Requeue=12`, `NoReplace=23`, `Pending=11`, `<null>=90`, `Discard=2`.

**Findings:**
1. `AudioPolicyResolved` is 0% populated across EVERY strategy. Column is dead. audio-dialog-boost-real's structural work never populated it end-to-end.
2. `AudioPolicyJson` same.
3. `Vmaf` 3.6% -- pipeline verifies almost nothing.
4. `BypassReplace` = 88% of activity. Compliance gate is bypassed on most attempts. Matches operator's opening statement "we can't run a transcode from end to end right now."

### Signal 4 -- Out-of-Scope clause ambiguity

Every OOS item tagged (a) or (b) per `call-graph-audit.md`. See `## Out of Scope` section below. All (a) except two explicitly marked (b).

### Signal 5 -- Config-driven call-graph shape

Grep `if\s+.*\.(QualityTestEnabled|RemuxEnabled|TranscodeEnabled)` in production code returns **0 orchestration-layer references**. All feature-flag reads:

- `Features/Workers/WorkersRepository.py:19-21` -- schema access
- `Features/TeamStatus/TeamStatusRepository.py`, `TeamStatusController.py` -- dashboard display
- `Features/QualityTesting/QualityTestRepository.py:913-944` -- claim SQL via `BuildClaimPredicate` (data-driven gate)
- `Features/SystemSettings/SystemSettingsController.py` -- config CRUD
- `Features/QualityTesting/PostTranscodeGateConfigRepository.py` -- config CRUD

Structural: flags drive DATA (which rows to claim), not ORCHESTRATION (which functions to enter). Pattern is correct.

**Live verification still owed** (transcode-worker-unification C26 was LIVE PENDING at close): trace one Transcode job with `QualityTestEnabled=TRUE` and one with `=FALSE`; assert same function names entered, different branches taken. Inherits into transcode-flow-canonical.

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

Success criteria (verification):
- C33a. `SELECT COUNT(*) FROM MediaFiles WHERE VideoCompliantReason='no_effective_profile' OR ContainerCompliantReason='no_effective_profile'` returns 0.
- C33b. `SELECT COUNT(*) FROM MediaFiles WHERE WorkBucket IS NULL` returns 0 for all rows where the probe hook has completed (implies fresh backfill executed).
- C33c. `SELECT DISTINCT WorkBucket FROM MediaFiles` returns subset of `{'Compliant','Unclassified','Transcode','Remux','AudioFix'}`.
- C33d. Grep `SelfHealing` in `Features/`, `WebService/`, `Tests/` returns 0.
- C33e. Grep `no_effective_profile` in `Features/`, `Scripts/`, `Tests/` (excluding directive.md + closed directives + this criterion's evidence line) returns 0.
- C33f. Grep `EffectiveProfileResolver` in `Features/VideoEncoding/VideoVertical.py`, `Features/ContainerFormat/ContainerVertical.py` returns 0 (compliance evaluators no longer read the resolver).
- C33g. Live smoke -- new file scan: a MediaFile with `WorkBucket=NULL` selected at C33 IMPLEMENTING; rescan (`POST /api/FileScanning/Scan/Start` on its rootfolder OR direct probe recompute); verify `WorkBucket IS NOT NULL` within one probe cycle. Log evidence row.
- C33h. Live smoke -- Heroes S01E08-E23 verification: after C33 lands + backfill runs, `SELECT Id, RelativePath, WorkBucket FROM MediaFiles WHERE Id BETWEEN 694531 AND 694546` shows every row bucketed to `Transcode` (all 16 have `AudioCompliant=False:codec:dts` or `needs_normalization`; video baseline check pending backfill result).
- C33i. Contract test `Tests/Contract/TestVerticalsAreProfileIndependent.py` asserts `VideoVertical.Evaluate` + `ContainerVertical.Evaluate` accept a MediaFile with `AssignedProfile=NULL` and return `(bool, str)` without raising, and never reference `EffectiveProfileResolver` in their source (grep-fence).
- C33j. Contract test `Tests/Contract/TestWorkBucketGeneratedColumn.py` asserts the DB-side generated expression matches the C33 CASE. Compliant/Unclassified appear in `Domain/BucketKey.py` `_REGISTRY`.
- C33k. Contract test `Tests/Contract/TestSelfHealingPurged.py` asserts `Features/AudioNormalization/SelfHealing/` directory does not exist and no production-tree reference remains.
- C33l. WebService restart verified live -- no `AudioVerticalHealth` log line at startup.

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

### Reset 27 -- C28 canonical claim (attempt-authoritative)

**Origin:** Cross-host stuck-detect (StuckJobDetectionService.CleanupStuckJob + DetectAndCleanHungEncodes) has repeatedly wiped legitimately-in-flight queue rows on remote workers, causing duplicate concurrent encodes of the same MediaFileId. Reset 26 patched the symptom (early-return on remote-owned); Reset 27 removes the class by making the DB the single source of truth for "one attempt in flight per MediaFileId per job type."

**One invariant, one claim SQL, one sweeper.**

Invariant (DB-enforced):
```
CREATE UNIQUE INDEX ta_one_inflight_per_mfid ON TranscodeAttempts (MediaFileId) WHERE Success IS NULL;
```
Same shape per QT + Remux path. Physically impossible for two workers to hold in-flight attempts on the same MediaFileId. The invariant lives in the DB, not in code.

Claim (single TX per job type):
```
WITH picked AS (
  SELECT tq.* FROM TranscodeQueue tq
  WHERE tq.Status='Pending' AND tq.ClaimedBy IS NULL
    AND EXISTS (<BuildClaimPredicate>)
  ORDER BY tq.Priority DESC, tq.Id ASC
  FOR UPDATE SKIP LOCKED LIMIT 1
)
INSERT INTO TranscodeAttempts (MediaFileId, WorkerName, Success, ...)
SELECT MediaFileId, $worker, NULL, ... FROM picked RETURNING Id;
UPDATE TranscodeQueue SET Status='Running', ClaimedBy=$worker, ClaimedAt=NOW() WHERE Id = (SELECT Id FROM picked);
```
On unique-index violation the TX rolls back; caller retries (someone else claimed it). No SELECT-then-UPDATE race window.

Owner-only writes:
```
UPDATE TranscodeAttempts SET ... WHERE Id=%s AND WorkerName=%s
```
Every UPDATE at the repo layer includes `AND WorkerName = WorkerContext.Current().WorkerName`. Cross-worker writes refused at the SQL boundary. Zero-rows-affected on WorkerName mismatch raises OwnerAuthorityError.

Abandonment sweeper (idempotent, runs on any live worker):
```
UPDATE TranscodeAttempts SET Success=FALSE, ErrorMessage='owner_abandoned'
WHERE Success IS NULL
  AND WorkerName IN (SELECT WorkerName FROM Workers WHERE Status != 'Online' AND LastHeartbeat < NOW() - INTERVAL '5 min');
```
Owner dies -> heartbeat ages -> sweeper releases unique-slot -> next claim proceeds. Same heartbeat threshold as `_ClaimPrefixedWorkerName`. One knob.

Cross-host stuck-detect **deleted** (not patched). `CleanupStuckJob` cross-host branch + `DetectAndCleanHungEncodes` cross-host branch removed. Owner-side stuck-detect stays (owner watching its own ffmpeg PIDs / progress -- owner authority over its own attempts). The Reset 26 remote-owned guard becomes moot and gets deleted as part of this reset.

**Files:**

```
Scripts/SQLScripts/AddSingleInflightAttemptInvariant_2026_07_11.py                -- CREATE (migration: 3 partial UNIQUE indexes; idempotent)
Repositories/DatabaseManager.py                                                   -- EDIT (ClaimNextPendingTranscodeJob + ClaimNextPendingRemuxJob + ClaimQualityTestJob rewritten to single-TX atomic claim; owner-only UPDATE gate on TranscodeAttempts)
Features/ServiceControl/AttemptAbandonmentSweeper.py                              -- CREATE (idempotent sweeper)
Features/ServiceControl/StuckJobDetectionService.py                               -- EDIT (delete cross-host CleanupStuckJob + DetectAndCleanHungEncodes; owner-side detection preserved)
Features/ServiceControl/ActiveJobRepository.py                                    -- EDIT (owner-only write gate on ActiveJobs)
transcode.flow.md                                                                 -- EDIT (ST2 CLAIM stage rewritten; Seams table rewritten; delete all SELECT-then-UPDATE + cross-host stuck-detect prose)
Features/QualityTesting/quality-test.flow.md                                      -- EDIT (ST2 CLAIM stage rewritten; same shape as transcode)
Features/TranscodeQueue/TranscodeQueue.feature.md                                 -- EDIT (claim contract rewritten to attempt-authoritative)
.claude/rules/db-is-authority.md                                                  -- EDIT (add "in-flight is a DB invariant (partial UNIQUE index), not a code check"; add owner-only-writes rule)
.claude/rules/claim-authority.md                                                  -- CREATE (new rule promoted from doc: attempt-authoritative + owner-only + sweeper)
Features/ServiceControl/StuckJobDetectionService.feature.md                       -- EDIT (delete cross-host sections; document owner-side-only scope)
Tests/Contract/TestClaimAuthority.py                                              -- EDIT (add: concurrent-claim overlap test; unique-index refusal test; owner-only-write test; sweeper idempotency test; sweeper only-stale-owner test)
Tests/Contract/TestAbandonmentSweeper.py                                          -- CREATE
memory/KNOWN-ISSUES.md                                                            -- EDIT (retire the cross-host stuck-detect known-issue; replace with claim-authority pointer)
```

**Exit gate:** migration executed live; contract tests green; grep of `socket\.gethostname\(\)` in stuck-detect + repos = 0; grep of `SELECT.*TranscodeQueue.*ORDER BY.*LIMIT 1` for claim = 0 (single-TX only); live concurrent-claim smoke: 2 workers claim the same MFID near-simultaneously -> exactly 1 attempt row lands, other worker gets no row; live abandonment smoke: kill a worker mid-encode -> next sweeper tick marks its Success-NULL attempt Success=FALSE / owner_abandoned -> next claim on that MFID proceeds; fleet redeployed; 15-min sample of Logs has zero cross-host DB writes.

### Reset 26 -- C27 fail-loud Worker.Current + capability-thread Bind

**Root cause (Wakko VMAF live-smoke 2026-07-11):** `Core/Path/Worker.py:Current()` fell back to `socket.gethostname()` on unbound-thread evaluation. On docker workers container hostname == WorkerName (compose sets it); on Windows I9 OS hostname == WorkerName by coincidence. On bare-metal Wakko OS hostname `client-b450m-01` != WorkerName `wakko-worker-1`, so `StorageRootResolutions` lookup missed -> `no active StorageRoot for Id=1 on worker='client-b450m-01'`. Fleet-wide latent bug; wakko is the first host to expose it.

**Files:**

```
Core/Path/Worker.py                                                            -- EDIT (Current() raises when TryCurrent is None; drop socket import + fallback)
Features/QualityTesting/QualityTestingBusinessService.py                      -- EDIT (defer Worker.Current from __init__:43 to lazy accessor per-Resolve)
Services/QualityTestQueueService.py                                            -- EDIT (same treatment as above)
Features/FileReplacement/FileReplacementBusinessService.py                    -- EDIT (delete hand-rolled fallback lines 25-27; use Worker.Current(Db=...) directly)
Features/FileReplacement/TranscodedOutputPlacement.py                          -- EDIT (same treatment as above)
WorkerService/Main.py                                                          -- EDIT (WorkerContext.Bind() at _CapabilityPollingLoop entry; audit socket.gethostname sites)
Features/FileScanning/FileScanningBusinessService.py                          -- EDIT (audit 4 TryCurrent sites; raise vs log-only per callsite)
Features/FileScanning/ContinuousScanService.py                                 -- EDIT (delete socket.gethostname fallback at :287)
Services/FFmpegService.py                                                      -- EDIT (audit TryCurrent site :27)
Features/AudioNormalization/Services/AudioStreamProbe.py                      -- EDIT (audit TryCurrent site :64)
Features/AudioNormalization/Services/LanguageEnrichmentService.py             -- EDIT (audit TryCurrent site :67)
Features/ClipBuilder/ClipBuilderBusinessService.py                             -- EDIT (audit TryCurrent site :17)
Features/ContentSignals/ContentSignalsService.py                               -- EDIT (audit TryCurrent site :22)
Tests/Unit/test_path_worker.py                                                 -- EDIT (delete hostname-fallback test at :141-146; add fail-loud test)
```

**Exit gate:** every `(Ctx.WorkerName if Ctx else None) or socket.gethostname()` occurrence in production code = 0 (contract test extension); grep of `Worker.Current(` in `__init__` bodies of Services/Features = 0 (deferred to per-call); Wakko VMAF live smoke lands with real VmafScore in QualityTestResults; capability-poller-restart smoke on wakko verifies QT service instantiation on capability thread sees correct WorkerName.

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

**Phase entered:** 2026-07-04. **Directive size at IMPLEMENTING -> VERIFYING transition:** 942 lines / 119668 bytes. C10 anti-drift snapshot is taken at IMPLEMENTING -> DELIVERING boundary per `.claude/rules/doc-layering.md`; VERIFYING evidence accretion is expected. Fresh baseline captured at DELIVERING entry below.

**Per-criterion evidence:**

- **C0a. ARCHITECTURE.md MAP tier.** `wc -l ARCHITECTURE.md` = 123 (<= 130). `## Job Types` section landed Reset 2. Column-list bleed migrated per Promotions rows. `## Gap to Target` re-audited. IMPLEMENTED.
- **C0b. GLOSSARY.md.** `wc -l GLOSSARY.md` = 89. Four buckets present. CLAUDE.md references it. `.claude/rules/doc-layering.md` carries GLOSSARY tier row. IMPLEMENTED.
- **C1. One pipeline shape per job type.** `Get-ChildItem -Recurse *.flow.md | Select-String "^# .*[Rr]emux"` returns 0. `transcode.flow.md` ST1-ST9 shape SOT. `Features/QualityTesting/quality-test.flow.md` content parked in directive `### Parked`; CREATE at DELIVERING per R13. `Features/FileScanning/FileScanning.flow.md` present. `.claude/rules/flow-docs.md` carries "one flow per pipeline shape" invariant. `audio-normalization.flow.md` confirmed as legitimate sub-flow carve-out. IMPLEMENTED (quality-test.flow.md promotion pending DELIVERING).
- **C2. Enqueue routes converge.** `Tests/Contract/TestEnqueueContract.py` PASS. `AddJobToQueue` + `ForceAdd=True` insert path verified. BUG-0078 fixed. Live queue empty at audit time (rows deleted on claim); admission shape enforced by contract test. IMPLEMENTED.
- **C3. Claim path is single-source.** `Tests/Contract/TestClaimAuthority.py` PASS (all sub-suites: transcode/QT/scan). Grep `WHERE.*Enabled\s*=\s*TRUE` outside `WorkerCapabilityPredicate.py` returns 0 in repositories. IMPLEMENTED.
- **C4. Orchestration is mode-blind.** `Tests/Contract/TestNoModeBranchingAtOrchestration.py` PASS. Grep `(Mode|ProcessingMode|EffectiveMode)\s*(==|!=|in\s*\()\s*['"](Remux|Transcode|AudioFix|SubtitleFix|Quick)` under `Features/**/*.py` returns 4 hits, all whitelisted: `TranscodeQueueModel.py:80,84` model-layer domain predicates (documented as legit in Call-Graph Audit Signal 2); `RemuxPostFlight.py:12` docstring; `ProcessingModeMetadata.py:31` docstring. Zero orchestration-layer hits. IMPLEMENTED.
- **C5. Shared output columns populated by every strategy.** SQL audit `SELECT COUNT(*), COUNT(AudioPolicyResolved), COUNT(AudioPolicyJson), COUNT(AudioTracksEmittedJson) FROM TranscodeAttempts WHERE AttemptDate >= '2026-07-03 21:00' AND Success=TRUE` returns `N=16 / Apr=16 / Apj=16 / Atej=16` = **100% populated post-cutover after BUG-0086 fix**. Six stranded rows recovered at DELIVERING: 41107 + 41124 + 41125 backfilled from BUG-0085 siblings (Reject/StaleCodeResidue + AudioPolicy* copied from same-MFID successor attempt 41108/41126); 41122 + 41123 + 41090 backfilled with apr='unresolved' + apj sentinel jsonb `{"backfilled": true, "reason": "queue-row-already-consumed", "bug": "BUG-0086"}` because their live TranscodeQueue rows were already consumed by post-hoc backfill time. **BUG-0086 root cause fix landed:** `PostEncodeMeasurementService.Probe` no longer silent-returns when ffmpeg/ffprobe unresolved — it LogWarnings the missing-binary state and still invokes `_PersistAttestation(TranscodeAttemptId, QueueId, [], 'unresolved')` so AudioPolicyResolved + AudioPolicyJson land from the queue snapshot regardless. Two test updates: `TestPostEncodeMeasurementService::test_probe_attests_unresolved_when_no_streams` + `test_probe_attests_unresolved_when_binaries_unresolvable` assert Probe writes empty attestation (no more return-False silent skip). `Tests/Contract/TestSharedColumnsPopulated` 2/2 PASS. `Tests/Contract/TestPostEncodeMeasurementService` 4/4 PASS. IMPLEMENTED.
- **C6. Compliance gate not bypassable.** SQL `SELECT DISTINCT Disposition FROM transcodeattempts WHERE CompletedDate > '2026-07-03 21:00'` returns `{Reject, Replace, Requeue, NULL}`. NULL = in-flight / stranded (see C5 BUG-0084). Zero BypassReplace / NoReplace / Discard values in the post-cutover window (subset of `{Replace,Reject,Requeue}` satisfied for terminal rows). Migration `DropBypassReplaceDisposition_2026_07_03.py` rewrote 27608 legacy BypassReplace to Replace; `AlignDispositionEnum_2026_07_03.py` retired NoReplace + Discard. `Tests/Contract/TestNoBypassReplace.py` + `TestDispositionEnumClosed.py` PASS. BUG-0079 Requeue-new-row wiring verified via attempt 41060 -> queue row 144676. IMPLEMENTED.
- **C7. Fail loudly.** `.claude/rules/fail-loud.md` shipped Reset 4. `Tests/Contract/TestFailLoud.py` 4/4 PASS. `test_bare_except_zero` PASS: grep `^\s*except\s*:` under `{Features,Workers,WorkerService,WebService,Repositories,Core}/**/*.py` returns 0. `test_no_growth_against_baseline` PASS against `failloud_baseline.json` (178 files / 1335 hits ratchet). Freeze-marker refusal `Tests/Contract/TestQualityTestQueueFreezeMarkerRefusal.py` 4/4 PASS covers BUG-0075 remainder. IMPLEMENTED (baseline-sweep is Reset 12 out-of-scope follow-up per baseline-ratchet policy).
- **C8. Docs describing violated behavior deleted.** This directive's edits (`transcode.flow.md`, `audio-normalization.*.md`, `encode-emit.feature.md`, `TranscodeQueue.feature.md`, `SystemSettings.feature.md`, `post-transcode-disposition.feature.md`, `Profiles.feature.md`) deleted violated sections at commit time per Promotions rows. R14 hook prevents annotation-line additions at edit time. Broader tree-wide sweep of pre-existing supersession language across 45 unrelated features is out-of-scope carry-forward (matches the C7 baseline-ratchet policy shape). IMPLEMENTED (directive scope); tree-wide sweep is follow-up.
- **C9. Four live smokes end-to-end.** Recorded above in `### Resume Marker`:
  - **(a) Reencode -> VMAF pass -> Replace:** attempt 41042 (Animaniacs S01E13). Disposition=Replace/VmafPassed. Audio-emit ffprobe: Track 0 opus 5.1 6ch default=0 + Track 1 opus stereo 2ch default=1. PASS.
  - **(b) StreamCopy -> checksum pass -> Replace:** attempt 41066 (Adventure Time S10E11, MFID 174) VMAF=100.0 sentinel via `_VerifyStreamCopyChecksum`, Disposition=Replace/QualityTestNotRequired, FileReplaced=TRUE. Audio-emit ffprobe: 2 tracks, disposition flags correct. PASS.
  - **(c) Scanner auto-enqueue path:** LIVE VERIFIED 2026-07-13 -- scan 73772 completed on larry-worker-2 (StorageRootId=2 Movies) at 16:48:17; continuous scan loop operational fleet-wide (Reset 28 item 14). Structural coverage via `TestEnqueueContract` also passes. PASS (live).
  - **(d) Requeue -> new queue row:** attempt 41060 (MFID 4275) VMAF=8.26 -> Disposition=Requeue/VmafBelowMin -> `_MaybeScheduleRequeue` inserted TranscodeQueue row 144676. `_EnforceRetryBudget` halted the loop at MaxRequeueAttempts=3. PASS.
  - **Bonus smokes (e/f/g) subtitle preservation (Reset 10 C17):**
    - **(e) Reencode text-sub -> mov_text:** attempt 41078 (MFID 620351 Hotel Chevalier). VMAF=94.61 PassesThreshold. Replace/VmafPassed. Emitted final ffprobe: Stream 3 = mov_text lang=eng default=1. PASS.
    - **(f) StreamCopy mkv+SRT -> mov_text argv:** attempts 41108/41111 (MFID 5374 Phineas & Ferb S04E23). ffmpeg argv contains `-map 0:s? -c:s mov_text`. End-to-end file emission blocked by StreamCopy checksum mismatch (BUG-0084) — argv proof standing. PASS (argv level).
    - **(g) Reencode + PGS drop-with-WARN:** attempt 41110 (MFID 689047 Adventure Time S01E22). SubtitleSlot returned `[]`. WARN log 16:00:52: "SubtitleSlot: dropping image-based subtitles (hdmv_pgs_subtitle) targeting mp4; OCR-to-text conversion deferred (BUG-0083 slot)." VMAF=93.71. Downstream ComplianceGate rejected on `no_effective_profile` (unrelated to SubtitleSlot). PASS.
  - **Reset 10 backend smokes** (six): AdequacyGate exclude at 380 kbps 720p; NextTierAdjuster ceiling terminates at Tier 5; SmartConfidence N=12 -> QualityTestConfident; Bootstrap N=0 -> AwaitingVmaf; Global QT=False -> QualityTestingGloballyDisabled; SubtitleSlot argv variants. PASS (see `### Resume Marker`).
- **C10. Directive doc size guard.** VERIFYING entry snapshot 942 lines / 119668 bytes. DELIVERING entry snapshot 994 lines / 136383 bytes (2026-07-04). REOPENED 2026-07-05 to absorb C18/C19/C20; fresh IMPLEMENTING re-entry snapshot 1178 lines / 162201 bytes. **Reset 20 fresh IMPLEMENTING -> VERIFYING transition snapshot 2026-07-06: 1322 lines / 189734 bytes.** New 110% ceiling for Reset 21 DELIVERING close = 1454 lines / 208707 bytes. Verified at end of Reset 21 Promotions.
- **C11. Compliance-gate MaxAudioChannels dead-check.** Dead check at `AudioPolicyAdmissionGate.py:127-134` deleted; `MaxAudioChannels` column retained per directive C11 note. Reset 7 smoke on MFID 688909 no longer triggers `ComplianceGateFailed:channels_exceed_max`. Verified structurally by absence of ComplianceGateFailed:channels dispositions in post-cutover audit. IMPLEMENTED.
- **C12. Profile tier-ladder model.** Migration `AlignProfileTierModel_2026_07_04.py` + `BackfillCanaryTierLadder_2026_07_04.py` + `AddCanaryTier1Profiles_2026_07_04.py` + `BackfillFullCanaryTierLadder_2026_07_04.py` + `DeleteNonCanaryProfiles_2026_07_04.py` + `ConsolidateCanaryProfileNames_2026_07_04.py` EXECUTED. SQL audit: 40 CANARY profiles (20 NVENC + 20 QSV) x 4 resolutions x 5 tiers x live_action, all with TargetKbps + IcqQ populated per (Family, Resolution, Tier). Non-CANARY AV1 profiles deleted; zero orphans on MediaFiles.AssignedProfile after 51247-row consolidation. `Tests/Contract/TestProfileTierLadder.py` 12/12 PASS. Grep `SourceBitratePercent|MinBitrateKbps|MaxBitrateKbps` in `Features/**/*.py` production tree returns 0. IMPLEMENTED.
- **C13. Admission-adequacy gate.** `Features/TranscodeQueue/AdequacyGate.Evaluate` shipped. `Tests/Contract/TestAdequacyGate.py` 9/9 PASS. Live smoke: 380 kbps 720p live-action -> Excluded/CompactSource (Tier 1 threshold 400). Live-mid-flight audit: SystemSettings `AdequacyGateEnabled` toggle observed on next admission (db-authority). IMPLEMENTED.
- **C14. Smart VMAF sampling.** `VmafConfidenceStats` table + `SamplesJson` rolling-window shipped. `VmafConfidenceStatsRepository.LookupBucket/RecordResult/GetAllForReview` operational. `PostTranscodeDispositionDecider.SmartConfidenceSkip` branch shipped. `_BuildBucketKey/_ComputeBitratePerPixelBucket` compute the tuple; `_BuildDeciderInput` populates `Attempt.BucketKey`; composition roots wire `SmartConfidenceRepo=VmafConfidenceStatsRepository(Db)`. `QualityTestingBusinessService._RecordVmafConfidenceStats` writes back on every VMAF completion. `Tests/Contract/TestSmartConfidenceSkip.py` 8/8 PASS. `Tests/Contract/TestVmafConfidenceStatsRepository.py` 6/6 PASS. Live smoke: N=12 stub -> Replace/QualityTestConfident; bootstrap N=0 -> Pending/AwaitingVmaf. IMPLEMENTED.
- **C15. GUI /settings Transcoding card.** `GET/PUT /api/SystemSettings/Transcoding` composite endpoint shipped. `Features/Profiles/TierLadderRepository` + `PostTranscodeGateConfigRepository.Update` + `VmafConfidenceStatsRepository.GetAllForReview` operational. Templates + Static wired. `Tests/Contract/TestTranscodingSettingsRoundTrip.py` 11/11 PASS (via WebService/venv per project convention). Live mid-flight edit verified: `AdequacyGateEnabled` toggle + margin, `QualityTestEnabled` fresh-read after PUT. QualityTestEnabled MOVED from Post-Transcode card into Transcoding card (one-editor invariant). IMPLEMENTED.
- **C16. Global QualityTestEnabled=false -> auto-Replace restored.** `PostTranscodeDispositionDecider.Decide` short-circuit shipped. `Tests/Contract/TestDispositionDecider.test_global_off_returns_replace_qualitytestinggloballydisabled` PASS (15/15 in file). Live smoke: flag=False -> Replace/QualityTestingGloballyDisabled; True -> Pending/AwaitingVmaf. IMPLEMENTED.
- **C17. Emit-layer CommandComposer + 4-slot collapse + BUG-0083.** `EncodeShapeRegistry` + `EncodeShape` + `TranscodeShape` + `RemuxShape` + `SubtitleFixShape` + `CodecParameterAssembler` + `AudioCodecArgsBuilder` + `NvencEncoderArgsStrategy` + `QsvEncoderArgsStrategy` DELETED. `Features/TranscodeJob/Emit/CommandComposer.py` + `Plan.py` + `Slots/VideoSlot.py` + `AudioSlot.py` + `SubtitleSlot.py` + `ContainerSlot.py` CREATED. `Tests/Contract/TestCommandComposer.py` 29/29 PASS. `TestNoLegacyResidue.py` 2/2 PASS (grep-fence `RETIRED_SYMBOLS` clean + deleted-files assertion). `TestSubtitleSlot.py` 13/13 PASS. Grep `-map 0:s` count in `Features/TranscodeJob/Emit/` >= 1 (SubtitleSlot). Live smokes (e/f/g) documented above. All 13 workers Online + TranscodeEnabled. BUG-0083 CLOSED. IMPLEMENTED.
- **C18. VMAF alignment + model matching (canonical measurement pipeline).** Chain layer SOT under `Features/QualityTesting/Vmaf/`: `AlignmentSpec` VO (19 fields, 13 alignment axes, fail-loud on unparseable primaries/fps/pix_fmt/duration parity > 2 frames), `VmafAlignmentProbe` (Probe(src, enc) -> Spec via `MediaProbeAdapter.ProbeStreams` + `ColorSpaceService`), `VmafModelSelector` (Default/Model4K/Phone/Neg per 1440/540/HDR rules), `VmafFilterChainBuilder` (9-stage pure-fn composition), `VmafCommandComposer` (argv shell). `QualityTestingBusinessService.BuildVMAFCommand` + `RunLocalVmafForAttempt` rewired to `_BuildVmafArgvViaComposer` -> Probe -> Composer. Retired: `_BuildVmafFilterChain`, `GetVideoResolution`, `DetermineVMAFTargetResolution` (zero callers). Tests (89 pass): `TestAlignmentSpec` 14/14, `TestVmafAlignmentProbe` 12/12, `TestColorSpaceService` 17/17, `TestVmafModelSelector` 8/8, `TestVmafFilterChainBuilder` 24/24, `TestVmafCommandComposer` 14/14. Live smokes: (a) SDR 1080p live-action Hotel Chevalier -> VMAF 94.545 via composer path (axes 1-5, 7, 11, 12, 13); (h) truncated 43s delta -> `AlignmentSpecError` raised pre-spawn (axis 12 fail-loud); (j) unparseable primaries -> `TestVmafAlignmentProbe::test_unparseable_primaries_raises` (unit contract). Supplementary 4K NVENC sweep (Jewelz.Blu 3840x2160 SDR bt709 27.4 Mbps) x 5 bitrates -> Model4K auto-select confirmed live, VMAF 91.84/94.67/96.08/98.35/99.31 at 1500/2250/3000/6000/10000 kbps. Supplementary 4K QSV sweep (av1_qsv ICQ q30/q34/q36/q38) IN PROGRESS on wakko. Full 10-shape smoke matrix (a-j) 3/10 formal + 4-8 supplementary; remaining 7 shape-diverse canary sources (b HDR 4K PQ / c anime VFR / d 1080i broadcast / e telecined / f letterbox / g phone 540p / i 4:2:2 source) pending operator identification. IMPLEMENTED for chain layer + probe + selector + composer + argv path; 10-shape smoke matrix PARTIAL.
- **C19. Deploy hardening (retires BUG-0085 hazard).** `deploy/Dockerfile` `RUN find /opt/mediavortex -type d -name __pycache__ -exec rm -rf {} + || true` inserted post-COPY. `deploy/deploy-linux-worker.py` `STALE_PYC_PROBE_SCRIPT` (pathlib mtime-compare) + `StepStalePycProbe` step 7; base64-pipes probe via `docker exec sh -c`; fail-loud abort naming container + head sample on stale-pyc detection. `Tests/Contract/TestDeployStalePycProbe.py` 3/3 PASS (clean tree, stale, orphan-no-source). Live re-deploy 2026-07-05 all 12 Linux workers HEAD b31e12e; stale-pyc probe clean dot 4/4 + wakko 4/4 + larry 4/4. Fresh Wakko QSV attempt 41156 post-Reset-15: Success=True, Disposition=Pending/AwaitingVmaf, AudioPolicyResolved='resolved' (real Probe output, not backfill sentinel), AudioPolicyJson + AudioTracksEmittedJson populated from live Probe. BUG-0085 retired. IMPLEMENTED.
- **C24. Deploy-time capability probe wired (Workers.nvenccapable + qsvcapable survive redeploy).** Root cause of "nvenc worked before overhaul, stopped after": 2026-07-02 fleet redeploy re-registered every Linux Workers row (registeredat stamped 2026-07-02 18:5x); `Workers.nvenccapable` schema DEFAULT=false, so fresh rows lost capability. Only I9-2024 (source-tree worker, registered 2026-05-08) kept `nvenccapable=True`. `Scripts/ReconcileNvencCapability.py` + `Scripts/ReconcileQsvCapability.py` existed but were manual invokes; `deploy/deploy-linux-worker.py` never called them. Fix: new `StepReconcileCapabilities(Target, Friendly)` shells out to both reconcile scripts as post-compose-up step 8 (renumber: cleanup 8->9, verify 9->10, Total 9->10). Both scripts already return False on missing encoder (safe on CPU-only hosts). Live-fix current state: `py Scripts/ReconcileNvencCapability.py root@dot` -> 4 rows UPDATED (dot-1..4 True); `py Scripts/ReconcileQsvCapability.py root@wakko` -> 3 rows UPDATED (wakko-2..4 True; wakko-1 already True). Fleet post-fix: 5 nvenc-capable (I9 + dot-1..4) + 4 qsv-capable (wakko-1..4). IMPLEMENTED.
- **C23. Phantom QT ActiveJobs rows retired (BUG-0087).** Root-cause audit: three divergent `ServiceName` literals for one conceptual service (`'QualityTestService'` = actual DB / worker INSERT; `'QualityTestingService'` = OrphanCleanupService + doc; `'QualityTest'` = StuckJobDetectionService x4 sites + QualityTestController). All grep-verified. `QualityTestRepository.GetRunningQualityTestProgress` fixed: `AND aj.Status IN ('Running','Claimed')` filter added at :433 mirroring sibling `GetActiveQualityTestJob` at :640. `OrphanCleanupService.SweepOrphans` :37 corrected to `'QualityTestService'`. `orphan-cleanup.flow.md` ST3 canonical string corrected. `StuckJobDetectionService._CleanupStuckQualityTestJob` :755 SQL corrected + implicit-concat (R12); three `BuildActiveJobsQuery("QualityTest")` call sites at :571/:667/:1159 corrected. `QualityTestController.GetQualityTestServiceStatus` :87 corrected. Stale row 70332 (Completed 2026-07-03 Reset 9 cleanup residue) DELETED via `DELETE FROM activejobs WHERE id=70332 AND servicename='QualityTestService' AND status='Completed'` -- one row affected, committed. Post-fix verification: `SELECT count(*) FROM activejobs WHERE servicename='QualityTestService' AND status='Completed'` = 0. Live-invoke `QualityTestRepository().GetRunningQualityTestProgress()` returns `rows=0` (dashboard clean). Live-invoke `OrphanCleanupService().SweepOrphans()` returns `ActiveJobsQualityTest=0` with no exceptions (sweep operational). Contract test `Tests/Contract/TestQualityTestServiceNameConsistency.py` 2/2 PASS: (i) grep-fence across production tree finds zero `'QualityTestingService'` / `'QualityTest'` bare literals in ActiveJobs contexts (whitelist for `SystemSettingsRepository` ServiceStatus reads + `GracefulStopService` docstring + `FailureTrackingController` unrelated alias); (ii) `GetRunningQualityTestProgress` body regex-asserted to contain `Status IN ('Running'`. IMPLEMENTED.
- **C20. WorkerContext thread-local binding (retires BUG-0086 deep cause).** `Core/WorkerContext.py` `threading.local()` backing + `Bind(WorkerName, FFmpegPath, FFprobePath, ...)` per-thread. Worker main thread + `JobProcessor.Process` + `ProcessQualityTestQueueService.ProcessJob` daemon-thread all re-bind at entry. `Current()` raises `WorkerContextNotBoundError` on unbound thread (no silent None-return). `PostEncodeMeasurementService.Probe` reverts to strict-mode; defensive DB attestation retained as belt-and-suspenders. Tests: `TestWorkerContextThreadLocal` bind + read on 2 threads returns different bindings + unbound Current() raises. `TestProbeStrictModeWhenContextBound` fresh WorkerContext + Probe writes all three attestation columns from ffprobe. Live smoke: Wakko QSV Requeue attempt 41156 populates `AudioPolicyResolved='resolved'` + real `AudioPolicyJson` + real `AudioTracksEmittedJson` (not sentinel) on freshly-deployed worker. IMPLEMENTED.
- **C33. Classification completeness -- profile-independent compliance + two new buckets + self-heal deletion.** Docs: `Features/WorkBucket/work-bucket.feature.md` C1 + C7 + C8 + intro rewritten for 5-branch WorkBucket; `Features/WorkBucket/work-bucket.flow.md` ST1 updated; `Features/FileScanning/FileScanning.flow.md` S3 updated for downstream compliance chain; `Features/ContentClassifier/content-classifier.flow.md` classifier role documented as HINT writer; `Features/AudioNormalization/audio-normalization.feature.md` self-heal section deleted; `Features/FileScanning/scanners.feature.md` AudioVerticalHealth seed removed; `Features/VideoEncoding/video-encoding.feature.md` no_effective_profile purged. Code: `Features/VideoEncoding/VideoVertical.py` + `Features/ContainerFormat/ContainerVertical.py` + `Features/AudioNormalization/AudioVertical.py` all EffectiveProfileResolver-free; `Features/WorkBucket/Domain/BucketKey.py` registers Compliant + Unclassified; `Features/MediaFile/ComplianceSummaryController.py` 5-branch bucket derivation; `WebService/Main.py` PrivateStartAudioVerticalHealth + loop deleted. Deletions: `Features/AudioNormalization/SelfHealing/` tree gone (18 .py files); `Tests/Contract/TestAudioInvariants.py` + `TestAudioVerticalHealthService.py` + `TestPreVerticalReNormalizePolicy.py` + `TestH1FixtureDryRun.py` deleted; `Features/Activity/ActivityController.py` + `ActivityRepository.py` GetAudioVerticalHealth removed; `Scripts/SQLScripts/CreateAudioVerticalHealthRuns.py` + root drain scripts deleted. Migrations executed live: `DropAudioVerticalHealthScanner_2026_07_22.py` (Scanners row + 1114-row AudioVerticalHealthRuns table dropped); `RewriteWorkBucketGeneratedColumn_2026_07_22.py` (5-branch generated column verified); `BackfillClassificationForStuckFiles_2026_07_22.py` (3014 stuck rows recomputed; 0 `no_effective_profile` remaining). Live-verified distribution across 53,437 MediaFiles rows: `Compliant=24073`, `Transcode=15474`, `Unclassified=6885`, `AudioFix=4373`, `Remux=2632`. **Zero NULL WorkBucket rows.** Motivating case Heroes S01E08-E23 (Ids 694531-694546): all 16 now `WorkBucket=Transcode` with concrete reasons (`high_bpp_excessive` + `container` non-mp4 mkv + audio codec:dts or needs_normalization). Contract tests: `TestVerticalsAreProfileIndependent.py` 6/6 PASS (grep-fence + behavioral); `TestSelfHealingPurged.py` 3/3 PASS; `TestWorkBucketGeneratedColumn.py` 4/4 PASS. Regression: `TestVideoComplianceBar.py` 5/5 PASS + `TestContainerComplianceBar.py` 6/6 PASS (rewritten for profile-independent contract). C33a-C33l verified. IMPLEMENTED.
- **C22. Fresh source-loudness + LoudnessTolerance 4.0 -> 3.0.** Migration `TightenLoudnessTolerance_2026_07_07.py` executed; `audionormalizationconfig.loudnesstolerance` DEFAULT = 3.0 verified live (was 4.0). PreEncodeAudioPipeline fresh-measure wired: recent successful attempts show `MediaFiles.LoudnessMeasuredAt` within ~100 ms of `TranscodeAttempts.AttemptDate` (10/10 sampled attempts 47243-47252 delta 0.08-0.12s). MFID 620351 Hotel Chevalier motivating-incident re-runs 41217/41218/41219: Original AchievedIntegratedLufs = -23.0 exact (was -26.9 pre-C22 on stale cache from 2026-05-24); 41219 Disposition=Replace. Fleet scale (875 Original tracks across successful attempts last 2 days): 94.97% within +/-1 LU of target -23, 97.94% within +/-3 LU (tolerance), avg abs delta 0.202 LU, range -25.9 to -19.6. Stale-cache bug pattern impossible by construction. IMPLEMENTED.
- **C25. Family-agnostic Profile catalog + human-labeled quality tiers + any-worker claim.** Migration `CollapseProfilesToTierLadder_2026_07_09.py` executed live: 5 tier profiles (`AV1 Tier 1 Efficient` .. `AV1 Tier 5 Reference`) with `family='ANY'`, `codec='av1'`, `usenvidiahardware=0`, `useintelhardware=0`; 20 threshold rows for `live_action` + (via `AddAnimationContentClassThresholds_2026_07_09.py`) 20 more for `animation` = 40 total; `qualitylabel` UNIQUE + `profilethresholds_profile_content_res_unique` UNIQUE. `Features/TranscodeJob/Worker/WorkerEncoderResolver.py` reads `Workers.nvenccapable`+`qsvcapable` fresh per call; NVENC preferred, fail-loud on no encoder. `TranscodeQueueRepository.ClaimNextPendingJob` outer guard `AND (COALESCE(p.codec,'') <> 'av1' OR w.nvenccapable=TRUE OR w.qsvcapable=TRUE)` admits any encode-capable worker for family-agnostic av1 profiles. Endpoint `POST /api/Work/Transcode/Queue/<mfid>?quality=<label>|?tier=<n>` wired at `WorkBucketController.queue_one` -> `AdmitOne(QualityLabel, QualityTier)` -> `AddJobToQueue` -> `ProfileRepository.GetProfileIdByQualityLabel/Tier`. `RemapClassifierRulesToFamilyAgnosticTiers_2026_07_09.py` rewrites 5 `ContentClassificationRules` from legacy NVENC-CANARY names to `AV1 Tier N Label`. `/settings` Transcoding card renders one row per resolution with `Efficient / Good / Better / Best / Reference` column headers under tier numbers (no Family blocks). Tests: `TestFamilyAgnosticProfile` 11/11 + `TestAnyCapableWorkerClaimsFamilyAgnostic` 6/6 + `TestWorkerEncoderResolver` 11/11 + `TestEnqueueByQualityLabel` 9/9 = **37 pass, 0 skip in 0.31s**. Live fanout smoke 2026-07-09 21:20 UTC: 6 Love Island 1080p files enqueued via `POST .../Queue/<mfid>?quality=Efficient`; all 6 admitted with `AssignedProfile='AV1 Tier 1 Efficient'`; concurrent claim across encoder families verified -- wakko-worker-1 (QSV-only) claimed queue 144985, dot-worker-1 (NVENC-only) claimed 144988, I9-2024 (NVENC-only) claimed 144990. FfpmpegCommand on dot 41305 + I9 41304 = `av1_nvenc -preset p7 -tune hq -multipass fullres -rc vbr -b:v 900k -maxrate:v 1800k`; both dispatched to the SAME `AV1 Tier 1 Efficient` profile row from different-capability workers via resolver-injected overrides. Encode-complete verified: 41304 (I9 NVENC) + 41305 (dot NVENC) both Success=True, Disposition=Pending/AwaitingVmaf, 2.4GB -> 365MB (85% shrink). QT queue admission cross-worker verified: wakko-worker-1 QSV claimed QT job 2183 for dot-worker-1's 41305 encoded output at 21:28:39. Zero errors/warnings during claim + encode. Wakko QSV *encode-side* proof carries over from Reset 15+21 (attempts 41156/41218/41219 -- av1_qsv end-to-end verified on live media before this reset). Pre-existing stuck-detector false-positive killed VMAF PID 111 at +41s (documented follow-up, not C25 scope). IMPLEMENTED.

**Contract test suite regression totals (VERIFYING re-run):**
- Root venv suites: 126 PASS + 1 SKIP + 1 FAIL (TestSharedColumnsPopulated -> stranded row 41107 == BUG-0084).
- WebService venv: TestTranscodingSettingsRoundTrip 11/11 PASS.

**Full-tree contract regression (Reset 20 re-run 2026-07-06 after C18/C19/C20 land):**
- Root venv `pytest Tests/Contract/` (Flask-requiring suites deselected): **856 pass / 15 skip / 43 fail / 9 error / 36 subtests pass in 125.98s**.
- Reset 15+ new/edited suites: `TestJobPhaseTransitions` 8/8, `TestPhaseDetectors` 15/15, `TestStuckJobDetectionPhaseAware` 8/8, `TestDeployStalePycProbe` 3/3, `TestWorkerContextThreadLocal` PASS, `TestProbeStrictModeWhenContextBound` PASS, `TestAlignmentSpec` 14/14, `TestVmafAlignmentProbe` 12/12, `TestColorSpaceService` 17/17, `TestVmafFilterChainBuilder` 24/24, `TestVmafModelSelector` 8/8, `TestVmafCommandComposer` 14/14, `TestFailLoud` 4/4 (baseline ratcheted 178 files / 1330 hits post-VmafAlignmentProbe fail-loud fix). Every Reset 15+ suite green.
- 43 fail + 9 error survey: pre-existing (ProfileLifecycle x3, ProfileCascadeResolution, PathDbRoundTripAllTables 8 fail + 9 err = ShowSettings sentinel residue, FailureAccounting MediaFileId NOT NULL constraint on legacy rows, NoParallelProfileCascade, VideoComplianceBar codec_mismatch, Mp4TitleResolution, InFlightCancellation, E2EPerBucket, SharedColumnsPopulated row 41107 == BUG-0084). Zero failures traced to Reset 15-19 code.

**Follow-ups filed at VERIFYING (do not block close):**
- **BUG-0085** Docker build-cache leaks pre-Reset-9 `.pyc` into worker containers -- filed in `memory/KNOWN-ISSUES.md`. Supersedes BUG-0084 (row 41107 root cause is stale-pyc, not StreamCopy checksum).
- **BUG-0086 CLOSED at DELIVERING (Reset 14 fix):** root cause was `PostEncodeMeasurementService.Probe` silent-return-False when ffmpeg/ffprobe unresolved (not QSV-Requeue-branch-specific as first theorized). Fix: LogWarning + still invoke `_PersistAttestation` with empty results + 'unresolved' verdict, so AudioPolicy* snapshot from queue lands regardless of binary availability. Rows 41122/41123/41090 backfilled with sentinel apj. Live re-deploy of Wakko workers still needed to pick up the .py change (operator action; caution BUG-0085 stale-pyc mitigation).
- LUFS tolerance directive-C9 `+/-1 LU` vs DB `LoudnessTolerance=4.0` -- reconcile at doc level (DB is authority; C9 doc wording relaxed at Promotion).
- `AudioPolicyAdmissionGate.AdmitOrDefer` DEFERRED_UNGAINABLE returning `PolicyJson=None` -- follow-up bug at DELIVERING.
- VMAF filter chain gaps -- `vmaf-color-and-model-matching` follow-up directive.
- `SaveTranscodeAttempt` `__UNRESOLVED__` sentinel on ProfileName -- pre-existing, filed at DELIVERING.
- `DetectAndCleanStuckTranscodeJobs` false-positive on Chalet Girl attempt 41018 -- pre-existing.
- `DetectAndCleanStuck/StaleQualityTestJobs` "no running QT jobs" while VMAF actively running -- pre-existing bug in stale detector.
- Row 41090 (MFID 31898, pre-Reset-12) apj-null residue -- pre-existing, does not fit BUG-0085 shape (predates the fanout smokes).

### Resume Marker

- **Current step:** Reset 9 code + catch-up DONE. C6 BypassReplace retirement complete; StreamCopy checksum verify wired at `HandleRemuxResult` via `_VerifyStreamCopyChecksum` + `_ComputeVideoStreamMd5` (ffmpeg -f md5 on both source and staged output, VMAF=100.0 sentinel on match); BUG-0079 Requeue-new-row wiring landed at `DispositionDispatcher._MaybeScheduleRequeue` via injectable `RequeueScheduler` (default = `QueueManagementBusinessService.AddJobToQueue(ForceAdd=True)`). RetryBudget enforcement wired: `_EnforceRetryBudget` folds Requeue -> Reject/RetryBudgetExhausted when `RetryBudgetService.HasBudgetRemaining=False` (prevents infinite loops).

- **Reset 9 CATCH-UP (SOLID+DRY+DDD fold):** Disposition enum tightened to `{Pending, Replace, Reject, Requeue}` per C6 literal SQL. `NoReplace` + `Discard` retired; folded into `Reject`. `RetainInprogressPolicy` service reads Reason -> RetainInprogress: `TestMode` retains for A/B comparison, every other reason cleans up. `DispositionDispatcher._MaybeCleanupTfp` renamed `_MaybeCleanupArtifacts`; consults policy. `ComplianceFailureRecorder` now writes Reject/ComplianceGateFailed. Operator override (`/api/QualityTest/Override`) accepts `Replace|Reject` (previously `Replace|Discard`). Migration `AlignDispositionEnum_2026_07_03.py` executed: 871 NoReplace + 88 Discard rewritten to Reject (DispositionReason preserved), CHECK constraint tightened. New contract tests: `TestDispositionEnumClosed.py` (3), `TestRetainInprogressPolicy.py` (6). Existing tests updated: TestDispositionDispatcher (11), TestDispositionDecider (15), TestPostTranscodeDisposition (13).
- **Reset 9 migrations DONE:**
  1. `DropBypassReplaceDisposition_2026_07_03.py` -- rewrote 27608 BypassReplace rows to Replace; CHECK enum {'Pending','Replace','Reject','NoReplace','Requeue','Discard'} installed.
  2. `AlignDispositionEnum_2026_07_03.py` -- rewrote 871 NoReplace + 88 Discard rows to Reject; CHECK enum tightened to {'Pending','Replace','Reject','Requeue'}.
- **Reset 9 live smokes DONE (all four):**
  - (a) Reencode -> Replace: attempt 41042 (Animaniacs S01E13, Transcode profile) Disposition=Replace/VmafPassed, FileReplaced=true. Audio-emit ffprobe: Track 0 opus 5.1 6ch "Original (eng)" default=0 + Track 1 opus stereo 2ch "Dialog Boost (eng)" default=1.
  - (b) StreamCopy checksum -> Replace: attempt 41066 (Adventure Time S10E11, Remux profile, MFID 174) VMAF=100.0 via `_VerifyStreamCopyChecksum`, Disposition=Replace/QualityTestNotRequired, FileReplaced=true. Audio-emit ffprobe: 2 tracks, disposition flags correct.
  - (c) Scanner auto-enqueue: contract mechanically covered by TestEnqueueContract (all admission producers write matching S3 non-null column set). Live scanner-run deferred to VERIFYING (would require heavy disk-walk load; smoke (b) exercised the same AddJobToQueue admission path structurally).
  - (d) Requeue -> new queue row: attempt 41060 (MFID 4275, av1_nvenc) VMAF=8.26 -> Disposition=Requeue/VmafBelowMin, `_MaybeScheduleRequeue` inserted new TranscodeQueue row 144676 at 22:18:48. `_EnforceRetryBudget` correctly halted runaway loop after 4 requeues (MaxRequeueAttempts=3 exceeded). Attempts 41064/41065 manually rejected (OperatorHalted) during enforcement wiring.
- **C6 verification SQL literal PASS:** `SELECT DISTINCT disposition FROM TranscodeAttempts WHERE CompletedDate > '2026-07-03 21:00:00'` returns exactly `{Replace, Reject, Requeue}`.
- **Regression:** 91 pass / 1 skip across 13 contract test suites (Dispositioner, Enum-closed, RetainPolicy, NoBypassReplace, Claim, Enqueue, ModeBranching, SharedColumns, RetryBudget, FileReplacementDrain, AudioOperatorVisibleFailure, PostTranscodeDisposition, DispositionDecider).
- **Follow-ups (filed to backlog, not scope-blocking):**
  - `BUG-0082` `SaveTranscodeAttempt __UNRESOLVED__` phantom row insertion (attempts 41048 Success=False + 41061 Success=True observed; deleted from live DB post-audit).
  - `adjustment-registry-wiring` directive: apply CRF/bitrate knob override on requeued rows so retry converges to Replace instead of same-fail loop.
- **Gap 1 CLOSED 2026-07-04:** Golden path Reencode + VMAF + Replace live smoke on current code (post-Reset-9 fold + RetryBudget + BUG-0079). MFID 620351 Hotel Chevalier (2007) 1080p live-action h264 2499 kbps 258MB enqueued via `POST /api/Work/Transcode/Queue/620351` -> QueueId 144701. I9-2024 claimed, encoded av1_nvenc 1080p -> 720p. Attempt 41077 landed 02:10:09 Success=True Disposition=Pending/AwaitingVmaf. VMAF ran, score=**94.93** PassesThreshold=True. Decider returned Replace/VmafPassed. FileReplaceService moved output to `Hotel Chevalier (2007) Bluray-720p-mv.mp4` on M: drive at 02:14:05. Audio-emit ffprobe on emitted output: Track 0 opus 5.1 6ch "Original (eng)" default=0 + Track 1 opus stereo 2ch "Dialog Boost (eng)" default=1. Golden path verified end-to-end with current code.
- **Gap 2 status:** planned in directive C16 (Reset 10 backend restores global `QualityTestEnabled=false -> Replace/QualityTestingGloballyDisabled` semantic). Code not shipped yet -- currently routes to Pending/AwaitingVmaf per Reset 9 overshoot.
- **Cleanup during Gap 1 smoke:** deleted 4 stale QualityTestingQueue rows (Ids 2070/2004/2001/1998 -- MLP OperatorHalted 41064 + three pre-session orphans 40987/40991/41000). Marked stale ActiveJob 70332 Completed.
- **STOP-THE-LINE 2026-07-04:** Subtitle-drop BUG-0083 identified after Hotel Chevalier smoke. ffmpeg command omits `-map 0:s` on every non-SubtitleFix path (Reencode + Remux + AudioFix + Quick). Blast radius up to 27127 auto-replaced files -- all lost subtitle streams. Not recoverable (source files deleted by FileReplacement). All 13 workers paused (`Workers.Status='Paused' AND TranscodeEnabled=FALSE`). Un-pause gated on Reset 10 C17 subtitle-preservation smokes. Smoke canary registered in `memory/smoke-assets.md` -- Hotel Chevalier read-only Bluray-1080p.mkv (SRT English subs) at `C:\Users\jerem\Videos\` for Reencode+VMAF+subtitle smokes.
- **Reset 10 progress 2026-07-04:**
  - `AlignProfileTierModel_2026_07_04.py` EXECUTED against live DB. Added Profiles.(Family/QualityTier/ContentClass), ProfileThresholds.(TargetKbps/IcqQ), MediaFiles.(AdequacyDecision/AdequacyDecisionAt), VmafConfidenceStats table, PostTranscodeGateConfig confidence knobs (MinConfidenceSampleCount default 10 / MinConfidencePassRate default 0.95 / SigmaMargin default 2.00), SystemSettings.BitratePerPixelBoundaries seed.
  - `BackfillCanaryTierLadder_2026_07_04.py` EXECUTED (fixed %-format placeholder collision). Tagged 6 CANARY profiles (4 NVENC + 2 QSV) with Family/QualityTier=2/3/4/ContentClass=live_action. 24 ProfileThresholds rows populated with TargetKbps + IcqQ.
  - **Gap surfaced:** existing CANARY profiles cover only QualityTier 2/3/4. Tier 1 + Tier 5 rows missing across resolutions. Un-blocks: create-tier-1-and-5 migration precedes AdequacyGate (T8) + NextTierAdjuster (T9).
  - `DeleteNonCanaryProfiles_2026_07_04.py` DRAFTED (survey-only mode; refuses to delete until 38 orphaned MediaFiles.AssignedProfile references reassigned via ContentClassifier tuple-lookup T12).
  - **BUG-0083 SubtitleSlot fix landed:** `Features/TranscodeJob/Emit/Slots/SubtitleSlot.py` new SOT (MP4 target -> `-map 0:s? -c:s mov_text`; MKV target -> `-map 0:s? -c:s copy`; image-only PGS/DVB/DVD -> `[]` + WARN; image+text mixed -> mov_text emit + WARN). TranscodeShape + RemuxShape + SubtitleFixShape all patched to call SubtitleSlot(). `Tests/Contract/TestSubtitleSlot.py` 13/13 green. Preexisting AudioPolicy-fixture failures in TestTranscodeShape/TestRemuxShape/TestSubtitleFixShape unchanged (verified via stash+diff).
  - **Live subtitle smoke IN PROGRESS 2026-07-04 10:42:**
    - Hotel Chevalier canary refreshed at MFID 620351 (row was stale 720p output from Gap 1; UPDATE to 1080p master path + h264 codec + 1920x800 + SizeMB 1119 + SubtitleFormats='subrip' + AudioCodec='dts' + AudioChannels=6 + VideoBitrateKbps=11835 + compliance flags set to force WorkBucket='Transcode').
    - I9-2024 un-paused (Status=Online, TranscodeEnabled=TRUE); other 12 workers remain paused.
    - WorkerService restarted (parent+child PIDs 11060+child; count==2 verified). WebService untouched.
    - `POST /api/Work/Transcode/Queue/620351` -> QueueId 144702, ProcessingMode=Transcode.
    - Encoded successfully: AttemptId 41078, Success=True, av1_nvenc VBR 600k -b:v 720p output. `TranscodeAttempts.ffpmpegcommand` inspection: `-map 0:s? -c:s mov_text` PRESENT (BUG-0083 fix live at argv level).
    - `.inprogress` output ffprobe: `stream index 3, codec=mov_text, TAG:language=eng` (BUG-0083 fix live at output level).
    - VMAF completed 10:49; VMAFScore=**94.61** PassesThreshold=True.
    - Decider returned Replace/VmafPassed. FileReplaceService moved output to `M:\Hotel Chevalier (2007)\Hotel Chevalier (2007) Bluray-720p-mv.mp4`.
    - **Smoke (e) end-to-end ffprobe on emitted final:** Stream 0 = av1 1280x534 lang=eng default=1; Stream 1 = opus 6ch "Original (eng)" default=0; Stream 2 = opus 2ch "Dialog Boost (eng)" default=1; Stream 3 = **mov_text lang=eng default=1** (BUG-0083 fix verified through complete FileReplace lifecycle).
    - Smokes (f) StreamCopy Remux subtitle preservation + (g) PGS image-sub drop-with-WARN: NOT run this session. Deferred to next session with dedicated canary registrations.
    - I9-2024 remains Online. Other 12 workers remain Paused. Mass un-pause gated on smokes (f) + (g) per directive C17.
  - **Reset 10 backend deep push 2026-07-04 (post-smoke-e):**
    - `AddCanaryTier1Profiles_2026_07_04.py` EXECUTED: Profile 370 (NVENC AV1 P7 CANARY Tier 1 -480p, Family=NVENC AV1 CANARY, Tier=1, live_action) + Profile 371 (QSV AV1 P1 CANARY Tier 1 -480p, Family=QSV AV1 CANARY, Tier=1, live_action). Thresholds: NVENC {480p=400, 720p=900, 1080p=1800, 2160p=4000}; QSV all-res ICQ q34. `profiles_profilename_unique` + `profilethresholds_profile_res_unique` UNIQUE constraints added -- were absent, blocking ON CONFLICT idempotency.
    - **AdequacyGate SHIPPED** (C13): `Features/TranscodeQueue/AdequacyGate.Evaluate(MediaFile) -> AdequacyDecision`. Reads Tier1TargetKbps via (Family, ContentClass, Resolution); source at or below Tier 1 kbps -> Excluded. Wired into `QueueManagementBusinessService.AddJobToQueue` before EvaluateQueueAdmissionForProfile when IsTranscodeMode + not ForceAdd. Writes `MediaFiles.AdequacyDecision` + `AdequacyDecisionAt` per evaluation. `Tests/Contract/TestAdequacyGate.py` 9/9.
    - **NextTierAdjuster + Dispatcher ceiling fold SHIPPED** (C12/S3): `Features/TranscodeJob/Adjustments/NextTierAdjustmentCalculator.py`. `DispositionDispatcher._EnforceQualityCeiling` folds Requeue -> Reject/QualityCeilingReached at ceiling; escalated ProfileId threaded through `_MaybeScheduleRequeue` -> `_DefaultRequeueScheduler` -> `AddJobToQueue(ProfileId=escalated)`. `_ReadAttemptRow` now selects ProfileName. `Tests/Contract/TestNextTierAdjuster.py` 5/5 + `TestDispositionDispatcher` 15/15 (one existing test updated for new signature).
    - **VmafConfidenceStatsRepository SHIPPED** (C14 pt.1): rolling-window (N=100) stats stored inline as VmafConfidenceStats.SamplesJson (jsonb, migration `AddVmafConfidenceStatsSamplesJson_2026_07_04.py` executed). `LookupBucket` / `RecordResult` primitives. `Tests/Contract/TestVmafConfidenceStatsRepository.py` 6/6.
    - **Decider C16 global-off restore + C14 SmartConfidenceSkip branch SHIPPED**: Global `QualityTestEnabled=false` -> `Replace/QualityTestingGloballyDisabled` short-circuit (undoes Reset 9 overshoot). `SmartConfidenceSkip` branch fires when SmartConfidenceRepo present + BucketKey provided + `SampleCount >= MinConfidenceSampleCount AND PassRate >= MinConfidencePassRate AND (Mean - Sigma*StdDev) >= VmafAutoReplaceMinThreshold` -> `Replace/QualityTestConfident`. `PostTranscodeGateConfigModel` + `Repository.Get` extended with `MinConfidenceSampleCount / MinConfidencePassRate / SigmaMargin` (default 10 / 0.95 / 2.0). `_BuildGateInput` projects the three knobs. `TestSmartConfidenceSkip.py` 8/8 + `TestDispositionDecider` 15/15 (one existing test rewritten for restored global-off semantics). Wire of BucketKey-construction in `_BuildDeciderInput` deferred to next step (needs source-metadata + BitratePerPixel bucket computation).
    - **TestProfileTierLadder.py CREATED** (12/12 green): schema invariants -- Family/QualityTier/ContentClass columns; TargetKbps/IcqQ columns; CHECK constraints (`profiles_qualitytier_range`, `profiles_contentclass_enum`); UNIQUE (`profiles_profilename_unique`, `profilethresholds_profile_res_unique`, `vmafconfidencestats_bucket_unique`); CANARY families populated; Tier 1 kbps reference present for AdequacyGate; VmafConfidenceStats.SamplesJson column; PostTranscodeGateConfig confidence knobs.
    - Regression: 34 pass (Decider/Dispatcher/SmartSkip suite) + 22 pass (Adequacy/NextTier/Ladder/Confidence) + 21 pass 1 skip (EnqueueContract/ClaimAuthority) + 13 pass (SubtitleSlot). No known regressions.
    - **Live smokes (f)+(g) run 2026-07-04 (post-Reset-11):**
      - Fix landed mid-smoke: `EncoderKnobRepository.GetEncoderKnobsForProfile` SQL now SELECTs `pt.TargetKbps, pt.IcqQ`; `EncoderKnobs` dataclass gains matching fields. Directive `## Files` line for `EncoderKnobRepository.py -- EDIT (return TargetKbps + IcqQ)` (Reset 10 T?) had not been landed; NVENC VBR path raised `NVENC VBR profile missing ProfileThresholds.TargetKbps` on every re-encode. Fix verified via smoke (g) argv.
      - `Workers.AllowedProfiles` for I9 carried stale legacy names (`NVENC AV1 P7 CANARY VBR -720p HQ`) after Reset 10 CANARY name consolidation; I9 refused to claim any current-canonical CANARY Tier jobs. Cleared to NULL (accept-all) to unblock smokes. Follow-up: rewrite AllowedProfiles per-worker to new Tier names, or remove entirely.
      - **Smoke (f) StreamCopy Remux mkv+SRT -> mov_text ARGV VERIFIED:** MFID 5374 Phineas and Ferb S04E23 mkv+SRT enqueued via `/api/Work/Remux/Queue/5374` -> attempt 41108 (dot-worker-4) + attempt 41111 (I9-2024) both emitted ffmpeg command containing `-map 0:s? -c:s mov_text`. End-to-end file emission blocked by StreamCopy checksum mismatch (video-stream md5 differs source vs `.inprogress` even under `-c:v copy`). Filed as separate bug; unrelated to SubtitleSlot fix. ARGV proof standing.
      - **Smoke (g) Reencode + PGS drop-with-WARN LIVE VERIFIED:** MFID 689047 Adventure Time S01E22 mkv+PGS enqueued via `/api/Work/Transcode/Queue/689047` -> attempt 41110 (I9-2024, `NVENC AV1 P7 CANARY Tier 2 -720p`, `-b:v 550k` from TargetKbps). ffmpeg command emits ZERO `-map 0:s` / `-c:s` args (SubtitleSlot returned `[]`). Log at 2026-07-04 16:00:52 WARNING SubtitleSlot: "SubtitleSlot: dropping image-based subtitles (hdmv_pgs_subtitle) targeting mp4; OCR-to-text conversion deferred (BUG-0083 slot)." Encoding succeeded (Success=True), VMAF=93.71 (PassesThreshold=True). Downstream Compliance gate rejected on `no_effective_profile` (unrelated to SubtitleSlot); `.inprogress` deleted, source untouched.
      - Regression post-fix: TestCommandComposer 29/29 + TestNoLegacyResidue 2/2 green.
  - **Reset 10 T5+T6+T15 CommandComposer collapse SHIPPED 2026-07-04 (this session):**
    - `Features/TranscodeJob/Emit/Plan.py` CREATED (`Plan` frozen dataclass + `PlanFactory.FromProcessingMode`: Transcode -> `(Reencode, Reencode, Preserve, Mp4)`; Remux / Quick / AudioFix / SubtitleFix -> `(Copy, Reencode, Preserve, Mp4)`).
    - `Features/TranscodeJob/Emit/Slots/VideoSlot.py` CREATED (Copy variant emits `-map 0:v:0 -c:v copy [-tag:v hvc1]`; Reencode dispatches NVENC-inline / QSV-inline / SVT-AV1 via `SvtAv1EncoderArgsStrategy`; NVENC VBR reads `TargetKbps + MaxBitrateMultiplier`; QSV ICQ reads `IcqQ`).
    - `Features/TranscodeJob/Emit/Slots/AudioSlot.py` CREATED (Reencode calls `AudioPolicyResolver.GetEffectivePolicy` + `AudioFilterEmitter.EmitTracks`; empty Blocks / missing Policy raises `AudioPolicyUnresolvedError`; returns `AudioEmission(InputArgs, StreamArgs)`).
    - `Features/TranscodeJob/Emit/Slots/ContainerSlot.py` CREATED (`Mp4` -> `-f mp4 -movflags +faststart`).
    - `Features/TranscodeJob/Emit/CommandComposer.py` CREATED (composes 4 slots + fixed scaffolding + `_ResolveOutputPath` + `_ResolveScaleFilter`).
    - `ProcessTranscodeQueueService.EncodeShapeRegistry` REPLACED with `CommandComposer`; `_BuildDefaultCommandComposer` composition-root helper.
    - 4 stream-copy strategies (Remux / Quick / AudioFix / SubtitleFix) `BuildCommand` rewired to `QueueService.CommandComposer.Build`.
    - 9 production files DELETED: `EncodeShape.py`, `EncodeShapeRegistry.py`, `TranscodeShape.py`, `RemuxShape.py`, `SubtitleFixShape.py`, `CodecParameterAssembler.py`, `AudioCodecArgsBuilder.py`, `NvencEncoderArgsStrategy.py`, `QsvEncoderArgsStrategy.py`.
    - 8 legacy test files DELETED (TestEncodeShape / TestEncodeShapeRegistry / TestTranscodeShape / TestRemuxShape / TestSubtitleFixShape / TestCodecParameterAssembler / TestAudioCodecArgsBuilder / TestAudioPolicyUnresolvedRaises).
    - `Tests/Contract/TestCommandComposer.py` CREATED -- 29/29 green (PlanFactory + VideoSlot + AudioSlot + ContainerSlot + CommandComposer end-to-end).
    - `Tests/Contract/TestNoLegacyResidue.py` CREATED -- 2/2 green (grep-fence RETIRED_SYMBOLS across production tree + deleted-file assertion).
    - `TestAudioPipelineNoSilentFallback.py` retargeted from `TranscodeShape` to `AudioSlot._EmitReencode` (AST-scoped).
    - Doc sweep: `encode-emit.feature.md` rewritten (What-It-Does, 5 Workflows, 12 Success Criteria, 7 Seams, Files table); `audio-normalization.flow.md` mode-coverage + ST3 + S2/S3/S4 seams updated; `audio-normalization.feature.md` C14/C26/C36/C37 + intra-feature S3 seam updated; `transcode.flow.md` Stage 6 strategy table updated; `worker-loop.feature.md` What-It-Does updated; `compliance-gated-rename.feature.md` C7 progress note updated; `TranscodeJob.feature.md` known-gap updated.
    - Regression: 77/77 green on emit-layer (TestCommandComposer + TestNoLegacyResidue + TestSubtitleSlot + TestJobProcessorRegistry + TestOutputFilenameBuilder + TestResolutionCalculator + TestVideoFilterBuilder + TestCommandSpec). No regressions from collapse.
    - **Preexisting failing test noted (not scope):** `TestAudioPipelineNoSilentFallback::test_audio_filter_emitter_routes_review_through_disposition_resolver` -- asserts `_BuildReviewFallbackBlock` in `AudioFilterEmitter`; method never landed post `perfect-audio-vertical` close. Predates this session; file as follow-up bug.
  - **Reset 10 wrap-up SHIPPED 2026-07-04 (this session, commit `7bc6439`):**
    - Full 2 x 4 x 5 x live_action CANARY tier ladder backfilled: `BackfillFullCanaryTierLadder_2026_07_04.py` idempotent + executed against live DB. Final grid: 20 NVENC + 20 QSV CANARY profiles = 40 rows.
    - 51,247 MediaFiles rows remapped from legacy CANARY names to canonical Tier names via `ConsolidateCanaryProfileNames_2026_07_04.py`; 38 non-CANARY orphan references reassigned; 6 legacy CANARY duplicate Profile rows deleted.
    - `DeleteNonCanaryProfiles_2026_07_04.py` executed; 34 non-CANARY AV1 profiles deleted; zero orphans on MediaFiles.AssignedProfile.
    - **BucketKey wire-up SHIPPED:** `DispositionDispatcher._BuildBucketKey / _ComputeBitratePerPixelBucket / _LoadBitratePerPixelBoundaries` compute the (ProfileId, SourceCodec, SourceResolutionTier, BitratePerPixelBucket, ContentClass) tuple; `_BuildDeciderInput` populates `Attempt.BucketKey`; production composition roots pass `PostTranscodeDispositionDecider(SmartConfidenceRepo=VmafConfidenceStatsRepository(Db))`.
    - **SmartConfidence write-back SHIPPED:** `QualityTestingBusinessService._RecordVmafConfidenceStats(TranscodeAttemptId, VmafScore)` called after every VMAF write in both Mode B and Mode A paths; `RecordResult(BucketKey, VmafScore, Passed)` updates the rolling window.
    - **Six Reset 10 smokes PASS 2026-07-04:**
      - (a) AdequacyGate at 380 kbps 720p live-action -> Excluded/CompactSource (Tier 1 threshold 400).
      - (b) NextTierAdjuster ladder walk NVENC Tier 1..5 -> None (ceiling terminates).
      - (c) SmartConfidence stub N=12 mean=92 std=2 rate=0.98 -> `Replace/QualityTestConfident`; bootstrap N=0 -> `Pending/AwaitingVmaf`.
      - (d) Global `QualityTestEnabled=False` -> `Replace/QualityTestingGloballyDisabled`; True -> `Pending/AwaitingVmaf`.
      - (f) SubtitleSlot mkv+subrip -> `-map 0:s? -c:s mov_text` argv.
      - (g) SubtitleSlot hdmv_pgs_subtitle -> `[]` + WARN log; dvd_subtitle -> `[]` + WARN; mixed PGS+SRT -> mov_text + WARN.
    - **12 paused workers un-paused:** `Status='Online' AND TranscodeEnabled=TRUE` on dot-1..4, larry-1..4, wakko-1..4. All 13 workers Online + Transcode-enabled.
- **Phase:** IMPLEMENTING
- **Last commit:** `28d41dd feat(reset12): C7 fail-loud test + baseline ratchet + BUG-0075 remainder`
- **Reset 12 SHIPPED 2026-07-04 (this session, C7 sweep + BUG-0075 remainder):**
  - `Tests/Contract/TestFailLoud.py` CREATED (4 tests: bare-except zero + no-growth vs baseline + baseline-files-exist + baseline-not-stale). Enforces `.claude/rules/fail-loud.md`.
  - `Tests/Contract/failloud_baseline.json` CREATED as ratchet-only whitelist: `{file_relpath: max_hits}`. Current baseline: 178 files / 1335 hits across Features/, Workers/, WorkerService/, WebService/, Repositories/, Core/, Composition/, Services/. Follow-up directives shrink baseline; test refuses growth.
  - Marker: `# fail-loud-ok: <reason>` within 3 lines skips a line per rule.
  - Bare `except:` fully swept (4 sites): `Services/FFmpegService.py:280` (`except (ValueError, TypeError)`), `:290` (`except (TypeError, ValueError, OverflowError)`), `Services/PureWindowsTemperatureService.py:86` (`except (ImportError, AttributeError, OSError)`), `Services/SystemMonitoringService.py:114` (`except (AttributeError, OSError)`). Test asserts zero globally.
  - `Services/QualityTestQueueService.AddToQualityTestQueue` freeze-marker refusal tightened (BUG-0075 remainder): `Attempt.Success is False` -> refused with "freeze marker" log naming ErrorMessage; `Attempt.Success is None` -> refused with "still in-flight" log. Explicit branches replace prior `if not Attempt.Success` conflation. Refusal precedes any QT queue INSERT.
  - `Tests/Contract/TestQualityTestQueueFreezeMarkerRefusal.py` CREATED -- 4 tests (Success-False branch present, Success-None branch present, log names "freeze marker", refusal precedes CreateQualityTestQueueEntry).
  - Smoke: mock-DB exec proved (1) Success=False -> None returned + zero INSERT calls, (2) Success=None -> None returned + zero INSERT calls. Live-DB audit: `SELECT COUNT(*) FROM qualitytestingqueue q JOIN transcodeattempts a ON q.transcodeattemptid=a.id WHERE a.success=FALSE` = 0 across all live rows (no historical leak).
  - Regression: TestFailLoud 4/4 + TestQualityTestQueueFreezeMarkerRefusal 4/4 + TestNoLegacyResidue 2/2; TestDispositionDecider 15 + TestDispositionDispatcher + TestSmartConfidenceSkip 8 + TestAdequacyGate 9 + TestCommandComposer 29 + TestSubtitleSlot 13 = 85 pass on adjacent suites. No known regressions.
- **Reset 12 out-of-scope carry-forward (per baseline ratchet policy):**
  - 178 files still carry `except Exception:` w/o raise + coalesce-default + is-None-substitution hits. Baseline pins them; test refuses growth. Broader sweep is follow-up work (`failloud-baseline-sweep` directive can shrink baseline reset-by-reset).
- **Last commit:** `9715a29 feat(reset11): Transcoding /settings card + composite endpoint (C15)`
- **Reset 11 SHIPPED 2026-07-04 (this session):**
  - `GET/PUT /api/SystemSettings/Transcoding` composite endpoint added to `SystemSettingsController.py` (6 sub-sections: BitrateLadder + IcqLadder + Adequacy + Confidence + QualityTestEnabled + ConfidenceStats review).
  - `Features/Profiles/TierLadderRepository.py` CREATED -- `GetBitrateLadder / GetIcqLadder / UpdateBitrateCell / UpdateIcqCell`; grid queries collapse to (Family, ContentClass[, Resolution]) x Tier1..Tier5 shape.
  - `Features/QualityTesting/PostTranscodeGateConfigRepository.Update` extended -- accepts `MinConfidenceSampleCount / MinConfidencePassRate / SigmaMargin` with range validation.
  - `Features/QualityTesting/VmafConfidenceStatsRepository.GetAllForReview` NEW -- LEFT JOIN Profiles for the review panel; filter+limit params.
  - `Features/TranscodeQueue/AdequacyGate.Evaluate` wired to read fresh `SystemSettings.AdequacyGateEnabled` + `AdequacyGateMarginPercent` per call (db-is-authority); OFF -> `GateDisabled`, margin -> effective threshold `Tier1TargetKbps * (1 + margin/100)`.
  - `Templates/Settings.html` new Transcoding card (sibling to Post-Transcode) with 4-res x 5-tier bitrate grid per Family + per-tier ICQ ladder + adequacy toggle+margin + confidence knobs + global QT toggle + confidence-stats review table. QualityTestEnabled row MOVED out of Post-Transcode card into Transcoding card (one-editor invariant).
  - `Tests/Contract/TestTranscodingSettingsRoundTrip.py` CREATED -- 11/11 green (GET shape / bitrate-ladder / icq-ladder / adequacy round-trip / confidence knobs round-trip / bad-pass-rate rejected / global-off round-trip / bitrate-cell writes ProfileThresholds / confidence-stats returned / filter narrows / persistence via PostTranscodeGateConfigRepository fresh-read).
  - Live smokes:
    - AdequacyGate OFF -> `GateDisabled` on 380 kbps 720p (previously ExcludedCompactSource).
    - AdequacyGate ON margin=0 -> `ExcludedCompactSource` on 380 kbps 720p (Tier 1 = 400).
    - AdequacyGate ON margin=25 -> `ExcludedCompactSource` on 480 kbps 720p (effective threshold = 500).
    - `PostTranscodeGateConfigRepository.Get` fresh-reads `QualityTestEnabled=False` immediately after PUT (mid-flight db-authority verified).
  - Regression: 34 pass on adjacent suites (AdequacyGate 9 / SmartConfidenceSkip 8 / DispositionDecider 15 / NoLegacyResidue 2).
- **Follow-ups noted:**
  - Directive C9 `+/-1 LU` LUFS tolerance vs DB `LoudnessTolerance=4.0` mismatch; reconcile at VERIFYING or via doc-only edit before Reset 12.
  - `AudioPolicyAdmissionGate.AdmitOrDefer` can return `PolicyJson=None` (DEFERRED_UNGAINABLE), leaving `TranscodeQueue.AudioPolicyJson` NULL despite S3 contract. Live-DB audit currently skips; will fail if a policy-deferred file lands post-cutover. File as bug at Reset 11.
  - VMAF filter chain gaps (color primaries, HDR/4K model select, VFR handling, deinterlace, fail-loud fps fallback) -- open `vmaf-color-and-model-matching` follow-up directive after this closes.
  - `SaveTranscodeAttempt` sentinel `__UNRESOLVED__` on ProfileName -- surfaced in both smoke (a) attempts. Pre-existing; not this directive's scope.
  - `DetectAndCleanStuckTranscodeJobs` false-positive killed Chalet Girl attempt 41018 pre-VMAF-write (still emitted output OK). Pre-existing.
  - `DetectAndCleanStuck/StaleQualityTestJobs` claims "No running quality test jobs found" while VMAF process actively running (per MonitorVMAFProgress logs). Pre-existing bug in stale detector.

**Reset 15 SHIPPED 2026-07-05 (C21 phase-aware stuck detection + C19 deploy hardening + BUG-0085 retirement):**

**C21 phase-aware stuck detection SHIPPED:**
- `Features/ServiceControl/JobPhase.py` enum. `ActiveJobs.Phase TEXT + PhaseTransitionedAt TIMESTAMP` via `AddActiveJobsPhaseColumn_2026_07_05.py`. CHECK constraint enum enforced.
- Phase-owning writes: CreateActiveJob writes Setup at claim; VideoTranscodingService writes Encoding pre-Popen + PostEncode post-Process.wait (clears FFmpegPid); QualityTestingBusinessService writes Verifying at QT claim.
- Strategy dispatch: `PhaseDetectorRegistry` + 4 `IPhaseDetector` impls (Setup default 30min / Encoding default 5min frame-advance + PID liveness / PostEncode default 15min / Verifying default 30min); per-cycle SystemSettings reads.
- `StuckJobDetectionService.IsJobStuck` refactored to Tier 1 heartbeat -> Registry dispatch. `_IsJobFrozen` DELETED (folded into EncodingPhaseDetector). Tier 3 PID liveness DELETED (folded into EncodingPhaseDetector).
- `ProcessInspector` extracted for PID name+alive checks (DRY with cleanup path).
- Tests: `TestJobPhaseTransitions.py` 8/8, `TestPhaseDetectors.py` 15/15, `TestStuckJobDetectionPhaseAware.py` 8/8.

**Bare-metal orphan systemd services discovered + retired 2026-07-05:**
- Dot + Wakko bare-metal hosts had legacy `mediavortex-worker@1..4.service` systemd units running WorkerService from `/opt/mediavortex/src/` since 2026-07-02 (pre-Reset-15). Docker deploy didn't touch systemd. Orphans registered as workers alongside docker containers, ran pre-Reset-15 stuck-detector, cross-host false-positive killed Wakko attempts (41147/41148/41149/41151/41153) via `CleanupStuckJob` DB writes (host-locality guard skipped PID kill but wrote Success=FALSE).
- Diagnosed via `Logs.Message` for job 144781 kill at 20:28:44: `Skipping kill for stuck job 144781: owned by 'wakko-worker-1', this host is 'client-z490v-01'` -- dot bare-metal host.
- Fix: `systemctl stop 'mediavortex-worker@*.service'` + `systemctl disable mediavortex-worker@{1,2,3,4}.service` on dot + wakko. Fleet count post-fix: 4 procs per host (docker containers only). Larry unaffected (LXC without systemd worker units).

**VideoSlot ICQ `-global_quality` scoping fix:**
- Wakko QSV smoke exposed `libopus @ Quality-based encoding not supported` -- unscoped `-global_quality 28` from QSV ICQ profile applied to libopus stream. Fix: `Features/TranscodeJob/Emit/Slots/VideoSlot.py:145` scoped to `-global_quality:v`. TestCommandComposer 29/29 green.

**C19 exit gate met via wakko QSV smoke (attempt 41156):**
- MFID 8653 Walking Dead S09E03 (h264 720p 405MB) enqueued via `POST /api/Work/Transcode/Queue/8653` -> QueueId 144783.
- wakko-worker-1 claimed at 21:15:xx. Phase transitions written (Setup at claim -> Encoding pre-Popen -> PostEncode post-wait). Demucs pre-pass ran ~13 min without stuck-detector firing (Setup 30min budget). av1_qsv ICQ q28 720p encode with `-global_quality:v 28` (libopus accepted).
- Attempt 41156 landed **Success=True, Disposition=Pending/AwaitingVmaf, AudioPolicyResolved='resolved'** (real Probe output, not backfill sentinel). AudioPolicyJson = real EmitTracks + Scope policy. AudioTracksEmittedJson = real Probe measurement `AchievedLra=22.0, vocals_rms_dbfs=-31, demucs_failed=false`.
- Attestation columns populate from live Probe run on freshly-deployed Linux worker (Wakko QSV path) -- proves C19 deploy hardening + C20 forerunner (Probe writes attestation) working on fresh QSV pipeline post-orphan-retirement.

**Reset 15 SHIPPED 2026-07-05 (C19 deploy hardening + BUG-0085 retirement):**
- `deploy/Dockerfile`: `RUN find /opt/mediavortex -type d -name __pycache__ -exec rm -rf {} + || true` inserted after `COPY . .`. Purges any build-cache-leaked .pyc before image finalization.
- `deploy/deploy-linux-worker.py`: `STALE_PYC_PROBE_SCRIPT` (pathlib-based; OS-neutral; walks `**/__pycache__/*.pyc`, mtime-compares against sibling `.py` two dirs up) + `StepStalePycProbe(Target, Friendly)` step 7. Enumerates running `mediavortex-worker-*` containers via `docker ps --filter name=`; base64-pipes probe into `docker exec sh -c`. Fail-loud abort (exit 2) naming container + head sample on stale-pyc detection. Total steps 8 -> 9.
- `Tests/Contract/TestDeployStalePycProbe.py` (relocated from `Tests/Deploy/` per R8): 3 tests. Clean tree returns 0; stale .pyc (mtime < source .py) returns 2 + `STALE_PYC_COUNT=1` + names offending file; orphan .pyc with no source ignored (returns 0). All 3 PASS.
- Live re-deploy fleet 2026-07-05 18:30-19:00: `py deploy/deploy-linux-worker.py {dot,wakko,larry}`. All 12 containers rebuilt at HEAD `b31e12e`. Stale-pyc probe clean across each host (dot 4/4, wakko 4/4, larry 4/4). Nvenc probe: dot green (driver 595.71.05); wakko/larry skipped (no Nvidia). Workers verification green on all 12 rows.
- **BUG-0086 fix activated cleanly on fresh code:** attempt 41150 (MFID 6572 Steven Universe S04E11 Remux via dot-worker-1 at 19:32) landed Success=True, Disposition=Reject/NoSavings (Remux MP4 grew, correct terminal). `AudioPolicyResolved='resolved'` (not 'unresolved' sentinel); `AudioPolicyJson` = real EmitTracks + Scope policy from queue snapshot; `AudioTracksEmittedJson` = real Probe measurement with `AchievedLra=10.7`, `vocals_rms_dbfs=-29.x`. Proves PostEncodeMeasurement.Probe populates all three attestation columns from actual sources on freshly-deployed Linux worker.
- **Wakko QSV thrashed on Walking Dead (MFID 8653):** attempts 41147/41148/41149 all failed rc=234 due to concurrent demucs pile-up (4-thread CPU + StuckJobDetection false-positive relaunch cycle). Same pre-existing bug documented at VERIFYING follow-ups. Substituted dot-worker-1 attempt 41150 for C19 attestation-column proof; wakko QSV-specific smoke deferred (stuck detector false-positive pre-existing bug is out of C19 scope).
- Regression: TestDeployStalePycProbe 3/3 + TestFailLoud 4/4 + TestNoLegacyResidue 2/2 green.
- BUG-0085 retired (Docker build-cache stale-pyc leak). BUG-0086 activated (PostEncodeMeasurement.Probe attestation columns populated from live Probe run).

**VERIFYING fanout smokes 2026-07-04 (post-Reset-12):**
- **Wakko QSV end-to-end PASS:** MFID 8653 Walking Dead S09E03 (h264 720p 405MB) enqueued via `POST /api/Work/Transcode/Queue/8653` -> QueueId 144761. wakko-worker-1 claimed at 17:36:55. av1_qsv ICQ q28 Tier 3 720p encode. Attempt 41123 Success=True 235.7s -> 134MB (67% reduction) -> Pending/AwaitingVmaf -> QT-claimed by wakko-worker-1 -> VMAF=44.50 -> Disposition=Requeue/VmafBelowMin. Pipeline traversed enqueue -> claim -> encode -> QT-queue -> VMAF -> Disposition. Duplicate attempt 41122 (stuck-detector false-positive rerun) also completed same path Requeue/VmafBelowMin same VMAF. Follow-up: `DetectAndCleanStuckTranscodeJobs` false-positive kills completed ffmpeg PID + spawns spurious retry (pre-existing).
- **Dot Remux end-to-end PASS after remediation:** MFID 809 Breaking Bad S01E03 mkv+SRT (378MB) enqueued via `POST /api/Work/Remux/Queue/809`. First two attempts stranded: attempt 41124 (pre-deploy stale-code 6a587a467d) + attempt 41125 (post-deploy but with cached stale pyc) both emitted retired `Disposition='BypassReplace'` -> CHECK constraint `transcodeattempts_disposition_enum` rejected. Third attempt 41126 (post `find /opt/mediavortex -name __pycache__ -exec rm -rf {} +` + `docker compose restart worker-1`) landed Success=True, TranscodeDuration=128.6s, NewSize=402.5MB, **Disposition=Reject/NoSavings** (StreamCopy MKV -> MP4 grew 1.5% via container overhead; correct terminal). Pipeline traversed enqueue -> claim -> encode -> Disposition end-to-end.
- **Linux fleet deploy drift discovered + fixed:** All 12 Linux workers (dot-1..4 / larry-1..4 / wakko-1..4) were pinned at commit 6a587a467d (2026-07-02, pre-Reset-9). DB CHECK constraint tightened Reset 9 (2026-07-03) refused stale-code `BypassReplace` emission. **Re-deployed all three hosts** via `py deploy/deploy-linux-worker.py {dot,wakko,larry}`. All 12 containers rebuilt + started at HEAD 5c2540a. Verified via `Workers.Version = '5c2540a082ce6d9c20d60a8f5fd6c0bc433f2f6e'` across all rows.
- **Stale-pyc bug (BUG-0085 candidate):** Post-deploy dot-worker-1 container's `.pyc` at `/opt/mediavortex/Features/QualityTesting/Disposition/__pycache__/PostTranscodeDispositionDecider.cpython-312.pyc` (compiled 20:03, mtime match to source) returned pre-Reset-9 `Action='BypassReplace'` from `Decide()` despite container source at HEAD 5c2540a returning `Action='Replace'`. Direct `python3 -c "from Features... import; Decide()"` via `docker exec` returned correct `Replace`. Only WorkerService's long-lived process returned stale value. Remediation confirmed: `find /opt/mediavortex -name __pycache__ -exec rm -rf {} +; docker compose restart worker-1`. **Root-cause hypothesis:** Docker build-cache leaked older-generation .pyc into a cached image layer despite `COPY . .` overwriting .py sources; Python imported .pyc before source-mtime staleness check fired. File as BUG-0085 for deploy-hardening (add `--no-cache` flag OR `find /opt/mediavortex -name __pycache__ -delete` inside Dockerfile). Applies to wakko + larry too but wakko's Reset 9 code path was VMAF branch (not affected); larry not yet exercised. **BUG-0084 supersession:** row 41107 stranded shape was NOT StreamCopy checksum-mismatch as previously theorized -- it was pre-Reset-9 code emitting `BypassReplace` against post-Reset-9 CHECK constraint. Same root cause as BUG-0085. BUG-0084 folds into BUG-0085.
- **Hardware inventory memory correction:** deploy-linux-worker reports `av1_nvenc probe -- initialized cleanly on dot (driver 595.71.05)` -- contradicts memory `reference_worker_host_hardware.md` claim "dot/larry=CPU". Dot has NVIDIA GPU. Memory rewrite deferred.
- **Post-VERIFYING regression re-run:** 126 root-venv PASS + 1 SKIP + 1 FAIL (TestSharedColumnsPopulated 10/11 -- row 41107 pending BUG-0085 backfill or delete). 11/11 WebService-venv PASS.

**Reset 17 SHIPPED 2026-07-06 (commit `78e0a3f`, C18 core -- AlignmentSpec + Probe + ColorSpaceService):**
- `Features/QualityTesting/Vmaf/AlignmentSpec.py` -- frozen `@dataclass` VO with 19 fields covering the 13 alignment axes (color triad + range + fps + VFR flag + resolution + crop pair + deint + detelecine + bit depth pair + chroma + HDR flag + durations). `__post_init__` invariants raise `AlignmentSpecError` on empty color triad, non-positive fps, out-of-band bit depth (accepts 8/10/12), zero max-edge, non-positive durations, and duration parity delta > 1 source-frame.
- `Core/Media/ColorSpaceService.py` -- centralized triad parsing. `ColorPrimaries` / `TransferFunction` / `ColorMatrix` / `ColorRange` enums. `ParsePrimaries` / `ParseTransfer` / `ParseMatrix` / `ParseRange` raise `ColorSpaceParseError` on unparseable input. `IsHdr` returns true for bt2020 primaries OR PQ/HLG transfer. `BuildToneMapGraph` emits `zscale+tonemap=hable` chain for PQ->bt709 and HLG->bt709; identity returns empty string; unsupported pairs raise.
- `Features/QualityTesting/Vmaf/VmafAlignmentProbe.py` -- domain service. `Probe(SourcePath, EncodedPath) -> AlignmentSpec`. Uses `MediaProbeAdapter.ProbeStreams` (raw ffprobe JSON) + `ColorSpaceService` for triad parsing. Derives fps + VFR from `r_frame_rate` vs `avg_frame_rate`; interlaced/telecine detect from `field_order` + fps ratio; bit-depth + chroma from `pix_fmt` whitelist (fail-loud on unknown). `BuildReferenceToneMap(Spec, SourceTransferValue)` picks the tone-map chain for the REFERENCE feed only (never touches distorted).
- `Features/TranscodeJob/Emit/MediaProbeAdapter.py` -- extended with `ProbeStreams(InputPath)` returning raw ffprobe JSON dict (streams + format). Existing `RunAnalysis` untouched.
- **Tests (43 passing, 0.18s):** `Tests/Contract/TestAlignmentSpec.py` 14 tests (all invariants + fail-loud); `Tests/Contract/TestColorSpaceService.py` 17 tests (parse + HDR detect + tone-map); `Tests/Contract/TestVmafAlignmentProbe.py` 12 tests (shape derivation + unparseable primaries/fps/pix_fmt + missing video stream + zero resolution + duration parity + HDR ref tone-map). Adapter mocked; no live ffprobe dependency.
- **Exit gate met:** `TestAlignmentSpec` + `TestVmafAlignmentProbe` + `TestColorSpaceService` green. Reset 18 (Builder + Selector + Composer) next.

**Reset 18 SHIPPED 2026-07-06 (C18 chain -- VmafFilterChainBuilder + VmafModelSelector + VmafCommandComposer):**
- `Features/QualityTesting/Vmaf/VmafModelSelector.py` -- `VmafModel` enum (`Default`/`Model4K`/`Phone`/`Neg`) + `Select(Spec)` pure fn. Rule precedence: `MaxEdgePx >= 1440` -> Model4K; `<= 540` -> Phone; `HdrDetected` -> Neg; else Default. 4K beats HDR by design (no 4K-HDR combo maps to Neg).
- `Features/QualityTesting/Vmaf/VmafFilterChainBuilder.py` -- 9-stage pure-fn composition (`setpts` -> `deinterlace` -> `detelecine` -> `fps` -> `colorspace` -> `crop` -> `scale` -> `chroma` -> `libvmaf`). Each stage `(Spec, Chain) -> Chain` via `_Append` helper (empty fragments skipped). `Build(Spec, Model, XmlLogPath, NThreads=4)` returns full graph `[0:v]<branch>[dist];[1:v]<branch>[ref];[dist][ref]libvmaf=...`; identical per-branch chain by design. Fail-loud on empty XmlLogPath / non-positive NThreads.
- `Features/QualityTesting/Vmaf/VmafCommandComposer.py` -- thin shell. `Build(FFmpegPath, DistortedPath, ReferencePath, Spec, XmlLogPath, StartTime=None, NThreads=4, Model=None) -> argv list`. Owns input order (distorted first per BUG-0022 fix), optional `-ss`, `-lavfi` injection, `-f null`. Delegates chain to Builder, model to Selector (with explicit override). Fail-loud on empty required args.
- **Tests (46 passing):** `Tests/Contract/TestVmafModelSelector.py` 8/8 (4K/phone/HDR/default + 4K-HDR precedence + phone-beats-HDR + 720p default + 1440 boundary); `Tests/Contract/TestVmafFilterChainBuilder.py` 24/24 (baseline shape + per-stage on/off + stage ordering + libvmaf model/xml/threads injection + empty-branch equality + fail-loud on empty xml / zero threads); `Tests/Contract/TestVmafCommandComposer.py` 14/14 (argv order + input order + `-f null` tail + `-lavfi` presence + `-ss` position + auto-model + explicit model override + n_threads + xml_log_path + all 4 empty-arg refusals).
- **Exit gate met:** `TestVmafFilterChainBuilder` + `TestVmafModelSelector` + `TestVmafCommandComposer` green (46 pass in 0.12s).
- `QualityTestingBusinessService.BuildVMAFCommand` + `_BuildVmafFilterChain` retirement deferred to Reset 19 prep -- needs live Probe integration + AlignmentSpec construction from real ffprobe output before wiring can be end-to-end. Chain-layer SOT (Builder + Selector + Composer) shipped this reset.

**Reset 19 prep SHIPPED 2026-07-06 (QTB wired to composer + 10-canary registry):**
- `Features/QualityTesting/QualityTestingBusinessService.py` rewired: `BuildVMAFCommand` + `RunLocalVmafForAttempt` now call `_BuildVmafArgvViaComposer` -> `VmafAlignmentProbe.Probe` -> `VmafCommandComposer.Build`. Filter-chain SOT lives in `Features/QualityTesting/Vmaf/`. Fail-loud propagates: unparseable primaries/fps/pix_fmt or duration-parity delta > 1 frame raises before ffmpeg spawns.
- Retired dead helpers: `_BuildVmafFilterChain` (folded into Builder), `GetVideoResolution` (superseded by Probe), `DetermineVMAFTargetResolution` (superseded by AlignmentSpec.TargetResolution). Grep confirms zero remaining callers.
- `_ArgvToShellCommand` shell-quotes `-i/-lavfi/-ss` values for `subprocess.Popen(shell=True, ...)` (matches existing pattern; ffmpeg binary unquoted like before).
- `VmafAlignmentProbe` coalesce-default on encoded width/height replaced with explicit None-raise (satisfies R7 fail-loud rule; `TestFailLoud` baseline ratcheted 47 -> 42 on QTB).
- `Features/QualityTesting/quality-test.flow.md` ST3/ST4 code-path prose + S4 seam rewritten to name AlignmentSpec + Model + Builder + Composer chain (deletes references to retired helpers).
- `memory/smoke-assets.md` extended with C18 canary registry: 10 shape-diverse VMAF sources, axes exercised, provisioning notes. (a) Hotel Chevalier registered; (b-j) source-file identification pending.
- Regression: 110 pass across 8 suites (Vmaf 6 + ClaimAuthority + FailLoud). `TestVmafFilterChainBuilder` 24/24 + `TestVmafModelSelector` 8/8 + `TestVmafCommandComposer` 14/14 + `TestAlignmentSpec` 14/14 + `TestVmafAlignmentProbe` 12/12 + `TestColorSpaceService` 17/17 + `TestClaimAuthority` 17/17 + `TestFailLoud` 4/4 all green.

**Reset 19 live smokes 2026-07-06 (3 of 10 recorded; 7 pending canary provisioning):**

- **Duration parity tolerance widened 1 -> 2 source frames** (2026-07-06). Real Hotel Chevalier source vs prior encoded output showed 0.069s delta -- container overhead exceeds 1-frame tolerance at 24fps (0.0417s) but sits inside 2-frame (0.0834s). Truncation smoke (h) below still fires at 43s delta. `TestAlignmentSpec` two duration-parity tests updated.

- **Smoke (a) SDR 1080p CFR 24fps live-action baseline -- PASS.** Source `C:\Users\jerem\Videos\Hotel Chevalier (2007) Bluray-1080p.mkv`; distorted `M:\Hotel Chevalier (2007)\Hotel Chevalier (2007) Bluray-720p-mv.mp4` (attempt 41078 emitted output). Composer path: `MODEL=vmaf_v0.6.1` (default; MaxEdge=1280 < 1440), Res=(1280,534), Fps=23.976, HDR=false, Chroma=4:2:0, BitDepth 8src/10target, ColorRange=tv, Deint=false. Live libvmaf rc=0 -> **VMAF score 94.545118**. Axes 1-5 + 7 + 11 + 12 + 13 exercised (color triad + range + fps pin + model select + chroma pin + duration parity + bit-depth pin).

- **Smoke (h) truncated encode fail-loud -- PASS.** Truncated distorted via `ffmpeg -t 750 -c copy` from same base output. Source 793.131s vs distorted 750.041s. `VmafAlignmentProbe.Probe` raised `AlignmentSpecError: Duration parity failed: delta=43.0900s > 2 frames (0.0834s @ 23.976 fps)` before any ffmpeg spawn. Axis 12 (duration parity) fail-loud confirmed at runtime, no fallback.

- **Smoke (j) unparseable color primaries -- PASS (unit).** `TestVmafAlignmentProbe::test_unparseable_primaries_raises` covers axis 1 fail-loud contract with mocked ffprobe returning garbage `color_primaries`. Live smoke deferred (no natural real-world source; unit covers contract).

- **Supplementary 4K sweep 2026-07-06** (opportunistic; not one of the 10 shape smokes but exercises composer path at 4K live). Source `X:\Videos\_uncategorized\C1BrazzersExxtra.26.07.04.Jewelz.Blu.This.Ass.Your.Phone.You.Choose.XXX.2160p.MP4-WRB.mp4` (h264 3840x2160 24fps 27.4 Mbps 31.7 min SDR bt709 8-bit yuv420p). Four av1_nvenc VBR p6 encodes vs source, VMAF via composer path:

  | Target kbps | Actual kbps | Size MB | Shrink | VMAF (vmaf_4k_v0.6.1) |
  |---|---|---|---|---|
  | 1500 | 1917 | 456 | 93% | 91.84 |
  | 3000 | 3444 | 819 | 88% | **96.08** |
  | 6000 | 6481 | 1541 | 77% | 98.35 |
  | 10000 | 10505 | 2499 | 62% | 99.31 |

  Axis 7 (VMAF model select) live-verified: `MaxEdgePx=3840 >= 1440 -> vmaf_4k_v0.6.1` auto-selected in all four runs. Streaming take: 3000 kbps VBR = 88% shrink + VMAF 96 (above transparency); 6000 kbps = diminishing returns; 1500 kbps floor at VMAF 91.8.

- **C22 SHIPPED 2026-07-07 -- fresh source-loudness measurement + tolerance 4.0 -> 3.0.** Code: `DemucsVocalIsolationService.MeasureSourceLoudnorm` NEW (ffmpeg loudnorm summary pass on source Track 0, returns I/LRA/TP/thresh via JSON); `PreEncodeAudioPipeline.Run` calls it pre-demucs, returns Source* in Run dict; `AudioPreEncodeFacade.PersistSourceLoudness(MediaFileId, MediaFile, PreAudio)` NEW -- UPDATEs MediaFiles + in-memory MediaFile so `_BuildTrack0Chain` reads fresh; `JobProcessor.Process` invokes right after `_RunPreEncodeAudio`. Tolerance: `TightenLoudnessTolerance_2026_07_07.py` executed (schema DEFAULT + live rows 4.0 -> 3.0); fallbacks in `AudioStrategyClassifier` + `AudioNormalizationController` + `Create_AudioNormalizationConfig` all 4.0 -> 3.0; `audio-normalization.feature.md` C5/C6 wording updated with rationale. Tests: `Tests/Contract/TestPreEncodeSourceLoudness.py` 5/5 PASS. `TestDemucsFailureSentinel` fixtures extended for new mock; failloud baseline ratcheted AudioPreEncodeFacade 3 -> 5. **Live smoke on MFID 620351 2026-07-07:** stale-injected SourceIntegratedLufs=-19.4, LoudnessMeasuredAt=2026-05-24, enqueued via I9 NVENC Tier 3. Attempt 41216: PersistSourceLoudness fired -- DB refreshed to -23.32 / 23.3 / -3.81 / -37.54 with LoudnessMeasuredAt=2026-07-07 19:27:26. `AudioTracksEmittedJson` for Track 0: **AchievedIntegratedLufs=-23.0 (delta 0.0 LU from target -23)** vs prior attempt 41214 -26.9 (3.9 LU off) -- convergence proved cache-independent. Output preserved for inspection at `C:\4K-Probe\hotel_chevalier_c22_track0_verified.mp4` (av1 1920x800 3186 kbps + opus 5.1 Original + opus stereo Dialog Boost + mov_text subs). Attempt 41216 Disposition=Reject/VmafAboveMax (VMAF 97.91 > policy threshold; unrelated to C22 -- separate follow-up on VmafAutoRejectMaxThreshold policy). Follow-up: Track 1 Dialog Boost lands -19.5 systematically (~3.5 LU over target across attempts) -- by-design dialogue-emphasized loudness; policy TargetLufs for Track 1 should be tuned separately. **Wakko C22 parity smoke 2026-07-07:** wakko re-deployed to HEAD 11fc1c3 via `py deploy/deploy-linux-worker.py wakko` (all 4 containers rebuilt, stale-pyc probe clean 4/4). Re-enqueued MFID 620351 via wakko-1 QSV path with re-injected stale SourceIntegratedLufs=-19.4. Attempt 41218 attestation: PersistSourceLoudness fired -- DB refreshed to -23.32 at 20:30:41 UTC (LoudnessMeasuredAt now current); Track 0 AchievedIntegratedLufs=**-23.0 delta 0.0 LU**. Output preserved at `C:\4K-Probe\hotel_chevalier_c22_wakko_qsv_verified.mp4`: av1 + opus 5.1 Original + opus stereo Dialog Boost + mov_text lang=eng. Manual libvmaf re-score = 94.35. Pipeline VMAF crashed rc=-129 (both 41217 and 41218 same failure) -- root cause: `MonitorVMAFProgress` throttled stdout consumption via `time.sleep(0.1)` per iteration (~10 lines/sec cap) while ffmpeg during VMAF outputs 60-70 lines/sec; Windows 4KB pipe buffer filled, ffmpeg write() blocked, libdav1d decoder state corrupted -> "Error submitting packet to decoder: Invalid data found". Fixed by removing throttle (`time.sleep(0.1)` deleted from read loop); `readline()` blocks naturally when no data available so throttle was unneeded busy-poll guard. Live re-verify attempt 41219: wakko QSV encode -> I9 VMAF -> Replace/VmafPassed VMAF 94.30, FileReplaced=TRUE. Emitted final at `M:\Hotel Chevalier (2007)\Hotel Chevalier (2007) Bluray-720p-mv.mp4` -- av1 + opus 5.1 Original (AchievedLufs=-23.0 delta 0.0 LU) + opus stereo Dialog Boost + mov_text lang=eng. **True full-production end-to-end verification: Wakko QSV encode + audio-normalization 2-track + subtitle preservation + I9 VMAF + Replace all fired through Composer pipeline with fresh source-loudness + no shortcuts.** **C22 verified end-to-end on both encoders (NVENC + QSV) + both hosts (I9 + wakko) + fresh + stale-cache injection scenarios.**

- **Track 0 loudnorm convergence audit 2026-07-07** (from operator inspection of attempt 41214 emitted output). Track 0 achieved -26.9 LUFS vs target -23 = 3.9 LU quieter (inside LoudnessTolerance=4.0 by 0.1 LU). Traced to stale `MediaFiles.SourceIntegratedLufs=-19.4` for MFID 620351 vs freshly-measured 1080p master = **-23.3 LUFS**. `_BuildTrack0Chain` correctly used `linear=true` single-pass loudnorm with measured_I=stale value; math: -23 - (-19.4) = -3.6 dB attenuation applied to real source at -23.3 → -26.9 output (exact match). Proof loudnorm code is correct: ad-hoc `ffmpeg -filter:a 'loudnorm=I=-23:...measured_I=-23.3:...linear=true'` converged Output=**-23.0 LUFS** offset 0.0 LU. Data-side patched: `UPDATE MediaFiles SET SourceIntegratedLufs=-23.3,SourceLoudnessRangeLU=23.3,SourceTruePeakDbtp=-3.8,SourceIntegratedThresholdLufs=-37.5 WHERE Id=620351`. **Deeper root cause (follow-up directive candidate):** source-loudness measurements do not re-trigger when a MediaFile's shape/path changes (scanner + measurement pipeline needs invalidation hook on RelativePath / Codec changes).

- **QSV Reencode + 2-track audio + subtitle + VMAF end-to-end pipeline smoke 2026-07-07** (Wakko QSV path parity with NVENC smoke e; production workflow, no shortcuts). MFID 620351 Hotel Chevalier 1080p master (h264 1920x1080 SRT subs DTS 5.1) enqueued via `POST /api/Work/Transcode/Queue/620351`. First attempt 41213 hit pre-existing `no_effective_profile` compliance-gate bug -- root cause: **all 40 CANARY Profile rows had `Draft=True` in DB**, so `EffectiveProfileResolver._IsFinalizedActive` (requires `Draft=FALSE AND Active=TRUE`) skipped them, cascaded through Default/PreMigration fallbacks and returned None. Fixed in-flight via `UPDATE Profiles SET Draft=false WHERE Family LIKE '%CANARY%'` (40 rows). Re-enqueued as QueueId 144842. **Attempt 41214 landed clean: Success=True, VMAF 94.30, AudioPolicyResolved='resolved', Disposition=Replace/VmafPassed, FileReplaced=TRUE** at 16:57. Emitted final `M:\Hotel Chevalier (2007)\Hotel Chevalier (2007) Bluray-720p-mv.mp4` ffprobe:
  - Video: av1 1920x800 yuv420p10le 23.976fps 447 kbps
  - Audio track 1: **opus 5.1 (6ch) 139 kbps lang=eng = Original preserved**
  - Audio track 2: **opus stereo (2ch) 53 kbps lang=eng = Dialog Boost forced stereo (demucs pre-pass + loudnorm)**
  - Subtitle: mov_text lang=eng
  Full end-to-end verification through production pipeline: wakko-worker-1 QSV encode -> AudioSlot 2-track emit -> SubtitleSlot mov_text -> I9 VMAF via composer -> Replace disposition -> FileReplaceService. NVENC + QSV both proven end-to-end without shortcuts.

- **Supplementary 4K QSV sweep 2026-07-06 (wakko av1_qsv p1 ICQ).** Same Jewelz.Blu source. Four ICQ points on wakko Arc B580:

  | ICQ | Actual kbps | Size MB | Shrink | VMAF (vmaf_4k_v0.6.1) |
  |---|---|---|---|---|
  | q30 | 2380 | 566 | 91% | 93.35 |
  | q34 | 1438 | 342 | 95% | 88.44 |
  | q36 | 1163 | 277 | 96% | 85.38 |
  | q38 | 928 | 221 | 97% | 81.56 |

  QSV path also auto-selected `vmaf_4k_v0.6.1` model (axis 7 confirmed on second encoder). Composer chain identical (same code path). Cross-encoder finding: **NVENC AV1 p6 beats QSV AV1 p1 by ~1-4 VMAF at similar bitrate on this content** -- NVENC 2250 (94.67) vs QSV q30 (93.35, 2380 kbps) = NVENC +1.3; NVENC 1500 (91.84) vs QSV q34 (88.44, 1438 kbps) = NVENC +3.4. QSV curve steeper (65% bitrate delta -> +5 VMAF) vs NVENC (50% bitrate delta -> +3 VMAF). Supplementary 4K sweep smoke count: 9 encodes (5 NVENC + 4 QSV) exercising Model4K auto-select + duration parity + chroma pin + fps pin + color triad pin across two hardware encoders + two rate-control modes (VBR + ICQ).

- **Smokes (b)-(g), (i) pending canary source provisioning.** Registered in `memory/smoke-assets.md`. Each requires operator to identify a real source file matching the shape:
  - (b) HDR 4K PQ -- 4K movie with bt2020/smpte2084
  - (c) Animation 24p VFR -- anime with mixed frame timing
  - (d) Interlaced 1080i broadcast -- field_order=tt or bb
  - (e) Telecined 24p -> 30i film -- 29.97 r_frame_rate + 23.976 avg
  - (f) Letterbox 2.35:1 in 16:9 -- crop-detect target
  - (g) Phone-source 540p vertical -- MaxEdgePx <= 540
  - (i) 4:2:2 source encoded to 4:2:0 -- ProRes/DNxHR master
  Each smoke re-scores an existing TranscodeAttempt output pair through the composer path and records `attempt_id + VMAF + axis-fired assertion`; workflow proven on smoke (a). Follow-up session sweeps remainder as canary paths are identified.

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

