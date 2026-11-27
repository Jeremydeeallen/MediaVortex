# directive: target-policy-1a-tables | # see policy.S1 -- the view resolves today's targets; fixture rows live in a transaction that is always rolled back
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from Core.Database.DatabaseService import DatabaseService
from Features.Policy.Target import Target, Undecided
from Features.Policy.TargetResolver import VIEW_COLUMNS, FromRow, TargetResolver

_TV_FIXTURE_ID = 751897
_SELECT = "SELECT " + ", ".join(VIEW_COLUMNS) + " FROM MediaFileTargets WHERE MediaFileId = %s"


# directive: target-policy-1a-tables | # see policy.S1
def _Scalar(Db, Sql, Params=()):
    return Db.ExecuteScalar(Sql, Params)


# directive: target-policy-1a-tables | # see policy.S1 -- writes happen on one pooled connection and are rolled back before it returns to the pool
class _RolledBack:

    # directive: target-policy-1a-tables | # see policy.S1
    def __init__(self, Db):
        self.Db = Db
        self.Connection = None

    # directive: target-policy-1a-tables | # see policy.S1
    def __enter__(self):
        self.Connection = self.Db.GetConnection()
        return self.Connection.cursor()

    # directive: target-policy-1a-tables | # see policy.S1
    def __exit__(self, ExcType, Exc, Tb):
        self.Connection.rollback()
        self.Db.CloseConnection(self.Connection)
        return False


# directive: target-policy-1a-tables | # see policy.S1
def _ViewRow(Cursor, MediaFileId):
    Cursor.execute(_SELECT, (int(MediaFileId),))
    Values = Cursor.fetchone()
    return dict(zip(VIEW_COLUMNS, Values))


