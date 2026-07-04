from dataclasses import dataclass
from typing import Optional

from Core.Database.DatabaseService import DatabaseService


@dataclass(frozen=True)
class AdequacyDecision:
    Excluded: bool
    Reason: str
    SourceKbps: Optional[int]
    Tier1TargetKbps: Optional[int]


# directive: transcode-flow-canonical | # see transcode.ST2
class AdequacyGate:

    # directive: transcode-flow-canonical | # see transcode.ST2
    def __init__(self, Db: Optional[DatabaseService] = None):
        self.Db = Db or DatabaseService()

    # directive: transcode-flow-canonical | # see transcode.ST2
    def Evaluate(self, MediaFile) -> AdequacyDecision:
        Family = self._ResolveFamily(MediaFile)
        SourceRes = getattr(MediaFile, 'ResolutionCategory', None)
        SourceKbps = self._ResolveSourceKbps(MediaFile)
        if not Family:
            return self._Emit(MediaFile, 'InsufficientData:NoFamily', Excluded=False, SourceKbps=SourceKbps, Tier1TargetKbps=None)
        if not SourceRes:
            return self._Emit(MediaFile, 'InsufficientData:NoResolutionCategory', Excluded=False, SourceKbps=SourceKbps, Tier1TargetKbps=None)
        if SourceKbps is None or SourceKbps <= 0:
            return self._Emit(MediaFile, 'InsufficientData:NoSourceKbps', Excluded=False, SourceKbps=SourceKbps, Tier1TargetKbps=None)
        ContentClass = getattr(MediaFile, 'ContentClass', None) or 'live_action'
        Tier1TargetKbps = self._Tier1Target(Family, SourceRes, ContentClass)
        if Tier1TargetKbps is None:
            return self._Emit(MediaFile, f'InsufficientData:NoTier1Reference:{Family}/{ContentClass}/{SourceRes}',
                            Excluded=False, SourceKbps=SourceKbps, Tier1TargetKbps=None)
        if SourceKbps <= Tier1TargetKbps:
            return self._Emit(MediaFile, 'ExcludedCompactSource',
                            Excluded=True, SourceKbps=SourceKbps, Tier1TargetKbps=Tier1TargetKbps)
        return self._Emit(MediaFile, 'Admitted', Excluded=False, SourceKbps=SourceKbps, Tier1TargetKbps=Tier1TargetKbps)

    # directive: transcode-flow-canonical | # see transcode.ST2
    def _ResolveFamily(self, MediaFile) -> Optional[str]:
        AssignedProfile = getattr(MediaFile, 'AssignedProfile', None)
        if not AssignedProfile:
            return None
        Row = self.Db.ExecuteQuery(
            "SELECT Family FROM Profiles WHERE ProfileName = %s",
            (AssignedProfile,),
        )
        if not Row:
            return None
        Family = Row[0].get('family')
        return Family if Family else None

    # directive: transcode-flow-canonical | # see transcode.ST2
    def _ResolveSourceKbps(self, MediaFile) -> Optional[int]:
        Vbr = getattr(MediaFile, 'VideoBitrateKbps', None)
        if Vbr:
            return int(Vbr)
        Obr = getattr(MediaFile, 'OverallBitrate', None)
        if Obr:
            return int(Obr)
        return None

    # directive: transcode-flow-canonical | # see transcode.ST2
    def _Tier1Target(self, Family: str, Resolution: str, ContentClass: str) -> Optional[int]:
        Row = self.Db.ExecuteQuery(
            "SELECT pt.TargetKbps FROM Profiles p "
            "JOIN ProfileThresholds pt ON pt.ProfileId = p.Id "
            "WHERE p.Family = %s AND p.QualityTier = 1 AND p.ContentClass = %s "
            "  AND pt.Resolution = %s AND pt.TargetKbps IS NOT NULL "
            "ORDER BY p.Id LIMIT 1",
            (Family, ContentClass, Resolution),
        )
        if not Row:
            return None
        Value = Row[0].get('targetkbps')
        return int(Value) if Value is not None else None

    # directive: transcode-flow-canonical | # see transcode.ST2
    def _Emit(self, MediaFile, Reason: str, Excluded: bool,
            SourceKbps: Optional[int], Tier1TargetKbps: Optional[int]) -> AdequacyDecision:
        MediaFileId = getattr(MediaFile, 'Id', None)
        if MediaFileId is not None:
            Encoded = f"{Reason}:src={SourceKbps}:tier1={Tier1TargetKbps}"
            self.Db.ExecuteNonQuery(
                "UPDATE MediaFiles SET AdequacyDecision = %s, AdequacyDecisionAt = NOW() WHERE Id = %s",
                (Encoded, int(MediaFileId)),
            )
        return AdequacyDecision(Excluded=Excluded, Reason=Reason,
                              SourceKbps=SourceKbps, Tier1TargetKbps=Tier1TargetKbps)
