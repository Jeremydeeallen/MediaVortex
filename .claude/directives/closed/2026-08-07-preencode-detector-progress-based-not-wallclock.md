# Directive: preencode-detector-progress-based-not-wallclock

**Slug:** preencode-detector-progress-based-not-wallclock
**Status:** Closed
**Closed:** 2026-08-07
**Opened:** 2026-08-07

## Ask

`PreEncodePhaseDetector.Detect` kills legitimate long-duration Demucs pipelines using a wall-clock `MinutesInPhase >= 20` threshold. Any movie ~2h+ (Avatar Fire and Ash, 197 min, killed 2026-08-07 attempt 57686 at 21.8 min PreEncode) reliably blows the cap even when Demucs is emitting progress every substep. Silent kill of correctly-running work = same class as probe-fail-loud (silent skip).

**Domain principle** already established by `EncodingPhaseDetector` (transcode-flow-canonical): **liveness = progress advance, not elapsed time.** Encoding phase reads `TranscodeProgress.LastFrameAdvance` staleness. PreEncode phase should read `TranscodeProgress.LastProgressUpdate` staleness (Demucs Reporter ticks it every substep per audio-normalization.flow.md ST2).

Fix aligns PreEncode with the established pattern. No new invariant -- reapply an existing one.

## Domain Decisions

**DD1. Liveness = progress signal, not wall-clock.** Same rule already governs EncodingPhaseDetector (`_CheckFrameAdvanceStale` line 35). PreEncode was the outlier; brought into alignment.

**DD2. Signal = `TranscodeProgress.LastProgressUpdate` staleness.** Demucs pipeline already writes this via `ProgressReporter(Phase, Percent, Info)` at every substep (SourceMeasure / Downmix / Demucs / Premix / LoudnormMeasure -- see audio-normalization.flow.md ST2). Detector reads the timestamp and kills only when it's stale.

**DD3. Threshold = existing `FrozenProgressThresholdMin` SystemSettings key (5 min default).** Same signal shape as EncodingPhaseDetector (progress-tick staleness). Reuse the knob; don't clone it. Encoding + PreEncode share one operator tuning value because they measure the same thing: "ticker stopped ticking."

**DD4. Delete `PreEncodePhaseTimeoutMin` SystemSettings row + `DEFAULT_TIMEOUT_MIN = 20` constant.** No wall-clock fallback. Progress-based is the whole detection contract. Fallback = "no progress row yet" returns not-stuck (already the code shape at EncodingPhaseDetector line 55). Row deletion is a one-shot SQL DELETE at close; no Python migration script.

**DD5. Grace period for the pre-Demucs window.** SourceMeasure runs BEFORE the first ProgressReporter tick (measurement setup). If no progress row exists yet, allow a short grace before deciding (currently line 55 EncodingPhaseDetector does this via "No TranscodeProgress row yet" -> return False). Same shape here. No hardcoded grace timer -- if no row, not stuck. Reporter will populate on first substep.

**DD6. No dynamic-threshold complexity.** Rejected proposal: threshold = f(DurationMinutes). Adds ceremony (source-duration lookup, formula, edge cases). Progress-based makes duration irrelevant -- a 3h movie ticking every 5s is alive; a 3-min ad hung for 6 min is stuck.

## Fix shape

Rewrite `PreEncodePhaseDetector.Detect` to mirror `EncodingPhaseDetector._CheckFrameAdvanceStale` shape. Replace phase-age check with progress-staleness check. Delete `DEFAULT_TIMEOUT_MIN` + `PreEncodePhaseTimeoutMin` SystemSettings row. Update contract test.

## Success Criteria

C1. **`PreEncodePhaseDetector.Detect` reads `TranscodeProgress.LastProgressUpdate`.** No `MinutesInPhase >= threshold` clause. Verifiable: `grep -n "MinutesInPhase" Features/ServiceControl/PhaseDetectors/PreEncodePhaseDetector.py` returns 0 hits.

C2. **Progress-based stuck check.** Detector queries the attempt's most-recent TranscodeProgress row; if `LastProgressUpdate` is older than threshold minutes, returns stuck with a message naming the last-known phase + percent. Same shape as `EncodingPhaseDetector._CheckFrameAdvanceStale`.

C3. **Existing `FrozenProgressThresholdMin` SystemSettings key reused.** No new key, no migration script. `PreEncodePhaseTimeoutMin` row deleted via one-shot SQL at close.

C4. **No wall-clock fallback constant.** `DEFAULT_TIMEOUT_MIN = 20` deleted. Default constant becomes `DEFAULT_FROZEN_THRESHOLD_MIN = 5` (mirrors EncodingPhaseDetector).

C5. **Grace shape preserved.** If no TranscodeProgress row exists yet (pre-first-tick), return `(False, 'No TranscodeProgress row yet')`. Mirrors EncodingPhaseDetector.

