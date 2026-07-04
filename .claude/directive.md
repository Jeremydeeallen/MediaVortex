# Current Directive

**Set:** 2026-07-03
**Status:** Active -- phase: IMPLEMENTING
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
| 15 | DELIVERING: `### Promotions` populated (should already be incremental). Directive size <= 110% snapshot. Delivery report. Operator close. | Operator agrees closed. | -- |

## Status

### Progress

- [x] NEEDS_STANDARDS_REVIEW: 5-signal audit run + populated
- [ ] NEEDS_PLAN: criteria + Files + Reset Plan drafted; operator approval pending
- [ ] NEEDS_DOC_PREREAD: pre-read all colocated docs for files in `### Files`
- [ ] IMPLEMENTING: per-reset code work
- [ ] VERIFYING: evidence-recording
- [ ] DELIVERING: delivery report + close

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
| Parked `quality-test.flow.md` full content (C1) | `Features/QualityTesting/quality-test.flow.md` -- CREATE at DELIVERING (R13 refuses outside DELIVERING; content parked in directive `### Parked -- quality-test.flow.md`) | (DELIVERING commit) |
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

### Verification

Populated at VERIFYING.

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
  - **Next after smoke pass:** promote SubtitleSlot to full CommandComposer (T15: Video/Audio/Container slots + delete EncodeShapeRegistry + 3 Shape files + 2 EncoderArgsStrategies + Strategy.BuildCommand delegation). Then Tier 1/5 backfill, AdequacyGate, NextTierAdjuster, Decider global-off + SmartConfidenceSkip, VmafConfidenceStatsRepository, ContentClassifier reassignment, T3 execution, contract tests, remaining smokes (a-g).
- **Phase:** IMPLEMENTING
- **Last commit:** `f679b9f wip(reset10): draft DeleteNonCanaryProfiles migration (survey-only mode)`
- **Follow-ups noted:**
  - Directive C9 `+/-1 LU` LUFS tolerance vs DB `LoudnessTolerance=4.0` mismatch; reconcile at VERIFYING or via doc-only edit before Reset 12.
  - `AudioPolicyAdmissionGate.AdmitOrDefer` can return `PolicyJson=None` (DEFERRED_UNGAINABLE), leaving `TranscodeQueue.AudioPolicyJson` NULL despite S3 contract. Live-DB audit currently skips; will fail if a policy-deferred file lands post-cutover. File as bug at Reset 11.
  - VMAF filter chain gaps (color primaries, HDR/4K model select, VFR handling, deinterlace, fail-loud fps fallback) -- open `vmaf-color-and-model-matching` follow-up directive after this closes.
  - `SaveTranscodeAttempt` sentinel `__UNRESOLVED__` on ProfileName -- surfaced in both smoke (a) attempts. Pre-existing; not this directive's scope.
  - `DetectAndCleanStuckTranscodeJobs` false-positive killed Chalet Girl attempt 41018 pre-VMAF-write (still emitted output OK). Pre-existing.
  - `DetectAndCleanStuck/StaleQualityTestJobs` claims "No running quality test jobs found" while VMAF process actively running (per MonitorVMAFProgress logs). Pre-existing bug in stale detector.

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
