# Queue Priority -- impact-based scoring with manual override window

## What It Does

Replaces the legacy "Priority = `int(SizeMB)`" assignment with an impact-based
score in 1-194, leaving 195-200 reserved for manual user overrides. The new
priority puts the highest-bytes-saved transcodes at the front of the queue
without requiring the operator to think about it; explicit user prioritization
via the existing UI Priority modal still wins.

Drives the `ORDER BY Priority DESC, DateAdded ASC` claim order used by every
worker. No worker code changes required -- only the value written into the
column at queue-population time, plus the Update Priority modal's accepted
range.

## Concern

Dogfood -- the operator surfaced today that every queued file gets
`Priority = file_size_in_MB`, which means already-efficient AV1 files end up
ahead of compressible h264 and the documented 1-100 manual range can never
beat the auto-set values.

## Success Criteria

### A. Score formula

1. `QueueManagementBusinessService.CalculatePriority(MediaFile, ProfileSettings)`
   returns an integer in `[1, 194]`. Inputs are `MediaFile.SizeMB`,
   `MediaFile.DurationMinutes`, `MediaFile.AssignedProfile`,
   `MediaFile.ResolutionCategory`, plus the matching `ProfileThresholds`
   row (`VideoBitrateKbps`, `AudioBitrateKbps`) for that profile and
   resolution. Pure function -- same inputs always produce the same output.

2. The estimated post-transcode size is computed deterministically from the
   profile target bitrate:
   ```python
   target_size_mb = ((video_kbps + audio_kbps) * duration_minutes * 60) / (8 * 1024)
   estimated_savings_mb = max(0, size_mb - target_size_mb)
   ```
   Reading the actual configured profile target (instead of guessing via a
   codec multiplier) means already-efficient sources (av1 at profile bitrate,
   files barely above target) correctly land at savings = 0 -> priority 1,
   and a profile change automatically reflects in the next CalculatePriority
   call without any code change. No `EXPECTED_REDUCTION` or `STANDARD_KBPS`
   constants are needed.

3. Final priority is computed via:
   ```python
   import math
   score = math.log10(estimated_savings_mb + 1)        # 0..5+
   priority = int(round(1 + min(193, (score / 5.0) * 193)))
   priority = max(1, min(194, priority))
   ```
   Log scaling is required: a 30 GB save is ~4x more urgent than a 300 MB
   save, not 100x. Linear scaling on raw size produces a top-heavy queue
   where one BluRay rip suppresses everything else.

4. Fallback when any required input is NULL or missing
   (`DurationMinutes`, `AssignedProfile`, or no `ProfileThresholds` row
   for the resolution category): use `estimated_savings_mb = size_mb * 0.5`
   so the file gets a rough non-zero priority instead of erroring or
   landing at the bottom. The fallback path logs a warning via
   `LoggingService.LogWarning` naming the MediaFileId and which input was
   missing -- per the Phase 2a loud-failure rule, silent fallbacks are
   forbidden.

5. Files with `MediaFile.SizeMB` NULL or 0 receive `Priority = 1` (lowest
   non-zero) so the queue does not error on partial-scan rows.

### B. Manual override window

6. The Priority modal in `Templates/Queue.html` (line 106 input min/max)
   accepts `[1, 200]`, not `[1, 100]` as before. Hint text updated to
   "1-194 = auto / 195-200 = reserved for manual override".

7. The Add Job dialog's Priority input (`Templates/Queue.html` line 134) uses
   the same `[1, 200]` range with the same hint text.

8. `POST /api/TranscodeQueue/PrioritizeJob` server-side validation accepts
   `1 <= NewPriority <= 200`. The `Features/TranscodeQueue/TranscodeQueueController.py`
   bounds check (currently `1 <= NewPriority <= 100`) is updated.

9. `POST /api/TranscodeQueue/AddJob` server-side validation accepts
   `1 <= Priority <= 200` (same site, line 173 today).

10. Auto-assignment never produces a value in `[195, 200]`. Independently
    verifiable: a SQL query `SELECT MIN(Priority), MAX(Priority) FROM TranscodeQueue WHERE ClaimedBy IS NULL`
    after a fresh `PopulateQueue` returns `MIN >= 1, MAX <= 194`.

### C. Queue ordering observable correctness

11. The first item a worker would claim from a fresh queue (per
    `ORDER BY Priority DESC, DateAdded ASC LIMIT 1`) is a high-impact file
    (large h264 or larger). Tested by inspecting `GetNextJob()` output on a
    representative queue.

