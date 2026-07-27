from typing import Optional


# directive: verify-signal-cleanup | # see DOMAIN.md 2026-07-26 Vmaf-truthful rule
class RetryBudgetService:

    # directive: verify-signal-cleanup
    def __init__(self, AttemptRepository, GateConfigRepository):
        self.AttemptRepository = AttemptRepository
        self.GateConfigRepository = GateConfigRepository

    # directive: verify-signal-cleanup
    def HasBudgetRemaining(self, MediaFileId: int) -> bool:
        GateConfig = self.GateConfigRepository.Get()
        MaxAttempts = int(GateConfig.MaxRequeueAttempts)
        RequeuedCount = self._CountRequeueDispositions(MediaFileId)
        return RequeuedCount < MaxAttempts

    # directive: verify-signal-cleanup
    def _CountRequeueDispositions(self, MediaFileId: int) -> int:
        Attempts = self.AttemptRepository.GetTranscodeAttemptsByMediaFileId(MediaFileId) or []
        Count = 0
        for A in Attempts:
            Disposition = getattr(A, 'Disposition', None)
            if Disposition == 'Requeue':
                Count += 1
        return Count
