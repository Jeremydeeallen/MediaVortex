import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from Tests.Contract.TestFailLoud import (
    _EnumerateProductionFiles,
    _CountFailLoudHits,
    BASELINE_PATH,
    REPO_ROOT,
)


def Main():
    Result = {}
    for F in _EnumerateProductionFiles():
        Src = F.read_text(encoding='utf-8')
        Hits, _ = _CountFailLoudHits(Src)
        if Hits > 0:
            Rel = str(F.relative_to(REPO_ROOT)).replace(os.sep, '/')
            Result[Rel] = Hits
    D = {
        '_note': 'Auto-captured baseline of fail-loud anti-pattern hits per production file. Test refuses growth. When a file is swept clean, remove its entry.',
        'files': dict(sorted(Result.items())),
    }
    with open(BASELINE_PATH, 'w', encoding='utf-8') as F:
        json.dump(D, F, indent=2)
    print(f'{len(Result)} files / {sum(Result.values())} hits')


if __name__ == '__main__':
    Main()
