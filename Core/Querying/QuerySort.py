from typing import Dict, Optional
from Core.Querying.Interfaces.IQuerySort import IQuerySort
from Core.Querying.Exceptions import InvalidColumnError


_VALID_DIRECTIONS = ("ASC", "DESC")


# directive: paged-query-core | # see paged-query.C6
class QuerySort(IQuerySort):
    # directive: paged-query-core | # see paged-query.C7
    def __init__(self, Column: str, Direction: str, AllowedColumns: Dict[str, str], NullsLast: bool = True):
        if not AllowedColumns:
            raise InvalidColumnError("AllowedColumns whitelist cannot be empty")
        if Column is None or Column not in AllowedColumns:
            raise InvalidColumnError(f"Sort column '{Column}' is not in the per-query whitelist: {sorted(AllowedColumns.keys())}")
        Normalized = (Direction or "DESC").upper()
        if Normalized not in _VALID_DIRECTIONS:
            raise InvalidColumnError(f"Sort direction '{Direction}' must be one of {_VALID_DIRECTIONS}")
        self.Column = Column
        self.SqlExpr = AllowedColumns[Column]
        self.Direction = Normalized
        self.NullsLast = NullsLast

    # directive: paged-query-core | # see paged-query.C6
    def ToOrderBy(self) -> str:
        Suffix = " NULLS LAST" if self.NullsLast else ""
        return f"ORDER BY {self.SqlExpr} {self.Direction}{Suffix}"

    @staticmethod
    # directive: paged-query-core | # see paged-query.C7
    def Create(Column: Optional[str], Direction: Optional[str], AllowedColumns: Dict[str, str], DefaultColumn: Optional[str] = None, NullsLast: bool = True) -> "QuerySort":
        Resolved = Column if Column in (AllowedColumns or {}) else DefaultColumn
        return QuerySort(Resolved, Direction, AllowedColumns, NullsLast)
