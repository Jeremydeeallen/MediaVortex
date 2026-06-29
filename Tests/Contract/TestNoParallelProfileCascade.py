import os
import unittest
from pathlib import Path


# directive: transcode-worker-unification | # see profiles.C23
class TestNoParallelProfileCascade(unittest.TestCase):
    """Audit -- only EffectiveProfileResolver may read MediaFiles.AssignedProfile + SystemSettings('DefaultProfileName') in the same function scope."""

    ROOT = Path(__file__).resolve().parent.parent.parent

    SCAN_DIRS = ['Features', 'Templates', 'WebService', 'Core', 'Services', 'Repositories', 'Models']

    EXEMPT_FILES = {
        'Features/Profiles/EffectiveProfileResolver.py',  # canonical home of the cascade
        'Tests/Contract/TestNoParallelProfileCascade.py',  # this test
        'Features/SystemSettings/SystemSettingsController.py',  # AssignedProfile appears only in a description string, not cascade logic
    }

    # directive: transcode-worker-unification | # see profiles.C23
    def test_no_parallel_cascade_implementations(self):
        # see profiles.C23
        Violations = []
        for D in self.SCAN_DIRS:
            Root = self.ROOT / D
            if not Root.exists():
                continue
            for P in Root.rglob('*'):
                if not P.is_file() or P.suffix not in ('.py',):
                    continue
                Rel = str(P.relative_to(self.ROOT)).replace('\\', '/')
                if Rel in self.EXEMPT_FILES:
                    continue
                if '/__pycache__/' in Rel or Rel.endswith('.pyc'):
                    continue
                try:
                    Text = P.read_text(encoding='utf-8', errors='ignore')
                except Exception:
                    continue
                if 'AssignedProfile' in Text and 'DefaultProfileName' in Text:
                    Violations.append(Rel)
        if Violations:
            self.fail(
                "Parallel profile cascade detected in: " + ', '.join(Violations) +
                ". Only EffectiveProfileResolver may consume both fields in the same scope. "
                "Inject EffectiveProfileResolver and call .Resolve(mediafile) instead."
            )


if __name__ == '__main__':
    unittest.main()
