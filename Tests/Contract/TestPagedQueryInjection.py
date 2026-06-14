# see paged-query.C7 -- SQL injection rejection for sort + filter column names

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from Core.Querying import (
    EqualsFilter,
    LikeFilter,
    RangeFilter,
    InListFilter,
    QuerySort,
    InvalidColumnError,
)


# directive: paged-query-core | # see paged-query.C7
class TestInjectionRejected(unittest.TestCase):
    # directive: paged-query-core | # see paged-query.C7
    def test_sort_drop_table_rejected(self):
        with self.assertRaises(InvalidColumnError):
            QuerySort("; DROP TABLE Users--", "DESC", {"Size": "SizeMB"})

    # directive: paged-query-core | # see paged-query.C7
    def test_sort_or_one_equals_one_rejected(self):
        with self.assertRaises(InvalidColumnError):
            QuerySort("1' OR '1'='1", "DESC", {"Size": "SizeMB"})

    # directive: paged-query-core | # see paged-query.C7
    def test_equals_filter_column_with_quote_rejected(self):
        with self.assertRaises(InvalidColumnError):
            EqualsFilter("col'; DROP TABLE Users--", "x")

    # directive: paged-query-core | # see paged-query.C7
    def test_like_filter_column_with_semicolon_rejected(self):
        with self.assertRaises(InvalidColumnError):
            LikeFilter("col;DROP", "x", MatchMode="contains")

    # directive: paged-query-core | # see paged-query.C7
    def test_range_filter_column_with_paren_rejected(self):
        with self.assertRaises(InvalidColumnError):
            RangeFilter("col(1)", Low=1, High=2)

    # directive: paged-query-core | # see paged-query.C7
    def test_inlist_filter_column_with_space_rejected(self):
        with self.assertRaises(InvalidColumnError):
            InListFilter("col with spaces", [1, 2])

    # directive: paged-query-core | # see paged-query.C7
    def test_sort_whitelist_unlisted_column_rejected(self):
        with self.assertRaises(InvalidColumnError):
            QuerySort("ArbitraryColumn", "DESC", {"Size": "SizeMB"})

    # directive: paged-query-core | # see paged-query.C7
    def test_filter_whitelist_unlisted_column_rejected(self):
        with self.assertRaises(InvalidColumnError):
            EqualsFilter("ArbitraryColumn", "x", AllowedColumns={"Status", "Mode"})


if __name__ == "__main__":
    unittest.main()
