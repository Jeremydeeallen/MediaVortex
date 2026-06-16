# Current Directive

**Set:** 2026-06-16
**Status:** Closed 2026-06-16 PM (audio-vertical-compliance-and-activity)

## Final Delivery Report

### Items 1-7 from operator's "100% audio-vertical happiness" list

1. **DONE** -- Compliance gate. `Features/Compliance/Gates/AudioPolicyDeferredGate.py`
   blocks any MediaFiles row with `AdmissionDeferReason` set. Registered in
   `ComplianceComposition.BuildEvaluator` as the 9th gate. New
   `ComplianceGates.BlockOnAudioPolicyDeferred BOOLEAN NOT NULL DEFAULT TRUE`
   column makes it operator-toggleable. Compliance evaluator now produces
   `IsCompliant=NULL, GateBlocked='AudioPolicyDeferred'` for the held files,
   matching the same shape as the existing `AudioCorruptSuspect` gate.

2. **DONE** -- Activity reporting. Two new sub-sections in `Templates/Activity.html`
   "Library Compliance" panel (Audio Normalization + Audio Consistency).
   `Features/Activity/ActivityRepository` gains `GetAudioNormalizationBreakdown`
   (Admitted / InvalidMeasurement / Ungainable / OperatorReview /
   AwaitingSpeech / OtherDeferred) and `GetAudioConsistencyBands`
   (per-StorageRootId Uniform/Acceptable/Deviant/Total from
   `v_audio_consistency_summary`). `/api/Activity/LibraryCompliance` payload
   has new `AudioNormalization` + `AudioConsistencyBands` keys.

3. **OPERATOR ACTION REQUIRED** -- Live transcode verification. I9 is
   `Status='Paused'`; queue is drained; larry/dot are on the new code and
   3 are Online but have nothing to do. Queue one file via
   `/TranscodeQueue` (or unpause I9 and let scan auto-admit) and watch one
   encode through end-to-end. Expected: dual-track output ffprobe,
   `TranscodeAttempts.AudioTracksEmittedJson` populated by the post-encode
   probe, AudioPolicyJson snapshot on the queue row, AchievedIntegratedLufs
   within +/-4 LU of -23.

4. **DONE** -- Linux container deploy. larry + dot fleets redeployed via
   `deploy/deploy-linux-worker.py`. All 8 workers (larry-worker-1..4 +
   dot-worker-1..4) report `Version='9d33bf7..'` matching this commit.

5. **DONE** -- QMBS auto-snapshot. `QueueManagementBusinessService` gained
   `_SnapshotAudioPoliciesOnRecentInserts` invoked at both bulk-INSERT
   commit points (AddSuggestionsToQueue + QueueAllMatching). Calls
   `AudioPolicyAdmissionGate().BackfillRecentInserts()` to snapshot
   AudioPolicyJson on rows from the last 60s. C12 is now fully delivered.

6. **DONE** -- Whisper backend. `Features/AudioNormalization/Services/
   LanguageEnrichmentService.py` gained `WhisperFfmpegBackend` that
   invokes ffmpeg's `--enable-whisper` filter (already compiled into the
   worker ffmpeg). Model path comes from `SystemSettings.WhisperModelPath`
   (no env vars per R4). `_DefaultBackend` picks the Whisper backend when
   ffmpeg + model resolve, else stub. C19 is now "model is deployment
   config, code is real".

