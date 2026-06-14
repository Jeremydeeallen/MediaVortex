from typing import List


# directive: paged-query-core | # see paged-query.C1
class PagedQueryResult:
    # directive: paged-query-core | # see paged-query.C1
    def __init__(self, Rows: List, TotalCount: int, Page: int, PageSize: int):
        self.Rows = Rows or []
        self.TotalCount = int(TotalCount) if TotalCount is not None else 0
        self.Page = Page
        self.PageSize = PageSize

    # directive: paged-query-core | # see paged-query.C1
    def TotalPages(self) -> int:
        if self.PageSize <= 0:
            return 0
        return (self.TotalCount + self.PageSize - 1) // self.PageSize

    # directive: paged-query-core | # see paged-query.C1
    def __iter__(self):
        return iter(self.Rows)

    # directive: paged-query-core | # see paged-query.C1
    def __len__(self):
        return len(self.Rows)

    # directive: paged-query-core | # see paged-query.C1
    def ToDict(self) -> dict:
        return {
            "Rows": self.Rows,
            "TotalCount": self.TotalCount,
            "Page": self.Page,
            "PageSize": self.PageSize,
            "TotalPages": self.TotalPages(),
        }
