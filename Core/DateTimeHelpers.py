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
