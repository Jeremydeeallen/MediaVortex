from Core.Path.Path import Path


# directive: path-class-implementation | # see path.C5
def test_returns_none_for_legacy_null_row():
    """C5: FromRow returns None for legacy rows with NULL StorageRootId or RelativePath."""
    assert Path.FromRow({"StorageRootId": None, "RelativePath": "x"}) is None
    assert Path.FromRow({"StorageRootId": 7, "RelativePath": None}) is None
    p = Path.FromRow({"StorageRootId": 7, "RelativePath": "Show/file.mkv"})
    assert p == Path(7, "Show/file.mkv")


# directive: path-class-implementation | # see path.S1
def test_reads_with_prefix():
    """S1: prefix='Output' reads OutputStorageRootId / OutputRelativePath columns."""
    row = {
        "StorageRootId": 7, "RelativePath": "Show/source.mkv",
        "OutputStorageRootId": 8, "OutputRelativePath": "Show/output.mkv",
    }
    src = Path.FromRow(row)
    dst = Path.FromRow(row, "Output")
    assert src == Path(7, "Show/source.mkv")
    assert dst == Path(8, "Show/output.mkv")
