from dataclasses import dataclass, replace


# directive: plan-factory-driven-by-compliance-flags | # see transcode.D2
@dataclass(frozen=True)
class Plan:
    VideoOp: str
    AudioOp: str
    SubtitleOp: str
    ContainerOp: str

    # directive: partial-pipeline-completion | # see transcode.D13
    def WithSlotForcedToCopy(self, Side: str) -> 'Plan':
        if Side == 'VideoSlot':
            return replace(self, VideoOp='Copy')
        if Side == 'AudioSlot':
            return replace(self, AudioOp='Copy')
        raise ValueError(f"WithSlotForcedToCopy: Side must be 'VideoSlot' or 'AudioSlot', got {Side!r}")


# directive: plan-factory-driven-by-compliance-flags | # see transcode.D2
class PlanFactory:

    # directive: plan-factory-driven-by-compliance-flags | # see transcode.D2 -- per-dimension compliance drives slot ops; ProcessingMode is a reporting tag (D3), not a shape input
    def FromComplianceState(self, MediaFile) -> Plan:
        VideoCompliant = getattr(MediaFile, 'VideoCompliant', None)
        AudioCompliant = getattr(MediaFile, 'AudioCompliant', None)
        ContainerCompliant = getattr(MediaFile, 'ContainerCompliant', None)
        if VideoCompliant is None or AudioCompliant is None or ContainerCompliant is None:
            raise ValueError(
                f"PlanFactory.FromComplianceState: MediaFile.Id={getattr(MediaFile, 'Id', None)} "
                f"has None compliance flag (VideoCompliant={VideoCompliant}, "
                f"AudioCompliant={AudioCompliant}, ContainerCompliant={ContainerCompliant}); "
                f"admission gate should have deferred this file to Unclassified."
            )
        return Plan(
            VideoOp='Copy' if VideoCompliant else 'Reencode',
            AudioOp='Copy' if AudioCompliant else 'Reencode',
            SubtitleOp='Preserve',
            ContainerOp='Preserve' if ContainerCompliant else 'Mp4',
        )
