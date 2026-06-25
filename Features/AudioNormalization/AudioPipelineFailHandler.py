from typing import Optional

from Core.Database.DatabaseService import DatabaseService
from Features.AudioNormalization.AudioStrategyResult import AudioPolicyUnresolvedError
from Features.AudioNormalization.TranscodeAudioPolicyVerdictRepository import (
    TranscodeAudioPolicyVerdictRepository,
)


# directive: audio-pipeline-fail-loud
class AudioPipelineFailHandler:

    # directive: audio-pipeline-fail-loud
    def __init__(
        self,
        WorkerName: str,
        Db: Optional[DatabaseService] = None,
        VerdictRepository: Optional[TranscodeAudioPolicyVerdictRepository] = None,
        StateReporter=None,
    ):
        self.WorkerName = WorkerName
        self._Db = Db or DatabaseService()
        self.VerdictRepository = VerdictRepository or TranscodeAudioPolicyVerdictRepository(self._Db)
        self._StateReporter = StateReporter

    # directive: audio-pipeline-fail-loud
    def _GetStateReporter(self):
        if self._StateReporter is not None:
            return self._StateReporter
        from WorkerService.WorkerStateReporter import WorkerStateReporter
        return WorkerStateReporter(self._Db, self.WorkerName)

    # directive: audio-pipeline-fail-loud
    def HandleUnresolved(self, TranscodeAttemptId: int, Error: AudioPolicyUnresolvedError) -> dict:
        Reason = f"audio-policy-unresolved:{Error.PolicyName}:{Error.TrackIndex}"
        ErrorMessage = f"AudioPolicyUnresolvedError {Error.PolicyName}: {Error.Reason} (track={Error.TrackIndex})"

        self._Db.ExecuteNonQuery(
            "UPDATE TranscodeAttempts SET Success = FALSE, ErrorMessage = %s, AudioPolicyResolved = %s "
            "WHERE Id = %s",
            (ErrorMessage, 'unresolved', int(TranscodeAttemptId)),
        )

        Reporter = self._GetStateReporter()
        Reporter.Transition(f'Faulted:{Error.PolicyName[:30]}')

        return {
            'Reason': Reason,
            'ErrorMessage': ErrorMessage,
            'TranscodeAttemptId': int(TranscodeAttemptId),
            'PolicyName': Error.PolicyName,
            'TrackIndex': Error.TrackIndex,
        }
