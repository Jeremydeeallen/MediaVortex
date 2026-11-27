from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from Core.Database.DatabaseService import DatabaseService
from Core.Resolution.ResolutionTierRegistry import ResolutionTierRegistry

NO_DOWNSCALING = 'No downscaling'


@dataclass(frozen=True)
# directive: transcode-flow-canonical | # see profiles.C3
class BitrateLadderCell:
    Family: str
    ContentClass: str
    Resolution: str
    Tier: int
    TargetKbps: Optional[int]


@dataclass(frozen=True)
# directive: transcode-flow-canonical | # see profiles.C3
class IcqLadderCell:
    Family: str
    ContentClass: str
    Tier: int
    IcqQ: Optional[int]


@dataclass(frozen=True)
# directive: profile-row-lookup | # see profile-tier-ladder.S5 -- one joined Profiles + ProfileThresholds row; Columns carries every column for EncoderKnobs
class ProfileRow:
    Columns: Dict[str, Any]
    ProfileId: int
    ProfileName: str
    Codec: Optional[str]
    RateControlMode: Optional[str]
    Resolution: str
    ContentClass: str
    TranscodeDownTo: Optional[str]
    TargetResolution: str
    TargetKbps: Optional[int]
    VideoBitrateKbps: Optional[int]
    AudioBitrateKbps: Optional[int]
    Quality: Optional[int]
    IcqQ: Optional[int]
    ContainerType: Optional[str]


