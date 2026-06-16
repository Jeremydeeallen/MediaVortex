import sys
import unittest
from pathlib import Path
from unittest.mock import patch, MagicMock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from Features.AudioNormalization.Services.AudioRemeasurementService import (
    AudioRemeasurementService,
    REASON_INVALID_LOUDNESS,
    REASON_OPERATOR_REVIEW,
)


# directive: perfect-audio-vertical | # see perfect-audio-vertical.C13
class _StubMeasurement:
    """Stub EbuR128MeasurementService that returns a fixed (Success, Reason) without touching ffmpeg."""

    # directive: perfect-audio-vertical | # see perfect-audio-vertical.C13
    def __init__(self, Success=True, Reason=None):
        self.Success = Success
        self.Reason = Reason
        self.Calls = []

    # directive: perfect-audio-vertical | # see perfect-audio-vertical.C13
    def MeasureAndPersist(self, MediaFileId, LocalFilePath, AudioStreamIndex=0):
        self.Calls.append((MediaFileId, LocalFilePath, AudioStreamIndex))
        return self.Success, self.Reason


# directive: perfect-audio-vertical | # see perfect-audio-vertical.C13
class _StubValidator:
    """Stub LoudnessMeasurementValidator with a configurable IsValid result."""

    # directive: perfect-audio-vertical | # see perfect-audio-vertical.C13
    def __init__(self, Valid=True):
        self.Valid = Valid

    # directive: perfect-audio-vertical | # see perfect-audio-vertical.C13
    def IsValid(self, MediaFile):
        return self.Valid


# directive: perfect-audio-vertical | # see perfect-audio-vertical.C13
class TestAudioRemeasurementService(unittest.TestCase):
    """C13: re-measure invalid files; clear defer reason on success; route to operator review on persistent silence."""

    # directive: perfect-audio-vertical | # see perfect-audio-vertical.C13
    def test_process_clears_defer_when_measurement_valid(self):
        Svc = AudioRemeasurementService(
            MeasurementService=_StubMeasurement(Success=True),
            Validator=_StubValidator(Valid=True),
        )
        with patch(
            'Features.AudioNormalization.Services.AudioRemeasurementService.DatabaseService'
        ) as MockDb:
            Instance = MagicMock()
            MockDb.return_value = Instance
            Instance.ExecuteQuery.return_value = [{
                'id': 42, 'filename': 'x', 'sourceintegratedlufs': -23.5,
                'sourceloudnessrangelu': 9.0, 'sourcetruepeakdbtp': -1.5,
                'sourceintegratedthresholdlufs': -33.5, 'admissiondeferreason': None,
            }]
            Ok, Reason = Svc.Process(42, '/dev/null')
            self.assertTrue(Ok)
            self.assertIsNone(Reason)
            ExecuteNonQueryCalls = [Call.args[0] for Call in Instance.ExecuteNonQuery.call_args_list]
            ClearCalls = [Sql for Sql in ExecuteNonQueryCalls if 'AdmissionDeferReason = NULL' in Sql]
            self.assertGreaterEqual(len(ClearCalls), 1)

    # directive: perfect-audio-vertical | # see perfect-audio-vertical.C13
    def test_process_routes_to_review_when_measurement_succeeds_but_still_invalid(self):
        Svc = AudioRemeasurementService(
            MeasurementService=_StubMeasurement(Success=True),
            Validator=_StubValidator(Valid=False),
        )
        with patch(
            'Features.AudioNormalization.Services.AudioRemeasurementService.DatabaseService'
        ) as MockDb:
            Instance = MagicMock()
            MockDb.return_value = Instance
            Instance.ExecuteQuery.return_value = [{
                'id': 42, 'filename': 'x', 'sourceintegratedlufs': -70.0,
                'sourceloudnessrangelu': None, 'sourcetruepeakdbtp': None,
                'sourceintegratedthresholdlufs': None, 'admissiondeferreason': None,
            }]
            Ok, Reason = Svc.Process(42, '/dev/null')
            self.assertTrue(Ok)
            self.assertEqual(Reason, 'routed_to_operator_review')
            ExecuteNonQueryCalls = Instance.ExecuteNonQuery.call_args_list
            ReviewCalls = [
                Call for Call in ExecuteNonQueryCalls
                if len(Call.args) >= 2 and REASON_OPERATOR_REVIEW in Call.args[1]
            ]
            self.assertGreaterEqual(len(ReviewCalls), 1)

    # directive: perfect-audio-vertical | # see perfect-audio-vertical.C13
    def test_process_returns_false_when_measurement_fails(self):
        Svc = AudioRemeasurementService(
            MeasurementService=_StubMeasurement(Success=False, Reason='timeout'),
            Validator=_StubValidator(Valid=True),
        )
        Ok, Reason = Svc.Process(42, '/dev/null')
        self.assertFalse(Ok)
        self.assertEqual(Reason, 'timeout')

    # directive: perfect-audio-vertical | # see perfect-audio-vertical.C13
    def test_mark_for_remeasurement_uses_invalid_reason_default(self):
        Svc = AudioRemeasurementService(
            MeasurementService=_StubMeasurement(Success=True),
            Validator=_StubValidator(Valid=True),
        )
        with patch(
            'Features.AudioNormalization.Services.AudioRemeasurementService.DatabaseService'
        ) as MockDb:
            Instance = MagicMock()
            MockDb.return_value = Instance
            Svc.MarkForRemeasurement(42)
            Instance.ExecuteNonQuery.assert_called_once()
            Args = Instance.ExecuteNonQuery.call_args.args
            self.assertIn(REASON_INVALID_LOUDNESS, Args[1])


if __name__ == '__main__':
    unittest.main()
