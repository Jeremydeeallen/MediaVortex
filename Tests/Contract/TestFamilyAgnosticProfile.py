# see transcode-flow-canonical.C25
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

import pytest

from Core.Database.DatabaseService import DatabaseService


EXPECTED_LABELS = {'Efficient', 'Good', 'Better', 'Best', 'Reference'}
EXPECTED_RESOLUTIONS = {'480p', '720p', '1080p', '2160p'}


@pytest.fixture(scope='module')
# directive: transcode-flow-canonical
def Db():
    return DatabaseService()


# directive: transcode-flow-canonical
class TestFamilyAgnosticProfile:

    # directive: transcode-flow-canonical
    def test_profiles_qualitylabel_column_present(self, Db):
        R = Db.ExecuteQuery(
            "SELECT 1 FROM information_schema.columns "
            "WHERE table_name='profiles' AND column_name='qualitylabel'"
        )
        assert R, "profiles.qualitylabel column must exist post-CollapseProfilesToTierLadder"

    # directive: transcode-flow-canonical
    def test_profilethresholds_contentclass_column_present(self, Db):
        R = Db.ExecuteQuery(
            "SELECT 1 FROM information_schema.columns "
            "WHERE table_name='profilethresholds' AND column_name='contentclass'"
        )
        assert R, "profilethresholds.contentclass column must exist post-migration"

    # directive: transcode-flow-canonical
    def test_qualitylabel_unique_constraint_present(self, Db):
        R = Db.ExecuteQuery(
            "SELECT 1 FROM pg_constraint WHERE conname='profiles_qualitylabel_unique'"
        )
        assert R, "profiles_qualitylabel_unique constraint must be present"

    # directive: transcode-flow-canonical
    def test_profilethresholds_contentclass_res_unique_present(self, Db):
        R = Db.ExecuteQuery(
            "SELECT 1 FROM pg_constraint WHERE conname='profilethresholds_profile_content_res_unique'"
        )
        assert R, "profilethresholds_profile_content_res_unique must replace the old res-only unique"

    # directive: transcode-flow-canonical
    def test_five_tier_profiles_are_family_agnostic(self, Db):
        R = Db.ExecuteQuery(
            "SELECT qualitylabel, family, codec, usenvidiahardware, useintelhardware, qualitytier "
            "FROM profiles WHERE qualitylabel IS NOT NULL ORDER BY qualitytier"
        )
        assert len(R) == 5, f"Expected exactly 5 family-agnostic tier profiles; got {len(R)}"
        for Row in R:
            assert Row['family'] == 'ANY', f"family must be 'ANY'; got {Row['family']!r} for tier {Row['qualitytier']}"
            assert Row['codec'] == 'av1', f"codec must be 'av1'; got {Row['codec']!r}"
            assert int(Row['usenvidiahardware']) == 0, f"usenvidiahardware must be 0 (encoder resolved at claim); got {Row['usenvidiahardware']}"
            assert int(Row['useintelhardware']) == 0, f"useintelhardware must be 0 (encoder resolved at claim); got {Row['useintelhardware']}"

    # directive: transcode-flow-canonical
    def test_five_quality_labels_match_expected(self, Db):
        R = Db.ExecuteQuery(
            "SELECT qualitylabel FROM profiles WHERE qualitylabel IS NOT NULL"
        )
        Labels = {Row['qualitylabel'] for Row in R}
        assert Labels == EXPECTED_LABELS, f"Expected {EXPECTED_LABELS}; got {Labels}"

    # directive: transcode-flow-canonical
    def test_twenty_threshold_rows_across_tiers_and_resolutions(self, Db):
        R = Db.ExecuteQuery(
            "SELECT COUNT(*) AS n FROM profilethresholds pt "
            "JOIN profiles p ON p.id = pt.profileid "
            "WHERE p.family = 'ANY' AND p.qualitylabel IS NOT NULL "
            "  AND pt.contentclass = 'live_action' "
            "  AND pt.resolution IN ('480p','720p','1080p','2160p')"
        )
        assert int(R[0]['n']) == 20, f"Expected 20 threshold rows (5 tiers x 4 resolutions); got {R[0]['n']}"

    # directive: transcode-flow-canonical
    def test_every_tier_covers_every_resolution(self, Db):
        R = Db.ExecuteQuery(
            "SELECT p.qualitytier, pt.resolution FROM profilethresholds pt "
            "JOIN profiles p ON p.id = pt.profileid "
            "WHERE p.family = 'ANY' AND p.qualitylabel IS NOT NULL AND pt.contentclass = 'live_action'"
        )
        Coverage = {}
        for Row in R:
            Coverage.setdefault(int(Row['qualitytier']), set()).add(Row['resolution'])
        for Tier in (1, 2, 3, 4, 5):
            assert Coverage.get(Tier) == EXPECTED_RESOLUTIONS, f"Tier {Tier} missing resolutions: expected {EXPECTED_RESOLUTIONS}, got {Coverage.get(Tier)}"

    # directive: transcode-flow-canonical
    def test_targetkbps_populated_for_all_rows(self, Db):
        R = Db.ExecuteQuery(
            "SELECT COUNT(*) AS n FROM profilethresholds pt "
            "JOIN profiles p ON p.id = pt.profileid "
            "WHERE p.family = 'ANY' AND p.qualitylabel IS NOT NULL "
            "  AND pt.contentclass = 'live_action' AND pt.targetkbps IS NULL"
        )
        assert int(R[0]['n']) == 0, f"All family-agnostic thresholds must have TargetKbps populated; got {R[0]['n']} NULLs"

    # directive: transcode-flow-canonical
    def test_icqq_populated_for_all_rows(self, Db):
        R = Db.ExecuteQuery(
            "SELECT COUNT(*) AS n FROM profilethresholds pt "
            "JOIN profiles p ON p.id = pt.profileid "
            "WHERE p.family = 'ANY' AND p.qualitylabel IS NOT NULL "
            "  AND pt.contentclass = 'live_action' AND pt.icqq IS NULL"
        )
        assert int(R[0]['n']) == 0, f"All family-agnostic thresholds must have IcqQ populated; got {R[0]['n']} NULLs"

    # directive: transcode-flow-canonical
    def test_legacy_canary_families_deleted(self, Db):
        R = Db.ExecuteQuery(
            "SELECT COUNT(*) AS n FROM profiles WHERE family IN ('NVENC AV1 CANARY', 'QSV AV1 CANARY')"
        )
        assert int(R[0]['n']) == 0, f"Legacy per-Family CANARY profiles must be deleted; got {R[0]['n']} rows"


if __name__ == '__main__':
    sys.exit(pytest.main([__file__, '-v']))
