# Flow: Display Timezone

**Slug:** display-timezone

## What this flow describes

How a single timestamp value travels from the PostgreSQL database (UTC) to a
user's browser (rendered in the configured display timezone). One conversion
boundary, one fallback path.

## Stages

```
DB (UTC) -> Flask serialization -> JSON over HTTP -> JS parses Date -> formatTime() -> user sees TZ-local
```

## ST1 -- Stage 1: Storage

- All datetime columns in PostgreSQL hold UTC values.
- Cluster `timezone = Etc/UTC` (verified by `SHOW timezone;`).
- `NOW()` and `CURRENT_TIMESTAMP` return UTC timestamps.
- Schema columns are `TIMESTAMP WITHOUT TIME ZONE`. Migration to `TIMESTAMPTZ`
  is deferred (non-blocking; the cluster TZ + convention keep values correct).
- Python writes from worker code use `datetime.now()`. On UTC hosts this
  matches; on non-UTC hosts it does not. Step 6 of the feature replaces these
  with `datetime.now(timezone.utc)` to make the source unambiguous.

## ST2 -- Stage 2: Server-side serialization

- `Core/Web/UtcJsonProvider.UtcJsonProvider` (subclass of Flask's
  `DefaultJSONProvider`) intercepts every datetime in any `jsonify(...)` call.
- Naive datetimes (no tzinfo) are reinterpreted as UTC. Aware datetimes in
  any other zone are converted to UTC via `astimezone()`.
- Output format: `2026-05-08T22:11:19.123456Z` -- ISO-8601 with the explicit
  `Z` suffix so the frontend has zero ambiguity.
- Wired in once during Flask app construction (`WebService/Main.py`). No
  endpoint code needs to know about timezones.

## ST3 -- Stage 3: Template-render path (server-rendered HTML)

- The Flask app registers a `context_processor` that loads
  `SystemSettings.DisplayTimezone` from the DB once per process and caches it
  on `WebServiceApp._CachedDisplayTimezone`. Every `render_template(...)` call
  has `display_timezone` available.
- `Templates/Base.html` emits:
  ```html
  <script>window.MV_TIMEZONE = "{{ display_timezone or 'UTC' }}";</script>
  <script src="{{ url_for('static', filename='js/timezone.js') }}"></script>
  ```
- Templates that show timestamps emit a `<span class="js-tz" data-utc="..."
  data-fmt="...">UTC fallback</span>` element. The text content is the UTC
  fallback shown if JS fails to load.

## ST4 -- Stage 4: Client-side JS

- `static/js/timezone.js` is loaded after the existing JS bundle in `Base.html`.
- On `DOMContentLoaded`, `applyTimezoneSweep()` finds every `.js-tz` element,
  reads `data-utc`, parses with `new Date()`, and rewrites `textContent` via
  `Intl.DateTimeFormat([], {timeZone: window.MV_TIMEZONE, ...})`.
- The element's `title` attribute is set to the original UTC string for
  ops/troubleshooting tooltips.
- Format presets: `full`, `datetime`, `date`, `time`, `short`, `relative`.
  Unknown format names fall back to `full`.

## ST5 -- Stage 5: Dynamic content (AJAX-built rows)

- JS that builds tables/rows from JSON responses calls `formatTime(utcIso, fmt)`
  directly:
  ```javascript
  $row.find('.timestamp').text(formatTime(data.AttemptDate, 'short'));
  ```
- After AJAX inserts new `.js-tz` nodes, call `applyTimezoneSweep(root)` on the
  newly-inserted container so the sweep covers them too.
- For "X minutes ago" relative displays, use `formatRelative(utcIso)` -- it
  computes against the browser's current time (UTC under the hood) and falls
  back to absolute date for ages older than 30 days.

## ST6 -- Stage 6 (extension): Server-side date bucketing -- SQL aggregations

Endpoints that return rows bucketed by day, hour, or any time period must
do the bucketing in the user's configured display timezone, not in UTC.
Otherwise a transcode finishing 23:30 Chicago time (04:30 UTC next day)
falls into the *next* bucket on the chart relative to what the user expects.

The pattern:

```sql
-- WRONG: buckets by UTC day
GROUP BY DATE(ta.CompletedDate)

-- RIGHT: buckets by configured display TZ day
GROUP BY DATE(ta.CompletedDate AT TIME ZONE 'UTC' AT TIME ZONE %s)
```

The `%s` parameter comes from `SystemSettings.DisplayTimezone`. The double
`AT TIME ZONE` is the idiomatic PostgreSQL pattern for converting a naive
`TIMESTAMP` (which is UTC by convention here) to a target TZ before truncating.

Same rule applies to `DATE_TRUNC('day', col)`, `DATE_TRUNC('hour', col)`,
`EXTRACT(DOW FROM col)`, and any other temporal grouping. The labels rendered
by the chart on the client side use the same TZ via `formatTime`, so the
server-bucketing and the axis-label rendering agree.

Audit at 2026-05-08 found exactly one endpoint of this kind:
`Features/TeamStatus/TeamStatusController.py:193` `GetSavingsByDay`.

