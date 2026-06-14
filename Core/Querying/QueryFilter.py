from typing import Any, Iterable, List, Tuple
from Core.Database.DatabaseService import EscapeLikePattern
from Core.Querying.Interfaces.IQueryFilter import IQueryFilter
from Core.Querying.Exceptions import InvalidColumnError


_IDENT_PATTERN_CHARS = set("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_.")


# directive: paged-query-core | # see paged-query.C7
def _AssertSafeColumn(Column: str):
    if not Column or not isinstance(Column, str):
        raise InvalidColumnError(f"Filter column must be a non-empty string, got: {Column!r}")
    for Ch in Column:
        if Ch not in _IDENT_PATTERN_CHARS:
            raise InvalidColumnError(f"Filter column '{Column}' contains disallowed character {Ch!r}; only [A-Za-z0-9_.] permitted")


# directive: paged-query-core | # see paged-query.C6
class EqualsFilter(IQueryFilter):
    # directive: paged-query-core | # see paged-query.C7
    def __init__(self, Column: str, Value: Any, AllowedColumns: Iterable[str] = None):
        _AssertSafeColumn(Column)
        if AllowedColumns is not None and Column not in AllowedColumns:
            raise InvalidColumnError(f"Filter column '{Column}' is not in the per-query filter whitelist")
        self.Column = Column
        self.Value = Value

    # directive: paged-query-core | # see paged-query.C6
    def ToClause(self) -> str:
        if self.Value is None:
            return f"{self.Column} IS NULL"
        return f"{self.Column} = %s"

    # directive: paged-query-core | # see paged-query.C6
    def Params(self) -> Tuple:
        if self.Value is None:
            return ()
        return (self.Value,)


# directive: paged-query-core | # see paged-query.C8
class LikeFilter(IQueryFilter):
    # directive: paged-query-core | # see paged-query.C8
    def __init__(self, Column: str, Pattern: str, AllowedColumns: Iterable[str] = None, MatchMode: str = "contains", CaseInsensitive: bool = True):
        _AssertSafeColumn(Column)
        if AllowedColumns is not None and Column not in AllowedColumns:
            raise InvalidColumnError(f"Filter column '{Column}' is not in the per-query filter whitelist")
        if MatchMode not in ("contains", "prefix", "suffix", "exact"):
            raise InvalidColumnError(f"LikeFilter MatchMode must be one of contains/prefix/suffix/exact, got: {MatchMode!r}")
        self.Column = Column
        self.RawPattern = Pattern or ""
        self.MatchMode = MatchMode
        self.CaseInsensitive = CaseInsensitive

    # directive: paged-query-core | # see paged-query.C8
    def ToClause(self) -> str:
        if self.CaseInsensitive:
            return f"LOWER({self.Column}) LIKE LOWER(%s) ESCAPE '!'"
        return f"{self.Column} LIKE %s ESCAPE '!'"

    # directive: paged-query-core | # see paged-query.C8
    def Params(self) -> Tuple:
        Escaped = EscapeLikePattern(self.RawPattern)
        if self.MatchMode == "contains":
            return (f"%{Escaped}%",)
        if self.MatchMode == "prefix":
            return (f"{Escaped}%",)
        if self.MatchMode == "suffix":
            return (f"%{Escaped}",)
        return (Escaped,)


# directive: paged-query-core | # see paged-query.C3
class NotLikeFilter(IQueryFilter):
    # directive: paged-query-core | # see paged-query.C3
    def __init__(self, Column: str, Pattern: str, AllowedColumns: Iterable[str] = None, MatchMode: str = "contains", CaseInsensitive: bool = True):
        _AssertSafeColumn(Column)
        if AllowedColumns is not None and Column not in AllowedColumns:
            raise InvalidColumnError(f"Filter column '{Column}' is not in the per-query filter whitelist")
        if MatchMode not in ("contains", "prefix", "suffix", "exact"):
            raise InvalidColumnError(f"NotLikeFilter MatchMode must be one of contains/prefix/suffix/exact, got: {MatchMode!r}")
        self.Column = Column
        self.RawPattern = Pattern or ""
        self.MatchMode = MatchMode
        self.CaseInsensitive = CaseInsensitive

    # directive: paged-query-core | # see paged-query.C3
    def ToClause(self) -> str:
        if self.CaseInsensitive:
            return f"LOWER({self.Column}) NOT LIKE LOWER(%s) ESCAPE '!'"
        return f"{self.Column} NOT LIKE %s ESCAPE '!'"

    # directive: paged-query-core | # see paged-query.C3
    def Params(self) -> Tuple:
        Escaped = EscapeLikePattern(self.RawPattern)
        if self.MatchMode == "contains":
            return (f"%{Escaped}%",)
        if self.MatchMode == "prefix":
            return (f"{Escaped}%",)
        if self.MatchMode == "suffix":
            return (f"%{Escaped}",)
        return (Escaped,)


