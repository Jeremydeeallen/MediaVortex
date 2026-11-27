from dataclasses import dataclass, asdict
from typing import Optional, Dict, Any

from Core.Database.BaseRepository import BaseRepository
from Core.Logging.LoggingService import LoggingService
from Features.Profiles.TierLadderRepository import TierLadderRepository


@dataclass
# directive: nvenc-rate-anchored-remediation
class EncoderKnobs:  # see transcode.ST6
    """Every column CommandBuilder reads to emit an ffmpeg command. Read fresh per call."""

    ProfileId: int
    ProfileName: str
    Codec: Optional[str]
    Preset: Optional[int]
    FilmGrain: Optional[int]
    YadifMode: Optional[int]
    YadifParity: Optional[int]
    YadifDeint: Optional[int]
    UseNvidiaHardware: Optional[int]
    Tune: Optional[str]
    Multipass: Optional[str]
    PixelFormat: Optional[str]
    AudioCodec: Optional[str]
    AudioBitrateKbps: Optional[int]
    AudioChannels: Optional[int]
    AudioFilter: Optional[str]
    Container: Optional[str]
    FastStart: Optional[bool]
    AqStrength: Optional[int]
    RateControlMode: Optional[str]
    TargetResolution: Optional[str]
    Quality: Optional[int]
    VideoBitrateKbps: Optional[int]
    ContainerType: Optional[str]
    SourceBitratePercent: Optional[int]
    MinBitrateKbps: Optional[int]
    MaxBitrateKbps: Optional[int]
    MaxBitrateMultiplier: Optional[float]
    Gop: Optional[int]
    RcLookahead: Optional[int]
    BFrames: Optional[int]
    BRefMode: Optional[str]
    ScaleHeight: Optional[int]
    # NVENC advanced knobs surfaced 2026-06-29 (Phase B of wakko onboarding); previously hardcoded.
    SpatialAq: Optional[int] = None
    TemporalAq: Optional[int] = None
    WeightedPred: Optional[int] = None
    # QSV (av1_qsv) Profile-level flag + low-power switch.
    UseIntelHardware: Optional[int] = None
    LowPower: Optional[int] = None
    # QSV (av1_qsv) per-threshold knobs.
    QsvExtBrc: Optional[int] = None
    QsvAdaptiveI: Optional[int] = None
    QsvAdaptiveB: Optional[int] = None
    QsvLookaheadDepth: Optional[int] = None
    QsvBStrategy: Optional[int] = None
    QsvTileCols: Optional[int] = None
    QsvTileRows: Optional[int] = None
    # directive: transcode-flow-canonical -- tier ladder rate columns.
    TargetKbps: Optional[int] = None
    IcqQ: Optional[int] = None

    # directive: nvenc-rate-anchored-remediation
    def ToDict(self) -> Dict[str, Any]:
        return asdict(self)


# directive: nvenc-rate-anchored-remediation, profile-row-lookup | # see transcode.ST6, profile-tier-ladder.S5
class EncoderKnobRepository(BaseRepository):
    """Single read path used by CommandBuilder to fetch encoder knobs for a profile + content class + source resolution."""

    # directive: profile-row-lookup | # see profile-tier-ladder.S5 -- knobs come from the encode row (the source row's target), the same row admission and compliance read
    def GetEncoderKnobsForProfile(self, ProfileName: str, ContentClass: str, SourceResolution: str) -> Optional[EncoderKnobs]:
        """Fetch every knob CommandBuilder needs. Reads fresh per call; never caches."""
        try:
            Tiers = TierLadderRepository(self.DatabaseService)
            Source = Tiers.GetProfileRow(ProfileName, ContentClass, SourceResolution)
            Encode = Tiers.GetEncodeRow(ProfileName, ContentClass, SourceResolution)
            if Source is None or Encode is None:
                LoggingService.LogWarning(
                    f"EncoderKnobs not found: profile='{ProfileName}' class='{ContentClass}' source='{SourceResolution}'",
                    "EncoderKnobRepository", "GetEncoderKnobsForProfile",
                )
                return None

            Row = Encode.Columns
            ActualTarget = SourceResolution if Source.TargetResolution == Source.Resolution else Source.TargetResolution
            return EncoderKnobs(
                ProfileId=Encode.ProfileId,
                ProfileName=Encode.ProfileName,
                Codec=Row.get('Codec'),
                Preset=Row.get('Preset'),
                FilmGrain=Row.get('FilmGrain'),
                YadifMode=Row.get('YadifMode'),
                YadifParity=Row.get('YadifParity'),
                YadifDeint=Row.get('YadifDeint'),
                UseNvidiaHardware=Row.get('UseNvidiaHardware'),
                Tune=Row.get('Tune'),
                Multipass=Row.get('Multipass'),
                PixelFormat=Row.get('PixelFormat'),
                AudioCodec=Row.get('ProfileAudioCodec'),
                AudioBitrateKbps=Row.get('ProfileAudioBitrateKbps'),
                AudioChannels=Row.get('AudioChannels'),
                AudioFilter=Row.get('AudioFilter'),
                Container=Row.get('Container'),
                FastStart=Row.get('FastStart'),
                AqStrength=Row.get('AqStrength'),
                RateControlMode=Row.get('RateControlMode'),
                TargetResolution=ActualTarget,
                Quality=Row.get('Quality'),
                VideoBitrateKbps=Row.get('VideoBitrateKbps'),
                ContainerType=Row.get('ContainerType'),
                SourceBitratePercent=Row.get('SourceBitratePercent'),
                MinBitrateKbps=Row.get('MinBitrateKbps'),
                MaxBitrateKbps=Row.get('MaxBitrateKbps'),
                MaxBitrateMultiplier=float(Row['MaxBitrateMultiplier']) if Row.get('MaxBitrateMultiplier') is not None else None,
                Gop=Row.get('Gop'),
                RcLookahead=Row.get('RcLookahead'),
                BFrames=Row.get('BFrames'),
                BRefMode=Row.get('BRefMode'),
                ScaleHeight=Row.get('ScaleHeight'),
                SpatialAq=Row.get('SpatialAq'),
                TemporalAq=Row.get('TemporalAq'),
                WeightedPred=Row.get('WeightedPred'),
                UseIntelHardware=Row.get('UseIntelHardware'),
                LowPower=Row.get('LowPower'),
                QsvExtBrc=Row.get('QsvExtBrc'),
                QsvAdaptiveI=Row.get('QsvAdaptiveI'),
                QsvAdaptiveB=Row.get('QsvAdaptiveB'),
                QsvLookaheadDepth=Row.get('QsvLookaheadDepth'),
                QsvBStrategy=Row.get('QsvBStrategy'),
                QsvTileCols=Row.get('QsvTileCols'),
                QsvTileRows=Row.get('QsvTileRows'),
                TargetKbps=Row.get('TargetKbps'),
                IcqQ=Row.get('IcqQ'),
            )
        except Exception as e:
            LoggingService.LogException(
                f"Exception reading encoder knobs for profile '{ProfileName}' class '{ContentClass}' at '{SourceResolution}'",
                e, "EncoderKnobRepository", "GetEncoderKnobsForProfile",
            )
            return None
