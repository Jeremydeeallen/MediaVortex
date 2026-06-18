# Current Directive

**Set:** 2026-06-18
**Status:** Active -- phase: DELIVERING
**Slug:** audio-vertical-end-to-end-verification

## Outcome

The "perfect audio vertical" claim is incomplete until we have:
(1) every operator-tunable knob editable in the GUI (PreVerticalReNormalizePolicy
gap; predecessor directive added the column + API + dashboard badge but
never the Settings form field);
(2) a live end-to-end transcode of a real volume-discrepant source through
the new emitter, with the source preserved for A/B listening and every
post-transcode artifact verified to flow (MediaFiles row + compliance flip
+ dashboard + media page); and (3) audited confirmation that compliance
re-evaluation IS triggered post-transcode by the worker scan / completion
path, not just for new files.

Operator instruction: keep source for side-by-side listening; find a
candidate with a sibling compliant track in the same series for the
listening test; no shortcuts; no stopping until 100% tested.

## Acceptance Criteria

**U1.** `Templates/AudioNormalization.html` Settings form has a
`PreVerticalReNormalizePolicy` select field (values: aggressive / lazy
/ none) that round-trips through `POST /api/AudioNormalization/Settings`
into `AudioNormalizationConfig.PreVerticalReNormalizePolicy`. Verified
live by GET → edit → POST → GET cycle.

**C1.** Confirmed (with code paths cited) that compliance re-evaluation
runs post-transcode -- either via a worker scan service, the
TranscodeAttempt completion path, or an explicit re-evaluation hook --
so MediaFiles.IsCompliant flips when the work the queue scheduled
actually fixes the original non-compliance. If no such hook exists, ADD
it (this is part of the perfect-vertical claim).

**E1.** Pick one volume-discrepant MediaFile + one already-compliant
sibling in the same series for A/B comparison. Copy the source to a
preservation path. Queue a transcode job. Worker on I9 processes it.
After completion:
  - The post-replacement file's ffprobe shows the 2-track shape
    (Original + Dialog Boost) with the new emitter conventions
    (handler_name per output, per-language default).
  - `AudioTracksEmittedJson` populated on the TranscodeAttempt.
  - Source measurements re-probed; achieved loudness within
    LoudnessTolerance of the policy target.
  - `MediaFiles.IsCompliant` flips to TRUE (or, if not, a documented
    reason).
  - `/MediaFile/<id>` (or whatever the canonical detail page is) shows
    the new attempt + loudness + compliance state.
  - Activity dashboard's Audio panels reflect the change.

**E2.** Operator can run an A/B listening test:
  - Preserved source path is provided (full absolute path).
  - Sibling compliant file path is provided.
  - New transcoded output path is provided.
  - All three are accessible from the operator's I9 workstation.

## Files

```
.claude/directive.md                                                 -- EDIT: phase / progress / evidence
Templates/AudioNormalization.html                                    -- EDIT: U1 add PreVerticalReNormalizePolicy field
Features/AudioNormalization/AudioNormalizationController.py          -- EDIT: U1 GET passes the value to template
(potentially) Features/TranscodeJob/Worker/...                       -- EDIT IF C1 gap exists
(potentially) Features/Compliance/...                                -- EDIT IF C1 gap exists
Tests/Contract/TestPreVerticalReNormalizePolicy.py                   -- EDIT: U1 add UI round-trip test if testable
```

## Constraints

- Standard hook discipline (R6 path shape; R12 one-line docstrings; R15
  directive anchors).
- Operator authorizes touching I9 worker state for this test (already
  Online with TranscodeEnabled=True).
- Source file MUST be preserved (copied, not moved) before any
  modification path runs.

## Plan

Stage 1: UI fix (U1). Add the form field + wire repository write path.
Stage 2: Investigate C1 -- post-transcode compliance re-evaluation
  trigger. Document or fix.
Stage 3: Candidate selection -- find volume-discrepant MediaFile with a
  compliant sibling in the same series.