12. Existing queue items keep their stored Priority. Recalculation only
    applies to NEW queue items going forward, so changing the formula does
    not silently reorder current pending work. A separate one-shot
    `Scripts/SQLScripts/RecalculateQueuePriorities.py` is offered for
    operators who want to rebalance an existing queue manually.

### D. Display alignment

13. The Priority column on `/TranscodeQueue` renders the value as-is (no UI
    change needed; the existing badge logic at `Templates/Queue.html:326`
    works for any positive integer). Verified by visual inspection that
    priorities like 109, 169, 194 render without truncation.

14. `getPriorityBadgeClass(priority)` (the JS color helper, `Templates/Queue.html`
    around line 326) rebrackets to the new range:
    - `>= 195`: red badge ("manual override")
    - `>= 150`: yellow ("high impact")
    - `>= 75`: blue ("medium impact")
    - `< 75`: gray ("low impact")
    Bracket boundaries are calibrated to the score distribution shown in
    `transcode.flow.md` Stage 4 priority section.

## Status

IN PROGRESS

### Progress

- [x] Flow doc extended (`transcode.flow.md` Stage 4, "Priority calculation" subsection)
- [x] Feature doc drafted (this file)
- [x] Refined formula to profile-target (criteria A1-A4 rewritten 2026-05-09)
- [ ] Implement `CalculatePriority(MediaFile, ProfileSettings)` rewrite -- pure function, no DB calls inside the function itself; callers fetch `ProfileThresholds` and pass it in
- [ ] Update every queue-population caller (`PopulateQueue`, `QueueByFolder`, `AddSuggestionsToQueue`, single-file `AddJobToQueue`) to look up `ProfileThresholds` for `(AssignedProfile, ResolutionCategory)` and pass to `CalculatePriority`. Each caller already has access to the MediaFile and profile context.
- [ ] Update server-side validation in `TranscodeQueueController` (PrioritizeJob, AddJob: 100 -> 200)
- [ ] Update template input bounds + hint text (`Queue.html` two sites: PriorityModal + AddJob)
- [ ] Update `getPriorityBadgeClass` JS color brackets in `Queue.html`
- [ ] Write `Scripts/SQLScripts/RecalculateQueuePriorities.py` (optional rebalance, dry-run by default; uses the same `CalculatePriority` + `ProfileThresholds` lookup)
- [ ] Smoke test: PopulateQueue against current MediaFiles, query `MIN/MAX/AVG(Priority)` on the result
- [ ] Live verify: queue a file via UI, confirm assigned priority lands in 1-194 and is reasonable for its size/profile combination
- [ ] Live verify: an already-transcoded av1 file at profile bitrate gets priority = 1 (savings clamps to 0)
- [ ] Live verify: set a job to 200 manually via the modal, confirm the API accepts it and the worker claims it next

NEXT: implement Step 3 (`CalculatePriority` rewrite) once criteria are
explicitly approved per `/n` protocol.

## Scope

```
Features/TranscodeQueue/QueueManagementBusinessService.py   -- CalculatePriority and module constants
Features/TranscodeQueue/TranscodeQueueController.py         -- bounds validation
Templates/Queue.html                                         -- modal/input bounds + JS color brackets
Scripts/SQLScripts/RecalculateQueuePriorities.py             -- optional rebalance script (NEW)
transcode.flow.md                                             -- Stage 4 priority subsection
```

## Files

| File | Role |
|------|------|
| `Features/TranscodeQueue/QueueManagementBusinessService.py` | `CalculatePriority(MediaFile, ProfileSettings)` rewrite from `int(SizeMB)` to log-scaled impact score using the profile's target bitrate. Each queue-population caller looks up the `ProfileThresholds` row once and passes it in -- no module constants needed. |
| `Features/TranscodeQueue/TranscodeQueueController.py` | `PrioritizeJob` endpoint bounds check 1-100 -> 1-200; `AddJob` Priority bounds check |
| `Templates/Queue.html` | PriorityModal `min`/`max` attributes (line 106), AddJob Priority input (line 134), `getPriorityBadgeClass` JS color thresholds (around line 326) |
| `Scripts/SQLScripts/RecalculateQueuePriorities.py` | NEW. Walks current TranscodeQueue, recomputes Priority per the new formula, dry-run by default. Operator opts in to rebalance an existing queue without re-populating |
| `transcode.flow.md` | Stage 4 "Priority calculation" subsection (already added in this `/n` step 4) |

## Deviation from conventions

None. Each criterion is a pass/fail observable from outside the code (DB
query, API call, page inspection, unit-test of the pure function). The
formula constants live in code, not the DB, so changes are reviewable via
git diff.
