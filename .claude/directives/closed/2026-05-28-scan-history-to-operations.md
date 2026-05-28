# Current Directive

**Set:** 2026-05-28
**Closed:** 2026-05-28
**Status:** Closed -- Success
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

Active 2026-05-28 -- shipped (commit 01380f0); pending operator visual confirmation on /Operations + /Activity.

Shipped:
- [x] 1. `Templates/Activity.html`: removed `RecentScansStrip` DOM, `RenderRecentScans` JS, and the call site in `RenderActiveJobs`. Active Scans block stays for in-flight.
- [x] 2. `GET /api/SQLQueries/GetRecentScanRuns` added to `SQLQueriesController.py`. Pattern filter applied to BOTH Completed and Failed rows because interrupted scans are currently flagged Completed with a housekeeping ErrorMessage (known quirk per FileScanning.flow.md). Stopped status excluded entirely.
- [x] 3. Recent Scans card added to `Templates/Operations.html` between Recent Failures and Stuck Jobs, with `LoadRecentScans` / `RenderRecentScans` JS following the Recent Successes / Recent Failures pattern. Card colored bg-info to distinguish from green successes + red failures.
- [x] 4. Wired into both page-load (constructor) and Refresh button (`RefreshPage`).
- [x] 5. WebService restarted twice (initial endpoint test + filter refinement after seeing Completed-with-housekeeping-ErrorMessage leak through). Final smoke-test against live data confirms only `errormessage: null` rows appear.
- [x] 6. `FileScanning.flow.md` Surface section: /Activity described as in-flight only; /Operations carries scan history; pattern list and "real failure" classification documented with the rationale + the "add a substring here if noise appears" note.

Verified by operator. Closed Success 2026-05-28.

Doc supersession sweep at closure:
- Deleted `Features/FileScanning/scanning-on-activity-page.feature.md` -- fully superseded draft; the active-scan-visibility design (and its evolution through three directives) is captured by `FileScanning.flow.md` Surface section plus the closed-directive archive.
- Removed dead `_BuildRecentScans` + `RecentScans` payload key from `Features/TeamStatus/TeamStatusController.py`; the /Activity UI no longer consumes it (Operations uses `/api/SQLQueries/GetRecentScanRuns`).
- Updated `Features/FileScanning/ad-hoc-drive-scans.feature.md` progress checklist entries 10-11 to point at the closed directives + the Operations Recent Scans card instead of the deleted draft.
- Updated `Features/FileScanning/FileScanning.feature.md` criterion 17: removed `[BUG]` flag (closed by the two directives), updated phase enum to the shipped values (`SizeSurvey / Walking / Reconciling / Probing / Completing`), updated heartbeat-write column list to match the producer side, removed the `scanning-on-activity-page.feature.md` cross-reference.
