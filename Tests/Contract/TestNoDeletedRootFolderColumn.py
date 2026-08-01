# see scan-broken-restore -- prevents regression of the retired `RootFolders.RootFolder` column reference that broke scanning 2026-07-31.
import re
import subprocess
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
PATTERN = re.compile(r'\bFROM\s+RootFolders\b.*?\bRootFolder\b', re.IGNORECASE)
BAD_SELECT = re.compile(r'SELECT\s+RootFolder\s+FROM\s+RootFolders\b', re.IGNORECASE)

SCAN_DIRS = ('Features', 'Core', 'Services', 'WorkerService', 'WebService', 'Scripts', 'Repositories')


def _TrackedFiles():
    R = subprocess.run(
        ['git', '-C', str(REPO_ROOT), 'ls-files'],
        capture_output=True, text=True, timeout=30,
    )
    if R.returncode != 0:
        raise RuntimeError(f'git ls-files failed: {R.stderr}')
    return [L.strip() for L in R.stdout.splitlines() if L.strip()]


class TestNoDeletedRootFolderColumn(unittest.TestCase):

    def test_no_select_rootfolder_from_rootfolders(self):
        Offenders = []
        for RelPath in _TrackedFiles():
            if not RelPath.endswith('.py'):
                continue
            if not any(RelPath.replace('\\', '/').startswith(D + '/') for D in SCAN_DIRS):
                continue
            AbsPath = REPO_ROOT / RelPath
            try:
                Content = AbsPath.read_text(encoding='utf-8', errors='replace')
            except Exception:
                continue
            for I, Line in enumerate(Content.splitlines(), start=1):
                if BAD_SELECT.search(Line):
                    Offenders.append(f'{RelPath}:{I}: {Line.strip()[:200]}')
        self.assertEqual(
            [], Offenders,
            'SELECT RootFolder FROM RootFolders is retired -- column no longer exists. '
            'Use StorageRootId + RelativePath instead.\n  '
            + '\n  '.join(Offenders)
        )


if __name__ == '__main__':
    unittest.main()