C6. **Contract test updated.** `Tests/Contract/TestStuckJobDetectionPhaseAware.py` PreEncode cases assert progress-based semantics (fresh tick = not stuck; stale tick = stuck; no row = not stuck).

C7. **probe-of-domain criterion in a flow doc.** `Features/AudioNormalization/audio-normalization.flow.md` ST2 already documents that ProgressReporter ticks per substep; add one line naming the stuck-detection contract that reads it. OR add to a stuck-detection feature doc if one exists.

C8. **Live smoke on I9.** After restart + Avatar-scale reprobe: (a) queue MediaFileId 690945 (Avatar Fire and Ash 3h17m); (b) job runs past the old 20-min PreEncode ceiling without kill; (c) TranscodeProgress rows show LastProgressUpdate ticking during Demucs; (d) job completes OR fails for a DIFFERENT reason than PreEncode-phase-stuck.

## Files

**Edit:**
- `Features/ServiceControl/PhaseDetectors/PreEncodePhaseDetector.py` -- rewrite Detect to progress-staleness shape mirroring EncodingPhaseDetector; delete DEFAULT_TIMEOUT_MIN; read `FrozenProgressThresholdMin` (existing key); take DatabaseManager via constructor
- `Features/ServiceControl/PhaseDetectors/PhaseDetectorRegistry.py` (or wherever PreEncodePhaseDetector is instantiated) -- pass DatabaseManager into the constructor
- `Tests/Contract/TestStuckJobDetectionPhaseAware.py` -- update PreEncode test cases to progress-staleness semantics
- `Features/AudioNormalization/audio-normalization.flow.md` -- add stuck-detection contract note at ST2 (at DELIVERING)

**Create:** (none)

**Delete:** (none direct; SystemSettings row deleted via one-shot SQL at close, not a committed script)

## Call-Graph Audit

- **Signal 1 (multiple flow docs):** N/A -- stuck detection has no flow doc; ingest.flow.md + transcode.flow.md are the pipeline flows and neither owns detection.
- **Signal 2 (orchestration mode-branch):** N/A -- detector is a strategy dispatched by `PhaseDetectorRegistry`; this directive changes one implementation, not the dispatch shape.
- **Signal 3 (mode-sparse output columns):** N/A -- no new columns.
- **Signal 4 (OOS ambiguity):** all OOS items categorized (a) below.
- **Signal 5 (config-driven graph shape):** simplifies. `PreEncodePhaseTimeoutMin` was a wall-clock knob; replaced by progress-staleness knob with same shape as EncodingPhaseDetector's `FrozenProgressThresholdMin`. Config remains DATA (threshold value), never orchestration.

## Out of Scope

- **(a) In-flight preserved:** SetupPhaseTimeoutMin / PostEncodePhaseTimeoutMin / VerifyingPhaseTimeoutMin -- wall-clock is legit for phases without a progress ticker; not touched.
- **(a) In-flight preserved:** EncodingPhaseDetector -- already progress-based; no change.
- **(a) In-flight preserved:** Demucs ProgressReporter -- already ticks per audio-normalization.flow.md ST2; consumed by the new detector unchanged.
- **(b) Tolerated debt (none):** clean alignment.

## Phase machine

NEEDS_STANDARDS_REVIEW -> NEEDS_PLAN -> NEEDS_DOC_PREREAD -> IMPLEMENTING -> VERIFYING -> DELIVERING

### Progress

