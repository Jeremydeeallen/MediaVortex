from typing import Any, Iterable, List, Tuple
from Core.Querying.Interfaces.IQueryFilter import IQueryFilter
from Core.Querying.Filters._ColumnSafety import AssertSafeColumn
from Core.Querying.Exceptions.InvalidColumnError import InvalidColumnError


# directive: paged-query-core | # see paged-query.C3
class InListFilter(IQueryFilter):
    # directive: paged-query-core | # see paged-query.C3
    def __init__(self, Column: str, Values: List[Any], AllowedColumns: Iterable[str] = None):
        AssertSafeColumn(Column, AllowedColumns)
        if Values is None or len(Values) == 0:
            raise InvalidColumnError(
                f"InListFilter on '{Column}' requires a non-empty Values list"
            )
        self.Column = Column
        self.Values = list(Values)

    # directive: paged-query-core | # see paged-query.C3
    def ToClause(self) -> str:
        Placeholders = ", ".join(["%s"] * len(self.Values))
        return f"{self.Column} IN ({Placeholders})"

    # directive: paged-query-core | # see paged-query.C3
    def Params(self) -> Tuple:
        return tuple(self.Values)
