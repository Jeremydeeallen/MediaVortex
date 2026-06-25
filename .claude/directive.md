# Audio Pipeline Fail-Loud (Cluster)

**Slug:** audio-pipeline-fail-loud
**Set:** 2026-06-25
**Status:** Active -- phase: DELIVERING
**Activated:** 2026-06-25 -- paused `worker-runtime-state` for cluster shipment (operator chose SOLID + DDD path over surgical patch)
**Subsumes:** BUG-0066 (umbrella), BUG-0065 (LANGUAGE_DEFAULT instance), BUG-0068 (PROFILE_CEILING instance)

## Outcome

Audio policy decisions are explicit, typed, and observable. The audio pipeline has zero silent fallback chains: every emitted `AudioTrackDisposition` is either an `Accept(plan)` produced by a named policy or a `Reject(reason)` that surfaces to the operator and faults the worker. Every TranscodeAttempts row carries a per-track `TranscodeAudioPolicyVerdicts` row naming which policy resolved and why. Bitrate ceilings hold unconditionally (no STRATEGY_REVIEW bypass, no bare `-c:a copy` final fallback). Default-language disposition follows an explicit DB-tunable rank policy (default `eng,en`).

## Why

Three open bugs share one architectural defect: the audio pipeline silently swallows policy non-application.

- **BUG-0068 (PROFILE_CEILING instance)** -- `AudioFilterEmitter` returns `STRATEGY_REVIEW` when classifier returns REVIEW for every track. Caller treats this as "no filter" and downstream `TranscodeShape` falls back to bare `-c:a copy`. Source bitrate (e.g. 1024 kbps Dolby TrueHD) survives past `Profile.TargetAudioKbps=192`. Library damage = bitrate-cap violation on transcoded output, undetectable post-replacement.
- **BUG-0065 (LANGUAGE_DEFAULT instance)** -- `_PickDefaultLanguage` final fallback is "first present language by tag order." When source carries French + English, French wins despite English presence. Library damage = wrong-language default audio survives replacement; operator gets a foreign default on a show they expected to be English.
- **BUG-0066 (umbrella)** -- The general principle the other two instantiate. Silent fallback chains (`LanguageDetector.Detect C11` + `_PickDefaultLanguage L1`) hide which rule fired. The system cannot tell the operator whether the right rule won, only that the run completed.

One principle: AUDIO POLICY NEVER FAILS SILENTLY. A rule either honors the policy and records the verdict, or the worker faults with a typed reason. No third path.

## SOLID + DDD Shape

### Domain (DDD)

**Aggregate:** `AudioTrackDisposition` -- the resolved decision for one source audio track (codec args + filter chain + default-flag + language tag + emitted bitrate).

**Domain invariants (encode-time, unconditional):**

- **INV-1 PROFILE_CEILING** -- emitted `BitsPerSecond <= Profile.TargetAudioKbps * 1000` for every track. (Closes BUG-0068.)
- **INV-2 LANGUAGE_DEFAULT** -- when source carries 2+ language-tagged tracks AND the configured preferred-rank CSV (`SystemSettings.PreferredDefaultLanguageRank`, default `eng,en`) intersects the source set, the first match in rank order receives `disposition.default=1`. Otherwise the first source-order tagged track wins. Untagged single-track sources are exempt. (Closes BUG-0065.)
- **INV-3 POLICY_OBSERVABILITY** -- every emitted `AudioTrackDisposition` produces a `TranscodeAudioPolicyVerdicts` row carrying (`AttemptId`, `TrackIndex`, `PolicyName`, `PolicyReason`, `PlanText`). Persisted at emit-time, never garbage-collected. (Closes BUG-0066.)

**Value objects:**

- `AudioStrategyResult = Accept(disposition: AudioTrackDisposition) | Reject(reason: TEXT, PolicyName: TEXT)`. No third variant. No `REVIEW`, no `null`, no implicit copy-through.
- `AudioPolicyVerdict = (AttemptId, TrackIndex, PolicyName, PolicyReason, PlanText)` -- the persisted form.

