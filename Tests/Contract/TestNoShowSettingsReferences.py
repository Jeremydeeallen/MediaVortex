import os
import unittest
from pathlib import Path


# directive: work-transcode-unified | # see work-bucket.C11
class TestNoShowSettingsReferences(unittest.TestCase):
    """Audit -- no surviving references to the deleted ShowSettings vertical (incl. deprecated markers)."""

    ROOT = Path(__file__).resolve().parent.parent.parent

    SCAN_DIRS = ['Features', 'Templates', 'WebService', 'Core', 'Services', 'Repositories', 'Models']

    EXEMPT_FILES = {
        'Scripts/SQLScripts/CreateSeriesProfilesAndDeprecateShowSettings.py',
        'Scripts/SQLScripts/DeprecateSmartPopulateIndex.py',
        'Scripts/SQLScripts/DropDeprecatedShowSettingsArtifacts.py',
        'Tests/Contract/TestNoShowSettingsReferences.py',
    }

    NEEDLES = [
        'ShowSettings',
        '/api/ShowSettings/',
        'Features/ShowSettings/',
        'smart-populate',
        'remux-populate-card',
        'ShowSettings_DEPRECATED_',
        'idx_mediafiles_smartpopulate',
    ]

    # directive: work-transcode-unified | # see work-bucket.C11
    def test_no_references_in_production_tree(self):
        Violations = []
        for D in self.SCAN_DIRS:
            Root = self.ROOT / D
            if not Root.exists():
                continue
            for P in Root.rglob('*'):
                if not P.is_file():
                    continue
                if P.suffix not in ('.py', '.html', '.md', '.feature', '.flow'):
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
                for N in self.NEEDLES:
                    if N in Text:
                        Violations.append(f"{Rel}: contains {N!r}")
                        break
        if Violations:
            self.fail("Surviving ShowSettings references:\n  " + "\n  ".join(Violations))


if __name__ == '__main__':
    unittest.main()
