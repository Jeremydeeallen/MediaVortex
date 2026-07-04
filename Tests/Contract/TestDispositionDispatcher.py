from unittest.mock import MagicMock

import pytest

from Features.QualityTesting.Disposition.Disposition import Disposition
from Features.QualityTesting.Disposition.DispositionDispatcher import DispositionDispatcher
from Features.QualityTesting.Models.DispositionResult import DispositionResult


# directive: perfect-solid-transcode-pipeline | # see perfect-solid-transcode-pipeline.C8
def _MakeGate(MinThreshold=88.0, MaxThreshold=98.0, WhenVmafUnavailable='block', QualityTestEnabled=True):
    """Build a mock GateConfig model for the dispatcher to read."""
    G = MagicMock()
    G.VmafAutoReplaceMinThreshold = MinThreshold
    G.VmafAutoReplaceMaxThreshold = MaxThreshold
    G.WhenVmafUnavailable = WhenVmafUnavailable
    G.QualityTestEnabled = QualityTestEnabled
    return G


# directive: perfect-solid-transcode-pipeline | # see perfect-solid-transcode-pipeline.C8
def _MakeDispatcher(AttemptRow=None, DeciderOutcome=None, GateConfig=None, RetryBudgetService=None,
                    VmafCapableRows=None):
    """Wire a DispositionDispatcher with mocks; return (dispatcher, db, decider, cleanup)."""
    Db = MagicMock()
    if VmafCapableRows is None:
        VmafCapableRows = []
    Db.ExecuteQuery.side_effect = [
        [AttemptRow] if AttemptRow is not None else [],
        VmafCapableRows,
    ]
    Decider = MagicMock()
    Decider.Decide.return_value = DeciderOutcome or Disposition(Action='Pending', Reason='AwaitingVmaf')
    GateRepo = MagicMock()
    GateRepo.Get.return_value = GateConfig or _MakeGate()
    Cleanup = MagicMock()
    Disp = DispositionDispatcher(
        Decider=Decider,
        GateConfigRepository=GateRepo,
        AttemptCleanupService=Cleanup,
        DatabaseService=Db,
        RetryBudgetService=RetryBudgetService,
    )
    return Disp, Db, Decider, Cleanup


