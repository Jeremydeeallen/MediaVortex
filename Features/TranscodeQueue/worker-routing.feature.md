# Worker Routing -- tag-based affinity for queue claim

**Slug:** worker-routing

## What It Does

Adds a tag-based routing layer on top of the existing "fair race" queue claim. Today every transcode-enabled worker is identical to every other one -- whoever wins the `SELECT FOR UPDATE SKIP LOCKED` race claims the next-priority job, regardless of any worker characteristics. After this feature, an operator can:

1. **Tag a worker** with arbitrary labels (e.g. `fast`, `av1-only`, `local-disk`, `i9`).
2. **Pin a profile** to require or prefer a tag (e.g. "the SVT-AV1 P4 4K profile requires a `fast` worker") so heavyweight jobs go to capable hardware.
3. **Pin a queue row** to require or prefer a tag at populate time (advanced use; same shape).

The claim query gains a tag-match score that orders pending rows so a job's preferred-tag worker wins the race when one is polling. Hard requirements act as a filter (a non-matching worker simply skips that row, like the existing `AcceptsInterlaced=false` path). Untagged rows behave exactly as today -- no tag, no preference, fair race wins.

This is not a load-balancer. It is not a least-loaded scheduler. It is a *routing* layer: "this job belongs on workers with these tags."

## Concern

Operator dogfood -- 2026-05-09. Today's claim model treats all workers as interchangeable, but they are not: I9-2024 has a different CPU/disk profile than the LXC fleet, and certain profiles (e.g. 4K SVT-AV1) finish 4-5x faster on a fast worker. There is also no way to keep a worker idle for a specific class of work (e.g. "reserve I9 for VMAF-quality re-runs at off hours"). A fair race produces approximately-fair throughput but cannot honour deliberate operator preference.

## Success Criteria

### A. Schema

1. `Workers` table gains a nullable `Tags TEXT` column storing comma-separated lower-cased tag strings (e.g. `"fast,local-disk,av1"`). Migration `Scripts/SQLScripts/AddWorkerRoutingColumns.py` runs idempotently. Verifiable: `\d Workers` shows the column.

2. `Profiles` table gains nullable `PreferredWorkerTags TEXT` and `RequiredWorkerTags TEXT` columns (same comma-separated shape). Same migration, idempotent. Verifiable: `\d Profiles` shows both columns.

3. `TranscodeQueue` does **not** get its own tag columns. Routing is profile-driven; per-job overrides are out of scope for this feature. (If a future case justifies per-job overrides, that is a separate `/n`.) Verifiable: scope section of this doc and the migration script both omit TranscodeQueue.

### B. Claim algorithm

4. The atomic claim query (`DatabaseManager.ClaimNextPendingTranscodeJob`) is updated. The new shape, in pseudocode:

    ```sql
    UPDATE TranscodeQueue
    SET Status='Running', ClaimedBy=?, ClaimedAt=NOW(), DateStarted=NOW()
    WHERE Id = (
        SELECT tq.Id FROM TranscodeQueue tq
        LEFT JOIN MediaFiles mf ON mf.Id = tq.MediaFileId
        LEFT JOIN Profiles p ON p.Name = mf.AssignedProfile
        WHERE tq.Status='Pending'
          AND (p.RequiredWorkerTags IS NULL
               OR <every tag in p.RequiredWorkerTags appears in worker_tags>)
          AND (mf.IsInterlaced IS NULL OR mf.IsInterlaced='0' OR worker_accepts_interlaced)
        ORDER BY
          (CASE WHEN p.PreferredWorkerTags IS NULL THEN 0
                ELSE <count of preferred tags the worker has> END) DESC,
          tq.Priority DESC,
          tq.DateAdded ASC
        LIMIT 1
        FOR UPDATE SKIP LOCKED
    )
    RETURNING ...
    ```

    The worker's tags and `AcceptsInterlaced` are passed as parameters. The required-tag check is a filter (row excluded entirely if the worker doesn't have all required tags). The preferred-tag count is the primary sort key, breaking ties via the existing `Priority DESC, DateAdded ASC`. Verifiable: with three workers (A=`fast`, B=`fast,gpu`, C=untagged) and a profile preferring `fast,gpu`, worker B's claim returns that job before A; worker C never claims it; if no `fast,gpu` job is pending, C and A still race fairly on others.

5. The `AcceptsInterlaced=false` filter is kept and lives in the same WHERE clause. Two filters compose: a non-interlace-capable worker that also lacks a required tag still skips the row. Verifiable: code inspection plus a contract-test queue with both constraints.

6. **Untagged claim path** (no profile has tag columns set): the query reduces to today's `ORDER BY Priority DESC, DateAdded ASC` because every preferred-match score evaluates to 0. No regression for operators who don't opt into routing. Verifiable: `EXPLAIN` shows the same plan as today's claim when both Profiles tag columns are NULL across the board.

