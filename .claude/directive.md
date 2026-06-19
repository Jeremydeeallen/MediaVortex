# Current Directive

**Set:** 2026-06-18
**Status:** Active -- phase: IMPLEMENTING
**Slug:** audio-review-queue-grouping

## Outcome

`/AudioNormalization` Review tab currently renders 1,896 individual rows
with one Resolve button each -- unusable. Group them by
`AdmissionDeferReason`, show counts, and offer a bulk Resolve per group
that clears the audio defer reason (NOT IsCompliant) so ComplianceGate
re-routes the file to whatever WorkBucket applies (Transcode / Remux /
AudioFixOnly / None).

## Acceptance Criteria

**G1.** `GET /api/AudioNormalization/Review` returns
`{Groups: [{AdmissionDeferReason, Count, AuditOnlyAudio, AlsoNeedsTranscode, AlsoNeedsRemux, Samples:[Id,FileName,SourceIntegratedLufs]}], Total}`.
Samples cap at 5 per group for drill-down preview. The flat `Rows` array
is removed.

**G2.** `POST /api/AudioNormalization/Review/Resolve` accepts
`{AdmissionDeferReason: <reason>}` and clears the column for every
MediaFile carrying that reason. Returns `{Cleared: N}`. ComplianceGate
re-evaluation is triggered for affected rows.

**G3.** Review tab UI renders one row per group: reason text, total,
breakdown chips (audio-only / +Transcode / +Remux), expand toggle that
fetches samples, single Resolve-all button per group.

**G4.** Bulk Resolve flips no IsCompliant bits directly -- it only
clears AdmissionDeferReason. The compliance recompute is triggered
through the existing `QueueManagementBusinessService.RecomputeForFiles`
chain so each file lands in the correct WorkBucket.

## Files

```
.claude/directive.md                                                 -- EDIT: progress
Features/AudioNormalization/AudioNormalizationController.py          -- EDIT: rewrite /Review GET + add /Review/Resolve bulk POST
Features/AudioNormalization/Services/AudioOperatorReviewService.py   -- EDIT: GroupedSummary() + BulkClearByReason() methods
Templates/AudioNormalization.html                                    -- EDIT: replace flat Review table with grouped collapsible rows
Tests/Contract/TestAudioOperatorReviewServiceGrouping.py             -- CREATE: grouping + bulk clear contracts
```

## Status

### Progress

- [ ] G1 API grouping
- [ ] G2 bulk resolve endpoint
- [ ] G3 grouped UI
- [ ] G4 recompute trigger on bulk
- [ ] verify live (1896 -> grouped -> bulk resolve smoke)

### Promotions

[Populated at DELIVERING phase]
