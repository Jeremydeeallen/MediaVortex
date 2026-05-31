from dataclasses import dataclass, asdict
from typing import Optional, Dict, Any

from Core.Database.BaseRepository import BaseRepository
from Core.Logging.LoggingService import LoggingService


@dataclass
# directive: nvenc-rate-anchored-remediation
class EncoderKnobs:
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

    # directive: nvenc-rate-anchored-remediation
    def ToDict(self) -> Dict[str, Any]:
        return asdict(self)


# directive: nvenc-rate-anchored-remediation
class EncoderKnobRepository(BaseRepository):
    """Single read path used by CommandBuilder to fetch encoder knobs for a profile + source resolution."""

    # directive: nvenc-rate-anchored-remediation
    def GetEncoderKnobsForProfile(self, ProfileName: str, SourceResolution: str) -> Optional[EncoderKnobs]:
        """Fetch every knob CommandBuilder needs. Reads fresh per call; never caches."""
        try:
            TargetResolution = self._ResolveTargetResolution(ProfileName, SourceResolution)
            if TargetResolution is None:
                return None

            NormalizedSource = self._NormalizeResolution(SourceResolution)
            LookupResolution = NormalizedSource if TargetResolution == 'No downscaling' else TargetResolution

            Query = (
                "SELECT p.Id AS ProfileId, p.ProfileName, "
                "       p.Codec, p.Preset, p.FilmGrain, "
                "       p.YadifMode, p.YadifParity, p.YadifDeint, p.UseNvidiaHardware, "
                "       p.Tune, p.Multipass, p.PixelFormat, "
                "       p.AudioCodec, p.AudioBitrateKbps, p.AudioChannels, p.AudioFilter, "
                "       p.Container, p.FastStart, p.AqStrength, p.RateControlMode, "
                "       pt.Resolution, pt.Quality, pt.VideoBitrateKbps, pt.ContainerType, "
                "       pt.SourceBitratePercent, pt.MinBitrateKbps, pt.MaxBitrateKbps, "
                "       pt.MaxBitrateMultiplier, pt.Gop, "
                "       pt.RcLookahead, pt.BFrames, pt.BRefMode, "
                "       pt.ScaleHeight "
                "FROM Profiles p "
                "JOIN ProfileThresholds pt ON pt.ProfileId = p.Id "
                "WHERE p.ProfileName = %s AND pt.Resolution = %s "
                "LIMIT 1"
            )
            Rows = self.ExecuteQuery(Query, (ProfileName, LookupResolution))
            if not Rows:
                LoggingService.LogWarning(
                    f"EncoderKnobs not found: profile='{ProfileName}' source='{SourceResolution}' lookup='{LookupResolution}'",
                    "EncoderKnobRepository", "GetEncoderKnobsForProfile",
                )
                return None

            Row = Rows[0]
            ActualTarget = SourceResolution if TargetResolution == 'No downscaling' else TargetResolution
            return EncoderKnobs(
                ProfileId=Row['ProfileId'],
                ProfileName=Row['ProfileName'],
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
                AudioCodec=Row.get('AudioCodec'),
                AudioBitrateKbps=Row.get('AudioBitrateKbps'),
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
            )
        except Exception as e:
            LoggingService.LogException(
                f"Exception reading encoder knobs for profile '{ProfileName}' at '{SourceResolution}'",
                e, "EncoderKnobRepository", "GetEncoderKnobsForProfile",
            )
            return None

    # directive: nvenc-rate-anchored-remediation
    def _ResolveTargetResolution(self, ProfileName: str, SourceResolution: str) -> Optional[str]:
        """Look up TranscodeDownTo for the (Profile, SourceResolution) pair; treat empty as 'No downscaling'."""
        Query = (
            "SELECT pt.TranscodeDownTo FROM ProfileThresholds pt "
            "JOIN Profiles p ON pt.ProfileId = p.Id "
            "WHERE p.ProfileName = %s AND pt.Resolution = %s LIMIT 1"
        )
        Rows = self.ExecuteQuery(Query, (ProfileName, SourceResolution))
        if not Rows:
            Normalized = self._NormalizeResolution(SourceResolution)
            if Normalized != SourceResolution:
                Rows = self.ExecuteQuery(Query, (ProfileName, Normalized))
        if not Rows:
            LoggingService.LogWarning(
                f"No ProfileThresholds row for profile='{ProfileName}' resolution='{SourceResolution}'",
                "EncoderKnobRepository", "_ResolveTargetResolution",
            )
            return None
        Value = Rows[0].get('TranscodeDownTo')
        return Value if Value else 'No downscaling'

    # directive: nvenc-rate-anchored-remediation
    def _NormalizeResolution(self, Resolution: str) -> str:
        """Bucket WIDTHxHEIGHT pixel strings to category labels by long-edge (letterbox-safe; portrait-safe)."""
        if not Resolution or 'x' not in Resolution:
            return Resolution
        Parts = Resolution.lower().split('x')
        if len(Parts) != 2 or not Parts[0].isdigit() or not Parts[1].isdigit():
            return Resolution
        Tier = max(int(Parts[0]), int(Parts[1]))
        if Tier >= 3840:
            return '2160p'
        if Tier >= 1920:
            return '1080p'
        if Tier >= 1280:
            return '720p'
        return '480p'
