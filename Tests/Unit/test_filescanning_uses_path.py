# directive: filescanning-uses-path | # see path.S5
import re
from pathlib import Path as PyPath


_FS_DIR = PyPath(__file__).resolve().parent.parent.parent / "Features" / "FileScanning"
_OS_PATH_VAR_RX = re.compile(r"(?i)os\.path\.(exists|isfile|isdir|getsize|getmtime|dirname|basename|join|split|splitext)\s*\(\s*\w*(?:path|filepath)\w*")


# directive: filescanning-uses-path | # see path.S5
def test_no_pathstorage_import_in_filescanning():
    """C1: zero Core.PathStorage references in Features/FileScanning/."""
    Offenders = []
    for File in _FS_DIR.rglob("*.py"):
        Src = File.read_text(encoding="utf-8")
        if "Core.PathStorage" in Src:
            Offenders.append(str(File))
    assert not Offenders, f"FileScanning reintroduced Core.PathStorage: {Offenders}"


# directive: filescanning-uses-path | # see path.S5
def test_no_os_path_on_path_variable_in_filescanning():
    """C8: no os.path.<op>(<path-named var>) callsites in Features/FileScanning/."""
    Offenders = []
    for File in _FS_DIR.rglob("*.py"):
        Src = File.read_text(encoding="utf-8")
        for LineNo, Line in enumerate(Src.splitlines(), start=1):
            if _OS_PATH_VAR_RX.search(Line):
                Offenders.append(f"{File}:{LineNo}: {Line.strip()}")
    assert not Offenders, f"FileScanning has os.path on path-named vars: {Offenders}"


# directive: filescanning-uses-path | # see path.S3
def test_module_helpers_present_in_businessservice():
    """C2: BusinessService module exposes the lazy Worker + StorageRoots helpers used throughout the vertical."""
    from Features.FileScanning import FileScanningBusinessService as Mod
    assert callable(getattr(Mod, "_GetWorker", None))
    assert callable(getattr(Mod, "_GetStorageRoots", None))
    assert callable(getattr(Mod, "_LocalExists", None))
    assert callable(getattr(Mod, "_LocalIsDir", None))
    assert callable(getattr(Mod, "_Exists", None))
    assert callable(getattr(Mod, "_LastSegment", None))
    assert callable(getattr(Mod, "_ParentDir", None))
