# Strategy dispatcher: picks per-codec EncoderArgsStrategy keyed on Profile.codec; legacy flag fallback for backward compat.
from typing import Dict, Any

from Core.Logging.LoggingService import LoggingService
from Features.TranscodeJob.Emit.EncoderArgsStrategies.IEncoderArgsStrategy import IEncoderArgsStrategy
from Features.TranscodeJob.Emit.EncoderArgsStrategies.NvencEncoderArgsStrategy import NvencEncoderArgsStrategy
from Features.TranscodeJob.Emit.EncoderArgsStrategies.QsvEncoderArgsStrategy import QsvEncoderArgsStrategy
from Features.TranscodeJob.Emit.EncoderArgsStrategies.SvtAv1EncoderArgsStrategy import SvtAv1EncoderArgsStrategy


# directive: perfect-solid-transcode-pipeline-phase2 | # see perfect-solid-transcode-pipeline-phase2.C4
class CodecParameterAssembler:
    """Codec arg synthesis dispatcher. Routes to NvencEncoderArgsStrategy / QsvEncoderArgsStrategy / SvtAv1EncoderArgsStrategy by Profile.codec."""

    def __init__(self, Strategies: Dict[str, IEncoderArgsStrategy] = None):
        self.Strategies = Strategies or {
            'av1_nvenc': NvencEncoderArgsStrategy(),
            'av1_qsv':   QsvEncoderArgsStrategy(),
            'libsvtav1': SvtAv1EncoderArgsStrategy(),
        }

    def _ResolveStrategy(self, ProfileSettings: Dict[str, Any]) -> IEncoderArgsStrategy:
        """Pick strategy via Codec field; fall back to legacy UseNvidiaHardware/UseIntelHardware flag for rows without Codec set."""
        Codec = ProfileSettings.get('Codec')
        if Codec and Codec in self.Strategies:
            return self.Strategies[Codec]
        if ProfileSettings.get('UseNvidiaHardware') == 1:
            return self.Strategies['av1_nvenc']
        if ProfileSettings.get('UseIntelHardware') == 1:
            return self.Strategies['av1_qsv']
        return self.Strategies['libsvtav1']

    # directive: perfect-solid-transcode-pipeline-phase2 | # see perfect-solid-transcode-pipeline-phase2.C4
    def AddCodecParameters(self, CommandParts: list, CodecParameters: list, ProfileSettings: Dict[str, Any]) -> None:
        """Dispatch codec arg emission to the per-encoder Strategy."""
        try:
            self._ResolveStrategy(ProfileSettings).AddCodecParameters(CommandParts, CodecParameters, ProfileSettings)
            VideoBitrate = ProfileSettings.get('VideoBitrateKbps')
            if VideoBitrate and VideoBitrate != '' and VideoBitrate != 'None':
                CommandParts.extend(['-maxrate', f'{VideoBitrate}k'])
        except Exception as e:
            LoggingService.LogException(
                "Error adding codec parameters -- transcode will run with partial/default settings",
                e, "AddCodecParameters", "CodecParameterAssembler"
            )

    # directive: perfect-solid-transcode-pipeline-phase2 | # see perfect-solid-transcode-pipeline-phase2.C4
    def AddFilmGrainParameter(self, CommandParts: list, CodecParameters: list, ProfileSettings: Dict[str, Any]) -> None:
        """Dispatch film-grain emission to the per-encoder Strategy (SvtAv1 emits, NVENC/QSV no-op)."""
        try:
            self._ResolveStrategy(ProfileSettings).AddFilmGrainParameter(CommandParts, CodecParameters, ProfileSettings)
        except Exception as e:
            LoggingService.LogException(
                "Error adding film-grain parameter -- transcode will run without grain synthesis",
                e, "AddFilmGrainParameter", "CodecParameterAssembler"
            )

    # directive: perfect-solid-transcode-pipeline-phase2 | # see perfect-solid-transcode-pipeline-phase2.C4
    def AddPixelFormatParameter(self, CommandParts: list, CodecParameters: list, ProfileSettings: Dict[str, Any]) -> None:
        """Emit -pix_fmt arg pair from ProfileSettings.PixelFormat (encoder-agnostic; same arg for all backends)."""
        try:
            PixFmt = ProfileSettings.get('PixelFormat')
            if PixFmt:
                CommandParts.extend(['-pix_fmt', str(PixFmt)])
        except Exception as e:
            LoggingService.LogException(
                "Error adding pixel format parameter -- transcode will fall back to encoder default",
                e, "AddPixelFormatParameter", "CodecParameterAssembler"
            )
