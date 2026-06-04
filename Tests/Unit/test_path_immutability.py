import pytest
from dataclasses import FrozenInstanceError
from Core.Path.Path import Path


# directive: path-class-implementation | # see path.C15
def test_setattr_raises():
    """C15: Path is frozen; setattr on existing field raises."""
    p = Path(7, "Show/file.mkv")
    with pytest.raises((FrozenInstanceError, AttributeError)):
        p.RelativePath = "x"
    with pytest.raises((FrozenInstanceError, AttributeError)):
        p.StorageRootId = 8
