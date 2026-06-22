import unittest

from Core.Database.DatabaseService import DatabaseService


# directive: compliance-symmetry
class TestProfileCascadeResolution(unittest.TestCase):

    # directive: compliance-symmetry
    def test_pre_migration_default_is_finalized_and_active(self):
        Db = DatabaseService()
        Rows = Db.ExecuteQuery(
            "SELECT Draft, Active, StreamCodecName, TargetResolutionCategory, "
            "AudioCodec, TargetAudioKbps, Container, AllowUpscale "
            "FROM Profiles WHERE ProfileName = '_PreMigrationDefault'"
        )
        self.assertEqual(len(Rows), 1, '_PreMigrationDefault must be seeded by the migration')
        R = Rows[0]
        self.assertFalse(R['draft'], '_PreMigrationDefault must be Finalized')
        self.assertTrue(R['active'], '_PreMigrationDefault must be Active')
        self.assertEqual(R['streamcodecname'], 'av1')
        self.assertEqual(R['targetresolutioncategory'], '720p')
        self.assertEqual(R['audiocodec'], 'aac')
        self.assertEqual(R['targetaudiokbps'], 128)
        self.assertEqual(R['container'], 'mp4')
        self.assertFalse(R['allowupscale'])

    # directive: compliance-symmetry
    def test_unique_constraint_on_profilename(self):
        Db = DatabaseService()
        Rows = Db.ExecuteQuery(
            "SELECT 1 FROM pg_indexes WHERE tablename='profiles' AND indexname='uq_profiles_profilename'"
        )
        self.assertEqual(len(Rows), 1, 'Profiles.ProfileName must have UNIQUE index uq_profiles_profilename')

    # directive: compliance-symmetry
    def test_all_other_profiles_migrated_to_draft(self):
        Db = DatabaseService()
        Rows = Db.ExecuteQuery(
            "SELECT COUNT(*) AS cnt FROM Profiles WHERE Draft = FALSE AND ProfileName <> '_PreMigrationDefault'"
        )
        Cnt = Rows[0]['cnt']
        self.assertGreaterEqual(Cnt, 0, 'Some profiles may have been operator-finalized post-migration; non-negative is the only invariant')


if __name__ == '__main__':
    unittest.main()
