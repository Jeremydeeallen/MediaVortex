from typing import Any, List, Tuple
from Core.Querying.Interfaces.IQueryFilter import IQueryFilter
from Core.Querying.Exceptions.InvalidColumnError import InvalidColumnError


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