# directive: transcode-flow-canonical | # see profiles.C3
class TierLadderRepository:

    # directive: transcode-flow-canonical | # see profiles.C3
    def __init__(self, Db: Optional[DatabaseService] = None):
        self.Db = Db or DatabaseService()

    @staticmethod
    # directive: profile-row-lookup | # see profile-tier-ladder.C9 -- WIDTHxHEIGHT buckets to a category label by the registry; labels pass through
    def NormalizeResolution(Resolution: str) -> str:
        if not Resolution or 'x' not in Resolution:
            return Resolution
        Parts = Resolution.lower().split('x')
        if len(Parts) != 2 or not Parts[0].isdigit() or not Parts[1].isdigit():
            return Resolution
        Tier = ResolutionTierRegistry().FromDims(int(Parts[0]), int(Parts[1]))
        return Tier.Name[1:] if Tier.Name.startswith('T') else Tier.Name

    # directive: profile-row-lookup | # see profile-tier-ladder.S5 -- the source row: the one lookup every consumer shares
    def GetProfileRow(self, ProfileName: str, ContentClass: str, Resolution: str) -> Optional[ProfileRow]:
        Rows = self.Db.ExecuteQuery(
            "SELECT pt.*, p.ProfileName, p.Codec, p.Preset, p.FilmGrain, p.YadifMode, p.YadifParity, p.YadifDeint, "
            "       p.UseNvidiaHardware, p.UseIntelHardware, p.Tune, p.Multipass, p.PixelFormat, "
            "       p.AudioCodec AS ProfileAudioCodec, p.AudioBitrateKbps AS ProfileAudioBitrateKbps, "
            "       p.AudioChannels, p.AudioFilter, p.Container, p.FastStart, p.AqStrength, p.RateControlMode, "
            "       p.SpatialAq, p.TemporalAq, p.WeightedPred, p.LowPower "
            "FROM ProfileThresholds pt JOIN Profiles p ON p.Id = pt.ProfileId "
            "WHERE p.ProfileName = %s AND pt.ContentClass = %s AND pt.Resolution = %s "
            "ORDER BY pt.Id LIMIT 1",
            (ProfileName, ContentClass, self.NormalizeResolution(Resolution)),
        )
        if not Rows:
            return None
        R = Rows[0]
        DownTo = R.get('TranscodeDownTo')
        Source = R.get('Resolution')
        return ProfileRow(
            Columns=R,
            ProfileId=int(R.get('ProfileId')),
            ProfileName=R.get('ProfileName'),
            Codec=R.get('Codec'),
            RateControlMode=R.get('RateControlMode'),
            Resolution=Source,
            ContentClass=R.get('ContentClass'),
            TranscodeDownTo=DownTo,
            TargetResolution=DownTo if DownTo and DownTo != NO_DOWNSCALING else Source,
            TargetKbps=int(R.get('TargetKbps')) if R.get('TargetKbps') is not None else None,
            VideoBitrateKbps=int(R.get('VideoBitrateKbps')) if R.get('VideoBitrateKbps') is not None else None,
            AudioBitrateKbps=int(R.get('AudioBitrateKbps')) if R.get('AudioBitrateKbps') is not None else None,
            Quality=int(R.get('Quality')) if R.get('Quality') is not None else None,
            IcqQ=int(R.get('IcqQ')) if R.get('IcqQ') is not None else None,
            ContainerType=R.get('ContainerType'),
        )

    # directive: profile-row-lookup | # see profile-tier-ladder.S5 -- the row at the source row's target resolution: the knobs the encoder runs with
    def GetEncodeRow(self, ProfileName: str, ContentClass: str, SourceResolution: str) -> Optional[ProfileRow]:
        Source = self.GetProfileRow(ProfileName, ContentClass, SourceResolution)
        if Source is None or Source.TargetResolution == Source.Resolution:
            return Source
        return self.GetProfileRow(ProfileName, ContentClass, Source.TargetResolution)

    # directive: tv-video-rule-tier1, profile-row-lookup | # see video-encoding.C1, profile-tier-ladder.C9
    def GetTierEncodeKbps(self, Tier: int, ContentClass: str, Resolution: str) -> Optional[int]:
        ProfileName = self.GetTierProfileName(Tier)
        if ProfileName is None:
            return None
        Row = self.GetEncodeRow(ProfileName, ContentClass, Resolution)
        return Row.TargetKbps if Row else None

    # directive: tv-video-rule-tier1 | # see classifier.C9
    def GetTierProfileName(self, Tier: int) -> Optional[str]:
        Row = self.Db.ExecuteQuery(
            "SELECT ProfileName FROM Profiles "
            "WHERE Family = 'ANY' AND QualityTier = %s AND QualityLabel IS NOT NULL "
            "ORDER BY Id LIMIT 1",
            (int(Tier),),
        )
        if not Row:
            return None
        return Row[0].get('profilename')

    # directive: video-vertical-codec-match-skip
    def GetProfileCodec(self, ProfileName: str) -> Optional[str]:
        Row = self.Db.ExecuteQuery(
            "SELECT Codec FROM Profiles WHERE ProfileName = %s LIMIT 1",
            (ProfileName,),
        )
        if not Row:
            return None
        Value = Row[0].get('codec')
        return str(Value).strip().lower() if Value else None

    # directive: pre-encode-savings-gate, profile-row-lookup | # see video-encoding.C1, profile-tier-ladder.C9
    def GetProfileTarget(self, ProfileName: str, ContentClass: str, Resolution: str) -> Optional[int]:
        Row = self.GetEncodeRow(ProfileName, ContentClass, Resolution)
        return Row.TargetKbps if Row else None

    # directive: transcode-flow-canonical, profile-row-lookup | # see profiles.C3, profile-tier-ladder.C10 -- cells are keyed by the row's class, so the animation ladder is editable
    def GetBitrateLadder(self) -> List[BitrateLadderCell]:
        Rows = self.Db.ExecuteQuery(
            "SELECT p.Family, pt.ContentClass, pt.Resolution, p.QualityTier, "
            "  MIN(pt.TargetKbps) AS targetkbps "
            "FROM Profiles p "
            "JOIN ProfileThresholds pt ON pt.ProfileId = p.Id "
            "WHERE p.Family IS NOT NULL AND p.QualityTier IS NOT NULL "
            "  AND pt.ContentClass IS NOT NULL AND pt.TargetKbps IS NOT NULL "
            "GROUP BY p.Family, pt.ContentClass, pt.Resolution, p.QualityTier "
            "ORDER BY p.Family, pt.ContentClass, pt.Resolution, p.QualityTier"
        )
        return [
            BitrateLadderCell(
                Family=R.get('family') or '',
                ContentClass=R.get('contentclass') or '',
                Resolution=R.get('resolution') or '',
                Tier=int(R.get('qualitytier') or 0),
                TargetKbps=int(R.get('targetkbps')) if R.get('targetkbps') is not None else None,
            )
            for R in Rows
        ]

    # directive: transcode-flow-canonical | # see transcode-flow-canonical.C25
    def GetTierLabelMap(self) -> dict:
        Rows = self.Db.ExecuteQuery(
            "SELECT QualityTier, QualityLabel FROM Profiles "
            "WHERE Family = 'ANY' AND QualityLabel IS NOT NULL "
            "ORDER BY QualityTier"
        )
        return {int(R['qualitytier']): R['qualitylabel'] for R in Rows if R.get('qualitytier') is not None}

    # directive: transcode-flow-canonical, profile-row-lookup | # see profiles.C3, profile-tier-ladder.C10
    def GetIcqLadder(self) -> List[IcqLadderCell]:
        Rows = self.Db.ExecuteQuery(
            "SELECT p.Family, pt.ContentClass, p.QualityTier, "
            "  MIN(pt.IcqQ) AS icqq "
            "FROM Profiles p "
            "JOIN ProfileThresholds pt ON pt.ProfileId = p.Id "
            "WHERE p.Family IS NOT NULL AND p.QualityTier IS NOT NULL "
            "  AND pt.ContentClass IS NOT NULL AND pt.IcqQ IS NOT NULL "
            "GROUP BY p.Family, pt.ContentClass, p.QualityTier "
            "ORDER BY p.Family, pt.ContentClass, p.QualityTier"
        )
        return [
            IcqLadderCell(
                Family=R.get('family') or '',
                ContentClass=R.get('contentclass') or '',
                Tier=int(R.get('qualitytier') or 0),
                IcqQ=int(R.get('icqq')) if R.get('icqq') is not None else None,
            )
            for R in Rows
        ]

    # directive: transcode-flow-canonical, profile-row-lookup | # see profiles.C3, profile-tier-ladder.C10
    def UpdateBitrateCell(self, Family: str, ContentClass: str, Resolution: str,
                          Tier: int, TargetKbps: int) -> int:
        if TargetKbps <= 0:
            raise ValueError(f"TargetKbps must be > 0, got {TargetKbps}")
        Affected = self.Db.ExecuteNonQuery(
            "UPDATE ProfileThresholds SET TargetKbps = %s "
            "WHERE Resolution = %s AND ContentClass = %s "
            "  AND ProfileId IN (SELECT Id FROM Profiles WHERE Family = %s AND QualityTier = %s)",
            (int(TargetKbps), Resolution, ContentClass, Family, int(Tier)),
        )
        return int(Affected or 0)

    # directive: transcode-flow-canonical, profile-row-lookup | # see profiles.C3, profile-tier-ladder.C10
    def UpdateIcqCell(self, Family: str, ContentClass: str, Tier: int, IcqQ: int) -> int:
        if IcqQ < 1 or IcqQ > 51:
            raise ValueError(f"IcqQ must be in [1,51], got {IcqQ}")
        Affected = self.Db.ExecuteNonQuery(
            "UPDATE ProfileThresholds SET IcqQ = %s "
            "WHERE ContentClass = %s "
            "  AND ProfileId IN (SELECT Id FROM Profiles WHERE Family = %s AND QualityTier = %s)",
            (int(IcqQ), ContentClass, Family, int(Tier)),
        )
        return int(Affected or 0)
