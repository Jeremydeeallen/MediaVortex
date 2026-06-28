import os
import unittest
from Features.WorkBucket.Domain.ProfileName import ProfileName, InvalidProfileError
from Core.Database.DatabaseService import DatabaseService


# directive: work-transcode-unified
class TestProfileNameVO(unittest.TestCase):

    @classmethod
    # directive: work-transcode-unified
    def setUpClass(cls):
        # see work-bucket.C3
        os.environ.setdefault('MEDIAVORTEX_DB_HOST', '10.0.0.15')

    # directive: work-transcode-unified
    def test_accepts_finalized_active_profile(self):
        # see work-bucket.C3
        Rows = DatabaseService().ExecuteQuery(
            "SELECT ProfileName FROM Profiles WHERE Draft = FALSE AND Active = TRUE LIMIT 1"
        )
        if not Rows:
            self.skipTest("No finalized active profile in DB")
        Name = Rows[0]['profilename']
        P = ProfileName(Name)
        self.assertEqual(P.Value, Name)

    # directive: work-transcode-unified
    def test_refuses_unknown(self):
        # see work-bucket.C3
        with self.assertRaises(InvalidProfileError):
            ProfileName('definitely-not-a-real-profile-xyz')

    # directive: work-transcode-unified
    def test_refuses_draft(self):
        # see work-bucket.C3
        DatabaseService().ExecuteNonQuery(
            "INSERT INTO Profiles (ProfileName, Codec, Container, Draft, Active) "
            "VALUES (%s, 'h264', 'mp4', TRUE, TRUE) ON CONFLICT (ProfileName) DO UPDATE SET Draft = TRUE, Active = TRUE",
            ('test-draft-profile-xyz',),
        )
        try:
            with self.assertRaises(InvalidProfileError):
                ProfileName('test-draft-profile-xyz')
        finally:
            DatabaseService().ExecuteNonQuery(
                "DELETE FROM Profiles WHERE ProfileName = %s",
                ('test-draft-profile-xyz',),
            )

    # directive: work-transcode-unified
    def test_refuses_inactive(self):
        # see work-bucket.C3
        DatabaseService().ExecuteNonQuery(
            "INSERT INTO Profiles (ProfileName, Codec, Container, Draft, Active) "
            "VALUES (%s, 'h264', 'mp4', FALSE, FALSE) ON CONFLICT (ProfileName) DO UPDATE SET Draft = FALSE, Active = FALSE",
            ('test-inactive-profile-xyz',),
        )
        try:
            with self.assertRaises(InvalidProfileError):
                ProfileName('test-inactive-profile-xyz')
        finally:
            DatabaseService().ExecuteNonQuery(
                "DELETE FROM Profiles WHERE ProfileName = %s",
                ('test-inactive-profile-xyz',),
            )


if __name__ == '__main__':
    unittest.main()