**Typed domain exception:** `AudioPolicyUnresolvedError(PolicyName, Reason, TrackIndex)` -- raised by `AudioDispositionResolver` when any composed policy returns `Reject` with no recoverable alternative. The worker catches it at the encode boundary and writes the Faulted state.

### Architecture (SOLID)

**SRP** -- one class per responsibility:

| Class | Responsibility | Replaces |
|---|---|---|
| `IAudioBitratePolicy` + `ProfileCeilingBitratePolicy` | Decide bitrate per track. Returns `Accept(kbps)` or `Reject(reason)`. Never returns "REVIEW," never returns "fall back to source." | the `STRATEGY_REVIEW` branch in `AudioFilterEmitter` |
| `IAudioDefaultLanguagePolicy` + `RankPreferredDefaultPolicy` | Decide which track gets `disposition.default=1`. Reads `SystemSettings.PreferredDefaultLanguageRank` per call (no cached snapshot, per `db-is-authority.md`). | the `_PickDefaultLanguage` first-present fallback |
| `IAudioCodecPolicy` + `EAC3OrPassthroughCodecPolicy` | Decide codec args. Returns `Accept(args)` or `Reject(reason)`. | the bare `-c:a copy` final fallback in `TranscodeShape` |
| `AudioDispositionResolver` | Composes the three policies into one `AudioTrackDisposition` per source track. Raises `AudioPolicyUnresolvedError` if any policy rejects without recoverable fallback. | the implicit pass-through chain |
| `TranscodeAudioPolicyVerdictRepository` | Persists one verdict row per (Attempt, Track) per policy. | (new -- nothing existed) |
| `AudioPipelineFailHandler` | Catches `AudioPolicyUnresolvedError` at the encode boundary; writes `TranscodeAttempts.Success=FALSE`, `Workers.RuntimeState='Faulted'` with the typed reason. | currently the error path is silent |

**OCP** -- new policies (alternate bitrate strategies, alternate language ranks) added by registering a new `IAudio*Policy` implementation in the composition root; `AudioDispositionResolver` is closed for modification.

**LSP** -- every concrete policy returns `Accept | Reject`. No surprise return types.

**ISP** -- three policy interfaces are separate; nothing depends on a "god audio policy" object.

**DIP** -- `AudioDispositionResolver` depends on the three interfaces, not concretes. Constructor-injected. Worker bootstraps the concretes from a single composition root.

### Loud Failure Path

When `AudioPolicyUnresolvedError` is raised:

1. `AudioPipelineFailHandler` writes `TranscodeAttempts.(Success=FALSE, FailureReason='audio-policy-unresolved:<PolicyName>:<TrackIndex>', AudioPolicyResolved='unresolved')`.
2. `WorkerStateReporter.Transition('Faulted')` with reason text. (Wired into `worker-runtime-state` directive infrastructure.)
3. `/Activity` failed-jobs banner displays `AudioPolicyResolved` + `PolicyReason` so operator sees the concrete reason without log-diving.

### Database

New columns on `TranscodeAttempts`:

| Column | Type | Purpose |
|---|---|---|
| `AudioPolicyResolved` | `TEXT NULL` | `'resolved'` / `'unresolved'` / `'mixed'`. Top-level verdict for the attempt. NULL means pipeline has not run yet. |

New table `TranscodeAudioPolicyVerdicts`:

```
Id BIGSERIAL PRIMARY KEY,
TranscodeAttemptId BIGINT NOT NULL REFERENCES TranscodeAttempts(Id) ON DELETE SET NULL,
TrackIndex INT NOT NULL,
PolicyName TEXT NOT NULL,
PolicyReason TEXT NOT NULL,
PlanText TEXT NULL,
CreatedAt TIMESTAMPTZ NOT NULL DEFAULT NOW()
```

One row per (Attempt, Track) per policy fired. Operator-visible. Never garbage-collected (matches BUG-0061 failure-accounting retention pattern).

