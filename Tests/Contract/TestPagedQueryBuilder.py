# see paged-query.C10 -- live-DB tests for PagedQueryBuilder (count strategy, paging, filters)

import sys
import unittest
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from Core.Database.DatabaseService import DatabaseService
from Core.Querying import (
    PagedQuery,
    PagedQueryBuilder,
    PagedQueryConfig,
    QuerySort,
    EqualsFilter,
    LikeFilter,
    InListFilter,
    AndComposer,
    CountStrategy,
)


TEST_TABLE = "__test_pagedquery_" + uuid.uuid4().hex[:8]


# directive: paged-query-core | # see paged-query.C10
class TestPagedQueryBuilderLive(unittest.TestCase):
    @classmethod
    # directive: paged-query-core | # see paged-query.C10
    def setUpClass(cls):
        cls.DB = DatabaseService()
        cls.Builder = PagedQueryBuilder(cls.DB, PagedQueryConfig(DefaultPageSize=10, MaxPageSize=500))
        cls.DB.ExecuteNonQuery(
            f"CREATE TABLE IF NOT EXISTS {TEST_TABLE} ("
            "  Id SERIAL PRIMARY KEY, "
            "  ShowName TEXT NOT NULL, "
            "  SizeMB INTEGER, "
            "  Mode TEXT, "
            "  FilePath TEXT"
            ")"
        )
        for I in range(1, 51):
            cls.DB.ExecuteNonQuery(
                f"INSERT INTO {TEST_TABLE} (ShowName, SizeMB, Mode, FilePath) VALUES (%s, %s, %s, %s)",
                (f"Show{I:03d}", I * 100, "Transcode" if I % 2 == 0 else "Remux", f"T:\\Show{I:03d}\\file_with!_special%chars.mkv"),
            )

    @classmethod
    # directive: paged-query-core | # see paged-query.C10
    def tearDownClass(cls):
        cls.DB.ExecuteNonQuery(f"DROP TABLE IF EXISTS {TEST_TABLE}")

    # directive: paged-query-core | # see paged-query.C10
    def test_window_count_matches_actual_total(self):
        SortWhitelist = {"Size": "SizeMB", "Name": "ShowName"}
        Query = PagedQuery(Page=1, PageSize=10, Sort=QuerySort("Size", "DESC", SortWhitelist))
        Result = self.Builder.Execute(
            RowsSelect=f"SELECT Id, ShowName, SizeMB, Mode, FilePath, COUNT(*) OVER () AS __TotalCount FROM {TEST_TABLE}",
            Query=Query,
            CountStrategyChoice=CountStrategy.WINDOW,
        )
        self.assertEqual(Result.TotalCount, 50)
        self.assertEqual(len(Result.Rows), 10)
        self.assertEqual(Result.Page, 1)
        self.assertEqual(Result.PageSize, 10)
        self.assertEqual(Result.TotalPages(), 5)

    # directive: paged-query-core | # see paged-query.C10
    def test_window_count_strips_internal_column(self):
        SortWhitelist = {"Size": "SizeMB"}
        Query = PagedQuery(Page=1, PageSize=3, Sort=QuerySort("Size", "DESC", SortWhitelist))
        Result = self.Builder.Execute(
            RowsSelect=f"SELECT Id, ShowName, SizeMB, COUNT(*) OVER () AS __TotalCount FROM {TEST_TABLE}",
            Query=Query,
            CountStrategyChoice=CountStrategy.WINDOW,
        )
        for Row in Result.Rows:
            self.assertNotIn("__totalcount", Row)
            self.assertNotIn("__TotalCount", Row)

    # directive: paged-query-core | # see paged-query.C9
    def test_case_insensitive_dict_rows(self):
        SortWhitelist = {"Size": "SizeMB"}
        Query = PagedQuery(Page=1, PageSize=1, Sort=QuerySort("Size", "DESC", SortWhitelist))
        Result = self.Builder.Execute(
            RowsSelect=f"SELECT Id, ShowName, SizeMB, COUNT(*) OVER () AS __TotalCount FROM {TEST_TABLE}",
            Query=Query,
            CountStrategyChoice=CountStrategy.WINDOW,
        )
        Row = Result.Rows[0]
        self.assertEqual(Row["ShowName"], Row["showname"])
        self.assertEqual(Row["SHOWNAME"], Row["ShowName"])

    # directive: paged-query-core | # see paged-query.C10
    def test_separate_count_matches_actual_total(self):
        SortWhitelist = {"Size": "SizeMB"}
        Query = PagedQuery(
            Page=1,
            PageSize=5,
            Sort=QuerySort("Size", "ASC", SortWhitelist),
            Filters=[EqualsFilter("Mode", "Transcode")],
        )
        Result = self.Builder.Execute(
            RowsSelect=f"SELECT Id, ShowName, SizeMB, Mode FROM {TEST_TABLE}",
            Query=Query,
            CountStrategyChoice=CountStrategy.SEPARATE,
            CountSelect=f"SELECT COUNT(*) AS Total FROM {TEST_TABLE}",
        )
        self.assertEqual(Result.TotalCount, 25)
        self.assertEqual(len(Result.Rows), 5)

    # directive: paged-query-core | # see paged-query.C10
    def test_count_strategy_none_returns_negative_one(self):
        SortWhitelist = {"Size": "SizeMB"}
        Query = PagedQuery(Page=1, PageSize=5, Sort=QuerySort("Size", "ASC", SortWhitelist))
        Result = self.Builder.Execute(
            RowsSelect=f"SELECT Id, ShowName, SizeMB FROM {TEST_TABLE}",
            Query=Query,
            CountStrategyChoice=CountStrategy.NONE,
        )
        self.assertEqual(Result.TotalCount, -1)
        self.assertEqual(len(Result.Rows), 5)

    # directive: paged-query-core | # see paged-query.C10
    def test_page_beyond_last_returns_empty_rows(self):
        SortWhitelist = {"Size": "SizeMB"}
        Query = PagedQuery(Page=999, PageSize=10, Sort=QuerySort("Size", "DESC", SortWhitelist))
        Result = self.Builder.Execute(
            RowsSelect=f"SELECT Id, COUNT(*) OVER () AS __TotalCount FROM {TEST_TABLE}",
            Query=Query,
            CountStrategyChoice=CountStrategy.WINDOW,
        )
        self.assertEqual(Result.TotalCount, 0)
        self.assertEqual(len(Result.Rows), 0)

    # directive: paged-query-core | # see paged-query.C10
    def test_multi_filter_and_composition(self):
        SortWhitelist = {"Size": "SizeMB"}
        Query = PagedQuery(
            Page=1,
            PageSize=100,
            Sort=QuerySort("Size", "ASC", SortWhitelist),
            Filters=[
                AndComposer([
                    EqualsFilter("Mode", "Transcode"),
                    InListFilter("ShowName", ["Show010", "Show020", "Show030"]),
                ]),
            ],
        )
        Result = self.Builder.Execute(
            RowsSelect=f"SELECT Id, ShowName, Mode, COUNT(*) OVER () AS __TotalCount FROM {TEST_TABLE}",
            Query=Query,
            CountStrategyChoice=CountStrategy.WINDOW,
        )
        self.assertEqual(Result.TotalCount, 3)
        Names = sorted(R["ShowName"] for R in Result.Rows)
        self.assertEqual(Names, ["Show010", "Show020", "Show030"])

    # directive: paged-query-core | # see paged-query.C8
    def test_like_filter_with_special_chars(self):
        SortWhitelist = {"Size": "SizeMB"}
        Query = PagedQuery(
            Page=1,
            PageSize=100,
            Sort=QuerySort("Size", "ASC", SortWhitelist),
            Filters=[LikeFilter("FilePath", "file_with!_special%chars", MatchMode="contains")],
        )
        Result = self.Builder.Execute(
            RowsSelect=f"SELECT Id, FilePath, COUNT(*) OVER () AS __TotalCount FROM {TEST_TABLE}",
            Query=Query,
            CountStrategyChoice=CountStrategy.WINDOW,
        )
        self.assertEqual(Result.TotalCount, 50)
        self.assertEqual(len(Result.Rows), 50)

    # directive: paged-query-core | # see paged-query.C8
    def test_like_filter_no_match_for_unescaped_wildcard(self):
        SortWhitelist = {"Size": "SizeMB"}
        Query = PagedQuery(
            Page=1,
            PageSize=100,
            Sort=QuerySort("Size", "ASC", SortWhitelist),
            Filters=[LikeFilter("FilePath", "file_NOPE_special%chars", MatchMode="contains")],
        )
        Result = self.Builder.Execute(
            RowsSelect=f"SELECT Id, FilePath, COUNT(*) OVER () AS __TotalCount FROM {TEST_TABLE}",
            Query=Query,
            CountStrategyChoice=CountStrategy.WINDOW,
        )
        self.assertEqual(Result.TotalCount, 0)

    # directive: paged-query-core | # see paged-query.C1
    def test_pagesize_clamp_applied(self):
        SortWhitelist = {"Size": "SizeMB"}
        Query = PagedQuery(Page=1, PageSize=10000, Sort=QuerySort("Size", "DESC", SortWhitelist))
        Result = self.Builder.Execute(
            RowsSelect=f"SELECT Id, SizeMB, COUNT(*) OVER () AS __TotalCount FROM {TEST_TABLE}",
            Query=Query,
            CountStrategyChoice=CountStrategy.WINDOW,
        )
        self.assertEqual(Result.PageSize, 500)


if __name__ == "__main__":
    unittest.main()