### C. Operator surface

7. The Activity page worker tile (already redesigned by `activity-dashboard-improvements.feature.md`) renders the worker's tags as a comma-separated muted-text line above the action buttons: `Tags: fast, local-disk` or `Tags: <none>`. This is purely informational on the tile; editing happens via a small "Edit Tags" link that opens a tag input modal. Verifiable: render the page, observe the tags row exists per tile.

8. New endpoint `POST /api/TeamStatus/Workers/<name>/Tags` body `{"Tags": "fast,local-disk"}` UPSERTs `Workers.Tags`. Mirrors the existing Status / Capability endpoints. Server normalizes (lowercases, strips whitespace, dedupes). Verifiable: POST with `"Fast, FAST , local-disk"`, query `SELECT Tags FROM Workers WHERE WorkerName=?`, value is `"fast,local-disk"`.

9. The Profiles edit page (`Templates/ShowSettings.html` or wherever profiles are edited -- see Files section for resolution) gains two text inputs: `Preferred Worker Tags` and `Required Worker Tags`. Same comma-separated input format; same server-side normalization. Verifiable: edit a profile via the UI, set `Required: fast`, save, confirm the value persists on reload.

### D. Backwards compatibility

10. A worker with `Tags=NULL` or `Tags=""` behaves exactly like today: it can claim any job whose profile has no `RequiredWorkerTags` set. It will lose the preferred-tag race to a tagged worker for any job whose profile has `PreferredWorkerTags`, but it never gets blocked from work that has no requirements. Verifiable: keep the local Windows worker (I9-2024) with no tags after migration; queue ordinary 720p jobs; confirm I9-2024 still claims them at the usual rate.

11. Existing pending TranscodeQueue rows are unaffected by the migration. The change is purely routing on claim; rows themselves carry no tag state. Verifiable: `SELECT COUNT(*) FROM TranscodeQueue WHERE Status='Pending'` is identical immediately before and after the migration runs.

### E. Observability

12. The `ClaimNextPendingTranscodeJob` log entry on a successful claim is extended to include: `WorkerName`, `WorkerTags`, `JobId`, `ProfileName`, `RequiredTags`, `PreferredTags`, `MatchScore` (the count used in the sort). One log row per claim. Verifiable: induce a tagged-claim, query `SELECT Message FROM Logs WHERE FunctionName='ClaimNextPendingTranscodeJob' ORDER BY TimeStamp DESC LIMIT 1`, confirm all seven fields appear.

13. The Activity dashboard active-jobs row (already showing Worker, Target resolution per the activity-dashboard feature) does **not** need a Tags column. Tags live on workers, not on jobs in flight; the worker tile shows them. Adding to the active-jobs row would be redundant and clutter a dense table. Verifiable: visual inspection.

### F. Flow doc update

14. `transcode.flow.md` Stage 2.2 ("Claim job atomically") is updated to reflect the new ORDER BY structure. The doc shows the routing-aware ORDER BY clause and a one-paragraph note: "Workers and profiles can carry tags; required tags filter rows out of a worker's view, preferred tags reorder them. Untagged everywhere = today's behavior." Verifiable: `git diff transcode.flow.md` shows the Stage 2.2 row updated.

15. **[BUG-0043] An NVENC-capable worker (e.g. i9 with `nvenccapable=TRUE`) does not claim CPU-only profile jobs (`Profiles.usenvidiahardware=0`) when a CPU profile would otherwise be the next-eligible row.** Today the claim ordering is strictly `Priority DESC, DateAdded ASC` with no codec-awareness, so the moment a CPU-profile row reaches the top of the queue, an NVENC worker grabs it and burns 20+ minutes of GPU-worker compute on a job the CPU-only workers (wakko / dot) could have done. Fixed (via C1–C6) means: tag i9 with `nvenc` (or similar), set the SVT-AV1 P6 FG8 CRF36 >720p profile's `PreferredWorkerTags=cpu` (or `RequiredWorkerTags=cpu`), and confirm via a synthetic test queue holding only one CPU-profile row that wakko (or dot) claims it within one poll tick while i9 sits idle if no NVENC work is pending. The interim operator workaround until this ships: queue CPU jobs at a lower `Priority` than NVENC jobs so the i9 exhausts NVENC work first.

## Status

DRAFTED -- awaiting operator approval.

### Progress

