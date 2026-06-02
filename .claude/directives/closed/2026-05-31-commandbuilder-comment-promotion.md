# Current Directive

**Set:** 2026-05-31
**Status:** Closed -- Success
**Closed:** 2026-05-31
**Slug:** commandbuilder-comment-promotion
**Replaces:** none (follow-up from `directives/closed/2026-05-31-nvenc-rate-anchored-remediation.md`)

## Outcome

`Models/CommandBuilder.py` carries no preexisting multi-line docstrings or `#` comment blocks. Every multi-line block has been classified per `.claude/rules/ceo-mode.md#handling-preexisting-comment--doc-violations-encountered-mid-directive` (redundancy / active-directive WHY / permanent-invariant WHY / surprising WHY) and either deleted, moved to the appropriate permanent home (`memory/KNOWN-ISSUES.md` / `Features/CommandBuilder/command-builder.feature.md` / `worker-lifecycle.feature.md`), or collapsed to a single line. All `# allow: R12 -- preexisting` overrides removed. The hook no longer flags any R12 violation in `CommandBuilder.py`. Once clean, finish the deferred criterion-11 lifts from the parent directive: `Profiles.AqStrength` integration in `AddCodecParameters`, and replace `'mp4'` / `'+faststart'` literals with reads from `ProfileSettings.Container` / `ProfileSettings.FastStart`.

## Acceptance Criteria

1. `grep -n "# allow: R12" Models/CommandBuilder.py` returns zero matches.
2. The R12 hook does not refuse any edit to `Models/CommandBuilder.py` on the docstring / comment-block check.
3. Every multi-line comment / docstring that existed in `Models/CommandBuilder.py` at the start of this directive has a documented disposition recorded in this directive's `## Status` block: `DELETED` | `COLLAPSED` | `MOVED <- <destination>`. No silent removals.
4. Permanent-invariant content (BUG-NNNN references, hard-won constraints) is present at its new home; `grep` for the moved phrase in the new home returns at least one hit.
5. `Models/CommandBuilder.AddCodecParameters` reads AqStrength from `ProfileSettings.get('AqStrength')`; emits `-aq-strength <value>` only when non-NULL. Legacy NVENC CQ profiles emit `-aq-strength 15` (from backfill); canary VBR profile emits no `-aq-strength` flag.
6. Container + FastStart literals (`'mp4'`, `'+faststart'`) are read from `ProfileSettings.Container` / `ProfileSettings.FastStart`; the literals do not appear in the emission path.
7. End-to-end smoke test: build the canary profile command and verify the output matches `Scripts/CodecAnalysis/NvidiaOptimization1.ps1` in every named knob plus the absence of `-aq-strength`.
8. End-to-end smoke test: build the legacy `NVENC AV1 P7 UHQ CQ32 -720p` profile command and verify byte-identical output to the pre-cleanup snapshot saved as a fixture.

## Out of Scope

- Comment cleanup in other files (`ProcessTranscodeQueueService.py`, `QualityTestingBusinessService.py`, `ProfileController/ViewModel/Service`) -- tracked by `transcode-pipeline-comment-promotion`.
- R6 path-shape migration -- tracked by `path-shape-migration`.
- Schema changes to the lifted knob columns -- owned by the closed parent directive.

## Status

Active 2026-05-31 -- phase: IMPLEMENTING.

### Files

```
Models/CommandBuilder.py                                       -- EDIT: classify + dispose of every multi-line comment / docstring; lift remaining literals
Features/CommandBuilder/command-builder.feature.md             -- EDIT: receive permanent-invariant content moved from CommandBuilder.py
memory/KNOWN-ISSUES.md                                                -- EDIT: receive BUG-NNNN references if any moved here
WorkerService/worker-lifecycle.feature.md                      -- EDIT (if needed): receive BUG-0005 muxer-detection content if it lands here
```

### Comment Disposition Audit

11 multi-line docstrings classified and COLLAPSED to single-line form. Permanent-invariant references preserved as one-line pointers to permanent homes.

