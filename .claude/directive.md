# Audio Pipeline Fail-Loud (Cluster)

**Slug:** audio-pipeline-fail-loud
**Set:** 2026-06-25
**Status:** Active -- phase: NEEDS_STANDARDS_REVIEW
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

(Empty -- populated at IMPLEMENTING -> DELIVERING. Each new criterion C9/C10/C11/C12 + C8 extension promotes to `Features/AudioNormalization/audio-normalization.feature.md`. Three policy interfaces + verdicts persistence seam promote to the same feature doc's `## Seams` section.)

### Verification

(Populated at VERIFYING -- one entry per C8/C9/C10/C11/C12 with concrete evidence.)

### Decisions Made

(Populated during execution.)

## Activation Protocol

After `worker-runtime-state` closes (operator confirms; per `feedback_never_close_until_operator_agrees`):

```powershell
git mv .claude/directives/backlog/audio-pipeline-fail-loud.md .claude/directive.md
# Edit Status line: **Status:** Active -- phase: NEEDS_STANDARDS_REVIEW
```

The hook will then enforce the phase machine from NEEDS_STANDARDS_REVIEW onward.
