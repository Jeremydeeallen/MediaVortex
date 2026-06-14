from abc import ABC, abstractmethod


# directive: paged-query-core | # see paged-query.C6
class IQuerySort(ABC):
    @abstractmethod
    # directive: paged-query-core | # see paged-query.C6
    def ToOrderBy(self) -> str:
        ...
