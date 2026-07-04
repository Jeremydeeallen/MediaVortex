import json
import re
import sys
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO_ROOT))

BASELINE_PATH = REPO_ROOT / 'Tests' / 'Contract' / 'failloud_baseline.json'

PRODUCTION_ROOTS = ('Features', 'Workers', 'WorkerService', 'WebService', 'Repositories', 'Core', 'Composition', 'Services')

EXCLUDE_PATH_FRAGMENTS = ('/venv/', '/site-packages/', '/__pycache__/')

MARKER = 'fail-loud-ok:'
MARKER_WINDOW = 3


# directive: transcode-flow-canonical | # see transcode.ST8
def _EnumerateProductionFiles():
    Files = []
    for Root in PRODUCTION_ROOTS:
        Base = REPO_ROOT / Root
        if not Base.exists():
            continue
        for P in Base.rglob('*.py'):
            Norm = str(P).replace('\\', '/')
            if any(Frag in Norm for Frag in EXCLUDE_PATH_FRAGMENTS):
                continue
            Files.append(P)
    return Files


# directive: transcode-flow-canonical | # see transcode.ST8
def _HasNearbyMarker(Lines, Index):
    Lo = max(0, Index - MARKER_WINDOW)
    Hi = min(len(Lines), Index + MARKER_WINDOW + 1)
    for J in range(Lo, Hi):
        if MARKER in Lines[J]:
            return True
    return False


# directive: transcode-flow-canonical | # see transcode.ST8
def _CountFailLoudHits(Source):
    Lines = Source.split('\n')
    Hits = 0
    Details = []
    for I, L in enumerate(Lines):
        if _HasNearbyMarker(Lines, I):
            continue
        if re.match(r'^\s*except\s*:\s*(#.*)?$', L):
            Hits += 1
            Details.append((I + 1, 'bare-except', L.strip()))
            continue
        M = re.match(r'^(\s*)except\s+(Exception|BaseException)[^:]*:\s*(#.*)?$', L)
        if M:
            Indent = len(M.group(1))
            HasRaise = False
            for J in range(I + 1, min(I + 50, len(Lines))):
                NL = Lines[J]
                if NL.strip() == '':
                    continue
                NI = len(NL) - len(NL.lstrip())
                if NI <= Indent:
                    break
                if re.search(r'\braise\b', NL):
                    HasRaise = True
                    break
            if not HasRaise:
                Hits += 1
                Details.append((I + 1, 'except-Exception-no-raise', L.strip()))
                continue
        if re.search(r'=\s+[^#\n]*\bor\s+(0|None|""|\'\')\b', L) or re.search(r'return\s+[^#\n]*\bor\s+(0|None|""|\'\')\b', L):
            Hits += 1
            Details.append((I + 1, 'coalesce-default', L.strip()))
            continue
        M2 = re.match(r'^(\s*)if\s+(\w[\w\.]*)\s+is\s+None\s*:\s*$', L)
        if M2 and I + 1 < len(Lines):
            Var = M2.group(2)
            Next = Lines[I + 1]
            if re.match(r'^\s+' + re.escape(Var) + r'\s*=\s*', Next):
                Hits += 1
                Details.append((I + 1, 'is-None-substitution', L.strip()))
                continue
    return Hits, Details


# directive: transcode-flow-canonical | # see transcode.ST8
def _LoadBaseline():
    with open(BASELINE_PATH, 'r', encoding='utf-8') as F:
        return json.load(F).get('files', {})


# directive: transcode-flow-canonical | # see transcode.ST8 -- see directive C7 for baseline ratchet policy
class TestFailLoud(unittest.TestCase):

    def test_bare_except_zero(self):
        Offenders = []
        for File in _EnumerateProductionFiles():
            Source = File.read_text(encoding='utf-8')
            Lines = Source.split('\n')
            for I, L in enumerate(Lines):
                if _HasNearbyMarker(Lines, I):
                    continue
                if re.match(r'^\s*except\s*:\s*(#.*)?$', L):
                    Rel = str(File.relative_to(REPO_ROOT)).replace('\\', '/')
                    Offenders.append(f'{Rel}:{I + 1}: {L.strip()}')
        self.assertEqual(
            [], Offenders,
            'Bare `except:` refused. Name the exception, or add `# fail-loud-ok: <reason>` within 3 lines.\n  ' + '\n  '.join(Offenders),
        )

    def test_no_growth_against_baseline(self):
        Baseline = _LoadBaseline()
        Grew = []
        for File in _EnumerateProductionFiles():
            Rel = str(File.relative_to(REPO_ROOT)).replace('\\', '/')
            Source = File.read_text(encoding='utf-8')
            Hits, Details = _CountFailLoudHits(Source)
            Allowed = Baseline.get(Rel, 0)
            if Hits > Allowed:
                DetailLines = [f'    line {Ln} [{Kind}] {Src}' for Ln, Kind, Src in Details]
                Grew.append(f'{Rel}: {Hits} hits > baseline {Allowed}\n' + '\n'.join(DetailLines))
        self.assertEqual(
            [], Grew,
            'New fail-loud hits. Fix, or add `# fail-loud-ok: <reason>` within 3 lines.\n  ' + '\n\n  '.join(Grew),
        )

    def test_baseline_files_still_exist(self):
        Baseline = _LoadBaseline()
        Missing = [F for F in Baseline if not (REPO_ROOT / F).exists()]
        self.assertEqual(
            [], Missing,
            f'Baseline references deleted files. Remove from failloud_baseline.json: {Missing}',
        )

    def test_baseline_not_stale(self):
        Baseline = _LoadBaseline()
        Stale = []
        for File in _EnumerateProductionFiles():
            Rel = str(File.relative_to(REPO_ROOT)).replace('\\', '/')
            if Rel not in Baseline:
                continue
            Source = File.read_text(encoding='utf-8')
            Hits, _ = _CountFailLoudHits(Source)
            Expected = Baseline[Rel]
            if Hits < Expected:
                Stale.append(f'{Rel}: {Hits} actual < {Expected} baseline (ratchet: update failloud_baseline.json)')
        self.assertEqual(
            [], Stale,
            'Baseline stale for files whose hit count dropped. Ratchet baseline down:\n  ' + '\n  '.join(Stale),
        )


if __name__ == '__main__':
    unittest.main()
