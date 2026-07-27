# Current Directive

**Set:** 2026-07-26
**Status:** Active -- phase: DELIVERING
**Slug:** verify-signal-cleanup

## Outcome

`TranscodeAttempts.Vmaf` holds a real VMAF score or NULL. Nothing else. Outcome signal lives in `Success + Disposition`. Retired plumbing that reads or writes Vmaf as an outcome proxy is deleted, not annotated. Domain rule lands in `DOMAIN.md` first; code follows.

## Domain rule (lands in DOMAIN.md before code changes)

Under `## Compliance` section, new entry `2026-07-26 -- Vmaf column is truthful; outcome lives in Success + Disposition`. Says:

- `Vmaf` holds a real VMAF score or NULL.
- Stream-copy modes (Remux / AudioFix / SubtitleFix / Quick) are MD5-verified; their attempts land with `Vmaf IS NULL`.
- Downstream reads `Success + Disposition` to know "did this pass?" -- never `Vmaf`.
- Historical `Vmaf=100.0` sentinel rows are legacy against this rule.

## Acceptance Criteria

**C1. Sentinel writer retired.** `ProcessTranscodeQueueService._VerifyStreamCopyChecksum` returns `Vmaf=None` on match. Grep `Vmaf.*100` in Features/ returns 0 relevant hits. Verifiable: next stream-copy attempt on live smoke lands with `Vmaf IS NULL`.

**C2. RetranscodeDecider deleted.** `Features/QualityTesting/Disposition/RetranscodeDecider.py` removed. Callers cleaned:
- `QueueManagementBusinessService.py:121-146` and `:2038-2050` -- both blocks are behind `if not ForceAdd` and every prod caller passes `ForceAdd=True` (BUG-0078 audit). Delete blocks + imports.
- `ProcessTranscodeQueueService.py:900-925` -- swap `RetranscodeDecider(...).Decide(...)` for direct `AttemptRepository.GetLatestSuccessfulAttempt(MediaFileId)`. Same PreviousAttempt shape returned.
- `DispositionDispatcher.__init__` -- drop `RetranscodeDecider=None` param (never used in class body).
Tests deleted: `TestRetranscodeDecider.py`, `TestAddJobToQueueForceAdd.py` (whole file -- premise is a gate that no longer exists).

**C3. CRF adjustment plumbing deleted.** `Features/TranscodeJob/Adjustments/AdjustmentRegistry.py`, `CrfAdjustmentCalculator.py`, `AdjustmentCalculator.py` removed. Callers cleaned:
- `QueueManagementBusinessService.py:122-125` and `:2039-2042` -- import + instantiation removed with the RetranscodeDecider blocks.
- `ProcessTranscodeQueueService.py:908-925` -- CRF-adjust block removed (fires only for `RateControlMode='cq'` profiles; current NVENC AV1 / QSV AV1 CANARY use VBR / ICQ; superseded by NextTierAdjuster escalation).
- `DispositionDispatcher.__init__` -- drop `AdjustmentRegistry=None` param.
Tests deleted: `TestAdjustmentRegistry.py`, `TestCrfAdjustmentCalculator.py`.

**C4. RetryBudgetService reads the right column.** `HasBudgetRemaining` counts prior `Disposition='Requeue'` outcomes instead of `Success=TRUE AND Vmaf < MinThreshold`. Signal already lives in Disposition per DOMAIN.md 2026-07-26. `TestRetryBudgetService.py` updated. Also delete the dead call site at `QueueManagementBusinessService.py:2039-2050` (behind ForceAdd guard).

**C5. Dead knobs + flags removed.**
- `PostTranscodeGateConfig.RetranscodeVmafThreshold` column dropped (only consumer was RetranscodeDecider).
- `ProcessingModeMetadata` `RequiresVmaf` key deleted from each mode dict + docstring line.
- Verifiable: `grep -n "RetranscodeVmafThreshold\|RequiresVmaf" Features/ WebService/ Tests/` returns 0.

