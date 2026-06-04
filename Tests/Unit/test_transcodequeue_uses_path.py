# directive: transcodequeue-uses-path | # see path.S5
import re
from pathlib import Path as PyPath


_TQ_DIR = PyPath(__file__).resolve().parent.parent.parent / "Features" / "TranscodeQueue"
_OS_PATH_VAR_RX = re.compile(r"(?i)os\.path\.(exists|isfile|isdir|getsize|getmtime|dirname|basename|join|split|splitext)\s*\(\s*\w*(?:path|filepath)\w*")


# directive: transcodequeue-uses-path | # see path.S5
def test_no_pathstorage_import_in_transcodequeue():
    """C1: zero Core.PathStorage references in Features/TranscodeQueue/."""
    Offenders = []
    for File in _TQ_DIR.rglob("*.py"):
        Src = File.read_text(encoding="utf-8")
        if "Core.PathStorage" in Src:
            Offenders.append(str(File))
    assert not Offenders, f"TranscodeQueue reintroduced Core.PathStorage: {Offenders}"


# directive: transcodequeue-uses-path | # see path.S5
def test_no_os_path_on_path_variable_in_transcodequeue():
    """C4: no os.path.<op>(<path-named var>) callsites in Features/TranscodeQueue/."""
    Offenders = []
    for File in _TQ_DIR.rglob("*.py"):
        Src = File.read_text(encoding="utf-8")
        for LineNo, Line in enumerate(Src.splitlines(), start=1):
            if _OS_PATH_VAR_RX.search(Line):
                Offenders.append(f"{File}:{LineNo}: {Line.strip()}")
    assert not Offenders, f"TranscodeQueue has os.path on path-named vars: {Offenders}"
