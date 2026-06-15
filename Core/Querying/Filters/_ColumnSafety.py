from typing import Iterable
from Core.Querying.Exceptions.InvalidColumnError import InvalidColumnError


_IDENT_PATTERN_CHARS = frozenset(
    "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_."
)


# directive: paged-query-core | # see paged-query.C7
def AssertSafeColumn(Column: str, AllowedColumns: Iterable[str] = None):
    """Reject identifiers that are not pure [A-Za-z0-9_.] AND not in the per-query whitelist when provided."""
    if not Column or not isinstance(Column, str):
        raise InvalidColumnError(f"Filter column must be a non-empty string, got: {Column!r}")
    for Ch in Column:
        if Ch not in _IDENT_PATTERN_CHARS:
            raise InvalidColumnError(
                f"Filter column '{Column}' contains disallowed character {Ch!r}; only [A-Za-z0-9_.] permitted"
            )
    if AllowedColumns is not None and Column not in AllowedColumns:
        raise InvalidColumnError(
            f"Filter column '{Column}' is not in the per-query filter whitelist"
        )
