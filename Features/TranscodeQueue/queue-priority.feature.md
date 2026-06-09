# Queue Priority -- largest non-compliant first, with manual override window

**Slug:** queue-priority

## What It Does

Defines the order in which workers claim transcode queue rows. One contract serves every claim path (`ClaimNextPendingTranscodeJob`, `ClaimNextPendingRemuxJob`) and every operator-facing list view (`/TranscodeQueue` page, SQLQueries diagnostics, `GetTranscodeQueueItemsPaginated`).

The order is:

```sql
ORDER BY (CASE WHEN tq.Priority >= 195 THEN tq.Priority ELSE 0 END) DESC,
         tq.SizeMB DESC NULLS LAST,
         tq.DateAdded ASC
```

Read top-down:
1. **Manual override window (195-200):** queue rows with `Priority >= 195` jump the queue. Used by the operator Priority modal and by `AudioFixPriorityHints` (`Features/TranscodeQueue/AudioFixPriorityHintsController.py`), which validates the boost is in `[195, 200]` server-side.
2. **Largest non-compliant first:** outside the override window, the largest `SizeMB` claims first. Mirrors the **TV - Next Batch** / **Movies - Next Batch** UI cards (`next-batch-per-drive.feature.md`) — what the operator sees in the cards is what the worker claims.
3. **DateAdded ASC tiebreaker:** within identical size, the older queue row wins.

Auto-computed Priority is no longer written at queue-insert time. All `CreateQueueItem*` paths in `QueueManagementBusinessService` write `Priority = 0`. The `Priority` column on `TranscodeQueue` is reserved exclusively for the 195-200 override window — operator UI overrides and folder-pin hint boosts.

## Concern

Operator dogfood. The prior contract computed a log-scaled "impact score" (`log10(estimated_savings_mb + 1)` mapped into 1-194) at insert time, then ordered by that. Two failure modes:

1. **Log compression flattened the size signal.** A 10× difference in source size moved priority by only ~40 points (700 MB → ~89, 7000 MB → ~127). Combined with the `DateAdded ASC` tiebreaker, claim order did not track size in practice.

2. **Already-efficient large files sank to Priority 1.** Files where `SizeMB - target_size_mb ≈ 0` (e.g. a 6 GB AV1 source against an AV1 profile) computed savings ≈ 0 → Priority 1. The same file sat at the top of Next Batch (still `NeedsTranscode = TRUE`, still huge), creating a disagreement between what the UI surfaced and what the worker actually picked.

The fix is to make claim order match the operator-facing card: largest non-compliant first. The estimated-savings math moves out of the claim path entirely — admission decisions (whether a file should be queued at all) live in `marginal-savings-gate.feature.md`.

## Success Criteria

### A. Claim order

1. `ClaimNextPendingTranscodeJob` ORDER BY (both AcceptsInterlaced branches) is `(CASE WHEN tq.Priority >= 195 THEN tq.Priority ELSE 0 END) DESC, tq.SizeMB DESC NULLS LAST, tq.DateAdded ASC`. Verifiable: `grep -n 'ORDER BY' Features/TranscodeQueue/TranscodeQueueRepository.py` shows this exact composite in both branches of `ClaimNextPendingTranscodeJob`.

2. `ClaimNextPendingRemuxJob` ORDER BY uses the same composite (unqualified `Priority` + `SizeMB` because the Remux SELECT does not alias). Verifiable: same grep above, in `ClaimNextPendingRemuxJob`.

3. With every queue row at `Priority = 0` and no manual overrides set, the next-claimed row is the one with the largest `SizeMB`. Verifiable: insert two `Pending` rows with `Priority = 0` and `SizeMB = (100, 5000)`; the next claim returns the 5000 MB row.

4. A queue row with `Priority = 200` claims before any row with `Priority < 195`, regardless of `SizeMB`. Verifiable: insert one row at `Priority = 200, SizeMB = 50` and one at `Priority = 0, SizeMB = 9999`; the next claim returns the 200-priority row.

5. Two rows both at `Priority = 200` claim in `SizeMB DESC` order. Verifiable: insert two override-window rows; the larger claims first.

### B. Manual override window

6. The operator Priority modal (`Templates/Queue.html`) accepts `[1, 200]`. Values `[195, 200]` jump the queue per criterion 4; values `[1, 194]` are accepted but do not affect claim order (CASE collapses them to 0).

7. `AudioFixPriorityHints` server-side validation (`Features/TranscodeQueue/AudioFixPriorityHintsController.py:AddPin`) rejects `BoostedPriority` outside `[195, 200]` with HTTP 400. Hint-boosted rows surface ahead of size-ordered rows. Verifiable: pin a folder with `BoostedPriority=195`; matching `AudioFix` queue rows claim before any larger non-pinned row.

### C. Insert sites

