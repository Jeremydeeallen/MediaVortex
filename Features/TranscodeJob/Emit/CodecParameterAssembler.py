# directive: perfect-solid-transcode-pipeline-phase2 | # see perfect-solid-transcode-pipeline-phase2.C4
from typing import Dict, Any

from Core.Logging.LoggingService import LoggingService


# directive: perfect-solid-transcode-pipeline-phase2 | # see perfect-solid-transcode-pipeline-phase2.C4
class CodecParameterAssembler:
    """Assembles codec, film-grain, and pixel-format ffmpeg parameter pairs from ProfileSettings."""

    # directive: perfect-solid-transcode-pipeline-phase2 | # see perfect-solid-transcode-pipeline-phase2.C4
    def AddCodecParameters(self, CommandParts: list, CodecParameters: list, ProfileSettings: Dict[str, Any]) -> None:
        """Append codec args (NVENC knobs or software CRF/preset) read from ProfileSettings (no literals)."""
        try:
            ParamLookup = {}
            for Param in CodecParameters:
                ParamLookup[Param['ParameterName']] = Param

            UseNvidiaHardware = ProfileSettings.get('UseNvidiaHardware', 0)

            if UseNvidiaHardware == 1:
                Preset = ProfileSettings.get('Preset')
                if Preset is not None and Preset != '' and Preset != 'None':
                    CommandParts.extend(['-preset', f'p{Preset}'])

                Tune = ProfileSettings.get('Tune')
                if Tune:
                    CommandParts.extend(['-tune', str(Tune)])

                Multipass = ProfileSettings.get('Multipass')
                if Multipass:
                    CommandParts.extend(['-multipass', str(Multipass)])

                CommandParts.extend(['-rc', 'vbr'])

                RateControlMode = (ProfileSettings.get('RateControlMode') or 'cq').lower()
                if RateControlMode == 'vbr':
                    SrcKbps = ProfileSettings.get('SourceVideoBitrateKbps')
                    Pct = ProfileSettings.get('SourceBitratePercent')
                    MinKbps = ProfileSettings.get('MinBitrateKbps')
                    MaxKbps = ProfileSettings.get('MaxBitrateKbps')
                    Multiplier = ProfileSettings.get('MaxBitrateMultiplier')
                    if not SrcKbps or float(SrcKbps) <= 0:
                        raise ValueError(
                            f"VBR profile cannot encode: source VideoBitrateKbps missing or zero (SrcKbps={SrcKbps})."
                        )
                    if not Pct or float(Pct) <= 0:
                        raise ValueError(
                            f"VBR profile missing SourceBitratePercent on ProfileThresholds (got {Pct})."
                        )
                    if not Multiplier or float(Multiplier) <= 0:
                        raise ValueError(
                            f"VBR profile missing MaxBitrateMultiplier on ProfileThresholds (got {Multiplier})."
                        )
                    Calc = int(round(float(SrcKbps) * float(Pct) / 100.0))
                    if MinKbps is not None:
                        Calc = max(Calc, int(MinKbps))
                    if MaxKbps is not None:
                        Calc = min(Calc, int(MaxKbps))
                    MaxRate = int(round(Calc * float(Multiplier)))
                    CommandParts.extend([
                        '-b:v', f'{Calc}k',
                        '-maxrate:v', f'{MaxRate}k',
                        '-bufsize:v', f'{MaxRate}k',
                    ])
                else:
                    CommandParts.extend(['-b:v', '0'])
                    Quality = ProfileSettings.get('Quality')
                    if Quality is not None and Quality != '' and Quality != 'None':
                        CommandParts.extend(['-cq', str(Quality)])

                CommandParts.extend(['-spatial-aq', '1', '-temporal-aq', '1'])
                AqStrength = ProfileSettings.get('AqStrength')
                if AqStrength is not None:
                    CommandParts.extend(['-aq-strength', str(int(AqStrength))])

                RcLookahead = ProfileSettings.get('RcLookahead')
                if RcLookahead is not None:
                    CommandParts.extend(['-rc-lookahead', str(int(RcLookahead))])

                BFrames = ProfileSettings.get('BFrames')
                if BFrames is not None:
                    CommandParts.extend(['-bf', str(int(BFrames))])

                BRefMode = ProfileSettings.get('BRefMode')
                if BRefMode:
                    CommandParts.extend(['-b_ref_mode', str(BRefMode)])

                Gop = ProfileSettings.get('Gop')
                if Gop is not None and Gop != '' and Gop != 'None':
                    CommandParts.extend(['-g', str(int(Gop))])
            else:
                Quality = ProfileSettings.get('Quality')
                if Quality is not None and Quality != '' and Quality != 'None':
                    if 'crf' in ParamLookup:
                        CommandParts.extend(['-crf', str(Quality)])

                Preset = ProfileSettings.get('Preset')
                if Preset is not None and Preset != '' and Preset != 'None':
                    if 'preset' in ParamLookup:
                        CommandParts.extend(['-preset', str(Preset)])

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
        """Append SVT-AV1 film-grain param when software path + supported + FilmGrain>0; skip for NVENC."""
        try:
            UseNvidiaHardware = ProfileSettings.get('UseNvidiaHardware', 0)

            if UseNvidiaHardware == 1:
                return

            ParamLookup = {}
            for Param in CodecParameters:
                ParamLookup[Param['ParameterName']] = Param

            if 'film-grain' in ParamLookup:
                FilmGrain = ProfileSettings.get('FilmGrain')
                if FilmGrain is not None and FilmGrain != '' and FilmGrain != 'None' and FilmGrain > 0:
                    CommandParts.extend(['-svtav1-params', f'film-grain={FilmGrain}'])

        except Exception as e:
            LoggingService.LogException(
                "Error adding film-grain parameter -- transcode will run without grain synthesis",
                e, "AddFilmGrainParameter", "CodecParameterAssembler"
            )

    # directive: perfect-solid-transcode-pipeline-phase2 | # see perfect-solid-transcode-pipeline-phase2.C4
    def AddPixelFormatParameter(self, CommandParts: list, CodecParameters: list, ProfileSettings: Dict[str, Any]) -> None:
        """Emit -pix_fmt arg pair from ProfileSettings.PixelFormat (NVENC vs SVT-AV1 mismatch routes via autoconvert)."""
        try:
            PixFmt = ProfileSettings.get('PixelFormat')
            if PixFmt:
                CommandParts.extend(['-pix_fmt', str(PixFmt)])

        except Exception as e:
            LoggingService.LogException(
                "Error adding pixel format parameter -- transcode will fall back to encoder default",
                e, "AddPixelFormatParameter", "CodecParameterAssembler"
            )