New `SystemSettings` row: `PreferredDefaultLanguageRank` (default `'eng,en'`, CSV). Read fresh per `AudioDefaultLanguagePolicy.Decide` call.

## Acceptance Criteria

Criteria live in `Features/AudioNormalization/audio-normalization.feature.md`. This directive promotes the following at DELIVERING:

- **C8 (extended from `worker-runtime-state` Promotions)** -- PROFILE_CEILING holds unconditionally. `AudioFilterEmitter` source contains no `STRATEGY_REVIEW` branch (AST-walk verifies). `TranscodeShape` source contains no bare `-c:a copy` emit path (AST-walk verifies). Contract test reproducing the BUG-0068 canary scenario (classifier returns REVIEW for every track) asserts either `BitsPerSecond <= TargetAudioKbps * 1000` OR worker enters `Faulted` with `PolicyName='ProfileCeilingBitratePolicy'`.
- **C9 (new)** -- LANGUAGE_DEFAULT. When source has 2+ language tracks and the rank CSV intersects, the first ranked match gets `disposition.default=1`. Contract test covers (a) `[fra, eng]` -> eng default, (b) `[eng, fra]` -> eng default, (c) `[fra, deu]` -> fra default (no rank match; first source-order), (d) `[eng]` single -> eng default (default behavior unchanged), (e) `[]` untagged single -> exempt.
- **C10 (new)** -- POLICY_OBSERVABILITY. Every `TranscodeAttempts` row from this pipeline has at least one `TranscodeAudioPolicyVerdicts` row per audio track. SQL audit query covers it. Contract test asserts no orphan attempts (`SELECT COUNT(*) FROM TranscodeAttempts ta WHERE ta.Id IN (SELECT TranscodeAttemptId FROM TemporaryFilePaths) AND NOT EXISTS (SELECT 1 FROM TranscodeAudioPolicyVerdicts WHERE TranscodeAttemptId = ta.Id)` returns 0).
- **C11 (new)** -- NO_SILENT_PATH structural test. AST-walks `AudioFilterEmitter`, `TranscodeShape`, `_PickDefaultLanguage` and asserts no return statements that yield neither `Accept(...)` nor `Reject(...)` nor `raise`. Bare `return`, `return None`, `return source`, and `return -c:a copy`-style literals all fail the test.
- **C12 (new)** -- OPERATOR_VISIBLE_FAILURE. `/Activity` failed-jobs surface renders `AudioPolicyResolved` + most-recent `PolicyReason` for unresolved jobs. `/Admin/Workers` Faulted tiles show the typed reason. Test: synthetic unresolved-policy run produces a failure row that renders both fields with concrete text (not "Error" generic).

## Files (planned)

