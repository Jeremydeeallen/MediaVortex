import json
from datetime import datetime, timezone
from typing import Optional

from Core.Logging.LoggingService import LoggingService
from Features.QualityTesting.Disposition.Disposition import Disposition
from Features.QualityTesting.Models.DispositionResult import DispositionResult


# directive: perfect-solid-transcode-pipeline | # see perfect-solid-transcode-pipeline.C8
class DispositionDispatcher:
    """Orchestrates ST7 disposition: read attempt + gate config, delegate to Decider, write outcome, cleanup TFP (replaces PostTranscodeDispositionService.DecidePostTranscodeDisposition)."""

    TERMINAL_DISPOSITIONS = ('Reject', 'Requeue')
    VALID_DISPOSITIONS = ('Pending', 'Replace', 'Reject', 'Requeue')

    # directive: transcode-flow-canonical | # see transcode.ST7
    def __init__(self, Decider, GateConfigRepository, AttemptCleanupService, DatabaseService,
                 RetranscodeDecider=None, AdjustmentRegistry=None, RetryBudgetService=None,
                 RequeueScheduler=None, RetainInprogressPolicy=None):
        """Inject core dependencies plus optional Phase-2 strategies, Requeue scheduler (BUG-0079), and retain-inprogress policy."""
        self.Decider = Decider
        self.GateConfigRepository = GateConfigRepository
        self.AttemptCleanupService = AttemptCleanupService
        self.DatabaseService = DatabaseService
        self.RetranscodeDecider = RetranscodeDecider
        self.AdjustmentRegistry = AdjustmentRegistry
        self.RetryBudgetService = RetryBudgetService
        self.RequeueScheduler = RequeueScheduler
        from Features.QualityTesting.Disposition.RetainInprogressPolicy import RetainInprogressPolicy as _DefaultPolicy
        self.RetainPolicy = RetainInprogressPolicy or _DefaultPolicy()

    # directive: perfect-solid-transcode-pipeline | # see perfect-solid-transcode-pipeline.C8
    def Dispatch(self, TranscodeAttemptId: int) -> DispositionResult:
        """Decide + commit disposition for an attempt; idempotent on non-Pending; returns legacy DispositionResult."""
        try:
            Row = self._ReadAttemptRow(TranscodeAttemptId)
            if Row is None:
                return DispositionResult(Disposition='Reject', Reason='TranscodeFailed',
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
            Outcome, EscalatedProfileId = self._EnforceQualityCeiling(Outcome, Row, TranscodeAttemptId)
            Outcome = self._EnforceRetryBudget(Outcome, Row, TranscodeAttemptId)

            self._CommitDisposition(TranscodeAttemptId, Outcome.Action, Outcome.Reason)
            self._MaybeCleanupArtifacts(TranscodeAttemptId, Outcome.Action, Outcome.Reason)
            self._MaybeScheduleRequeue(TranscodeAttemptId, Outcome.Action, Row, EscalatedProfileId)

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
            "Disposition, DispositionReason, TestVariantSetId, MediaFileId, ProfileName "
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

    # directive: transcode-flow-canonical | # see transcode.ST7
    def _TestVariantShortCircuit(self, TranscodeAttemptId: int, Row: dict) -> Optional[DispositionResult]:
        """Test-variant attempts always disposition as Reject/TestMode; RetainInprogressPolicy keeps the artifact for comparison."""
        TestVariantSetId = Row.get('TestVariantSetId')
        if TestVariantSetId is None:
            return None
        self._CommitDisposition(TranscodeAttemptId, 'Reject', 'TestMode')
        LoggingService.LogInfo(
            f"Disposition for TranscodeAttempt {TranscodeAttemptId}: Reject (Reason=TestMode, TestVariantSetId={TestVariantSetId})",
            "DispositionDispatcher", "_TestVariantShortCircuit",
        )
        return DispositionResult(
            Disposition='Reject',
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
            'MinConfidenceSampleCount': int(getattr(GateConfig, 'MinConfidenceSampleCount', 10)),
            'MinConfidencePassRate': float(getattr(GateConfig, 'MinConfidencePassRate', 0.95)),
            'SigmaMargin': float(getattr(GateConfig, 'SigmaMargin', 2.0)),
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

    # directive: transcode-flow-canonical | # see transcode.ST7 -- NextTierAdjuster ceiling fold
    def _EnforceQualityCeiling(self, Outcome: Disposition, Row: dict, TranscodeAttemptId: int):
        if Outcome.Action != 'Requeue':
            return Outcome, None
        CurrentProfileName = Row.get('ProfileName')
        if not CurrentProfileName:
            return Outcome, None
        from Features.TranscodeJob.Adjustments.NextTierAdjustmentCalculator import NextTierAdjuster
        NextProfile = NextTierAdjuster(self.DatabaseService).Get(CurrentProfileName)
        if NextProfile is None:
            LoggingService.LogWarning(
                f"QualityCeiling reached (TranscodeAttemptId={TranscodeAttemptId}, ProfileName={CurrentProfileName}): overriding Requeue -> Reject/QualityCeilingReached",
                "DispositionDispatcher", "_EnforceQualityCeiling",
            )
            return Disposition(Action='Reject', Reason='QualityCeilingReached'), None
        LoggingService.LogInfo(
            f"NextTier escalation (TranscodeAttemptId={TranscodeAttemptId}): {CurrentProfileName} -> {NextProfile.ProfileName} (Tier {NextProfile.QualityTier})",
            "DispositionDispatcher", "_EnforceQualityCeiling",
        )
        return Outcome, NextProfile.ProfileId

    # directive: transcode-flow-canonical | # see transcode.ST7 -- BUG-0079 cap
    def _EnforceRetryBudget(self, Outcome: Disposition, Row: dict, TranscodeAttemptId: int) -> Disposition:
        """Requeue -> Reject/RetryBudgetExhausted when MediaFile.MaxRequeueAttempts already hit. Prevents infinite loops."""
        if Outcome.Action != 'Requeue':
            return Outcome
        if self.RetryBudgetService is None:
            return Outcome
        MediaFileId = Row.get('MediaFileId')
        if MediaFileId is None:
            return Outcome
        try:
            HasBudget = self.RetryBudgetService.HasBudgetRemaining(MediaFileId)
        except Exception as Ex:
            LoggingService.LogException(
                "RetryBudget probe failed; leaving Requeue in place",
                Ex, "DispositionDispatcher", "_EnforceRetryBudget",
            )
            return Outcome
        if HasBudget:
            LoggingService.LogInfo(
                f"RetryBudget OK (TranscodeAttemptId={TranscodeAttemptId}, MediaFileId={MediaFileId}): Requeue proceeds",
                "DispositionDispatcher", "_EnforceRetryBudget",
            )
            return Outcome
        LoggingService.LogWarning(
            f"RetryBudget exhausted (TranscodeAttemptId={TranscodeAttemptId}, MediaFileId={MediaFileId}): overriding Requeue -> Reject/RetryBudgetExhausted",
            "DispositionDispatcher", "_EnforceRetryBudget",
        )
        return Disposition(Action='Reject', Reason='RetryBudgetExhausted')

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

    # directive: transcode-flow-canonical | # see transcode.ST7
    def _MaybeCleanupArtifacts(self, TranscodeAttemptId: int, Action: str, Reason: str) -> None:
        """For terminal dispositions, drop TFP row via AttemptCleanupService unless the Reason retains inprogress for operator inspection."""
        if Action not in self.TERMINAL_DISPOSITIONS:
            return
        if self.RetainPolicy.ShouldRetain(Reason or ''):
            LoggingService.LogInfo(
                f"Retaining inprogress artifact for TranscodeAttempt {TranscodeAttemptId} (Reason={Reason})",
                "DispositionDispatcher", "_MaybeCleanupArtifacts",
            )
            return
        self.AttemptCleanupService.Cleanup(TranscodeAttemptId)

    # directive: transcode-flow-canonical | # see transcode.ST7 -- BUG-0079 + NextTier escalation
    def _MaybeScheduleRequeue(self, TranscodeAttemptId: int, Action: str, Row: dict, EscalatedProfileId: Optional[int] = None) -> None:
        if Action != 'Requeue':
            return
        MediaFileId = Row.get('MediaFileId')
        if MediaFileId is None:
            LoggingService.LogError(
                f"Requeue for TranscodeAttempt {TranscodeAttemptId}: MediaFileId missing; cannot enqueue new attempt",
                "DispositionDispatcher", "_MaybeScheduleRequeue",
            )
            return
        Scheduler = self.RequeueScheduler or self._DefaultRequeueScheduler
        try:
            Result = Scheduler(MediaFileId, TranscodeAttemptId, EscalatedProfileId)
            LoggingService.LogInfo(
                f"Requeue for TranscodeAttempt {TranscodeAttemptId} (MediaFileId={MediaFileId}, EscalatedProfileId={EscalatedProfileId}): scheduler result={Result}",
                "DispositionDispatcher", "_MaybeScheduleRequeue",
            )
        except Exception as Ex:
            LoggingService.LogException(
                f"Requeue scheduling failed for TranscodeAttempt {TranscodeAttemptId} (MediaFileId={MediaFileId})",
                Ex, "DispositionDispatcher", "_MaybeScheduleRequeue",
            )

    # directive: transcode-flow-canonical | # see transcode.ST7 -- BUG-0079 + NextTier escalation
    def _DefaultRequeueScheduler(self, MediaFileId: int, TranscodeAttemptId: int, EscalatedProfileId: Optional[int] = None) -> dict:
        from Features.TranscodeQueue.QueueManagementBusinessService import QueueManagementBusinessService
        from Repositories.DatabaseManager import DatabaseManager
        Service = QueueManagementBusinessService(DatabaseManager())
        return Service.AddJobToQueue(MediaFileId=MediaFileId, ForceAdd=True, ProfileId=EscalatedProfileId)
