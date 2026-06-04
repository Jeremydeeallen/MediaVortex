# directive: qualitytesting-uses-path | # see path.S5
import re
from pathlib import Path as PyPath
from unittest.mock import MagicMock

import pytest

from Features.QualityTesting.QualityTestingBusinessService import QualityTestingBusinessService
from Core.Path import Path, Worker


_QT_DIR = PyPath(__file__).resolve().parent.parent.parent / "Features" / "QualityTesting"
_OS_PATH_VAR_RX = re.compile(r"(?i)os\.path\.(exists|isfile|isdir|getsize|getmtime|dirname|basename|join|split|splitext)\s*\(\s*\w*(?:path|filepath)\w*")


# directive: qualitytesting-uses-path | # see path.S5
def test_no_pathstorage_import_in_qualitytesting():
    """C1: zero Core.PathStorage references in Features/QualityTesting/."""
    Offenders = []
    for File in _QT_DIR.rglob("*.py"):
        Src = File.read_text(encoding="utf-8")
        if "Core.PathStorage" in Src:
            Offenders.append(str(File))
    assert not Offenders, f"QualityTesting reintroduced Core.PathStorage: {Offenders}"


# directive: qualitytesting-uses-path | # see path.S5
def test_no_os_path_on_path_variable_in_qualitytesting():
    """C6: no os.path.<op>(<path-named var>) callsites in Features/QualityTesting/."""
    Offenders = []
    for File in _QT_DIR.rglob("*.py"):
        Src = File.read_text(encoding="utf-8")
        for LineNo, Line in enumerate(Src.splitlines(), start=1):
            if _OS_PATH_VAR_RX.search(Line):
                Offenders.append(f"{File}:{LineNo}: {Line.strip()}")
    assert not Offenders, f"QualityTesting has os.path on path-named vars: {Offenders}"


# directive: qualitytesting-uses-path | # see path.S3
def test_business_service_initializes_lazy_state():
    """C3-C4: __init__ initializes _Worker and _StorageRoots to None for lazy construction."""
    S = QualityTestingBusinessService(DatabaseManagerInstance=MagicMock())
    assert S._Worker is None
    assert S._StorageRoots is None


# directive: qualitytesting-uses-path | # see path.S3
def test_get_worker_caches_across_calls():
    """C3: _GetWorker caches the Worker after first construction."""
    S = QualityTestingBusinessService(DatabaseManagerInstance=MagicMock())
    Sentinel = MagicMock(spec=Worker)
    S._Worker = Sentinel
    assert S._GetWorker() is Sentinel
    assert S._GetWorker() is Sentinel