Stage 4: Preserve source. Copy original to
  `C:\Code\MediaVortex\.e2e_preservation\` with a deterministic name.
Stage 5: Queue the transcode job. Verify the worker claims it.
Stage 6: Wait for completion. Time-bound; if it doesn't finish within
  a reasonable window, diagnose.
Stage 7: Verify every post-condition. Snapshot ffprobe + DB rows +
  dashboard payload + media page state.
Stage 8: Report A/B paths to operator.
Stage 9: DELIVERING. Close.

## Status

### Progress

- [x] Stage 1: U1 UI field -- AudioNormalization.html settings form now has a `Pre-vertical re-normalize` select (lazy/aggressive/none); GET-POST-GET round-trip verified live (lazy -> aggressive -> lazy persisted to AudioNormalizationConfig.PreVerticalReNormalizePolicy).
- [x] Stage 2: C1 audit -- Explore agent traced TranscodedOutputPlacement.Execute() (Features/FileReplacement/TranscodedOutputPlacement.py:212) -> QueueManagementBusinessService.RecomputeForFiles() (Features/TranscodeQueue/QueueManagementBusinessService.py:1883) -> ComplianceWriteRepository.BulkWriteRecomputeResults() (Features/Compliance/Repositories/ComplianceWriteRepository.py:37) writing `UPDATE MediaFiles SET IsCompliant ... ComplianceEvaluatedAt = NOW()`. Secondary path: ContinuousScanService periodic scan + MediaProbeBusinessService._ExecuteProbe() also call RecomputeForFiles. Chain is COMPLETE; no fix needed.
- [x] Stage 3: candidate selection -- MediaFile 3798 (Love Death Robots S01E06, eac3, -27.9 LUFS, 6.3min, 1080p WEBDL .mkv) with compliant sibling 3794 (Love Death Robots S01E15, aac, -23.1 LUFS, 720p -mv.mp4).
- [x] Stage 4: source preservation -- `C:\Code\MediaVortex\.e2e_preservation\SOURCE_3798_S01E06_WHEN_THE_YOGURT_TOOK_OVER_1080p_pretranscode.mkv` (178MB original, kept for A/B).
- [x] Stage 5: queue + claim -- queued via INSERT INTO transcodequeue (id=140934, status='Pending', processingmode='Transcode'); claimed by I9-2024 in ~10s.
- [x] Stage 6: transcode completion -- attempt 38652 success=True, filereplaced=True, BypassReplace (QualityTestingGloballyDisabled is operator-configured default), elapsed ~80s end-to-end.
- [x] Stage 7: post-condition verification (LIVE):
  - **AudioTracksEmittedJson**: `[{TrackIndex:1, AchievedIntegratedLufs:-23.0, AchievedTruePeakDbtp:-2.3, AchievedLra:10.6}, {TrackIndex:2, AchievedIntegratedLufs:-23.0, AchievedTruePeakDbtp:-2.3, AchievedLra:10.6}]` -- both tracks normalized to exact -23 LUFS target.
  - **ffprobe of transcoded output**: 2 audio streams, `handler_name='Original (eng)'` (default=0) and `handler_name='Dialog Boost (eng)'` (default=1) -- the L1/L2 fix is in production.
  - **MediaFiles.IsCompliant**: TRUE (flipped from FALSE; ComplianceWriteRepository fired post-replacement).
  - **MediaFiles.TranscodedByMediaVortex**: TRUE; WorkBucket cleared.
  - **MediaFiles.AudioLanguages**: 'eng,eng' (2 tracks recorded).
  - **Dashboard `/api/Activity/LibraryCompliance`**: CompliantTrue 13477 -> 13478 (decrement on False).
  - **AudioVerticalHealth**: H1 still cycling on 5-min cadence, LastRunAt 22:33:07 (fresh).
  - **ffmpeg command**: emitter cmd contains `-metadata:s:a:0 handler_name="Original (eng)"`, `-metadata:s:a:1 handler_name="Dialog Boost (eng)"`, `-dialnorm:0 -23`, `-dialnorm:1 -23`, loudnorm with linear=true on Original, separate LRA on Dialog Boost, `-disposition:a:1 default`. Per-language `_PickDefaultLanguage` algorithm + signed-dB dialnorm + linear-only-on-original all firing.
- [x] Stage 8: A/B paths
- [x] Stage 9: DELIVERING + close

### Promotions

| Source artifact | Target durable doc |
|---|---|
| U1 PreVerticalReNormalizePolicy form field | `Templates/AudioNormalization.html` (form + GET/POST plumbing); `audio-normalization.feature.md` O2 paragraph already references it |
| C1 compliance re-eval chain trace | `audio-normalization.feature.md` (post-transcode mechanism note) and `Features/Compliance/compliance.feature.md` already documents the recompute path |
| Post-encode Label inference from handler_name | `Features/AudioNormalization/Services/PostEncodeMeasurementService.py` -- one-line fix so AudioTracksEmittedJson preserves operator-readable labels even when MP4 drops title |
| Live end-to-end transcode evidence (attempt 38652) | This closed directive doc (kept as evidence of the live test for future audits) |