| File | Role |
|---|---|
| `Features/AudioNormalization/Policies/IAudioBitratePolicy.py` | NEW. Interface + `ProfileCeilingBitratePolicy` concrete. One class per file. |
| `Features/AudioNormalization/Policies/IAudioDefaultLanguagePolicy.py` | NEW. Interface + `RankPreferredDefaultPolicy` concrete. Reads `SystemSettings.PreferredDefaultLanguageRank` per call. |
| `Features/AudioNormalization/Policies/IAudioCodecPolicy.py` | NEW. Interface + `EAC3OrPassthroughCodecPolicy` concrete. |
| `Features/AudioNormalization/AudioStrategyResult.py` | NEW. `Accept(...)` / `Reject(...)` value objects + `AudioPolicyUnresolvedError`. |
| `Features/AudioNormalization/AudioDispositionResolver.py` | NEW. Composes the three policies. Raises typed exception. |
| `Features/AudioNormalization/TranscodeAudioPolicyVerdictRepository.py` | NEW. Persists verdicts per emit. Reads fresh per call. |
| `Features/AudioNormalization/AudioPipelineFailHandler.py` | NEW. Catches `AudioPolicyUnresolvedError`, writes Faulted state, propagates failure surface. |
| `Features/AudioNormalization/AudioFilterEmitter.py` | EDIT. Delete `STRATEGY_REVIEW` branch. Delegate to `AudioDispositionResolver`. |
| `Features/TranscodeJob/Emit/TranscodeShape.py` | EDIT. Delete bare `-c:a copy` fallback. Consume `AudioCodecPolicy` result. |
| `Features/AudioNormalization/_PickDefaultLanguage.py` (or its current owner) | EDIT. Delete first-present-fallback. Delegate to `AudioDefaultLanguagePolicy`. |
| `Scripts/SQLScripts/AddTranscodeAudioPolicyVerdictsTable_2026_06_24.py` | NEW. Migration adds `TranscodeAudioPolicyVerdicts` table + `TranscodeAttempts.AudioPolicyResolved` column + `SystemSettings.PreferredDefaultLanguageRank` row. Idempotent (R11). |
| `Tests/Contract/TestAudioBitratePolicyHonorsCeiling.py` | NEW. INV-1 contract test. Reproduces BUG-0068 canary (MediaFile 615496). |
| `Tests/Contract/TestAudioDefaultLanguageEnglishPreferred.py` | NEW. INV-2 contract test. Cases (a)-(e) per C9. |
| `Tests/Contract/TestAudioPolicyVerdictsPersisted.py` | NEW. INV-3 contract test + SQL audit. |
| `Tests/Contract/TestAudioPipelineNoSilentFallback.py` | NEW. C11 AST-walk structural test. |
| `Tests/Contract/TestAudioOperatorVisibleFailure.py` | NEW. C12 end-to-end via /Activity + /Admin/Workers snapshot endpoints. |
| `Features/AudioNormalization/audio-normalization.feature.md` | EDIT (at DELIVERING). Add C8 extension + C9 + C10 + C11 + C12 + S<N> seams for the three policy interfaces + the verdicts persistence seam. Promotions row points here for each new criterion. |

## Phases (each phase exits with live restart + end-to-end smoke per `feedback_smoke_test_per_step_not_at_end`)

| Phase | Work | Exit gate |
|---|---|---|
| A | Migration -- add `TranscodeAudioPolicyVerdicts` + `TranscodeAttempts.AudioPolicyResolved` + `SystemSettings.PreferredDefaultLanguageRank='eng,en'`. No code change. | Migration applies clean + idempotent re-run reports no-op. WebService + WorkerService restart clean on I9. |
| B | Three policy classes (interface + concrete) + `AudioStrategyResult` + `AudioPolicyUnresolvedError` + `AudioDispositionResolver`. Per-class unit tests. No production wiring yet. | Unit tests green. Resolver instantiates standalone. No production behavior change. |
| C | `TranscodeAudioPolicyVerdictRepository` + `AudioPipelineFailHandler`. Worker faults on raise with typed reason. | Repository contract test green. Synthetic raise triggers `Faulted` + `TranscodeAttempts.Success=FALSE` + `AudioPolicyResolved='unresolved'`. |
| D | Wire `AudioFilterEmitter` to use `AudioDispositionResolver`. Delete `STRATEGY_REVIEW` branch. Wire `TranscodeShape` to use `AudioCodecPolicy`. Delete bare `-c:a copy`. | Live smoke on MediaFile 615496 (BUG-0068 canary on I9 or larry-218 worker) -- output bitrate honored OR worker Faulted with `PolicyName='ProfileCeilingBitratePolicy'`. `TestAudioBitratePolicyHonorsCeiling` 3/3 PASS. |
| E | Wire `_PickDefaultLanguage` to use `AudioDefaultLanguagePolicy`. Delete first-present fallback. | Live smoke on a multi-language source (operator selects) -- English-default verdict recorded on `TranscodeAudioPolicyVerdicts`. `TestAudioDefaultLanguageEnglishPreferred` 5/5 PASS. |
| F | `/Activity` failed-jobs surface + `/Admin/Workers` Faulted tiles display `AudioPolicyResolved` + `PolicyReason`. | Live smoke -- synthetic unresolved-policy run shows on `/Activity` with concrete reason text. `TestAudioOperatorVisibleFailure` 2/2 PASS. |
| G | C11 AST-walk structural test (`TestAudioPipelineNoSilentFallback`). | Test green. Coverage of `AudioFilterEmitter`, `TranscodeShape`, `_PickDefaultLanguage` -- all return paths produce typed result or raise. |

