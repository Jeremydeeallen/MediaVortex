from typing import List, Optional, Tuple

from Core.Database.DatabaseService import DatabaseService
from Core.Logging.LoggingService import LoggingService
from Core.Resolution.ResolutionTier import ResolutionTier
from Core.Resolution.ResolutionTierRegistry import ResolutionTierRegistry
from Repositories.DatabaseManager import DatabaseManager
from Features.Profiles.EffectiveProfileResolver import EffectiveProfileResolver
from Features.Profiles.EffectiveProfile import EffectiveProfile


_PIXEL_COUNTS = {
    '480p': 345600,
    '720p': 921600,
    '1080p': 2073600,
    '2160p': 8294400,
}
_ASSUMED_FPS = 24


# directive: compliance-rip
class VideoVertical:
    """Video compliance vertical -- self-contained. Pure `Evaluate(mf)` returns the verdict without writing; `RecomputeFor(ids)` evaluates + writes. Inlined predicates: codec acceptable, resolution exceeds target, savings meaningful, no upscale + MinSourceBpp override."""

    # directive: compliance-rip
    def __init__(self, Db: Optional[DatabaseService] = None, RepoMgr: Optional[DatabaseManager] = None, ProfileResolver: Optional[EffectiveProfileResolver] = None, TierRegistry: Optional[ResolutionTierRegistry] = None):
        self._Db = Db or DatabaseService()
        self._RepoMgr = RepoMgr or DatabaseManager()
        self._Resolver = ProfileResolver or EffectiveProfileResolver()
        self._TierRegistry = TierRegistry or ResolutionTierRegistry()

    # directive: compliance-rip
    def Evaluate(self, Mf) -> Tuple[Optional[bool], Optional[str]]:
        """Pure verdict: (Compliant, Reason). No DB write."""
        Rules = self._LoadRules()
        return self._EvaluateInternal(Mf, Rules)

    # directive: compliance-rip
    def RecomputeFor(self, MediaFileIds: List[int]) -> None:
        Rules = self._LoadRules()
        for Id in MediaFileIds:
            Mf = self._RepoMgr.GetMediaFileById(Id)
            if Mf is None:
                raise ValueError(f"MediaFileId {Id} not found")
            Compliant, Reason = self._EvaluateInternal(Mf, Rules)
            self._WriteResult(Id, Compliant, Reason)

    # directive: compliance-rip
    def _LoadRules(self) -> dict:
        """Fresh DB read per call."""
        Rows = self._Db.ExecuteQuery(
            "SELECT AcceptableVideoCodecsCsv, EstimatedSavingsMBThreshold, PreventUpscale, ResolutionExceedsProfileTarget, MinSourceBpp "
            "FROM VideoComplianceRules ORDER BY Id LIMIT 1"
        )
        if not Rows:
            raise RuntimeError("VideoComplianceRules has no rows -- migration not applied")
        R = Rows[0]
        return {
            'AcceptableCodecs': self._ParseCsv(R['AcceptableVideoCodecsCsv']),
            'SavingsThreshold': int(R['EstimatedSavingsMBThreshold']),
            'PreventUpscale': bool(R['PreventUpscale']),
            'ResolutionExceedsProfileTarget': bool(R['ResolutionExceedsProfileTarget']),
            'MinSourceBpp': float(R['MinSourceBpp']),
        }

    # directive: compliance-rip
    def _EvaluateInternal(self, Mf, Rules: dict) -> Tuple[Optional[bool], Optional[str]]:
        Profile = self._Resolver.Resolve(Mf)
        if Profile is None:
            return (None, 'no_effective_profile')
        if Profile.TargetResolutionCategory is None:
            return (None, 'no_profile_thresholds')

        SrcTier = self._TierRegistry.FromCategory(getattr(Mf, 'ResolutionCategory', None))
        TgtTier = Profile.TargetResolutionCategory

        if Rules['PreventUpscale'] and SrcTier is not None and SrcTier.Rank < TgtTier.Rank:
            return (True, 'upscale_prevented')

        Applies = False
        Reason = None

        if Rules['ResolutionExceedsProfileTarget'] and SrcTier is not None and SrcTier.Rank > TgtTier.Rank:
            Applies = True
            Reason = f'ResolutionExceedsProfileTarget:{SrcTier.Name}'

        SrcCodec = (getattr(Mf, 'Codec', None) or '').lower()
        if SrcCodec and SrcCodec not in Rules['AcceptableCodecs']:
            Applies = True
            if Reason is None:
                Reason = f'AcceptableVideoCodecsCsv:{SrcCodec}'

        MvTrusted = bool(getattr(Mf, 'TranscodedByMediaVortex', False))
        EstSavings = self._EstimatedSavingsMB(Mf, Profile)
        if EstSavings is not None and EstSavings >= Rules['SavingsThreshold'] and not MvTrusted:
            Applies = True
            if Reason is None:
                Reason = f'EstimatedSavingsMBThreshold:{round(EstSavings, 1)}'

        if not Applies:
            return (True, None)
        if self._IsAlreadyEfficient(Mf, Rules['MinSourceBpp']):
            return (True, 'efficient_bpp_override')
        return (False, Reason or 'unspecified')

    @staticmethod
    # directive: compliance-rip
    def _EstimatedSavingsMB(Mf, Profile: EffectiveProfile) -> Optional[float]:
        TargetVk = Profile.TargetVideoKbps
        if not TargetVk:
            return None
        Dur = getattr(Mf, 'DurationMinutes', None)
        if Dur is None or Dur <= 0:
            return None
        TargetAk = Profile.TargetAudioKbps if Profile.TargetAudioKbps else 0
        TargetSizeMB = ((TargetVk + TargetAk) * Dur * 60.0) / (8 * 1024)
        SrcSize = getattr(Mf, 'SizeMB', None) or 0.0
        return max(0.0, SrcSize - TargetSizeMB)

    # directive: compliance-rip
    def _IsAlreadyEfficient(self, Mf, MinBpp: float) -> bool:
        Bitrate = getattr(Mf, 'VideoBitrateKbps', None)
        Tier = (getattr(Mf, 'ResolutionCategory', None) or '').lower()
        if not Bitrate or Tier not in _PIXEL_COUNTS:
            return False
        Pixels = _PIXEL_COUNTS[Tier]
        Bpp = (float(Bitrate) * 1000.0) / (Pixels * _ASSUMED_FPS)
        return Bpp < MinBpp

    @staticmethod
    # directive: compliance-rip
    def _ParseCsv(Csv: Optional[str]) -> set:
        if not Csv:
            return set()
        return {Tok.strip().lower() for Tok in Csv.split(',') if Tok.strip()}

    # directive: compliance-rip
    def _WriteResult(self, MediaFileId: int, Compliant, Reason):
        self._Db.ExecuteNonQuery(
            "UPDATE MediaFiles SET VideoCompliant = %s, VideoCompliantReason = %s WHERE Id = %s",
            (Compliant, Reason, MediaFileId),
        )