## ST7 -- Stage 7 (extension): Date-input filter inputs

`<input type="datetime-local">` reads a wall-clock value with no timezone.
When the user picks "2026-05-08 09:00" in their Chicago browser, the value
is the local-naive string `2026-05-08T09:00`. Before sending to the API,
convert to UTC ISO using the configured display TZ:

```javascript
function localToUtcIso(localValue, tz) {
    // localValue is the raw value from <input type="datetime-local">.
    // tz comes from window.MV_TIMEZONE.
    // Treat the input as a wall-clock time in `tz`, return the ISO-Z string.
}
```

(Helper to be added in `static/js/timezone.js` -- see audit feature doc.)

## ST8 -- Stage 8: Configuration changes

## Seams

| ID | Transition | Producer (writer) | Wire shape | Consumer (reader) expects | Verification |
|---|---|---|---|---|---|
| S1 | `ST1 -> ST2` (DB -> serializer) | Any code writing `TIMESTAMP WITHOUT TIME ZONE` columns; convention requires UTC values | Naive UTC datetime | `Core/Web/UtcJsonProvider` reinterprets naive as UTC | `SHOW timezone;` -> `Etc/UTC`; any sampled `NOW()` matches `\timing` server clock |
| S2 | `ST2 -> ST3/ST4` (server -> browser) | `UtcJsonProvider.dumps()` | ISO-8601 with trailing `Z` (e.g. `2026-05-08T22:11:19.123456Z`) | JS `new Date(s)` parses as UTC instant | Open any JSON-returning endpoint in DevTools; every `datetime` field ends in `Z` |
| S3 | `ST3 -> ST4` (template -> sweep) | Templates emit `<span class="js-tz" data-utc="..." data-fmt="...">UTC fallback</span>` | DOM element with `data-utc` attribute | `static/js/timezone.js::applyTimezoneSweep()` rewrites `textContent` in `window.MV_TIMEZONE` | DevTools: element's title attribute holds the UTC ISO, textContent shows TZ-local |
| S4 | `ST6` SQL bucketing | Endpoint reads `SystemSettings.DisplayTimezone` and passes to SQL | `DATE(col AT TIME ZONE 'UTC' AT TIME ZONE %s)` | Chart on client uses same TZ for axis labels via `formatTime` | Pick a record at 23:30 local time, observe chart bucket = local day (not UTC day) |
| S5 | `ST8 -> session` (config change) | `POST /api/SystemSettings/DisplayTimezone` writes row + bumps cache | `SystemSettings.(Key='DisplayTimezone', Value=<IANA name>)` | `WebServiceApp._CachedDisplayTimezone` read once per process; needs WebService restart to pick up | After restart: `SELECT Value FROM SystemSettings WHERE Key='DisplayTimezone'` matches `window.MV_TIMEZONE` in browser console |

- Operator hits `POST /api/SystemSettings/DisplayTimezone {"Value": "..."}` or
  edits the value via the new Display Timezone card on `/settings` (commit
  505fac2 added a dedicated dropdown + custom-text input + Save button).
- Repository writes the new value. The WebService process keeps using the
  cached value -- new template renders still emit the old `MV_TIMEZONE`.
- Operator restarts WebService (Ctrl+C, re-launch) to pick up the new value,
  OR refreshes a page (no-op in this design -- still cached).
- Per-user TZ override is a future enhancement (cookie/localStorage), not in
  scope for the global setting.

## Failure Modes

| Failure | Symptom | Resolution |
|---------|---------|------------|
| `SystemSettings.DisplayTimezone` row missing | `display_timezone` resolves to `'UTC'`; browser renders in UTC | Re-insert the row (`INSERT INTO SystemSettings ... WHERE NOT EXISTS`) and restart WebService |
| Invalid IANA TZ name (typo, e.g. `America/Chicag0`) | `Intl.DateTimeFormat` throws; `formatTime()` falls back to `Date.toISOString()` (UTC) | Operator sets a valid IANA name from the [tzdb list](https://en.wikipedia.org/wiki/List_of_tz_database_time_zones) |
| JS disabled in browser | `.js-tz` elements stay on the UTC fallback text | No fix -- design is graceful by intent. The `title` UTC value is still useful via View Source |
| `timezone.js` 404 (missing static file) | Browser console error; `formatTime` is undefined; `.js-tz` elements stay on UTC fallback | Verify static dir mapping in WebService Flask config; redeploy |
| Stale cache after operator changes setting | New value in DB but UI still renders old TZ until WebService restarts | Document this as expected. If problematic, drop the cache and read per-request |
| Aware datetime in non-UTC tzinfo from a Python writer | `UtcJsonProvider` converts via `astimezone()`; correct on the wire | None needed |
| Naive datetime from a non-UTC client (worker on non-UTC host) | Stored as if UTC even though it isn't; off by the host's offset | Step 6 of feature: replace `datetime.now()` with `datetime.now(timezone.utc)` |
| Bad client clock (browser system time wrong) | Relative displays ("X min ago") drift; absolute formats unaffected | OS-level fix; outside MediaVortex scope |