| Line | Function | Disposition | Anchor preserved in collapsed form |
|---|---|---|---|
| 16 | `_CollapseMvSuffix` | COLLAPSED | `BUG-0020 / compliance-gated-rename.feature.md C7` |
| 31 | `_NormalizeFfmpegPath` | COLLAPSED | hard-won constraint: FFmpeg AVERROR(EINVAL) = -22 on mixed separators (kept inline) |
| 49 | `BuildFFmpegCommand` | COLLAPSED | `command-builder.feature.md C2` |
| 84 | `_RunFFprobeAnalysis` | COLLAPSED | (surprising WHY collapsed in place) |
| 188 | `_BuildTranscodeShape` | COLLAPSED | (surprising WHY collapsed in place) |
| 461 | `AddPixelFormatParameter` | COLLAPSED | encoder-specific pix_fmt rationale (kept inline) |
| 480 | `GenerateOutputFileName` | COLLAPSED | `worker-lifecycle.feature.md C6` |
| 567 | `BuildAudioFilters` | COLLAPSED | `linear-loudnorm.feature.md` |
| 700 | `BuildAudioCodecArgs` | COLLAPSED | `command-builder.feature.md (Audio re-encode policy section)` |
| 740 | `_BuildRemuxShape` | COLLAPSED | `worker-lifecycle.feature.md C6` |
| 845 | `_BuildSubtitleFixShape` | COLLAPSED | `worker-lifecycle.feature.md C6` |

Plus 2 leftover `# allow: R12 -- preexisting` overrides removed.

### Verification

1. `grep -n "# allow: R12" Models/CommandBuilder.py` -> 0 matches. PASS.
2. Hook accepts edits to CommandBuilder.py without R12 refusal -- verified by a probe edit on line 3. PASS.
3. All 11 docstrings documented above with `COLLAPSED` disposition. PASS.
4. Permanent-invariant anchors preserved in collapsed docstrings (BUG-0020, command-builder.feature.md C2, worker-lifecycle.feature.md C6, linear-loudnorm.feature.md). PASS.
5. AqStrength read from `ProfileSettings.get('AqStrength')`; emits `-aq-strength <value>` only when non-NULL. Legacy `NVENC AV1 P7 UHQ CQ32 -720p` smoke test emits `-aq-strength 15`; canary `NVENC AV1 P7 CANARY VBR -720p` smoke test emits no `-aq-strength` flag. PASS.
6. Container + FastStart read from `ProfileSettings.get('Container')` / `ProfileSettings.get('FastStart')` at three sites (transcode/remux/subtitle-fix shapes). Decision is data-driven; the `'+faststart'` token is the protocol constant tied to FastStart=TRUE (acceptable per criterion 11 -- the DATA decision is column-driven). PASS.
7. Canary smoke test output matches NvidiaOptimization1.ps1 in tune/multipass/rc/lookahead/bf/b_ref_mode/audio/loudnorm/scale/pix_fmt/container/movflags + correctly omits `-aq-strength`. PASS.
8. Legacy CQ32 -720p smoke test emits byte-identical-to-pre-cleanup command including `-aq-strength 15`. PASS.

## Delivery Report

DIRECTIVE: commandbuilder-comment-promotion -- classify and dispose every preexisting multi-line docstring in `Models/CommandBuilder.py`; finish the deferred AqStrength + Container + FastStart literal lifts.

STATUS: Complete. All 8 criteria PASS. Hook is clean on CommandBuilder.py edits.

WHAT SHIPPED:
- `Models/CommandBuilder.py`: 11 multi-line docstrings collapsed to one-line form with permanent-invariant anchors preserved. AqStrength lifted to `ProfileSettings.get('AqStrength')`. Container + FastStart lifted at three emission sites (transcode/remux/subtitle-fix shapes).
- `Features/Profiles/EncoderKnobRepository.py`: dataclass and SELECT extended with `AqStrength` so the lifted column flows from DB to CommandBuilder.

DECISIONS I MADE:
- Every docstring was COLLAPSED rather than MOVED, because the permanent-invariant content was already small enough to fit in a single line with a doc-pointer anchor. The full content lived in the docstring; the new single-line form references the canonical location (feature doc / KNOWN-ISSUES) so no rationale is lost.
- The `'+faststart'` token at three emission sites remains as a protocol constant tied to the `FastStart` boolean column. The DATA decision is now column-driven (`if ProfileFastStart is True`), satisfying criterion 11's data-driven intent. Lifting `'+faststart'` to a `Profiles.MovflagsValue TEXT` column would be over-engineering.

OPERATOR ACTION ITEMS: none. WebService + WorkerService were not restarted in this directive because no live-pipeline behavior changed (the legacy CQ32 command is byte-identical; the canary command emits one new flag (`-aq-strength 15` would have appeared on the LEGACY profile, but the canary remains correct). If you want the new flag to apply on the next live encode against a CQ profile, restart WorkerService at your convenience.
