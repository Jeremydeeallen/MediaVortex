# see paged-query.C1 -- contract tests for the PagedQuery value object + filters/sort

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from Core.Querying import (
    PagedQuery,
    PagedQueryConfig,
    PagedQueryResult,
    QuerySort,
    EqualsFilter,
    LikeFilter,
    RangeFilter,
    InListFilter,
    AndComposer,
    OrComposer,
    InvalidColumnError,
    InvalidPageError,
)


SORT_WHITELIST = {"Size": "SizeMB", "Name": "FileName", "Added": "DateAdded"}


# directive: paged-query-core | # see paged-query.C7
class TestQuerySort(unittest.TestCase):
    # directive: paged-query-core | # see paged-query.C6
    def test_emits_order_by_with_nulls_last_by_default(self):
        Sort = QuerySort("Size", "DESC", SORT_WHITELIST)
        self.assertEqual(Sort.ToOrderBy(), "ORDER BY SizeMB DESC NULLS LAST")

    # directive: paged-query-core | # see paged-query.C6
    def test_lowercase_direction_normalizes_to_upper(self):
        Sort = QuerySort("Name", "asc", SORT_WHITELIST)
        self.assertEqual(Sort.ToOrderBy(), "ORDER BY FileName ASC NULLS LAST")

    # directive: paged-query-core | # see paged-query.C7
    def test_unlisted_column_raises_invalid_column(self):
        with self.assertRaises(InvalidColumnError):
            QuerySort("UnknownColumn", "DESC", SORT_WHITELIST)

    # directive: paged-query-core | # see paged-query.C7
    def test_invalid_direction_raises(self):
        with self.assertRaises(InvalidColumnError):
            QuerySort("Size", "SIDEWAYS", SORT_WHITELIST)

    # directive: paged-query-core | # see paged-query.C7
    def test_create_falls_back_to_default_column(self):
        Sort = QuerySort.Create("Bogus", "DESC", SORT_WHITELIST, DefaultColumn="Size")
        self.assertEqual(Sort.ToOrderBy(), "ORDER BY SizeMB DESC NULLS LAST")

    # directive: paged-query-core | # see paged-query.C6
    def test_nulls_last_can_be_disabled(self):
        Sort = QuerySort("Size", "DESC", SORT_WHITELIST, NullsLast=False)
        self.assertEqual(Sort.ToOrderBy(), "ORDER BY SizeMB DESC")


# directive: paged-query-core | # see paged-query.C4
class TestQueryFilters(unittest.TestCase):
    # directive: paged-query-core | # see paged-query.C6
    def test_equals_filter_emits_placeholder(self):
        Filter = EqualsFilter("Status", "Pending")
        self.assertEqual(Filter.ToClause(), "Status = %s")
        self.assertEqual(Filter.Params(), ("Pending",))

    # directive: paged-query-core | # see paged-query.C6
    def test_equals_filter_null_emits_is_null_no_params(self):
        Filter = EqualsFilter("ProcessingMode", None)
        self.assertEqual(Filter.ToClause(), "ProcessingMode IS NULL")
        self.assertEqual(Filter.Params(), ())

    # directive: paged-query-core | # see paged-query.C8
    def test_like_filter_escapes_special_chars(self):
        Filter = LikeFilter("FilePath", "Showname_with%special!chars", MatchMode="contains")
        Clause = Filter.ToClause()
        Params = Filter.Params()
        self.assertIn("ESCAPE '!'", Clause)
        self.assertEqual(Params, ("%Showname!_with!%special!!chars%",))

    # directive: paged-query-core | # see paged-query.C8
    def test_like_filter_prefix_mode(self):
        Filter = LikeFilter("FilePath", "T:\\Westworld\\", MatchMode="prefix")
        Params = Filter.Params()
        self.assertTrue(Params[0].endswith("%"))
        self.assertFalse(Params[0].startswith("%"))

    # directive: paged-query-core | # see paged-query.C3
    def test_range_filter_low_only(self):
        Filter = RangeFilter("SizeMB", Low=1000)
        self.assertEqual(Filter.ToClause(), "SizeMB >= %s")
        self.assertEqual(Filter.Params(), (1000,))

    # directive: paged-query-core | # see paged-query.C3
    def test_range_filter_low_and_high(self):
        Filter = RangeFilter("SizeMB", Low=100, High=5000)
        self.assertIn(">=", Filter.ToClause())
        self.assertIn("<=", Filter.ToClause())
        self.assertEqual(Filter.Params(), (100, 5000))

    # directive: paged-query-core | # see paged-query.C3
    def test_inlist_filter_emits_placeholders(self):
        Filter = InListFilter("Codec", ["h264", "h265", "av1"])
        self.assertEqual(Filter.ToClause(), "Codec IN (%s, %s, %s)")
        self.assertEqual(Filter.Params(), ("h264", "h265", "av1"))

    # directive: paged-query-core | # see paged-query.C4
    def test_and_composer_combines_clauses(self):
        Composer = AndComposer([EqualsFilter("Status", "Pending"), RangeFilter("SizeMB", Low=100)])
        self.assertEqual(Composer.ToClause(), "(Status = %s AND SizeMB >= %s)")
        self.assertEqual(Composer.Params(), ("Pending", 100))

    # directive: paged-query-core | # see paged-query.C4
    def test_or_composer_combines_clauses(self):
        Composer = OrComposer([EqualsFilter("Mode", "Transcode"), EqualsFilter("Mode", "Remux")])
        self.assertEqual(Composer.ToClause(), "(Mode = %s OR Mode = %s)")
        self.assertEqual(Composer.Params(), ("Transcode", "Remux"))

    # directive: paged-query-core | # see paged-query.C4
    def test_empty_composer_raises(self):
        with self.assertRaises(InvalidColumnError):
            AndComposer([])
        with self.assertRaises(InvalidColumnError):
            OrComposer([])


