# Current Directive

**Set:** 2026-06-03
**Status:** Closed -- Success
**Closed:** 2026-06-03
**Slug:** per-profile-vmaf-skip-doc-promotion
**Replaces:** none (cleanup of `directives/closed/2026-06-03-per-profile-vmaf-skip.md` which closed Success without proper doc promotion)

## Outcome

The contract that `Profiles.qualitytestrequired` is the per-attempt source of truth for whether VMAF runs is captured in `post-transcode-disposition.feature.md` (the feature doc that already owns the dispositioner's decision table). The code anchor in `ProcessTranscodeQueueService.CreateTranscodeAttempt` points at the new feature-doc criterion instead of the transient directive slug. Future readers find the contract by following the slug, not by digging through closed-directive archives.

## Acceptance Criteria

1. `post-transcode-disposition.feature.md` gains a new criterion (e.g. C30) that states: "`TranscodeAttempts.QualityTestRequired` is sourced from `Profiles.qualitytestrequired` at attempt-creation time. Default TRUE preserves existing behavior. Verifiable: SELECT QualityTestRequired FROM TranscodeAttempts WHERE Id=<N> equals SELECT qualitytestrequired FROM profiles WHERE profilename = (the AssignedProfile of the source MediaFile of the attempt)." Verifiable in this directive: grep the feature doc, criterion present with concrete verification phrasing.

2. `post-transcode-disposition.feature.md` `## Seams` table gains one row: `Profiles.qualitytestrequired -> TranscodeAttempts.QualityTestRequired -> dispositioner Row 2`. Producer = `ProcessTranscodeQueueService.CreateTranscodeAttempt` profile lookup, wire shape = BOOLEAN, consumer = `_DecideFromInputs` Row 2 (`if not QualityTestRequired: return ('BypassReplace', 'QualityTestNotRequired')`), verification = contract test or SQL audit. Verifiable: grep the feature doc, row present with concrete fields.

3. Code anchor in `Features/TranscodeJob/ProcessTranscodeQueueService.py:CreateTranscodeAttempt` is updated: the line `# see per-profile-vmaf-skip.C3` (transient directive) is replaced with `# see post-transcode-disposition.C30` (durable feature doc). Verifiable: grep for `# see per-profile-vmaf-skip` returns 0 results; grep for `# see post-transcode-disposition.C30` returns 1.

## Out of Scope

- The broader `filereplacement-decompose` doc gaps (transcoded-output-placement Seams, post-transcode-pipeline.C15 evidence update, remuxed-flag fields). Separate follow-up sweep -- explicitly noted at close.
- Per-file `QualityTestOverride` design. Still deferred.
- Hook honesty diffs A/B/C -- separate directive `hook-honesty-fence`, awaiting operator paste.

## Constraints

- Feature doc edit + code anchor edit must land in the same commit (atomic promotion).
- R18 override for `post-transcode-disposition.feature.md` if its line count > 50.
- No new code logic. Only doc text + one anchor line.

## Engineering Calls Already Made

- `post-transcode-disposition.feature.md` is the right home (not `qualitytesting.feature.md`) because the dispositioner's decision table is where the flag is consumed; the feature doc owns the decision contract.
- Criterion numbering: feature doc has criteria up to ~C26 in the qt-queue-visibility extension. New criterion will be C30 to leave room and avoid collision.

## Status

Active 2026-06-03 -- phase: DELIVERING -- direct close after doc + anchor edits land.

### Files

```
Features/QualityTesting/post-transcode-disposition.feature.md   -- EDIT: add C30 + Seams row (C1, C2)
Features/TranscodeJob/ProcessTranscodeQueueService.py           -- EDIT: repoint anchor # see per-profile-vmaf-skip.C3 -> # see post-transcode-disposition.C30 (C3)
```

### R18 overrides

- `Features/QualityTesting/post-transcode-disposition.feature.md` (size unknown; partial-read sufficient for edit but DELIVERING-time edit may need full doc scope)

### Promotions

| Source artifact | Target file | Commit |
|---|---|---|
| Per-profile VMAF skip contract (new criterion + Seam) | `Features/QualityTesting/post-transcode-disposition.feature.md` | TBD |
| Code anchor repointing from directive to feature doc | `Features/TranscodeJob/ProcessTranscodeQueueService.py` | TBD |

### Verification

- C1: `grep -n "^30\." Features/QualityTesting/post-transcode-disposition.feature.md` returns the new criterion under section J.
- C2: `grep -n "^## Seams\|^| S1 " Features/QualityTesting/post-transcode-disposition.feature.md` returns the new Seams section + S1 row.
- C3: `grep "see post-transcode-disposition" Features/TranscodeJob/ProcessTranscodeQueueService.py` returns 1; `grep "see per-profile-vmaf-skip" ...` returns 0. Smoke import OK.

### Decisions Made

- Used criterion number 30 (skipping C27-29 to leave room for in-progress amendments).
- Added ## Seams section to the feature doc — it did not previously exist (the doc predates the seams-table convention).
- Anchor format `# see <slug>.C<N> | see <slug>.S<N>` for two pointers (criterion + seam) on one line per R12.
