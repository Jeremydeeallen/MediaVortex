from typing import List, Optional, Tuple
from Core.Querying.PagedQuery import PagedQuery
from Core.Querying.PagedQueryResult import PagedQueryResult
from Core.Querying.PagedQueryConfig import PagedQueryConfig
from Core.Querying.CountStrategy import CountStrategy
from Core.Querying.Exceptions import InvalidColumnError


_WINDOW_COUNT_COLUMN = "__totalcount"


# directive: paged-query-core | # see paged-query.C1
class PagedQueryBuilder:
    # directive: paged-query-core | # see paged-query.C1
    def __init__(self, DatabaseService, Config: Optional[PagedQueryConfig] = None):
        if DatabaseService is None:
            raise InvalidColumnError("PagedQueryBuilder requires a DatabaseService instance")
        self.DatabaseService = DatabaseService
        self.Config = Config or PagedQueryConfig()

    # directive: paged-query-core | # see paged-query.C1
    def Execute(
        self,
        RowsSelect: str,
        Query: PagedQuery,
        RowsSelectParams: Tuple = (),
        StaticWhere: Optional[Tuple[str, Tuple]] = None,
        GroupBy: str = "",
        Having: str = "",
        OrderByOverride: str = "",
        CountStrategyChoice: CountStrategy = CountStrategy.WINDOW,
        CountSelect: Optional[str] = None,
        CountSelectParams: Tuple = (),
    ) -> PagedQueryResult:
        ClampedPageSize = self.Config.ClampPageSize(Query.PageSize)
        WhereClause, WhereParams = self._BuildWhereClause(Query, StaticWhere)
        OrderClause = self._BuildOrderBy(Query, OrderByOverride)

        RowsSql = (
            f"{RowsSelect} "
            f"{WhereClause} "
            f"{GroupBy} "
            f"{Having} "
            f"{OrderClause} "
            f"LIMIT %s OFFSET %s"
        )
        Offset = (Query.Page - 1) * ClampedPageSize
        RowsParams = tuple(RowsSelectParams) + tuple(WhereParams) + (ClampedPageSize, Offset)
        Rows = self.DatabaseService.ExecuteQuery(RowsSql, RowsParams)

        TotalCount = self._ResolveTotalCount(
            Rows=Rows,
            Query=Query,
            CountStrategyChoice=CountStrategyChoice,
            CountSelect=CountSelect,
            CountSelectParams=CountSelectParams,
            WhereClause=WhereClause,
            WhereParams=WhereParams,
            GroupBy=GroupBy,
            Having=Having,
        )

        if CountStrategyChoice == CountStrategy.WINDOW:
            self._StripWindowCountColumn(Rows)

        return PagedQueryResult(
            Rows=Rows,
            TotalCount=TotalCount,
            Page=Query.Page,
            PageSize=ClampedPageSize,
        )

    # directive: paged-query-core | # see paged-query.C4
    def _BuildWhereClause(self, Query: PagedQuery, StaticWhere: Optional[Tuple[str, Tuple]]) -> Tuple[str, Tuple]:
        Fragments: List[str] = []
        Params: List = []
        if StaticWhere and StaticWhere[0]:
            Fragments.append(StaticWhere[0])
            Params.extend(StaticWhere[1] or ())
        for Filter in Query.Filters:
            Clause = Filter.ToClause()
            if Clause:
                Fragments.append(Clause)
                Params.extend(Filter.Params())
        if not Fragments:
            return ("", ())
        return ("WHERE " + " AND ".join(Fragments), tuple(Params))

    # directive: paged-query-core | # see paged-query.C6
    def _BuildOrderBy(self, Query: PagedQuery, OrderByOverride: str) -> str:
        if Query.Sort is not None:
            return Query.Sort.ToOrderBy()
        if OrderByOverride:
            return OrderByOverride if OrderByOverride.upper().lstrip().startswith("ORDER BY") else f"ORDER BY {OrderByOverride}"
        return ""

    # directive: paged-query-core | # see paged-query.C10
    def _StripWindowCountColumn(self, Rows):
        for Row in Rows:
            KeyMap = getattr(Row, "_key_map", None)
            if KeyMap is not None:
                ActualKey = KeyMap.pop(_WINDOW_COUNT_COLUMN, None)
                if ActualKey is not None:
                    dict.__delitem__(Row, ActualKey)
            elif _WINDOW_COUNT_COLUMN in Row:
                del Row[_WINDOW_COUNT_COLUMN]

    # directive: paged-query-core | # see paged-query.C10
    def _ResolveTotalCount(self, Rows, Query, CountStrategyChoice, CountSelect, CountSelectParams, WhereClause, WhereParams, GroupBy, Having) -> int:
        if CountStrategyChoice == CountStrategy.NONE:
            return -1
        if CountStrategyChoice == CountStrategy.WINDOW:
            if not Rows:
                return 0
            First = Rows[0]
            if _WINDOW_COUNT_COLUMN in First:
                Raw = First[_WINDOW_COUNT_COLUMN]
                return int(Raw) if Raw is not None else 0
            return 0
        if CountStrategyChoice == CountStrategy.SEPARATE:
            if not CountSelect:
                raise InvalidColumnError("CountStrategy.SEPARATE requires CountSelect to be provided")
            CountSql = (
                f"{CountSelect} "
                f"{WhereClause} "
                f"{GroupBy} "
                f"{Having}"
            )
            CountParams = tuple(CountSelectParams) + tuple(WhereParams)
            CountRows = self.DatabaseService.ExecuteQuery(CountSql, CountParams)
            if not CountRows:
                return 0
            FirstRow = CountRows[0]
            for Key, Value in FirstRow.items():
                if Value is not None:
                    try:
                        return int(Value)
                    except (TypeError, ValueError):
                        continue
            return 0
        raise InvalidColumnError(f"Unknown CountStrategy: {CountStrategyChoice}")
