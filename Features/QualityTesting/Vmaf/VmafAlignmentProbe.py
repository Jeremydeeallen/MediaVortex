# directive: transcode-flow-canonical
from typing import Any, Dict, Optional, Tuple
from Features.QualityTesting.Vmaf.AlignmentSpec import AlignmentSpec
from Core.Media.ColorSpaceService import (
    ColorSpaceService,
    ColorPrimaries,
    TransferFunction,
    ColorMatrix,
    ColorRange,
)
from Features.TranscodeJob.Emit.MediaProbeAdapter import MediaProbeAdapter


# directive: transcode-flow-canonical
class VmafAlignmentProbeError(RuntimeError):
    pass


# directive: transcode-flow-canonical
class VmafAlignmentProbe:
    PIX_FMT_BIT_DEPTH = {
        "yuv420p": 8, "yuv422p": 8, "yuv444p": 8, "nv12": 8,
        "yuv420p10le": 10, "yuv422p10le": 10, "yuv444p10le": 10, "p010le": 10,
        "yuv420p12le": 12, "yuv422p12le": 12, "yuv444p12le": 12,
    }
    PIX_FMT_CHROMA = {
        "yuv420p": "4:2:0", "yuv420p10le": "4:2:0", "yuv420p12le": "4:2:0", "nv12": "4:2:0", "p010le": "4:2:0",
        "yuv422p": "4:2:2", "yuv422p10le": "4:2:2", "yuv422p12le": "4:2:2",
        "yuv444p": "4:4:4", "yuv444p10le": "4:4:4", "yuv444p12le": "4:4:4",
    }

    # directive: transcode-flow-canonical
    def __init__(self, Adapter: Optional[MediaProbeAdapter] = None):
        self.Adapter = Adapter or MediaProbeAdapter()

    # directive: transcode-flow-canonical
    def Probe(self, SourcePath: str, EncodedPath: str) -> AlignmentSpec:
        SourceProbe = self.Adapter.ProbeStreams(SourcePath)
        EncodedProbe = self.Adapter.ProbeStreams(EncodedPath)
        return self._DeriveSpec(SourceProbe, EncodedProbe)

    # directive: transcode-flow-canonical
    def _DeriveSpec(self, SourceProbe: Dict[str, Any], EncodedProbe: Dict[str, Any]) -> AlignmentSpec:
        SourceVideo = self._SelectVideoStream(SourceProbe)
        EncodedVideo = self._SelectVideoStream(EncodedProbe)
        SourceFormat = SourceProbe.get('format', {}) or {}
        EncodedFormat = EncodedProbe.get('format', {}) or {}

        SourceDuration = self._ParseDuration(SourceFormat, SourceVideo, "source")
        EncodedDuration = self._ParseDuration(EncodedFormat, EncodedVideo, "encoded")

        SourceFps = self._ParseFps(SourceVideo.get('r_frame_rate'), "source r_frame_rate")
        SourceAvgFps = self._ParseFps(SourceVideo.get('avg_frame_rate'), "source avg_frame_rate")
        VfrDetected = abs(SourceFps - SourceAvgFps) > 0.02
        TargetFps = self._ParseFps(EncodedVideo.get('r_frame_rate'), "encoded r_frame_rate")

        Width = int(EncodedVideo.get('width') or 0)
        Height = int(EncodedVideo.get('height') or 0)
        if Width <= 0 or Height <= 0:
            raise VmafAlignmentProbeError(f"Encoded resolution invalid: {Width}x{Height}")
        MaxEdgePx = max(Width, Height)

        EncodedPrimaries = ColorSpaceService.ParsePrimaries(EncodedVideo.get('color_primaries') or 'bt709')
        EncodedTransfer = ColorSpaceService.ParseTransfer(EncodedVideo.get('color_transfer') or 'bt709')
        EncodedMatrix = ColorSpaceService.ParseMatrix(EncodedVideo.get('color_space') or 'bt709')
        EncodedRange = ColorSpaceService.ParseRange(EncodedVideo.get('color_range') or 'tv')

        SourcePrimaries = ColorSpaceService.ParsePrimaries(SourceVideo.get('color_primaries') or 'bt709')
        SourceTransfer = ColorSpaceService.ParseTransfer(SourceVideo.get('color_transfer') or 'bt709')
        HdrDetected = ColorSpaceService.IsHdr(SourcePrimaries, SourceTransfer)

        SourceField = (SourceVideo.get('field_order') or 'progressive').lower()
        DeinterlaceNeeded = SourceField not in ('progressive', '', 'unknown')
        DetelecineNeeded = self._IsTelecined(SourceFps, SourceAvgFps, SourceField)

        SourceBitDepth = self._ParseBitDepth(SourceVideo.get('pix_fmt', ''), "source")
        TargetBitDepth = self._ParseBitDepth(EncodedVideo.get('pix_fmt', ''), "encoded")
        ChromaSubsampling = self._ParseChroma(EncodedVideo.get('pix_fmt', ''), "encoded")

        return AlignmentSpec(
            ColorPrimaries=EncodedPrimaries.value,
            TransferFunction=EncodedTransfer.value,
            ColorMatrix=EncodedMatrix.value,
            ColorRange=EncodedRange.value,
            SourceFps=SourceFps,
            TargetFps=TargetFps,
            VfrDetected=VfrDetected,
            TargetResolution=(Width, Height),
            SourceCrop=None,
            EncodedCrop=None,
            DeinterlaceNeeded=DeinterlaceNeeded,
            DetelecineNeeded=DetelecineNeeded,
            SourceBitDepth=SourceBitDepth,
            TargetBitDepth=TargetBitDepth,
            ChromaSubsampling=ChromaSubsampling,
            HdrDetected=HdrDetected,
            MaxEdgePx=MaxEdgePx,
            SourceDurationSec=SourceDuration,
            EncodedDurationSec=EncodedDuration,
        )

    # directive: transcode-flow-canonical
    def _SelectVideoStream(self, Probe: Dict[str, Any]) -> Dict[str, Any]:
        for Stream in Probe.get('streams', []) or []:
            if Stream.get('codec_type') == 'video':
                return Stream
        raise VmafAlignmentProbeError("No video stream in probe")

    # directive: transcode-flow-canonical
    def _ParseFps(self, RateStr: Optional[str], Field: str) -> float:
        if not RateStr or '/' not in RateStr:
            raise VmafAlignmentProbeError(f"Unparseable framerate {Field}: {RateStr!r}")
        Numer, Denom = RateStr.split('/', 1)
        try:
            N = float(Numer)
            D = float(Denom)
        except (ValueError, TypeError) as Ex:
            raise VmafAlignmentProbeError(f"Unparseable framerate {Field}: {RateStr!r}") from Ex
        if D == 0.0 or N <= 0.0:
            raise VmafAlignmentProbeError(f"Framerate {Field} invalid: {RateStr!r}")
        return N / D

    # directive: transcode-flow-canonical
    def _ParseDuration(self, Format: Dict[str, Any], Video: Dict[str, Any], Which: str) -> float:
        for Source in (Format.get('duration'), Video.get('duration')):
            if Source is None:
                continue
            try:
                Value = float(Source)
            except (ValueError, TypeError):
                continue
            if Value > 0.0:
                return Value
        raise VmafAlignmentProbeError(f"Duration unreadable for {Which}")

    # directive: transcode-flow-canonical
    def _ParseBitDepth(self, PixFmt: str, Which: str) -> int:
        Key = (PixFmt or '').strip().lower()
        if Key in self.PIX_FMT_BIT_DEPTH:
            return self.PIX_FMT_BIT_DEPTH[Key]
        raise VmafAlignmentProbeError(f"Unparseable pix_fmt for {Which}: {PixFmt!r}")

    # directive: transcode-flow-canonical
    def _ParseChroma(self, PixFmt: str, Which: str) -> str:
        Key = (PixFmt or '').strip().lower()
        if Key in self.PIX_FMT_CHROMA:
            return self.PIX_FMT_CHROMA[Key]
        raise VmafAlignmentProbeError(f"Unparseable pix_fmt for {Which}: {PixFmt!r}")

    # directive: transcode-flow-canonical
    def _IsTelecined(self, RFps: float, AvgFps: float, FieldOrder: str) -> bool:
        if FieldOrder in ('progressive', '', 'unknown'):
            return False
        return abs(RFps - 29.97) < 0.05 and abs(AvgFps - 23.976) < 0.1

    # directive: transcode-flow-canonical
    def BuildReferenceToneMap(self, Spec: AlignmentSpec, SourceTransferValue: str) -> str:
        if not Spec.HdrDetected:
            return ""
        TargetTransfer = ColorSpaceService.ParseTransfer(Spec.TransferFunction)
        SourceTransfer = ColorSpaceService.ParseTransfer(SourceTransferValue)
        if SourceTransfer == TargetTransfer:
            return ""
        return ColorSpaceService.BuildToneMapGraph(SourceTransfer, TargetTransfer)
