# directive: path-db-roundtrip-live | # see path.S7
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path as PyPath

import pytest

sys.path.append(str(PyPath(__file__).parent.parent.parent))

from Core.Database.DatabaseService import DatabaseService, EscapeLikePattern
from Core.Path.Path import Path, PathError


SENTINEL_PREFIX = "__mvtest_path_roundtrip__"


# directive: path-db-roundtrip-live | # see path.C17
def _RequireWorkersStopped():
    """C17: this contract test must run with all transcode workers stopped (larry LXC 218 + I9 WorkerService). Operator procedure -- see directive."""
    return True


@pytest.fixture(scope="module")
# directive: path-db-roundtrip-live | # see path.S7
def Db():
    """Module-scoped DatabaseService connecting to live 10.0.0.15:5432."""
    return DatabaseService()


@pytest.fixture(scope="module")
# directive: path-db-roundtrip-live | # see path.S7
def StorageRootId(Db):
    """Pick the longest-prefix StorageRoot for sentinels; skip module if no roots."""
    Rows = Db.ExecuteQuery(
        "SELECT Id FROM StorageRoots ORDER BY length(CanonicalPrefix) DESC LIMIT 1"
    )
    if not Rows:
        pytest.skip("No StorageRoots in DB; cannot run contract tests")
    Row = Rows[0]
    return Row["id"] if "id" in Row else Row["Id"]


# directive: path-db-roundtrip-live | # see path.S7
def _Sentinel(Suffix: str = "mp4") -> str:
    """Build a unique sentinel RelativePath; includes timestamp + uuid8 for parallel-safety."""
    Ts = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S%f")
    Uniq = uuid.uuid4().hex[:8]
    return f"{SENTINEL_PREFIX}/{Ts}_{Uniq}.{Suffix}"


# directive: path-db-roundtrip-live | # see path.S7
def _SentinelLegacyForm(Rel: str) -> str:
    """Convert sentinel RelativePath to a Windows-style legacy filepath for tables requiring filepath."""
    return "M:\\" + Rel.replace("/", "\\")


@pytest.fixture
# directive: path-db-roundtrip-live | # see path.S7
def CleanupSentinels(Db):
    """Per-test cleanup: deletes any rows matching the sentinel LIKE prefix across the 6 tables."""
    yield
    LikePattern = EscapeLikePattern(SENTINEL_PREFIX) + "%"
    Tables = [
        ("MediaFiles", "RelativePath", "FilePath"),
        ("MediaFilesArchive", "RelativePath", "FilePath"),
        ("TranscodeQueue", "RelativePath", "FilePath"),
        ("TranscodeAttempts", "RelativePath", "FilePath"),
        ("ShowSettings", "RelativePath", "ShowFolder"),
    ]
    for Table, RelCol, LegacyCol in Tables:
        Db.ExecuteNonQuery(
            f"DELETE FROM {Table} WHERE {RelCol} LIKE %s ESCAPE '!' OR {LegacyCol} LIKE %s ESCAPE '!'",
            (LikePattern, LikePattern),
        )
    Db.ExecuteNonQuery(
        "DELETE FROM TemporaryFilePaths WHERE SourceRelativePath LIKE %s ESCAPE '!' OR OutputRelativePath LIKE %s ESCAPE '!' OR OriginalPath LIKE %s ESCAPE '!'",
        (LikePattern, LikePattern, LikePattern),
    )


# directive: path-db-roundtrip-live | # see path.S7
def test_mediafiles_round_trip(Db, StorageRootId, CleanupSentinels):
    """C2: MediaFiles INSERT (StorageRootId, RelativePath) -> SELECT -> Path.FromRow -> equal."""
    Rel = _Sentinel("mp4")
    Sentinel = Path(StorageRootId, Rel)
    Db.ExecuteNonQuery(
        "INSERT INTO MediaFiles (FilePath, StorageRootId, RelativePath) VALUES (%s, %s, %s)",
        (_SentinelLegacyForm(Rel), Sentinel.StorageRootId, Sentinel.RelativePath),
    )
    Rows = Db.ExecuteQuery(
        "SELECT StorageRootId, RelativePath FROM MediaFiles WHERE RelativePath = %s",
        (Rel,),
    )
    assert len(Rows) == 1
    assert Path.FromRow(Rows[0]) == Sentinel