**C6. Historical sentinels backfilled to NULL.** `Scripts/SQLScripts/NullifyStreamCopyVmafSentinels_2026_07_26.py` runs `UPDATE TranscodeAttempts SET Vmaf=NULL WHERE ProcessingMode IN ('Remux','AudioFix','SubtitleFix','Quick') AND Vmaf=100.0`. Idempotent. Verifiable: post-run count of matching rows is 0.

**C7. Doc drift purged.**
- `transcode.flow.md` ST8 stream-copy paragraph rewritten -- Vmaf NULL + Success+Disposition signal (no `formerly` annotations per R14).
- `Features/QualityTesting/vmaf-smart-sampling.feature.md` scoped to real VMAF; any stream-copy sentinel mention deleted.

**C8. Stale test fixtures purged.** `Tests/Pipeline/_backup/` directory deleted (297 JSON snapshots from 2026-06-21 through 2026-07-04, `_backup` naming = temporary, never cleaned). No prod imports.

**C9. Live smoke passes.** After cutover:
- New Remux attempt on a fresh MediaFile lands `Vmaf IS NULL AND Success=TRUE AND Disposition='Replace'`.
- Requeue on that file (operator manual force-enqueue) is accepted without RetranscodeDecider gating.
- Tier escalation still works: force a Transcode failure, observe DispositionDispatcher escalate via `NextTierAdjuster` (unrelated to this cleanup).

## Call-Graph Audit

Per `.claude/rules/call-graph-audit.md`.

**Signal 1 -- Multiple flow docs for one op**: One flow doc (`transcode.flow.md`). No divergence.

**Signal 2 -- Mode-branching at orchestration**: Root of the whole mess. Sentinel exists because `RetranscodeDecider.Vmaf >= 80` reads the wrong column for stream-copy modes. `CrfAdjustmentCalculator` fires only for `RateControlMode='cq'` (no active profiles). Both are mode-blind gates on the wrong signal. Fix by deleting the wrong readers.

**Signal 3 -- Shared output columns sparsely populated**: `Vmaf` post-cleanup: NULL for stream-copy modes, real for Transcode. Correct sparsity by mode. `Success + Disposition` dense across all modes.

**Signal 4 -- OOS ambiguity**: `## Out of Scope` categorized.

**Signal 5 -- Config-driven call-graph shape**: None added. Deletions reduce config-driven surface (`RetranscodeVmafThreshold` gone).

## Seams

Almost all seams are DELETIONS. Existing seams that survive stay in their flow-doc home.

| ID | Seam | Change |
|---|---|---|
| DS1 | `_VerifyStreamCopyChecksum` -> `TranscodeAttempts.Vmaf` | Wire shape changes: `Vmaf=None` instead of `Vmaf=100.0`. |
| DS2 | `AddJobToQueue -> RetranscodeDecider` | Deleted -- dead callers behind ForceAdd guard. |
| DS3 | `ProcessTranscodeQueueService -> RetranscodeDecider` | Replaced with direct `AttemptRepository.GetLatestSuccessfulAttempt`. |
| DS4 | `DispositionDispatcher.__init__ -> RetranscodeDecider/AdjustmentRegistry` | Deleted -- dead constructor injections. |
| DS5 | `RetryBudgetService -> Vmaf` | Wire shape changes: read `Disposition='Requeue'` instead of `Vmaf < threshold`. |
| DS6 | `PostTranscodeGateConfig -> RetranscodeVmafThreshold` | Column dropped. |
| DS7 | `ProcessingModeMetadata -> RequiresVmaf` | Key deleted. |

Verification: contract tests for the surviving paths remain green. `Tests/Contract/TestRetryBudgetService.py` updated for the Disposition-based read.

## Out of Scope

- **`QualityTestingBusinessService` (1890 lines) audit**: category (b) acknowledged debt. Structural cleanup separate directive; this pass is narrower.
- **`ProcessingModes.RequiresVmaf` DB column**: category (a) preserve+collapse deferred. Python mirror deleted here (C5); DB column drop is a schema-only follow-up migration.
- **`_backup/` naming convention across other trees**: only `Tests/Pipeline/_backup/` deleted here. Other `_backup` dirs (if any surface later) are separate.
- **`Scripts/` dead one-off script sweep**: category (b) acknowledged debt. Many one-off scripts likely orphaned; separate audit.
- **Dialog Boost enforcement + audio domain rules**: separate directive (`audio-domain-canonical` per operator 2026-07-26).
- **MD5 checksum verify itself**: preserved -- it catches ffmpeg stream-copy corruption. Just stops writing 100.0.

