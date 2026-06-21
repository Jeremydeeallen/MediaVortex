import re
import unittest
from pathlib import Path


_REPO = Path(__file__).resolve().parents[2]


# directive: vertical-column-ownership-test
_OWNERSHIP = {
    'AudioCompliant': 'Features/AudioNormalization',
    'AudioCompliantReason': 'Features/AudioNormalization',
    'VideoCompliant': 'Features/VideoEncoding',
    'VideoCompliantReason': 'Features/VideoEncoding',
    'ContainerCompliant': 'Features/ContainerFormat',
    'ContainerCompliantReason': 'Features/ContainerFormat',
}

# directive: vertical-column-ownership-test
_GENERATED_NEVER_WRITTEN = ('WorkBucket', 'IsCompliant')

# directive: vertical-column-ownership-test
_SCAN_ROOTS = ('Features', 'Repositories', 'Services', 'WebService', 'WorkerService', 'Core')

# directive: vertical-column-ownership-test
_EXCLUDE_DIRS = ('venv', '__pycache__', '.claude', 'Tests', 'Scripts', 'Templates')


# directive: vertical-column-ownership-test
def _IterPyFiles():
    for Root in _SCAN_ROOTS:
        RootPath = _REPO / Root
        if not RootPath.exists():
            continue
        for P in RootPath.rglob('*.py'):
            if any(Ex in P.parts for Ex in _EXCLUDE_DIRS):
                continue
            yield P


# directive: vertical-column-ownership-test
def _FindWritePatterns(FileText: str, Column: str):
    """Return list of (line_number, matched_text) where Column is being SET in SQL."""
    Hits = []
    Pat1 = re.compile(rf"\bSET\b[^\n]*\b{re.escape(Column)}\s*=", re.IGNORECASE)
    Pat2 = re.compile(rf"\b{re.escape(Column)}\s*=\s*v\.", re.IGNORECASE)
    for LineNo, Line in enumerate(FileText.splitlines(), start=1):
        if Pat1.search(Line) or Pat2.search(Line):
            Hits.append((LineNo, Line.strip()[:160]))
    return Hits


# directive: vertical-column-ownership-test
class TestVerticalColumnOwnership(unittest.TestCase):
    """Per-vertical compliance columns must be written only by the owning vertical. WorkBucket + IsCompliant are GENERATED columns -- no Python writes allowed."""

    # directive: vertical-column-ownership-test
    def test_per_vertical_columns_written_only_by_owner(self):
        Violations = []
        for P in _IterPyFiles():
            Text = P.read_text(encoding='utf-8', errors='replace')
            RelPath = str(P.relative_to(_REPO)).replace('\\', '/')
            for Col, OwnerDir in _OWNERSHIP.items():
                Hits = _FindWritePatterns(Text, Col)
                if not Hits:
                    continue
                if not RelPath.startswith(OwnerDir + '/') and not RelPath.startswith(OwnerDir.replace('/', '\\') + '\\'):
                    for LineNo, Snippet in Hits:
                        Violations.append(f"{RelPath}:{LineNo}  writes {Col}  (owner: {OwnerDir})  >>  {Snippet}")
        self.assertEqual([], Violations, "\nPer-vertical column writes outside owner vertical:\n" + "\n".join(Violations))

    # directive: vertical-column-ownership-test
    def test_generated_columns_never_written_by_python(self):
        Violations = []
        for P in _IterPyFiles():
            Text = P.read_text(encoding='utf-8', errors='replace')
            RelPath = str(P.relative_to(_REPO)).replace('\\', '/')
            for Col in _GENERATED_NEVER_WRITTEN:
                for LineNo, Snippet in _FindWritePatterns(Text, Col):
                    Violations.append(f"{RelPath}:{LineNo}  writes {Col}  (GENERATED; Postgres refuses)  >>  {Snippet}")
        self.assertEqual([], Violations, "\nGENERATED columns must never be set by Python:\n" + "\n".join(Violations))


if __name__ == '__main__':
    unittest.main()
