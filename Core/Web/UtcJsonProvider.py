"""UTC-aware JSON serialization for Flask.

All datetime values returned via jsonify() are emitted as ISO-8601 with the
explicit `Z` suffix (`2026-05-08T22:11:19.123456Z`). The frontend parses
these as UTC and converts to the configured display timezone via the
`formatTime()` JS helper -- see Static/js/timezone.js.

Storage convention: every datetime column in PostgreSQL is treated as UTC.
Naive datetimes (no tzinfo) are reinterpreted as UTC at serialization time.
This is the single conversion point -- individual endpoints do not need to
know about timezones.

Wire it in once during Flask app construction:

    from Core.Web.UtcJsonProvider import UtcJsonProvider
    self.App.json = UtcJsonProvider(self.App)
"""

from datetime import datetime, timezone, date
from flask.json.provider import DefaultJSONProvider


class UtcJsonProvider(DefaultJSONProvider):
    """Flask JSON provider that always serializes datetimes as UTC ISO-8601 with `Z`.

    Treats naive datetimes as UTC (matches our storage convention -- the postgres
    cluster runs in UTC and all NOW() calls return UTC). Aware datetimes in any
    other timezone are converted to UTC before serialization.
    """

    def default(self, o):
        if isinstance(o, datetime):
            if o.tzinfo is None:
                o = o.replace(tzinfo=timezone.utc)
            else:
                o = o.astimezone(timezone.utc)
            # Strip subsecond if zero, keep with Z suffix otherwise
            return o.strftime('%Y-%m-%dT%H:%M:%S.%fZ')
        if isinstance(o, date):
            return o.isoformat()
        return super().default(o)
