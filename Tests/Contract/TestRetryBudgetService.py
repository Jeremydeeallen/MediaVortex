from unittest.mock import MagicMock

from Features.QualityTesting.Disposition.RetryBudgetService import RetryBudgetService


# directive: verify-signal-cleanup | # see DOMAIN.md 2026-07-26 Vmaf-truthful rule
def _MakeAttempt(Disposition=None):
    A = MagicMock()
    A.Disposition = Disposition
    return A


def _MakeGateConfig(MaxRequeueAttempts=3):
    G = MagicMock()
    G.MaxRequeueAttempts = MaxRequeueAttempts
    return G


class TestRetryBudgetService:

    def test_no_prior_attempts_has_budget(self):
        AttemptRepo = MagicMock()
        AttemptRepo.GetTranscodeAttemptsByMediaFileId.return_value = []
        GateRepo = MagicMock()
        GateRepo.Get.return_value = _MakeGateConfig()
        Svc = RetryBudgetService(AttemptRepo, GateRepo)
        assert Svc.HasBudgetRemaining(MediaFileId=42) is True

    def test_below_max_has_budget(self):
        AttemptRepo = MagicMock()
        AttemptRepo.GetTranscodeAttemptsByMediaFileId.return_value = [
            _MakeAttempt(Disposition='Requeue'), _MakeAttempt(Disposition='Requeue'),
        ]
        GateRepo = MagicMock()
        GateRepo.Get.return_value = _MakeGateConfig(MaxRequeueAttempts=3)
        Svc = RetryBudgetService(AttemptRepo, GateRepo)
        assert Svc.HasBudgetRemaining(MediaFileId=42) is True

    def test_at_max_exhausted(self):
        AttemptRepo = MagicMock()
        AttemptRepo.GetTranscodeAttemptsByMediaFileId.return_value = [
            _MakeAttempt(Disposition='Requeue'), _MakeAttempt(Disposition='Requeue'), _MakeAttempt(Disposition='Requeue'),
        ]
        GateRepo = MagicMock()
        GateRepo.Get.return_value = _MakeGateConfig(MaxRequeueAttempts=3)
        Svc = RetryBudgetService(AttemptRepo, GateRepo)
        assert Svc.HasBudgetRemaining(MediaFileId=42) is False

    def test_replace_disposition_does_not_consume_budget(self):
        AttemptRepo = MagicMock()
        AttemptRepo.GetTranscodeAttemptsByMediaFileId.return_value = [
            _MakeAttempt(Disposition='Replace'), _MakeAttempt(Disposition='Replace'), _MakeAttempt(Disposition='Replace'),
        ]
        GateRepo = MagicMock()
        GateRepo.Get.return_value = _MakeGateConfig(MaxRequeueAttempts=3)
        Svc = RetryBudgetService(AttemptRepo, GateRepo)
        assert Svc.HasBudgetRemaining(MediaFileId=42) is True

    def test_reject_disposition_does_not_consume_budget(self):
        AttemptRepo = MagicMock()
        AttemptRepo.GetTranscodeAttemptsByMediaFileId.return_value = [
            _MakeAttempt(Disposition='Reject'), _MakeAttempt(Disposition='Reject'), _MakeAttempt(Disposition='Reject'),
        ]
        GateRepo = MagicMock()
        GateRepo.Get.return_value = _MakeGateConfig(MaxRequeueAttempts=3)
        Svc = RetryBudgetService(AttemptRepo, GateRepo)
        assert Svc.HasBudgetRemaining(MediaFileId=42) is True

    def test_null_disposition_does_not_consume_budget(self):
        AttemptRepo = MagicMock()
        AttemptRepo.GetTranscodeAttemptsByMediaFileId.return_value = [
            _MakeAttempt(Disposition=None), _MakeAttempt(Disposition=None), _MakeAttempt(Disposition=None),
        ]
        GateRepo = MagicMock()
        GateRepo.Get.return_value = _MakeGateConfig(MaxRequeueAttempts=3)
        Svc = RetryBudgetService(AttemptRepo, GateRepo)
        assert Svc.HasBudgetRemaining(MediaFileId=42) is True

    def test_reads_gate_config_fresh_per_call(self):
        AttemptRepo = MagicMock()
        AttemptRepo.GetTranscodeAttemptsByMediaFileId.return_value = [
            _MakeAttempt(Disposition='Requeue'), _MakeAttempt(Disposition='Requeue'),
        ]
        GateRepo = MagicMock()
        GateRepo.Get.side_effect = [
            _MakeGateConfig(MaxRequeueAttempts=3),
            _MakeGateConfig(MaxRequeueAttempts=1),
        ]
        Svc = RetryBudgetService(AttemptRepo, GateRepo)
        assert Svc.HasBudgetRemaining(MediaFileId=42) is True
        assert Svc.HasBudgetRemaining(MediaFileId=42) is False
        assert GateRepo.Get.call_count == 2
