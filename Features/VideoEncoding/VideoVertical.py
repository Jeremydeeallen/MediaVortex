from typing import List, Optional, Tuple

from Core.Database.DatabaseService import DatabaseService
from Core.Logging.LoggingService import LoggingService
from Core.Resolution.ResolutionTierRegistry import ResolutionTierRegistry
from Repositories.DatabaseManager import DatabaseManager
from Features.Profiles.EffectiveProfileResolver import EffectiveProfileResolver
from Features.Profiles.EffectiveProfile import EffectiveProfile


# directive: compliance-symmetry
_BITRATE_ROUNDING_TOLERANCE = 1.05

# directive: worker-runtime-state
_PIXEL_COUNTS = {'480p': 345600, '720p': 921600, '1080p': 2073600, '2160p': 8294400}


# directive: compliance-symmetry
class VideoVertical:

    # directive: compliance-symmetry
    def __init__(self, Db: Optional[DatabaseService] = None, RepoMgr: Optional[DatabaseManager] = None, ProfileResolver: Optional[EffectiveProfileResolver] = None, TierRegistry: Optional[ResolutionTierRegistry] = None):
        self._Db = Db or DatabaseService()
        self._RepoMgr = RepoMgr or DatabaseManager()
        self._Resolver = ProfileResolver or EffectiveProfileResolver()
        self._TierRegistry = TierRegistry or ResolutionTierRegistry()

    # directive: worker-runtime-state
    def _LoadRules(self):
        Rows = self._Db.ExecuteQuery(
            "SELECT AcceptableVideoCodecsCsv, MinSourceBpp, MaxSourceBpp, ResolutionExceedsProfileTarget "
            "FROM VideoComplianceRules ORDER BY Id LIMIT 1"
        )
        if not Rows:
            raise RuntimeError('VideoComplianceRules has no rows -- migration not applied')
        R = Rows[0]
        Csv = (R.get('AcceptableVideoCodecsCsv') or R.get('acceptablevideocodecscsv') or '').strip()
        Allowed = [C.strip().lower() for C in Csv.split(',') if C.strip()]
        MinBpp = R.get('MinSourceBpp') if 'MinSourceBpp' in R else R.get('minsourcebpp')
        MaxBpp = R.get('MaxSourceBpp') if 'MaxSourceBpp' in R else R.get('maxsourcebpp')
        ResExceeds = R.get('ResolutionExceedsProfileTarget') if 'ResolutionExceedsProfileTarget' in R else R.get('resolutionexceedsprofiletarget')
        return Allowed, (float(MinBpp) if MinBpp is not None else 0.0), (float(MaxBpp) if MaxBpp is not None else 0.0), bool(ResExceeds)

    # directive: worker-runtime-state
    def Evaluate(self, Mf) -> Tuple[Optional[bool], Optional[str]]:
        AllowedCodecs, MinBpp, MaxBpp, ResExceeds = self._LoadRules()

        Profile = self._Resolver.Resolve(Mf)
        if Profile is None:
            return (None, 'no_effective_profile')

        SrcCodec = (getattr(Mf, 'Codec', None) or '').lower()
        if SrcCodec and AllowedCodecs and SrcCodec not in AllowedCodecs:
            return (False, f'codec:{SrcCodec}')

        SrcKbps = getattr(Mf, 'VideoBitrateKbps', None)
        ResCat = getattr(Mf, 'ResolutionCategory', None)
        Pixels = _PIXEL_COUNTS.get((ResCat or '').lower())
        Bpp = (float(SrcKbps) * 1000.0) / (Pixels * 24.0) if (SrcKbps and Pixels) else None

        if Bpp is not None and MinBpp > 0 and Bpp < MinBpp:
            return (True, 'efficient_bpp_override')

        if Bpp is not None and MaxBpp > 0 and Bpp > MaxBpp:
            return (False, f'high_bpp_excessive:{Bpp:.3f}>{MaxBpp:.3f}')

        if ResExceeds and Profile.TargetResolutionCategory is not None:
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
