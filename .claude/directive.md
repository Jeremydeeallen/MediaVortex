# Current Directive

**Set:** 2026-05-28
**Status:** Active
**Replaces:** `directives/closed/2026-05-28-scan-largest-first.md` (closed Success)

## Outcome

Scan history lives on `/Operations` the same way transcode and VMAF history does -- one place to look for "what's run, what's failed, what succeeded." The `/Activity` page stops carrying a Recent Scans strip because that's not where activity history belongs; activity surfaces in-flight work, history surfaces on Operations. When the operator looks at scan failures, they see real failures only -- not the noise from admin housekeeping (zombie clears, application restarts, deploy-time stuck cleanups, operator soft-stops). The classification of "real failure" is defined by `Status='Failed'` with an `ErrorMessage` that doesn't match a small, explicit set of housekeeping patterns; everything else is omitted from operator views.

## Acceptance Criteria

1. **`/Activity` Recent Scans strip removed.** The `<div id="RecentScansStrip">` block and `RenderRecentScans` function come out of `Templates/Activity.html`. `_BuildRecentScans` stays in the controller for now (Operations uses it via a different endpoint) but is no longer rendered on /Activity. Verifiable: `/Activity` has no "Recent scans" section anywhere.

2. **`/Operations` gains a "Recent Scans" card.** Same visual shape as the existing "Recent Successes" / "Recent Failures" transcode cards -- a card with header, last N entries listed below. Defaults to the last 15 entries. Each entry shows: drive (RootFolderPath), worker, status icon (Completed=green / Failed=red), duration, dispositions (+N ~U -D), end time relative ("4m ago"). Verifiable: visual inspection -- card present, entries readable.

3. **"Real failure" filter.** Recent Scans on Operations includes:
   - `Status='Completed'` -- always
   - `Status='Failed'` with `ErrorMessage NOT NULL` AND not matching the housekeeping patterns below
   And EXCLUDES:
   - `Status='Stopped'` -- soft-stop is an operator action, not a failure
   - `Status='Failed'` with `ErrorMessage` matching any of: `%Application restarted%`, `%Zombie%`, `%pre-redeploy%`, `%Stuck scan cleaned by StuckJobDetectionService%`, `%post-deploy mass clear%`, `%Stopped pre-redeploy%`
   Verifiable: SQL preview against current data -- the existing zombie / stuck-cleanup / application-restarted rows do NOT appear in the Operations Recent Scans card.

4. **Sort + limit contract.** Recent Scans on Operations is ordered by `EndTime DESC`, limit configurable via query param `?limit=N` (default 15, max 50). Verifiable: hit endpoint with limit=5, get exactly 5; limit=100, get 50 (capped).

5. **New endpoint `GET /api/SQLQueries/GetRecentScanRuns`** lives in `Features/SQLQueries/SQLQueriesController.py` next to `GetRecentSuccesses`. Same JSON shape: `{Success, Results: [...], Count}`. Each Result entry: `RootFolderPath, WorkerName, Status, StartTime, EndTime, DurationSec, NewFiles, UpdatedFiles, DeletedFiles, ProcessedFiles, ErrorMessage`. Verifiable: GET the endpoint, response matches shape.

6. **Refresh button on the Recent Scans card** calls the endpoint and re-renders. Same pattern the Recent Successes / Recent Failures cards use. Verifiable: visual click + observe re-fetch.

7. **Doc sweep on close.** Update `FileScanning.flow.md` Surface section to point Scan history → `/Operations` (not `/Activity`). Drop the obsolete `RecentScansStrip` mention. Add a one-paragraph note explaining the "real failure" classification so a future reader can extend the pattern set without re-discovering the rationale.

## Out of Scope

- Re-rendering or filtering the Operations transcode-failure card. Transcode failures already use TranscodeAttempts, separate pipeline, separate doc.
- A scan-row click-through / detail modal. Card shows summary lines only; if the operator wants details they hit `/SQLQueries`.
- Cleaning up the existing noise rows in `ScanJobs`. The filter handles them at query time; bulk delete is a separate operator decision.
- Schema changes. No new columns -- the filter is pattern-based against the existing `ErrorMessage` column.

## Constraints

- Pattern list lives in ONE place (the controller query) so future additions are a single-file edit.
- No new pollers on `/Operations`; card loads on page load + on Refresh button click. Same shape as the existing cards.
- `/Activity` stops touching scan history entirely -- the strip element is removed from the DOM, not just hidden.
- Empty-state for the Operations card: `<em>No recent scans</em>` when zero results, matching the transcode cards' empty state.

## Escalation Defaults

- If the pattern list misses a real-world admin message (operator sees noise re-appear later), add it to the list -- not a re-architect. The directive accepts that the list will grow over time.
- Risk tolerance: low. UI + read-only endpoint; no producer-side changes; trivial rollback.

## Engineering Calls Already Made

- Recent Scans goes on /Operations as a third card alongside Recent Successes + Recent Failures, NOT folded into either. Scan completions have a different shape (drive, file counts, duration) than transcode completions (savings %, profile, attempt).
- The "real failure" filter is a pattern list -- not a new `IsRealFailure` column -- because the symptom is small (today's debug noise) and a schema change would be wrong-scoped.
- The /Activity strip is removed entirely, not feature-flagged. CEO mode + tight criteria -- no need for a toggle.

## Status

Active 2026-05-28 -- next step: implement.

Plan:
1. Remove `RecentScansStrip` DOM block + `RenderRecentScans` from `Templates/Activity.html`. Stop calling RenderRecentScans from RenderActiveJobs.
2. Add `GetRecentScanRuns` endpoint to `SQLQueriesController.py` with the pattern filter applied via SQL `NOT ILIKE` chain.
3. Add Recent Scans card markup + JS loader (`LoadRecentScans` / `RenderRecentScans`) to `Templates/Operations.html` -- mirror the Recent Successes / Recent Failures card structure.
4. Wire the card into the page-load + Refresh sequence in `operationsManager`.
5. Restart WebService, verify on /Operations + /Activity in browser.
6. Doc sweep: `FileScanning.flow.md` Surface section.
