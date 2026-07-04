from dataclasses import dataclass


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
        Mode = (ProcessingMode or '').strip()
        if Mode == 'Transcode':
            return Plan(VideoOp='Reencode', AudioOp='Reencode', SubtitleOp='Preserve', ContainerOp='Mp4')
        if Mode in ('Remux', 'Quick', 'AudioFix', 'SubtitleFix'):
            return Plan(VideoOp='Copy', AudioOp='Reencode', SubtitleOp='Preserve', ContainerOp='Mp4')
        raise ValueError(f"PlanFactory.FromProcessingMode: unknown ProcessingMode={ProcessingMode!r}")