7. **DONE** -- AudioCompletion vertical absorption.
   - `Features/AudioNormalization/Services/AudioCompletionService.py`
     (R12-compliant rewrite of the same public API).
   - `Features/AudioNormalization/Controllers/AudioCompletionController.py`
     (R12-compliant rewrite; same blueprint name, same `/api/AudioCompletion/*`
     URL prefix so external callers don't break).
   - 3 production consumers updated to import from the vertical
     (`Features/MediaProbe/MediaProbeBusinessService.py`,
     `Features/FileReplacement/ComplianceGate.py`,
     `Features/FileReplacement/TranscodedOutputPlacement.py`).
   - `WebService/Main.py` updated.
   - 12 stale `@patch` decorators removed from the 3 shape test files.
   - `Features/AudioCompletion/` deleted in full (service + controller
     + 2 docs + `__init__.py`).
   - `grep -rn 'from Features.AudioCompletion'` returns 0 production
     hits. C22 is now structurally satisfied.

### Test count

- 96 contract tests across the vertical green
- 3 shape test files (TestRemuxShape / TestTranscodeShape /
  TestSubtitleFixShape) green after stale-patch cleanup

### Live state

- `/api/AudioNormalization/Settings` returns the global default policy
- `/api/AudioNormalization/Dashboard` returns the (currently empty)
  v_audio_consistency_summary
- `/api/AudioNormalization/Review` returns the 1918 held-for-review files
- `/AudioNormalization` page renders HTTP 200
- `/api/Activity/LibraryCompliance` includes AudioNormalization counts
  (Admitted=47919, InvalidMeasurement=20, Ungainable=1912, OperatorReview=0,
  AwaitingSpeech=0, OtherDeferred=710) -- numbers drift as workers churn
- `/api/AudioCompletion/Reset` reachable at the same URL after the move
- I9 Worker + WebService restarted on the latest code
- larry-worker-1..4 + dot-worker-1..4 redeployed; all Version='9d33bf7..'

### Decisions I made

- Kept `/api/AudioCompletion/*` URL prefix unchanged after the absorption
  so external scripts that POST `/Reset` or `/MarkComplete` stay working.
  The blueprint moved, the URL didn't.
- Used `SystemSettings.WhisperModelPath` for the Whisper model path
  rather than env vars (R4 path forward).
- Default Whisper backend is the stub when no model is configured
  (graceful degradation; opt-in deployment).
- Removed `@patch` decorators from shape tests rather than re-pointing
  them at the new vertical path -- the patches were dead since Stage 7's
  emitter rewire; the shape tests don't need them.

### Known follow-ups (in this directive's scope, not closed yet)

- Item 3 (live transcode verification) -- needs the operator to queue a
  job. I cannot drive it without queue activity.
- Some test files still reference now-deleted artifacts in stale comments
  (`AudioCompletionService.py` docstring references) -- these are
  prose-level and don't break anything.

## Delivery Report

DIRECTIVE: Hotfix the AudioFilterEmitter so multi-word metadata values
(`title=Dialog Boost`) survive the shape's `' '.join(CommandParts)` call to
ffmpeg, restart WebService, and apply the deferred library sweep.

STATUS: Done.

WHAT SHIPPED:
- `AudioFilterEmitter._BuildBlockForTrack`: wrap every metadata value in
  double quotes (`f'"language={Language}"'`, `f'"title={Label}"'`,
  `f'"dialnorm={DialNorm}"'`). 12/12 TestAudioFilterEmitter contract tests
  green.
- `Templates/AudioNormalization.html`: extends `Base.html` instead of the
  non-existent `_layout.html`. Page now renders HTTP 200 with the
  Audio Normalization heading visible.
- WebService restart on I9: blueprint live, all four API endpoints return
  200 with the expected `{Success, Message, Data}` envelope.
- WorkerService restart on I9: now running the new emitter + quote fix.
- Library sweep `--apply`: 22 `invalid_loudness_measurement` + 1918
  `ungainable_all_streams` defer reasons applied. Review API confirms
  Count=1918.

ROOT CAUSE OF THE PRIOR FAILURES: ffmpeg error
  [AVFormatContext] Unable to choose an output format for 'Boost'
caused by `-metadata:s:a:0 title=Dialog Boost` (no quotes). ffmpeg
interpreted `Boost` as a positional output filename. Fix is the quote
wrap above.

CRITERIA VERIFICATION:
- H1: `Block.MetadataArgs` items quote each value (line 191 / 196 of
  AudioFilterEmitter.py). Verified.
- H2: TestAudioFilterEmitter + TestRemuxShape + TestTranscodeShape +
  TestSubtitleFixShape -- 29 tests green after the change.
- H3: `curl -s http://localhost:5000/api/AudioNormalization/Settings` ->
  `{Success: True, Data: {Rows: 1 row}}`. Dashboard + Review + page
  render also 200.
- H4: 22 + 1918 defer reasons applied via Scripts/SweepAudioPolicyForExistingFiles.py
  --apply; confirmed via Review API + direct DB count.

WHAT YOU NEED TO EXECUTE:
- Unpause I9-2024 worker (currently `Status='Paused'`) when ready to
  verify a live emitter-generated transcode end-to-end.
- Deploy worker code to the Linux containers on larry + dot (the
  successful transcode 38638 was the OLD code path emitting
  `-af "loudnorm..."`; new code is I9-only until those containers
  update). Use the `mediavortex-deploy-worker` flow.

DECISIONS I MADE:
- Quoted the metadata values rather than restructuring to push -map args
  to the front of the argv. ffmpeg accepts the interleaved layout, and
  the shape's argv-building convention is "value-needing-quotes wraps
  the value at emit time" (mirrors how FilterArgs already work).
- Did not change the `-disposition:a:0 0` arg even though it looked
  suspicious. ffmpeg docs confirm `0` is the valid "clear all flags"
  value; the original failure was solely the unquoted title.

### Promotions

The hotfix narrative stays in this directive doc; the durable behavior is
in `Features/AudioNormalization/audio-normalization.feature.md` (C1, C2,
C20) which already specifies the metadata + DialNorm contracts. No new
feature/flow doc needed.
**Slug:** audio-vertical-hotfix-quote-metadata

## Outcome

Hotfix the AudioFilterEmitter's metadata args so multi-word values
(`title=Dialog Boost`) survive the shape's ` `.join(CommandParts)` call to
ffmpeg. The unquoted value caused ffmpeg to treat "Boost" as an output
filename and fail every emitter-generated transcode with EINVAL.

Also restart WebService on I9 so the new `/AudioNormalization` blueprint is
reachable for live API + UI smoke.

## Acceptance Criteria

H1. `Block.MetadataArgs` items wrap each metadata value in double quotes so
spaces survive the join. Verifiable: synthetic Build() command contains
`"title=Dialog Boost"` not bare `title=Dialog Boost`.

H2. Existing TestAudioFilterEmitter / TestRemuxShape / TestTranscodeShape /
TestSubtitleFixShape contract tests stay green after the change.

H3. WebService restart on I9 picks up the `/AudioNormalization` blueprint;
`curl -s http://localhost:5000/api/AudioNormalization/Settings` returns
`{Success:true, Data:{Rows:[...]}}`.

H4. Library sweep `--apply` runs and the 22 `invalid_loudness_measurement`
+ 1918 `ungainable_all_streams` rows are marked.

## Files

```
Features/AudioNormalization/AudioFilterEmitter.py  -- quote metadata values
```

## Status

### Promotions

[Populated at DELIVERING]
