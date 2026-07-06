# directive: transcode-flow-canonical
from enum import Enum


# directive: transcode-flow-canonical
class ColorSpaceParseError(ValueError):
    pass


# directive: transcode-flow-canonical
class ColorPrimaries(Enum):
    Bt709 = "bt709"
    Bt2020 = "bt2020"
    Smpte170m = "smpte170m"
    Smpte240m = "smpte240m"


# directive: transcode-flow-canonical
class TransferFunction(Enum):
    Bt709 = "bt709"
    Smpte170m = "smpte170m"
    Smpte2084 = "smpte2084"
    AribStdB67 = "arib-std-b67"
    Bt2020_10 = "bt2020-10"
    Bt2020_12 = "bt2020-12"


# directive: transcode-flow-canonical
class ColorMatrix(Enum):
    Bt709 = "bt709"
    Bt2020Nc = "bt2020nc"
    Bt2020C = "bt2020c"
    Smpte170m = "smpte170m"


# directive: transcode-flow-canonical
class ColorRange(Enum):
    Tv = "tv"
    Pc = "pc"


# directive: transcode-flow-canonical
class ColorSpaceService:
    PRIMARIES_MAP = {
        "bt709": ColorPrimaries.Bt709,
        "bt2020": ColorPrimaries.Bt2020,
        "smpte170m": ColorPrimaries.Smpte170m,
        "smpte240m": ColorPrimaries.Smpte240m,
    }

    TRANSFER_MAP = {
        "bt709": TransferFunction.Bt709,
        "smpte170m": TransferFunction.Smpte170m,
        "smpte2084": TransferFunction.Smpte2084,
        "arib-std-b67": TransferFunction.AribStdB67,
        "bt2020-10": TransferFunction.Bt2020_10,
        "bt2020-12": TransferFunction.Bt2020_12,
    }

    MATRIX_MAP = {
        "bt709": ColorMatrix.Bt709,
        "bt2020nc": ColorMatrix.Bt2020Nc,
        "bt2020c": ColorMatrix.Bt2020C,
        "smpte170m": ColorMatrix.Smpte170m,
    }

    RANGE_MAP = {
        "tv": ColorRange.Tv,
        "mpeg": ColorRange.Tv,
        "limited": ColorRange.Tv,
        "pc": ColorRange.Pc,
        "jpeg": ColorRange.Pc,
        "full": ColorRange.Pc,
    }

    # directive: transcode-flow-canonical
    @classmethod
    def ParsePrimaries(cls, Value: str) -> ColorPrimaries:
        if not Value:
            raise ColorSpaceParseError("ColorPrimaries empty")
        Key = Value.strip().lower()
        if Key not in cls.PRIMARIES_MAP:
            raise ColorSpaceParseError(f"Unparseable ColorPrimaries: {Value!r}")
        return cls.PRIMARIES_MAP[Key]

    # directive: transcode-flow-canonical
    @classmethod
    def ParseTransfer(cls, Value: str) -> TransferFunction:
        if not Value:
            raise ColorSpaceParseError("TransferFunction empty")
        Key = Value.strip().lower()
        if Key not in cls.TRANSFER_MAP:
            raise ColorSpaceParseError(f"Unparseable TransferFunction: {Value!r}")
        return cls.TRANSFER_MAP[Key]

    # directive: transcode-flow-canonical
    @classmethod
    def ParseMatrix(cls, Value: str) -> ColorMatrix:
        if not Value:
            raise ColorSpaceParseError("ColorMatrix empty")
        Key = Value.strip().lower()
        if Key not in cls.MATRIX_MAP:
            raise ColorSpaceParseError(f"Unparseable ColorMatrix: {Value!r}")
        return cls.MATRIX_MAP[Key]

    # directive: transcode-flow-canonical
    @classmethod
    def ParseRange(cls, Value: str) -> ColorRange:
        if not Value:
            raise ColorSpaceParseError("ColorRange empty")
        Key = Value.strip().lower()
        if Key not in cls.RANGE_MAP:
            raise ColorSpaceParseError(f"Unparseable ColorRange: {Value!r}")
        return cls.RANGE_MAP[Key]

    # directive: transcode-flow-canonical
    @classmethod
    def IsHdr(cls, Primaries: ColorPrimaries, Transfer: TransferFunction) -> bool:
        return (
            Primaries == ColorPrimaries.Bt2020
            or Transfer in (TransferFunction.Smpte2084, TransferFunction.AribStdB67)
        )

    # directive: transcode-flow-canonical
    @classmethod
    def BuildToneMapGraph(cls, SourceTransfer: TransferFunction, TargetTransfer: TransferFunction) -> str:
        if SourceTransfer == TargetTransfer:
            return ""
        HdrSources = (TransferFunction.Smpte2084, TransferFunction.AribStdB67)
        if SourceTransfer in HdrSources and TargetTransfer == TransferFunction.Bt709:
            return "zscale=t=linear:npl=100,tonemap=hable:desat=0,zscale=p=bt709:t=bt709:m=bt709:r=tv,format=yuv420p"
        raise ColorSpaceParseError(
            f"Unsupported tone-map: {SourceTransfer.value} -> {TargetTransfer.value}"
        )
