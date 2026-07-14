import re
import sys
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO_ROOT))

DEPLOY_DIR = REPO_ROOT / 'deploy'
STARTUP_FILES = [REPO_ROOT / 'StartMediaVortex.py', REPO_ROOT / 'StopMediaVortex.py']

PIP_INSTALL_RE = re.compile(r'pip\s+install\b[^\n]*', re.IGNORECASE)
ALLOWED_MARKERS = ('-r ', 'requirements.txt', '--upgrade pip', 'torch')


def _AuditFile(Path):
    Bad = []
    Lines = Path.read_text(encoding='utf-8').splitlines()
    for I, Line in enumerate(Lines, start=1):
        Stripped = Line.strip()
        if Stripped.startswith('#') or Stripped.startswith('//'):
            continue
        M = PIP_INSTALL_RE.search(Line)
        if not M:
            continue
        WithContext = ' '.join(Lines[I - 1:min(I - 1 + 20, len(Lines))])
        if any(Marker in WithContext for Marker in ALLOWED_MARKERS):
            continue
        Bad.append(f'{Path.relative_to(REPO_ROOT)}:{I}: {Stripped}')
    return Bad


class TestDeployPipInstallsRequirementsTxt(unittest.TestCase):

    def test_no_hand_picked_pip_installs(self):
        Offenders = []
        for P in DEPLOY_DIR.rglob('*'):
            if not P.is_file():
                continue
            if P.suffix in ('.py',) or P.name == 'Dockerfile':
                Offenders.extend(_AuditFile(P))
        for P in STARTUP_FILES:
            if P.exists():
                Offenders.extend(_AuditFile(P))
        self.assertEqual(
            [], Offenders,
            'Hand-picked pip install (no -r requirements) found. Route through pip install -r <requirements.txt>. Torch is the only exception.\n  '
            + '\n  '.join(Offenders),
        )


if __name__ == '__main__':
    unittest.main()
