# directive: perfect-solid-transcode-pipeline-phase2 | # see perfect-solid-transcode-pipeline-phase2.C5

import sys
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from Features.TranscodeJob.Emit.AudioCodecArgsBuilder import AudioCodecArgsBuilder


# directive: perfect-solid-transcode-pipeline-phase2 | # see perfect-solid-transcode-pipeline-phase2.C5
def _MakeMediaFile(AudioCodec=None, AudioChannels=None, AudioBitrateKbps=None):
    """Build a stub MediaFile exposing audio-related attributes."""
    return SimpleNamespace(
        AudioCodec=AudioCodec,
        AudioChannels=AudioChannels,
        AudioBitrateKbps=AudioBitrateKbps,
    )


# directive: perfect-solid-transcode-pipeline-phase2 | # see perfect-solid-transcode-pipeline-phase2.C5
class TestAudioCodecArgsBuilder:
    """Verify audio codec selection logic ported from CommandBuilder.BuildAudioCodecArgs."""

    # directive: perfect-solid-transcode-pipeline-phase2 | # see perfect-solid-transcode-pipeline-phase2.C5
    def test_default_audio_bitrate_for_2_channels(self):
        """Stereo (2ch) default bitrate = 128 kbps."""
        Builder = AudioCodecArgsBuilder()
        assert Builder.DefaultAudioBitrateForChannels(2) == 128

    # directive: perfect-solid-transcode-pipeline-phase2 | # see perfect-solid-transcode-pipeline-phase2.C5
    def test_default_audio_bitrate_for_6_channels(self):
        """5.1 (6ch) default bitrate = 256 kbps."""
        Builder = AudioCodecArgsBuilder()
        assert Builder.DefaultAudioBitrateForChannels(6) == 256

    # directive: perfect-solid-transcode-pipeline-phase2 | # see perfect-solid-transcode-pipeline-phase2.C5
    def test_default_audio_bitrate_for_8_channels(self):
        """7.1 (8ch) default bitrate = 384 kbps."""
        Builder = AudioCodecArgsBuilder()
        assert Builder.DefaultAudioBitrateForChannels(8) == 384

    # directive: perfect-solid-transcode-pipeline-phase2 | # see perfect-solid-transcode-pipeline-phase2.C5
    def test_default_audio_bitrate_handles_none(self):
        """None channels => 128 default."""
        Builder = AudioCodecArgsBuilder()
        assert Builder.DefaultAudioBitrateForChannels(None) == 128

    # directive: perfect-solid-transcode-pipeline-phase2 | # see perfect-solid-transcode-pipeline-phase2.C5
    def test_aac_source_preserved(self):
        """AAC source => -c:a aac with source bitrate."""
        Builder = AudioCodecArgsBuilder()
        Mf = _MakeMediaFile(AudioCodec='aac', AudioChannels=2, AudioBitrateKbps=160)
        Args = Builder.BuildAudioCodecArgs(Mf, ProfileBitrate=None)
        assert Args == ['-c:a', 'aac', '-b:a', '160k']

    # directive: perfect-solid-transcode-pipeline-phase2 | # see perfect-solid-transcode-pipeline-phase2.C5
    def test_eac3_source_preserved(self):
        """EAC3 source => -c:a eac3 with source bitrate."""
        Builder = AudioCodecArgsBuilder()
        Mf = _MakeMediaFile(AudioCodec='eac3', AudioChannels=6, AudioBitrateKbps=384)
        Args = Builder.BuildAudioCodecArgs(Mf, ProfileBitrate=None)
        assert Args == ['-c:a', 'eac3', '-b:a', '384k']

    # directive: perfect-solid-transcode-pipeline-phase2 | # see perfect-solid-transcode-pipeline-phase2.C5
    def test_profile_bitrate_overrides_source(self):
        """ProfileBitrate set => override source bitrate."""
        Builder = AudioCodecArgsBuilder()
        Mf = _MakeMediaFile(AudioCodec='aac', AudioChannels=2, AudioBitrateKbps=160)
        Args = Builder.BuildAudioCodecArgs(Mf, ProfileBitrate=192)
        assert Args == ['-c:a', 'aac', '-b:a', '192k']

    # directive: perfect-solid-transcode-pipeline-phase2 | # see perfect-solid-transcode-pipeline-phase2.C5
    def test_mp3_source_converted_to_aac(self):
        """MP3 source => -c:a aac (mp3 is not MP4-stream-copy-compatible for mp4)."""
        Builder = AudioCodecArgsBuilder()
        Mf = _MakeMediaFile(AudioCodec='mp3', AudioChannels=2, AudioBitrateKbps=128)
        Args = Builder.BuildAudioCodecArgs(Mf, ProfileBitrate=None)
        assert Args == ['-c:a', 'aac', '-b:a', '128k']

    # directive: perfect-solid-transcode-pipeline-phase2 | # see perfect-solid-transcode-pipeline-phase2.C5
    def test_unknown_source_routed_to_eac3(self):
        """Unknown source codec (e.g. dts) => -c:a eac3 with default bitrate."""
        Builder = AudioCodecArgsBuilder()
        Mf = _MakeMediaFile(AudioCodec='dts', AudioChannels=6)
        Args = Builder.BuildAudioCodecArgs(Mf, ProfileBitrate=None)
        assert Args == ['-c:a', 'eac3', '-b:a', '256k']
