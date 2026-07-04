import sys
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parents[2]))

import pytest

from Core.Database.DatabaseService import DatabaseService


NVENC_CANARY = 'NVENC AV1 CANARY'
QSV_CANARY = 'QSV AV1 CANARY'


@pytest.fixture(scope='module')
def Db():
    return DatabaseService()


# directive: transcode-flow-canonical | # see transcode.ST5
class TestProfileTierLadder:

    # directive: transcode-flow-canonical | # see transcode.ST5
    def test_profiles_have_family_qualitytier_contentclass_columns(self, Db):
        Cols = Db.ExecuteQuery(
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_name = 'profiles' AND column_name IN ('family', 'qualitytier', 'contentclass')"
        )
        Names = {C['column_name'] for C in Cols}
        assert Names == {'family', 'qualitytier', 'contentclass'}

    # directive: transcode-flow-canonical | # see transcode.ST5
    def test_profilethresholds_have_targetkbps_and_icqq(self, Db):
        Cols = Db.ExecuteQuery(
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_name = 'profilethresholds' AND column_name IN ('targetkbps', 'icqq')"
        )
        Names = {C['column_name'] for C in Cols}
        assert Names == {'targetkbps', 'icqq'}

    # directive: transcode-flow-canonical | # see transcode.ST5
    def test_qualitytier_check_range(self, Db):
        R = Db.ExecuteQuery(
            "SELECT 1 FROM pg_constraint WHERE conname = 'profiles_qualitytier_range'"
        )
        assert R, "profiles_qualitytier_range CHECK constraint must be present"

    # directive: transcode-flow-canonical | # see transcode.ST5
    def test_contentclass_check_enum(self, Db):
        R = Db.ExecuteQuery(
            "SELECT 1 FROM pg_constraint WHERE conname = 'profiles_contentclass_enum'"
        )
        assert R, "profiles_contentclass_enum CHECK constraint must be present"

    # directive: transcode-flow-canonical | # see transcode.ST5
    def test_profilename_unique(self, Db):
        R = Db.ExecuteQuery(
            "SELECT 1 FROM pg_constraint WHERE conname = 'profiles_profilename_unique'"
        )
        assert R, "profiles_profilename_unique UNIQUE constraint must be present"

    # directive: transcode-flow-canonical | # see transcode.ST5
    def test_profilethresholds_unique(self, Db):
        R = Db.ExecuteQuery(
            "SELECT 1 FROM pg_constraint WHERE conname = 'profilethresholds_profile_res_unique'"
        )
        assert R, "profilethresholds_profile_res_unique UNIQUE constraint must be present"

    # directive: transcode-flow-canonical | # see transcode.ST5
    def test_nvenc_canary_family_present(self, Db):
        R = Db.ExecuteQuery(
            "SELECT COUNT(*) AS n FROM Profiles WHERE Family = %s AND ContentClass = 'live_action'",
            (NVENC_CANARY,),
        )
        assert int(R[0]['n']) >= 2, "NVENC AV1 CANARY family should have multiple tier profiles"

    # directive: transcode-flow-canonical | # see transcode.ST5
    def test_qsv_canary_family_present(self, Db):
        R = Db.ExecuteQuery(
            "SELECT COUNT(*) AS n FROM Profiles WHERE Family = %s AND ContentClass = 'live_action'",
            (QSV_CANARY,),
        )
        assert int(R[0]['n']) >= 2, "QSV AV1 CANARY family should have multiple tier profiles"

    # directive: transcode-flow-canonical | # see transcode.ST5
    def test_tier_1_reference_kbps_present_for_adequacygate(self, Db):
        R = Db.ExecuteQuery(
            "SELECT pt.Resolution, pt.TargetKbps FROM ProfileThresholds pt "
            "JOIN Profiles p ON p.Id = pt.ProfileId "
            "WHERE p.Family = %s AND p.QualityTier = 1 AND p.ContentClass = 'live_action' "
            "  AND pt.TargetKbps IS NOT NULL",
            (NVENC_CANARY,),
        )
        Resolutions = {R2['Resolution'] for R2 in R}
        assert Resolutions >= {'480p', '720p', '1080p', '2160p'}, f"NVENC Tier 1 must cover all resolutions; got {Resolutions}"

    # directive: transcode-flow-canonical | # see transcode.ST5
    def test_vmafconfidencestats_bucket_unique(self, Db):
        R = Db.ExecuteQuery(
            "SELECT 1 FROM pg_constraint WHERE conname = 'vmafconfidencestats_bucket_unique'"
        )
        assert R, "vmafconfidencestats_bucket_unique constraint must be present"

    # directive: transcode-flow-canonical | # see transcode.ST5
    def test_vmafconfidencestats_samplesjson_column(self, Db):
        R = Db.ExecuteQuery(
            "SELECT 1 FROM information_schema.columns "
            "WHERE table_name = 'vmafconfidencestats' AND column_name = 'samplesjson'"
        )
        assert R, "VmafConfidenceStats.SamplesJson column must be present"

    # directive: transcode-flow-canonical | # see transcode.ST5
    def test_gateconfig_confidence_knobs_present(self, Db):
        Cols = Db.ExecuteQuery(
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_name = 'posttranscodegateconfig' "
            "  AND column_name IN ('minconfidencesamplecount', 'minconfidencepassrate', 'sigmamargin')"
        )
        Names = {C['column_name'] for C in Cols}
        assert Names == {'minconfidencesamplecount', 'minconfidencepassrate', 'sigmamargin'}


if __name__ == '__main__':
    sys.exit(pytest.main([__file__, '-v']))
