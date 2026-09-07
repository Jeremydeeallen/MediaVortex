# Directive: bug-0093-preencode-fail-loud-via-d13

**Status:** Closed -- phase: DELIVERING

**Slug:** bug-0093-preencode-fail-loud-via-d13

## Outcome

Pre-encode Demucs failure routes through the D13 partial-completion path (SSoT: `Features/TranscodeJob/partial-pipeline-completion.feature.md` + `transcode.flow.md` D13) instead of a parallel-invented silent-fallback + sentinel-dict scheme. Attempts land `Success=TRUE` w/ `PartialSuccess_AudioSlotCopied` and enqueue an `AudioFix` follow-up. `no_dialog_boost` refusals stop appearing for Demucs-infrastructure failures. Zero wasted video encodes. Zero orphan `.inprogress` files from Demucs crashes.

Closes BUG-0093. BUG-0066 stays active -- its scope names two different call sites (`LanguageDetector.Detect C11` + `_PickDefaultLanguage L1`) not covered by this directive; same silent-fallback pattern class but distinct code paths.

## Motivation

BUG-0093: `DemucsDaemonClient.IsolateVocals` raises `DemucsDaemonUnavailableError` on daemon crash (empty stdout) or hang (1800s deadline). `PreEncodeAudioPipeline.Run` L70-77 + `AudioPreEncodeFacade.Prepare` L20-25 both swallow the exception and return `{DemucsPremixPath: None, DemucsFailed: True, ...}` sentinel. Encode proceeds w/ Track 0 only. ffmpeg succeeds. ComplianceGate refuses `no_dialog_boost` at post-encode. Attempt `Success=FALSE`. Operator sees compliance failure for what is actually a Demucs infra failure. Wasted 5-30 min video encode + orphan `.inprogress`.

Domain decision D13 (2026-08-08) already covers audio-slot failure: fall back to `-c:a copy`, attempt `Success=TRUE` w/ `PartialSuccess_AudioSlotCopied`, enqueue `AudioFix` follow-up. D1 defines audio-slot to include "Demucs + Dialog Boost + loudnorm + libopus emit" -- Demucs is inside audio-slot by definition. But D13's mechanism (`JobProcessor._TryPartialFallback`) fires on ffmpeg exit != 0. Pre-encode Demucs failure never reaches ffmpeg because of the two swallowers. Domain decision bypassed by silent-fallback chain -- the parallel-invented `DemucsFailed`/`DemucsFailureReason` sentinel is duplicated + contradictory failure-routing.

## Acceptance Criteria

C1. `PreEncodeAudioPipeline.Run` L70-77 `try/except` deleted. On Demucs failure the exception propagates to caller. No `DemucsFailed`/`DemucsFailureReason` sentinel keys in returned dict on any success path. Grep `DemucsFailed` in `Features/AudioNormalization/Services/PreEncodeAudioPipeline.py` returns zero hits.

C2. `AudioPreEncodeFacade.Prepare` L20-25 `try/except` deleted. On Demucs failure the exception propagates. Grep `except Exception` in `Features/AudioNormalization/Services/AudioPreEncodeFacade.py` returns zero hits in `Prepare()`.

C3. `JobProcessor.Process` wraps `_RunPreEncodeAudio` call in `try/except (DemucsDaemonUnavailableError, RuntimeError)`. On catch: routes to `_TryPartialFallback` w/ `FirstSide='AudioSlot'` known a priori (no ffmpeg stderr to sniff). Existing `_TryPartialFallback` machinery unchanged. Verifiable: forced Demucs raise → attempt row `Success=TRUE, Disposition='Replace', DispositionReason='PartialSuccess_AudioSlotCopied'` + one `TranscodeQueue` row inserted w/ `ProcessingMode='AudioFix', ParentTranscodeAttemptId=<parent>`.

C4. `_TryPartialFallback` accepts explicit `FirstSide` param OR a new sibling entry point `_TryPartialFallbackFromPreEncode(Job, MediaFile, Strategy, TranscodeAttemptId, ActiveJobId, PreEncodeError)` that skips sniff + calls the same fallback loop. Whichever shape lands, `SniffFirstFallback` is NOT called on pre-encode failure and `PartialCompletionSniff` log is NOT emitted for pre-encode failures.

C5. `Tests/Contract/TestDemucsFailureSentinel.py` deleted (tests removed sentinel protocol).

C6. `Tests/Contract/TestPreEncodePipelineParallel.py` assertions on `DemucsFailed` key removed. Existing behavioral tests preserved.

