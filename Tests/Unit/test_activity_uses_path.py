# directive: activity-uses-path | # see path.S3
import re
from pathlib import Path as PyPath


_ACTIVITY_DIR = PyPath(__file__).resolve().parent.parent.parent / "Features" / "Activity"
_OS_PATH_VAR_RX = re.compile(r"(?i)os\.path\.(exists|isfile|isdir|getsize|getmtime|dirname|basename|join|split|splitext)\s*\(\s*\w*(?:path|filepath)\w*")


# directive: activity-uses-path | # see path.S3
def _IterActivitySources():
    """Yield every .py source under Features/Activity/ with its text."""
    for File in _ACTIVITY_DIR.rglob("*.py"):
        yield File, File.read_text(encoding="utf-8")


# directive: activity-uses-path | # see path.S3
def test_no_pathstorage_import_in_activity():
    """C1: zero references to Core.PathStorage in Features/Activity/."""
    Offenders = []
    for File, Src in _IterActivitySources():
        if "Core.PathStorage" in Src:
            Offenders.append(str(File))
    assert not Offenders, f"Activity reintroduced Core.PathStorage references: {Offenders}"


# directive: activity-uses-path | # see path.S3
def test_no_os_path_on_path_variable_in_activity():
    """C1: zero os.path.<op>(<path-named var>) calls in Features/Activity/."""
    Offenders = []
    for File, Src in _IterActivitySources():
        for LineNo, Line in enumerate(Src.splitlines(), start=1):
            if _OS_PATH_VAR_RX.search(Line):
                Offenders.append(f"{File}:{LineNo}: {Line.strip()}")
    assert not Offenders, f"Activity reintroduced os.path on path-named variables: {Offenders}"
