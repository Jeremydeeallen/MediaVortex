from typing import List, Optional, Tuple

from Core.Database.DatabaseService import DatabaseService
from Core.Logging.LoggingService import LoggingService
from Features.MediaFile.Domain.MediaFileScope import IsAudioOnlyContainer
from Features.Profiles.TierLadderRepository import TierLadderRepository
from Features.VideoEncoding.VideoComplianceThresholdsRepository import VideoComplianceThresholdsRepository
from Repositories.DatabaseManager import DatabaseManager


# directive: video-compliance-multiplier | # see video-encoding.C1
class VideoVertical:

    # directive: video-compliance-multiplier
    def __init__(self, Db: Optional[DatabaseService] = None, RepoMgr: Optional[DatabaseManager] = None,
                 Thresholds: Optional[VideoComplianceThresholdsRepository] = None,
                 Tiers: Optional[TierLadderRepository] = None):
        self._Db = Db or DatabaseService()
        self._RepoMgr = RepoMgr or DatabaseManager()
        self._Thresholds = Thresholds or VideoComplianceThresholdsRepository(self._Db)
        self._Tiers = Tiers or TierLadderRepository(self._Db)

    # directive: mediavortex-output-terminal | # see transcode.flow.md D7 -- TranscodedByMediaVortex short-circuit lives at WorkBucket generated-column layer; VideoVertical only evaluates its own dimension
    def Evaluate(self, Mf) -> Tuple[Optional[bool], Optional[str]]:
        if IsAudioOnlyContainer(Mf):
            return (None, 'non_video_scope')

        ResolutionCategory = getattr(Mf, 'ResolutionCategory', None)
        SrcKbps = getattr(Mf, 'VideoBitrateKbps', None)
        AssignedProfile = getattr(Mf, 'AssignedProfile', None)

        if not ResolutionCategory:
            return (None, 'missing_input:ResolutionCategory')
        if not SrcKbps or int(SrcKbps) <= 0:
            return (None, 'missing_input:VideoBitrateKbps')
        if not AssignedProfile:
            return (None, 'missing_input:AssignedProfile')

        Family = self._ResolveFamily(AssignedProfile)
        if not Family:
            return (None, f'missing_input:Family(profile={AssignedProfile})')

        ContentClass = getattr(Mf, 'ContentClass', None) or 'live_action'
        Tier1TargetKbps = self._Tiers.GetTier1Target(Family, ContentClass, ResolutionCategory)
        if Tier1TargetKbps is None:
            return (None, f'missing_input:Tier1TargetKbps(family={Family},class={ContentClass},res={ResolutionCategory})')

        Multiplier = self._Thresholds.GetMultiplier(ResolutionCategory)
        Threshold = int(round(Tier1TargetKbps * Multiplier))

        Src = int(SrcKbps)
        if Src <= Threshold:
            return (True, f'source_at_or_below_multiplier:{Src}<={Threshold}(tier1={Tier1TargetKbps}*{Multiplier})')
        return (False, f'source_above_multiplier:{Src}>{Threshold}(tier1={Tier1TargetKbps}*{Multiplier})')

    # directive: video-compliance-multiplier
    def _ResolveFamily(self, AssignedProfile: str) -> Optional[str]:
        Rows = self._Db.ExecuteQuery(
            "SELECT Family FROM Profiles WHERE ProfileName = %s",
            (AssignedProfile,),
        )
        if not Rows:
            return None
        Family = Rows[0].get('family')
        return Family if Family else None

    # directive: compliance-reason-full-library-recompute | # see video-encoding.C5 -- Evaluate stays fail-loud (raises); batch orchestrator isolates per-row so one bad row does not abort a 237-row batch (BUG discovered via RetierTvToTier1 2026-08-07).
    def RecomputeFor(self, MediaFileIds: List[int]) -> None:
        for Id in MediaFileIds:
            try:
                Mf = self._RepoMgr.GetMediaFileById(Id)
                if Mf is None:
                    LoggingService.LogWarning(f"VideoVertical.RecomputeFor: MediaFileId {Id} not found; skipping", "VideoVertical", "RecomputeFor")
                    continue
                Compliant, Reason = self.Evaluate(Mf)
                self._WriteResult(Id, Compliant, Reason)
            # fail-loud-ok: batch-orchestrator per-row isolation; Evaluate stays fail-loud per video-encoding.C5; each row surfaces via LogException
            except Exception as Ex:
                LoggingService.LogException(f"VideoVertical.RecomputeFor: MediaFileId {Id} raised; skipping", Ex, "VideoVertical", "RecomputeFor")
                continue

    # directive: video-compliance-multiplier
    def _WriteResult(self, MediaFileId: int, Compliant, Reason):
        self._Db.ExecuteNonQuery(
            "UPDATE MediaFiles SET VideoCompliant = %s, VideoCompliantReason = %s WHERE Id = %s",
            (Compliant, Reason, MediaFileId),
        )
        LoggingService.LogInfo(f"VideoVertical.RecomputeFor Id={MediaFileId} -> Compliant={Compliant}, Reason={Reason!r}", "VideoVertical", "_WriteResult")
