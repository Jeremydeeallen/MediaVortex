from Core.Path.Path import Path


# directive: path-class-implementation | # see path.C1
def test_usable_in_set_and_dict():
    """C1: hashable, usable as dict key and set member; equal Paths collapse."""
    a = Path(7, "Show/file.mkv")
    b = Path(7, "Show/file.mkv")
    c = Path(8, "Show/file.mkv")
    assert hash(a) == hash(b)
    assert len({a, b, c}) == 2
    d = {a: "movie"}
    d[b] = "movie2"
    assert d[Path(7, "Show/file.mkv")] == "movie2"
    assert len(d) == 1
    d[c] = "different"
    assert len(d) == 2
