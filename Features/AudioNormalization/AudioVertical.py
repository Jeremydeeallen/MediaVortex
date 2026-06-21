from typing import List, Optional, Tuple

from Core.Database.DatabaseService import DatabaseService
from Core.Logging.LoggingService import LoggingService
from Repositories.DatabaseManager import DatabaseManager
from Features.AudioNormalization.AudioPolicyAdmissionGate import AudioPolicyAdmissionGate


# directive: compliance-rip
class AudioVertical:
    """Audio compliance vertical. Pure `Evaluate(mf)` returns the verdict without writing; `RecomputeFor(ids)` evaluates and writes."""

    # directive: compliance-rip
    def __init__(self, Gate: Optional[AudioPolicyAdmissionGate] = None, Db: Optional[DatabaseService] = None, RepoMgr: Optional[DatabaseManager] = None):
        self._Gate = Gate or AudioPolicyAdmissionGate()
        self._Db = Db or DatabaseService()
        self._RepoMgr = RepoMgr or DatabaseManager()

    # directive: compliance-rip
    def Evaluate(self, Mf) -> Tuple[Optional[bool], Optional[str]]:
        """Pure verdict: (Compliant, Reason). No DB write. Order: upstream audio gates -> admission gate -> AudioComplete."""
        if getattr(Mf, 'AudioCorruptSuspect', None) is True:
            return (None, 'audio_corrupt_suspect')
        if getattr(Mf, 'HasExplicitEnglishAudio', None) is False:
            return (None, 'no_english_audio')
        if not getattr(Mf, 'AudioCodec', None) and getattr(Mf, 'Resolution', None):
            return (None, 'no_audio_stream')
        if getattr(Mf, 'LoudnessMeasurementFailureReason', None):
            return (None, 'loudness_measurement_failed')
        Decision = self._Gate.AdmitOrDefer(Mf)
        if Decision.Outcome != 'admitted':
            return (None, Decision.DeferReason)
        AudioComplete = getattr(Mf, 'AudioComplete', None)
        if AudioComplete is True:
            return (True, None)
        return (False, 'needs_normalization')

    # directive: compliance-rip
    def RecomputeFor(self, MediaFileIds: List[int]) -> None:
        """For each MediaFileId, evaluate + write. Reads AudioNormalizationConfig fresh per file (db-is-authority). No try/except: failures propagate."""
        for Id in MediaFileIds:
            Mf = self._RepoMgr.GetMediaFileById(Id)
            if Mf is None:
                raise ValueError(f"MediaFileId {Id} not found")
            Compliant, Reason = self.Evaluate(Mf)
            self._WriteResult(Id, Compliant, Reason)

    # directive: compliance-rip
    def _WriteResult(self, MediaFileId: int, Compliant, Reason):
        self._Db.ExecuteNonQuery(
            "UPDATE MediaFiles SET AudioCompliant = %s, AudioCompliantReason = %s WHERE Id = %s",
            (Compliant, Reason, MediaFileId),
        )
        LoggingService.LogInfo(f"AudioVertical.RecomputeFor Id={MediaFileId} -> Compliant={Compliant}, Reason={Reason!r}", "AudioVertical", "_WriteResult")
