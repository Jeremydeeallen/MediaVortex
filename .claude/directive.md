# Directive: videoslotstrategy-persisted

**Status:** Active -- phase: IMPLEMENTING

**Slug:** videoslotstrategy-persisted

**Interrupts:** preencode-loudness-cache-hit (top of `.claude/current-feature` stack; shipped + deployed, delivery report pending).

### Promotions

- (populated at DELIVERING)

## What / Why

`PostTranscodeDispositionDecider.Decide` applies the `InsufficientSavings_<pct>pct_below_<threshold>pct` gate universally on every successful transcode attempt. This is wrong for attempts whose video slot is Copy (Remux, AudioFix, some TestVariant paths). Those attempts NEVER shrink the video stream by design -- their job is container fix, audio fix, or Dialog Boost, not video re-encode. My 20% savings threshold rejects them, `.inprogress` is deleted, MediaFile stays in Remux WorkBucket, queue never drains.

Damage window: since `04377aa5` (2026-08-11 InsufficientSavings gate landed). **468 rejected InsufficientSavings attempts in 48h; 467 still WorkBucket='Remux' with no queue row** (queue rows deleted during reject cleanup, no auto-re-admit). Source files intact on disk; encoder work wasted.

Per `transcode.flow.md` D3: **ProcessingMode is a reporting/priority tag only. Does not decide slot behavior.** Filtering the gate on ProcessingMode would work today by coincidence but breaks when future modes have per-slot combinations. The correct signal is: was the video slot Reencode or Copy for THIS attempt.

Fix: persist `VideoSlotStrategy` ('Copy' | 'Reencode') on `TranscodeAttempts` (symmetric with existing `AudioPolicyResolved` column). Decider reads it; applies `InsufficientSavings` only when strategy = 'Reencode'.

## Domain Decisions (operator, 2026-08-12)

D1. VideoSlotStrategy is the SoT for "was video re-encoded on this attempt." Neither ProcessingMode nor MediaFiles.VideoCompliant at decision-time are valid substitutes (D3 in transcode.flow.md).

D2. Historical rows (attempts written before this directive lands) keep `VideoSlotStrategy = NULL`. Decider treats NULL as "unknown" and DEFAULTS to skipping the gate to avoid breaking historical audit queries. Reason: safer to skip once for an unknown-strategy attempt than to falsely reject.

D3. One-shot recovery script re-queues the 467 Remux MediaFileIds that got InsufficientSavings-rejected. Idempotent: skips MediaFileIds that already have a Pending TranscodeQueue row.

## Scope

1. Migration: `ALTER TABLE TranscodeAttempts ADD COLUMN IF NOT EXISTS VideoSlotStrategy TEXT`. Idempotent per R11.
2. Writer: identify the layer that emits the video slot decision (`CommandComposer` / `VideoSlot._EmitCopy` vs `_EmitReencode`, or `JobProcessor.Process` after Strategy resolved) and persist 'Copy' or 'Reencode' onto the attempt at the same commit that writes `AudioPolicyResolved`. Single writer per code path.
3. Reader: `PostTranscodeDispositionDecider.Decide` reads `VideoSlotStrategy` from Attempt dict; if `'Copy'`: skip InsufficientSavings entirely; if `'Reencode'`: apply gate as today; if `None`/missing: skip (D2 safe default).
4. `DispositionDispatcher._BuildDeciderInput` projects VideoSlotStrategy from the row into the dict.
5. Contract tests:
    - `test_savings_gate_skipped_for_copy`: attempt dict with VideoSlotStrategy='Copy' + 0% savings → Replace/QualityTestingGloballyDisabled (or VMAF path), NOT Reject.
    - `test_savings_gate_fires_for_reencode`: attempt dict with VideoSlotStrategy='Reencode' + 0% savings + threshold=20 → Reject/InsufficientSavings_0pct_below_20pct.
    - `test_null_strategy_skips_gate_safe_default`: VideoSlotStrategy=None + 0% savings → Replace path (no false reject).
