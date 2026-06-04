import pytest
from Core.Path.Path import Path, PathError


ROOTS = [
    {"Id": 1, "CanonicalPrefix": "\\\\10.0.0.61\\xxx\\"},
    {"Id": 2, "CanonicalPrefix": "T:\\"},
    {"Id": 3, "CanonicalPrefix": "/mnt/media_tv/"},
    {"Id": 4, "CanonicalPrefix": "Z:\\"},
]


# directive: path-class-implementation | # see path.S6
def test_parses_unc():
    """S6: UNC shape parses against UNC prefix."""
    p = Path.FromLegacyString(r"\\10.0.0.61\xxx\Show\file.mkv", ROOTS)
    assert p == Path(1, "Show/file.mkv")


# directive: path-class-implementation | # see path.S6
def test_parses_windows_drive():
    """S6: Windows-drive shape parses against drive prefix."""
    p = Path.FromLegacyString(r"T:\Show\file.mkv", ROOTS)
    assert p == Path(2, "Show/file.mkv")


# directive: path-class-implementation | # see path.S6
def test_parses_posix():
    """S6: POSIX shape parses against POSIX prefix."""
    p = Path.FromLegacyString("/mnt/media_tv/Show/file.mkv", ROOTS)
    assert p == Path(3, "Show/file.mkv")


# directive: path-class-implementation | # see path.S6
def test_longest_prefix_wins():
    """S6 / D10: longest-prefix wins (caller sorts; UNC prefix is longer than T:\\ prefix)."""
    sorted_roots = sorted(ROOTS, key=lambda r: len(r["CanonicalPrefix"]), reverse=True)
    p = Path.FromLegacyString(r"\\10.0.0.61\xxx\file.mkv", sorted_roots)
    assert p.StorageRootId == 1


# directive: path-class-implementation | # see path.S6
def test_no_match_raises():
    """S6 / D10: empty input or no-prefix-match raises PathError."""
    with pytest.raises(PathError):
        Path.FromLegacyString("", ROOTS)
    with pytest.raises(PathError):
        Path.FromLegacyString(r"X:\unrecognized\path.mkv", ROOTS)