- [x] Read prior issues (`memory/KNOWN-ISSUES.md` -- no related entry)
- [x] Surveyed existing claim path (`DatabaseManager.ClaimNextPendingTranscodeJob`, `transcode.flow.md` Stage 2.2)
- [x] Confirmed activity-dashboard-improvements covers the worker-tile surface so this feature only needs to slot tags onto an already-redesigned tile
- [x] Drafted feature doc (this file)
- [ ] Operator approval
- [ ] Implement A1-A3 (Workers + Profiles columns, migration script)
- [ ] Implement B4-B6 (claim query rewrite + parameter plumbing in `ProcessTranscodeQueueService.GetNextJob` to pass `WorkerTags`)
- [ ] Implement C7-C9 (Activity tile tag row, `POST /Workers/<name>/Tags` endpoint, Profiles edit UI inputs)
- [ ] Implement E12 (extended claim log)
- [ ] Implement F14 (transcode.flow.md update)
- [ ] Smoke test: tag I9-2024 as `fast`; create a profile with `RequiredWorkerTags=fast`; queue a job under that profile; confirm only I9-2024 claims it; switch the profile to `PreferredWorkerTags=fast` and queue again; confirm I9-2024 wins the race when polling but other workers can claim if I9 is busy

NEXT: operator approval to start. Recommended implementation order: A (schema) -> B (claim query, smoke-tested standalone via SQL) -> C (UI) -> E/F (observability + docs). Worker code change is small (just pass `Workers.Tags` and `AcceptsInterlaced` into the call) -- the bulk of the work is the SQL and the UI.

## Scope

```
Repositories/DatabaseManager.py                              -- ClaimNextPendingTranscodeJob query rewrite, parameter plumbing
Features/TranscodeQueue/TranscodeQueueRepository.py          -- vertical-slice copy, same rewrite for consistency (legacy DatabaseManager is the live path)
Features/TranscodeJob/ProcessTranscodeQueueService.py        -- pass Workers.Tags into GetNextJob/ClaimNextPendingTranscodeJob
Features/TeamStatus/TeamStatusController.py                  -- new POST /Workers/<name>/Tags endpoint; /Workers payload includes Tags
Features/Profiles/ProfileRepository.py                       -- read/write PreferredWorkerTags + RequiredWorkerTags
Features/Profiles/ProfilesController.py                      -- accept tag fields in profile edit POST
Templates/ShowSettings.html or Templates/<profile-edit>.html  -- UI inputs (file resolution at implementation time)
Templates/Activity.html                                      -- worker tile Tags row + Edit Tags modal
Scripts/SQLScripts/AddWorkerRoutingColumns.py                -- NEW. Idempotent ADD COLUMN IF NOT EXISTS for Workers.Tags, Profiles.PreferredWorkerTags, Profiles.RequiredWorkerTags
transcode.flow.md                                            -- Stage 2.2 ORDER BY structure + one-paragraph note
```

## Files

| File | Role |
|------|------|
| `Repositories/DatabaseManager.py` | Rewrite `ClaimNextPendingTranscodeJob` to accept `WorkerTags` parameter, add LEFT JOINs to MediaFiles + Profiles, apply the required-tag filter and preferred-tag scoring in ORDER BY. The `_TagMatchScoreSql` helper builds the `CASE WHEN ... END` from the tag columns and worker tags array literal. |
| `Features/TranscodeQueue/TranscodeQueueRepository.py` | Mirror the rewrite for the dead-code copy. |
| `Features/TranscodeJob/ProcessTranscodeQueueService.py` | At `GetNextJob`, read `self.WorkerTags` (loaded from Workers row at startup, refreshed by capability poller every 60s so a tag change applies without restart) and pass into the claim call. |
| `Features/TeamStatus/TeamStatusController.py` | New `POST /Workers/<name>/Tags` endpoint -- normalize input, UPDATE Workers.Tags. Extend `/Workers` GET payload with `Tags`. |
| `Features/Profiles/ProfileRepository.py` and `ProfilesController.py` | Persist + serve PreferredWorkerTags + RequiredWorkerTags. |
| `Templates/ShowSettings.html` | Add two text inputs to the Profile edit form. (If profiles edit somewhere else, follow the actual surface -- check at implementation time.) |
| `Templates/Activity.html` | Worker tile gains a `Tags` row and an "Edit Tags" link triggering a Bootstrap modal that POSTs to `/Workers/<name>/Tags`. |
| `Scripts/SQLScripts/AddWorkerRoutingColumns.py` | NEW. Three idempotent `ALTER TABLE ... ADD COLUMN IF NOT EXISTS`. |
| `transcode.flow.md` | Stage 2.2 ORDER BY updated; one-paragraph routing note added. |

## Deviation from conventions

The query in criterion B4 mentions the SQL shape directly. Normally criteria avoid implementation detail, but the routing rule **is** the SQL clause -- describing it in prose only would lose the precision needed for review. Each behavioural assertion (filter on required, sort on preferred, untagged behaves as today) is also stated independently and is verifiable without reading the SQL.
