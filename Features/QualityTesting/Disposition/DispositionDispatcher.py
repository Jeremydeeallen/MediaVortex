import json
from datetime import datetime, timezone
from typing import Optional

from Core.Logging.LoggingService import LoggingService
from Features.QualityTesting.Disposition.Disposition import Disposition
from Features.QualityTesting.Models.DispositionResult import DispositionResult


# directive: perfect-solid-transcode-pipeline | # see perfect-solid-transcode-pipeline.C8
class DispositionDispatcher:
    """Orchestrates ST7 disposition: read attempt + gate config, delegate to Decider, write outcome, cleanup TFP (replaces PostTranscodeDispositionService.DecidePostTranscodeDisposition)."""

    TERMINAL_DISPOSITIONS = ('Discard', 'NoReplace', 'Requeue')
    VALID_DISPOSITIONS = ('Pending', 'Replace', 'BypassReplace', 'NoReplace', 'Requeue', 'Discard')

    # directive: perfect-solid-transcode-pipeline | # see perfect-solid-transcode-pipeline.C8
    def __init__(self, Decider, GateConfigRepository, AttemptCleanupService, DatabaseService,
                 RetranscodeDecider=None, AdjustmentRegistry=None, RetryBudgetService=None):
        """Inject the core decision dependencies plus optional Phase-2 strategies (composed for forward use)."""
        self.Decider = Decider
        self.GateConfigRepository = GateConfigRepository
        self.AttemptCleanupService = AttemptCleanupService
        self.DatabaseService = DatabaseService
        self.RetranscodeDecider = RetranscodeDecider
        self.AdjustmentRegistry = AdjustmentRegistry
        self.RetryBudgetService = RetryBudgetService

    # directive: perfect-solid-transcode-pipeline | # see perfect-solid-transcode-pipeline.C8
    def Dispatch(self, TranscodeAttemptId: int) -> DispositionResult:
        """Decide + commit disposition for an attempt; idempotent on non-Pending; returns legacy DispositionResult."""
        try:
            Row = self._ReadAttemptRow(TranscodeAttemptId)
            if Row is None:
                return DispositionResult(Disposition='Discard', Reason='TranscodeFailed',
                                         AuditPayload={'error': 'attempt_not_found'})

            Cached = self._CheckCachedDisposition(Row)
            if Cached is not None:
                LoggingService.LogDebug(
                    f"Disposition already committed for TranscodeAttempt {TranscodeAttemptId}: {Cached.Disposition} ({Cached.Reason})",
                    "DispositionDispatcher", "Dispatch",
                )
                return Cached

            ShortCircuit = self._TestVariantShortCircuit(TranscodeAttemptId, Row)
            if ShortCircuit is not None:
                return ShortCircuit

            GateConfig = self.GateConfigRepository.Get()
            VmafCapableWorkerOnline = self._QueryVmafCapableWorkerOnline()
            Attempt = self._BuildDeciderInput(Row, VmafCapableWorkerOnline)
            GateInput = self._BuildGateInput(GateConfig)

            Outcome = self.Decider.Decide(Attempt, GateInput)
            self._LogAdvisoryBudget(Outcome, Row, TranscodeAttemptId)

            self._CommitDisposition(TranscodeAttemptId, Outcome.Action, Outcome.Reason)
            self._MaybeCleanupTfp(TranscodeAttemptId, Outcome.Action)

            AuditPayload = self._BuildAuditPayload(TranscodeAttemptId, Attempt, VmafCapableWorkerOnline, GateConfig)
            LoggingService.LogInfo(
                f"Disposition for TranscodeAttempt {TranscodeAttemptId}: {Outcome.Action} (Reason={Outcome.Reason}) inputs={json.dumps(AuditPayload, default=str)}",
                "DispositionDispatcher", "Dispatch",
            )
            return DispositionResult(Disposition=Outcome.Action, Reason=Outcome.Reason, AuditPayload=AuditPayload)

        except Exception as Ex:
            LoggingService.LogException(
                f"Dispatch failed for TranscodeAttempt {TranscodeAttemptId}",
                Ex, "DispositionDispatcher", "Dispatch",
            )
            return DispositionResult(Disposition='Pending', Reason='', AuditPayload={'error': str(Ex)})

    # directive: perfect-solid-transcode-pipeline | # see perfect-solid-transcode-pipeline.C8
    def _ReadAttemptRow(self, TranscodeAttemptId: int) -> Optional[dict]:
        """Read the attempt row needed for the disposition decision; returns None if not found."""
        Rows = self.DatabaseService.ExecuteQuery(
            "SELECT Success, OldSizeBytes, NewSizeBytes, QualityTestRequired, VMAF, "
            "Disposition, DispositionReason, TestVariantSetId, MediaFileId "
            "FROM TranscodeAttempts WHERE Id = %s",
            (TranscodeAttemptId,),
        )
        if not Rows:
            LoggingService.LogError(
                f"Dispatch: TranscodeAttempt {TranscodeAttemptId} not found",
                "DispositionDispatcher", "_ReadAttemptRow",
            )
            return None
        return Rows[0]

    # directive: perfect-solid-transcode-pipeline | # see perfect-solid-transcode-pipeline.C8
    def _CheckCachedDisposition(self, Row: dict) -> Optional[DispositionResult]:
        """If a non-Pending disposition was already committed, return it (idempotent re-dispatch)."""
        Existing = Row.get('Disposition')
        if Existing and Existing != 'Pending':
            return DispositionResult(
                Disposition=Existing,
                Reason=Row.get('DispositionReason') or '',
                AuditPayload={'cached': True},
            )
        return None

    # directive: perfect-solid-transcode-pipeline | # see perfect-solid-transcode-pipeline.C8
    def _TestVariantShortCircuit(self, TranscodeAttemptId: int, Row: dict) -> Optional[DispositionResult]:
        """Test-variant attempts always disposition as NoReplace/TestMode (source preservation guaranteed)."""
        TestVariantSetId = Row.get('TestVariantSetId')
        if TestVariantSetId is None:
            return None
        self._CommitDisposition(TranscodeAttemptId, 'NoReplace', 'TestMode')
        LoggingService.LogInfo(
            f"Disposition for TranscodeAttempt {TranscodeAttemptId}: NoReplace (Reason=TestMode, TestVariantSetId={TestVariantSetId})",
            "DispositionDispatcher", "_TestVariantShortCircuit",
        )
        return DispositionResult(
            Disposition='NoReplace',
            Reason='TestMode',
            AuditPayload={'TranscodeAttemptId': TranscodeAttemptId, 'TestVariantSetId': TestVariantSetId, 'shortCircuit': True},
        )

    # directive: transcode-worker-unification | # see disposition.S1
    def _QueryVmafCapableWorkerOnline(self) -> bool:
        """Probe whether any VMAF-capable worker is online within the heartbeat window."""
        try:
            HeartbeatSec = self.GateConfigRepository.Get().WorkerHeartbeatWindowSec
            Rows = self.DatabaseService.ExecuteQuery(
                "SELECT 1 FROM Workers WHERE QualityTestEnabled = TRUE AND Status = 'Online' "
                "AND LastHeartbeat > NOW() - (INTERVAL '1 second' * %s) LIMIT 1",
                (HeartbeatSec,),
            )
            return bool(Rows)
        except Exception as Ex:
            LoggingService.LogException(
                "VmafCapableWorkerOnline probe failed; defaulting to False",
                Ex, "DispositionDispatcher", "_QueryVmafCapableWorkerOnline",
            )
            return False

    # directive: perfect-solid-transcode-pipeline | # see perfect-solid-transcode-pipeline.C8
    def _BuildDeciderInput(self, Row: dict, VmafCapableWorkerOnline: bool) -> dict:
        """Project the DB row into the pure-function Decider's expected input shape."""
        return {
            'Success': bool(Row.get('Success')),
            'OldSize': Row.get('OldSizeBytes') or 0,
            'NewSize': Row.get('NewSizeBytes') or 0,
            'QualityTestRequired': bool(Row.get('QualityTestRequired')),
            'VmafScore': Row.get('VMAF'),
            'VmafCapableWorkerOnline': VmafCapableWorkerOnline,
            'MediaFileId': Row.get('MediaFileId'),
        }

    # directive: perfect-solid-transcode-pipeline | # see perfect-solid-transcode-pipeline.C8
    def _BuildGateInput(self, GateConfig) -> dict:
        """Project GateConfig model fields into the pure-function Decider's expected input shape."""
        return {
            'VmafAutoReplaceMinThreshold': float(GateConfig.VmafAutoReplaceMinThreshold),
            'VmafAutoReplaceMaxThreshold': float(GateConfig.VmafAutoReplaceMaxThreshold),
            'WhenVmafUnavailable': GateConfig.WhenVmafUnavailable,
            'QualityTestEnabled': bool(getattr(GateConfig, 'QualityTestEnabled', True)),
        }

    # directive: perfect-solid-transcode-pipeline | # see perfect-solid-transcode-pipeline.C8
    def _BuildAuditPayload(self, TranscodeAttemptId: int, Attempt: dict, VmafCapableWorkerOnline: bool, GateConfig) -> dict:
        """Assemble the audit payload for the single rolled-up INFO log line per decision."""
        return {
            'TranscodeAttemptId': TranscodeAttemptId,
            'Success': Attempt['Success'],
            'OldSizeBytes': Attempt['OldSize'],
            'NewSizeBytes': Attempt['NewSize'],
            'QualityTestRequired': Attempt['QualityTestRequired'],
            'VmafScore': Attempt['VmafScore'],
            'VmafCapableWorkerOnline': VmafCapableWorkerOnline,
            'VmafAutoReplaceMinThreshold': float(GateConfig.VmafAutoReplaceMinThreshold),
            'VmafAutoReplaceMaxThreshold': float(GateConfig.VmafAutoReplaceMaxThreshold),
            'WhenVmafUnavailable': GateConfig.WhenVmafUnavailable,
            'QualityTestEnabled': bool(getattr(GateConfig, 'QualityTestEnabled', True)),
        }

    # directive: perfect-solid-transcode-pipeline | # see perfect-solid-transcode-pipeline.C8
    def _LogAdvisoryBudget(self, Outcome: Disposition, Row: dict, TranscodeAttemptId: int) -> None:
        """For Requeue dispositions, emit an advisory budget log line (Phase 2 will use this to override Requeue->Discard)."""
        if Outcome.Action != 'Requeue':
            return
        if self.RetryBudgetService is None:
            return
        MediaFileId = Row.get('MediaFileId')
        if MediaFileId is None:
            return
        try:
            HasBudget = self.RetryBudgetService.HasBudgetRemaining(MediaFileId)
            LoggingService.LogInfo(
                f"RetryBudget advisory (TranscodeAttemptId={TranscodeAttemptId}, MediaFileId={MediaFileId}): HasBudgetRemaining={HasBudget}",
                "DispositionDispatcher", "_LogAdvisoryBudget",
            )
        except Exception as Ex:
            LoggingService.LogException(
                "RetryBudget advisory probe failed (non-fatal)",
                Ex, "DispositionDispatcher", "_LogAdvisoryBudget",
            )

    # directive: perfect-solid-transcode-pipeline | # see perfect-solid-transcode-pipeline.C8
    def _CommitDisposition(self, TranscodeAttemptId: int, Action: str, Reason: str) -> None:
        """UPDATE TranscodeAttempts disposition columns; validates Action against the allowed enum."""
        if Action not in self.VALID_DISPOSITIONS:
            LoggingService.LogError(
                f"Refusing to commit invalid Disposition={Action!r} for attempt {TranscodeAttemptId}",
                "DispositionDispatcher", "_CommitDisposition",
            )
            return
        try:
            self.DatabaseService.ExecuteNonQuery(
                "UPDATE TranscodeAttempts SET Disposition = %s, DispositionReason = %s, "
                "DispositionDecidedAt = %s WHERE Id = %s",
                (Action, Reason or None, datetime.now(timezone.utc), TranscodeAttemptId),
            )
        except Exception as Ex:
            LoggingService.LogException(
                f"_CommitDisposition failed for attempt {TranscodeAttemptId}",
                Ex, "DispositionDispatcher", "_CommitDisposition",
            )

    # directive: perfect-solid-transcode-pipeline | # see perfect-solid-transcode-pipeline.C8
    def _MaybeCleanupTfp(self, TranscodeAttemptId: int, Action: str) -> None:
        """For terminal dispositions, drop the TFP row via AttemptCleanupService."""
        if Action in self.TERMINAL_DISPOSITIONS:
            self.AttemptCleanupService.Cleanup(TranscodeAttemptId)
