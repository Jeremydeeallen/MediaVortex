import pytest
from Core.Path.Path import Path, PathError


# directive: path-class-implementation | # see path.C12
def test_parentdir_join_lastsegment_identity():
    """C12: p.ParentDir().Join(p.LastSegment()) == p for any non-root Path."""
    p = Path(7, "Show/Season 1/file.mkv")
    assert p.ParentDir().Join(p.LastSegment()) == p
    p2 = Path(7, "file.mkv")
    assert p2.ParentDir().Join(p2.LastSegment()) == p2


# directive: path-class-implementation | # see path.C13
def test_parentdir_at_root_raises():
    """C13: Path(7, '') is root; ParentDir raises."""
    root = Path(7, "")
    with pytest.raises(PathError):
        root.ParentDir()


# directive: path-class-implementation | # see path.C14
def test_splitext():
    """C14: SplitExt returns (Path-without-ext, '.ext'); extensionless -> (self, '')."""
    p = Path(7, "Show/file.mkv")
    root, ext = p.SplitExt()
    assert root == Path(7, "Show/file")
    assert ext == ".mkv"
    p2 = Path(7, "Show/README")
    root2, ext2 = p2.SplitExt()
    assert root2 == p2
    assert ext2 == ""
    p3 = Path(7, "Show/.env")
    root3, ext3 = p3.SplitExt()
    assert root3 == p3
    assert ext3 == ""
