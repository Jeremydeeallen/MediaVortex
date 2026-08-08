from typing import List


# directive: transcode-flow-canonical | # see transcode.ST5
class ContainerSlot:

    # directive: plan-factory-driven-by-compliance-flags | # see transcode.D2 -- 'Preserve' = source container was already compliant; per D5 output is mp4 always so args are identical to 'Mp4'
    def Emit(self, Op: str) -> List[str]:
        Target = (Op or '').strip()
        if Target in ('Mp4', 'Preserve'):
            return ['-f', 'mp4', '-movflags', '+faststart+use_metadata_tags']
        raise ValueError(f"ContainerSlot.Emit: unknown Op={Op!r} (only 'Mp4' / 'Preserve' supported)")
