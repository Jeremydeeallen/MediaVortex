from typing import List, Optional


# directive: transcode-flow-canonical -- C33 5-branch bucket derivation
def DeriveBucket(VideoCompliant: Optional[bool], ContainerCompliant: Optional[bool], AudioCompliant: Optional[bool]) -> str:
    if VideoCompliant is None or ContainerCompliant is None or AudioCompliant is None:
        return 'Unclassified'
    if VideoCompliant and ContainerCompliant and AudioCompliant:
        return 'Compliant'
    if VideoCompliant is False:
        return 'Transcode'
    if ContainerCompliant is False:
        return 'Remux'
    return 'AudioFix'


# directive: transcode-flow-canonical -- C33 planned-ops per 5 buckets
def PlannedOps(Bucket: str, VideoCompliant: Optional[bool], ContainerCompliant: Optional[bool], AudioCompliant: Optional[bool]) -> List[str]:
    if Bucket in (None, 'Compliant', 'Unclassified'):
        return []
    Ops: List[str] = []
    if Bucket == 'Transcode':
        Ops.append('video_reencode')
        if ContainerCompliant is False:
            Ops.append('container_rewrite')
        if AudioCompliant is False:
            Ops.append('audio_reencode_loudnorm')
    elif Bucket == 'Remux':
        Ops.append('container_rewrite')
        if AudioCompliant is False:
            Ops.append('audio_reencode_loudnorm')
    elif Bucket == 'AudioFix':
        Ops.append('audio_reencode_loudnorm')
    return Ops
