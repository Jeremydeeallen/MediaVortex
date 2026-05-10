from dataclasses import dataclass
from datetime import datetime
from typing import Optional


@dataclass
class CodecCompatibilityModel:
    """One row of the (Kind, Name) -> IsAcceptable lookup.

    Replaces hardcoded class constants in QueueManagementBusinessService:
        Kind='Container'      replaces COMPATIBLE_CONTAINERS
        Kind='VideoCodec'     replaces ACCEPTABLE_VIDEO_CODECS
        Kind='AudioCodecMp4'  replaces MP4_COMPATIBLE_AUDIO_CODECS
    """
    Id: Optional[int] = None
    Kind: str = ""           # 'Container' | 'VideoCodec' | 'AudioCodecMp4'
    Name: str = ""
    IsAcceptable: bool = True
    Description: Optional[str] = None
    LastUpdated: Optional[datetime] = None
    Source: Optional[str] = None
