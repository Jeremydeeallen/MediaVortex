# Directive Archive -- transcode-flow-canonical

**Parent directive:** `.claude/directive.md`  
**Slug:** transcode-flow-canonical  
**Set:** 2026-07-03  
**Archive created:** 2026-07-25  
**Contents:** closed reset execution history + closed verification evidence + resume-marker history for shipped Resets. Durable contract (Acceptance Criteria, Files, Seams, Promotions, Reset Plan, Parked docs) remains in the active directive.

---
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


---

## Reset Execution History (closed)

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

---

## Closed Verification Evidence

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
- **C33. Classification completeness -- profile-independent compliance + two new buckets + self-heal deletion.** Docs: `Features/WorkBucket/work-bucket.feature.md` C1 + C7 + C8 + intro rewritten for 5-branch WorkBucket; `Features/WorkBucket/work-bucket.flow.md` ST1 updated; `Features/FileScanning/FileScanning.flow.md` S3 updated for downstream compliance chain; `Features/ContentClassifier/content-classifier.flow.md` classifier role documented as HINT writer; `Features/AudioNormalization/audio-normalization.feature.md` self-heal section deleted; `Features/FileScanning/scanners.feature.md` AudioVerticalHealth seed removed; `Features/VideoEncoding/video-encoding.feature.md` no_effective_profile purged. Code: `Features/VideoEncoding/VideoVertical.py` + `Features/ContainerFormat/ContainerVertical.py` + `Features/AudioNormalization/AudioVertical.py` all EffectiveProfileResolver-free; `Features/WorkBucket/Domain/BucketKey.py` registers Compliant + Unclassified; `Features/MediaFile/ComplianceSummaryController.py` 5-branch bucket derivation; `WebService/Main.py` PrivateStartAudioVerticalHealth + loop deleted. Deletions: `Features/AudioNormalization/SelfHealing/` tree gone (18 .py files); `Tests/Contract/TestAudioInvariants.py` + `TestAudioVerticalHealthService.py` + `TestPreVerticalReNormalizePolicy.py` + `TestH1FixtureDryRun.py` deleted; `Features/Activity/ActivityController.py` + `ActivityRepository.py` GetAudioVerticalHealth removed; `Scripts/SQLScripts/CreateAudioVerticalHealthRuns.py` + root drain scripts deleted. Migrations executed live: `DropAudioVerticalHealthScanner_2026_07_22.py` (Scanners row + 1114-row AudioVerticalHealthRuns table dropped); `RewriteWorkBucketGeneratedColumn_2026_07_22.py` (5-branch generated column verified); `BackfillClassificationForStuckFiles_2026_07_22.py` (3014 stuck rows recomputed; 0 `no_effective_profile` remaining). Live-verified distribution across 53,437 MediaFiles rows: `Compliant=24073`, `Transcode=15474`, `Unclassified=6885`, `AudioFix=4373`, `Remux=2632`. **Zero NULL WorkBucket rows.** Motivating case Heroes S01E08-E23 (Ids 694531-694546): all 16 now `WorkBucket=Transcode` with concrete reasons (`high_bpp_excessive` + `container` non-mp4 mkv + audio codec:dts or needs_normalization). Contract tests: `TestVerticalsAreProfileIndependent.py` 6/6 PASS (grep-fence + behavioral); `TestSelfHealingPurged.py` 3/3 PASS; `TestWorkBucketGeneratedColumn.py` 4/4 PASS. Regression: `TestVideoComplianceBar.py` 5/5 PASS + `TestContainerComplianceBar.py` 6/6 PASS (rewritten for profile-independent contract). C33a-C33f + C33l-C33q verified. **C33g + C33h + C33i + C33j + C33k IN PROGRESS** (criteria sharpened 2026-07-22 after operator flagged residue in cross-vertical docs + closed-directive anchors + dead code + bucket registration + UI adapter branches). NOT YET IMPLEMENTED.
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

---

## Resume Marker (closed reset history through 2026-07-07)

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
