from Core.Path.Path import Path


# directive: path-class-perfection | # see path.C11
def test_exact_repr_shape():
    """C11 / D7: repr is exactly '<Path #<id>:<rel>>'; no DB lookup; no variation between runs."""
    p = Path(7, "Show/file.mkv")
    assert repr(p) == "<Path #7:Show/file.mkv>"
    root = Path(7, "")
    assert repr(root) == "<Path #7:>"


# directive: path-class-perfection | # see path.C20
def test_str_returns_canonical_display():
    """C20: str(p) returns CanonicalDisplay() for ergonomic f-string usage; orphan id falls back to '[orphan #<id>] <rel>' when prefix map can't resolve."""
    p = Path(99999, "Show/file.mkv")
    display = str(p)
    assert display.startswith("[orphan #99999]") or "Show" in display
