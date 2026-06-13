# directive: perfect-solid-transcode-pipeline-phase2 | # see perfect-solid-transcode-pipeline-phase2.C7
"""Verify AudioFilterBuilder linear-or-refused contract and UngainablePeakError emission."""
import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from Features.TranscodeJob.Emit.AudioFilterBuilder import AudioFilterBuilder
from Features.TranscodeJob.Emit.UngainablePeakError import UngainablePeakError


# directive: perfect-solid-transcode-pipeline-phase2 | # see perfect-solid-transcode-pipeline-phase2.C7
class _MockMediaFile:
    """Duck-typed MediaFile stand-in for AudioFilterBuilder tests."""

    # directive: perfect-solid-transcode-pipeline-phase2 | # see perfect-solid-transcode-pipeline-phase2.C7
    def __init__(self, **Fields):
        """Set arbitrary attributes from kwargs."""
        for Name, Value in Fields.items():
            setattr(self, Name, Value)


# directive: perfect-solid-transcode-pipeline-phase2 | # see perfect-solid-transcode-pipeline-phase2.C7
def _MakeMockDb(NormalizationEnabled='true', TargetLoudness='-23', TruePeak='-2', MinLra='11'):
    """Build a mock DatabaseManager whose GetSystemSetting returns canned values per key."""
    Db = MagicMock()
    Settings = {
        'AudioNormalizationEnabled': NormalizationEnabled,
        'TargetLoudness': TargetLoudness,
        'TruePeak': TruePeak,
        'MinimumLoudnessRangeLU': MinLra,
    }
    Db.GetSystemSetting.side_effect = lambda Key: Settings.get(Key)
    return Db


# directive: perfect-solid-transcode-pipeline-phase2 | # see perfect-solid-transcode-pipeline-phase2.C7
class TestAudioFilterBuilder(unittest.TestCase):
    """C7: AudioFilterBuilder enforces linear-or-refused and emits typed errors."""

    # directive: perfect-solid-transcode-pipeline-phase2 | # see perfect-solid-transcode-pipeline-phase2.C7
    def test_normalization_disabled_returns_none(self):
        """When AudioNormalizationEnabled is off, Build returns None (kill switch)."""
        Db = _MakeMockDb(NormalizationEnabled='false')
        Builder = AudioFilterBuilder(Db)
        Mf = _MockMediaFile(Id=1, SourceIntegratedLufs=-20.0, SourceLoudnessRangeLU=11.0, SourceTruePeakDbtp=-8.0, SourceIntegratedThresholdLufs=-30.0)
        self.assertIsNone(Builder.Build(Mf))

    # directive: perfect-solid-transcode-pipeline-phase2 | # see perfect-solid-transcode-pipeline-phase2.C7
    def test_missing_measurements_raises_runtimeerror(self):
        """Missing measurement -> RuntimeError (NOT UngainablePeakError; that is a distinct case)."""
        Db = _MakeMockDb()
        Builder = AudioFilterBuilder(Db)
        Mf = _MockMediaFile(Id=2, SourceIntegratedLufs=None, SourceLoudnessRangeLU=11.0, SourceTruePeakDbtp=-8.0, SourceIntegratedThresholdLufs=-30.0)
        with self.assertRaises(RuntimeError) as Ctx:
            Builder.Build(Mf)
        self.assertNotIsInstance(Ctx.exception, UngainablePeakError)
        self.assertIn('SourceIntegratedLufs', str(Ctx.exception))

    # directive: perfect-solid-transcode-pipeline-phase2 | # see perfect-solid-transcode-pipeline-phase2.C7
    def test_gainable_returns_linear_filter(self):
        """When predicted peak <= TargetTp, returns linear=true loudnorm string."""
        Db = _MakeMockDb()
        Builder = AudioFilterBuilder(Db)
        Mf = _MockMediaFile(Id=3, SourceIntegratedLufs=-20.0, SourceLoudnessRangeLU=11.0, SourceTruePeakDbtp=-8.0, SourceIntegratedThresholdLufs=-30.0)
        Filter = Builder.Build(Mf)
        self.assertIsNotNone(Filter)
        self.assertIn('loudnorm=', Filter)
        self.assertIn('linear=true', Filter)
        self.assertNotIn('acompressor', Filter)
        self.assertNotIn('alimiter', Filter)

    # directive: perfect-solid-transcode-pipeline-phase2 | # see perfect-solid-transcode-pipeline-phase2.C7
    def test_ungainable_raises_typed_error(self):
        """ungainable peak raises UngainablePeakError, not bare RuntimeError."""
        Db = _MakeMockDb()
        Builder = AudioFilterBuilder(Db)
        Mf = _MockMediaFile(Id=999002, SourceIntegratedLufs=-30.0, SourceLoudnessRangeLU=11.0, SourceTruePeakDbtp=-3.0, SourceIntegratedThresholdLufs=-40.0)
        with self.assertRaises(UngainablePeakError):
            Builder.Build(Mf)

    # directive: perfect-solid-transcode-pipeline-phase2 | # see perfect-solid-transcode-pipeline-phase2.C7
    def test_ungainable_error_carries_diagnostics(self):
        """Raised UngainablePeakError carries the five diagnostic attributes populated."""
        Db = _MakeMockDb()
        Builder = AudioFilterBuilder(Db)
        Mf = _MockMediaFile(Id=999003, SourceIntegratedLufs=-30.0, SourceLoudnessRangeLU=11.0, SourceTruePeakDbtp=-3.0, SourceIntegratedThresholdLufs=-40.0)
        try:
            Builder.Build(Mf)
            self.fail('Expected UngainablePeakError')
        except UngainablePeakError as Err:
            self.assertEqual(Err.MediaFileId, 999003)
            self.assertAlmostEqual(Err.SourceIntegratedLufs, -30.0)
            self.assertAlmostEqual(Err.Gain, 7.0)
            self.assertAlmostEqual(Err.PredictedPeak, 4.0)
            self.assertEqual(Err.TargetTp, -2)

    # directive: perfect-solid-transcode-pipeline-phase2 | # see perfect-solid-transcode-pipeline-phase2.C7
    def test_ungainable_error_is_runtimeerror_subclass(self):
        """UngainablePeakError is a RuntimeError so legacy catch-RuntimeError sites still see it."""
        Db = _MakeMockDb()
        Builder = AudioFilterBuilder(Db)
        Mf = _MockMediaFile(Id=999004, SourceIntegratedLufs=-30.0, SourceLoudnessRangeLU=11.0, SourceTruePeakDbtp=-3.0, SourceIntegratedThresholdLufs=-40.0)
        try:
            Builder.Build(Mf)
            self.fail('Expected UngainablePeakError')
        except UngainablePeakError as Err:
            self.assertIsInstance(Err, RuntimeError)


if __name__ == '__main__':
    unittest.main()
