from dataclasses import dataclass

from Features.TranscodeJob import ProcessingModeMetadata


@dataclass(frozen=True)
# directive: label-decides-command | # see transcode.ST6
class Plan:
    VideoOp: str
    AudioOp: str
    SubtitleOp: str
    ContainerOp: str


# directive: label-decides-command | # see transcode.ST6
class PlanFactory:

    # directive: label-decides-command | # see transcode.ST6
    def FromProcessingMode(self, Mode) -> Plan:
        Meta = ProcessingModeMetadata.Get(Mode)
        if Meta is None:
            raise ValueError(f"PlanFactory.FromProcessingMode: unknown ProcessingMode {Mode!r}")
        return Plan(
            VideoOp=Meta['PlanVideoOp'],
            AudioOp=Meta['PlanAudioOp'],
            SubtitleOp=Meta['PlanSubtitleOp'],
            ContainerOp=Meta['PlanContainerOp'],
        )
