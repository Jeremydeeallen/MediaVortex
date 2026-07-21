from typing import List, Optional, Tuple

from Core.Database.DatabaseService import DatabaseService
from Core.Logging.LoggingService import LoggingService
from Core.Resolution.ResolutionTierRegistry import ResolutionTierRegistry
from Repositories.DatabaseManager import DatabaseManager
from Features.Profiles.EffectiveProfileResolver import EffectiveProfileResolver
from Features.Profiles.EffectiveProfile import EffectiveProfile


# directive: compliance-symmetry
_BITRATE_ROUNDING_TOLERANCE = 1.05


# directive: transcode-worker-unification
def _ComputeBpp(Mf) -> Optional[float]:
    Kbps = getattr(Mf, 'VideoBitrateKbps', None)
    Fps = getattr(Mf, 'FrameRate', None)
    Resolution = getattr(Mf, 'Resolution', None) or ''
    if not Kbps or not Fps or 'x' not in Resolution:
        return None
    try:
        W, H = Resolution.split('x', 1)
        Pixels = int(W) * int(H)
        FpsF = float(Fps)
    except (ValueError, TypeError):
        return None
    if Pixels <= 0 or FpsF < 1.0 or FpsF > 120.0:
        return None
    return (float(Kbps) * 1000.0) / (Pixels * FpsF)


# directive: compliance-symmetry
class VideoVertical:

    # directive: compliance-symmetry
    def __init__(self, Db: Optional[DatabaseService] = None, RepoMgr: Optional[DatabaseManager] = None, ProfileResolver: Optional[EffectiveProfileResolver] = None, TierRegistry: Optional[ResolutionTierRegistry] = None):
        self._Db = Db or DatabaseService()
        self._RepoMgr = RepoMgr or DatabaseManager()
        self._Resolver = ProfileResolver or EffectiveProfileResolver()
        self._TierRegistry = TierRegistry or ResolutionTierRegistry()

    # directive: transcode-worker-unification
    def _LoadRules(self):
        Rows = self._Db.ExecuteQuery(
            "SELECT AcceptableVideoCodecsCsv, BppTranscodeThreshold, ResolutionExceedsProfileTarget "
            "FROM VideoComplianceRules ORDER BY Id LIMIT 1"
        )
        if not Rows:
            raise RuntimeError('VideoComplianceRules has no rows -- migration not applied')
        R = Rows[0]
        Csv = (R.get('AcceptableVideoCodecsCsv') or R.get('acceptablevideocodecscsv') or '').strip()
        Allowed = [C.strip().lower() for C in Csv.split(',') if C.strip()]
        Threshold = R.get('BppTranscodeThreshold') if 'BppTranscodeThreshold' in R else R.get('bpptranscodethreshold')
        ResExceeds = R.get('ResolutionExceedsProfileTarget') if 'ResolutionExceedsProfileTarget' in R else R.get('resolutionexceedsprofiletarget')
        return Allowed, (float(Threshold) if Threshold is not None else 0.0), bool(ResExceeds)

    # directive: e2e-bug-fixes | # see e2e-bug-fixes.C31 -- MV outputs are compliance-exempt on the video side; original source is gone (deleted at first successful replacement), re-transcoding compressed AV1 produces generation-loss. Audio/Container verticals still run so audio-only or container-only issues route through AudioFix/Remux.
    def Evaluate(self, Mf) -> Tuple[Optional[bool], Optional[str]]:
        if bool(getattr(Mf, 'TranscodedByMediaVortex', False)):
            return (True, 'mediavortex_output_accepted')

        AllowedCodecs, BppThreshold, ResExceeds = self._LoadRules()

        Profile = self._Resolver.Resolve(Mf)
        if Profile is None:
            return (None, 'no_effective_profile')

        SrcCodec = (getattr(Mf, 'Codec', None) or '').lower()
        if SrcCodec and AllowedCodecs and SrcCodec not in AllowedCodecs:
            return (False, f'codec:{SrcCodec}')

        Bpp = _ComputeBpp(Mf)
        if Bpp is not None and BppThreshold > 0 and Bpp > BppThreshold:
            return (False, f'high_bpp_excessive:{Bpp:.3f}>{BppThreshold:.3f}')

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
