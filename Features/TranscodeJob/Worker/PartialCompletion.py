# directive: partial-pipeline-completion | # see transcode.D13
from typing import Literal
from Core.Logging.LoggingService import LoggingService


AUDIO_STDERR_MARKERS = ('libopus', 'demucs', 'loudnorm', 'audio')


# directive: partial-pipeline-completion | # see transcode.D13
def SniffFirstFallback(Stderr: str) -> Literal['AudioSlot', 'VideoSlot']:
    Text = (Stderr or '').lower()
    return 'AudioSlot' if any(Marker in Text for Marker in AUDIO_STDERR_MARKERS) else 'VideoSlot'


# directive: partial-pipeline-completion | # see transcode.D13
def OppositeSlot(Side: str) -> Literal['AudioSlot', 'VideoSlot']:
    if Side == 'AudioSlot':
        return 'VideoSlot'
    if Side == 'VideoSlot':
        return 'AudioSlot'
    raise ValueError(f"OppositeSlot: Side must be 'AudioSlot' or 'VideoSlot', got {Side!r}")


# directive: partial-pipeline-completion | # see transcode.D13
def DispositionReasonForCopiedSlot(CopiedSlot: str) -> str:
    if CopiedSlot == 'AudioSlot':
        return 'PartialSuccess_AudioSlotCopied'
    if CopiedSlot == 'VideoSlot':
        return 'PartialSuccess_VideoSlotCopied'
    raise ValueError(f"DispositionReasonForCopiedSlot: CopiedSlot must be 'AudioSlot' or 'VideoSlot', got {CopiedSlot!r}")


# directive: partial-pipeline-completion | # see transcode.D13
def FollowupPlanForCopiedSlot(CopiedSlot: str) -> dict:
    if CopiedSlot == 'AudioSlot':
        return {'ProcessingMode': 'AudioFix', 'AudioSlotOverride': None}
    if CopiedSlot == 'VideoSlot':
        return {'ProcessingMode': 'Transcode', 'AudioSlotOverride': 'Copy'}
    raise ValueError(f"FollowupPlanForCopiedSlot: CopiedSlot must be 'AudioSlot' or 'VideoSlot', got {CopiedSlot!r}")


# directive: partial-pipeline-completion | # see transcode.D13
def LogSniff(MediaFileId: int, Stderr: str, FirstFallback: str) -> None:
    Text = (Stderr or '').lower()
    Matched = [M for M in AUDIO_STDERR_MARKERS if M in Text]
    Head = (Stderr or '')[:200].replace('\n', ' ')
    LoggingService.LogInfo(
        f"PartialCompletionSniff MediaFileId={MediaFileId} markers_matched={Matched} first_fallback={FirstFallback} stderr_head={Head!r}",
        "PartialCompletion", "LogSniff",
    )


# directive: partial-pipeline-completion | # see transcode.D13
def LogFallbackAttempt(MediaFileId: int, AttemptNumber: int, CopiedSlot: str) -> None:
    LoggingService.LogInfo(
        f"PartialCompletionFallback MediaFileId={MediaFileId} attempt={AttemptNumber} copied_slot={CopiedSlot}",
        "PartialCompletion", "LogFallbackAttempt",
    )


# directive: partial-pipeline-completion | # see transcode.D13
def LogFallbackSuccess(MediaFileId: int, AttemptNumber: int, CopiedSlot: str) -> None:
    Reason = DispositionReasonForCopiedSlot(CopiedSlot)
    LoggingService.LogWarning(
        f"PartialCompletionSuccess MediaFileId={MediaFileId} attempt={AttemptNumber} copied_slot={CopiedSlot} disposition_reason={Reason}",
        "PartialCompletion", "LogFallbackSuccess",
    )


# directive: partial-pipeline-completion | # see transcode.D13
def LogBothFallbacksFailed(MediaFileId: int, OriginalStderr: str, Fallback1Stderr: str, Fallback2Stderr: str) -> None:
    LoggingService.LogError(
        f"PartialCompletionExhausted MediaFileId={MediaFileId} "
        f"original_stderr={(OriginalStderr or '')[:1000]!r} "
        f"fallback1_stderr={(Fallback1Stderr or '')[:1000]!r} "
        f"fallback2_stderr={(Fallback2Stderr or '')[:1000]!r}",
        "PartialCompletion", "LogBothFallbacksFailed",
    )


# directive: partial-pipeline-completion | # see transcode.D13
def LogPartialRetryExhausted(MediaFileId: int, ParentAttemptId: int, ChildStderr: str) -> None:
    LoggingService.LogError(
        f"PartialRetryExhausted MediaFileId={MediaFileId} ParentAttemptId={ParentAttemptId} "
        f"child_stderr={(ChildStderr or '')[:1000]!r}",
        "PartialCompletion", "LogPartialRetryExhausted",
    )
