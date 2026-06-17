from Core.Logging.LoggingService import LoggingService
from Features.AudioNormalization.SelfHealing.IAudioVerticalRemediation import IAudioVerticalRemediation
from Features.AudioNormalization.Workers.PostEncodeAudioHandler import PostEncodeAudioHandler


# directive: audio-vertical-perfection-and-self-healing | # see audio-normalization.H1
class EnqueueReProbe(IAudioVerticalRemediation):
    """Invokes PostEncodeAudioHandler.HandlePostEncode for each offending (attempt_id, media_file_id) pair."""

    Name = "EnqueueReProbe"

    # directive: audio-vertical-perfection-and-self-healing | # see audio-normalization.H1
    def __init__(self, Handler=None):
        """Inject handler for tests; default-construct using WorkerContext-resolved paths."""
        self._Handler = Handler

    # directive: audio-vertical-perfection-and-self-healing | # see audio-normalization.H1
    def Apply(self, RowIds):
        """Run probe against each (attempt_id, media_file_id) pair; count successes."""
        if not RowIds:
            return 0
        Handler = self._Handler or PostEncodeAudioHandler()
        Ok = 0
        for Item in RowIds:
            try:
                AttemptId, MediaFileId = Item
                if Handler.HandlePostEncode(AttemptId, MediaFileId):
                    Ok += 1
            except Exception as Ex:
                LoggingService.LogException(
                    f"EnqueueReProbe.Apply failed for {Item}",
                    Ex, self.Name, "Apply",
                )
        return Ok
