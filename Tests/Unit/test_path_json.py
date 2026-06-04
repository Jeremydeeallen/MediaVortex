from Core.Path.Path import Path


# directive: path-class-implementation | # see path.C7
def test_round_trip():
    """C7: Path -> ToJsonDict -> FromJsonDict round-trips."""
    original = Path(7, "Show/file.mkv")
    assert Path.FromJsonDict(original.ToJsonDict()) == original
    root = Path(7, "")
    assert Path.FromJsonDict(root.ToJsonDict()) == root


# directive: path-class-implementation | # see path.S2
def test_shape_stable():
    """S2 / D6: ToJsonDict shape is exactly {StorageRootId, RelativePath}, no extras."""
    p = Path(7, "Show/file.mkv")
    d = p.ToJsonDict()
    assert set(d.keys()) == {"StorageRootId", "RelativePath"}
    assert d["StorageRootId"] == 7
    assert d["RelativePath"] == "Show/file.mkv"
    assert isinstance(d["StorageRootId"], int)
    assert isinstance(d["RelativePath"], str)
