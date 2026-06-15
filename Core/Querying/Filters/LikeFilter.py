from typing import Iterable, Tuple
from Core.Database.DatabaseService import EscapeLikePattern
from Core.Querying.Interfaces.IQueryFilter import IQueryFilter
from Core.Querying.Filters._ColumnSafety import AssertSafeColumn
from Core.Querying.Exceptions.InvalidColumnError import InvalidColumnError


_VALID_MATCH_MODES = ("contains", "prefix", "suffix", "exact")


# directive: paged-query-core | # see paged-query.C8
class LikeFilter(IQueryFilter):
    # directive: paged-query-core | # see paged-query.C8
    def __init__(self, Column: str, Pattern: str, AllowedColumns: Iterable[str] = None, MatchMode: str = "contains", CaseInsensitive: bool = True):
        AssertSafeColumn(Column, AllowedColumns)
        if MatchMode not in _VALID_MATCH_MODES:
            raise InvalidColumnError(
                f"LikeFilter MatchMode must be one of {_VALID_MATCH_MODES}, got: {MatchMode!r}"
            )
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
