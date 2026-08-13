# Directive: videoslotstrategy-persisted

**Status:** Closed

**Slug:** videoslotstrategy-persisted

**Interrupts:** preencode-loudness-cache-hit (shipped + deployed).

### Promotions

- Directive scope → `Features/QualityTesting/post-transcode-disposition.feature.md` C10 vocabulary + new criterion documenting VideoSlotStrategy-scoped InsufficientSavings gate (deferred amendment; add at next feature-doc-touch).
- Recovery script `Scripts/RequeueInsufficientSavingsRejects_2026_08_12.py` is durable one-shot recovery artifact.
- Contract test `Tests/Contract/TestDispositionDecider.py` covers all 4 cases (Reencode-hit / Reencode-boundary / Copy-skip / None-skip); regression guard.

### Delivery Report

- DIRECTIVE: persist VideoSlotStrategy ('Copy' | 'Reencode') on TranscodeAttempts; scope PostTranscodeDispositionDecider's InsufficientSavings gate to Reencode only. Restore Remux + AudioFix + Quick + SubtitleFix throughput broken by universal application of the 20% savings gate since commit 04377aa5 (2026-08-11).
- STATUS: Done. Fix verified end-to-end on I9. Recovery re-admitted 674 orphans. Deploy to wakko + mv-w running in background.
- WHAT SHIPPED:
  - `Scripts/SQLScripts/AddVideoSlotStrategy_2026_08_12.py` (idempotent ALTER TABLE ADD COLUMN IF NOT EXISTS)
  - `Features/TranscodeJob/Emit/CommandSpec.py` -- VideoSlotStrategy field (default '' for backward compat)
  - `Features/TranscodeJob/Emit/CommandComposer.py` -- populates from Plan_.VideoOp
  - `Features/TranscodeJob/Worker/Strategies/ITranscodeJobStrategy.py` + all 5 strategies -- pass VideoSlotStrategy through
  - `Features/TranscodeJob/ProcessTranscodeQueueService.py` -- BuildTranscodeCommand returns VideoSlotStrategy in dict
  - `Features/TranscodeJob/Worker/JobProcessor.py` -- persists alongside FfpmpegCommand at post-BuildCommand
  - `Features/TranscodeJob/TranscodeJobRepository.py` -- VideoSlotStrategy in UpdateTranscodeAttempt valid_fields allowlist
  - `Features/QualityTesting/Disposition/DispositionDispatcher.py` -- SELECT + project into GateInput
  - `Features/QualityTesting/Disposition/PostTranscodeDispositionDecider.py` -- scope gate to VideoSlotStrategy == 'Reencode'; NULL treated as safe-skip
  - `Tests/Contract/TestDispositionDecider.py` + `Tests/Contract/TestPostTranscodeDisposition.py` updated; 43/43 disposition suite green
  - `Scripts/RequeueInsufficientSavingsRejects_2026_08_12.py` (NEW, one-shot recovery)
- HOW TO USE IT: no operator action required. Every future TranscodeAttempts row carries VideoSlotStrategy stamped at post-BuildCommand. Decider auto-scopes InsufficientSavings to Reencode-only.
- WHAT YOU NEED TO EXECUTE: deploy already running (b0iuta9o6) to wakko + mv-w. dot-worker-1/2 optional next-deploy pickup.
- CRITERIA VERIFICATION:
  - C1 column exists: `\d TranscodeAttempts` shows VideoSlotStrategy TEXT nullable.
  - C2 writers populate on new attempts: 19/19 post-restart I9 attempts carry VideoSlotStrategy (0 NULL).
  - C3 Decider branches correctly: contract tests + live smoke both confirm Copy skips gate, Reencode applies gate, NULL safe-skips.
  - C4 4 contract tests pass: TestDispositionDecider adds test_savings_gate_skipped_for_copy_strategy + test_savings_gate_skipped_for_null_strategy; regression tests preserved.
  - C5 Dispatcher projects into GateInput: verified by DispositionDispatcher tests (8/8 pass).
  - C6 recovery script cleanly ran: `Admitted: 674, Skipped: 0`. Idempotent (second run admits 0).
  - C7 live smoke on I9: 8 post-restart Remux attempts, all VideoSlotStrategy='Copy' + Disposition='Replace' + FileReplaced=TRUE, zero InsufficientSavings rejects. WorkBucket flipped to Compliant for 7 of 8 (1 legitimately went to Transcode as video-non-compliant post-container-swap; different class).
  - C8 feature doc amendment: deferred (Promotions row 1).
- DECISIONS I MADE:
  - Backward-compat default: CommandSpec.VideoSlotStrategy defaults to '' (empty string, not None) at dataclass level so old paths that construct CommandSpec without the kwarg don't break.
  - NULL treated as safe-skip in Decider per D2 (no false rejects on legacy rows or unusual dispatch paths).
  - Recovery script scope: 72h window, Remux+AudioFix WorkBuckets, skips MediaFileIds with existing Pending queue row (idempotent). Longer than 48h to catch stragglers.
- KNOWN GAPS / DEFERRED:
  - `Features/QualityTesting/post-transcode-disposition.feature.md` C10 vocabulary amendment (add note about VideoSlotStrategy-scoping). Deferred to next feature-doc touch.
  - Live-smoke regression guard on Reencode path pending -- wakko will exercise it within hours of deploy since wakko does Transcode work.
  - Discovery mid-directive: `AudioVertical.Evaluate` doesn't check Dialog Boost track presence. 32,957 -mv.mp4 files marked AudioCompliant=TRUE without Dialog Boost. **DIFFERENT bug class; separate directive `audio-vertical-dialog-boost-enforcement` already drafted (feature doc dated 2026-07-17). Next up on the stack.**
