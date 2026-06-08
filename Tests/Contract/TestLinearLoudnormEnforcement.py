# directive: legacy-audio-damage-accounting | # see legacy-audio-damage-accounting.C3

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from Models.CommandBuilder import CommandBuilder


PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent

LEGACY_CHAIN_LITERAL = 'loudnorm=I=-23:LRA=7:TP=-2'

DEFERRED_FILES_WHITELIST = {
    'Scripts/Smoke/EncodeAndVmaf.py',
    'Scripts/Smoke/FourKEncodingABC.py',
    'Scripts/Smoke/NewGirlEncodingABC_VarianceBoost.py',
    'Tests/Contract/TestLinearLoudnormEnforcement.py',
}


class _MockMediaFile:
    """Duck-typed MediaFile stand-in for BuildAudioFilters tests."""

    def __init__(self, **Fields):
        for Name, Value in Fields.items():
            setattr(self, Name, Value)


class TestLinearLoudnormEnforcement(unittest.TestCase):
    """C3, C4, C5: prove BuildAudioFilters is linear-or-refused and no legacy chain remains."""

    def test_linear_mode_when_gainable(self):
        """C3: BuildAudioFilters returns linear=true when peak fits in target."""
        Mf = _MockMediaFile(
            Id=999001,
            SourceIntegratedLufs=-20.0,
            SourceLoudnessRangeLU=11.0,
            SourceTruePeakDbtp=-8.0,
            SourceIntegratedThresholdLufs=-30.0,
        )
        Cb = CommandBuilder()
        Filter = Cb.BuildAudioFilters(Mf)
        if Filter is None:
            self.skipTest("AudioNormalizationEnabled is off in SystemSettings")
        self.assertIn('loudnorm=', Filter)
        self.assertIn('linear=true', Filter)
        self.assertNotIn('acompressor', Filter)
        self.assertNotIn('alimiter', Filter)

    def test_ungainable_peak_refuses(self):
        """C5: BuildAudioFilters raises RuntimeError instead of dynamic-mode fallback."""
        Mf = _MockMediaFile(
            Id=999002,
            SourceIntegratedLufs=-30.0,
            SourceLoudnessRangeLU=11.0,
            SourceTruePeakDbtp=-3.0,
            SourceIntegratedThresholdLufs=-40.0,
        )
        Cb = CommandBuilder()
        try:
            Result = Cb.BuildAudioFilters(Mf)
        except RuntimeError as Ex:
            Message = str(Ex)
            self.assertIn('ungainable_peak', Message)
            self.assertIn('999002', Message)
            return
        if Result is None:
            self.skipTest("AudioNormalizationEnabled is off in SystemSettings")
        self.fail(f"Expected RuntimeError(ungainable_peak); got Filter={Result!r}")

    def test_audit_no_legacy_chain_literal(self):
        """C4: the exact legacy chain literal (LRA=7 + no linear=true) is absent from production code."""
        Violations = []
        for PyFile in PROJECT_ROOT.rglob('*.py'):
            try:
                Rel = PyFile.relative_to(PROJECT_ROOT).as_posix()
            except ValueError:
                continue
            if 'venv' in Rel.lower() or '.git' in Rel:
                continue
            if Rel in DEFERRED_FILES_WHITELIST:
                continue
            try:
                Content = PyFile.read_text(encoding='utf-8', errors='replace')
            except Exception:
                continue
            for LineNo, Line in enumerate(Content.splitlines(), 1):
                if LEGACY_CHAIN_LITERAL in Line:
                    Violations.append(f"{Rel}:{LineNo}: {Line.strip()[:120]}")
        self.assertEqual(
            Violations,
            [],
            "Legacy dynamic-mode loudnorm chain found in production code:\n" + '\n'.join(Violations),
        )

    def test_audit_no_acompressor_in_audio_chains(self):
        """C4: no acompressor= references remain in any audio-filter emitter."""
        Violations = []
        for PyFile in PROJECT_ROOT.rglob('*.py'):
            try:
                Rel = PyFile.relative_to(PROJECT_ROOT).as_posix()
            except ValueError:
                continue
            if 'venv' in Rel.lower() or '.git' in Rel:
                continue
            if Rel in DEFERRED_FILES_WHITELIST:
                continue
            try:
                Content = PyFile.read_text(encoding='utf-8', errors='replace')
            except Exception:
                continue
            for LineNo, Line in enumerate(Content.splitlines(), 1):
                if 'acompressor=' in Line:
                    Violations.append(f"{Rel}:{LineNo}: {Line.strip()[:120]}")
        self.assertEqual(
            Violations,
            [],
            "acompressor= reference found (legacy chain prefix):\n" + '\n'.join(Violations),
        )


if __name__ == '__main__':
    unittest.main()
