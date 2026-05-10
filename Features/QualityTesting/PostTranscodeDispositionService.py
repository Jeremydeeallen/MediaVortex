"""PostTranscodeDispositionService.

The single decision function for the post-transcode pipeline. Replaces the
five split decision sites listed in `post-transcode-disposition.feature.md`:

  - ShouldQualityTestService.ProcessTranscodedFile
  - ShouldQualityTestService._ReplaceFileDirectly
  - QualityTestingBusinessService.CheckAndTriggerAutoReplace
  - FileReplacementBusinessService.ProcessFileReplacement (BypassVMAFCheck branch)
  - FileReplacementBusinessService.ProcessFileReplacementWithVMAF

`DecidePostTranscodeDisposition(TranscodeAttemptId)` is the only entry point.
Returns `(Disposition, Reason, AuditPayload)` and persists the decision to
TranscodeAttempts.Disposition / DispositionReason / DispositionDecidedAt.

The decision table is canonical in `transcode.flow.md` Stage 6. The branches
in `_DecideFromInputs` MUST mirror the rows in that table 1:1 -- if you add a
row to one, add it to the other in the same PR.
"""

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


# Allowed values -- enforced by the TranscodeAttempts.Disposition CHECK constraint.
DISPOSITIONS = ('Pending', 'Replace', 'BypassReplace', 'NoReplace', 'Requeue', 'Discard')

# Closed reason vocabulary -- per feature criterion 10.
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
)


class PostTranscodeDispositionService:
    """The single decision function for post-transcode disposition."""

    def __init__(self, DatabaseManagerInstance: DatabaseManager = None,
                 GateConfigRepoInstance: PostTranscodeGateConfigRepository = None):
        self.DatabaseManager = DatabaseManagerInstance or DatabaseManager()
        self.GateConfigRepo = GateConfigRepoInstance or PostTranscodeGateConfigRepository()

    def DecidePostTranscodeDisposition(self, TranscodeAttemptId: int) -> DispositionResult:
        """Decide the disposition for a transcode attempt.

        Idempotent: if the row already has a non-Pending Disposition, returns
        that decision unchanged with no side effects (no second log line, no
        second DB write). The first commit of a final disposition is the
        authoritative one; the worker may call this multiple times safely
        (e.g. once after transcode, once after VMAF lands).
        """
        try:
            # Pull all inputs in one query to avoid TranscodeAttemptModel coupling.
            # The model doesn't yet carry the Disposition columns; this keeps the
            # disposition service independent of model evolution.
            Db = DatabaseService()
            Rows = Db.ExecuteQuery(
                """
                SELECT Success, OldSizeBytes, NewSizeBytes, QualityTestRequired, VMAF,
                       Disposition, DispositionReason
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

            # Idempotency guard: if a final disposition is already committed,
            # return it unchanged. Pending re-decides as more inputs arrive.
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

            # Gather inputs.
            Success = bool(Row.get('Success'))
            OldSize = Row.get('OldSizeBytes') or 0
            NewSize = Row.get('NewSizeBytes') or 0
            QualityTestRequired = bool(Row.get('QualityTestRequired'))
            VmafScore = Row.get('VMAF')

            ServiceStatusRow = self.DatabaseManager.GetServiceStatus("QualityTestService")
            ServiceStatus = (ServiceStatusRow or {}).get('Status') if ServiceStatusRow else None

            GateConfig = self.GateConfigRepo.Get()

            AuditPayload = {
                'TranscodeAttemptId': TranscodeAttemptId,
                'Success': Success,
                'OldSizeBytes': OldSize,
                'NewSizeBytes': NewSize,
                'QualityTestRequired': QualityTestRequired,
                'VmafScore': VmafScore,
                'ServiceStatus': ServiceStatus,
                'VmafAutoReplaceMinThreshold': GateConfig.VmafAutoReplaceMinThreshold,
                'VmafAutoReplaceMaxThreshold': GateConfig.VmafAutoReplaceMaxThreshold,
                'WhenVmafUnavailable': GateConfig.WhenVmafUnavailable,
            }

            # Apply the decision table.
            Disposition, Reason = self._DecideFromInputs(
                Success=Success,
                OldSize=OldSize,
                NewSize=NewSize,
                QualityTestRequired=QualityTestRequired,
                VmafScore=VmafScore,
                ServiceStatus=ServiceStatus,
                GateConfig=GateConfig,
            )

            # Commit the decision (Pending too -- so subsequent re-decides see it).
            self._CommitDisposition(TranscodeAttemptId, Disposition, Reason)

            # Single rolled-up INFO line per decision (criterion 12).
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

    def _DecideFromInputs(self, Success, OldSize, NewSize, QualityTestRequired,
                          VmafScore, ServiceStatus, GateConfig) -> Tuple[str, str]:
        """The decision table from `transcode.flow.md` Stage 6, encoded.

        Order matches the table top-to-bottom -- first match wins. Adding /
        removing / changing a branch here MUST be accompanied by the matching
        flow-doc edit in the same PR (criterion 4).
        """
        # Row 1: transcode failed -> always Discard.
        if not Success:
            return ('Discard', 'TranscodeFailed')

        # Row 2: transcode succeeded but produced no savings.
        if NewSize and OldSize and NewSize >= OldSize:
            return ('Discard', 'NoSavings')

        # Row 3: quality testing not required -> bypass-replace by design.
        if not QualityTestRequired:
            return ('BypassReplace', 'QualityTestNotRequired')

        # The remaining rows depend on VMAF score and ServiceStatus.
        ServiceIsHealthy = (ServiceStatus or '').lower() == 'running'

        # Row 4: VMAF required, no score yet, service running -> wait for VMAF.
        if VmafScore is None and ServiceIsHealthy:
            return ('Pending', 'AwaitingVmaf')

        # Rows 5-7: VMAF score available -> compare to thresholds.
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

        # Rows 8-9: VMAF required, no score, service NOT healthy.
        if GateConfig.WhenVmafUnavailable == 'bypass':
            return ('BypassReplace', 'VmafServicePausedBypassed')
        # Default: 'block'.
        return ('NoReplace', 'VmafServicePaused')

    def _CommitDisposition(self, TranscodeAttemptId: int, Disposition: str, Reason: str) -> None:
        """Write the audit columns. Single UPDATE per disposition decision."""
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
