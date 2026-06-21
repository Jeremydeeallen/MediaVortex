from __future__ import annotations

from pathlib import Path

from Core.Database.DatabaseService import DatabaseService
from Tests.Pipeline.Harness import PermanentFixtures


_BUCKETS = ('Transcode', 'Remux', 'AudioFixOnly', 'Compliant')


# directive: e2e-pipeline-test-framework
def test_permanent_fixture_files_present():
    """Each permanent fixture directory has a binary + properties.json. Skip-with-message if a fixture is missing -- caller should run RegenerateFromLive.py."""
    for B in _BUCKETS:
        if not PermanentFixtures.IsAvailable(B):
            import pytest
            pytest.skip(f"Fixture {B!r} missing -- run: py Tests/Fixtures/PipelineFiles/RegenerateFromLive.py")
        Props = PermanentFixtures.GetProperties(B)
        FixturePath = PermanentFixtures.GetFixtureFile(B)
        assert FixturePath.stat().st_size > 0, f"{B} fixture is zero bytes"
        assert isinstance(Props['SourceMediaFileId'], int), f"{B} properties has bad SourceMediaFileId"


# directive: e2e-pipeline-test-framework
def test_permanent_fixture_properties_complete():
    """Each properties.json has the keys required by the test runner."""
    Required = {'CapturedAt', 'SourceMediaFileId', 'SourceCanonicalPath', 'FixtureFileName', 'FixtureLocalPath', 'ExpectedBucket', 'ExpectedReasons', 'Properties'}
    for B in _BUCKETS:
        if not PermanentFixtures.IsAvailable(B):
            continue
        Props = PermanentFixtures.GetProperties(B)
        Missing = Required - set(Props.keys())
        assert not Missing, f"{B} properties.json missing keys: {Missing}"


# directive: e2e-pipeline-test-framework
def test_manifest_includes_all_buckets():
    """The manifest enumerates every bucket; bucket entries point at the correct expected bucket value (or NULL for Compliant)."""
    M = PermanentFixtures.LoadManifest()
    if M is None:
        import pytest
        pytest.skip("manifest.json missing -- run RegenerateFromLive.py")
    assert set(M['Fixtures'].keys()) == set(_BUCKETS), f"Manifest missing buckets: {set(_BUCKETS) - set(M['Fixtures'].keys())}"
    Expected = {'Transcode': 'Transcode', 'Remux': 'Remux', 'AudioFixOnly': 'AudioFixOnly', 'Compliant': None}
    for B, V in M['Fixtures'].items():
        if 'Error' in V:
            import pytest
            pytest.skip(f"Bucket {B} regenerate errored: {V['Error']}")
        assert V['ExpectedBucket'] == Expected[B], f"Bucket {B} manifest ExpectedBucket={V['ExpectedBucket']!r}; expected {Expected[B]!r}"


# directive: e2e-pipeline-test-framework
def test_fixture_source_rows_still_match_expected_bucket():
    """The MediaFile row each fixture was captured from STILL sits in its expected bucket. If a row has been processed since capture, RegenerateFromLive needs to re-run."""
    Db = DatabaseService()
    Expected = {'Transcode': 'Transcode', 'Remux': 'Remux', 'AudioFixOnly': 'AudioFixOnly', 'Compliant': None}
    Stale = []
    for B in _BUCKETS:
        if not PermanentFixtures.IsAvailable(B):
            continue
        Props = PermanentFixtures.GetProperties(B)
        Id = int(Props['SourceMediaFileId'])
        Rows = Db.ExecuteQuery("SELECT WorkBucket FROM MediaFiles WHERE Id = %s", (Id,))
        if not Rows:
            Stale.append(f"  {B}: source MediaFileId={Id} no longer in DB")
            continue
        Actual = Rows[0]['WorkBucket']
        if Actual != Expected[B]:
            Stale.append(f"  {B}: source MediaFileId={Id} now in bucket={Actual!r}; expected {Expected[B]!r}")
    assert not Stale, "Fixture source rows have drifted; run RegenerateFromLive.py:\n" + "\n".join(Stale)
