import pytest
from Core.Path.Path import Path, PathError


# directive: path-class-implementation | # see path.C4
def test_strict_constructor_rejects_invalid():
    """C4: invalid inputs raise PathError at construction (empty RelativePath is the root per C13)."""
    with pytest.raises(PathError):
        Path(None, "x")
    with pytest.raises(PathError):
        Path(7, None)
    with pytest.raises(PathError):
        Path(7, "/abs/path")
    with pytest.raises(PathError):
        Path(7, "..\\escape")
    with pytest.raises(PathError):
        Path(7, "../escape")
    with pytest.raises(PathError):
        Path(7, "ok/../escape")
    with pytest.raises(PathError):
        Path("seven", "x")
    with pytest.raises(PathError):
        Path(True, "x")


# directive: path-class-implementation | # see path.C4
def test_relative_path_normalized():
    """C4 / D9: backslashes -> forward slashes, leading separators rejected, case preserved."""
    p = Path(7, "Show\\Season 1\\file.mkv")
    assert p.RelativePath == "Show/Season 1/file.mkv"
    p2 = Path(7, "MixedCASE/File.MKV")
    assert p2.RelativePath == "MixedCASE/File.MKV"
    p3 = Path(7, "")
    assert p3.RelativePath == ""
