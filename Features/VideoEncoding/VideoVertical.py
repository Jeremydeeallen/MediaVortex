from typing import List, Optional, Tuple

from Core.Database.DatabaseService import DatabaseService
from Core.Logging.LoggingService import LoggingService
from Features.MediaFile.Domain.MediaFileScope import IsAudioOnlyContainer
from Repositories.DatabaseManager import DatabaseManager


# directive: transcode-flow-canonical -- video baseline compliance is profile-independent per C33
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


# directive: transcode-flow-canonical -- C33 profile-independent baseline
class VideoVertical:

    # directive: transcode-flow-canonical -- C33
    def __init__(self, Db: Optional[DatabaseService] = None, RepoMgr: Optional[DatabaseManager] = None):
        self._Db = Db or DatabaseService()
        self._RepoMgr = RepoMgr or DatabaseManager()

    # directive: transcode-flow-canonical | # see video-encoding.C2
    def _LoadRules(self):
        Rows = self._Db.ExecuteQuery(
            "SELECT AcceptableVideoCodecsCsv FROM VideoComplianceRules ORDER BY Id LIMIT 1"
        )
        if not Rows:
            raise RuntimeError('VideoComplianceRules has no rows -- migration not applied')
        Csv = (Rows[0].get('AcceptableVideoCodecsCsv') or Rows[0].get('acceptablevideocodecscsv') or '').strip()
        return [C.strip().lower() for C in Csv.split(',') if C.strip()]

    # directive: transcode-flow-canonical | # see video-encoding.C3
    def _TargetKbpsFor(self, ProfileName: str, ResolutionCategory: str, ContentClass: str) -> Optional[int]:
        Rows = self._Db.ExecuteQuery(
            "SELECT pt.TargetKbps FROM Profiles p "
            "JOIN ProfileThresholds pt ON pt.ProfileId = p.Id "
            "WHERE p.ProfileName = %s AND pt.Resolution = %s AND pt.ContentClass = %s "
            "  AND pt.TargetKbps IS NOT NULL "
            "ORDER BY pt.Id LIMIT 1",
            (ProfileName, ResolutionCategory, ContentClass),
        )
        if not Rows:
            return None
        Value = Rows[0].get('targetkbps') if 'targetkbps' in Rows[0] else Rows[0].get('TargetKbps')
        return int(Value) if Value is not None else None

    # directive: transcode-flow-canonical | # see video-encoding.C3
    def Evaluate(self, Mf) -> Tuple[Optional[bool], Optional[str]]:
        if IsAudioOnlyContainer(Mf):
            return (None, 'non_video_scope')
        if bool(getattr(Mf, 'TranscodedByMediaVortex', False)):
            return (True, 'mediavortex_output_accepted')

        AllowedCodecs = self._LoadRules()

        SrcCodec = (getattr(Mf, 'Codec', None) or '').lower()
        if SrcCodec and AllowedCodecs and SrcCodec not in AllowedCodecs:
            return (False, f'codec:{SrcCodec}')

        AssignedProfile = getattr(Mf, 'AssignedProfile', None)
        ResolutionCategory = getattr(Mf, 'ResolutionCategory', None)
        SrcKbps = getattr(Mf, 'VideoBitrateKbps', None)
        if AssignedProfile and ResolutionCategory and SrcKbps and int(SrcKbps) > 0:
            ContentClass = getattr(Mf, 'ContentClass', None) or 'live_action'
            Target = self._TargetKbpsFor(AssignedProfile, ResolutionCategory, ContentClass)
            if Target is not None:
                if int(SrcKbps) <= int(Target):
                    return (True, f'source_at_or_below_target:{int(SrcKbps)}<={int(Target)}')
                return (False, f'source_above_target:{int(SrcKbps)}>{int(Target)}')

        return (True, None)

    # directive: transcode-flow-canonical -- C33
    def RecomputeFor(self, MediaFileIds: List[int]) -> None:
        for Id in MediaFileIds:
            Mf = self._RepoMgr.GetMediaFileById(Id)
            if Mf is None:
                raise ValueError(f"MediaFileId {Id} not found")
            Compliant, Reason = self.Evaluate(Mf)
            self._WriteResult(Id, Compliant, Reason)

    # directive: transcode-flow-canonical -- C33
    def _WriteResult(self, MediaFileId: int, Compliant, Reason):
        self._Db.ExecuteNonQuery(
            "UPDATE MediaFiles SET VideoCompliant = %s, VideoCompliantReason = %s WHERE Id = %s",
            (Compliant, Reason, MediaFileId),
        )
        LoggingService.LogInfo(f"VideoVertical.RecomputeFor Id={MediaFileId} -> Compliant={Compliant}, Reason={Reason!r}", "VideoVertical", "_WriteResult")