# directive: target-policy-1a-tables | # see policy.S1, policy.C4, policy.C7
class TestTargetResolver(unittest.TestCase):

    @classmethod
    # directive: target-policy-1a-tables | # see policy.S1
    def setUpClass(cls):
        cls.Db = DatabaseService()
        cls.Resolver = TargetResolver(cls.Db)

    # directive: target-policy-1a-tables | # see policy.S1
    def test_tv_fixture_resolves_the_library_tier_cell(self):
        T = self.Resolver.Resolve(_TV_FIXTURE_ID)
        self.assertIsInstance(T, Target, getattr(T, 'Reason', None))
        self.assertEqual((T.Tier, T.TierOrigin, T.ContentClass, T.ClassOrigin), (1, 'library', 'live_action', 'library'))
        self.assertEqual((T.FrameRateClass, T.SourceResolution, T.TargetResolution, T.TargetKbps), ('standard', '720p', '720p', 1000))
        self.assertEqual((T.VmafMin, T.VmafMax, T.QualityLabel, T.QualityTestRequired), (90.0, 96.0, 'Efficient', True))
        self.assertEqual((T.OutputContainer, T.CeilingMultiplier, T.ReviewBeforeReplace), ('mp4', 2.0, False))
        self.assertGreater(T.AudioPolicyId, 0)

    # directive: target-policy-1a-tables | # see policy.S2
    def test_resolve_many_returns_one_entry_per_id_and_matches_resolve(self):
        Ids = [int(R['Id']) for R in self.Db.ExecuteQuery("SELECT Id FROM MediaFiles WHERE StorageRootId = 1 ORDER BY Id LIMIT 25")]
        Many = self.Resolver.ResolveMany(Ids + [_TV_FIXTURE_ID])
        self.assertEqual(sorted(Many), sorted(set(Ids + [_TV_FIXTURE_ID])))
        self.assertEqual(Many[_TV_FIXTURE_ID], self.Resolver.Resolve(_TV_FIXTURE_ID))

    # directive: target-policy-1a-tables | # see policy.S1
    def test_unknown_id_raises(self):
        with self.assertRaises(LookupError):
            self.Resolver.Resolve(-1)

    # directive: target-policy-1a-tables | # see policy.C4 -- a library without a default tier is Undecided('Tier'), never defaulted
    def test_untiered_library_is_undecided_tier(self):
        Id = _Scalar(self.Db, "SELECT mf.Id FROM MediaFiles mf JOIN StorageRoots sr ON sr.Id = mf.StorageRootId WHERE sr.DefaultQualityTier IS NULL "
                              "AND NOT EXISTS (SELECT 1 FROM TargetOverrides t WHERE t.StorageRootId = mf.StorageRootId) ORDER BY mf.Id LIMIT 1")
        if Id is None:
            self.skipTest("every library has a default tier")
        self.assertEqual(self.Resolver.Resolve(int(Id)), Undecided(MediaFileId=int(Id), Reason='Tier'))

    # directive: target-policy-1a-tables | # see policy.C7
    def test_frame_rate_above_every_class_is_undecided(self):
        Id = _Scalar(self.Db, "SELECT mf.Id FROM MediaFiles mf JOIN StorageRoots sr ON sr.Id = mf.StorageRootId WHERE sr.DefaultQualityTier IS NOT NULL "
                              "AND (mf.FrameRate IS NULL OR mf.FrameRate > (SELECT MAX(MaxFps) FROM FrameRateClasses)) ORDER BY mf.Id LIMIT 1")
        if Id is None:
            self.skipTest("no file above the highest frame-rate class")
        self.assertEqual(self.Resolver.Resolve(int(Id)), Undecided(MediaFileId=int(Id), Reason='FrameRateClass'))

    # directive: target-policy-1a-tables | # see policy.W2
    def test_migrated_series_override_wins_over_the_library(self):
        Row = self.Db.ExecuteQuery(
            "SELECT t.StorageRootId, t.Key, t.QualityTier FROM TargetOverrides t WHERE t.Scope = 'series' "
            "AND EXISTS (SELECT 1 FROM MediaFiles mf WHERE mf.StorageRootId = t.StorageRootId AND split_part(mf.RelativePath, '/', 1) = t.Key) ORDER BY t.Id LIMIT 1"
        )
        if not Row:
            self.skipTest("no series override with files")
        Id = _Scalar(self.Db, "SELECT Id FROM MediaFiles WHERE StorageRootId = %s AND split_part(RelativePath, '/', 1) = %s ORDER BY Id LIMIT 1",
                     (int(Row[0]['StorageRootId']), Row[0]['Key']))
        T = self.Resolver.Resolve(int(Id))
        self.assertEqual((T.Tier, T.TierOrigin), (int(Row[0]['QualityTier']), 'series_override'))

    # directive: target-policy-1a-tables | # see policy.W2, policy.C7 -- a file override beats the library; the ladder cell follows the override's tier
    def test_file_override_changes_tier_and_cell_in_a_rolled_back_transaction(self):
        with _RolledBack(self.Db) as Cur:
            Cur.execute("INSERT INTO TargetOverrides (StorageRootId, Scope, Key, QualityTier, SetBy) VALUES (1, 'file', %s, 3, 'test:rolled-back')", (str(_TV_FIXTURE_ID),))
            T = FromRow(_ViewRow(Cur, _TV_FIXTURE_ID))
        self.assertIsInstance(T, Target)
        self.assertEqual((T.Tier, T.TierOrigin, T.QualityLabel), (3, 'file_override', 'Better'))
        Cell = _Scalar(self.Db, "SELECT TargetKbps FROM LadderCells WHERE QualityTier = 3 AND ContentClass = 'live_action' AND SourceResolution = '720p' AND FrameRateClass = 'standard'")
        self.assertEqual(T.TargetKbps, int(Cell))
        self.assertEqual(self.Resolver.Resolve(_TV_FIXTURE_ID).Tier, 1)

    # directive: target-policy-1a-tables | # see policy.C4 -- two explicit genre classes make the file Undecided('ContentClassConflict')
    def test_conflicting_genre_classes_are_undecided_in_a_rolled_back_transaction(self):
        with _RolledBack(self.Db) as Cur:
            Cur.execute("INSERT INTO GenreQualityTiers (Genre, QualityTier, ContentClass) VALUES ('_TestA', 2, 'animation'), ('_TestB', NULL, 'live_action')")
            Cur.execute("UPDATE MediaFiles SET Genres = '_TestA,_TestB' WHERE Id = %s", (_TV_FIXTURE_ID,))
            Conflict = FromRow(_ViewRow(Cur, _TV_FIXTURE_ID))
            Cur.execute("UPDATE MediaFiles SET Genres = '_TestA' WHERE Id = %s", (_TV_FIXTURE_ID,))
            GenreOnly = FromRow(_ViewRow(Cur, _TV_FIXTURE_ID))
        self.assertEqual(Conflict, Undecided(MediaFileId=_TV_FIXTURE_ID, Reason='ContentClassConflict'))
        self.assertIsInstance(GenreOnly, Target)
        self.assertEqual((GenreOnly.Tier, GenreOnly.TierOrigin, GenreOnly.ContentClass, GenreOnly.ClassOrigin), (2, 'genre=_TestA', 'animation', 'genre=_TestA'))

    # directive: target-policy-1a-tables | # see policy.C7 -- same file, higher frame rate: the high cell and 1.5x kbps
    def test_high_frame_rate_picks_the_high_cell_in_a_rolled_back_transaction(self):
        with _RolledBack(self.Db) as Cur:
            Cur.execute("UPDATE MediaFiles SET FrameRate = 59.94 WHERE Id = %s", (_TV_FIXTURE_ID,))
            T = FromRow(_ViewRow(Cur, _TV_FIXTURE_ID))
        self.assertIsInstance(T, Target)
        self.assertEqual(T.FrameRateClass, 'high')
        self.assertEqual(T.TargetKbps, 1500)

    # directive: target-policy-1a-tables | # see policy.S1
    def test_from_row_never_builds_a_partial_target(self):
        Row = {C: None for C in VIEW_COLUMNS}
        Row.update({'MediaFileId': 1, 'Undecided': 'LadderCell'})
        self.assertEqual(FromRow(Row), Undecided(MediaFileId=1, Reason='LadderCell'))
        Row['Undecided'] = None
        with self.assertRaises(TypeError):
            FromRow(Row)


if __name__ == '__main__':
    unittest.main()