6. Recovery script `Scripts/RequeueInsufficientSavingsRejects_2026_08_12.py`: SELECT MediaFileIds from TranscodeAttempts where DispositionReason LIKE 'InsufficientSavings%' in past 72h AND MediaFiles.WorkBucket='Remux' AND no existing Pending TranscodeQueue row for that MediaFileId. INSERT one Pending Remux queue row per matching MediaFile. Idempotent. Prints count admitted + count skipped.
7. Live smoke on I9: after deploy, one Remux job with `VideoSlotStrategy='Copy'` completes → observe Disposition=Replace + FileReplaced=TRUE (not Reject/InsufficientSavings). Confirm log line differentiates skip vs apply.

## Out of Scope

(a) Historical retroactive VideoSlotStrategy backfill for existing TranscodeAttempts rows -- category (a) tolerated: NULL is safe default per D2; no queryable value lost.
(b) Per-mode savings threshold configuration -- category (b) deferred: single global 20% threshold applied when strategy=Reencode is fine for now; if operator later wants different thresholds per mode, add per-mode column to QueueAdmissionConfig.
(c) Removing ProcessingMode column -- category (c) unrelated: ProcessingMode remains a reporting/priority tag per D3.

## Call-Graph Audit

- **Multiple flow docs.** `transcode.flow.md` remains SoT for pipeline shape. `audio-normalization.flow.md` remains SoT for audio pipeline. No new flow doc.
- **Orchestration mode-branching.** No new mode branch. VideoSlotStrategy is a DATA field consumed by the Decider's existing branch; the branch changes from "always apply savings" to "apply savings when strategy=Reencode." Same code path, data-driven condition.
- **Mode-sparse columns.** New column `VideoSlotStrategy` MUST be populated by every writer path that inserts/updates a TranscodeAttempts row post-encode. Symmetric with `AudioPolicyResolved`. Contract test verifies every mode's writer populates it.
- **OOS clarity.** (a)/(b)/(c) each explicitly typed.
- **Config-driven graph shape.** No new flag. Same functions called; data flow changes based on VideoSlotStrategy value.

## Acceptance Criteria

C1. `TranscodeAttempts.VideoSlotStrategy TEXT` column exists (nullable). Migration idempotent (`ADD COLUMN IF NOT EXISTS`).

C2. Every writer that persists a TranscodeAttempts row post-encode populates VideoSlotStrategy with `'Copy'` or `'Reencode'` for that attempt. Verifiable: post-directive live SQL `SELECT COUNT(*) FROM TranscodeAttempts WHERE VideoSlotStrategy IS NULL AND CompletedDate > <directive-close-date>` returns 0.

C3. `PostTranscodeDispositionDecider.Decide` reads `VideoSlotStrategy` from the Attempt dict:
    - `'Copy'` → InsufficientSavings check skipped; flow falls through to QualityTestingGloballyDisabled / QualityTestNotRequired / VMAF branches.
    - `'Reencode'` → InsufficientSavings check applied at `SavingsThresholdPercent` from GateConfig.
    - `None` / missing → skipped (safe default per D2).

C4. Contract test `Tests/Contract/TestVideoSlotStrategyGate.py` (NEW):
    - `test_copy_strategy_skips_savings_gate`
    - `test_reencode_strategy_applies_savings_gate`
    - `test_null_strategy_skips_savings_gate`
    - `test_reencode_strategy_ships_when_savings_above_threshold` (regression guard: gate still catches real overshoot on Reencode)

C5. `DispositionDispatcher._BuildDeciderInput` projects `VideoSlotStrategy` from Row into GateInput dict.

C6. `Scripts/RequeueInsufficientSavingsRejects_2026_08_12.py` runs cleanly against live DB. Prints `Admitted: <N>, Skipped (already queued): <M>`. Idempotent -- second run admits 0 (all already queued).

C7. Live smoke on I9 (mandatory per `ceo-mode.md#smoke-gate-verifying---delivering`):
    - Deploy fix + restart I9.
    - Wait for one Remux completion where VideoSlotStrategy='Copy'.
    - Confirm attempt shows `Disposition=Replace`, `FileReplaced=TRUE`, `DispositionReason != InsufficientSavings_*`.
    - Confirm target MediaFile's WorkBucket flipped to Compliant (or AudioFix if audio-only leak persists).
    - Run recovery script; observe TranscodeQueue Remux Pending count increase by ~467; observe wakko-worker-1 + I9-2024 start draining the recovered backlog.