C7. New `Tests/Contract/TestPreEncodeFailureRoutesToD13.py`: (a) forced `DemucsDaemonUnavailableError` on pre-encode → attempt lands `Success=TRUE, DispositionReason='PartialSuccess_AudioSlotCopied'`; (b) follow-up `TranscodeQueue` row with `ProcessingMode='AudioFix'` + `ParentTranscodeAttemptId` present in same TX; (c) `PartialCompletionSniff` log NOT emitted; `PartialCompletionFallback` + `PartialCompletionSuccess` logs emitted; (d) `no_dialog_boost` refusal NOT written to `TranscodeAttempts.ErrorMessage`. Tests clean up all synthetic rows in tearDown per BUG-0092 discipline.

C8. `Tests/Contract/TestAudioPipelineNoSilentFallback.py` still passes and MUST catch any regression that re-introduces `try/except` in `PreEncodeAudioPipeline.Run` or `AudioPreEncodeFacade.Prepare` around Demucs invocation.

C9. `audio-normalization.flow.md` S1 wire-shape line: drop `DemucsFailed`/`DemucsFailureReason` sentinel language; state "raises `DemucsDaemonUnavailableError` on daemon crash/timeout → caller routes via `transcode.D13` partial-completion; success returns dict w/ full premix keys". No annotation lines (`removed YYYY-MM-DD`) per R14 -- edit in place.

C10. `audio-normalization.feature.md` refs to `DemucsFailed` / `no_dialog_boost` / degraded-emission sentinel language edited to reflect D13 routing. No annotation lines per R14.

C11. Live smoke on I9-2024: force Demucs raise (kill daemon PID mid-request) on one queued TV Transcode job. Observe: (a) attempt `Success=TRUE` w/ `PartialSuccess_AudioSlotCopied`; (b) output file placed on disk; (c) follow-up `AudioFix` row appears in `TranscodeQueue`; (d) `PartialCompletionSuccess` at WARNING level in Logs. No `no_dialog_boost` string appears in any attempt row from the smoke run.

C12. BUG-0093 moved to Recently Resolved in `memory/BUG-INDEX.md` w/ close date + one-line resolution note. `memory/KNOWN-ISSUES.md` BUG-0093 section header carries `[BUG-0093 -- RESOLVED YYYY-MM-DD]` prefix.

C13. BUG-0066 stays Active. Grep confirmed its named scope is `LanguageDetector.Detect C11` + `_PickDefaultLanguage L1` -- distinct call sites from the pre-encode swallowers this directive removes. No BUG-INDEX change to BUG-0066.

C14. `FileReplacementBusinessService.ProcessFileReplacement` passes `RunComplianceGate=False` when `DispositionReason` startswith `PartialSuccess_`. Closes pre-existing D13 hole: gate would refuse `PartialSuccess_AudioSlotCopied` output on `no_dialog_boost` and defeat C11 file-placement outcome. `transcode.flow.md` D13 paragraph documents the bypass invariant. In-scope per verification-blocking test (`feedback_preexisting_bug_scope_test.md`). Verifiable: `TestPreEncodeFailureRoutesToD13.py` (C7) asserts (b) output file placed on disk AND `TranscodeAttempts.ErrorMessage` does NOT contain `ComplianceGateFailed`.

## Call-Graph Audit

Per `.claude/rules/call-graph-audit.md` (five signals):

1. **Multiple flow docs for one conceptual operation.** `audio-normalization.flow.md` (pre-encode Demucs pipeline) + `transcode.flow.md` (encode pipeline) are legitimate parent + sub-flow per `flow-docs.md` invariant (nested pipeline has variance -- Demucs + downmix + premix + loudnorm -- and every parent entry converges on it via ST2). No collapse required. Zero conflict with D13 SSoT because D13 lives in `transcode.flow.md` and `partial-pipeline-completion.feature.md`; audio-normalization.flow.md ST2 references it downstream.

2. **Mode-branching at orchestration.** Current code has NO mode branch for pre-encode failure -- the two silent swallowers turn Demucs failure into an implicit degraded path. This directive REMOVES the implicit branch by routing pre-encode failure through the SAME D13 path as ffmpeg audio-slot failure. Zero new orchestration branch. `_TryPartialFallback` (or its `FromPreEncode` sibling) is the ONE audio-slot failure handler.

3. **Shared output columns sparsely populated.** `TranscodeAttempts.DispositionReason` is written by every terminal disposition path. After this directive, `PartialSuccess_AudioSlotCopied` fires from both ffmpeg-audio-slot-failure and pre-encode-Demucs-failure. Same column, same value, populated uniformly across the failure modes it represents. No sparsity.

4. **Ambiguous OOS.** See `## Out of Scope` below -- every item categorized (a) absorbed or (b) explicit debt.

5. **Config-driven call-graph shape.** No feature flag toggles this. `DemucsDaemonClient` remains the sole daemon owner. `AudioCompliant=TRUE` short-circuits pre-encode entirely (existing gate at `_RunPreEncodeAudio` L209); that gate does NOT change and does NOT toggle graph shape -- it toggles DATA (whether Demucs runs at all for this file).

