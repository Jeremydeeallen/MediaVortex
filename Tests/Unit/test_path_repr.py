from Core.Path.Path import Path


# directive: path-class-implementation | # see path.C11
def test_exact_shape():
    """C11 / D7 / D8: repr and str are exactly '<Path #<id>:<rel>>'; no variation between runs."""
    p = Path(7, "Show/file.mkv")
    assert repr(p) == "<Path #7:Show/file.mkv>"
    assert str(p) == "<Path #7:Show/file.mkv>"
    root = Path(7, "")
    assert repr(root) == "<Path #7:>"
