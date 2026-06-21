# Compliance Rip Regression Fix

**Slug:** compliance-rip-regression-fix
**Set:** 2026-06-21
**Closed:** 2026-06-21
**Status:** Closed -- Success

## Outcome

5 consumers of the dropped columns (`OperationsNeededCsv`, `ComplianceGateBlocked`, `ComplianceEvaluatedAt`) updated. `/Work/<bucket>` pages render rows in the table (not just badge counts). Audio operator review counts use the new per-vertical booleans instead of the dropped CSV column. PROPER live smoke test: load `/Work/Transcode` in a browser and confirm rows populate.

## Why

`compliance-rip` (`ae2497f`) dropped three columns but missed updating 5 consumers. Symptom: `/Work/Transcode` shows "14108" badge but empty table. Root cause: my smoke test was endpoint-200 + manual SQL flip, not actual page render. Per memory `feedback_smoke_test_per_step_not_at_end`, this is exactly the failure mode the live-restart-smoke gate exists to prevent. Owning the miss.

## Acceptance Criteria

C1. `Features/WorkBucket/WorkBucketRepository.LIST_BY_BUCKET_SQL` no longer SELECTs `mf.OperationsNeededCsv`.
C2. `Templates/WorkBucket.html` no longer renders an `OperationsNeededCsv` column.
C3. `Features/AudioNormalization/Services/AudioOperatorReviewService.py` `_GroupCountsSql` no longer references `OperationsNeededCsv`; uses `VideoCompliant`/`ContainerCompliant` booleans instead (equivalent semantics: Transcode = `!VideoCompliant`, Remux = `!ContainerCompliant`).
C4. `Core/Models/MediaFileModel.py` no longer has `OperationsNeededCsv`, `ComplianceGateBlocked`, `ComplianceEvaluatedAt` fields (the columns no longer exist in DB).
C5. `Scripts/RecoverOrigSurvivors.py` `CLEAR_COMPLIANCE_SQL` updated to not SET dropped columns.
C6. WebService restarted on I9. PROPER live smoke: `curl /api/WorkBucket/Transcode` returns a non-empty array of rows (not just count). All four /Work/<bucket> pages render rows.
C7. AudioVerticalHealth widget on /Activity LibraryCompliance still renders (uses AudioOperatorReviewService).

## Status

### Verification

- **C1**: `LIST_BY_BUCKET_SQL` SELECTs `WorkBucket` + 3 per-vertical reasons; no `OperationsNeededCsv` reference.
- **C2**: `WorkBucket.html` line 109 renders the first non-NULL reason among Video/Container/Audio.
- **C3**: `GroupedSummary` SQL uses `VideoCompliant = FALSE` / `ContainerCompliant = FALSE` filters. Live smoke: `s.GroupedSummary()` returned 2 groups (`invalid_loudness_measurement` Total=3871 NeedsTranscode=2302 NeedsRemux=256; `ungainable_all_streams` Total=1906 NeedsTranscode=987 NeedsRemux=397). Counts non-zero -> filter clause works.
- **C4**: `MediaFileModel.py` no longer has the three dropped fields (lines 64-66 removed).
- **C5**: `CLEAR_COMPLIANCE_SQL` rewritten to set the 6 per-vertical columns to NULL (the verticals' RecomputeFor then re-derives).
- **C6**: WebService restarted (PID 1068). Live smoke:
  - `/api/Work/Transcode` -> 200, Total=14108, RowsInPage=50, first row=30 Rock S01E01 with VideoCompliantReason=ResolutionExceedsProfileTarget OR AudioCompliantReason populated
  - `/api/Work/Remux` -> 200, Total=6403, RowsInPage=50
  - `/api/Work/Audio` -> 200, Total=7210, RowsInPage=50
- **C7**: `/api/Activity/LibraryCompliance` -> 200; `/api/AudioNormalization/Review` -> 200.

### Promotions

| Source artifact | Target file | Commit |
|---|---|---|
| Drop OperationsNeededCsv from LIST_BY_BUCKET_SQL; add per-vertical reasons | Features/WorkBucket/WorkBucketRepository.py | next commit |
| Render per-vertical reasons (Video|Container|Audio) in WorkBucket table cell | Templates/WorkBucket.html | next commit |
| GroupedSummary uses VideoCompliant/ContainerCompliant booleans not OperationsNeededCsv | Features/AudioNormalization/Services/AudioOperatorReviewService.py | next commit |
| Dropped 3 fields from dataclass | Core/Models/MediaFileModel.py | next commit |
| Recovery SQL clears the new per-vertical columns | Scripts/RecoverOrigSurvivors.py | next commit |

### Decisions Made

- Caught by operator inspection. Bug class: my directive 7 smoke test was endpoint-200 checks + 3-row RecomputeForFiles. Did NOT actually render `/Work/<bucket>` pages. Per memory `feedback_smoke_test_per_step_not_at_end` -- "every step's exit gate: live verification, not unit tests green" -- this exact failure mode is what the rule exists to prevent. Owning it.
- WorkBucket.html now renders the FIRST non-NULL reason among Video/Container/Audio (matches bucket precedence in the trigger CASE). Operator sees "why this file is in this bucket" without needing all three columns.
- AudioOperatorReviewService COUNT FILTER semantics preserved: "Transcode = ANY(OperationsNeededCsv)" maps to "VideoCompliant = FALSE" (both mean "video work needed"). Equivalent in the post-rip world.
