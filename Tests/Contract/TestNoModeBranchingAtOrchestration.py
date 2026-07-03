# directive: transcode-flow-canonical | # see transcode.ST2 -- C4 enforcement

import os
import re
import sys
import unittest
from pathlib import Path as PyPath

sys.path.insert(0, str(PyPath(__file__).resolve().parent.parent.parent))

_REPO_ROOT = PyPath(__file__).resolve().parent.parent.parent

_SCAN_DIRS = [
    _REPO_ROOT / 'Features' / 'TranscodeJob',
    _REPO_ROOT / 'Features' / 'TranscodeQueue',
    _REPO_ROOT / 'Features' / 'FileReplacement',
    _REPO_ROOT / 'Features' / 'Activity',
]

_WHITELIST = {
    _REPO_ROOT / 'Features' / 'TranscodeQueue' / 'Models' / 'TranscodeQueueModel.py',
    _REPO_ROOT / 'Features' / 'TranscodeJob' / 'ProcessingModeMetadata.py',
    _REPO_ROOT / 'Features' / 'FileReplacement' / 'PostFlightProcessors' / 'RemuxPostFlight.py',
}


def _IsInStrategyOrModelsDir(FilePath: PyPath) -> bool:
    Parts = set(FilePath.parts)
    return 'Strategies' in Parts or 'Models' in Parts or 'PostFlightProcessors' in Parts


_MODE_BRANCH_PATTERN = re.compile(
    r"(Mode|ProcessingMode|EffectiveMode)\s*(==|!=|in\s*\()\s*['\"](Remux|Transcode|AudioFix|SubtitleFix|Quick)"
)


class TestNoModeBranchingAtOrchestration(unittest.TestCase):
    """Orchestration files must NOT branch on ProcessingMode literals; variance lives in Strategy classes or is data-driven via ProcessingModeMetadata / ProcessingModes DB rows. See `.claude/rules/call-graph-audit.md` Signal 2."""

    def test_no_mode_literal_branches_outside_strategy_or_models(self):
        Offenders = []
        for ScanDir in _SCAN_DIRS:
            for Root, _Dirs, Files in os.walk(ScanDir):
                for FileName in Files:
                    if not FileName.endswith('.py'):
                        continue
                    if FileName.startswith('_') or FileName == '__init__.py':
                        continue
                    FilePath = PyPath(Root) / FileName
                    if FilePath in _WHITELIST:
                        continue
                    if _IsInStrategyOrModelsDir(FilePath):
                        continue
                    try:
                        Text = FilePath.read_text(encoding='utf-8', errors='replace')
                    except OSError:
                        continue
                    for LineNum, Line in enumerate(Text.splitlines(), start=1):
                        Stripped = Line.strip()
                        if Stripped.startswith('#'):
                            continue
                        if _MODE_BRANCH_PATTERN.search(Line):
                            Offenders.append(f"{FilePath.relative_to(_REPO_ROOT)}:{LineNum}: {Stripped}")
        self.assertEqual(
            Offenders, [],
            f"Orchestration-layer ProcessingMode-literal branches found (must be Strategy or metadata-driven):\n" + "\n".join(Offenders),
        )


if __name__ == '__main__':
    unittest.main()
