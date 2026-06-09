from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional


# directive: path-schema-migration | # see path.S8
@dataclass
class MediaFileModel:
    """Media file metadata; typed pair (StorageRootId, RelativePath) is the canonical identity."""

    Id: Optional[int] = None
    SeasonId: Optional[int] = None
    StorageRootId: Optional[int] = None
    RelativePath: str = ""
    FileName: str = ""
    SizeMB: float = 0.0
    VideoBitrateKbps: Optional[int] = None
    AudioBitrateKbps: Optional[int] = None
    Resolution: Optional[str] = None
    Codec: Optional[str] = None
    DurationMinutes: Optional[float] = None
    FrameRate: Optional[float] = None
    LastScannedDate: Optional[datetime] = None
    CompressionPotential: Optional[str] = None
    AssignedProfile: Optional[str] = None
    IsInterlaced: Optional[bool] = None
    ResolutionCategory: Optional[str] = None
    FileModificationTime: Optional[datetime] = None
    LastModifiedDate: Optional[datetime] = None
    FileSize: Optional[int] = None
    TotalFrames: Optional[int] = None
    CodecProfile: Optional[str] = None
    ColorRange: Optional[str] = None
    FieldOrder: Optional[str] = None
    HasBFrames: Optional[int] = None
    RefFrames: Optional[int] = None
    PixelFormat: Optional[str] = None
    Level: Optional[int] = None
    AudioChannels: Optional[int] = None
    AudioSampleRate: Optional[int] = None
    AudioSampleFormat: Optional[str] = None
    AudioChannelLayout: Optional[str] = None
    AudioCodec: Optional[str] = None
    SubtitleFormats: Optional[str] = None
    ContainerFormat: Optional[str] = None
    OverallBitrate: Optional[int] = None
    TranscodedByMediaVortex: Optional[bool] = None
    AudioLanguages: Optional[str] = None
    HasExplicitEnglishAudio: Optional[bool] = None
    AudioComplete: Optional[bool] = None
    AudioCorruptSuspect: Optional[bool] = None
    AudioCorruptReason: Optional[str] = None
    SourceIntegratedLufs: Optional[float] = None
    SourceLoudnessRangeLU: Optional[float] = None
    SourceTruePeakDbtp: Optional[float] = None
    SourceIntegratedThresholdLufs: Optional[float] = None
    AdmissionDeferReason: Optional[str] = None
    LoudnessMeasurementFailureReason: Optional[str] = None
    AudioNormalizationMode: Optional[str] = None
    FFprobeFailureCount: Optional[int] = 0
    LastFFprobeError: Optional[str] = None
    LastFFprobeAttemptDate: Optional[datetime] = None
    WorkBucket: Optional[str] = None
    OperationsNeededCsv: Optional[str] = None
    ComplianceGateBlocked: Optional[str] = None
    ComplianceEvaluatedAt: Optional[datetime] = None
    HasForcedSubtitles: Optional[bool] = None

    # directive: path-schema-migration | # see path.S8
    def __post_init__(self):
        if self.LastScannedDate is None:
            self.LastScannedDate = datetime.now(timezone.utc)

    @property
    # directive: path-schema-migration | # see path.S8
    def PathObj(self):
        """Path object for the typed pair; raises PathError on invalid state."""
        from Core.Path.Path import Path
        return Path(self.StorageRootId, self.RelativePath or "")

    @property
    # directive: path-schema-migration | # see path.S8
    def FilePath(self) -> str:
        """Canonical display string; computed from typed pair via PathStorageRoots singleton."""
        if self.StorageRootId is None:
            return ""
        from Core.Path.Path import Path
        from Core.Path.PathStorageRoots import GetPrefixMap
        return Path(self.StorageRootId, self.RelativePath or "").CanonicalDisplay(GetPrefixMap())
