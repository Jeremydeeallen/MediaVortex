from typing import List, Optional, Tuple

from Core.Database.DatabaseService import DatabaseService
from Core.Logging.LoggingService import LoggingService
from Repositories.DatabaseManager import DatabaseManager
from Features.AudioNormalization.AudioPolicyAdmissionGate import AudioPolicyAdmissionGate
from Features.Profiles.EffectiveProfileResolver import EffectiveProfileResolver


# directive: compliance-symmetry
_BITRATE_ROUNDING_TOLERANCE = 1.05


# directive: compliance-symmetry
class AudioVertical:

    # directive: compliance-symmetry
    def __init__(self, Gate: Optional[AudioPolicyAdmissionGate] = None, Db: Optional[DatabaseService] = None, RepoMgr: Optional[DatabaseManager] = None, ProfileResolver: Optional[EffectiveProfileResolver] = None):
        self._Gate = Gate or AudioPolicyAdmissionGate()
        self._Db = Db or DatabaseService()
        self._RepoMgr = RepoMgr or DatabaseManager()
        self._Resolver = ProfileResolver or EffectiveProfileResolver()

    # directive: worker-runtime-state
    def _LoadAcceptableAudioCodecs(self) -> list:
        Rows = self._Db.ExecuteQuery(
            "SELECT AcceptableAudioCodecsCsv FROM ContainerComplianceRules ORDER BY Id LIMIT 1"
        )
        if not Rows:
            return []
        Csv = (Rows[0].get('AcceptableAudioCodecsCsv') or Rows[0].get('acceptableaudiocodecscsv') or '').strip()
        return [C.strip().lower() for C in Csv.split(',') if C.strip()]

    # directive: worker-runtime-state
    def Evaluate(self, Mf) -> Tuple[Optional[bool], Optional[str]]:
        if getattr(Mf, 'AudioCorruptSuspect', None) is True:
            return (None, 'audio_corrupt_suspect')
        if getattr(Mf, 'HasExplicitEnglishAudio', None) is False:
            return (None, 'no_english_audio')
        if not getattr(Mf, 'AudioCodec', None) and getattr(Mf, 'Resolution', None):
            return (None, 'no_audio_stream')
        if getattr(Mf, 'LoudnessMeasurementFailureReason', None):
            return (None, 'loudness_measurement_failed')

        Profile = self._Resolver.Resolve(Mf)
        if Profile is None:
            return (None, 'no_effective_profile')

        SrcCodec = (getattr(Mf, 'AudioCodec', None) or '').lower()
        AllowedCodecs = self._LoadAcceptableAudioCodecs()
        if SrcCodec and AllowedCodecs and SrcCodec not in AllowedCodecs:
            return (False, f'codec:{SrcCodec}')

        if Profile.TargetAudioKbps is not None:
            SrcKbps = getattr(Mf, 'AudioBitrateKbps', None)
            if SrcKbps is not None and SrcKbps > 0:
                Ceiling = Profile.TargetAudioKbps * _BITRATE_ROUNDING_TOLERANCE
                if float(SrcKbps) > Ceiling:
                    return (False, f'bitrate:{SrcKbps}>{Ceiling:.0f}')

        Decision = self._Gate.AdmitOrDefer(Mf)
        if Decision.Outcome != 'admitted':
            return (None, Decision.DeferReason)

        AudioComplete = getattr(Mf, 'AudioComplete', None)
        if AudioComplete is True:
            return (True, None)
        return (False, 'needs_normalization')

    # directive: compliance-symmetry
    def RecomputeFor(self, MediaFileIds: List[int]) -> None:
        for Id in MediaFileIds:
            Mf = self._RepoMgr.GetMediaFileById(Id)
            if Mf is None:
                raise ValueError(f"MediaFileId {Id} not found")
            Compliant, Reason = self.Evaluate(Mf)
            self._WriteResult(Id, Compliant, Reason)

    # directive: compliance-symmetry
    def _WriteResult(self, MediaFileId: int, Compliant, Reason):
        self._Db.ExecuteNonQuery(
            "UPDATE MediaFiles SET AudioCompliant = %s, AudioCompliantReason = %s WHERE Id = %s",
            (Compliant, Reason, MediaFileId),
        )
        LoggingService.LogInfo(f"AudioVertical.RecomputeFor Id={MediaFileId} -> Compliant={Compliant}, Reason={Reason!r}", "AudioVertical", "_WriteResult")
