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
| 11 | C7 sweep: grep audit; remove silent fallbacks. Contract test `TestFailLoud` green. Fix BUG-0077 as instance (freeze -> Success=FALSE). | `TestFailLoud` green. | **RESET 10** |
| 12 | VERIFYING: run every criterion's verification, record evidence in `### Verification`. Four live smokes documented. Directive size snapshot. | Criteria all IMPLEMENTED with evidence; snapshot recorded. | **RESET 11** |
| 13 | DELIVERING: `### Promotions` populated (should already be incremental). Directive size <= 110% snapshot. Delivery report. Operator close. | Operator agrees closed. | -- |

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

# Reset 10 -- C7 sweep + BUG-0077
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

### Promotions

Populated incrementally per step.

| Source (directive) | Target | Commit |
|---|---|---|
| Job Types section spec (C0a) | `ARCHITECTURE.md` `## Job Types` | (Reset 2 commit) |
| Gap to Target re-audit (Signal 3 findings + missing artifacts) | `ARCHITECTURE.md` `## Gap to Target` | (Reset 2 commit) |
| Glossary tier definition (C0b) | `GLOSSARY.md` created; `.claude/rules/doc-layering.md` tier row added | (Reset 3 commit) |
| Deprecated-term inventory (Remux / BypassReplace / ProcessingMode / Transcode ambiguity / AudioFix / SubtitleFix / Quick) | `GLOSSARY.md` Media-encoding + Job-model buckets | (Reset 3 commit) |

### Verification

Populated at VERIFYING.

### Resume Marker

- **Current step:** Reset 3 complete -- GLOSSARY.md created (4 buckets alphabetical, every entry cites authoritative source); CLAUDE.md links it; doc-layering.md adds Glossary tier row
- **Next:** Reset 4 -- create `.claude/rules/fail-loud.md` + `.claude/rules-details/fail-loud.md` (C7 pre-step, BEFORE code sweep)
- **Phase:** IMPLEMENTING
- **Last commit:** (Reset 3 pending commit)

### Promotions

_(populated incrementally per step; required at DELIVERING)_

| Source (directive) | Target | Commit |
|---|---|---|

### Verification

_(populated at VERIFYING)_

### Resume Marker

- **Current step:** 0 -- NEEDS_STANDARDS_REVIEW, running Call-Graph Audit
- **Next:** Signal 1 -- enumerate flow docs
- **Last commit:** (this directive-open commit; pending)
