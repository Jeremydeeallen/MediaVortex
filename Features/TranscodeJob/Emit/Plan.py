from dataclasses import dataclass

from Features.TranscodeJob import ProcessingModeMetadata


# directive: transcode-flow-canonical | # see transcode.ST5
@dataclass(frozen=True)
class Plan:
    VideoOp: str
    AudioOp: str
    SubtitleOp: str
    ContainerOp: str


# directive: transcode-flow-canonical | # see transcode.ST5
class PlanFactory:

    # directive: transcode-flow-canonical | # see transcode.ST5
    def FromProcessingMode(self, ProcessingMode: str) -> Plan:
        Meta = ProcessingModeMetadata.Get((ProcessingMode or '').strip())
        if Meta is None:
            raise ValueError(f"PlanFactory.FromProcessingMode: unknown ProcessingMode={ProcessingMode!r}")
        return Plan(
            VideoOp=Meta['PlanVideoOp'],
            AudioOp=Meta['PlanAudioOp'],
            SubtitleOp=Meta['PlanSubtitleOp'],
            ContainerOp=Meta['PlanContainerOp'],
        )
