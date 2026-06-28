import unittest
from Features.WorkBucket.Domain.ListSeriesRequest import ListSeriesRequest
from Features.WorkBucket.Domain.SortSpec import SortSpec


class _FakeArgs(dict):
    """Minimal MultiDict stand-in: supports get() and getlist()."""
    def __init__(self, pairs=()):
        super().__init__()
        self._multi = {}
        for K, V in (pairs if not isinstance(pairs, dict) else pairs.items()):
            self._multi.setdefault(K, []).append(V)
            self[K] = V

    def get(self, Key, Default=None):
        return self._multi.get(Key, [Default])[0]

    def getlist(self, Key):
        return self._multi.get(Key, [])


# directive: work-transcode-unified | # see work-bucket.C2
class TestListSeriesRequestVO(unittest.TestCase):
    """Parse defaults, sort string, drive multi-select, search term."""

    # directive: work-transcode-unified | # see work-bucket.C2
    def test_defaults(self):
        # see work-bucket.C2
        Req = ListSeriesRequest.FromQueryArgs(_FakeArgs())
        self.assertEqual(Req.PagedQuery.Page, 1)
        self.assertEqual(Req.PagedQuery.PageSize, 25)
        self.assertEqual(Req.Sort, SortSpec.TotalGbDesc)
        self.assertEqual(Req.Filter.StorageRootIds, ())
        self.assertEqual(Req.Filter.SearchTerm, '')

    # directive: work-transcode-unified | # see work-bucket.C2
    def test_paged_query_clamps(self):
        # see work-bucket.C2
        Req = ListSeriesRequest.FromQueryArgs(_FakeArgs({'pageSize': '500'}.items()))
        self.assertEqual(Req.PagedQuery.PageSize, 200)
        Min = ListSeriesRequest.FromQueryArgs(_FakeArgs({'pageSize': '0'}.items()))
        self.assertEqual(Min.PagedQuery.PageSize, 1)

    # directive: work-transcode-unified | # see work-bucket.C2
    def test_drive_multi_select(self):
        # see work-bucket.C2
        Args = _FakeArgs([('drive', '1'), ('drive', '3')])
        Req = ListSeriesRequest.FromQueryArgs(Args)
        self.assertEqual(Req.Filter.StorageRootIds, (1, 3))

    # directive: work-transcode-unified | # see work-bucket.C2
    def test_sort_parsing(self):
        # see work-bucket.C2
        Req = ListSeriesRequest.FromQueryArgs(_FakeArgs({'sort': 'FileCount.desc'}.items()))
        self.assertEqual(Req.Sort, SortSpec.FileCountDesc)
        Bad = ListSeriesRequest.FromQueryArgs(_FakeArgs({'sort': 'bogus'}.items()))
        self.assertEqual(Bad.Sort, SortSpec.TotalGbDesc)


if __name__ == '__main__':
    unittest.main()