# directive: path-db-roundtrip-live | # see path.S7
def test_mediafilesarchive_round_trip(Db, StorageRootId, CleanupSentinels):
    """C3: MediaFilesArchive INSERT -> SELECT -> Path.FromRow -> equal."""
    Rel = _Sentinel("mkv")
    Sentinel = Path(StorageRootId, Rel)
    ArchiveId = 9_000_000_000 + int(uuid.uuid4().int % 1_000_000_000)
    Db.ExecuteNonQuery(
        "INSERT INTO MediaFilesArchive (Id, FilePath, StorageRootId, RelativePath) VALUES (%s, %s, %s, %s)",
        (ArchiveId, _SentinelLegacyForm(Rel), Sentinel.StorageRootId, Sentinel.RelativePath),
    )
    Rows = Db.ExecuteQuery(
        "SELECT StorageRootId, RelativePath FROM MediaFilesArchive WHERE Id = %s",
        (ArchiveId,),
    )
    assert len(Rows) == 1
    assert Path.FromRow(Rows[0]) == Sentinel


# directive: path-db-roundtrip-live | # see path.S7
def test_transcodequeue_round_trip(Db, StorageRootId, CleanupSentinels):
    """C4: TranscodeQueue INSERT -> SELECT -> Path.FromRow -> equal."""
    Rel = _Sentinel("mp4")
    Sentinel = Path(StorageRootId, Rel)
    LegacyForm = _SentinelLegacyForm(Rel)
    Filename = Rel.rsplit("/", 1)[-1]
    Directory = LegacyForm.rsplit("\\", 1)[0]
    Db.ExecuteNonQuery(
        "INSERT INTO TranscodeQueue (FilePath, Filename, Directory, SizeBytes, SizeMB, StorageRootId, RelativePath, Status) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)",
        (LegacyForm, Filename, Directory, 0, 0.0, Sentinel.StorageRootId, Sentinel.RelativePath, "SentinelTest"),
    )
    Rows = Db.ExecuteQuery(
        "SELECT StorageRootId, RelativePath FROM TranscodeQueue WHERE RelativePath = %s",
        (Rel,),
    )
    assert len(Rows) == 1
    assert Path.FromRow(Rows[0]) == Sentinel


# directive: path-db-roundtrip-live | # see path.S7
def test_transcodeattempts_round_trip(Db, StorageRootId, CleanupSentinels):
    """C5: TranscodeAttempts INSERT -> SELECT -> Path.FromRow -> equal."""
    Rel = _Sentinel("mp4")
    Sentinel = Path(StorageRootId, Rel)
    Db.ExecuteNonQuery(
        "INSERT INTO TranscodeAttempts (FilePath, StorageRootId, RelativePath) VALUES (%s, %s, %s)",
        (_SentinelLegacyForm(Rel), Sentinel.StorageRootId, Sentinel.RelativePath),
    )
    Rows = Db.ExecuteQuery(
        "SELECT StorageRootId, RelativePath FROM TranscodeAttempts WHERE RelativePath = %s",
        (Rel,),
    )
    assert len(Rows) == 1
    assert Path.FromRow(Rows[0]) == Sentinel


# directive: path-db-roundtrip-live | # see path.S7
def test_temporaryfilepaths_source_prefix(Db, StorageRootId, CleanupSentinels):
    """C6: TemporaryFilePaths Source pair INSERT -> SELECT -> Path.FromRow(prefix='Source') -> equal."""
    Rel = _Sentinel("mkv")
    Sentinel = Path(StorageRootId, Rel)
    Db.ExecuteNonQuery(
        "INSERT INTO TemporaryFilePaths (SourceStorageRootId, SourceRelativePath) VALUES (%s, %s)",
        (Sentinel.StorageRootId, Sentinel.RelativePath),
    )
    Rows = Db.ExecuteQuery(
        "SELECT SourceStorageRootId, SourceRelativePath FROM TemporaryFilePaths WHERE SourceRelativePath = %s",
        (Rel,),
    )
    assert len(Rows) == 1
    assert Path.FromRow(Rows[0], Prefix="Source") == Sentinel


