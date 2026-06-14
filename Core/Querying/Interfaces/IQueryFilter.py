from abc import ABC, abstractmethod
from typing import Tuple


# directive: paged-query-core | # see paged-query.C6
class IQueryFilter(ABC):
    @abstractmethod
    # directive: paged-query-core | # see paged-query.C6
    def ToClause(self) -> str:
        ...

    @abstractmethod
    # directive: paged-query-core | # see paged-query.C6
    def Params(self) -> Tuple:
        ...
