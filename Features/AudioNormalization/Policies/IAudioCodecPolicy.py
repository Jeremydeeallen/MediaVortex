from abc import ABC, abstractmethod
from typing import Optional, Union

from Features.AudioNormalization.AudioStrategyResult import Accept, Reject


MP4_COMPAT_AUDIO_CODECS = ('aac', 'ac3', 'eac3', 'mp3')


# directive: worker-runtime-state
class IAudioCodecPolicy(ABC):

    # directive: worker-runtime-state
    @abstractmethod
    def Decide(
        self,
        SourceCodec: Optional[str],
        ForceReencode: bool,
        AudioCorruptSuspect: bool,
        ProfileCeilingKbps: Optional[int] = None,
        SourceBitrateKbps: Optional[int] = None,
    ) -> Union[Accept, Reject]:
        ...


# directive: worker-runtime-state
class EAC3OrPassthroughCodecPolicy(IAudioCodecPolicy):

    # directive: worker-runtime-state
    def Decide(self, SourceCodec, ForceReencode, AudioCorruptSuspect, ProfileCeilingKbps=None, SourceBitrateKbps=None):
        Name = 'EAC3OrPassthroughCodecPolicy'
        Codec = (SourceCodec or '').lower()
        IsMp4Compat = Codec in MP4_COMPAT_AUDIO_CODECS

        if ForceReencode:
            return Accept({'Codec': 'eac3', 'Mode': 'reencode', 'Reason': 'force_reencode'}, Name)

        if bool(AudioCorruptSuspect):
            return Accept({'Codec': 'eac3', 'Mode': 'reencode', 'Reason': 'audio_corrupt_suspect_reencode'}, Name)

        if ProfileCeilingKbps is not None and SourceBitrateKbps is not None:
            if int(SourceBitrateKbps) > int(ProfileCeilingKbps):
                return Accept({'Codec': 'eac3', 'Mode': 'reencode', 'Reason': 'source_bitrate_over_ceiling'}, Name)

        if IsMp4Compat:
            return Accept({'Codec': 'copy', 'Mode': 'stream_copy', 'Reason': 'mp4_compat_source'}, Name)

        return Accept({'Codec': 'eac3', 'Mode': 'reencode', 'Reason': 'non_mp4_compat_source'}, Name)
