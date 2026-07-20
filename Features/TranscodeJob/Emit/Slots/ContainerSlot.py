from typing import List


# directive: transcode-flow-canonical | # see transcode.ST5
class ContainerSlot:

    # directive: transcode-flow-canonical | # see transcode.ST5 -- use_metadata_tags preserves the mediavortex_* provenance keys in moov/udta (e2e-bug-fixes.C25); default MP4 muxer drops unknown keys.
    def Emit(self, Op: str) -> List[str]:
        Target = (Op or '').strip()
        if Target == 'Mp4':
            return ['-f', 'mp4', '-movflags', '+faststart+use_metadata_tags']
        raise ValueError(f"ContainerSlot.Emit: unknown Op={Op!r} (only 'Mp4' supported)")