# directive: path-db-roundtrip-live | # see path.S7
def test_temporaryfilepaths_output_prefix(Db, StorageRootId, CleanupSentinels):
    """C7: TemporaryFilePaths Output pair INSERT -> SELECT -> Path.FromRow(prefix='Output') -> equal."""
    Rel = _Sentinel("mp4")
    Sentinel = Path(StorageRootId, Rel)
    Db.ExecuteNonQuery(
        "INSERT INTO TemporaryFilePaths (OutputStorageRootId, OutputRelativePath) VALUES (%s, %s)",
        (Sentinel.StorageRootId, Sentinel.RelativePath),
    )
    Rows = Db.ExecuteQuery(
        "SELECT OutputStorageRootId, OutputRelativePath FROM TemporaryFilePaths WHERE OutputRelativePath = %s",
        (Rel,),
    )
    assert len(Rows) == 1
    assert Path.FromRow(Rows[0], Prefix="Output") == Sentinel


# directive: path-db-roundtrip-live | # see path.S7
def test_showsettings_round_trip(Db, StorageRootId, CleanupSentinels):
    """C8: ShowSettings INSERT -> SELECT -> Path.FromRow -> equal."""
    Rel = _Sentinel("folder")
    Sentinel = Path(StorageRootId, Rel)
    Db.ExecuteNonQuery(
        "INSERT INTO ShowSettings (ShowFolder, TargetResolution, StorageRootId, RelativePath) VALUES (%s, %s, %s, %s)",
        (_SentinelLegacyForm(Rel), "1080p", Sentinel.StorageRootId, Sentinel.RelativePath),
    )
    Rows = Db.ExecuteQuery(
        "SELECT StorageRootId, RelativePath FROM ShowSettings WHERE RelativePath = %s",
        (Rel,),
    )
    assert len(Rows) == 1
    assert Path.FromRow(Rows[0]) == Sentinel


# directive: path-db-roundtrip-live | # see path.D3
def test_null_typed_pair_returns_none_via_fromrow(Db, CleanupSentinels):
    """C9 / D3: a row with NULL typed-pair columns yields None from FromRow."""
    LegacyForm = _SentinelLegacyForm(_Sentinel("null"))
    Db.ExecuteNonQuery(
        "INSERT INTO MediaFiles (FilePath, StorageRootId, RelativePath) VALUES (%s, NULL, NULL)",
        (LegacyForm,),
    )
    Rows = Db.ExecuteQuery(
        "SELECT StorageRootId, RelativePath FROM MediaFiles WHERE FilePath = %s",
        (LegacyForm,),
    )
    assert len(Rows) == 1
    assert Path.FromRow(Rows[0]) is None


# directive: path-db-roundtrip-live | # see path.C10
def test_utf8_round_trip(Db, StorageRootId, CleanupSentinels):
    """C10: a UTF-8 RelativePath with multi-byte chars survives DB round-trip byte-equal."""
    Uniq = uuid.uuid4().hex[:8]
    Rel = f"{SENTINEL_PREFIX}/Cosmos Çafé - Épisode {Uniq} Â.mkv"
    Sentinel = Path(StorageRootId, Rel)
    Db.ExecuteNonQuery(
        "INSERT INTO MediaFiles (FilePath, StorageRootId, RelativePath) VALUES (%s, %s, %s)",
        (_SentinelLegacyForm(Rel), Sentinel.StorageRootId, Sentinel.RelativePath),
    )
    Rows = Db.ExecuteQuery(
        "SELECT StorageRootId, RelativePath FROM MediaFiles WHERE RelativePath = %s",
        (Rel,),
    )
    assert len(Rows) == 1
    Roundtripped = Path.FromRow(Rows[0])
    assert Roundtripped == Sentinel
    assert Roundtripped.RelativePath == Rel


_AUDIT_TABLES_FULL = [
    "MediaFiles",
    "MediaFilesArchive",
    "TranscodeQueue",
    "TranscodeAttempts",
    "ShowSettings",
]


