from dataclasses import dataclass
from Core.Querying import PagedQuery
from Features.WorkBucket.Domain.FilterSpec import FilterSpec
from Features.WorkBucket.Domain.SortSpec import SortSpec


@dataclass(frozen=True)
# directive: work-transcode-unified | # see work-bucket.C2
class ListSeriesRequest:
    """Parsed query-string parameters for GET /api/Work/<bucket>."""

    PagedQuery: PagedQuery
    Sort: SortSpec
    Filter: FilterSpec

    @classmethod
    # directive: work-transcode-unified | # see work-bucket.C2
    def FromQueryArgs(cls, Args) -> "ListSeriesRequest":
        # see work-bucket.C2
        Page = max(1, int(Args.get('page', 1) or 1))
        PageSize = max(1, min(200, int(Args.get('pageSize', 25) or 25)))
        Sort = SortSpec.FromString(Args.get('sort', '') or '')
        Drives = tuple(
            int(D) for D in Args.getlist('drive') if D.strip().isdigit()
        )
        SearchTerm = Args.get('search', '') or ''
        return cls(
            PagedQuery=PagedQuery(Page=Page, PageSize=PageSize),
            Sort=Sort,
            Filter=FilterSpec(StorageRootIds=Drives, SearchTerm=SearchTerm),
        )
