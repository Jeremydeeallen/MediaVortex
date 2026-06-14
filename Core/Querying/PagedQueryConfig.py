# directive: paged-query-core | # see paged-query.C1
class PagedQueryConfig:
    DefaultPageSize: int = 25
    MaxPageSize: int = 500
    MinPageSize: int = 1

    # directive: paged-query-core | # see paged-query.C1
    def __init__(self, DefaultPageSize: int = 25, MaxPageSize: int = 500, MinPageSize: int = 1):
        self.DefaultPageSize = DefaultPageSize
        self.MaxPageSize = MaxPageSize
        self.MinPageSize = MinPageSize

    # directive: paged-query-core | # see paged-query.C1
    def ClampPageSize(self, Requested: int) -> int:
        if Requested is None or Requested < self.MinPageSize:
            return self.DefaultPageSize
        if Requested > self.MaxPageSize:
            return self.MaxPageSize
        return Requested
