# Timezone Frontend Audit

## What It Does

Verifies that **every** user-visible timestamp in the MediaVortex web UI -- and
every server-side aggregation that creates time *buckets* the user sees -- honors
the configured display timezone (`SystemSettings.DisplayTimezone`).

The foundation feature (`display-timezone.feature.md`, 7 steps, completed 2026-05-08)
established the pipeline: UTC in DB, Flask UtcJsonProvider serializes with `Z`
suffix, JS `formatTime()` converts on render. **This audit closes the gap that
foundation work left open**: criteria 5-6 in that doc said "sweep templates"
without enumerating each surface, so several remained un-swept and the user
called out the Queue page rendering wrong + the Savings-by-Day chart bucketing
on UTC days instead of the configured TZ.

## Concern

Dogfood -- self-discovered after the foundation feature shipped. Surfaces below
are enumerated from a full grep of the codebase performed 2026-05-08.

## Success Criteria

### A. Tables that render timestamps from JSON

Each criterion below should be verified against a live page after WebService
restart with `SystemSettings.DisplayTimezone='America/Chicago'`. Pass = the
displayed timestamp matches the expected Chicago-local time corresponding to
the UTC value in the underlying DB row, with the short TZ abbreviation visible
where the format includes it.

1. **Queue page** (`Templates/Queue.html`): the `Date Added` column on every
   queue row renders in the configured TZ. The `formatDate()` helper already
   calls `window.formatTime`; criterion validates that the helper actually
   resolves at render time (i.e. `timezone.js` is loaded and `window.MV_TIMEZONE`
   is injected). Refresh the page; row timestamps should match the configured
   TZ, not the browser locale.
2. **Activity page** (`Templates/Activity.html`): every timestamp column on
   active and recent transcodes renders in the configured TZ. The `FormatDate`
   helper at the top of the page uses `window.formatTime`; verify the rendered
   times shift when the setting changes.
3. **Operations page** (`Templates/Operations.html`): the recent-attempts
   table, failure-list table, and stuck-job table all render their date
   columns through `window.formatTime`. Three sites total (lines ~686, ~757,
   ~840 pre-sweep -- now all use `formatTime`).
4. **SQLQueries page** (`Templates/SQLQueries.html`): the failure-list and
   stuck-job tables render dates through `window.formatTime`.
5. **Optimization page** (`Templates/Optimization.html`): the last-seen
   filter column and Jellyfin-device "last activity" column render through
   `window.formatTime`.
6. **FileScanning + Settings pages**: `ContinuousScanLastCompleted` element
   renders through `window.formatTime` with the `time` format preset.

### B. Chart axes (Chart.js)

7. **Savings by Day chart** (`Templates/Status.html`): the X-axis labels are
   rendered in the configured display TZ. Currently the labels come from the
   server as ISO date strings produced by `DATE(ta.CompletedDate)` -- this
   buckets in UTC. After the fix, labels respect the configured TZ so a
   transcode finishing 2026-05-08 23:30 Chicago time appears under the
   `2026-05-08` bucket, not `2026-05-09`.
8. **Any other Chart.js chart with a time/date axis**: same rule. (At time of
   audit, the SavingsChart on Status.html is the only one found. If new charts
   are added, they must follow the same pattern.)

### C. Server-side date bucketing (SQL)

9. **`GET /api/TeamStatus/SavingsByDay`** (`Features/TeamStatus/TeamStatusController.py:193-227`):
   the `GROUP BY DATE(ta.CompletedDate)` clause is replaced with
   `GROUP BY DATE(ta.CompletedDate AT TIME ZONE 'UTC' AT TIME ZONE :tz)` (or
   the equivalent psycopg2 parameterization), where `:tz` is read from
   `SystemSettings.DisplayTimezone`. Day-bucket boundaries align with the
   user's TZ midnights, not UTC midnights.
10. **Any other endpoint that returns date-bucketed aggregations**: same rule.
    Audit performed 2026-05-08 found only `SavingsByDay`. Future
    aggregation endpoints must apply the same pattern (see `## Pattern`
    section below).

### D. Static / pipeline pieces

11. **The navbar clock** (`Templates/Base.html` + `static/js/timezone.js`):
    renders the current time in the configured TZ, ticks every second, shows
    a short TZ abbreviation, has a tooltip pointing at `/settings`.
    (Implemented at commit 9e28558; this criterion is verification.)
12. **Server-rendered Jinja `strftime` calls**: there are zero hits as of
    2026-05-08 audit. Criterion locks that in: any new template that calls
    `value.strftime(...)` MUST be replaced with the `<span class="js-tz"
    data-utc="..." data-fmt="...">UTC fallback</span>` markup before merging.
13. **`<input type="datetime-local">` filter inputs**: there are zero hits as
    of 2026-05-08. Criterion locks that in: any new datetime-local input MUST
    convert local-naive value to a UTC ISO string before sending to the API
    (helper to be added: `localToUtcIso()` next to `formatTime` in
    `static/js/timezone.js`).
