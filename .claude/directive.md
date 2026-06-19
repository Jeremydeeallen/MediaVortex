# Current Directive

**Set:** 2026-06-19
**Status:** Active -- phase: IMPLEMENTING
**Slug:** audio-vertical-seam-contracts

## Outcome

Expose the audio vertical's cross-vertical contracts in `audio-normalization.feature.md`
as a durable section that other verticals can read without opening any
audio-vertical code file. Then deploy the audio vertical's current source
tree to larry, dot, wakko (skip wakko if offline). At close, the audio
vertical can be honestly called 100% done.

## Acceptance Criteria

**S1.** `audio-normalization.feature.md` gains a `## Cross-Vertical Contract`
section that enumerates four parts:
  1. **Columns the audio vertical WRITES** (other verticals may SELECT, must
     never UPDATE)
  2. **Columns the audio vertical READS** (operator-editable via Settings UI;
     no other vertical writes)
  3. **Stable function entry points** with signatures (`EmitTracks(...)`,
     `AdmitOrDefer(...)`, `ListReviewQueue()`, etc.)
  4. **Explicitly NOT contracts** (internal class names, SQL clauses,
     regex patterns -- callers must not depend on these)

**S2.** `transcode.flow.md` audio-stage section references the audio
vertical's seams by the names in S1 -- no inline duplication of internals.

**S3.** Existing intra-feature seam table in `audio-normalization.feature.md`
(`## Seams` IDs `S1..S14`) audited against current code; outdated rows
struck or updated.

**S4.** Deploy current source tree to larry + dot via existing deploy
scripts; verify each worker's `Workers.Version` stamp advances; unpause
both at the DB level. Wakko skipped if unreachable (gateway "Destination
unreachable" today); documented as deferred operationally.

## Files

```
.claude/directive.md                                                 -- EDIT: phase / progress / promotions
Features/AudioNormalization/audio-normalization.feature.md           -- EDIT: add Cross-Vertical Contract section; audit Seams table
transcode.flow.md                                                    -- EDIT: audio stage references seams by name only
```

## Plan

- [ ] Stage A: write cross-vertical contract section by reading current code surface
- [ ] Stage B: audit and update existing intra-feature Seams table
- [ ] Stage C: update transcode.flow.md audio references
- [ ] Stage D: commit + push
- [ ] Stage E: deploy to larry + dot via deploy/deploy-linux-worker.py
- [ ] Stage F: verify worker version stamps + unpause both
- [ ] Stage G: wakko deferred-due-to-offline noted
- [ ] Stage H: VERIFYING + DELIVERING

## Status

### Progress

(checklist above)

### Promotions

[Populated at DELIVERING phase]
