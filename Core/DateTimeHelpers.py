"""Datetime utilities for the storage-UTC + display-TZ design.

PostgreSQL `TIMESTAMP WITHOUT TIME ZONE` columns are returned by psycopg2 as
naive Python datetimes. Once we started using `datetime.now(timezone.utc)`
for current-time reads, every site that subtracts a DB datetime from a "now"
datetime began throwing:

    TypeError: can't subtract offset-naive and offset-aware datetimes

`AsAwareUtc()` promotes a possibly-naive datetime to aware UTC so subtraction
works regardless of which side came from the DB. All DB datetimes in this
project are UTC by convention (cluster timezone is `Etc/UTC`), so reinterpreting
a naive value as UTC is correct.

Use whenever you do `datetime.now(timezone.utc) - <db_value>` or vice versa.
"""

from datetime import datetime, timezone
from typing import Optional


def AsAwareUtc(Dt: Optional[datetime]) -> Optional[datetime]:
    """Promote a possibly-naive datetime to aware UTC. None passes through."""
    if Dt is None:
        return None
    return Dt if Dt.tzinfo is not None else Dt.replace(tzinfo=timezone.utc)


def ToUtcIsoZ(Dt: Optional[datetime]) -> Optional[str]:
    """Serialize a datetime as ISO-8601 with the explicit `Z` suffix.

    `dt.isoformat()` on a naive datetime produces a string with NO timezone
    suffix (`2026-05-08T22:48:16`). The browser's `new Date(...)` parses
    such strings as LOCAL time per the JS spec, which silently breaks
    UI timezone conversion -- the configured display TZ becomes a no-op
    because the moment is already interpreted as local.

    Use this helper anywhere a datetime is being serialized into a dict
    that will be returned by `jsonify`. The Flask `UtcJsonProvider`
    handles datetimes that are passed through as objects, but ViewModels
    that pre-format their datetimes bypass the provider -- this helper
    is the alternative.

    Always produces a `Z` suffix (not `+00:00`) for consistency with the
    convention established by `UtcJsonProvider`. JS's `new Date()` parses
    both correctly, but emitting one form everywhere is easier to grep.
    """
    if Dt is None:
        return None
    return AsAwareUtc(Dt).strftime('%Y-%m-%dT%H:%M:%S.%fZ')
