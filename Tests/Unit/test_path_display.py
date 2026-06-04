from Core.Path.Path import Path


PREFIXES = {1: "T:\\", 2: "\\\\10.0.0.61\\xxx\\"}


# directive: path-class-implementation | # see path.S8
def test_resolved_prefix():
    """S8: CanonicalDisplay joins prefix + RelativePath (backslash form)."""
    p = Path(1, "Show/file.mkv")
    assert p.CanonicalDisplay(PREFIXES) == r"T:\Show\file.mkv"
    p2 = Path(2, "Show/file.mkv")
    assert p2.CanonicalDisplay(PREFIXES) == r"\\10.0.0.61\xxx\Show\file.mkv"


# directive: path-class-implementation | # see path.S8
def test_orphan_marker():
    """S8: orphan StorageRoot renders as '[orphan #<id>] <rel>'."""
    p = Path(99, "Show/file.mkv")
    assert p.CanonicalDisplay(PREFIXES) == "[orphan #99] Show/file.mkv"
