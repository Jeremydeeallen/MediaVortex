# Current Directive

**Set:** 2026-06-03
**Status:** Closed -- Success
**Closed:** 2026-06-03
**Slug:** filereplacement-decompose-doc-promotion
**Replaces:** none (cleanup of `directives/closed/2026-06-02-filereplacement-decompose.md` which closed Success without updating the three sibling feature docs that the extraction touched)

## Outcome

Three sibling feature docs of `FileReplacement.feature.md` are updated to reflect the actual code shape after the 2026-06-02 decompose: `transcoded-output-placement.feature.md` knows about `TranscodedOutputPlacement.py`, `post-transcode-pipeline.feature.md` C15 has evidence pointing at the literal chokepoint, `remuxed-flag.feature.md` C4 names the correct method location. Code anchors in the extracted files repoint from any transient directive references to the durable feature/flow doc IDs. Future readers find each contract by following slugs, not by archaeology.

## Acceptance Criteria

1. `transcoded-output-placement.feature.md` `## Files` section names `TranscodedOutputPlacement.py` as the implementation home for criteria A1-7 (placement + `-mv` naming). A `## Seams` section exists with at least 2 rows: (a) `FileReplacementBusinessService.ProcessFileReplacement -> TranscodedOutputPlacement.Execute` (the orchestration -> placement seam) and (b) `TranscodedOutputPlacement.Execute -> ComplianceGate.Evaluate` (the placement -> gate seam). Verifiable: grep the doc for the two Seams rows and the Files mention.

2. `post-transcode-pipeline.feature.md` C15 is updated with an evidence line naming `PostTranscodeDispositionService.CleanupTemporaryFilePaths` as the literal chokepoint (the C15 contract is now live). Verifiable: grep C15 for the method reference.

3. `remuxed-flag.feature.md` C4 (the per-mode flag write) is updated to point at `TranscodedOutputPlacement._UpdateMediaFilesAfterReplacement` (the new home) instead of `FileReplacementBusinessService._UpdateMediaFilesAfterReplacement` (the old home). Verifiable: grep C4 for the new method reference; old reference returns 0 hits in that doc.

4. Code anchor in `Features/FileReplacement/TranscodedOutputPlacement.py:Execute` is updated to `# see transcoded-output-placement.<criterion-ID>` (durable) in addition to the existing directive anchor. Verifiable: grep for `# see transcoded-output-placement` in the file returns >=1 hit.

## Out of Scope

- Re-extracting `_NotifyJellyfin` from FR (still duplicated; tracked separately).
- R12 SQL relocation to Repository classes (deferred batch).
- Hook honesty diffs A/B/C (separate directive `hook-honesty-fence`).

## Constraints

- Keep edits surgical to avoid hitting the directive-growth gate at close.
- R18 overrides declared below for all three sibling docs (each > 50 lines).
- No code logic changes. Only doc edits + code anchor additions.

## Engineering Calls Already Made

- Same shape of fix as `per-profile-vmaf-skip-doc-promotion` (commit c054adb).
- `transcoded-output-placement.feature.md` did not have a `## Seams` section before; this directive adds one.

## Status

Active 2026-06-03 -- phase: DELIVERING.

### Files

```
Features/FileReplacement/transcoded-output-placement.feature.md   -- EDIT: Files + Seams (C1)
Features/FileReplacement/post-transcode-pipeline.feature.md       -- EDIT: C15 evidence (C2)
Features/FileReplacement/remuxed-flag.feature.md                  -- EDIT: C4 method reference (C3)
Features/FileReplacement/TranscodedOutputPlacement.py             -- EDIT: code anchor (C4)
```

### R18 overrides

- `Features/FileReplacement/transcoded-output-placement.feature.md` (109 lines)
- `Features/FileReplacement/post-transcode-pipeline.feature.md` (102 lines)
- `Features/FileReplacement/remuxed-flag.feature.md` (93 lines)

### Promotions

| Source artifact | Target file | Commit |
|---|---|---|
| Files + Seams update for placement contract | `Features/FileReplacement/transcoded-output-placement.feature.md` | TBD |
| C15 evidence row | `Features/FileReplacement/post-transcode-pipeline.feature.md` | TBD |
| C4 method-location update | `Features/FileReplacement/remuxed-flag.feature.md` | TBD |
| Code anchor pointing at feature doc | `Features/FileReplacement/TranscodedOutputPlacement.py` | TBD |

### Verification

- C1: transcoded-output-placement.feature.md has 5 mentions of TranscodedOutputPlacement (Files block + Seams S1/S2/S3 rows); `## Seams` section added.
- C2: post-transcode-pipeline.feature.md C15 names `PostTranscodeDispositionService.CleanupTemporaryFilePaths` + canary verification evidence.
- C3: remuxed-flag.feature.md C4 + C5 point at `TranscodedOutputPlacement._UpdateMediaFilesAfterReplacement`.
- C4: TranscodedOutputPlacement.py Execute carries `# see transcoded-output-placement.C4 | see transcoded-output-placement.S1`.

### Decisions Made

- Canary attempt 27614 cited inline in Seams S1 verification (durable provenance for the seam).
- post-transcode-pipeline.C15 phrasing kept legacy `_CommitDisposition` reference because that's still the dispositioner method that calls the chokepoint -- added "live as of 2026-06-02" to mark the implementation status.
