# directive: filereplacement-uses-path | # see path.S5
import re
from pathlib import Path as PyPath
from unittest.mock import MagicMock

import pytest

from Features.FileReplacement.FileReplacementBusinessService import FileReplacementBusinessService
from Features.FileReplacement.TranscodedOutputPlacement import TranscodedOutputPlacement
from Core.Path import Worker


_FR_DIR = PyPath(__file__).resolve().parent.parent.parent / "Features" / "FileReplacement"
_OS_PATH_VAR_RX = re.compile(r"(?i)os\.path\.(exists|isfile|isdir|getsize|getmtime|dirname|basename|join|split|splitext)\s*\(\s*\w*(?:path|filepath)\w*")


# directive: filereplacement-uses-path | # see path.S5
def test_no_pathstorage_import_in_filereplacement():
    """C1: zero Core.PathStorage references in Features/FileReplacement/."""
    Offenders = []
    for File in _FR_DIR.rglob("*.py"):
        Src = File.read_text(encoding="utf-8")
        if "Core.PathStorage" in Src:
            Offenders.append(str(File))
    assert not Offenders, f"FileReplacement reintroduced Core.PathStorage: {Offenders}"


# directive: filereplacement-uses-path | # see path.S5
def test_no_os_path_on_path_variable_in_filereplacement():
    """C5: no os.path.<op>(<path-named var>) callsites."""
    Offenders = []
    for File in _FR_DIR.rglob("*.py"):
        Src = File.read_text(encoding="utf-8")
        for LineNo, Line in enumerate(Src.splitlines(), start=1):
            if _OS_PATH_VAR_RX.search(Line):
                Offenders.append(f"{File}:{LineNo}: {Line.strip()}")
    assert not Offenders, f"FileReplacement has os.path on path-named vars: {Offenders}"


# directive: filereplacement-uses-path | # see path.S3
def test_business_service_initializes_lazy_state():
    """C2: __init__ initializes _Worker and _StorageRoots to None."""
    S = FileReplacementBusinessService(DatabaseManagerInstance=MagicMock())
    assert S._Worker is None
    assert S._StorageRoots is None
    assert S._StorageRootPrefixMap is None


# directive: filereplacement-uses-path | # see path.S3
def test_transcoded_output_placement_initializes_lazy_state():
    """C2: TranscodedOutputPlacement also has lazy Worker/StorageRoots state."""
    T = TranscodedOutputPlacement(DatabaseManagerInstance=MagicMock())
    assert T._Worker is None
    assert T._StorageRoots is None


# directive: filereplacement-uses-path | # see path.S5
def test_business_service_canonical_for_uses_prefix_map():
    """C4: _CanonicalFor builds a display string from the cached prefix map."""
    S = FileReplacementBusinessService(DatabaseManagerInstance=MagicMock())
    S._StorageRoots = [{"Id": 1, "CanonicalPrefix": "T:\\"}, {"Id": 2, "CanonicalPrefix": "M:\\"}]
    Result = S._CanonicalFor(1, "Show/file.mkv")
    assert Result == "T:\\Show\\file.mkv"


# directive: filereplacement-uses-path | # see path.C2
def test_paths_equal_helper():
    """C6: _PathsEqual normalizes backslashes and case-folds."""
    T = TranscodedOutputPlacement(DatabaseManagerInstance=MagicMock())
    assert T._PathsEqual("T:\\Show\\file.mkv", "T:/show/FILE.MKV")
    assert not T._PathsEqual("T:\\Show\\a.mkv", "T:\\Show\\b.mkv")
    assert T._PathsEqual(None, None)