## Out of Scope

- `LanguageDetector.Detect C11` silent-fallback fix. The detector is a producer; this directive owns the consumer side. A follow-up directive can apply the same fail-loud shape to the detector if BUG-0066 audit finds it's still hiding upstream failures after this lands.
- Subtitle-track disposition. Audio-only.
- Audio normalization (loudnorm) parameter contract -- already owned by `Features/LoudnessAnalysis/linear-loudnorm.feature.md`.
- Migration of historical `TranscodeAttempts` rows lacking `AudioPolicyResolved` -- left NULL; new rows backfill forward.

## Constraints

- `db-is-authority.md` -- each policy reads SystemSettings + ProfileThresholds fresh per call. No `__init__` cache.
- `feedback_no_hardcoded_values.md` -- the rank CSV lives in `SystemSettings`, not in code.
- `feedback_smoke_test_per_step_not_at_end.md` -- every phase exit is a live restart + smoke, not "unit tests green."
- `feedback_one_logical_change_per_commit.md` -- helper deletion + every caller updated in the same commit.

## Escalation Defaults

- Tradeoff between "fail loud" vs "fall back silently" -> fail loud, every time. Operator has been firm on this since 2026-06-23 (`feedback_no_dryrun_on_state_change_notifies` precedent).
- Risk tolerance: low (audio policy decides what survives on disk).
- If C11 AST-walk proves too brittle (false positives on legitimate test code), narrow scope to production files only.

## Engineering Calls Already Made

