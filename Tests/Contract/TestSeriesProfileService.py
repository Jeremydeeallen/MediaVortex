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
            "HAVING COUNT(*) >= 1 ORDER BY mf.StorageRootId, split_part(mf.RelativePath, '/', 1) LIMIT 1"
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

        # Snapshot pre-existing state so we can restore exactly what was there.
        PreExistingSeriesProfile = DatabaseService().ExecuteQuery(
            "SELECT AssignedProfile, TargetResolution FROM SeriesProfiles "
            "WHERE StorageRootId = %s AND RelativePath = %s LIMIT 1",
            (Identity.StorageRootId, Identity.RelativePath),
        )
        Original = DatabaseService().ExecuteQuery(
            "SELECT Id, AssignedProfile FROM MediaFiles "
            "WHERE StorageRootId=%s AND split_part(RelativePath,'/',1)=%s "
            "AND TranscodedByMediaVortex IS NOT TRUE",
            (Identity.StorageRootId, Identity.RelativePath),
        )
        try:
            FilesAffected = SeriesProfileService().SetProfile(Identity, Profile)
            self.assertEqual(FilesAffected, len(Original))
            Updated = DatabaseService().ExecuteQuery(
                "SELECT AssignedProfile FROM MediaFiles "
                "WHERE StorageRootId=%s AND split_part(RelativePath,'/',1)=%s "
                "AND TranscodedByMediaVortex IS NOT TRUE",
                (Identity.StorageRootId, Identity.RelativePath),
            )
            for R in Updated:
                self.assertEqual(R['assignedprofile'], Profile)
        finally:
            # Restore MediaFiles to exact pre-test values.
            for R in Original:
                DatabaseService().ExecuteNonQuery(
                    "UPDATE MediaFiles SET AssignedProfile = %s WHERE Id = %s",
                    (R.get('assignedprofile'), int(R['id'])),
                )
            # Restore SeriesProfiles to exact pre-test state (don't delete operator data).
            if PreExistingSeriesProfile:
                Pre = PreExistingSeriesProfile[0]
                DatabaseService().ExecuteNonQuery(
                    "INSERT INTO SeriesProfiles "
                    "  (StorageRootId, RelativePath, TargetResolution, AssignedProfile, CreatedDate, LastModifiedDate) "
                    "VALUES (%s, %s, %s, %s, NOW(), NOW()) "
                    "ON CONFLICT (StorageRootId, RelativePath) DO UPDATE "
                    "SET AssignedProfile = EXCLUDED.AssignedProfile, "
                    "    TargetResolution = EXCLUDED.TargetResolution",
                    (
                        Identity.StorageRootId,
                        Identity.RelativePath,
                        Pre.get('targetresolution'),
                        Pre.get('assignedprofile'),
                    ),
                )
            else:
                DatabaseService().ExecuteNonQuery(
                    "DELETE FROM SeriesProfiles WHERE StorageRootId = %s AND RelativePath = %s",
                    (Identity.StorageRootId, Identity.RelativePath),
                )


if __name__ == '__main__':
    unittest.main()