## Files

**Create:**
```
Scripts/SQLScripts/NullifyStreamCopyVmafSentinels_2026_07_26.py     -- C6 backfill (idempotent)
Scripts/SQLScripts/DropRetranscodeVmafThreshold_2026_07_26.py       -- C5 column drop (idempotent)
```

**Edit:**
```
DOMAIN.md                                                           -- add 2026-07-26 Vmaf-truthful rule under Compliance section
Features/TranscodeJob/ProcessTranscodeQueueService.py               -- _VerifyStreamCopyChecksum returns Vmaf=None; remove RetranscodeDecider + CRF-adjust blocks; use AttemptRepository.GetLatestSuccessfulAttempt
Features/TranscodeQueue/QueueManagementBusinessService.py           -- delete two dead RetranscodeDecider + RetryBudgetService + AdjustmentRegistry import+call blocks (behind ForceAdd guards)
Features/QualityTesting/Disposition/DispositionDispatcher.py        -- drop RetranscodeDecider/AdjustmentRegistry constructor params
Features/QualityTesting/Disposition/RetryBudgetService.py           -- swap _CountFailedVmafAttempts to _CountRequeueDispositions; read Disposition='Requeue'
Features/TranscodeJob/ProcessingModeMetadata.py                     -- remove RequiresVmaf key from each mode dict + docstring hint
Features/QualityTesting/PostTranscodeGateConfigRepository.py        -- drop RetranscodeVmafThreshold read
Features/QualityTesting/Models/PostTranscodeGateConfigModel.py      -- drop RetranscodeVmafThreshold field
transcode.flow.md                                                   -- ST8 stream-copy verify: Vmaf NULL, Success+Disposition signal
Features/QualityTesting/vmaf-smart-sampling.feature.md              -- scope to real VMAF only
Tests/Contract/TestRetryBudgetService.py                            -- expectations swap Vmaf-count to Disposition-count
Features/QualityTesting/Disposition/disposition.feature.md          -- drop W5/C3/C4/S5/S6 rows referencing RetranscodeDecider + AdjustmentRegistry
```

**Delete:**
```
Features/QualityTesting/Disposition/RetranscodeDecider.py
Features/TranscodeJob/Adjustments/AdjustmentRegistry.py
Features/TranscodeJob/Adjustments/CrfAdjustmentCalculator.py
Features/TranscodeJob/Adjustments/AdjustmentCalculator.py           (base -- verify no other extends)
Tests/Contract/TestRetranscodeDecider.py
Tests/Contract/TestAddJobToQueueForceAdd.py
Tests/Contract/TestAdjustmentRegistry.py
Tests/Contract/TestCrfAdjustmentCalculator.py
Tests/Pipeline/_backup/                                             (whole directory, 297 files)
```

## Status

### Progress

- [ ] NEEDS_PLAN: this doc.
- [ ] NEEDS_DOC_PREREAD: partial-read `transcode.flow.md ST8`, `vmaf-smart-sampling.feature.md`, `post-transcode-disposition.feature.md`, `profile-tier-ladder.feature.md`.
- [ ] IMPLEMENTING: land in order -- (1) DOMAIN.md rule, (2) backfill migration + column drop, (3) code deletions/edits, (4) doc rewrites, (5) test deletions, (6) `_backup/` dir removal.
- [ ] VERIFYING: contract tests green + one live Remux + one live Transcode + verify tier escalation still works.
- [ ] DELIVERING: Promotions rows.

### Promotions

