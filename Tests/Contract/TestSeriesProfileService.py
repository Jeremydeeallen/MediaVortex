import os
import unittest
from Core.Database.DatabaseService import DatabaseService
from Features.WorkBucket.Domain.ProfileName import InvalidProfileError
from Features.WorkBucket.Domain.SeriesIdentity import SeriesIdentity
from Features.WorkBucket.Services.SeriesProfileService import SeriesProfileService


# directive: work-transcode-unified | # see work-bucket.C3
class TestSeriesProfileService(unittest.TestCase):
    """Contract: SetProfile validates, upserts, and bulk-updates MediaFiles."""

    @classmethod
    # directive: work-transcode-unified | # see work-bucket.C3
    def setUpClass(cls):
        os.environ.setdefault('MEDIAVORTEX_DB_HOST', '10.0.0.15')

    # directive: work-transcode-unified | # see work-bucket.C3
    def test_set_profile_refuses_unknown_profile(self):
        # see work-bucket.C3
        Identity = SeriesIdentity(StorageRootId=99, RelativePath='__test_series__')
        with self.assertRaises(InvalidProfileError):
            SeriesProfileService().SetProfile(Identity, 'this-profile-does-not-exist')

    # directive: work-transcode-unified | # see work-bucket.C3
    def test_set_profile_updates_only_untranscoded_files(self):
        # see work-bucket.C3
        Sample = DatabaseService().ExecuteQuery(
            "SELECT mf.StorageRootId, split_part(mf.RelativePath, '/', 1) AS RelativePath "
            "FROM MediaFiles mf WHERE mf.WorkBucket = 'Transcode' AND mf.TranscodedByMediaVortex IS NOT TRUE "
            "GROUP BY mf.StorageRootId, split_part(mf.RelativePath, '/', 1) "
            "HAVING COUNT(*) >= 1 LIMIT 1"
        )
        if not Sample:
            self.skipTest("No untranscoded Transcode series available")
        ProfileRow = DatabaseService().ExecuteQuery(
            "SELECT ProfileName FROM Profiles WHERE Draft = FALSE AND Active = TRUE LIMIT 1"
        )
        if not ProfileRow:
            self.skipTest("No active profile available")
        Identity = SeriesIdentity(
            StorageRootId=int(Sample[0]['storagerootid']),
            RelativePath=Sample[0]['relativepath'],
        )
        Profile = ProfileRow[0]['profilename']
        Original = DatabaseService().ExecuteQuery(
            "SELECT Id, AssignedProfile FROM MediaFiles "
            "WHERE WorkBucket='Transcode' AND StorageRootId=%s AND split_part(RelativePath,'/',1)=%s "
            "AND TranscodedByMediaVortex IS NOT TRUE",
            (Identity.StorageRootId, Identity.RelativePath),
        )
        try:
            FilesAffected = SeriesProfileService().SetProfile(Identity, Profile)
            self.assertEqual(FilesAffected, len(Original))
            Updated = DatabaseService().ExecuteQuery(
                "SELECT AssignedProfile FROM MediaFiles "
                "WHERE WorkBucket='Transcode' AND StorageRootId=%s AND split_part(RelativePath,'/',1)=%s "
                "AND TranscodedByMediaVortex IS NOT TRUE",
                (Identity.StorageRootId, Identity.RelativePath),
            )
            for R in Updated:
                self.assertEqual(R['assignedprofile'], Profile)
        finally:
            for R in Original:
                DatabaseService().ExecuteNonQuery(
                    "UPDATE MediaFiles SET AssignedProfile = %s WHERE Id = %s",
                    (R.get('assignedprofile'), int(R['id'])),
                )
            DatabaseService().ExecuteNonQuery(
                "DELETE FROM SeriesProfiles WHERE StorageRootId = %s AND RelativePath = %s",
                (Identity.StorageRootId, Identity.RelativePath),
            )


if __name__ == '__main__':
    unittest.main()
