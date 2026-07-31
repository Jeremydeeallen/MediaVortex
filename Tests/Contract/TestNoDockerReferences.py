# see docker-purge -- enforces the baremetal-only invariant: no docker references in active tree
import re
import subprocess
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
PATTERN = re.compile(r'docker', re.IGNORECASE)

WHITELIST_DIRS = {
    '.claude/directives/closed',
    'memory/KNOWN-ISSUES-ARCHIVE.md',
    'Reports',
    'Scripts/SQLScripts/backups',
    'Static/vendor',
    'Static/webfonts',
    '.git',
    'venv',
    'WebService/venv',
    'WorkerService/venv',
    '__pycache__',
    'node_modules',
}

WHITELIST_FILES = {
    'Tests/Contract/TestNoDockerReferences.py',
    '.claude/directive.md',
    '.claude/current-feature',
}


def _IsWhitelisted(RelPath: str) -> bool:
    Normalized = RelPath.replace('\\', '/')
    if Normalized in WHITELIST_FILES:
        return True
    for D in WHITELIST_DIRS:
        if Normalized == D or Normalized.startswith(D + '/'):
            return True
    return False


def _TrackedFiles():
    R = subprocess.run(
        ['git', '-C', str(REPO_ROOT), 'ls-files'],
        capture_output=True, text=True, timeout=30,
    )
    if R.returncode != 0:
        raise RuntimeError(f'git ls-files failed: {R.stderr}')
    return [L.strip() for L in R.stdout.splitlines() if L.strip()]


class TestNoDockerReferences(unittest.TestCase):

    def test_no_docker_references_in_active_tree(self):
        Offenders = []
        for RelPath in _TrackedFiles():
            if _IsWhitelisted(RelPath):
                continue
            AbsPath = REPO_ROOT / RelPath
            if not AbsPath.is_file():
                continue
            try:
                Content = AbsPath.read_text(encoding='utf-8', errors='replace')
            except Exception:
                continue
            for I, Line in enumerate(Content.splitlines(), start=1):
                if PATTERN.search(Line):
                    if re.search(r'docker(?!y)', Line, re.IGNORECASE) is None:
                        continue
                    Offenders.append(f'{RelPath}:{I}: {Line.strip()[:200]}')
        self.assertEqual(
            [], Offenders,
            'Docker references found in active tree. MediaVortex is baremetal-only.\n  '
            + '\n  '.join(Offenders[:50])
            + (f'\n  ... ({len(Offenders) - 50} more)' if len(Offenders) > 50 else '')
        )


if __name__ == '__main__':
    unittest.main()
