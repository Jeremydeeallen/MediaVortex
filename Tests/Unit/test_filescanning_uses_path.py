# directive: path-class-perfection | # see path.C26
import re
from pathlib import Path as PyPath


_FS_DIR = PyPath(__file__).resolve().parent.parent.parent / "Features" / "FileScanning"
_OS_PATH_VAR_RX = re.compile(r"(?i)os\.path\.(exists|isfile|isdir|getsize|getmtime|dirname|basename|join|split|splitext)\s*\(\s*\w*(?:path|filepath)\w*")


# directive: path-class-perfection | # see path.C26
def test_no_pathstorage_import_in_filescanning():
    """Regression-guard: zero Core.PathStorage references (the legacy v1 module deleted by path-perfect-implementation)."""
    Offenders = []
    for File in _FS_DIR.rglob("*.py"):
        Src = File.read_text(encoding="utf-8")
        if "Core.PathStorage" in Src:
            Offenders.append(str(File))
    assert not Offenders, f"FileScanning reintroduced Core.PathStorage: {Offenders}"


# directive: path-class-perfection | # see path.C26
def test_no_os_path_on_path_variable_in_filescanning():
    """R6 regression-guard: no os.path.<op>(<path-named var>) callsites."""
    Offenders = []
    for File in _FS_DIR.rglob("*.py"):
        Src = File.read_text(encoding="utf-8")
        for LineNo, Line in enumerate(Src.splitlines(), start=1):
            if _OS_PATH_VAR_RX.search(Line):
                Offenders.append(f"{File}:{LineNo}: {Line.strip()}")
    assert not Offenders, f"FileScanning has os.path on path-named vars: {Offenders}"
