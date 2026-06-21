from typing import List, Optional

from Core.Database.DatabaseService import DatabaseService
from Core.Logging.LoggingService import LoggingService
from Repositories.DatabaseManager import DatabaseManager
from Features.Compliance.Operations.TranscodeOperation import TranscodeOperation
from Features.Profiles.EffectiveProfileResolver import EffectiveProfileResolver
from Features.Compliance.Models.TranscodeRulesModel import TranscodeRulesModel


_PIXEL_COUNTS = {
    '480p': 345600,
    '720p': 921600,
    '1080p': 2073600,
    '2160p': 8294400,
}
_ASSUMED_FPS = 24


# directive: video-vertical-and-bpp
class VideoVertical:
    """Video compliance vertical: writes (VideoCompliant, VideoCompliantReason). Temporarily wraps Features/Compliance/Operations/TranscodeOperation for equivalence; wrap dies at directive 7."""

    # directive: video-vertical-and-bpp
    def __init__(self, Db: Optional[DatabaseService] = None, RepoMgr: Optional[DatabaseManager] = None, ProfileResolver: Optional[EffectiveProfileResolver] = None, Op: Optional[TranscodeOperation] = None):
        self._Db = Db or DatabaseService()
        self._RepoMgr = RepoMgr or DatabaseManager()
        self._Resolver = ProfileResolver or EffectiveProfileResolver()
        self._Op = Op or TranscodeOperation()

    # directive: video-vertical-and-bpp
    def RecomputeFor(self, MediaFileIds: List[int]) -> None:
        """Per-id: wrap TranscodeOperation; apply MinSourceBpp override; write columns."""
        Rules = self._LoadRules()
        for Id in MediaFileIds:
            Compliant, Reason = self._EvaluateOne(Id, Rules)
            self._WriteResult(Id, Compliant, Reason)

    # directive: video-vertical-and-bpp
    def _LoadRules(self) -> dict:
        """Fresh DB read per call. Returns dict with TranscodeRulesModel-shaped fields + MinSourceBpp."""
        Rows = self._Db.ExecuteQuery(
            "SELECT AcceptableVideoCodecsCsv, EstimatedSavingsMBThreshold, PreventUpscale, ResolutionExceedsProfileTarget, MinSourceBpp "
            "FROM VideoComplianceRules ORDER BY Id LIMIT 1"
        )
        if not Rows:
            raise RuntimeError("VideoComplianceRules has no rows -- migration not applied")
        R = Rows[0]
        Wrapped = TranscodeRulesModel(
            Id=1,
            AcceptableVideoCodecsCsv=R['AcceptableVideoCodecsCsv'],
            EstimatedSavingsMBThreshold=R['EstimatedSavingsMBThreshold'],
            PreventUpscale=R['PreventUpscale'],
            ResolutionExceedsProfileTarget=R['ResolutionExceedsProfileTarget'],
        )
        return {'Wrapped': Wrapped, 'MinSourceBpp': float(R['MinSourceBpp'])}

    # directive: video-vertical-and-bpp
    def _EvaluateOne(self, MediaFileId: int, Rules: dict):
        Mf = self._RepoMgr.GetMediaFileById(MediaFileId)
        if Mf is None:
            raise ValueError(f"MediaFileId {MediaFileId} not found")
        Profile = self._Resolver.Resolve(Mf)
        if Profile is None:
            return (None, 'no_effective_profile')
        if Profile.TargetResolutionCategory is None:
            return (None, 'no_profile_thresholds')
        Result = self._Op.Apply(Mf, Profile, Rules['Wrapped'])
        if not Result.Applies:
            return (True, None)
        if self._IsAlreadyEfficient(Mf, Rules['MinSourceBpp']):
            return (True, 'efficient_bpp_override')
        Reason = self._FirstApplyReason(Result.Reasons)
        return (False, Reason)

    # directive: video-vertical-and-bpp
    def _IsAlreadyEfficient(self, Mf, MinBpp: float) -> bool:
        """Compute BPP from VideoBitrateKbps + ResolutionCategory; True if source is already at-or-below MinBpp (no transcode benefit)."""
        Bitrate = getattr(Mf, 'VideoBitrateKbps', None)
        Tier = (getattr(Mf, 'ResolutionCategory', None) or '').lower()
        if not Bitrate or Tier not in _PIXEL_COUNTS:
            return False
        Pixels = _PIXEL_COUNTS[Tier]
        Bpp = (float(Bitrate) * 1000.0) / (Pixels * _ASSUMED_FPS)
        return Bpp < MinBpp

    @staticmethod
    # directive: video-vertical-and-bpp
    def _FirstApplyReason(Reasons) -> str:
        for R in Reasons:
            if R.get('Outcome') == 'applies':
                return f"{R.get('Rule', '?')}:{R.get('Actual', '?')}"
        return 'unspecified'

    # directive: video-vertical-and-bpp
    def _WriteResult(self, MediaFileId: int, Compliant, Reason):
        self._Db.ExecuteNonQuery(
            "UPDATE MediaFiles SET VideoCompliant = %s, VideoCompliantReason = %s WHERE Id = %s",
            (Compliant, Reason, MediaFileId),
        )
