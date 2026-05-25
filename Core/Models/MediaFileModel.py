from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional


@dataclass
class MediaFileModel:
    """Represents individual media files with metadata."""
    
    Id: Optional[int] = None
    SeasonId: Optional[int] = None
    StorageRootId: Optional[int] = None
    RelativePath: str = ""
    FilePath: str = ""  # Legacy column; populated via Resolve at construction for worker I/O. Dropped in Phase F.
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

    # New metadata fields
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

    # Audio language tracking
    AudioLanguages: Optional[str] = None
    HasExplicitEnglishAudio: Optional[bool] = None

    # Audio completion state (audio-completion.feature.md + media-tabs-and-loudness)
    AudioComplete: Optional[bool] = None
    AudioCorruptSuspect: Optional[bool] = None
    AudioCorruptReason: Optional[str] = None
    SourceIntegratedLufs: Optional[float] = None
    SourceLoudnessRangeLU: Optional[float] = None
    SourceTruePeakDbtp: Optional[float] = None
    SourceIntegratedThresholdLufs: Optional[float] = None  # linear-loudnorm: measured_thresh
    AdmissionDeferReason: Optional[str] = None
    LoudnessMeasurementFailureReason: Optional[str] = None
    AudioNormalizationMode: Optional[str] = None

    # Cascade-materialized work-needed flags (media-tabs-and-loudness.feature.md).
    # Read-only on the model; written by the cascade recompute, not by workers.
    NeedsQuick: Optional[bool] = None
    NeedsTranscode: Optional[bool] = None

    # FFprobe failure tracking
    FFprobeFailureCount: Optional[int] = 0
    LastFFprobeError: Optional[str] = None
    LastFFprobeAttemptDate: Optional[datetime] = None
    
    def __post_init__(self):
        if self.LastScannedDate is None:
            self.LastScannedDate = datetime.now(timezone.utc)
        # Compute FilePath (canonical) from (StorageRootId, RelativePath) if not
        # explicitly supplied. After Phase F drops the FilePath column from DB,
        # this becomes the only way FilePath is populated.
        if not self.FilePath and self.StorageRootId is not None and self.RelativePath:
            try:
                from Core.PathStorage import CanonicalFor
                self.FilePath = CanonicalFor(self.StorageRootId, self.RelativePath)
            except Exception:
                pass
