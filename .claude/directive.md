# Current Directive

**Set:** 2026-07-03
**Status:** Active -- phase: NEEDS_STANDARDS_REVIEW
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

Populated at NEEDS_PLAN when Out of Scope list is drafted. Every OOS item must carry `(a)` (behavior preserved + duplication collapsed) or `(b)` (debt survives directive) tag. Default (a).

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

_(drafted at NEEDS_PLAN exit from Call-Graph Audit findings; do NOT populate here until Signal audit complete)_

## Status

### Progress

- [ ] NEEDS_STANDARDS_REVIEW: audit five signals, populate sections above.
- [ ] NEEDS_PLAN: draft criteria + Files + Reset Plan from audit findings.

### Files

_(populated at NEEDS_PLAN)_

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
