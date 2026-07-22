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

    # directive: transcode-flow-canonical -- C33 baseline rules only, no profile lookup
    def _LoadRules(self):
        Rows = self._Db.ExecuteQuery(
            "SELECT AcceptableVideoCodecsCsv, BppTranscodeThreshold "
            "FROM VideoComplianceRules ORDER BY Id LIMIT 1"
        )
        if not Rows:
            raise RuntimeError('VideoComplianceRules has no rows -- migration not applied')
        R = Rows[0]
        Csv = (R.get('AcceptableVideoCodecsCsv') or R.get('acceptablevideocodecscsv') or '').strip()
        Allowed = [C.strip().lower() for C in Csv.split(',') if C.strip()]
        Threshold = R.get('BppTranscodeThreshold') if 'BppTranscodeThreshold' in R else R.get('bpptranscodethreshold')
        return Allowed, (float(Threshold) if Threshold is not None else 0.0)

    # directive: transcode-flow-canonical -- C34 audio-only containers precede every other rule
    def Evaluate(self, Mf) -> Tuple[Optional[bool], Optional[str]]:
        if IsAudioOnlyContainer(Mf):
            return (None, 'non_video_scope')
        if bool(getattr(Mf, 'TranscodedByMediaVortex', False)):
            return (True, 'mediavortex_output_accepted')

        AllowedCodecs, BppThreshold = self._LoadRules()

        SrcCodec = (getattr(Mf, 'Codec', None) or '').lower()
        if SrcCodec and AllowedCodecs and SrcCodec not in AllowedCodecs:
            return (False, f'codec:{SrcCodec}')

        Bpp = _ComputeBpp(Mf)
        if Bpp is not None and BppThreshold > 0 and Bpp > BppThreshold:
            return (False, f'high_bpp_excessive:{Bpp:.3f}>{BppThreshold:.3f}')

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