# directive: perfect-solid-transcode-pipeline | # see perfect-solid-transcode-pipeline.C8
class TestDispositionDispatcher:
    """Contract: Dispatch reads attempt, delegates decision to Decider, commits + cleans up terminal dispositions."""

    # directive: transcode-flow-canonical | # see transcode.ST7
    def test_attempt_not_found_returns_reject(self):
        """Missing attempt row returns Reject/TranscodeFailed without invoking Decider."""
        Disp, Db, Decider, Cleanup = _MakeDispatcher(AttemptRow=None)
        Result = Disp.Dispatch(TranscodeAttemptId=999)
        assert Result.Disposition == 'Reject'
        assert Result.Reason == 'TranscodeFailed'
        Decider.Decide.assert_not_called()

    # directive: perfect-solid-transcode-pipeline | # see perfect-solid-transcode-pipeline.C8
    def test_cached_disposition_short_circuits(self):
        """Non-Pending existing disposition is returned without re-invoking the Decider."""
        Row = {'Success': True, 'OldSizeBytes': 100, 'NewSizeBytes': 80, 'QualityTestRequired': True,
               'VMAF': 92.0, 'Disposition': 'Replace', 'DispositionReason': 'VmafPassed',
               'TestVariantSetId': None, 'MediaFileId': 1}
        Disp, Db, Decider, Cleanup = _MakeDispatcher(AttemptRow=Row)
        Result = Disp.Dispatch(TranscodeAttemptId=5)
        assert Result.Disposition == 'Replace'
        assert Result.Reason == 'VmafPassed'
        assert Result.AuditPayload.get('cached') is True
        Decider.Decide.assert_not_called()

    # directive: transcode-flow-canonical | # see transcode.ST7
    def test_test_variant_short_circuits_to_reject_testmode(self):
        """Attempts tied to a TestVariantSetId are forced Reject/TestMode; RetainInprogressPolicy keeps artifact."""
        Row = {'Success': True, 'OldSizeBytes': 100, 'NewSizeBytes': 80, 'QualityTestRequired': True,
               'VMAF': 92.0, 'Disposition': None, 'DispositionReason': None,
               'TestVariantSetId': 7, 'MediaFileId': 1}
        Disp, Db, Decider, Cleanup = _MakeDispatcher(AttemptRow=Row)
        Result = Disp.Dispatch(TranscodeAttemptId=5)
        assert Result.Disposition == 'Reject'
        assert Result.Reason == 'TestMode'
        Decider.Decide.assert_not_called()
        Cleanup.Cleanup.assert_not_called()

    # directive: perfect-solid-transcode-pipeline | # see perfect-solid-transcode-pipeline.C8
    def test_decider_outcome_committed_for_replace(self):
        """Replace disposition: Decider called, DB UPDATE issued, cleanup NOT called (Replace is non-terminal for TFP)."""
        Row = {'Success': True, 'OldSizeBytes': 100, 'NewSizeBytes': 80, 'QualityTestRequired': True,
               'VMAF': 92.0, 'Disposition': None, 'DispositionReason': None,
               'TestVariantSetId': None, 'MediaFileId': 1}
        Disp, Db, Decider, Cleanup = _MakeDispatcher(
            AttemptRow=Row,
            DeciderOutcome=Disposition(Action='Replace', Reason='VmafPassed'),
        )
        Result = Disp.Dispatch(TranscodeAttemptId=5)
        assert Result.Disposition == 'Replace'
        assert Result.Reason == 'VmafPassed'
        Decider.Decide.assert_called_once()
        Cleanup.Cleanup.assert_not_called()

    # directive: transcode-flow-canonical | # see transcode.ST7
    def test_terminal_reject_triggers_cleanup(self):
        """Reject/TranscodeFailed triggers AttemptCleanupService.Cleanup (no retain-inprogress reason)."""
        Row = {'Success': False, 'OldSizeBytes': 100, 'NewSizeBytes': 0, 'QualityTestRequired': False,
               'VMAF': None, 'Disposition': None, 'DispositionReason': None,
               'TestVariantSetId': None, 'MediaFileId': 1}
        Disp, Db, Decider, Cleanup = _MakeDispatcher(
            AttemptRow=Row,
            DeciderOutcome=Disposition(Action='Reject', Reason='TranscodeFailed'),
        )
        Disp.Dispatch(TranscodeAttemptId=42)
        Cleanup.Cleanup.assert_called_once_with(42)

    # directive: perfect-solid-transcode-pipeline | # see perfect-solid-transcode-pipeline.C8
    def test_terminal_requeue_triggers_cleanup(self):
        """Requeue disposition triggers AttemptCleanupService.Cleanup (TFP belongs to the failed attempt)."""
        Row = {'Success': True, 'OldSizeBytes': 100, 'NewSizeBytes': 80, 'QualityTestRequired': True,
               'VMAF': 70.0, 'Disposition': None, 'DispositionReason': None,
               'TestVariantSetId': None, 'MediaFileId': 1}
        Disp, Db, Decider, Cleanup = _MakeDispatcher(
            AttemptRow=Row,
            DeciderOutcome=Disposition(Action='Requeue', Reason='VmafBelowMin'),
        )
        Disp.Dispatch(TranscodeAttemptId=42)
        Cleanup.Cleanup.assert_called_once_with(42)

    # directive: perfect-solid-transcode-pipeline | # see perfect-solid-transcode-pipeline.C8
    def test_pending_disposition_does_not_trigger_cleanup(self):
        """Pending (AwaitingVmaf) is NOT terminal -- TFP remains for the upcoming VMAF run."""
        Row = {'Success': True, 'OldSizeBytes': 100, 'NewSizeBytes': 80, 'QualityTestRequired': True,
               'VMAF': None, 'Disposition': None, 'DispositionReason': None,
               'TestVariantSetId': None, 'MediaFileId': 1}
        Disp, Db, Decider, Cleanup = _MakeDispatcher(
            AttemptRow=Row,
            DeciderOutcome=Disposition(Action='Pending', Reason='AwaitingVmaf'),
        )
        Disp.Dispatch(TranscodeAttemptId=42)
        Cleanup.Cleanup.assert_not_called()

    # directive: perfect-solid-transcode-pipeline | # see perfect-solid-transcode-pipeline.C8
    def test_advisory_budget_logged_for_requeue_when_service_provided(self):
        """When RetryBudgetService is composed, Requeue dispositions probe HasBudgetRemaining for advisory log."""
        Row = {'Success': True, 'OldSizeBytes': 100, 'NewSizeBytes': 80, 'QualityTestRequired': True,
               'VMAF': 70.0, 'Disposition': None, 'DispositionReason': None,
               'TestVariantSetId': None, 'MediaFileId': 7}
        BudgetSvc = MagicMock()
        BudgetSvc.HasBudgetRemaining.return_value = True
        Disp, Db, Decider, Cleanup = _MakeDispatcher(
            AttemptRow=Row,
            DeciderOutcome=Disposition(Action='Requeue', Reason='VmafBelowMin'),
            RetryBudgetService=BudgetSvc,
        )
        Disp.Dispatch(TranscodeAttemptId=42)
        BudgetSvc.HasBudgetRemaining.assert_called_once_with(7)

    # directive: perfect-solid-transcode-pipeline | # see perfect-solid-transcode-pipeline.C8
    def test_advisory_budget_skipped_for_non_requeue(self):
        """Advisory budget probe is only emitted for Requeue (Replace skips it)."""
        Row = {'Success': True, 'OldSizeBytes': 100, 'NewSizeBytes': 80, 'QualityTestRequired': True,
               'VMAF': 92.0, 'Disposition': None, 'DispositionReason': None,
               'TestVariantSetId': None, 'MediaFileId': 7}
        BudgetSvc = MagicMock()
        Disp, Db, Decider, Cleanup = _MakeDispatcher(
            AttemptRow=Row,
            DeciderOutcome=Disposition(Action='Replace', Reason='VmafPassed'),
            RetryBudgetService=BudgetSvc,
        )
        Disp.Dispatch(TranscodeAttemptId=42)
        BudgetSvc.HasBudgetRemaining.assert_not_called()

    # directive: transcode-flow-canonical | # see transcode.ST7 -- BUG-0079 cap
    def test_requeue_becomes_reject_when_budget_exhausted(self):
        """RetryBudgetService returns False -> Requeue overrides to Reject/RetryBudgetExhausted; scheduler NOT invoked."""
        Row = {'Success': True, 'OldSizeBytes': 100, 'NewSizeBytes': 80, 'QualityTestRequired': True,
               'VMAF': 70.0, 'Disposition': None, 'DispositionReason': None,
               'TestVariantSetId': None, 'MediaFileId': 7}
        BudgetSvc = MagicMock()
        BudgetSvc.HasBudgetRemaining.return_value = False
        Scheduler = MagicMock()
        Disp, Db, Decider, Cleanup = _MakeDispatcher(
            AttemptRow=Row,
            DeciderOutcome=Disposition(Action='Requeue', Reason='VmafBelowMin'),
            RetryBudgetService=BudgetSvc,
        )
        Disp.RequeueScheduler = Scheduler
        Result = Disp.Dispatch(TranscodeAttemptId=42)
        assert Result.Disposition == 'Reject'
        assert Result.Reason == 'RetryBudgetExhausted'
        Scheduler.assert_not_called()
        Cleanup.Cleanup.assert_called_once_with(42)

    # directive: transcode-flow-canonical | # see transcode.ST7 -- BUG-0079 scheduler
    def test_requeue_with_budget_invokes_scheduler(self):
        """RetryBudget=True + Requeue -> scheduler invoked with (MediaFileId, TranscodeAttemptId); cleanup fires."""
        Row = {'Success': True, 'OldSizeBytes': 100, 'NewSizeBytes': 80, 'QualityTestRequired': True,
               'VMAF': 70.0, 'Disposition': None, 'DispositionReason': None,
               'TestVariantSetId': None, 'MediaFileId': 7, 'ProfileName': None}
        BudgetSvc = MagicMock()
        BudgetSvc.HasBudgetRemaining.return_value = True
        Scheduler = MagicMock(return_value={'Success': True, 'QueueId': 999})
        Disp, Db, Decider, Cleanup = _MakeDispatcher(
            AttemptRow=Row,
            DeciderOutcome=Disposition(Action='Requeue', Reason='VmafBelowMin'),
            RetryBudgetService=BudgetSvc,
        )
        Disp.RequeueScheduler = Scheduler
        Result = Disp.Dispatch(TranscodeAttemptId=42)
        assert Result.Disposition == 'Requeue'
        # ProfileName=None -> ceiling short-circuit skipped; EscalatedProfileId is None
        Scheduler.assert_called_once_with(7, 42, None)
        Cleanup.Cleanup.assert_called_once_with(42)
