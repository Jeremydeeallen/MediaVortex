from typing import List, Optional
from Core.Querying.Interfaces.IQueryFilter import IQueryFilter
from Core.Querying.QuerySort import QuerySort
from Core.Querying.Exceptions import InvalidPageError


# directive: paged-query-core | # see paged-query.C1
class PagedQuery:
    # directive: paged-query-core | # see paged-query.C1
    def __init__(self, Page: int = 1, PageSize: int = 25, Sort: Optional[QuerySort] = None, Filters: Optional[List[IQueryFilter]] = None):
        if Page is None or not isinstance(Page, int) or Page < 1:
            raise InvalidPageError(f"Page must be a positive integer, got: {Page!r}")
        if PageSize is None or not isinstance(PageSize, int) or PageSize < 1:
            raise InvalidPageError(f"PageSize must be a positive integer, got: {PageSize!r}")
        self.Page = Page
        self.PageSize = PageSize
        self.Sort = Sort
        self.Filters = list(Filters) if Filters else []

    # directive: paged-query-core | # see paged-query.C1
    def Offset(self) -> int:
        return (self.Page - 1) * self.PageSize

    # directive: paged-query-core | # see paged-query.C1
    def Limit(self) -> int:
        return self.PageSize
