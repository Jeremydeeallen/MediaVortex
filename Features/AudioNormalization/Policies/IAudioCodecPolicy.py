from abc import ABC, abstractmethod
from typing import Optional, Union

from Features.AudioNormalization.AudioStrategyResult import Accept, Reject


MP4_COMPAT_AUDIO_CODECS = ('aac', 'ac3', 'eac3', 'mp3')


# directive: audio-pipeline-fail-loud
class IAudioCodecPolicy(ABC):

    # directive: audio-pipeline-fail-loud
    @abstractmethod
    def Decide(
        self,
        SourceCodec: Optional[str],
        ForceReencode: bool,
        AudioCorruptSuspect: bool,
    ) -> Union[Accept, Reject]:
        ...


# directive: audio-pipeline-fail-loud
class EAC3OrPassthroughCodecPolicy(IAudioCodecPolicy):

    # directive: audio-pipeline-fail-loud
    def Decide(self, SourceCodec, ForceReencode, AudioCorruptSuspect):
        Name = 'EAC3OrPassthroughCodecPolicy'
        Codec = (SourceCodec or '').lower()
        IsMp4Compat = Codec in MP4_COMPAT_AUDIO_CODECS

        if ForceReencode:
            return Accept({'Codec': 'eac3', 'Mode': 'reencode', 'Reason': 'force_reencode'}, Name)

        if bool(AudioCorruptSuspect):
            return Accept({'Codec': 'eac3', 'Mode': 'reencode', 'Reason': 'audio_corrupt_suspect_reencode'}, Name)

        if IsMp4Compat:
            return Accept({'Codec': 'copy', 'Mode': 'stream_copy', 'Reason': 'mp4_compat_source'}, Name)

        return Accept({'Codec': 'eac3', 'Mode': 'reencode', 'Reason': 'non_mp4_compat_source'}, Name)
