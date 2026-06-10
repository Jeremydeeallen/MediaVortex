# directive: perfect-solid-transcode-pipeline-phase2 | # see perfect-solid-transcode-pipeline-phase2.C5
from typing import Optional


# directive: perfect-solid-transcode-pipeline-phase2 | # see perfect-solid-transcode-pipeline-phase2.C5
class AudioCodecArgsBuilder:
    """Audio re-encode policy: MP4-compat codec preserved, mp3 -> aac, else -> eac3 (per command-builder.feature.md Audio re-encode policy)."""

    MP4_COMPATIBLE_AUDIO = ('aac', 'ac3', 'eac3', 'mp3')

    _AUDIO_DEFAULT_BITRATE_BY_CHANNELS = {
        1: 96,
        2: 128,
        6: 256,
        8: 384,
    }

    # directive: perfect-solid-transcode-pipeline-phase2 | # see perfect-solid-transcode-pipeline-phase2.C5
    def DefaultAudioBitrateForChannels(self, Channels: Optional[int]) -> int:
        """Default bitrate per channel-count tier; 128 fallback when channels unknown."""
        if not Channels or Channels < 1:
            return 128
        for Threshold in sorted(self._AUDIO_DEFAULT_BITRATE_BY_CHANNELS.keys()):
            if Channels <= Threshold:
                return self._AUDIO_DEFAULT_BITRATE_BY_CHANNELS[Threshold]
        return 384

    # directive: perfect-solid-transcode-pipeline-phase2 | # see perfect-solid-transcode-pipeline-phase2.C5
    def BuildAudioCodecArgs(self, MediaFile, ProfileBitrate: Optional[int]) -> list:
        """Resolve -c:a / -b:a args: aac/ac3/eac3 preserved, mp3 routed to aac, anything else to eac3."""
        SourceCodec = (getattr(MediaFile, 'AudioCodec', None) or '').lower()
        SourceChannels = getattr(MediaFile, 'AudioChannels', None)
        SourceBitrate = getattr(MediaFile, 'AudioBitrateKbps', None)
        OperatorOverride = bool(ProfileBitrate)

        if SourceCodec in ('aac', 'ac3', 'eac3'):
            Bitrate = ProfileBitrate if OperatorOverride else (
                SourceBitrate or self.DefaultAudioBitrateForChannels(SourceChannels)
            )
            return ['-c:a', SourceCodec, '-b:a', f'{Bitrate}k']

        if SourceCodec == 'mp3':
            Bitrate = ProfileBitrate if OperatorOverride else (
                SourceBitrate or self.DefaultAudioBitrateForChannels(SourceChannels)
            )
            return ['-c:a', 'aac', '-b:a', f'{Bitrate}k']

        Bitrate = ProfileBitrate if OperatorOverride else self.DefaultAudioBitrateForChannels(SourceChannels)
        return ['-c:a', 'eac3', '-b:a', f'{Bitrate}k']
