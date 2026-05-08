# Display Timezone

## What It Does

Renders every timestamp in the web UI in a user-configured IANA timezone while
storing all datetimes in PostgreSQL as UTC. The DB stays unambiguous; only the
display layer converts.

## Surface

- `SystemSettings.DisplayTimezone` row -- IANA TZ name (e.g. `America/Chicago`,
  `Europe/London`, `UTC`)
- `/Admin/SystemSettings` page -- existing UI lets the operator change the value
  via `POST /api/SystemSettings/DisplayTimezone`
- `window.MV_TIMEZONE` JS global -- set on every page from the cached value
- `formatTime(utcIso, fmt)`, `formatRelative(utcIso)`, `applyTimezoneSweep(root)`
  -- helpers in `static/js/timezone.js`
- `<span class="js-tz" data-utc="..." data-fmt="...">` markup pattern in
  templates (one element per displayed timestamp)

## Success Criteria

1. **DB is the source of truth in UTC.** Every datetime column on every table
   is treated as UTC. Reads return UTC values with the explicit `Z` suffix in
   JSON, regardless of which worker or machine produced the row.

2. **Flask `UtcJsonProvider` serializes every `datetime` as UTC ISO-8601 with
   the `Z` suffix.** Naive datetimes are reinterpreted as UTC at serialization
   time. Aware datetimes in any other zone are converted. No endpoint code has
   to remember to format dates -- the serializer is the single conversion site.

3. **`SystemSettings.DisplayTimezone` controls the UI display zone.** The
   default is `America/Chicago`. The value is an IANA timezone name, not a
   numeric offset, so DST is handled correctly. Editable via the existing
   SystemSettings POST endpoint and the `/Admin/SystemSettings` page.

4. **The display zone is cached per-process.** `WebService` reads it once on
   first template render and reuses the value to avoid a DB hit per request.
   Operators changing the value should refresh their browser; on `WebService`
   restart the cache is rebuilt from the current DB value.

5. **Templates use `<span class="js-tz" data-utc="..." data-fmt="...">` markup.**
   The element's text content is the UTC fallback shown if JS fails to load.
   On `DOMContentLoaded`, `applyTimezoneSweep()` rewrites the text into the
   configured TZ. The `title` attribute is set to the original UTC string for
   ops/troubleshooting tooltips.

6. **Dynamic content built via AJAX uses `formatTime(utcIso, fmt)` directly.**
   The same JS helper is callable from any inline script that builds rows
   from JSON responses.

7. **Format presets** (`full`, `datetime`, `date`, `time`, `short`, `relative`)
   cover the common UI cases. Unknown format names fall back to `full`.

8. **Edge cases handled:**
   - Date filter inputs (`<input type="datetime-local">`) -- caller converts
     local-naive value to UTC ISO before sending; API treats incoming ISO as UTC
   - CSV exports -- format on the server using `AT TIME ZONE 'X'` in SQL or
     equivalent in Python; include the TZ in the column header
   - Logs displayed in UI use the configured TZ; raw `psql` queries naturally
     show UTC, which is correct for ops
   - Heartbeat-age comparisons stay in UTC end-to-end (`NOW() - LastHeartbeat`),
     never round-trip through the display layer

## Status

IN PROGRESS

### Progress

- [x] 1. Add `SystemSettings.DisplayTimezone` row (default: `America/Chicago`)
- [x] 2. Implement `Core/Web/UtcJsonProvider.py` and wire into Flask app
- [x] 3. Inject `window.MV_TIMEZONE` from a cached context processor in Base.html
- [x] 4. Write `static/js/timezone.js` with `formatTime`, `formatRelative`,
      `applyTimezoneSweep`, and DOMContentLoaded auto-sweep
- [x] 5. Sweep templates: Activity, Operations, Queue, SQLQueries, Optimization,
      FileScanning, Settings now use `window.formatTime()` for all timestamp
      rendering. Status.html only does numeric arithmetic (no display strings)
      so no change needed there. Remaining static-strftime renderings: none
      (audit returned zero matches in `Templates/`).
- [x] 6. Audit `datetime.now()` -> `datetime.now(timezone.utc)` -- 44 production
      `.py` files updated via mechanical replacement; `from datetime import
      timezone` added where missing. 10/10 sample-module import smoke test
      passes. Scripts/, Tests/, and *.md left as-is.
- [ ] 7. Defer: TIMESTAMPTZ schema migration (per-column ALTER ... USING ... AT
      TIME ZONE 'UTC'). Non-blocking; safe to run during a quiet window.

NEXT: Step 7 is a quiet-window task. Feature is functionally complete. Restart
WebService to clear the per-process timezone cache and pick up the new
infrastructure on every page render.

## Scope

```
Core/Web/UtcJsonProvider.py
Features/SystemSettings/**
Templates/Base.html
Templates/Settings.html
static/js/timezone.js
WebService/Main.py
```

## Files

| File | Role |
|------|------|
| `Core/Web/UtcJsonProvider.py` | Flask `DefaultJSONProvider` subclass that emits UTC ISO with `Z` |
| `WebService/Main.py` | Wires the provider; provides `display_timezone` context processor |
| `Templates/Base.html` | Sets `window.MV_TIMEZONE` from `display_timezone`; loads `timezone.js` |
| `static/js/timezone.js` | `formatTime`, `formatRelative`, `applyTimezoneSweep`, DOMContentLoaded sweep |
| `Features/SystemSettings/SystemSettingsRepository.py` | `GetSystemSetting('DisplayTimezone')` |
| `Features/SystemSettings/SystemSettingsController.py` | Existing GET/POST endpoints work without modification |
| `Templates/Settings.html` | Renders DisplayTimezone in the editable settings list (already iterates SystemSettings rows) |
