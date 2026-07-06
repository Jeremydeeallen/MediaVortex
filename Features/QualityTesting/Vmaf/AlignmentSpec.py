# directive: transcode-flow-canonical
from dataclasses import dataclass
from typing import Optional, Tuple


# directive: transcode-flow-canonical
class AlignmentSpecError(ValueError):
    pass


# directive: transcode-flow-canonical
@dataclass(frozen=True)
class AlignmentSpec:
    ColorPrimaries: str
    TransferFunction: str
    ColorMatrix: str
    ColorRange: str
    SourceFps: float
    TargetFps: float
    VfrDetected: bool
    TargetResolution: Tuple[int, int]
    SourceCrop: Optional[Tuple[int, int, int, int]]
    EncodedCrop: Optional[Tuple[int, int, int, int]]
    DeinterlaceNeeded: bool
    DetelecineNeeded: bool
    SourceBitDepth: int
    TargetBitDepth: int
    ChromaSubsampling: str
    HdrDetected: bool
    MaxEdgePx: int
    SourceDurationSec: float
    EncodedDurationSec: float

    # directive: transcode-flow-canonical
    def __post_init__(self):
        if not self.ColorPrimaries:
            raise AlignmentSpecError("ColorPrimaries missing")
        if not self.TransferFunction:
            raise AlignmentSpecError("TransferFunction missing")
        if not self.ColorMatrix:
            raise AlignmentSpecError("ColorMatrix missing")
        if not self.ColorRange:
            raise AlignmentSpecError("ColorRange missing")
        if not isinstance(self.SourceFps, (int, float)) or self.SourceFps <= 0.0:
            raise AlignmentSpecError(f"SourceFps must be > 0, got {self.SourceFps!r}")
        if not isinstance(self.TargetFps, (int, float)) or self.TargetFps <= 0.0:
            raise AlignmentSpecError(f"TargetFps must be > 0, got {self.TargetFps!r}")
        Width, Height = self.TargetResolution
        if Width <= 0 or Height <= 0:
            raise AlignmentSpecError(f"TargetResolution invalid: {self.TargetResolution!r}")
        if self.SourceBitDepth not in (8, 10, 12):
            raise AlignmentSpecError(f"SourceBitDepth invalid: {self.SourceBitDepth!r}")
        if self.TargetBitDepth not in (8, 10, 12):
            raise AlignmentSpecError(f"TargetBitDepth invalid: {self.TargetBitDepth!r}")
        if self.MaxEdgePx <= 0:
            raise AlignmentSpecError(f"MaxEdgePx must be > 0, got {self.MaxEdgePx!r}")
        if self.SourceDurationSec <= 0.0 or self.EncodedDurationSec <= 0.0:
            raise AlignmentSpecError(
                f"Durations must be > 0, got source={self.SourceDurationSec!r} encoded={self.EncodedDurationSec!r}"
            )
        FrameSec = 1.0 / float(self.SourceFps)
        Delta = abs(self.SourceDurationSec - self.EncodedDurationSec)
        if Delta > FrameSec:
            raise AlignmentSpecError(
                f"Duration parity failed: delta={Delta:.4f}s > 1 frame ({FrameSec:.4f}s @ {self.SourceFps} fps)"
            )
