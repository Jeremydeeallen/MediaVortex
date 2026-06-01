# Active Jobs Table -- Filter and Sort

**Slug:** active-jobs-filter-sort

## What It Does

Adds client-side filtering by worker/machine name and column-header sorting to the Active Jobs table on the Activity page. Enables the operator to quickly find a specific machine's jobs when the fleet is running many simultaneous transcodes, and to sort by any column (file, type, worker, size, progress, FPS, speed, ETA) to identify bottlenecks.

## Surface

- `Templates/Activity.html` -- Active Jobs table (the `#ActiveJobsTable` card)
- No backend changes required (all data is already present in the API response)

## Scope

- Templates/Activity.html (JS rendering logic for the Active Jobs table)

## Success Criteria

1. A text input filter appears above the Active Jobs table. Typing a worker name (e.g. "larry") hides all rows whose Worker column does not contain the typed string (case-insensitive substring match). Clearing the filter restores all rows. The filter persists across auto-refresh cycles (typed value is not lost when the table re-renders).

2. Clicking any column header in the Active Jobs table sorts the table rows by that column. A second click on the same header reverses the sort direction. A visual indicator (arrow/chevron) on the active sort column shows the current direction (ascending/descending).

3. Sorting by numeric columns (Size, Progress, FPS, Speed) uses numeric comparison, not string comparison. A row with 1.2 GB sorts above 800 MB; a row at 95.0% sorts above 12.3%.

4. The default sort (no header clicked) remains the server-provided order (Priority DESC, DateAdded ASC -- the claim order). Clicking any header overrides this until the page is reloaded.

5. The filter and sort state survive auto-refresh (the 5-second polling cycle). When new data arrives, the current filter text and sort column/direction are re-applied to the fresh data. No flicker or scroll-position jump.

6. The footer row (total Size, total FPS) reflects only the visible (filtered) rows. If the filter hides 2 of 4 jobs, the footer sums only the 2 visible ones.

7. The VMAF row (if present) is included in filter/sort like any other row. Filtering by a machine name that has a VMAF job shows it; sorting by Type places the VMAF row among others alphabetically.

## Status

DRAFTED -- awaiting approval.

### Progress

- [ ] 1. Add filter input above Active Jobs table
- [ ] 2. Implement client-side filter logic with auto-refresh persistence
- [ ] 3. Add sort click handlers to column headers
- [ ] 4. Implement multi-type sort (numeric for Size/Progress/FPS/Speed, string for others)
- [ ] 5. Add sort direction indicator (chevron) to active header
- [ ] 6. Update footer to sum only visible/filtered rows
- [ ] 7. Verify VMAF row participates in filter/sort

## Files

- Templates/Activity.html