# directive: paged-query-core | # see paged-query.C1
class TestPagedQueryValueObject(unittest.TestCase):
    # directive: paged-query-core | # see paged-query.C1
    def test_offset_and_limit_correct(self):
        Query = PagedQuery(Page=3, PageSize=50)
        self.assertEqual(Query.Offset(), 100)
        self.assertEqual(Query.Limit(), 50)

    # directive: paged-query-core | # see paged-query.C1
    def test_page_zero_rejected(self):
        with self.assertRaises(InvalidPageError):
            PagedQuery(Page=0, PageSize=10)

    # directive: paged-query-core | # see paged-query.C1
    def test_page_size_zero_rejected(self):
        with self.assertRaises(InvalidPageError):
            PagedQuery(Page=1, PageSize=0)


# directive: paged-query-core | # see paged-query.C1
class TestPagedQueryConfig(unittest.TestCase):
    # directive: paged-query-core | # see paged-query.C1
    def test_clamp_too_large(self):
        Config = PagedQueryConfig(DefaultPageSize=25, MaxPageSize=500)
        self.assertEqual(Config.ClampPageSize(10000), 500)

    # directive: paged-query-core | # see paged-query.C1
    def test_clamp_negative_returns_default(self):
        Config = PagedQueryConfig(DefaultPageSize=25, MaxPageSize=500)
        self.assertEqual(Config.ClampPageSize(-1), 25)

    # directive: paged-query-core | # see paged-query.C1
    def test_clamp_passthrough(self):
        Config = PagedQueryConfig(DefaultPageSize=25, MaxPageSize=500)
        self.assertEqual(Config.ClampPageSize(100), 100)


# directive: paged-query-core | # see paged-query.C1
class TestPagedQueryResult(unittest.TestCase):
    # directive: paged-query-core | # see paged-query.C1
    def test_total_pages_rounds_up(self):
        Result = PagedQueryResult(Rows=[], TotalCount=101, Page=1, PageSize=25)
        self.assertEqual(Result.TotalPages(), 5)

    # directive: paged-query-core | # see paged-query.C1
    def test_total_pages_zero_when_empty(self):
        Result = PagedQueryResult(Rows=[], TotalCount=0, Page=1, PageSize=25)
        self.assertEqual(Result.TotalPages(), 0)

    # directive: paged-query-core | # see paged-query.C1
    def test_to_dict_shape(self):
        Result = PagedQueryResult(Rows=[{"A": 1}], TotalCount=1, Page=1, PageSize=25)
        D = Result.ToDict()
        self.assertEqual(D["TotalCount"], 1)
        self.assertEqual(D["Rows"], [{"A": 1}])
        self.assertEqual(D["Page"], 1)
        self.assertEqual(D["PageSize"], 25)
        self.assertEqual(D["TotalPages"], 1)


if __name__ == "__main__":
    unittest.main()
