# Feature: Manual Override Replace (force-replace a Requeue'd attempt with statistics)

## What It Does

Adds an operator-driven path to replace a transcoded file whose `Disposition='Requeue'` (or `'NoReplace'`) decision the user wants to override. The action transitions the attempt to `Disposition='BypassReplace'`, records who/when/why on the attempt, and runs the same `FileReplacementBusinessService.ProcessFileReplacement` path that an auto-approved attempt would.

Every override is recorded in a new `ManualOverrideEvents` audit table so trending statistics ("we're force-overriding 30% of Sister Wives attempts -- the VMAF gate is mis-calibrated for that show") are queryable without log grep.

## Concern

The bimodal VMAF bug (`KNOWN-ISSUES.md`) means VMAF score is unreliable for MKV sources. Operator visually verifies via the comparison slider, judges "this looks fine, keep it", and currently has no way to force the replacement. Today the only path is to re-queue with a different CRF, hoping for a higher score. With the override action, the operator can act on visual evidence directly.

Without trend statistics, repeated overrides become a tribal-knowledge problem -- nobody can answer "how often do we override?" or "which shows trigger the most overrides?" The audit table makes the trend a first-class operator surface.

## Surface

UI button on the `/VmafCompare` page (and any attempt-detail surface that shows VMAF/disposition) -- visible only when `Disposition IN ('Requeue','NoReplace')` and the staged output still exists on disk. Button label: "Replace anyway (override)". Click opens a modal that requires a free-text reason (>=10 chars) before submission.

API endpoint: `POST /api/QualityTest/OverrideReplace` with body `{TranscodeAttemptId, Reason}`. Returns `{Success, NewDisposition, ReplacementResult}`.

Stats surface: `/Activity` page gains an "Override trends" panel showing count-per-day for last 30 days, broken out by `ReasonCategory` (derived from Reason text via a small keyword bucketing).

## Success Criteria

1. `ManualOverrideEvents` table exists with columns `(Id, TranscodeAttemptId, MediaFileId, OldDisposition, NewDisposition, Reason, ReasonCategory, OverriddenBy, OverriddenAt)`. `\d ManualOverrideEvents` shows the columns; FK on `TranscodeAttemptId` references `TranscodeAttempts(Id)`.

2. `POST /api/QualityTest/OverrideReplace` with a valid attempt id whose current `Disposition IN ('Requeue','NoReplace')` returns `Success=true`, sets `TranscodeAttempts.Disposition='BypassReplace'`, sets `DispositionReason` to `'manual-override: <truncated reason>'`, and creates one `ManualOverrideEvents` row. Verifiable: integration test invokes the endpoint, queries both tables, asserts the columns updated and a row appeared.

3. Same endpoint refuses (HTTP 400, `Success=false`, descriptive Message) when the attempt's current `Disposition` is `Replace`, `BypassReplace`, `Discard`, or NULL. No DB state changes. Verifiable: integration test invokes against each forbidden state and asserts no `ManualOverrideEvents` row was created.

4. Same endpoint refuses (HTTP 400) when `Reason` is missing or has fewer than 10 characters. No DB state changes. Verifiable: integration test posts an empty and a 5-char reason and asserts rejection.

5. After a successful override, the existing `FileReplacementBusinessService.ProcessFileReplacement` flow runs: source archived to `MediaFilesArchive`, transcoded output moved to the canonical source path, MediaFiles re-probed, `TranscodeAttempts.FileReplaced=true`. Verifiable: integration test on a real transcoded staged file asserts the four post-conditions hold after the endpoint returns.

6. The override path uses the SAME `ProcessFileReplacement` entry point as auto-approved replacements -- no duplicate copy of the replacement logic. Verifiable: `grep -rn "ProcessFileReplacement" --include="*.py"` shows the override endpoint calling it directly; no parallel `_ReplaceFileForOverride` function exists.

