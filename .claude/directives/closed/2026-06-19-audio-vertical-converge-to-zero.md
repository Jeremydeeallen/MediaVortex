# Current Directive

**Set:** 2026-06-19
**Status:** Active -- phase: IMPLEMENTING
**Slug:** audio-vertical-converge-to-zero

## Outcome

Move the AUDIO VERTICAL from "mechanism done" to "library converged + every
operator-facing surface tells the truth." Zero gaps that need operator
input -- I own all decisions below per CEO mode + bar-lowering memory.

## Acceptance Criteria

**Z1.** Bulk Resolve action is correct-per-reason. The Review tab's
group action button picks an action that ACTUALLY resolves the
underlying state, not a misleading uniform "clear":
  - `ungainable_all_streams` -> "Resolve all" clears defer reason +
    triggers Recompute (current behavior; keep)
  - `operator_review_pending` -> "Resolve all" clears defer reason +
    triggers Recompute (current behavior; keep)
  - `invalid_loudness_measurement` -> "Re-measure all" calls
    AudioRemeasurementService.MarkForRemeasurement (already triggered
    by H1 but exposed for operator)
  - `LoudnessMeasurements` -> "Re-measure all" same path
  - `awaiting_speech_enrichment` -> "Re-run detection" enqueues
    speech enrichment

**Z2.** Three top-nav landing pages have contract tests:
TestWorkBucketRepository (counts + pagination + idempotent QueueOne).

**Z3.** Drain-rate measurement: capture detected counts at T0 and
T+N minutes; compute drain rate per invariant. If a rate is divergent
(new violations > drains), shorten interval OR raise batch.

**Z4.** "Audio" nav landing page renders a one-liner explaining
structural rarity when Total=0 -- nav stops lying about why it's empty.

**Z5.** `Workers.RemuxEnabled=TRUE` on I9 so the 11,338 Remux-bucket
files can actually flow.

**Z6.** Codebase casing sweep: every audio-vertical jsonify response
returns PascalCase keys at the envelope layer (matches CLAUDE.md
"PascalCase everywhere") OR lowercase consistently. Pick one,
normalize. Update consuming JS in same commit.

**Z7.** Library converges: SuccessfulAttempt + InvalidMeasurement +
ConsistencyBand H1 counts at zero in steady state OR documented
structural reason if non-zero is correct.

## Files

```
.claude/directive.md
Features/AudioNormalization/Services/AudioOperatorReviewService.py     -- Z1 per-reason action
Features/AudioNormalization/AudioNormalizationController.py            -- Z1 action endpoint variants
Templates/AudioNormalization.html                                      -- Z1 per-group button label/action
Templates/WorkBucket.html                                              -- Z4 empty-state note
Tests/Contract/TestWorkBucketRepository.py                             -- Z2
Tests/Contract/TestWorkBucketController.py                             -- Z2
(Z3 measurement: ad-hoc snapshot, no code persist)
(Z5: SQL UPDATE via QueryDatabase, no code change)
(Z6: jsonify normalization across the AN controllers)
```

## Status

### Progress

- [ ] Z1 per-reason bulk action
- [ ] Z2 work-bucket contract tests
- [ ] Z3 drain-rate measurement
- [ ] Z4 nav-empty truth
- [ ] Z5 RemuxEnabled flip
- [ ] Z6 casing sweep
- [ ] Z7 converge to zero (verify)

### Promotions

[Populated at DELIVERING phase]