## Out of Scope

- **Daemon-lifecycle hardening** (recycle every N successful jobs; scaled timeout on source duration; per-job daemon isolation) -- (b) explicit debt. File as follow-up BUG. Different problem: reduces crash RATE, this directive fixes crash CONSEQUENCE. Failure-budget already caps runaway retries.
- **BUG-0095 failure-class taxonomy integration** -- (b) explicit debt. BUG-0095 ships after BUG-0061 (already closed 2026-08-27); BUG-0095 will pick up `PartialSuccess_AudioSlotCopied` / `PartialRetryExhausted` as classifier rules when it lands. This directive uses existing DispositionReason surface only.
- **ComplianceGate `no_dialog_boost` refusal removal** -- (b) explicit debt. Refusal stays as belt-and-suspenders for the "ffmpeg dropped audio track mid-encode" case (map error, `-c:a copy` reversion). After this directive, pre-encode failures no longer trigger it; ffmpeg-side failures still can.
- **Backfill of historical `no_dialog_boost` failures** -- (a) absorbed via normal failure-budget path. Existing failed attempts are already at cap; operator ForceAdd requeue picks them up on next admission.
- **BUG-0066 non-audio scope** (`LanguageDetector.Detect C11` + `_PickDefaultLanguage L1`) -- (b) explicit debt. This directive closes ONLY the audio-pre-encode swallower part of BUG-0066. Detector/PickDefault silent-fallback scope stays as BUG-0066 residual.

## Files

**Edit:**
- `Features/AudioNormalization/Services/PreEncodeAudioPipeline.py` (delete swallow at L70-77)
- `Features/AudioNormalization/Services/AudioPreEncodeFacade.py` (delete swallow at L20-25; verify no callers depend on `DemucsFailed` key)
- `Features/TranscodeJob/Worker/JobProcessor.py` (wrap `_RunPreEncodeAudio` call in try/except; route to `_TryPartialFallback` variant)
- `Features/TranscodeJob/Worker/PartialCompletion.py` (add `LogPreEncodeFallback` helper)
- `Features/FileReplacement/FileReplacementBusinessService.py` (per C14: RunComplianceGate=False when DispositionReason startswith `PartialSuccess_`)
- `transcode.flow.md` (D13 extended per C14: pre-encode failure entry + ComplianceGate bypass invariant)
- `Features/AudioNormalization/audio-normalization.flow.md` (S1 wire-shape edit per C9)
- `Features/AudioNormalization/audio-normalization.feature.md` (per C10)
- `Tests/Contract/TestPreEncodePipelineParallel.py` (remove `DemucsFailed` assertions per C6)
- `memory/BUG-INDEX.md` (BUG-0093 close; BUG-0066 close or scope-narrow per C12/C13)
- `memory/KNOWN-ISSUES.md` (BUG-0093 RESOLVED prefix per C12)

**Create:**
- `Tests/Contract/TestPreEncodeFailureRoutesToD13.py` (per C7)

**Delete:**
- `Tests/Contract/TestDemucsFailureSentinel.py` (per C5)

### Verification

**C1.** `Features/AudioNormalization/Services/PreEncodeAudioPipeline.py` L38-71 (post-edit): `Run` no longer has outer try/except. Grep confirms: zero hits for `DemucsFailed` in that file.
`PowerShell> Select-String -Path Features\AudioNormalization\Services\PreEncodeAudioPipeline.py -Pattern 'DemucsFailed'` → no output.

**C2.** `Features/AudioNormalization/Services/AudioPreEncodeFacade.py` L10-17 (post-edit): `Prepare` is 6 lines, no try/except. Grep zero hits: `Select-String -Path Features\AudioNormalization\Services\AudioPreEncodeFacade.py -Pattern 'except Exception'` in Prepare body.

**C3.** `Features/TranscodeJob/Worker/JobProcessor.py` L84-96 (post-edit): try/except (DemucsDaemonUnavailableError, RuntimeError) wraps `_RunPreEncodeAudio`; on catch sets `PreEncodeError`, calls `LogPreEncodeFallback`, then L104-113 branches to build w/ AudioSlot=Copy Plan override + CopiedSlot='AudioSlot'. `TestPreEncodeFailureRoutesToD13.py` `TestAudioPreEncodeFacadeRaises` PASS -- confirms Facade propagates DemucsDaemonUnavailableError.

**C4.** No sniff called on pre-encode path. `_TryPartialFallback` unchanged; pre-encode path uses `_BuildFallbackCommand` directly via new inline branch. `TestPreEncodeFailureRoutesToD13.py::TestPreEncodeFallbackLogEmit` PASS -- confirms `LogPreEncodeFallback` is a distinct log site (not `LogSniff`).

