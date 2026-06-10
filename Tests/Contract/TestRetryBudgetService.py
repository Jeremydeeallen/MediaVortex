from unittest.mock import MagicMock

import pytest

from Features.QualityTesting.Disposition.RetryBudgetService import RetryBudgetService


# directive: perfect-solid-transcode-pipeline | # see perfect-solid-transcode-pipeline.C7
def _MakeAttempt(Success=True, VMAF=70.0):
    """Build a mock attempt object matching the repository return shape."""
    A = MagicMock()
    A.Success = Success
    A.VMAF = VMAF
    return A


# directive: perfect-solid-transcode-pipeline | # see perfect-solid-transcode-pipeline.C7
def _MakeGateConfig(MaxRequeueAttempts=3, VmafAutoReplaceMinThreshold=88.0):
    """Build a mock GateConfig model with configurable budget + threshold."""
    G = MagicMock()
    G.MaxRequeueAttempts = MaxRequeueAttempts
    G.VmafAutoReplaceMinThreshold = VmafAutoReplaceMinThreshold
    return G


# directive: perfect-solid-transcode-pipeline | # see perfect-solid-transcode-pipeline.C7
class TestRetryBudgetService:
    """Contract: HasBudgetRemaining counts only Success+VMAF<gate attempts; reads config fresh per call."""

    # directive: perfect-solid-transcode-pipeline | # see perfect-solid-transcode-pipeline.C7
    def test_no_prior_attempts_has_budget(self):
        """Empty attempt history -> budget remains."""
        AttemptRepo = MagicMock()
        AttemptRepo.GetTranscodeAttemptsByMediaFileId.return_value = []
        GateRepo = MagicMock()
        GateRepo.Get.return_value = _MakeGateConfig()
        Svc = RetryBudgetService(AttemptRepo, GateRepo)
        assert Svc.HasBudgetRemaining(MediaFileId=42) is True

    # directive: perfect-solid-transcode-pipeline | # see perfect-solid-transcode-pipeline.C7
    def test_below_max_has_budget(self):
        """Two prior VMAF-fail attempts under MaxRequeueAttempts=3 leaves budget."""
        AttemptRepo = MagicMock()
        AttemptRepo.GetTranscodeAttemptsByMediaFileId.return_value = [
            _MakeAttempt(VMAF=70), _MakeAttempt(VMAF=72),
        ]
        GateRepo = MagicMock()
        GateRepo.Get.return_value = _MakeGateConfig(MaxRequeueAttempts=3)
        Svc = RetryBudgetService(AttemptRepo, GateRepo)
        assert Svc.HasBudgetRemaining(MediaFileId=42) is True

    # directive: perfect-solid-transcode-pipeline | # see perfect-solid-transcode-pipeline.C7
    def test_at_max_exhausted(self):
        """Three prior VMAF-fail attempts at MaxRequeueAttempts=3 exhausts budget."""
        AttemptRepo = MagicMock()
        AttemptRepo.GetTranscodeAttemptsByMediaFileId.return_value = [
            _MakeAttempt(VMAF=70), _MakeAttempt(VMAF=72), _MakeAttempt(VMAF=80),
        ]
        GateRepo = MagicMock()
        GateRepo.Get.return_value = _MakeGateConfig(MaxRequeueAttempts=3)
        Svc = RetryBudgetService(AttemptRepo, GateRepo)
        assert Svc.HasBudgetRemaining(MediaFileId=42) is False

    # directive: perfect-solid-transcode-pipeline | # see perfect-solid-transcode-pipeline.C7
    def test_high_vmaf_does_not_consume_budget(self):
        """Attempts with VMAF >= gate threshold do not count against the budget."""
        AttemptRepo = MagicMock()
        AttemptRepo.GetTranscodeAttemptsByMediaFileId.return_value = [
            _MakeAttempt(VMAF=95), _MakeAttempt(VMAF=91), _MakeAttempt(VMAF=89),
        ]
        GateRepo = MagicMock()
        GateRepo.Get.return_value = _MakeGateConfig(MaxRequeueAttempts=3)
        Svc = RetryBudgetService(AttemptRepo, GateRepo)
        assert Svc.HasBudgetRemaining(MediaFileId=42) is True

    # directive: perfect-solid-transcode-pipeline | # see perfect-solid-transcode-pipeline.C7
    def test_failed_transcode_does_not_consume_budget(self):
        """Attempts with Success=False are not budget-consuming (they are infrastructure failures)."""
        AttemptRepo = MagicMock()
        AttemptRepo.GetTranscodeAttemptsByMediaFileId.return_value = [
            _MakeAttempt(Success=False, VMAF=None),
            _MakeAttempt(Success=False, VMAF=None),
            _MakeAttempt(Success=False, VMAF=None),
        ]
        GateRepo = MagicMock()
        GateRepo.Get.return_value = _MakeGateConfig(MaxRequeueAttempts=3)
        Svc = RetryBudgetService(AttemptRepo, GateRepo)
        assert Svc.HasBudgetRemaining(MediaFileId=42) is True

    # directive: perfect-solid-transcode-pipeline | # see perfect-solid-transcode-pipeline.C7
    def test_null_vmaf_does_not_consume_budget(self):
        """Attempts with no VMAF score yet (awaiting quality test) are not budget-consuming."""
        AttemptRepo = MagicMock()
        AttemptRepo.GetTranscodeAttemptsByMediaFileId.return_value = [
            _MakeAttempt(Success=True, VMAF=None),
            _MakeAttempt(Success=True, VMAF=None),
            _MakeAttempt(Success=True, VMAF=None),
        ]
        GateRepo = MagicMock()
        GateRepo.Get.return_value = _MakeGateConfig(MaxRequeueAttempts=3)
        Svc = RetryBudgetService(AttemptRepo, GateRepo)
        assert Svc.HasBudgetRemaining(MediaFileId=42) is True

    # directive: perfect-solid-transcode-pipeline | # see perfect-solid-transcode-pipeline.C7
    def test_reads_gate_config_fresh_per_call(self):
        """C7 invariant: GateConfig.Get is called on every HasBudgetRemaining; mid-flight MaxAttempts change is honored."""
        AttemptRepo = MagicMock()
        AttemptRepo.GetTranscodeAttemptsByMediaFileId.return_value = [
            _MakeAttempt(VMAF=70), _MakeAttempt(VMAF=72),
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

    # directive: perfect-solid-transcode-pipeline | # see perfect-solid-transcode-pipeline.C7
    def test_threshold_change_honored_per_call(self):
        """Threshold change mid-flight reclassifies which attempts count as budget-consuming."""
        AttemptRepo = MagicMock()
        AttemptRepo.GetTranscodeAttemptsByMediaFileId.return_value = [
            _MakeAttempt(VMAF=85), _MakeAttempt(VMAF=86), _MakeAttempt(VMAF=87),
        ]
        GateRepo = MagicMock()
        GateRepo.Get.return_value = _MakeGateConfig(MaxRequeueAttempts=3, VmafAutoReplaceMinThreshold=80.0)
        Svc = RetryBudgetService(AttemptRepo, GateRepo)
        assert Svc.HasBudgetRemaining(MediaFileId=42) is True
        GateRepo.Get.return_value = _MakeGateConfig(MaxRequeueAttempts=3, VmafAutoReplaceMinThreshold=88.0)
        assert Svc.HasBudgetRemaining(MediaFileId=42) is False
