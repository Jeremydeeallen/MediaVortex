import os
import re
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))


REPO_ROOT = Path(__file__).resolve().parent.parent.parent


# directive: transcode-flow-canonical | # see transcode.ST5
RETIRED_SYMBOLS = (
    'EncodeShapeRegistry',
    'TranscodeShape',
    'RemuxShape',
    'SubtitleFixShape',
    'NvencEncoderArgsStrategy',
    'QsvEncoderArgsStrategy',
    'CodecParameterAssembler',
    'AudioCodecArgsBuilder',
)


# directive: transcode-flow-canonical | # see transcode.ST5
PRODUCTION_ROOTS = ('Features', 'Workers', 'WorkerService', 'WebService', 'Repositories', 'Core', 'Composition')


# directive: transcode-flow-canonical | # see transcode.ST5
def _EnumeratePythonFiles():
    Files = []
    for Root in PRODUCTION_ROOTS:
        Base = REPO_ROOT / Root
        if not Base.exists():
            continue
        for Path_ in Base.rglob('*.py'):
            Files.append(Path_)
    return Files


# directive: transcode-flow-canonical | # see transcode.ST5
class TestNoLegacyResidue(unittest.TestCase):

    def test_retired_shape_symbols_absent_from_production_tree(self):
        Offenders = []
        for File in _EnumeratePythonFiles():
            try:
                Source = File.read_text(encoding='utf-8')
            except Exception:
                continue
            for Symbol in RETIRED_SYMBOLS:
                if re.search(r'\b' + re.escape(Symbol) + r'\b', Source):
                    Offenders.append(f'{File.relative_to(REPO_ROOT)} references {Symbol}')
        self.assertEqual(
            [], Offenders,
            'Retired symbols must not appear in production Python. Offenders:\n  ' + '\n  '.join(Offenders),
        )

    def test_deleted_files_are_gone(self):
        Deleted = (
            'Features/TranscodeJob/Emit/EncodeShape.py',
            'Features/TranscodeJob/Emit/EncodeShapeRegistry.py',
            'Features/TranscodeJob/Emit/TranscodeShape.py',
            'Features/TranscodeJob/Emit/RemuxShape.py',
            'Features/TranscodeJob/Emit/SubtitleFixShape.py',
            'Features/TranscodeJob/Emit/CodecParameterAssembler.py',
            'Features/TranscodeJob/Emit/AudioCodecArgsBuilder.py',
            'Features/TranscodeJob/Emit/EncoderArgsStrategies/NvencEncoderArgsStrategy.py',
            'Features/TranscodeJob/Emit/EncoderArgsStrategies/QsvEncoderArgsStrategy.py',
        )
        Present = [P for P in Deleted if (REPO_ROOT / P).exists()]
        self.assertEqual([], Present, f'Retired production files still present: {Present}')


if __name__ == '__main__':
    unittest.main()
