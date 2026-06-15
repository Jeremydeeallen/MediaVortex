from typing import Any, Iterable, Tuple
from Core.Querying.Interfaces.IQueryFilter import IQueryFilter
from Core.Querying.Filters._ColumnSafety import AssertSafeColumn
from Core.Querying.Exceptions.InvalidColumnError import InvalidColumnError


# directive: paged-query-core | # see paged-query.C3
class RangeFilter(IQueryFilter):
    # directive: paged-query-core | # see paged-query.C3
    def __init__(self, Column: str, Low: Any = None, High: Any = None, AllowedColumns: Iterable[str] = None):
        AssertSafeColumn(Column, AllowedColumns)
        if Low is None and High is None:
            raise InvalidColumnError(
                f"RangeFilter on '{Column}' must have at least one of Low or High"
            )
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