7. `ReasonCategory` is derived deterministically at insert time from the free-text reason via a documented bucketing rule (e.g. keywords "looks fine"/"visual"/"bimodal" -> `VisualOverride`; "wrong cutoff"/"threshold low" -> `ThresholdComplaint`; else `Uncategorized`). Verifiable: unit test seeds a row per category keyword and asserts the column value; the bucketing rule lives in one function whose tests cover every documented category.

8. The `/Activity` page renders an "Override trends" panel showing override count per day for the last 30 days, with stacked bars by `ReasonCategory`. When zero overrides exist, the panel renders a "No overrides recorded" empty state rather than disappearing. Verifiable: load `/Activity` after creating overrides via the endpoint; visually confirm the bars; load with zero overrides; visually confirm the empty state.

9. The same panel exposes a click-through to the underlying override list (filterable by date range, category, and show via folder prefix on `RelativePath`). Verifiable: clicking a bar segment routes to the list with the date+category pre-filtered; the URL is bookmarkable.

10. Operator audit query is single-statement and documented in the feature doc: `SELECT date_trunc('day', OverriddenAt) AS Day, ReasonCategory, COUNT(*) FROM ManualOverrideEvents WHERE OverriddenAt > NOW() - INTERVAL '30 days' GROUP BY 1, 2 ORDER BY 1 DESC, 2`. Verifiable: running that query on a seeded dataset returns the same counts as the rendered panel.

11. The UI button is hidden -- not just disabled -- when the attempt is in a state where override is forbidden (criterion 3). Disabled-but-visible buttons get clicked anyway and produce confusing 400 errors. Verifiable: load `/VmafCompare` against an attempt with `Disposition='Replace'`; the override button must not be present in the DOM.

12. A `ManualOverrideEvents` row is immutable after insert -- there is no UPDATE or DELETE endpoint, and the table has no `LastModified` column. An override cannot be "un-overridden"; if the operator regrets it, they queue a fresh transcode. Verifiable: code search for `UPDATE ManualOverrideEvents` and `DELETE FROM ManualOverrideEvents` returns no production code matches.

## Status

Draft -- awaiting criteria approval before any code.

### Progress

- [ ] Migration: create `ManualOverrideEvents` (Id PK, FK to TranscodeAttempts, audit columns, index on `(OverriddenAt, ReasonCategory)`)
- [ ] `BucketOverrideReason(Reason) -> ReasonCategory` pure function + unit tests
- [ ] `POST /api/QualityTest/OverrideReplace` endpoint (validation -> dispatch -> ProcessFileReplacement -> audit insert)
- [ ] Wire UI button into `/VmafCompare` attempt-detail (visibility guarded by current Disposition)
- [ ] Activity panel: "Override trends" stacked bar (30-day window, by ReasonCategory)
- [ ] Activity panel click-through to filtered override list
- [ ] Integration tests for all 12 criteria
- [ ] Update `transcode.flow.md` Stage 6 disposition table with the manual-override row

## Scope

`Features/QualityTesting/**`
`Features/Activity/**`
`Features/FileReplacement/FileReplacementBusinessService.py` (read-only -- called from new endpoint)
`Scripts/SQLScripts/AddManualOverrideEvents.py` (migration)
`Templates/VmafCompare.html`
`Templates/Activity.html`

## Files

- `Features/QualityTesting/QualityTestController.py` -- add `OverrideReplace` endpoint
- `Features/QualityTesting/ManualOverrideBusinessService.py` -- NEW: validation, dispatch, audit insert, reason bucketing
- `Features/QualityTesting/ManualOverrideRepository.py` -- NEW: ManualOverrideEvents CRUD (insert-only)
- `Features/QualityTesting/Models/ManualOverrideEventModel.py` -- NEW
- `Features/Activity/ActivityController.py` -- add `/api/Activity/OverrideTrends` and `/api/Activity/OverrideList`
- `Features/Activity/ActivityViewModel.py` -- assemble the trend data
- `Scripts/SQLScripts/AddManualOverrideEvents.py` -- migration script
- `Templates/VmafCompare.html` -- override button + modal
- `Templates/Activity.html` -- override trends panel
- `transcode.flow.md` -- add manual-override row to Stage 6 disposition table
