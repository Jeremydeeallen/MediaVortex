# see transcode-flow-canonical.C25
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

import pytest

from Core.Database.DatabaseService import DatabaseService


EXPECTED_LABELS = ('Efficient', 'Good', 'Better', 'Best', 'Reference')
EXPECTED_TIER_LABEL = {1: 'Efficient', 2: 'Good', 3: 'Better', 4: 'Best', 5: 'Reference'}


@pytest.fixture(scope='module')
# directive: transcode-flow-canonical
def Db():
    return DatabaseService()


# directive: transcode-flow-canonical
class TestQualityLabelLookupPreconditions:

    # directive: transcode-flow-canonical
    def test_each_expected_label_maps_to_exactly_one_profile(self, Db):
        for Label in EXPECTED_LABELS:
            R = Db.ExecuteQuery(
                "SELECT id, family, codec FROM profiles WHERE qualitylabel = %s",
                (Label,),
            )
            assert len(R) == 1, f"Label {Label!r} should uniquely identify one profile; got {len(R)}"
            assert R[0]['family'] == 'ANY', f"Label {Label!r} must map to family-agnostic profile"
            assert R[0]['codec'] == 'av1', f"Label {Label!r} must map to av1 codec"

    # directive: transcode-flow-canonical
    def test_no_duplicate_labels(self, Db):
        R = Db.ExecuteQuery(
            "SELECT qualitylabel, COUNT(*) AS n FROM profiles "
            "WHERE qualitylabel IS NOT NULL GROUP BY qualitylabel HAVING COUNT(*) > 1"
        )
        assert R == [], f"No duplicate quality labels allowed; got {R}"

    # directive: transcode-flow-canonical
    def test_tier_and_label_are_bijective(self, Db):
        R = Db.ExecuteQuery(
            "SELECT qualitytier, qualitylabel FROM profiles "
            "WHERE qualitylabel IS NOT NULL ORDER BY qualitytier"
        )
        Mapping = {int(Row['qualitytier']): Row['qualitylabel'] for Row in R}
        assert Mapping == EXPECTED_TIER_LABEL, f"Tier-to-label bijection broken; got {Mapping}"

    # directive: transcode-flow-canonical
    def test_lookup_by_label_is_indexable_via_unique_constraint(self, Db):
        R = Db.ExecuteQuery(
            "SELECT contype FROM pg_constraint WHERE conname = 'profiles_qualitylabel_unique'"
        )
        assert R and R[0]['contype'] == 'u', "profiles_qualitylabel_unique must be a UNIQUE constraint (backs O(1) label lookup)"


REPO_ROOT = Path(__file__).resolve().parent.parent.parent
CONTROLLER = REPO_ROOT / 'Features' / 'WorkBucket' / 'WorkBucketController.py'
ADMISSION_SERVICE = REPO_ROOT / 'Features' / 'WorkBucket' / 'Services' / 'QueueAdmissionAppService.py'
QUEUE_SERVICE = REPO_ROOT / 'Features' / 'TranscodeQueue' / 'QueueManagementBusinessService.py'
PROFILE_REPO = REPO_ROOT / 'Features' / 'Profiles' / 'ProfileRepository.py'


# directive: transcode-flow-canonical
def test_enqueue_endpoint_accepts_quality_label_query_param():
    Text = CONTROLLER.read_text(encoding='utf-8')
    assert "request.args.get('quality')" in Text, "queue_one route must read ?quality= query param"
    assert "QualityLabel=QualityLabel" in Text, "queue_one must plumb QualityLabel through to AdmitOne"


# directive: transcode-flow-canonical
def test_add_job_to_queue_signature_accepts_quality_label_and_tier():
    Text = QUEUE_SERVICE.read_text(encoding='utf-8')
    assert "QualityLabel: str = None" in Text, "AddJobToQueue must accept QualityLabel kwarg"
    assert "QualityTier: int = None" in Text, "AddJobToQueue must accept QualityTier kwarg"
    assert "GetProfileIdByQualityLabel" in Text, "AddJobToQueue must resolve via ProfileRepository.GetProfileIdByQualityLabel"
    assert "GetProfileIdByQualityTier" in Text, "AddJobToQueue must resolve via ProfileRepository.GetProfileIdByQualityTier"


# directive: transcode-flow-canonical
def test_enqueue_endpoint_accepts_tier_query_param():
    Text = CONTROLLER.read_text(encoding='utf-8')
    assert "request.args.get('tier')" in Text, "queue_one route must read ?tier= query param"
    assert "QualityTier=QualityTier" in Text, "queue_one must plumb QualityTier through to AdmitOne"


# directive: transcode-flow-canonical
def test_admission_service_admit_one_accepts_quality_kwargs():
    Text = ADMISSION_SERVICE.read_text(encoding='utf-8')
    assert "QualityLabel: str = None" in Text, "AdmitOne must accept QualityLabel kwarg"
    assert "QualityTier: int = None" in Text, "AdmitOne must accept QualityTier kwarg"


# directive: transcode-flow-canonical
def test_profile_repository_exposes_label_and_tier_lookup():
    Text = PROFILE_REPO.read_text(encoding='utf-8')
    assert "def GetProfileIdByQualityLabel" in Text, "ProfileRepository must expose GetProfileIdByQualityLabel"
    assert "def GetProfileIdByQualityTier" in Text, "ProfileRepository must expose GetProfileIdByQualityTier"


if __name__ == '__main__':
    sys.exit(pytest.main([__file__, '-v']))