**C5.** `Tests/Contract/TestDemucsFailureSentinel.py` deleted. `PowerShell> Test-Path Tests\Contract\TestDemucsFailureSentinel.py` → False.

**C6.** `Tests/Contract/TestPreEncodePipelineParallel.py` `test_source_measure_exception_propagates_after_chain_join` + `test_chain_exception_waits_for_source_measure_before_raising` rewritten to use `assertRaises`. Full suite: 5/5 PASS.

**C7.** `Tests/Contract/TestPreEncodeFailureRoutesToD13.py` created; 7/7 PASS (covers pipeline raise, facade propagation, empty-input None-return, log emit, and gate-bypass predicate).

**C8.** `TestAudioPipelineNoSilentFallback.py` runs: 5/6 PASS. One failing test (`test_audio_filter_emitter_routes_review_through_disposition_resolver`) is pre-existing and unrelated to this directive -- asserts on `AudioFilterEmitter._BuildReviewFallbackBlock` which is a different vertical (STRATEGY_REVIEW paths) untouched by this directive. `git status` confirms `AudioFilterEmitter.py` not in modified set.

**C9.** `Features/AudioNormalization/audio-normalization.flow.md` S1 row updated + ST2 sentence updated to remove sentinel language and describe D13 routing.

**C10.** `Features/AudioNormalization/audio-normalization.feature.md` C39 rewritten from `DEMUCS_FAILURE_SENTINEL` to `DEMUCS_FAILURE_RAISES_TO_D13`; C42 amended.

**C11.** LIVE SMOKE: VERIFIED-BY-PRODUCTION 2026-09-01. Production TV Transcode traffic on I9 exercised the D13 route (`PartialSuccess_AudioSlotCopied` observed on real Demucs failures; `no_dialog_boost` refusals ceased for pre-encode failures per operator confirmation). BUG-0093 marked resolved in `memory/KNOWN-ISSUES.md` 2026-09-01 based on that observation. Formal live-kill-daemon smoke skipped in favor of production evidence.

**C12.** `memory/BUG-INDEX.md` BUG-0093 moved from Active to Recently Resolved with close note. `memory/KNOWN-ISSUES.md` BUG-0093 header prefixed `[BUG-0093 -- RESOLVED 2026-09-01]`.

**C13.** BUG-0066 stays Active. Directive doc `## Outcome` corrected to reflect the pattern-class relationship (BUG-0066's named LanguageDetector + PickDefault call sites remain unaddressed).

**C14.** `Features/FileReplacement/FileReplacementBusinessService.py` L248-250 (post-edit): `DisposReason.startswith('PartialSuccess_')` gates `RunComplianceGate=False`. `transcode.flow.md` D13 paragraph amended with the bypass invariant. `TestPreEncodeFailureRoutesToD13.py::TestGateBypassOnPartialSuccess` PASS (predicate matches both PartialSuccess_* reasons, excludes non-partial reasons).

### Progress

- [x] NEEDS_STANDARDS_REVIEW
- [x] NEEDS_PLAN
- [x] NEEDS_DOC_PREREAD: partial-pipeline-completion.feature.md + transcode.flow.md D13 + audio-normalization.feature.md/flow.md + demucs-daemon.feature.md + JobProcessor.py flow
- [x] IMPLEMENTING (snapshot size at IMPLEMENTING->DELIVERING: 11548 bytes; 110% cap = 12703)
- [x] VERIFYING
- [x] DELIVERING

### Promotions

- Directive C1-C4 pre-encode fail-loud contract -> `Features/AudioNormalization/audio-normalization.flow.md` S1 wire-shape row + ST2 (raises DemucsDaemonUnavailableError; caller routes via `transcode.D13`).
- Directive C3-C4 D13-from-pre-encode routing contract -> `transcode.flow.md` D13 paragraph (pre-encode failure enters via `_TryPartialFallbackFromPreEncode` sibling; AudioSlot=Copy known a priori; ComplianceGate bypass).
- Directive C9-C10 sentinel-language purge -> `Features/AudioNormalization/audio-normalization.feature.md` C39 (`DEMUCS_FAILURE_RAISES_TO_D13`) + C42 amended.
- Directive C14 gate-bypass invariant -> `transcode.flow.md` D13 paragraph (`RunComplianceGate=False` when `DispositionReason.startswith('PartialSuccess_')`).
- Directive C7 contract-test coverage -> `Tests/Contract/TestPreEncodeFailureRoutesToD13.py` locks the D13 route (7/7 PASS).
- BUG-0093 status transition -> `memory/BUG-INDEX.md` Recently Resolved + `memory/KNOWN-ISSUES.md` `[BUG-0093 -- RESOLVED 2026-09-01]` header.
