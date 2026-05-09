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
- [x] Implement `CalculatePriority(MediaFile, TargetVideoKbps, TargetAudioKbps)` rewrite -- pure function with kbps params; callers pass them in. Fallback path with loud `LogWarning` when inputs missing.
- [x] Update profile-aware callers: `CreateQueueItemFromMediaFile` (passes Threshold bitrates directly), `CreateQueueItemFromMediaFileWithProfile` (looks up via `GetProfileSettingsForTargetResolution`). Remux + SubtitleFix + Simple paths intentionally use the fallback.
- [x] Update server-side validation in `TranscodeQueueController` (PrioritizeJob and AddJob: 100 -> 200)
- [x] Update template input bounds + hint text (`Queue.html` PriorityModal + AddJob)
- [x] Update `getPriorityBadgeClass` JS color brackets in `Queue.html` (>=195 red, >=150 yellow, >=75 blue, <75 gray)
- [x] Write `Scripts/SQLScripts/RecalculateQueuePriorities.py` (optional rebalance, dry-run by default; manual-override range 195-200 excluded by query)
- [x] Smoke test PASSED: profile-target path produces 107/136/150/173 across 1.5/4/8/30 GB. Already-efficient files clamp to priority 1. 200 GB worst case caps at 194.
- [x] Close priority-bypass paths (2026-05-09, after operator reported Priority=1076 on a Media-page-added Survivor episode): `SmartPopulateQueue` no longer pre-fills `Priority` in suggestion dicts; `AddSuggestionsToQueue` recomputes via `CalculatePriority` with profile bitrates; `AddJobToQueue` uses the profile-aware queue-item path and caps the manual-bonus at 194 (not 100). `Templates/ShowSettings.html` no longer sends `S.Priority` from the SmartPopulate UI.
- [x] Fix worker claim path (2026-05-09, found while verifying first criterion-11 dogfood): the live atomic claim in `DatabaseManager.ClaimNextPendingTranscodeJob` and the two peek/list paths in `DatabaseManager.GetNextPendingTranscodeJob` + `Features/TranscodeQueue/TranscodeQueueRepository.py` were ordering by `SizeMB DESC, DateAdded ASC` -- Priority was selected but never used. Changed all four queries to `ORDER BY Priority DESC, DateAdded ASC`. `transcode.flow.md:403` Stage 2.2 updated to match. Without this fix the entire feature was a no-op at the worker.
- [x] Queue UI default sort flipped from `SizeMB` to `Priority DESC` (`Templates/Queue.html:202`) so the visible row order matches worker claim order.
- [x] Live verify (DB-confirmed 2026-05-09): live queue inspection on 40 rows showed `MIN=1, MAX=90, AVG=33`, all values in [1,194]; `manual_195_200=0`; recent UI-added rows (Outlander, The Deuce, Project Runway) landed at sensible priorities for their size/profile combos. Two natural Priority=1 examples (Project Runway 720p HDTV-MKV at ~930 MB, already at/below profile target bitrate) confirm savings-clamp-to-zero behavior on the live data.
- [x] Live verify (DB-confirmed 2026-05-09): worker claim path is taking highest-priority items first. Running rows at priorities 90/89/59/54 ahead of 54-priority pending rows -- pre-fix behavior would have ordered by SizeMB and the larger 924+ MB files would have been claimed before the 90-priority Expedition Unknown. Criterion 11 PASSING in production.
- [ ] Live verify (UI only): set a job to 200 manually via the PriorityModal, confirm the API accepts it and the worker claims it next. (Not DB-verifiable; left open until next operator interaction.)
- [ ] Live verify (UI only): badge color brackets render correctly on `/TranscodeQueue` (>=195 red, >=150 yellow, >=75 blue, <75 gray). (Not DB-verifiable; left open until next operator interaction.)
- [x] Fix paginated Queue page sort whitelist (2026-05-09): `Repositories/DatabaseManager.GetTranscodeQueueItemsPaginated` mapped `'Priority' -> 'SizeMB'`, so the JS-driven Priority sort silently degraded to size sort. Fixed; controller + viewmodel defaults also flipped from `SizeMB` to `Priority`.

NEXT: two UI-only verifies remain (priority 200 modal accept + badge colors). Both are non-blocking for downstream features and can be confirmed during the next operator session on the Queue page.

## Scope

```
Features/TranscodeQueue/QueueManagementBusinessService.py    -- CalculatePriority and module constants
Features/TranscodeQueue/TranscodeQueueController.py          -- bounds validation; paginated sort default
Repositories/DatabaseManager.py                              -- GetTranscodeQueueItemsPaginated whitelist
Templates/Queue.html                                          -- modal bounds, color brackets, default sort
Scripts/SQLScripts/RecalculateQueuePriorities.py              -- optional rebalance script (NEW)
transcode.flow.md                                              -- Stage 4 priority subsection
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
