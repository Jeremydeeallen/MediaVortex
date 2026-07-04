# directive: transcode-flow-canonical | # see transcode.ST7
import re
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]

PRODUCTION_DIRS = ('Features', 'Workers', 'WorkerService', 'WebService', 'Repositories', 'Core')

FORBIDDEN_LITERALS = ("'NoReplace'", '"NoReplace"', "'Discard'", '"Discard"', "'BypassReplace'", '"BypassReplace"')

WHITELIST_PY_SUBSTR = (
    'Scripts/SQLScripts/',
    'Scripts\\SQLScripts\\',
    'Tests/Contract/TestDispositionEnumClosed.py',
    'Tests\\Contract\\TestDispositionEnumClosed.py',
    'Tests/Contract/TestNoBypassReplace.py',
    'Tests\\Contract\\TestNoBypassReplace.py',
)


# directive: transcode-flow-canonical | # see transcode.ST7
class TestDispositionEnumClosed(unittest.TestCase):

    # directive: transcode-flow-canonical | # see transcode.ST7
    def test_no_forbidden_disposition_literals_in_production(self):
        """Production code must use only {Pending, Replace, Reject, Requeue}. NoReplace / Discard / BypassReplace retired."""
        Hits = []
        for Sub in PRODUCTION_DIRS:
            Root = REPO_ROOT / Sub
            if not Root.exists():
                continue
            for Py in Root.rglob('*.py'):
                Rel = str(Py).replace('\\', '/')
                if any(W.replace('\\', '/') in Rel for W in WHITELIST_PY_SUBSTR):
                    continue
                Text = Py.read_text(encoding='utf-8', errors='replace')
                for LineNo, Line in enumerate(Text.splitlines(), start=1):
                    for Lit in FORBIDDEN_LITERALS:
                        if Lit in Line:
                            Hits.append(f"{Py.relative_to(REPO_ROOT)}:{LineNo}: {Lit} -> {Line.strip()[:180]}")
        self.assertEqual([], Hits, "Retired disposition literal found in production Python:\n" + '\n'.join(Hits))

    # directive: transcode-flow-canonical | # see transcode.ST7
    def test_dispatcher_valid_dispositions_matches_closed_enum(self):
        """DispositionDispatcher.VALID_DISPOSITIONS must be exactly {Pending, Replace, Reject, Requeue}."""
        Src = (REPO_ROOT / 'Features' / 'QualityTesting' / 'Disposition' / 'DispositionDispatcher.py').read_text(encoding='utf-8')
        Match = re.search(r"VALID_DISPOSITIONS\s*=\s*\(([^)]*)\)", Src)
        self.assertIsNotNone(Match)
        Values = set(V.strip().strip("'\"") for V in Match.group(1).split(',') if V.strip())
        self.assertEqual(Values, {'Pending', 'Replace', 'Reject', 'Requeue'})

    # directive: transcode-flow-canonical | # see transcode.ST7
    def test_dispatcher_terminal_dispositions_matches_closed_enum(self):
        """TERMINAL_DISPOSITIONS must be exactly {Reject, Requeue}."""
        Src = (REPO_ROOT / 'Features' / 'QualityTesting' / 'Disposition' / 'DispositionDispatcher.py').read_text(encoding='utf-8')
        Match = re.search(r"TERMINAL_DISPOSITIONS\s*=\s*\(([^)]*)\)", Src)
        self.assertIsNotNone(Match)
        Values = set(V.strip().strip("'\"") for V in Match.group(1).split(',') if V.strip())
        self.assertEqual(Values, {'Reject', 'Requeue'})


if __name__ == '__main__':
    unittest.main()
