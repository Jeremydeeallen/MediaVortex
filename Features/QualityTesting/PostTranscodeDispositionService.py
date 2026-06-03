import json
from datetime import datetime, timezone
from typing import Optional, Tuple

from Core.Logging.LoggingService import LoggingService
from Core.Database.DatabaseService import DatabaseService
from Repositories.DatabaseManager import DatabaseManager
from Features.QualityTesting.PostTranscodeGateConfigRepository import (
    PostTranscodeGateConfigRepository,
)
from Features.QualityTesting.Models.DispositionResult import DispositionResult


DISPOSITIONS = ('Pending', 'Replace', 'BypassReplace', 'NoReplace', 'Requeue', 'Discard')

REASONS = (
    'TranscodeFailed',
    'NoSavings',
    'QualityTestNotRequired',
    'AwaitingVmaf',
    'VmafBelowMin',
    'VmafPassed',
    'VmafAboveMax',
    'VmafServicePaused',
    'VmafServicePausedBypassed',
    'VmafCapabilityNotConfigured',
    'QualityTestingGloballyDisabled',
    'OperatorForcedReplace',
    'OperatorDiscarded',
    'TestMode',
    'ComplianceGateFailed',
)


# directive: filereplacement-decompose | see post-transcode-disposition.feature.md
class PostTranscodeDispositionService:
    """Single decision function for post-transcode disposition; see post-transcode-disposition.feature.md."""

    # directive: filereplacement-decompose
    def __init__(self, DatabaseManagerInstance: DatabaseManager = None,
                 GateConfigRepoInstance: PostTranscodeGateConfigRepository = None):
        self.DatabaseManager = DatabaseManagerInstance or DatabaseManager()
        self.GateConfigRepo = GateConfigRepoInstance or PostTranscodeGateConfigRepository()

    # directive: filereplacement-decompose | see post-transcode-disposition.C1, C2
    def DecidePostTranscodeDisposition(self, TranscodeAttemptId: int) -> DispositionResult:
        """Decide disposition for an attempt; idempotent on non-Pending; see post-transcode-disposition.C1, C2."""
        try:
            Db = DatabaseService()
            # allow: R12 SQL preexisting; relocate to TranscodeAttemptsRepository in follow-up
            Rows = Db.ExecuteQuery(
                """
                SELECT Success, OldSizeBytes, NewSizeBytes, QualityTestRequired, VMAF,
                       Disposition, DispositionReason, TestVariantSetId
                FROM TranscodeAttempts WHERE Id = %s
                """,
                (TranscodeAttemptId,),
            )
            if not Rows:
                LoggingService.LogError(
                    f"DecidePostTranscodeDisposition: TranscodeAttempt {TranscodeAttemptId} not found",
                    "PostTranscodeDispositionService", "DecidePostTranscodeDisposition",
                )
                return DispositionResult(Disposition='Discard', Reason='TranscodeFailed',
                                         AuditPayload={'error': 'attempt_not_found'})
            Row = Rows[0]

            ExistingDisposition = Row.get('Disposition')
            ExistingReason = Row.get('DispositionReason')
            if ExistingDisposition and ExistingDisposition != 'Pending':
                LoggingService.LogDebug(
                    f"Disposition already committed for TranscodeAttempt {TranscodeAttemptId}: "
                    f"{ExistingDisposition} ({ExistingReason})",
                    "PostTranscodeDispositionService", "DecidePostTranscodeDisposition",
                )
                return DispositionResult(
                    Disposition=ExistingDisposition,
                    Reason=ExistingReason or '',
                    AuditPayload={'cached': True},
                )

            TestVariantSetId = Row.get('TestVariantSetId')
            if TestVariantSetId is not None:
                self._CommitDisposition(TranscodeAttemptId, 'NoReplace', 'TestMode')
                LoggingService.LogInfo(
                    f"Disposition for TranscodeAttempt {TranscodeAttemptId}: NoReplace "
                    f"(Reason=TestMode, TestVariantSetId={TestVariantSetId}) -- source preservation guaranteed",
                    "PostTranscodeDispositionService", "DecidePostTranscodeDisposition",
                )
                return DispositionResult(
                    Disposition='NoReplace',
                    Reason='TestMode',
                    AuditPayload={'TranscodeAttemptId': TranscodeAttemptId, 'TestVariantSetId': TestVariantSetId, 'shortCircuit': True},
                )

            Success = bool(Row.get('Success'))
            OldSize = Row.get('OldSizeBytes') or 0
            NewSize = Row.get('NewSizeBytes') or 0
            QualityTestRequired = bool(Row.get('QualityTestRequired'))
            VmafScore = Row.get('VMAF')

            # allow: R12 SQL preexisting; relocate to WorkersRepository in follow-up
            CapableRows = DatabaseService().ExecuteQuery(
                """
                SELECT 1 FROM Workers
                WHERE QualityTestEnabled = TRUE
                  AND Status = 'Online'
                  AND LastHeartbeat > NOW() - INTERVAL '90 seconds'
                LIMIT 1
                """,
            )
            VmafCapableWorkerOnline = bool(CapableRows)

            GateConfig = self.GateConfigRepo.Get()

            AuditPayload = {
                'TranscodeAttemptId': TranscodeAttemptId,
                'Success': Success,
                'OldSizeBytes': OldSize,
                'NewSizeBytes': NewSize,
                'QualityTestRequired': QualityTestRequired,
                'VmafScore': VmafScore,
                'VmafCapableWorkerOnline': VmafCapableWorkerOnline,
                'VmafAutoReplaceMinThreshold': GateConfig.VmafAutoReplaceMinThreshold,
                'VmafAutoReplaceMaxThreshold': GateConfig.VmafAutoReplaceMaxThreshold,
                'WhenVmafUnavailable': GateConfig.WhenVmafUnavailable,
                'QualityTestEnabled': bool(getattr(GateConfig, 'QualityTestEnabled', True)),
            }

            Disposition, Reason = self._DecideFromInputs(
                Success=Success,
                OldSize=OldSize,
                NewSize=NewSize,
                QualityTestRequired=QualityTestRequired,
                VmafScore=VmafScore,
                VmafCapableWorkerOnline=VmafCapableWorkerOnline,
                GateConfig=GateConfig,
            )

            self._CommitDisposition(TranscodeAttemptId, Disposition, Reason)

            LoggingService.LogInfo(
                f"Disposition for TranscodeAttempt {TranscodeAttemptId}: {Disposition} "
                f"(Reason={Reason}) inputs={json.dumps(AuditPayload, default=str)}",
                "PostTranscodeDispositionService", "DecidePostTranscodeDisposition",
            )

            return DispositionResult(
                Disposition=Disposition,
                Reason=Reason,
                AuditPayload=AuditPayload,
            )

        except Exception as Ex:
            LoggingService.LogException(
                f"DecidePostTranscodeDisposition failed for TranscodeAttempt {TranscodeAttemptId}",
                Ex, "PostTranscodeDispositionService", "DecidePostTranscodeDisposition",
            )
            return DispositionResult(Disposition='Pending', Reason='', AuditPayload={'error': str(Ex)})

    # directive: filereplacement-decompose | see transcode.ST6
    def _DecideFromInputs(self, Success, OldSize, NewSize, QualityTestRequired,
                          VmafScore, VmafCapableWorkerOnline, GateConfig) -> Tuple[str, str]:
        """Decision table from transcode.flow.md ST6 encoded; see transcode.ST6."""
        if not Success:
            return ('Discard', 'TranscodeFailed')

        if not getattr(GateConfig, 'QualityTestEnabled', True):
            return ('BypassReplace', 'QualityTestingGloballyDisabled')

        if not QualityTestRequired:
            return ('BypassReplace', 'QualityTestNotRequired')

        if NewSize and OldSize and NewSize >= OldSize:
            return ('Discard', 'NoSavings')

        if VmafScore is not None:
            try:
                Score = float(VmafScore)
            except (TypeError, ValueError):
                Score = None
            if Score is not None:
                if Score < float(GateConfig.VmafAutoReplaceMinThreshold):
                    return ('Requeue', 'VmafBelowMin')
                if Score <= float(GateConfig.VmafAutoReplaceMaxThreshold):
                    return ('Replace', 'VmafPassed')
                return ('NoReplace', 'VmafAboveMax')

        return ('Pending', 'AwaitingVmaf')

    # directive: filereplacement-decompose
    def _CommitDisposition(self, TranscodeAttemptId: int, Disposition: str, Reason: str) -> None:
        """Write audit columns and TFP cleanup chokepoint; see post-transcode-pipeline.C15."""
        if Disposition not in DISPOSITIONS:
            LoggingService.LogError(
                f"Refusing to commit invalid Disposition={Disposition!r} for attempt {TranscodeAttemptId}",
                "PostTranscodeDispositionService", "_CommitDisposition",
            )
            return
        if Reason and Reason not in REASONS:
            LoggingService.LogError(
                f"Refusing to commit invalid Reason={Reason!r} for attempt {TranscodeAttemptId}",
                "PostTranscodeDispositionService", "_CommitDisposition",
            )
            return
        try:
            # allow: R12 SQL preexisting; relocate to TranscodeAttemptsRepository in follow-up
            DatabaseService().ExecuteNonQuery(
                """
                UPDATE TranscodeAttempts
                SET Disposition = %s,
                    DispositionReason = %s,
                    DispositionDecidedAt = %s
                WHERE Id = %s
                """,
                (Disposition, Reason or None, datetime.now(timezone.utc), TranscodeAttemptId),
            )
        except Exception as Ex:
            LoggingService.LogException(
                f"_CommitDisposition failed for attempt {TranscodeAttemptId}",
                Ex, "PostTranscodeDispositionService", "_CommitDisposition",
            )
            return

        # see post-transcode-pipeline.C15
        if Disposition in ('Discard', 'NoReplace', 'Requeue'):
            self.CleanupTemporaryFilePaths(TranscodeAttemptId)

    # directive: filereplacement-decompose | see post-transcode-pipeline.C15
    def CleanupTemporaryFilePaths(self, TranscodeAttemptId: int) -> None:
        """Delete TFP row; chokepoint for every non-Pending terminal exit; see post-transcode-pipeline.C15."""
        try:
            DatabaseService().ExecuteNonQuery(
                "DELETE FROM TemporaryFilePaths WHERE TranscodeAttemptId = %s",
                (TranscodeAttemptId,),
            )
        except Exception as Ex:
            LoggingService.LogException(
                f"CleanupTemporaryFilePaths failed for attempt {TranscodeAttemptId}",
                Ex, "PostTranscodeDispositionService", "CleanupTemporaryFilePaths",
            )

    # directive: filereplacement-decompose | see compliance-gated-rename.C2
    def RecordComplianceGateFailure(self, TranscodeAttemptId: int, CascadeReason: str) -> None:
        """Override Replace/BypassReplace -> NoReplace/ComplianceGateFailed; see compliance-gated-rename.C2."""
        try:
            # allow: R12 SQL preexisting; relocate to TranscodeAttemptsRepository in follow-up
            DatabaseService().ExecuteNonQuery(
                """
                UPDATE TranscodeAttempts
                SET ErrorMessage = %s
                WHERE Id = %s
                """,
                (f'ComplianceGateFailed: {CascadeReason}', TranscodeAttemptId),
            )
        except Exception as Ex:
            LoggingService.LogException(
                f"RecordComplianceGateFailure: failed to write ErrorMessage for attempt {TranscodeAttemptId}",
                Ex, "PostTranscodeDispositionService", "RecordComplianceGateFailure",
            )
        self._CommitDisposition(TranscodeAttemptId, 'NoReplace', 'ComplianceGateFailed')
        LoggingService.LogInfo(
            f"Disposition overridden for TranscodeAttempt {TranscodeAttemptId}: "
            f"NoReplace (Reason=ComplianceGateFailed, CascadeReason={CascadeReason})",
            "PostTranscodeDispositionService", "RecordComplianceGateFailure",
        )
