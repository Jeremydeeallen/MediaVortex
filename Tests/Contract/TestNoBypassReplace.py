# directive: transcode-flow-canonical | # see transcode.ST7
import re
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]

PRODUCTION_DIRS = ('Features', 'Workers', 'WorkerService', 'WebService', 'Repositories', 'Core')

WHITELIST_MD = {
    'transcode.flow.md',
    'GLOSSARY.md',
}


# directive: transcode-flow-canonical | # see transcode.ST7
class TestNoBypassReplace(unittest.TestCase):

    # directive: transcode-flow-canonical | # see transcode.ST7
    def test_no_bypassreplace_in_production_python(self):
        """No production .py file may reference the retired BypassReplace disposition value."""
        Hits = []
        for Sub in PRODUCTION_DIRS:
            Root = REPO_ROOT / Sub
            if not Root.exists():
                continue
            for Py in Root.rglob('*.py'):
                Text = Py.read_text(encoding='utf-8', errors='replace')
                for LineNo, Line in enumerate(Text.splitlines(), start=1):
                    if 'BypassReplace' in Line:
                        Hits.append(f"{Py.relative_to(REPO_ROOT)}:{LineNo}: {Line.strip()}")
        self.assertEqual([], Hits, "BypassReplace found in production Python:\n" + '\n'.join(Hits))

    # directive: transcode-flow-canonical | # see transcode.ST7
    def test_decider_never_returns_bypassreplace(self):
        """Structural: PostTranscodeDispositionDecider source must not contain the literal 'BypassReplace'."""
        Src = (REPO_ROOT / 'Features' / 'QualityTesting' / 'Disposition' / 'PostTranscodeDispositionDecider.py').read_text(encoding='utf-8')
        self.assertNotIn('BypassReplace', Src, "Decider still references BypassReplace")

    # directive: transcode-flow-canonical | # see transcode.ST7
    def test_dispatcher_valid_dispositions_omits_bypassreplace(self):
        """DispositionDispatcher.VALID_DISPOSITIONS must not include 'BypassReplace'."""
        Src = (REPO_ROOT / 'Features' / 'QualityTesting' / 'Disposition' / 'DispositionDispatcher.py').read_text(encoding='utf-8')
        Match = re.search(r"VALID_DISPOSITIONS\s*=\s*\(([^)]*)\)", Src)
        self.assertIsNotNone(Match, "VALID_DISPOSITIONS tuple not found in DispositionDispatcher")
        Values = Match.group(1)
        self.assertNotIn('BypassReplace', Values, f"VALID_DISPOSITIONS still contains BypassReplace: {Values}")

    # directive: transcode-flow-canonical | # see transcode.ST7
    def test_active_feature_docs_have_no_bypassreplace_references(self):
        """Active feature docs (not closed directives) must not describe live BypassReplace behavior."""
        Hits = []
        SkipDirs = ('.claude/directives/closed', '.claude/rules-details', 'memory', '.claude/directive.md')
        for Md in REPO_ROOT.rglob('*.md'):
            Rel = str(Md.relative_to(REPO_ROOT)).replace('\\', '/')
            if any(Rel.startswith(S) for S in SkipDirs):
                continue
            if Md.name in WHITELIST_MD:
                continue
            Text = Md.read_text(encoding='utf-8', errors='replace')
            for LineNo, Line in enumerate(Text.splitlines(), start=1):
                if 'BypassReplace' in Line:
                    Hits.append(f"{Rel}:{LineNo}: {Line.strip()[:200]}")
        self.assertEqual([], Hits, "BypassReplace found in active docs:\n" + '\n'.join(Hits))


if __name__ == '__main__':
    unittest.main()
