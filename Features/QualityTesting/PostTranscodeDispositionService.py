from typing import Tuple

from Features.QualityTesting.Disposition.AttemptCleanupService import AttemptCleanupService
from Features.QualityTesting.Disposition.ComplianceFailureRecorder import ComplianceFailureRecorder
from Features.QualityTesting.Disposition.DispositionDispatcher import DispositionDispatcher
from Features.QualityTesting.Disposition.PostTranscodeDispositionDecider import PostTranscodeDispositionDecider
from Features.QualityTesting.Disposition.RetryBudgetService import RetryBudgetService
from Features.QualityTesting.Models.DispositionResult import DispositionResult
from Features.QualityTesting.PostTranscodeGateConfigRepository import PostTranscodeGateConfigRepository
from Core.Database.DatabaseService import DatabaseService
from Repositories.DatabaseManager import DatabaseManager


# directive: perfect-solid-transcode-pipeline | # see perfect-solid-transcode-pipeline.C11
class PostTranscodeDispositionService:
    """Thin facade preserving backward-compat for existing tests + smoke scripts; delegates to ST7 Disposition layer (Phase 3 lifts construction to WorkerCompositionRoot)."""

    # directive: perfect-solid-transcode-pipeline | # see perfect-solid-transcode-pipeline.C11
    def __init__(self, DatabaseManagerInstance: DatabaseManager = None, GateConfigRepoInstance: PostTranscodeGateConfigRepository = None):
        """Stash DB manager + gate-config repo; construct child services on demand."""
        self.DatabaseManager = DatabaseManagerInstance or DatabaseManager()
        self.GateConfigRepo = GateConfigRepoInstance or PostTranscodeGateConfigRepository()

    # directive: perfect-solid-transcode-pipeline | # see perfect-solid-transcode-pipeline.C11
    def DecidePostTranscodeDisposition(self, TranscodeAttemptId: int) -> DispositionResult:
        """Delegate to DispositionDispatcher.Dispatch (preserves legacy return shape)."""
        Db = DatabaseService()
        Cleanup = AttemptCleanupService(Db)
        Retry = RetryBudgetService(AttemptRepository=self.DatabaseManager, GateConfigRepository=self.GateConfigRepo)
        return DispositionDispatcher(
            Decider=PostTranscodeDispositionDecider(),
            GateConfigRepository=self.GateConfigRepo,
            AttemptCleanupService=Cleanup,
            DatabaseService=Db,
            RetryBudgetService=Retry,
        ).Dispatch(TranscodeAttemptId)

    # directive: perfect-solid-transcode-pipeline | # see perfect-solid-transcode-pipeline.C11
    def _DecideFromInputs(self, Success, OldSize, NewSize, QualityTestRequired, VmafScore, VmafCapableWorkerOnline, GateConfig) -> Tuple[str, str]:
        """Delegate the pure-function decision to PostTranscodeDispositionDecider; returns legacy (Disposition, Reason) tuple."""
        Attempt = {
            'Success': Success, 'OldSize': OldSize, 'NewSize': NewSize,
            'QualityTestRequired': QualityTestRequired, 'VmafScore': VmafScore,
            'VmafCapableWorkerOnline': VmafCapableWorkerOnline,
        }
        GateInput = {
            'VmafAutoReplaceMinThreshold': float(getattr(GateConfig, 'VmafAutoReplaceMinThreshold', 80.0)),
            'VmafAutoReplaceMaxThreshold': float(getattr(GateConfig, 'VmafAutoReplaceMaxThreshold', 98.0)),
            'WhenVmafUnavailable': getattr(GateConfig, 'WhenVmafUnavailable', 'block'),
            'QualityTestEnabled': bool(getattr(GateConfig, 'QualityTestEnabled', True)),
        }
        Outcome = PostTranscodeDispositionDecider().Decide(Attempt, GateInput)
        return (Outcome.Action, Outcome.Reason)

    # directive: perfect-solid-transcode-pipeline | # see perfect-solid-transcode-pipeline.C11
    def CleanupTemporaryFilePaths(self, TranscodeAttemptId: int) -> None:
        """Delegate to AttemptCleanupService.Cleanup."""
        AttemptCleanupService(DatabaseService()).Cleanup(TranscodeAttemptId)

    # directive: perfect-solid-transcode-pipeline | # see perfect-solid-transcode-pipeline.C11
    def RecordComplianceGateFailure(self, TranscodeAttemptId: int, CascadeReason: str) -> None:
        """Delegate to ComplianceFailureRecorder.Record."""
        Db = DatabaseService()
        ComplianceFailureRecorder(DatabaseService=Db, AttemptCleanupService=AttemptCleanupService(Db)).Record(TranscodeAttemptId, CascadeReason)
