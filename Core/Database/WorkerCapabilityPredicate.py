"""Shared capability-predicate builder for all worker-gated claim queries.

The invariant (see `.claude/rules/db-is-authority.md`): every claim query that
gates on a Worker capability MUST embed the gate inside the SQL via the EXISTS
clause this module emits. No Python control-flow short-circuits. No boot-time
caches of capability flags. The DB is authoritative; this helper is the only
place that says what authoritative looks like.

If you find yourself hand-writing `EXISTS (SELECT 1 FROM Workers w WHERE ...)`
in a claim query, STOP and use this helper instead. One definition prevents
drift across the four claim paths.

Usage:

    sql_fragment, params = BuildClaimPredicate("dot-worker-1", "QualityTestEnabled")
    query = f'''
        SELECT ... FROM <queue_table>
        WHERE Status = 'Pending'
          AND {sql_fragment}
        ORDER BY ...
        FOR UPDATE OF <queue_alias> SKIP LOCKED
    '''
    cursor.execute(query, params + (...other params...))
"""

from typing import Tuple


_ALLOWED_CAPABILITIES = frozenset({
    "TranscodeEnabled",
    "QualityTestEnabled",
    "RemuxEnabled",
    "ScanEnabled",
    "AcceptsInterlaced",  # routing flag, not pure capability, but uses same pattern
})


def BuildClaimPredicate(WorkerName: str, Capability: str) -> Tuple[str, tuple]:
    """Return (sql_fragment, params) for the worker-capability EXISTS gate.

    The fragment is positional-parameter SQL (%s) and the params tuple must be
    prepended (or merged) into the cursor.execute params list in the same order
    as the fragment appears in the parent query.

    Capability MUST be one of the whitelisted column names in
    `_ALLOWED_CAPABILITIES` -- raises ValueError otherwise. The whitelist
    prevents SQL injection via the column-name interpolation; we cannot
    bind a column name as a parameter.

    The fragment gates on three conditions:
      1. Worker name matches.
      2. Worker is Online (not Paused, not Offline).
      3. Worker has the requested capability enabled.

    Mid-flight changes to any of these are honored by the next claim attempt
    because the DB row is re-read on every query execution. No caching.
    """
    if Capability not in _ALLOWED_CAPABILITIES:
        raise ValueError(
            f"Capability {Capability!r} is not in the allowed list. "
            f"Add it to _ALLOWED_CAPABILITIES if it is a real Workers column."
        )
    Fragment = (
        f"EXISTS (SELECT 1 FROM Workers w "
        f"WHERE w.WorkerName = %s "
        f"AND w.Status = 'Online' "
        f"AND w.{Capability} = TRUE)"
    )
    return Fragment, (WorkerName,)
