from Core.Path.Path import Path


# directive: path-class-implementation | # see path.C1
def test_equal_when_typed_pair_matches():
    """C1: equality by (StorageRootId, RelativePath) tuple."""
    a = Path(7, "Show/file.mkv")
    b = Path(7, "Show/file.mkv")
    assert a == b
    assert {a, b} == {a}


# directive: path-class-implementation | # see path.C2
def test_case_sensitive_on_relative_path():
    """C2/D2: case-sensitive identity on RelativePath."""
    a = Path(7, "Show/file.mkv")
    b = Path(7, "show/FILE.MKV")
    assert a != b


# directive: path-class-implementation | # see path.C3
def test_storage_root_part_of_identity():
    """C3: StorageRootId is part of identity."""
    a = Path(7, "Show/file.mkv")
    b = Path(8, "Show/file.mkv")
    assert a != b
