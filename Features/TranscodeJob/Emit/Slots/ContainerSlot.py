from typing import List


# directive: transcode-flow-canonical | # see transcode.ST5
class ContainerSlot:

    # directive: transcode-flow-canonical | # see transcode.ST5
    def Emit(self, Op: str) -> List[str]:
        Target = (Op or '').strip()
        if Target == 'Mp4':
            return ['-f', 'mp4', '-movflags', '+faststart']
        raise ValueError(f"ContainerSlot.Emit: unknown Op={Op!r} (only 'Mp4' supported)")
