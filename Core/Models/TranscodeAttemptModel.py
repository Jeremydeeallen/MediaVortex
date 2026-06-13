from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional


# directive: path-schema-migration | # see path.S8
@dataclass
class TranscodeAttemptModel:
    """Single transcode attempt; typed pair (StorageRootId, RelativePath) is the canonical identity."""

    Id: Optional[int] = None
    StorageRootId: Optional[int] = None
    RelativePath: str = ""
    AttemptDate: Optional[datetime] = None
    Quality: int = 0
    OldSizeBytes: int = 0
    NewSizeBytes: int = 0
    Success: Optional[bool] = None
    SizeReductionBytes: int = 0
    SizeReductionPercent: float = 0.0
    ErrorMessage: Optional[str] = None
    TranscodeDurationSeconds: float = 0.0
    FfpmpegCommand: Optional[str] = None
    AudioBitrateKbps: Optional[int] = None
    VideoBitrateKbps: Optional[int] = None
    ProfileName: Optional[str] = None
    VMAF: Optional[float] = None
    QualityTestRequired: int = 1
    QualityTestCompleted: int = 0
    FileReplaced: bool = False
    FileReplacedDate: Optional[datetime] = None
    ReplacementType: Optional[str] = None
    CompletedDate: Optional[datetime] = None
    StartTime: Optional[str] = None
    PreferredAttempt: bool = False
    WorkerName: Optional[str] = None
    MediaFileId: Optional[int] = None

    # directive: path-schema-migration | # see path.S8
    def __post_init__(self):
        if self.AttemptDate is None:
            self.AttemptDate = datetime.now(timezone.utc)

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

    @property
    def OldSizeMB(self) -> float:
        return self.OldSizeBytes / (1024 * 1024) if self.OldSizeBytes > 0 else 0.0

    @property
    def NewSizeMB(self) -> float:
        return self.NewSizeBytes / (1024 * 1024) if self.NewSizeBytes > 0 else 0.0

    @property
    def OldSizeGB(self) -> float:
        return self.OldSizeBytes / (1024 * 1024 * 1024) if self.OldSizeBytes > 0 else 0.0

    @property
    def NewSizeGB(self) -> float:
        return self.NewSizeBytes / (1024 * 1024 * 1024) if self.NewSizeBytes > 0 else 0.0

    @property
    def CompressionRatio(self) -> float:
        if self.NewSizeBytes > 0 and self.OldSizeBytes > 0:
            return self.OldSizeBytes / self.NewSizeBytes
        return 0.0

    @property
    def IsCompressed(self) -> bool:
        return self.NewSizeBytes < self.OldSizeBytes

    @property
    def TranscodeDurationMinutes(self) -> float:
        return self.TranscodeDurationSeconds / 60.0 if self.TranscodeDurationSeconds > 0 else 0.0

    @property
    def VMAFQualityRating(self) -> str:
        if self.VMAF is None:
            return "Not measured"
        if self.VMAF >= 90:
            return "Excellent"
        if self.VMAF >= 80:
            return "Good"
        if self.VMAF >= 70:
            return "Fair"
        if self.VMAF >= 60:
            return "Poor"
        return "Very Poor"

    def CalculateSizeReduction(self):
        if self.OldSizeBytes > 0 and self.NewSizeBytes > 0:
            self.SizeReductionBytes = self.OldSizeBytes - self.NewSizeBytes
            self.SizeReductionPercent = (self.SizeReductionBytes / self.OldSizeBytes) * 100.0
        else:
            self.SizeReductionBytes = 0
            self.SizeReductionPercent = 0.0
