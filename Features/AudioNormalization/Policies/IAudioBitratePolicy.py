from abc import ABC, abstractmethod
from typing import Optional, Union

from Features.AudioNormalization.AudioStrategyResult import Accept, Reject


# directive: audio-pipeline-fail-loud
class IAudioBitratePolicy(ABC):

    # directive: audio-pipeline-fail-loud
    @abstractmethod
    def Decide(
        self,
        ProfileCeilingKbps: Optional[int],
        SourceBitrateKbps: Optional[int],
        ConfigBitrateKbps: Optional[int],
    ) -> Union[Accept, Reject]:
        ...


# directive: audio-pipeline-fail-loud
class ProfileCeilingBitratePolicy(IAudioBitratePolicy):

    # directive: audio-pipeline-fail-loud
    def Decide(self, ProfileCeilingKbps, SourceBitrateKbps, ConfigBitrateKbps):
        Name = 'ProfileCeilingBitratePolicy'
        Ceiling = int(ProfileCeilingKbps) if ProfileCeilingKbps is not None else None
        Config = int(ConfigBitrateKbps) if ConfigBitrateKbps is not None else None
        Source = int(SourceBitrateKbps) if SourceBitrateKbps is not None else None

        if Ceiling is None and Config is None:
            return Reject('no_ceiling_and_no_config_bitrate', Name)

        if Ceiling is None:
            return Accept(Config, Name)

        if Config is not None:
            return Accept(min(Config, Ceiling), Name)

        if Source is not None:
            return Accept(min(Source, Ceiling), Name)

        return Accept(Ceiling, Name)
