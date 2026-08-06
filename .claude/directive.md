# Probe Loudness Remove

**Slug:** probe-loudness-remove
**Status:** Active -- phase: IMPLEMENTING
**Opened:** 2026-08-06
**Interrupts:** concurrency-cap-live-reload

## Ask

Probe-time loudness measurement is expensive (~30s/file, 26,940-file backlog = ~217 hours of ffmpeg work) AND immediately superseded by transcode-time measurement in `AudioPreEncodeFacade.py:80`. Delete probe-time loudness. Probe stays metadata-only per SRP + writer-owns-cascade.

Under `audio-vertical-dialog-boost-enforcement` policy (every file transcodes), priority-by-loudness is moot; UI populates lazily.

## Fix shape

Delete `Features/MediaProbe/MediaProbeBusinessService.py:135-151` (EbuR128 try-block). Delete `_MaybeAutoMarkAudioCompleteAtTarget` method + call site (dead after C1 -- only fires when loudness succeeds).

## Success Criteria

C1. **Probe path no longer calls `EbuR128MeasurementService`.** `grep -rn "EbuR128MeasurementService\|MeasureAndPersist" Features/MediaProbe/` returns 0. Verifiable: `Tests/Contract/TestProbeNoLoudness.py::test_probe_does_not_import_ebur128`.

C2. **Probe path no longer calls `_MaybeAutoMarkAudioCompleteAtTarget`.** Only fires when loudness succeeds; dead code without its trigger. `grep -rn "_MaybeAutoMarkAudioCompleteAtTarget" Features/MediaProbe/` returns 0. Method definition + call site both deleted.

C3. **AudioPreEncodeFacade still writes Source loudness columns.** `grep -n "SourceIntegratedLufs=%s" Features/AudioNormalization/Services/AudioPreEncodeFacade.py` still returns line 80. File diff across directive = 0 lines.

C4. **Contract test `TestPreEncodeSourceLoudness.py` still green.** Transcode-time write path unchanged.

C5. **`probe.feature.md` amended at DELIVERING.** Loudness explicitly named out-of-scope for probe with pointer to `audio-normalization`.

C6. **Live smoke.** Fresh probe of a file with NULL `SourceIntegratedLufs` completes without writing that column. Then transcode the file: SourceIntegratedLufs becomes non-NULL.

C7. **Probe throughput measured up >= 5x** on batch of 25 files with NULL Source loudness. Baseline captured pre-fix; post-fix batch time measured. Evidence in close report.

## Files

**Edit:**
- `Features/MediaProbe/MediaProbeBusinessService.py` -- delete lines 135-151 (EbuR128 try-block) + delete `_MaybeAutoMarkAudioCompleteAtTarget` method (line 276 area) + call site (line 146)
- `Features/MediaProbe/probe.feature.md` -- scope amendment (at DELIVERING; promotion target)

**Create:**
- `Tests/Contract/TestProbeNoLoudness.py`

## Call-Graph Audit

- Signal 1 (multiple flow docs): probe is single flow in probe.feature.md. No dup.
- Signal 2 (orchestration mode-branch): none -- pure deletion.
- Signal 3 (mode-sparse output columns): Source*Lufs will populate at transcode-time-only; NULL for unprobed-untranscoded files. Documented in OOS as acceptable degradation.
- Signal 4 (OOS ambiguity): all OOS items categorized below.
- Signal 5 (config-driven graph shape): none -- not gated by any flag.

## Out of Scope

- **(b) Tolerated debt (filed at IMPLEMENTING):** `ContentSignalsService` also inside probe path -- same class of "expensive audio/video-pipeline concern in probe". Separate directive.
- **(a) In-flight preserved:** `QueueManagementBusinessService` priority scoring (lines 315-317) degrades to NULL-tier for unprobed files -- acceptable under strict Dialog Boost policy.
- **(a) In-flight preserved:** `/Activity` on-target loudness widget populates lazily as files transcode.
- Loudness re-measurement policy (`AudioRemeasurementService` / `AudioRemeasurementRunner`) -- untouched.
- Post-encode loudness verification -- untouched.

## Phase machine

NEEDS_STANDARDS_REVIEW -> NEEDS_PLAN -> NEEDS_DOC_PREREAD -> IMPLEMENTING -> VERIFYING -> DELIVERING

### Progress

- [x] NEEDS_STANDARDS_REVIEW: rules loaded from session start; standards/index.md read; call-graph audit five signals populated
- [x] NEEDS_PLAN: criteria + Files locked
- [ ] NEEDS_PLAN: verify `_MaybeAutoMarkAudioCompleteAtTarget` has no other callers
- [ ] NEEDS_DOC_PREREAD: read `probe.feature.md`, `AudioPreEncodeFacade` region, `audio-vertical-dialog-boost-enforcement.feature.md`
- [ ] IMPLEMENTING: delete EbuR128 try-block + method (C1, C2)
- [ ] IMPLEMENTING: contract test `TestProbeNoLoudness` (C1, C2)
- [ ] IMPLEMENTING: file BUG-NNNN for ContentSignals-in-probe (OOS deferred)
- [ ] VERIFYING: TestPreEncodeSourceLoudness still green (C4)
- [ ] VERIFYING: TestWriterOwnsCascadeEnforcement still green
- [ ] VERIFYING: live smoke probe + transcode round-trip (C6)
- [ ] VERIFYING: probe throughput >=5x baseline (C7)
- [ ] DELIVERING: amend `probe.feature.md` (C5); populate Promotions; close report

### Promotions

_Populated at DELIVERING. Content promotes into `Features/MediaProbe/probe.feature.md`._