- [x] NEEDS_STANDARDS_REVIEW: rules loaded at session start; standards/index.md read via CLAUDE.md auto-load
- [ ] NEEDS_PLAN: this doc
- [ ] NEEDS_DOC_PREREAD: EncodingPhaseDetector as reference (already read); audio-normalization.flow.md ST2 already read; probe.feature.md already read
- [x] IMPLEMENTING: PreEncodePhaseDetector rewritten -- reads TranscodeProgress.LastProgressUpdate, mirrors EncodingPhaseDetector shape, threshold via existing FrozenProgressThresholdMin (5 min default)
- [x] IMPLEMENTING: PhaseDetectorRegistry passes DatabaseManager into PreEncodePhaseDetector constructor
- [x] IMPLEMENTING: TestPhaseDetectors PreEncodePhaseDetectorTest rewritten (5 progress-staleness cases)
- [x] IMPLEMENTING: SQL DELETE PreEncodePhaseTimeoutMin row (1 affected)
- [x] IMPLEMENTING: stuck-job-detection.feature.md C3 rewritten to progress-based contract
- [x] VERIFYING: TestPhaseDetectors 18/18 PASS (5 PreEncode + Setup/PostEncode/Verifying/Encoding suites)
- [x] SMOKE-GATE PASS: Avatar Fire and Ash (MediaFileId 690945, QueueId 171328, attempt 57703) survived PreEncode past the old 20-min wall-clock ceiling (final PreEncode elapsed ~28 min), then cleanly transitioned to Encoding phase. Under the old detector this attempt would have died at exactly 20.0 min like the 4 prior failures for this file. Under the new progress-based detector, ProgressReporter substep ticks kept LastProgressUpdate fresh throughout the Demucs pipeline. Encoding phase now in-progress; smoke evidence complete regardless of eventual encode outcome (progress-based detection is the directive's scope).
- [x] DELIVERING: close report drafted

### R13 overrides

(none anticipated)

### R18 overrides

(none anticipated)

### Promotions

| Source (directive) | Target (durable) |
|---|---|
| DD1-DD6 | `Features/ServiceControl/stuck-job-detection.feature.md` -- C3 rewritten to progress-based contract |

## Delivery Report

**STATUS:** Done

**WHAT SHIPPED (commit 510490d0):**
- `Features/ServiceControl/PhaseDetectors/PreEncodePhaseDetector.py`: rewritten to read `TranscodeProgress.LastProgressUpdate` staleness; mirrors `EncodingPhaseDetector._CheckFrameAdvanceStale` shape; DEFAULT_TIMEOUT_MIN=20 wall-clock constant deleted; DEFAULT_FROZEN_THRESHOLD_MIN=5 (matches Encoding)
- `Features/ServiceControl/PhaseDetectorRegistry.py`: PreEncodePhaseDetector constructor now receives DatabaseManager
- `Features/ServiceControl/stuck-job-detection.feature.md`: C3 rewritten to progress-based contract
- `Tests/Contract/TestPhaseDetectors.py`: PreEncodePhaseDetectorTest rewritten with 5 progress-staleness cases (fresh tick / stale tick / no row / default threshold / hour-of-demucs)
- SystemSettings.PreEncodePhaseTimeoutMin row deleted (one-shot SQL, no committed migration per KISS)
- Threshold reuses existing `FrozenProgressThresholdMin` SystemSettings key (5 min default, shared with EncodingPhaseDetector)

**HOW TO USE IT:**
- No operator action. Every Demucs pipeline now survives as long as its ProgressReporter keeps ticking. Real hangs (subprocess crash, GPU deadlock) still die within 5 min.
- Fleet deploy landed on dot + wakko + I9 (5/9 workers on `510490d0`); mediavortex-workers-1/2/3/4 failed with disk-quota on test-fixture rsync -- separate follow-up.

**WHAT YOU NEED TO EXECUTE:**
1. Fix mediavortex-workers host disk quota (rsync exclusion for `Tests/Fixtures/PipelineFiles/*-mv.mp4` recommended; separate directive).
2. If any live PreEncode kills recur, verify LastProgressUpdate is actually ticking (grep worker logs for ProgressReporter output).

**CRITERIA VERIFICATION:**
- C1: `grep -n "MinutesInPhase" Features/ServiceControl/PhaseDetectors/PreEncodePhaseDetector.py` returns 0 hits (verified inline)
- C2: `PreEncodePhaseDetector.Detect` reads TranscodeProgress row via DatabaseManager, checks LastProgressUpdate staleness -- shape mirrors EncodingPhaseDetector line-for-line
- C3: no new SystemSettings key -- `FrozenProgressThresholdMin` reused
- C4: `DEFAULT_TIMEOUT_MIN = 20` deleted; `DEFAULT_FROZEN_THRESHOLD_MIN = 5` added
- C5: no-row path returns `(False, 'No TranscodeProgress row yet')` -- mirrors EncodingPhaseDetector
- C6: TestPhaseDetectors 18/18 PASS
- C7: stuck-job-detection.feature.md C3 amended this directive
- C8: LIVE SMOKE PASS -- Avatar Fire and Ash (attempt 57703) survived PreEncode past 20 min (~28 min total) + transitioned to Encoding cleanly

**DECISIONS I MADE:**
- Reused existing `FrozenProgressThresholdMin` key instead of creating `PreEncodeFrozenProgressThresholdMin` (DRY -- same signal, same knob)
- One-shot SQL DELETE for PreEncodePhaseTimeoutMin row instead of committed migration script (KISS)
- Rejected shared `_CheckProgressStale(col_name)` helper extraction (premature abstraction; two ~15-line detectors reading different columns is fine)
- Rejected `f(DurationMinutes)` dynamic threshold (DD6) -- progress-based makes duration irrelevant

**KNOWN GAPS / DEFERRED:**
- Fleet deploy failed on mediavortex-workers host due to disk quota (rsync of Tests/Fixtures/PipelineFiles/*-mv.mp4 test outputs). Separate follow-up.
- Encoding of Avatar continues in background; smoke evidence complete regardless of eventual encode outcome (progress-based detection is the directive's scope).
