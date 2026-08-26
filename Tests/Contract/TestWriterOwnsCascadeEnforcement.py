import re
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))


_ROOT = Path(__file__).resolve().parent.parent.parent


_COMPLIANCE_INPUT_COLUMNS = [
    'Resolution',
    'ResolutionCategory',
    'Codec',
    'VideoBitrateKbps',
    'AudioCodec',
    'AudioChannels',
    'AudioBitrateKbps',
    'ContainerFormat',
    'AudioLanguages',
    'HasExplicitEnglishAudio',
    'AssignedProfile',
    'SourceIntegratedLufs',
    'SourceLoudnessRangeLU',
    'SourceTruePeakDbtp',
    'TranscodedByMediaVortex',
]


_SEARCH_ROOTS = ['Features', 'WorkerService']


def _FunctionBody(Lines, LineIdx):
    Back = LineIdx
    while Back >= 0:
        M = re.match(r'^(\s*)def\s+', Lines[Back])
        if M:
            Indent = len(M.group(1))
            EndIdx = LineIdx
            while EndIdx + 1 < len(Lines):
                Next = Lines[EndIdx + 1]
                if Next.strip() and (len(Next) - len(Next.lstrip())) <= Indent:
                    break
                EndIdx += 1
            return '\n'.join(Lines[Back: EndIdx + 1])
        Back -= 1
    return ''


class TestWriterOwnsCascadeEnforcement(unittest.TestCase):

    def test_every_service_layer_mediafiles_writer_cascades(self):
        Pattern = re.compile(
            r'UPDATE\s+MediaFiles[\s\S]{0,600}?\bSET\s+(?:\w+\s*=\s*[^,]+,\s*)*(' + '|'.join(_COMPLIANCE_INPUT_COLUMNS) + r')\s*=',
            re.IGNORECASE,
        )
        Violations = []
        for RootName in _SEARCH_ROOTS:
            RootPath = _ROOT / RootName
            if not RootPath.exists():
                continue
            for PyFile in RootPath.rglob('*.py'):
                if '__pycache__' in PyFile.parts:
                    continue
                Name = PyFile.name
                # directive: tv-tier1-classifier-pin -- MediaFilesRepository is the sanctioned raw writer; service layer (ProfileAssignmentService, ProbeStage) owns cascade.
                if PyFile.resolve() == (_ROOT / 'Features' / 'MediaFiles' / 'MediaFilesRepository.py').resolve():
                    continue
                try:
                    Text = PyFile.read_text(encoding='utf-8', errors='ignore')
                except Exception:
                    continue
                Lines = Text.split('\n')
                for Match in Pattern.finditer(Text):
                    LineIdx = Text[: Match.start()].count('\n')
                    Body = _FunctionBody(Lines, LineIdx)
                    if not Body:
                        continue
                    if 'RecomputeForFiles' in Body:
                        continue
                    if 'cascade-ok' in Body:
                        continue
                    Violations.append(f"{PyFile.relative_to(_ROOT)}:{LineIdx + 1}: {Lines[LineIdx].strip()[:120]}")
        self.assertEqual(
            Violations, [],
            'writer-owns-cascade violations (service-layer UPDATE MediaFiles SET '
            '<compliance-input-column> without calling RecomputeForFiles in the '
            'same function):\n' + '\n'.join(Violations)
        )


if __name__ == '__main__':
    unittest.main()