@pytest.mark.parametrize("TableName", _AUDIT_TABLES_FULL)
# directive: path-db-roundtrip-live | # see path.C11
def test_positive_audit_100_rows(Db, TableName):
    """C11: 100 production rows with typed pair NOT NULL all parse via FromRow."""
    Rows = Db.ExecuteQuery(
        f"SELECT StorageRootId, RelativePath FROM {TableName} WHERE StorageRootId IS NOT NULL AND RelativePath IS NOT NULL LIMIT 100"
    )
    if not Rows:
        pytest.skip(f"{TableName} has zero rows with typed-pair populated")
    Failures = []
    for Row in Rows:
        try:
            Result = Path.FromRow(Row)
            if Result is None:
                Failures.append((Row, "FromRow returned None on non-NULL row"))
        except PathError as Exc:
            Failures.append((Row, f"PathError: {Exc}"))
    assert not Failures, f"{TableName}: {len(Failures)} parse failures: {Failures[:3]}"


# directive: path-db-roundtrip-live | # see path.C11
def test_positive_audit_temporaryfilepaths_source(Db):
    """C11 (TemporaryFilePaths Source): 100 production rows with Source typed pair NOT NULL all parse."""
    Rows = Db.ExecuteQuery(
        "SELECT SourceStorageRootId, SourceRelativePath FROM TemporaryFilePaths WHERE SourceStorageRootId IS NOT NULL AND SourceRelativePath IS NOT NULL LIMIT 100"
    )
    if not Rows:
        pytest.skip("TemporaryFilePaths has zero rows with Source typed pair populated")
    Failures = [(Row, "None") for Row in Rows if Path.FromRow(Row, Prefix="Source") is None]
    assert not Failures, f"TemporaryFilePaths Source: {len(Failures)} parse failures"


# directive: path-db-roundtrip-live | # see path.C11
def test_positive_audit_temporaryfilepaths_output(Db):
    """C11 (TemporaryFilePaths Output): 100 production rows with Output typed pair NOT NULL all parse."""
    Rows = Db.ExecuteQuery(
        "SELECT OutputStorageRootId, OutputRelativePath FROM TemporaryFilePaths WHERE OutputStorageRootId IS NOT NULL AND OutputRelativePath IS NOT NULL LIMIT 100"
    )
    if not Rows:
        pytest.skip("TemporaryFilePaths has zero rows with Output typed pair populated")
    Failures = [(Row, "None") for Row in Rows if Path.FromRow(Row, Prefix="Output") is None]
    assert not Failures, f"TemporaryFilePaths Output: {len(Failures)} parse failures"


@pytest.mark.parametrize("TableName", ["MediaFiles", "MediaFilesArchive", "TranscodeQueue", "TranscodeAttempts"])
# directive: path-db-roundtrip-live | # see path.C12
def test_null_branch_audit(Db, TableName):
    """C12: rows where one of the typed columns IS NULL yield None from FromRow (D3 branch)."""
    Rows = Db.ExecuteQuery(
        f"SELECT StorageRootId, RelativePath FROM {TableName} WHERE StorageRootId IS NULL OR RelativePath IS NULL LIMIT 10"
    )
    if not Rows:
        pytest.skip(f"{TableName} has zero rows with NULL typed pair")
    for Row in Rows:
        assert Path.FromRow(Row) is None, f"{TableName}: NULL row produced non-None Path: {Row!r}"


# directive: path-db-roundtrip-live | # see path.C13
def test_no_sentinel_rows_remain_after_suite(Db):
    """C13: after all tests, no sentinel rows remain in any of the 6 tables."""
    LikePattern = EscapeLikePattern(SENTINEL_PREFIX) + "%"
    Counts = {}
    for Table, Col in [
        ("MediaFiles", "RelativePath"),
        ("MediaFilesArchive", "RelativePath"),
        ("TranscodeQueue", "RelativePath"),
        ("TranscodeAttempts", "RelativePath"),
        ("ShowSettings", "RelativePath"),
    ]:
        Row = Db.ExecuteQuery(f"SELECT COUNT(*) AS cnt FROM {Table} WHERE {Col} LIKE %s ESCAPE '!'", (LikePattern,))
        Counts[Table] = Row[0]["cnt"]
    Row = Db.ExecuteQuery(
        "SELECT COUNT(*) AS cnt FROM TemporaryFilePaths WHERE SourceRelativePath LIKE %s ESCAPE '!' OR OutputRelativePath LIKE %s ESCAPE '!'",
        (LikePattern, LikePattern),
    )
    Counts["TemporaryFilePaths"] = Row[0]["cnt"]
    assert all(C == 0 for C in Counts.values()), f"sentinel rows leaked: {Counts}"