14. **CSV / report exports**: a grep finds no current CSV-export endpoint that
    serializes datetimes. Criterion locks that in: any future CSV export must
    format datetimes server-side using `AT TIME ZONE` against the configured
    DisplayTimezone, and the column header must include the TZ name (e.g.
    `"Completed (America/Chicago)"`).

### E. Timezone change propagation

15. **Refresh-only update**: changing `SystemSettings.DisplayTimezone` and
    refreshing the browser causes the displayed values on every page in
    sections A and B above to shift by the new offset, with no other
    configuration step required (other than the documented WebService
    restart that flushes the per-process cache established in the foundation
    feature).

## Status

IN PROGRESS

### Progress

- [x] Surface inventory complete (this doc enumerates each one)
- [x] Foundation feature (`display-timezone.feature.md`) shipped: UtcJsonProvider, MV_TIMEZONE injection, formatTime helper, table sweep, datetime.now() audit
- [ ] Step A1-A6 (table renderings): verify post-restart on a live page each
- [ ] Step A1 specifically: investigate why user reports Queue page "not even
      working"; if WebService was restarted with current code, dig deeper
- [ ] Step B7 (Savings chart): the chart consumes labels from the API; the
      fix lives in step C9
- [x] Step C9 (SavingsByDay SQL): `GET /api/TeamStatus/SavingsByDay` reads
      DisplayTimezone from SystemSettings and buckets via
      `DATE(ta.CompletedDate AT TIME ZONE 'UTC' AT TIME ZONE :tz)`. Validated
      against real data: pre-fix had a single "2026-05-08 UTC" bar mixing 45
      May-7-Chicago jobs with 93 May-8-Chicago jobs; post-fix the bars match
      Chicago-day rollups exactly (34/28/75/93 etc.).
- [ ] Step C10 enforcement: add a one-line note to CLAUDE.md or the
      project conventions reminding future authors of the pattern
- [ ] Step D11 (navbar clock): visual verify post-restart
- [ ] Step D13 (datetime-local helper): add `localToUtcIso(localValue)` to
      `static/js/timezone.js` even though no input currently needs it -- so
      future authors have a clear path to the right pattern
- [ ] Step E15: end-to-end test by changing DisplayTimezone to a non-default
      value, restarting WebService, refreshing each page, and confirming the
      shift

## Pattern (for future authors)

When adding a new aggregation endpoint that returns rows bucketed by day,
hour, or any time period:

```python
# WRONG: bucket by UTC day
GROUP BY DATE(ta.CompletedDate)

# RIGHT: bucket by configured display TZ day
GROUP BY DATE(ta.CompletedDate AT TIME ZONE 'UTC' AT TIME ZONE %s)
```

The `%s` parameter comes from `SystemSettings.DisplayTimezone`. The double
`AT TIME ZONE` is the idiomatic PostgreSQL pattern for converting a naive
`TIMESTAMP` (which we know is UTC by convention) to a target TZ before
truncating. Don't use `DATE_TRUNC('day', col)` without the conversion --
same UTC-bucket bug.

When adding a new template timestamp display:

```html
<!-- WRONG: server formats in whatever TZ Python decided -->
<span>{{ value.strftime('%Y-%m-%d %H:%M') }}</span>

<!-- RIGHT: js-tz markup with UTC fallback for no-JS gracefulness -->
<span class="js-tz" data-utc="{{ value.isoformat() }}Z" data-fmt="datetime">
  {{ value.strftime('%Y-%m-%d %H:%M') }} UTC
</span>
```

For AJAX-built rows in JS:

```javascript
// WRONG: browser locale, ignores configured TZ
const dt = new Date(row.CompletedDate).toLocaleString();

// RIGHT: configured TZ via the helper
const dt = window.formatTime(row.CompletedDate, 'datetime');
```

## Scope

```
Templates/Queue.html
Templates/Activity.html
Templates/Operations.html
Templates/SQLQueries.html
Templates/Optimization.html
Templates/FileScanning.html
Templates/Settings.html
Templates/Status.html
Templates/Base.html
Features/TeamStatus/TeamStatusController.py
Features/SystemSettings/display-timezone.flow.md
static/js/timezone.js
```

## Files

| File | Role |
|------|------|
| `Features/TeamStatus/TeamStatusController.py` | `GetSavingsByDay` -- needs `AT TIME ZONE` |
| `Templates/Status.html` | SavingsChart consumes the bucketed labels |
| `Templates/Queue.html` | `formatDate()` helper -- live verify post-restart |
| `Templates/Activity.html` | `FormatDate()` helper -- live verify post-restart |
| `Templates/Operations.html` | 3 inline sites already converted -- live verify |
| `Templates/SQLQueries.html` | 2 inline sites already converted -- live verify |
| `Templates/Optimization.html` | 2 inline sites already converted -- live verify |
| `Templates/FileScanning.html`, `Templates/Settings.html` | scan-status time -- live verify |
| `Templates/Base.html` | navbar clock element + `window.MV_TIMEZONE` injection |
| `static/js/timezone.js` | `formatTime`, `formatRelative`, `applyTimezoneSweep`, `startNavClock`, future `localToUtcIso` |
| `Features/SystemSettings/display-timezone.flow.md` | Flow doc gets a new "Server-side date bucketing" stage covering the SQL pattern |