# directive: paged-query-core | # see paged-query.C3
class RangeFilter(IQueryFilter):
    # directive: paged-query-core | # see paged-query.C3
    def __init__(self, Column: str, Low: Any = None, High: Any = None, AllowedColumns: Iterable[str] = None):
        _AssertSafeColumn(Column)
        if AllowedColumns is not None and Column not in AllowedColumns:
            raise InvalidColumnError(f"Filter column '{Column}' is not in the per-query filter whitelist")
        if Low is None and High is None:
            raise InvalidColumnError(f"RangeFilter on '{Column}' must have at least one of Low or High")
        self.Column = Column
        self.Low = Low
        self.High = High

    # directive: paged-query-core | # see paged-query.C3
    def ToClause(self) -> str:
        if self.Low is not None and self.High is not None:
            return f"({self.Column} >= %s AND {self.Column} <= %s)"
        if self.Low is not None:
            return f"{self.Column} >= %s"
        return f"{self.Column} <= %s"

    # directive: paged-query-core | # see paged-query.C3
    def Params(self) -> Tuple:
        if self.Low is not None and self.High is not None:
            return (self.Low, self.High)
        if self.Low is not None:
            return (self.Low,)
        return (self.High,)


# directive: paged-query-core | # see paged-query.C3
class InListFilter(IQueryFilter):
    # directive: paged-query-core | # see paged-query.C3
    def __init__(self, Column: str, Values: List[Any], AllowedColumns: Iterable[str] = None):
        _AssertSafeColumn(Column)
        if AllowedColumns is not None and Column not in AllowedColumns:
            raise InvalidColumnError(f"Filter column '{Column}' is not in the per-query filter whitelist")
        if Values is None or len(Values) == 0:
            raise InvalidColumnError(f"InListFilter on '{Column}' requires a non-empty Values list")
        self.Column = Column
        self.Values = list(Values)

    # directive: paged-query-core | # see paged-query.C3
    def ToClause(self) -> str:
        Placeholders = ", ".join(["%s"] * len(self.Values))
        return f"{self.Column} IN ({Placeholders})"

    # directive: paged-query-core | # see paged-query.C3
    def Params(self) -> Tuple:
        return tuple(self.Values)


# directive: paged-query-core | # see paged-query.C4
class AndComposer(IQueryFilter):
    # directive: paged-query-core | # see paged-query.C4
    def __init__(self, Filters: List[IQueryFilter]):
        if not Filters:
            raise InvalidColumnError("AndComposer requires at least one inner filter")
        self.Filters = list(Filters)

    # directive: paged-query-core | # see paged-query.C4
    def ToClause(self) -> str:
        return "(" + " AND ".join(F.ToClause() for F in self.Filters) + ")"

    # directive: paged-query-core | # see paged-query.C4
    def Params(self) -> Tuple:
        Combined: List[Any] = []
        for F in self.Filters:
            Combined.extend(F.Params())
        return tuple(Combined)


# directive: paged-query-core | # see paged-query.C4
class OrComposer(IQueryFilter):
    # directive: paged-query-core | # see paged-query.C4
    def __init__(self, Filters: List[IQueryFilter]):
        if not Filters:
            raise InvalidColumnError("OrComposer requires at least one inner filter")
        self.Filters = list(Filters)

    # directive: paged-query-core | # see paged-query.C4
    def ToClause(self) -> str:
        return "(" + " OR ".join(F.ToClause() for F in self.Filters) + ")"

    # directive: paged-query-core | # see paged-query.C4
    def Params(self) -> Tuple:
        Combined: List[Any] = []
        for F in self.Filters:
            Combined.extend(F.Params())
        return tuple(Combined)