8. No `CreateQueueItem*` function in `Features/TranscodeQueue/QueueManagementBusinessService.py` calls `CalculatePriority` when constructing a `TranscodeQueueModel`. All queue inserts write `Priority = 0`. Verifiable: `grep -n 'Priority=self.CalculatePriority' Features/TranscodeQueue/QueueManagementBusinessService.py` returns no matches.

9. `CalculatePriority` is still defined for the `ComputePriorityScore` / `ComputePriorityScoresForFiles` path that maintains `MediaFiles.PriorityScore` — a separate denormalized column used by non-claim readers (SmartPopulate-style queue helpers, backfill scripts). Removing it would break those. See `priority-materialization.feature.md`.

### D. Operator-facing list views match claim order

10. `GetAllTranscodeQueueItems`, `GetTranscodeQueueItemsByStatus`, `GetNextPendingTranscodeJob`, and the `Status='Running'` / `Status='Pending'` diagnostic queries in `GetQueueStatistics` all use the same composite ORDER BY. So what the operator sees at the top of `/TranscodeQueue` and in SQLQueries diagnostics is what the next worker will actually claim. Verifiable: `grep -n 'ORDER BY' Features/TranscodeQueue/TranscodeQueueRepository.py Features/SQLQueries/SQLQueriesController.py` shows the composite in every diagnostic / list query against `TranscodeQueue`.

11. `GetTranscodeQueueItemsPaginated` with `SortBy='Priority'` returns rows in the composite order (override-window first, then `SizeMB DESC`). Other `SortBy` values (`SizeMB`, `DateAdded`, `FileName`) sort by their named column alone. Verifiable: paginated request with `SortBy=Priority` and a mix of override-window + auto-zero rows returns override rows first, then largest size first.

## Seams

| ID | Seam | Producer | Wire shape | Consumer expects | Verification |
|---|---|---|---|---|---|
| S1 | Queue insert -> claim ORDER BY | `QueueManagementBusinessService.CreateQueueItem*` | `TranscodeQueue.(Priority INT, SizeMB DOUBLE, DateAdded TIMESTAMP)` — Priority=0 unless operator/hint override | `TranscodeQueueRepository.ClaimNextPendingTranscodeJob` reads composite ORDER BY | Insert rows at varying sizes with `Priority=0`; verify next claim is largest |
| S2 | Manual override -> claim | `TranscodeQueueController.PrioritizeJob` writes `Priority` in `[1, 200]` | Same column, values `>= 195` interpreted as "override" | Claim CASE surfaces override-window rows ahead of size-ordered rows | Set one row to `Priority=200`; confirm it claims before larger rows |
| S3 | AudioFix hint boost -> claim | `AudioFixPriorityHintsController.AddPin` / `ApplyAll` UPDATEs `Priority = BoostedPriority` for matching `ProcessingMode='AudioFix'` rows | Same column, controller enforces `[195, 200]` | Same CASE; hint-boosted rows surface first within their mode | Pin folder; observe matching rows reach top of AudioFix claim |

## Status

COMPLETE -- claim order unified with Next Batch contract, manual override window preserved.

## Files

| File | Role |
|------|------|
| `Features/TranscodeQueue/TranscodeQueueRepository.py` | `ClaimNextPendingTranscodeJob`, `ClaimNextPendingRemuxJob`, `GetAllTranscodeQueueItems`, `GetTranscodeQueueItemsByStatus`, `GetNextPendingTranscodeJob`, `GetTranscodeQueueItemsPaginated` (when SortBy=Priority), `GetQueueStatistics` (active/next diagnostics) — all use the composite ORDER BY |
| `Features/TranscodeQueue/QueueManagementBusinessService.py` | `CreateQueueItemFromMediaFileSimple`, `CreateQueueItemFromMediaFileWithProfile`, `CreateQueueItemFromMediaFile`, `CreateRemuxQueueItem`, `PopulateQueueForSubtitleFix` insert site — all write `Priority=0`. `CalculatePriority` retained for `ComputePriorityScore` (MediaFiles.PriorityScore) only |
| `Features/TranscodeQueue/AudioFixPriorityHintsController.py` | Enforces `BoostedPriority IN [195, 200]` — fits the override window contract |
| `Features/SQLQueries/SQLQueriesController.py` | The pending-queue diagnostic query uses the composite ORDER BY |
| `Templates/Queue.html` | Priority modal accepts `[1, 200]`; `[1, 194]` is a no-op on claim order (CASE collapses to 0); `[195, 200]` jumps the queue |

## See also

- `Features/TranscodeQueue/next-batch-per-drive.feature.md` — the operator-facing UI card whose SQL shape this claim contract mirrors.
- `Features/TranscodeQueue/priority-materialization.feature.md` — `MediaFiles.PriorityScore` column, maintained for non-claim readers; no longer the claim driver.
- `Features/TranscodeQueue/audio-fix-priority-hints.flow.md` — the folder-pinning flow whose hints land in the override window.
- `Features/TranscodeQueue/marginal-savings-gate.feature.md` — the queue-admission gate that decides whether a file enters the queue at all (the impact-savings math moved here).
