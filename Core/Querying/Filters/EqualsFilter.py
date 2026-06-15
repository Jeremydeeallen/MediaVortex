from typing import Any, Iterable, Tuple
from Core.Querying.Interfaces.IQueryFilter import IQueryFilter
from Core.Querying.Filters._ColumnSafety import AssertSafeColumn


# directive: paged-query-core | # see paged-query.C6
class EqualsFilter(IQueryFilter):
    # directive: paged-query-core | # see paged-query.C7
    def __init__(self, Column: str, Value: Any, AllowedColumns: Iterable[str] = None):
        AssertSafeColumn(Column, AllowedColumns)
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
