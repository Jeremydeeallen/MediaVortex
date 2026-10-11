# Current Directive

**Set:** 2026-10-11
**Status:** Closed 2026-10-11
**Slug:** remove-savings-gate
**Replaces:** `directives/closed/2026-10-10-long-filename-output.md` (closed Success)

## Outcome

A finished video re-encode is no longer thrown away for saving too little space. Files that sit just over the bitrate ceiling (Greatest American Hero S01E01-E08, Loki S02E03) stop looping: their encode is kept, the file becomes compliant, and it is not queued for Transcode again. The "minimum savings percent" setting disappears from `/settings`. Backlog row 22. Operator 2026-10-11: "remove the save 20% rule altogether. Simplify."

## Acceptance Criteria

1. A successful re-encode is never rejected because of how much smaller (or larger) the output is than the source. Verify: decider contract tests at 13%, 0% and -20% savings return a non-savings disposition.
2. A file whose last re-encode was rejected for insufficient savings completes Transcode on its next run and is not queued for Transcode again. Verify: live run of MediaFiles 698773.
3. `/settings` no longer shows or saves a minimum-savings-percent field, and the admission-config API neither returns nor accepts it. Verify: GET against the running WebService; page load.
4. No production code names the savings threshold or the insufficient-savings reason. Verify: `grep -rnE "InsufficientSavings|SavingsThresholdPercent" --include=*.py --include=*.html Features Core Services Repositories WorkerService WebService Templates` returns 0.

## Call-Graph Audit

- **Flow docs:** `transcode.flow.md` (ST7 disposition). One flow; no pair describes one operation.
- **Orchestration mode branches:** the removed gate was itself a mode branch inside the decider (`VideoSlotStrategy == 'Reencode'`); removing it deletes the branch. None added.
- **Signal 5:** no flag. The threshold was data; removing it removes one decision, not a graph node toggled by config.
- **Shared output columns:** `TranscodeAttempts.DispositionReason` keeps historical `InsufficientSavings_*` values; no new writer. No mode-sparse column introduced.
- **OOS categories:** below.

## Out of Scope

- (b) Column `QueueAdmissionConfig.PreEncodeSavingsThresholdPercent` stays in the table, unread. Dropping a column is irreversible and is the operator's call.
- (b) Historical `TranscodeAttempts` rows keep their `InsufficientSavings_*` reason: they are history.
- (b) `Scripts/RequeueInsufficientSavingsRejects_2026_08_12.py` and `Scripts/SQLScripts/AddPreEncodeSavingsThreshold_2026_08_10.py` are dated one-shots; left as they are.
- (b) The queue-admission `MinTranscodeSavingsMB` gate is a different rule (pre-queue, absolute MB); untouched.

## Constraints

- Deploy through `py deploy/deploy-fleet.py` (drain in code).

## Escalation Defaults

- Risk tolerance: medium.

## Engineering Calls Already Made

- Operator 2026-10-11: remove the rule altogether, no replacement rule.

## Status

### Files

```
Features/QualityTesting/Disposition/PostTranscodeDispositionDecider.py
Features/QualityTesting/Disposition/DispositionDispatcher.py
Features/TranscodeQueue/QueueAdmissionConfigRepository.py
Features/TranscodeQueue/Models/QueueAdmissionConfigModel.py
Features/SystemSettings/SystemSettingsController.py
Templates/Settings.html
Tests/Contract/TestDispositionDecider.py
Tests/Contract/TestPostTranscodeDisposition.py
Features/QualityTesting/post-transcode-disposition.feature.md
transcode.flow.md (ST7 inputs, decision table, outcomes)
```

### Plan

One commit: delete the savings branch from the decider, the threshold plumbing from the dispatcher, the field from the admission-config model / repository / API / settings page, and the tests that assert the rejection (replaced by tests asserting no rejection). Deploy fleet. Re-queue 698773.

Seams changed:

| Seam | Producer | Wire shape | Consumer expects | Verification |
|---|---|---|---|---|
| Dispatcher -> decider | `DispositionDispatcher._BuildGateInput` | dict without `SavingsThresholdPercent` | `PostTranscodeDispositionDecider.Decide` no longer reads it | contract tests |
| Settings page -> API -> DB | `Templates/Settings.html` save | JSON without `PreEncodeSavingsThresholdPercent` | `SystemSettingsController` PUT / `QueueAdmissionConfigRepository.Update` no longer accept it | live GET/PUT round-trip of the remaining fields |

Deleted code, by bucket: the savings branch is a rule the operator retired (not a workaround, not a default) -- delete.

### Promotions

| Source artifact | Target file |
|---|---|
| Output size is not a disposition input; savings reasons leave the closed vocabulary | `transcode.flow.md` ST7 (inputs, decision table, Reject reasons), `Features/QualityTesting/post-transcode-disposition.feature.md` criteria 10-11 (same commit as the code) |

### Verification

- **Commit:** `2c47bf86`, pushed. Fleet on `2c47bf86`, 9 workers OK (`deploy-fleet.py`, 467.8s, drained).
- **Tests:** decider, disposition table, dispatcher suites 40/40. `TestFailLoud` baseline tests fail identically with and without this change (baseline file is stale); not touched. Claim tests not run (they take live queue rows).
- **1:** decider tests at 13%, 0% and -20% savings return `Replace/VmafPassed`.
- **2, live 2026-10-11 (UTC):**
  - 698773 Greatest American Hero S01E01-E08: attempt 99821 Transcode on wakko-worker-1, 15.0% smaller, `Replace`, placed. VideoCompliant, bucket moved Transcode -> AudioFix; hand-off queued Audio (attempt 99824 running). Prior attempt 99810 was rejected `InsufficientSavings_13pct_below_20pct`.
  - 751141 Loki S02E03: attempt 99822 Transcode on dot-worker-1, 11.7% smaller, `Replace`, placed. VideoCompliant, bucket AudioFix; Audio attempt 99823 running.
- **3:** running WebService: GET `/api/SystemSettings/QueueAdmissionConfig` returns no savings-percent field; PUT of the two remaining fields round-trips; `/settings` loads (200) with no savings-percent input.
- **4:** production grep returns 0.

### Decisions Made

- No replacement rule: an output larger than its source is also kept, as "remove altogether" reads.
- The dead setting was removed from the page and API in the same commit rather than left as a knob that does nothing.
- Both files were queued with the API's force flag: manual add without it was refused as `Upscale` against a 2160p default profile target, which is unrelated to this rule.
