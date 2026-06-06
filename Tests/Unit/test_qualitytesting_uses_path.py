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


# directive: path-class-perfection | # see path.C26
def test_business_service_constructor_injects_worker():
    """C26: __init__ sets _Worker via constructor-injection (default = Worker.Current()); no _StorageRoots field after AC #2 cache decomposition."""
    S = QualityTestingBusinessService(DatabaseManagerInstance=MagicMock())
    assert isinstance(S._Worker, Worker)
    assert not hasattr(S, '_StorageRoots')


# directive: qualitytesting-uses-path | # see path.S3
def test_get_worker_caches_across_calls():
    """C3: _GetWorker caches the Worker after first construction."""
    S = QualityTestingBusinessService(DatabaseManagerInstance=MagicMock())
    Sentinel = MagicMock(spec=Worker)
    S._Worker = Sentinel
    assert S._GetWorker() is Sentinel
    assert S._GetWorker() is Sentinel
