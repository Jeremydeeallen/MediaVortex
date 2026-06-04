import sys
import uuid
import unittest
from datetime import datetime, timezone
from pathlib import Path as PyPath

sys.path.append(str(PyPath(__file__).parent.parent.parent))

from Core.Database.DatabaseService import DatabaseService
from Core.Path.Path import Path


SENTINEL_PREFIX = "__mvtest_path_roundtrip__"


# directive: path-class-implementation | # see path.S7
class TestPathDbRoundTrip(unittest.TestCase):
    """S7: Path inserted via typed columns round-trips through Path.FromRow on SELECT."""

    @classmethod
    # directive: path-class-implementation | # see path.S7
    def setUpClass(cls):
        """Pick a StorageRoot for sentinel inserts; skip if no roots configured."""
        cls.Db = DatabaseService()
        Rows = cls.Db.ExecuteQuery(
            "SELECT Id FROM StorageRoots ORDER BY length(CanonicalPrefix) DESC LIMIT 1"
        )
        if not Rows:
            raise unittest.SkipTest("No StorageRoots in DB; cannot run contract test")
        Row = Rows[0]
        cls.StorageRootId = Row["id"] if "id" in Row else Row["Id"]

    # directive: path-class-implementation | # see path.S7
    def setUp(self):
        """Build a unique sentinel path per test method."""
        Ts = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S%f")
        Uniq = uuid.uuid4().hex[:8]
        self.RelativePathValue = f"{SENTINEL_PREFIX}/{Ts}_{Uniq}.mp4"
        self.SentinelFilePath = "M:\\" + self.RelativePathValue.replace("/", "\\")

    # directive: path-schema-migration | # see path.S8
    def tearDown(self):
        """Delete the sentinel row by typed pair (FilePath column is gone)."""
        self.Db.ExecuteNonQuery(
            "DELETE FROM MediaFiles WHERE StorageRootId = %s AND RelativePath = %s",
            (self.StorageRootId, self.RelativePathValue),
        )

    # directive: path-schema-migration | # see path.S8
    def test_typed_columns_round_trip_through_path_class(self):
        """S7: INSERT (StorageRootId, RelativePath) -> SELECT -> Path.FromRow -> equal Path."""
        SentinelPath = Path(self.StorageRootId, self.RelativePathValue)
        self.Db.ExecuteNonQuery(
            "INSERT INTO MediaFiles (StorageRootId, RelativePath) VALUES (%s, %s)",
            (SentinelPath.StorageRootId, SentinelPath.RelativePath),
        )
        Rows = self.Db.ExecuteQuery(
            "SELECT StorageRootId, RelativePath FROM MediaFiles WHERE StorageRootId = %s AND RelativePath = %s",
            (SentinelPath.StorageRootId, SentinelPath.RelativePath),
        )
        self.assertEqual(len(Rows), 1, "expected one round-tripped row")
        Roundtripped = Path.FromRow(Rows[0])
        self.assertIsNotNone(Roundtripped)
        self.assertEqual(Roundtripped, SentinelPath)

    # directive: path-schema-migration | # see path.S8
    def test_json_dict_round_trip_with_db_row(self):
        """S2 / C7: Path.ToJsonDict from a DB-sourced Path round-trips through FromJsonDict."""
        SentinelPath = Path(self.StorageRootId, self.RelativePathValue)
        self.Db.ExecuteNonQuery(
            "INSERT INTO MediaFiles (StorageRootId, RelativePath) VALUES (%s, %s)",
            (SentinelPath.StorageRootId, SentinelPath.RelativePath),
        )
        Rows = self.Db.ExecuteQuery(
            "SELECT StorageRootId, RelativePath FROM MediaFiles WHERE StorageRootId = %s AND RelativePath = %s",
            (SentinelPath.StorageRootId, SentinelPath.RelativePath),
        )
        FromDb = Path.FromRow(Rows[0])
        JsonRoundTrip = Path.FromJsonDict(FromDb.ToJsonDict())
        self.assertEqual(JsonRoundTrip, FromDb)


if __name__ == "__main__":
    unittest.main()