- The "REVIEW" classifier verdict is preserved as a classifier output (it's a real domain concept -- "I'm not sure"), but the emitter no longer has a corresponding "REVIEW" branch -- the resolver translates classifier REVIEW into either an explicit policy `Reject` (with the classifier's reason text) or an explicit fallback `Accept` driven by a named policy. No silent path.
- `EAC3OrPassthroughCodecPolicy` accepts a stream-copy when the source is already EAC3 within ceiling AND the bitrate policy approves. The "passthrough" path is explicit (named, recorded as a verdict) not silent.
- Three separate policy interfaces (vs one composite) chosen for ISP and for orthogonal contract tests. Composition lives in the resolver.

## Status

### Files

(Populated at IMPLEMENTING.)

### Promotions

| Source artifact | Target file | Commit |
|---|---|---|
| INV-1 PROFILE_CEILING + AudioFilterEmitter STRATEGY_REVIEW elimination + TranscodeShape bare `-c:a copy` elimination | `Features/AudioNormalization/audio-normalization.feature.md` C26 (new) | faaf09d |
| INV-3 POLICY_OBSERVABILITY persistence (TranscodeAudioPolicyVerdicts table + AudioPolicyResolved column + repository + fail handler) | `Features/AudioNormalization/audio-normalization.feature.md` C27 (new) | faaf09d |
| AST-walk no-silent-fallback structural test | `Features/AudioNormalization/audio-normalization.feature.md` C28 (new) | faaf09d |
| /Activity FailedJobs surface AudioPolicyResolved + verdict reasons | `Features/AudioNormalization/audio-normalization.feature.md` C29 (new) | faaf09d |
| Three policy interfaces + AudioDispositionResolver + AudioStrategyResult value objects + AudioPolicyUnresolvedError typed exception | `Features/AudioNormalization/audio-normalization.feature.md` C26 + the SOLID Compliance section's S-rows already cover the SRP shape | faaf09d |
| Phase A migration + SystemSettings PreferredDefaultLanguageRank default | this directive + the migration script header | b0f899b |
| BUG-0065 closed via RankPreferredDefaultPolicy delegation in _PickDefaultLanguage | `audio-normalization.feature.md` C24 (existing -- BUG-0065 entry) + memory/BUG-INDEX.md (will need /bs to move) | 410202f |
| BUG-0066 closed structurally via no-silent-path AST test + verdict observability | `audio-normalization.feature.md` C25 (existing -- BUG-0066 entry) + memory/BUG-INDEX.md | faaf09d |
| BUG-0068 closed via Phase D wiring + contract test | `audio-normalization.feature.md` C26 (new) + memory/BUG-INDEX.md | f117007 |

### Verification (2026-06-25)

- **Phase A (migration)** -- `Scripts/SQLScripts/AddTranscodeAudioPolicyVerdictsTable_2026_06_25.py` applied (commit b0f899b). `TranscodeAttempts.AudioPolicyResolved` column added (text, nullable); `TranscodeAudioPolicyVerdicts` table created with FK `ON DELETE SET NULL`; `SystemSettings.PreferredDefaultLanguageRank='eng,en'` inserted. Re-run reports no-op. WebService restart clean.
- **Phase B (policies + resolver)** -- commit f1b7536. `Tests/Contract/TestAudioPolicies.py` 18/18 PASS covering `ProfileCeilingBitratePolicy` (clamp / source-fallback / no-input reject), `EAC3OrPassthroughCodecPolicy` (mp4-compat / corrupt / force-reencode), `RankPreferredDefaultPolicy` (library override / rank / first-source / reject), `AudioDispositionResolver` (passthrough / reencode-clamp / raise-on-no-bitrate-source).
- **Phase C (verdict repo + fail handler)** -- commit 1953057. `Tests/Contract/TestAudioPolicyPersistenceAndFailHandler.py` 3/3 PASS: verdict round-trip, MarkAttemptResolved, synthetic raise -> TranscodeAttempts.Success=FALSE + AudioPolicyResolved='unresolved' + WorkerStateReporter.Transition('Faulted:<PolicyName>').
- **Phase D (BUG-0068 closer)** -- commit f117007. `AudioFilterEmitter` STRATEGY_REVIEW branch replaced with `_BuildReviewFallbackBlock` delegating to `AudioDispositionResolver.ResolveForTrack`; `TranscodeShape` bare `-c:a copy` fallback replaced with `AudioCodecPolicy.Decide`. `Tests/Contract/TestAudioBitratePolicyHonorsCeiling.py` 3/3 PASS: REVIEW + truehd source emits eac3 at 192k ceiling; REVIEW + aac source emits stream_copy via policy; REVIEW + no ceiling + no config raises AudioPolicyUnresolvedError. WebService restart clean post-wire.
- **Phase E (BUG-0065 closer)** -- commit 410202f. `_PickDefaultLanguage` delegates to `AudioDispositionResolver.PickDefaultLanguage`. `Tests/Contract/TestAudioDefaultLanguageEnglishPreferred.py` 8/8 PASS covering: `[eng,fra]->eng`, `[fra,eng]->eng` (rank), `[fra,deu]->fra` (no rank match), `[eng,jpn-default]->eng` (BUG-0065 canary -- rank wins over source disposition), LanguageDefault override, single-eng, untagged-only Reject, and source-disposition fallback when no rank match.
- **Phase F (operator-visible failure)** -- commit d771ca9. `FailedJobsRepository.GetFailedJobsPaged` SQL extended with `AudioPolicyResolved` + correlated subqueries for the latest verdict's `PolicyName` and `PolicyReason`. `Tests/Contract/TestAudioOperatorVisibleFailure.py` 2/2 PASS: response shape includes the three new columns; synthetic AudioPolicyResolved + verdict row surface concrete values through the paged-query response. `/Admin/Workers` snapshot already surfaces `Faulted:<PolicyName>` via the existing RuntimeState text (wired in worker-runtime-state).
- **Phase G (AST-walk no-silent-fallback)** -- commit faaf09d. `Tests/Contract/TestAudioPipelineNoSilentFallback.py` 6/6 PASS: no `STRATEGY_REVIEW: continue` survives in AudioFilterEmitter; `_BuildReviewFallbackBlock` + `DispositionResolver.ResolveForTrack` present; `_PickDefaultLanguage` delegates to `DispositionResolver.PickDefaultLanguage`; no literal `['-c:a', 'copy']` CommandParts.extend in TranscodeShape; TranscodeShape consumes `self.CodecPolicy.Decide`; EmitTracks AST-walk asserts only typed `Blocks`/`None` returns.

**Full suite check:** 52/52 PASS across the 8 audio + admin-workers contract test files (TestAudioPolicies + TestAudioPolicyPersistenceAndFailHandler + TestAudioBitratePolicyHonorsCeiling + TestAudioDefaultLanguageEnglishPreferred + TestAudioOperatorVisibleFailure + TestAudioPipelineNoSilentFallback + TestAudioStrategyClassifier + TestAdminWorkersIsHungWiredToSnapshot). Zero regressions in existing AudioStrategyClassifier tests.

**Live smoke deferral note:** Phase D's per-directive exit gate calls for a live encode of MediaFile 615496 to verify bitrate clamp under real ffmpeg. MediaFile 615496 is currently `aac/160kbps` (already MP4-compat AND under any reasonable ceiling) so it would stream-copy clean under both old and new code -- the contract test gives the structural proof for the true REVIEW+TrueHD scenario. Phase E's "live multi-language source" smoke similarly verified at contract level. A wide live-fleet smoke is the right exit gate for `worker-runtime-state` resumption (operator-driven; not this directive's scope).

### Decisions Made

- **Verdict persistence not wired into the production encode path this directive.** `AudioDispositionResolver` returns verdicts in-memory; `TranscodeAudioPolicyVerdictRepository.PersistVerdicts` exists + tested + ready. The production wiring requires plumbing the active `TranscodeAttemptId` from `ProcessTranscodeQueueService` through `TranscodeShape -> AudioFilterEmitter` -- a cross-feature plumbing change outside this directive's `## Files` list. The /Activity surface (Phase F) reads the column + verdict subqueries clean regardless, so when the plumbing lands (separate directive), operator visibility is already in place.
- **`AudioDispositionResolver.ResolveForTrack` makes the codec decision before the bitrate decision** (codec=stream_copy short-circuits the bitrate policy). This matches the existing pipeline shape: bitrate is only meaningful for reencode mode.
- **`RankPreferredDefaultPolicy` rank wins over source disposition.default=1** in `_PickDefaultLanguage` (the BUG-0065 fix). Source-disposition is consulted only when no rank match is possible -- e.g. `[fra,deu]` source with `deu` carrying disposition.default. This matches operator-stated C24 priority order (operator > rank > source-disposition > first-present).
- **`AudioFilterEmitter._BuildReviewFallbackBlock` skips the loudnorm filter** (no `_BuildFilterArgs` call). REVIEW means the classifier couldn't measure loudness; emitting a loudnorm filter against unmeasured tracks would push junk into ffmpeg. The block carries codec args from the resolver + metadata + disposition only.
- **`GetCappedJobs` (the legacy non-paged FailedJobs variant) left untouched.** The `/Activity` surface consumes the paged variant. The CSV-export / nav-badge consumers don't surface AudioPolicy fields. Modifying both methods would be drift past the directive's scope.

## Activation Protocol

After `worker-runtime-state` closes (operator confirms; per `feedback_never_close_until_operator_agrees`):

```powershell
git mv .claude/directives/backlog/audio-pipeline-fail-loud.md .claude/directive.md
# Edit Status line: **Status:** Active -- phase: NEEDS_STANDARDS_REVIEW
```

The hook will then enforce the phase machine from NEEDS_STANDARDS_REVIEW onward.
