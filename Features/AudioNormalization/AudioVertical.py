from typing import List, Optional

from Core.Database.DatabaseService import DatabaseService
from Core.Logging.LoggingService import LoggingService
from Repositories.DatabaseManager import DatabaseManager
from Features.AudioNormalization.AudioPolicyAdmissionGate import AudioPolicyAdmissionGate


# directive: compliance-schema-and-audio
class AudioVertical:
    """Audio vertical's compliance computation entry point. Writes (AudioCompliant, AudioCompliantReason) per MediaFileId by wrapping AudioPolicyAdmissionGate + AudioComplete check."""

    # directive: compliance-schema-and-audio
    def __init__(self, Gate: Optional[AudioPolicyAdmissionGate] = None, Db: Optional[DatabaseService] = None, RepoMgr: Optional[DatabaseManager] = None):
        self._Gate = Gate or AudioPolicyAdmissionGate()
        self._Db = Db or DatabaseService()
        self._RepoMgr = RepoMgr or DatabaseManager()

    # directive: compliance-schema-and-audio
    def RecomputeFor(self, MediaFileIds: List[int]) -> None:
        """For each MediaFileId, evaluate audio compliance + write (AudioCompliant, AudioCompliantReason). Reads AudioNormalizationConfig fresh per file (db-is-authority). No try/except: failures propagate."""
        for Id in MediaFileIds:
            Compliant, Reason = self._EvaluateOne(Id)
            self._WriteResult(Id, Compliant, Reason)

    # directive: audio-vertical-gate-propagation
    def _EvaluateOne(self, MediaFileId: int):
        """Return (Compliant, Reason). Order: upstream audio gates -> admission gate -> AudioComplete. Gate-blocked -> (NULL, reason); admitted+complete -> (TRUE, NULL); admitted+incomplete -> (FALSE, 'needs_normalization'); deferred -> (NULL, DeferReason)."""
        Mf = self._RepoMgr.GetMediaFileById(MediaFileId)
        if Mf is None:
            raise ValueError(f"MediaFileId {MediaFileId} not found")
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

    # directive: compliance-schema-and-audio
    def _WriteResult(self, MediaFileId: int, Compliant, Reason):
        """Single UPDATE writing both columns atomically. NULL Reason cleared explicitly."""
        self._Db.ExecuteNonQuery(
            "UPDATE MediaFiles SET AudioCompliant = %s, AudioCompliantReason = %s WHERE Id = %s",
            (Compliant, Reason, MediaFileId),
        )
        LoggingService.LogInfo(f"AudioVertical.RecomputeFor Id={MediaFileId} -> Compliant={Compliant}, Reason={Reason!r}", "AudioVertical", "_WriteResult")
