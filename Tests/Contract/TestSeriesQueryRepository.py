import os
import unittest
from Core.Querying import PagedQuery
from Features.WorkBucket.Domain.BucketKey import BucketKey
from Features.WorkBucket.Domain.FilterSpec import FilterSpec
from Features.WorkBucket.Domain.SortSpec import SortSpec
from Features.WorkBucket.Repositories.SeriesQueryRepository import SeriesQueryRepository


# directive: work-transcode-unified | # see work-bucket.C1
class TestSeriesQueryRepository(unittest.TestCase):

    @classmethod
    # directive: work-transcode-unified | # see work-bucket.C1
    def setUpClass(cls):
        os.environ.setdefault('MEDIAVORTEX_DB_HOST', '10.0.0.15')

    # directive: work-transcode-unified | # see work-bucket.C1
    def test_list_series_by_bucket_transcode_returns_only_transcode_files(self):
        Repo = SeriesQueryRepository()
        Result = Repo.ListSeriesByBucket(
            Bucket=BucketKey.FromUrlKey('Transcode'),
            Query=PagedQuery(Page=1, PageSize=25),
            Sort=SortSpec.TotalGbDesc,
            Filter=FilterSpec(),
        )
        self.assertGreaterEqual(Result.TotalCount, 0)
        for S in Result.Rows:
            self.assertGreater(S.FileCount, 0)
            self.assertGreaterEqual(S.TotalGB, 0)
            self.assertEqual(S.Bucket.BucketName, 'Transcode')

    # directive: work-transcode-unified | # see work-bucket.C1
    def test_having_clause_excludes_empty_series(self):
        Repo = SeriesQueryRepository()
        Result = Repo.ListSeriesByBucket(
            Bucket=BucketKey.FromUrlKey('Transcode'),
            Query=PagedQuery(Page=1, PageSize=100),
            Sort=SortSpec.TotalGbDesc,
            Filter=FilterSpec(),
        )
        for S in Result.Rows:
            self.assertGreater(S.FileCount, 0)

    # directive: work-transcode-unified | # see work-bucket.C2
    def test_sort_total_gb_desc_is_monotonic(self):
        Repo = SeriesQueryRepository()
        Result = Repo.ListSeriesByBucket(
            Bucket=BucketKey.FromUrlKey('Transcode'),
            Query=PagedQuery(Page=1, PageSize=10),
            Sort=SortSpec.TotalGbDesc,
            Filter=FilterSpec(),
        )
        Prev = None
        for S in Result.Rows:
            if Prev is not None:
                self.assertLessEqual(S.TotalGB, Prev)
            Prev = S.TotalGB

    # directive: work-transcode-unified | # see work-bucket.C1
    def test_none_bucket_raises(self):
        Repo = SeriesQueryRepository()
        with self.assertRaises((AttributeError, TypeError, ValueError)):
            Repo.ListSeriesByBucket(
                Bucket=None,
                Query=PagedQuery(Page=1, PageSize=10),
                Sort=SortSpec.TotalGbDesc,
                Filter=FilterSpec(),
            )

    # directive: work-transcode-unified | # see work-bucket.C6
    def test_filter_search_term_narrows_results(self):
        Repo = SeriesQueryRepository()
        All = Repo.ListSeriesByBucket(
            Bucket=BucketKey.FromUrlKey('Transcode'),
            Query=PagedQuery(Page=1, PageSize=100),
            Sort=SortSpec.TotalGbDesc,
            Filter=FilterSpec(),
        )
        if not All.Rows:
            self.skipTest("No Transcode series in DB")
        Anchor = All.Rows[0].ShowName
        Narrowed = Repo.ListSeriesByBucket(
            Bucket=BucketKey.FromUrlKey('Transcode'),
            Query=PagedQuery(Page=1, PageSize=100),
            Sort=SortSpec.TotalGbDesc,
            Filter=FilterSpec(SearchTerm=Anchor),
        )
        self.assertGreaterEqual(len(Narrowed.Rows), 1)
        for S in Narrowed.Rows:
            self.assertIn(Anchor.lower(), S.ShowName.lower())


if __name__ == '__main__':
    unittest.main()