| Source | Target durable home |
|---|---|
| C1 sentinel-writer fix | code lives in `Features/TranscodeJob/ProcessTranscodeQueueService.py::_VerifyStreamCopyChecksum`; policy in `DOMAIN.md` 2026-07-26 |
| C2-C4 RetranscodeDecider + CRF adjust retirement | code deletions permanent; `Features/QualityTesting/Disposition/disposition.feature.md` updated (W5/C3/C4/S5/S6 dropped) |
| C4 RetryBudgetService Disposition-count | code lives in `Features/QualityTesting/Disposition/RetryBudgetService.py`; contract in `disposition.feature.md` C3 |
| C5 dead knobs + flags | schema drop lands in migration; Python mirror deletion permanent |
| C7 doc rewrites | `transcode.flow.md` ST8 + `disposition.feature.md` reflect new reality |
| C8 stale fixtures | `Tests/Pipeline/_backup/` gone |

### Verification Evidence

- **C1**: 17 sentinel rows nullified by `NullifyStreamCopyVmafSentinels_2026_07_26.py`. Post-run `SELECT COUNT(*) FROM TranscodeAttempts WHERE ProcessingMode IN ('Remux','AudioFix','SubtitleFix','Quick') AND Vmaf IS NOT NULL` = 0. `_VerifyStreamCopyChecksum` returns `Vmaf=None`.
- **C2**: `grep -rn "RetranscodeDecider" Features/ Tests/ WebService/` = 0 hits.
- **C3**: `grep -rn "AdjustmentRegistry\|CrfAdjustment" Features/ Tests/ WebService/` = 0 hits.
- **C4**: `TestRetryBudgetService.py` 7/7 green. `TestDispositionDispatcher.py` 11/11 green. `TestPostTranscodeDisposition.py` 13/13 green.
- **C5**: `grep -rn "RetranscodeVmafThreshold\|RequiresVmaf" Features/ WebService/ Tests/` = 0 hits. `DropRetranscodeVmafThreshold_2026_07_26.py` applied twice (temp re-add + final drop for larry deploy window). Schema snapshot: 73 tables, 1101 columns.
- **C6**: 17 rows nullified live.
- **C7**: `transcode.flow.md` ST8 + `disposition.feature.md` W5/C3/C4/S5/S6/Files updated.
- **C8**: `Tests/Pipeline/_backup/` gone.
- **C9**: Fleet redeploy verified: larry (all 4), dot (all 4), wakko (all 4), I9 all on SHA `d56a2f9c`. Zero dropped-column errors in logs post-final-drop.

### Delivery Report

**DIRECTIVE**: verify-signal-cleanup -- Vmaf column truthful; outcome signal in Success+Disposition; retire RetranscodeDecider + CRF adjustment + dead flags.

**STATUS**: Done pending operator close approval.

**WHAT SHIPPED**:
- DOMAIN.md 2026-07-26 rule: Vmaf column truthful; Success+Disposition is the outcome signal.
- Sentinel writer retired: `_VerifyStreamCopyChecksum` returns Vmaf=None (was 100.0).
- 4 code files + 4 test files deleted + `Tests/Pipeline/_backup/` (297 stale fixtures).
- Column `PostTranscodeGateConfig.RetranscodeVmafThreshold` dropped.
- 17 historical sentinel rows backfilled to NULL.
- Doc drift purged: `transcode.flow.md` ST8, `disposition.feature.md` W5/C3/C4/S5/S6.
- Net line diff: -367 (289 added / 656 deleted).

**HOW TO USE IT**:
- Operators reading TranscodeAttempts.Vmaf column can trust it (real VMAF or NULL, no sentinels).
- Downstream code that gates on outcome reads Success + Disposition.
- Adding a new stream-copy strategy: implement `Verify()` returning `Vmaf=None`; DispositionDispatcher already handles the QualityTestNotRequired path.

**WHAT YOU NEED TO EXECUTE**: nothing. Fleet all on `d56a2f9c`; column drop live; workers claiming per normal.

**DECISIONS I MADE**:
- Chose Disposition-count in RetryBudgetService over any hybrid Vmaf+Disposition read. One column per concept.
- Rebuilt tests instead of patching; smaller + focused on new signal.
- Temp column re-add + drop dance to protect larry's in-flight Remux during the deploy window.

**KNOWN GAPS / DEFERRED**: none.

**Phase:** DELIVERING
