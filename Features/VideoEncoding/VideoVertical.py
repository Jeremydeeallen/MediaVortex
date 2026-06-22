from typing import List, Optional, Tuple

from Core.Database.DatabaseService import DatabaseService
from Core.Logging.LoggingService import LoggingService
from Core.Resolution.ResolutionTierRegistry import ResolutionTierRegistry
from Repositories.DatabaseManager import DatabaseManager
from Features.Profiles.EffectiveProfileResolver import EffectiveProfileResolver
from Features.Profiles.EffectiveProfile import EffectiveProfile


# directive: compliance-symmetry
_BITRATE_ROUNDING_TOLERANCE = 1.05


# directive: compliance-symmetry
class VideoVertical:

    # directive: compliance-symmetry
    def __init__(self, Db: Optional[DatabaseService] = None, RepoMgr: Optional[DatabaseManager] = None, ProfileResolver: Optional[EffectiveProfileResolver] = None, TierRegistry: Optional[ResolutionTierRegistry] = None):
        self._Db = Db or DatabaseService()
        self._RepoMgr = RepoMgr or DatabaseManager()
        self._Resolver = ProfileResolver or EffectiveProfileResolver()
        self._TierRegistry = TierRegistry or ResolutionTierRegistry()

    # directive: compliance-symmetry
    def Evaluate(self, Mf) -> Tuple[Optional[bool], Optional[str]]:
        Profile = self._Resolver.Resolve(Mf)
        if Profile is None:
            return (None, 'no_effective_profile')
        if Profile.StreamCodecName is None:
            return (None, 'no_profile_stream_codec')
        if Profile.TargetResolutionCategory is None:
            return (None, 'no_profile_resolution')

        SrcCodec = (getattr(Mf, 'Codec', None) or '').lower()
        TgtCodec = (Profile.StreamCodecName or '').lower()
        if SrcCodec and SrcCodec != TgtCodec:
            return (False, f'codec:{SrcCodec}')

        SrcTier = self._TierRegistry.FromCategory(getattr(Mf, 'ResolutionCategory', None))
        TgtTier = Profile.TargetResolutionCategory

        if SrcTier is not None:
            if SrcTier.Rank > TgtTier.Rank:
                return (False, f'resolution:{SrcTier.Name}')
            if SrcTier.Rank < TgtTier.Rank and not Profile.AllowUpscale:
                return (True, 'upscale_prevented')

        if Profile.TargetVideoKbps is not None:
            SrcKbps = getattr(Mf, 'VideoBitrateKbps', None)
            if SrcKbps is not None and SrcKbps > 0:
                Ceiling = Profile.TargetVideoKbps * _BITRATE_ROUNDING_TOLERANCE
                if float(SrcKbps) > Ceiling:
                    return (False, f'bitrate:{SrcKbps}>{Ceiling:.0f}')

        return (True, None)

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
            "UPDATE MediaFiles SET VideoCompliant = %s, VideoCompliantReason = %s WHERE Id = %s",
            (Compliant, Reason, MediaFileId),
        )
        LoggingService.LogInfo(f"VideoVertical.RecomputeFor Id={MediaFileId} -> Compliant={Compliant}, Reason={Reason!r}", "VideoVertical", "_WriteResult")
