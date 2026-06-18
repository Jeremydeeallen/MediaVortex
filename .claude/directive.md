# Current Directive

**Set:** 2026-06-18
**Status:** Active -- phase: IMPLEMENTING
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

- [ ] Stage 1: U1 UI field
- [ ] Stage 2: C1 post-transcode compliance re-evaluation audit
- [ ] Stage 3: candidate selection
- [ ] Stage 4: source preservation
- [ ] Stage 5: queue + claim
- [ ] Stage 6: transcode completion
- [ ] Stage 7: post-condition verification
- [ ] Stage 8: A/B paths to operator
- [ ] Stage 9: DELIVERING + close

### Promotions

[Populated at DELIVERING phase]