C8. `Features/QualityTesting/post-transcode-disposition.feature.md` amended at DELIVERING: C10 vocabulary already includes `InsufficientSavings_*` -- add note that gate is scoped to `VideoSlotStrategy='Reencode'`. Add new criterion C42 (or next) documenting the VideoSlotStrategy column + Decider read.

## Principle Analysis

**KISS.** One column + one writer + one reader if-branch. Symmetric with existing `AudioPolicyResolved` pattern -- reuse of established shape, not invention.

**DDD.** VideoSlotStrategy is an encoder-plan concept that belongs on TranscodeAttempts alongside audio-slot decision state. Not tangled in decider or command composer. Cross-context read via existing repository interface.

**DRY.** One SoT for "was video re-encoded on this attempt." Gate + audit queries + future analysis all read same column. No parsing of FfpmpegCommand string, no cross-referencing MediaFiles.VideoCompliant.

**SOLID.**
- SRP: Decider evaluates gates given known slot decisions -- doesn't guess from mode. Writer stamps strategy at the layer that decides it. Each responsibility isolated.
- OCP: adding new ProcessingMode / new slot combinations only requires the writer to populate VideoSlotStrategy correctly. Decider unchanged.
- LSP: n/a.
- ISP: no new interface.
- DIP: Decider depends on Attempt dict shape (existing contract); dispatcher populates. No new dependency direction.

**SSoT.** `TranscodeAttempts.VideoSlotStrategy` IS the SoT for video slot strategy per attempt. Downstream (audit queries, disposition, future analysis) reads it directly. No inference required.

## Files

- `Scripts/SQLScripts/AddVideoSlotStrategy_2026_08_12.py` (NEW, idempotent ALTER TABLE)
- `Features/QualityTesting/Disposition/PostTranscodeDispositionDecider.py` (add VideoSlotStrategy read; scope savings gate)
- `Features/QualityTesting/Disposition/DispositionDispatcher.py` (project VideoSlotStrategy into GateInput dict; SELECT VideoSlotStrategy from attempt row)
- `Features/TranscodeJob/Worker/JobProcessor.py` (persist VideoSlotStrategy at same commit as AudioPolicyResolved OR CommandComposer stamps it)
- Wherever `CommandComposer.Build` returns / `VideoSlot._EmitCopy` vs `_EmitReencode` decides: NEEDS_PLAN identifies the exact writer surface + call site.
- `Tests/Contract/TestVideoSlotStrategyGate.py` (NEW, per C4)
- `Scripts/RequeueInsufficientSavingsRejects_2026_08_12.py` (NEW, per C6)
- `Features/QualityTesting/post-transcode-disposition.feature.md` (amend at DELIVERING)

## Progress

- [ ] NEEDS_STANDARDS_REVIEW: rules + standards index (already loaded).
- [ ] NEEDS_PLAN:
    - Identify exact code path that decides VideoSlot=Copy vs Reencode (grep `_EmitCopy` / `_EmitReencode` / `AudioSlot` writer pattern).
    - Identify exact persistence layer (which UpdateTranscodeAttempt call sets AudioPolicyResolved? Add VideoSlotStrategy alongside).
    - Confirm DispositionDispatcher's SELECT columns for `_ReadAttemptRow` include VideoSlotStrategy after migration (or extend query).
- [ ] NEEDS_DOC_PREREAD: Read `Features/QualityTesting/Disposition/disposition.feature.md` sections covering C2 (pure Decider), audio-normalization sections covering AudioPolicyResolved writer pattern (symmetry reference).
- [ ] IMPLEMENTING: migration + writer + reader + contract test + recovery script.
- [ ] VERIFYING: contract test + live smoke on I9 per C7 + recovery script execution.
- [ ] DELIVERING: Promotions, feature-doc amendment, delivery report.

## Deviation from conventions

No new `videoslotstrategy-persisted.feature.md`. Change amends existing `post-transcode-disposition.feature.md` at DELIVERING (Decider is the primary consumer). Persistence details land in `audio-normalization.feature.md` C42 addendum or similar since it symmetric with AudioPolicyResolved. Doc-layering rule: promotions move durable content into existing feature docs.
