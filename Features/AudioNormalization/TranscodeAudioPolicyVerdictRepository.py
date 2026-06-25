from typing import List, Optional

from Core.Database.DatabaseService import DatabaseService


# directive: audio-pipeline-fail-loud
class TranscodeAudioPolicyVerdictRepository:

    # directive: audio-pipeline-fail-loud
    def __init__(self, Db: Optional[DatabaseService] = None):
        self._Db = Db or DatabaseService()

    # directive: audio-pipeline-fail-loud
    def PersistVerdicts(self, TranscodeAttemptId: int, Verdicts: List[dict]) -> int:
        Count = 0
        for V in (Verdicts or []):
            self._Db.ExecuteNonQuery(
                "INSERT INTO TranscodeAudioPolicyVerdicts "
                "(TranscodeAttemptId, TrackIndex, PolicyName, PolicyReason, PlanText) "
                "VALUES (%s, %s, %s, %s, %s)",
                (
                    int(TranscodeAttemptId),
                    int(V.get('TrackIndex', 0)),
                    str(V.get('PolicyName') or ''),
                    str(V.get('PolicyReason') or ''),
                    V.get('PlanText'),
                ),
            )
            Count += 1
        return Count

    # directive: audio-pipeline-fail-loud
    def MarkAttemptResolved(self, TranscodeAttemptId: int, Outcome: str):
        self._Db.ExecuteNonQuery(
            "UPDATE TranscodeAttempts SET AudioPolicyResolved = %s WHERE Id = %s",
            (str(Outcome), int(TranscodeAttemptId)),
        )

    # directive: audio-pipeline-fail-loud
    def GetVerdictsForAttempt(self, TranscodeAttemptId: int) -> List[dict]:
        Rows = self._Db.ExecuteQuery(
            "SELECT TrackIndex, PolicyName, PolicyReason, PlanText, CreatedAt "
            "FROM TranscodeAudioPolicyVerdicts WHERE TranscodeAttemptId = %s "
            "ORDER BY Id ASC",
            (int(TranscodeAttemptId),),
        )
        return [dict(R) for R in (Rows or [])]
