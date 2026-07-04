from typing import Any, Dict, List, Optional

from Features.TranscodeJob.Emit.EncoderArgsStrategies.SvtAv1EncoderArgsStrategy import SvtAv1EncoderArgsStrategy


# directive: transcode-flow-canonical | # see transcode.ST5
class VideoSlot:

    # directive: transcode-flow-canonical | # see transcode.ST5
    def __init__(self, VideoFilterBuilder=None, SvtAv1Args=None):
        self.VideoFilterBuilder = VideoFilterBuilder
        self.SvtAv1Args = SvtAv1Args or SvtAv1EncoderArgsStrategy()

    # directive: transcode-flow-canonical | # see transcode.ST5
    def Emit(self, Op: str, MediaFile, ProfileSettings: Dict[str, Any],
             CodecParameters: List[str], ScaleFilter: Optional[str], MaxCpuThreads: Optional[int]) -> List[str]:
        if Op == 'Copy':
            return self._EmitStreamCopy(MediaFile)
        if Op == 'Reencode':
            return self._EmitReencode(MediaFile, ProfileSettings, CodecParameters, ScaleFilter, MaxCpuThreads)
        raise ValueError(f"VideoSlot.Emit: unknown Op={Op!r}")

    # directive: transcode-flow-canonical | # see transcode.ST5
    def _EmitStreamCopy(self, MediaFile) -> List[str]:
        Parts: List[str] = ['-map', '0:v:0', '-c:v', 'copy']
        VideoCodec = (getattr(MediaFile, 'Codec', '') or '').lower()
        if VideoCodec in ('hevc', 'h265', 'x265'):
            Parts.extend(['-tag:v', 'hvc1'])
        return Parts

    # directive: transcode-flow-canonical | # see transcode.ST5
    def _EmitReencode(self, MediaFile, ProfileSettings: Dict[str, Any], CodecParameters: List[str],
                      ScaleFilter: Optional[str], MaxCpuThreads: Optional[int]) -> List[str]:
        Parts: List[str] = ['-map', '0:v:0']
        UseNvidiaHardware = ProfileSettings.get('UseNvidiaHardware', 0)
        Codec = ProfileSettings.get('Codec')
        VideoCodec = 'av1_nvenc' if UseNvidiaHardware == 1 else (Codec or 'libsvtav1')
        Parts.extend(['-c:v', VideoCodec])
        if MaxCpuThreads:
            Parts.extend(['-threads', str(MaxCpuThreads)])
        self._AppendCodecParameters(Parts, CodecParameters, ProfileSettings, VideoCodec)
        RawInterlaced = getattr(MediaFile, 'IsInterlaced', None) if MediaFile else None
        IsInterlaced = str(RawInterlaced).strip().lower() in ('1', 'true', 'yes', 't') if RawInterlaced is not None else False
        if self.VideoFilterBuilder is not None:
            VideoFilter = self.VideoFilterBuilder.Build(ProfileSettings, ScaleFilter, IsInterlaced)
            if VideoFilter:
                Parts.extend(['-vf', f'"{VideoFilter}"'])
        self._AppendFilmGrain(Parts, CodecParameters, ProfileSettings, VideoCodec)
        PixFmt = ProfileSettings.get('PixelFormat')
        if PixFmt:
            Parts.extend(['-pix_fmt', str(PixFmt)])
        return Parts

    # directive: transcode-flow-canonical | # see transcode.ST5
    def _AppendCodecParameters(self, Parts: List[str], CodecParameters: List[str],
                               ProfileSettings: Dict[str, Any], VideoCodec: str) -> None:
        if VideoCodec == 'av1_nvenc':
            self._EmitNvencArgs(Parts, ProfileSettings)
        elif VideoCodec == 'av1_qsv':
            self._EmitQsvArgs(Parts, ProfileSettings)
        else:
            self.SvtAv1Args.AddCodecParameters(Parts, CodecParameters, ProfileSettings)
        VideoBitrate = ProfileSettings.get('VideoBitrateKbps')
        if VideoBitrate and VideoBitrate != '' and VideoBitrate != 'None':
            Parts.extend(['-maxrate', f'{VideoBitrate}k'])

    # directive: transcode-flow-canonical | # see transcode.ST5
    def _AppendFilmGrain(self, Parts: List[str], CodecParameters: List[str],
                         ProfileSettings: Dict[str, Any], VideoCodec: str) -> None:
        if VideoCodec in ('av1_nvenc', 'av1_qsv'):
            return
        self.SvtAv1Args.AddFilmGrainParameter(Parts, CodecParameters, ProfileSettings)

    # directive: transcode-flow-canonical | # see transcode.ST5
    def _EmitNvencArgs(self, Parts: List[str], ProfileSettings: Dict[str, Any]) -> None:
        Preset = ProfileSettings.get('Preset')
        if Preset is not None and Preset != '' and Preset != 'None':
            Parts.extend(['-preset', f'p{Preset}'])
        Tune = ProfileSettings.get('Tune')
        if Tune:
            Parts.extend(['-tune', str(Tune)])
        Multipass = ProfileSettings.get('Multipass')
        if Multipass:
            Parts.extend(['-multipass', str(Multipass)])
        Parts.extend(['-rc', 'vbr'])
        RateControlMode = (ProfileSettings.get('RateControlMode') or 'cq').lower()
        if RateControlMode == 'vbr':
            self._EmitNvencVbrRateArgs(Parts, ProfileSettings)
        else:
            Parts.extend(['-b:v', '0'])
            Quality = ProfileSettings.get('Quality')
            if Quality is not None and Quality != '' and Quality != 'None':
                Parts.extend(['-cq', str(Quality)])
        SpatialAq = ProfileSettings.get('SpatialAq', 1) if ProfileSettings.get('SpatialAq') is not None else 1
        TemporalAq = ProfileSettings.get('TemporalAq', 1) if ProfileSettings.get('TemporalAq') is not None else 1
        Parts.extend(['-spatial-aq', str(int(SpatialAq)), '-temporal-aq', str(int(TemporalAq))])
        AqStrength = ProfileSettings.get('AqStrength')
        if AqStrength is not None:
            Parts.extend(['-aq-strength', str(int(AqStrength))])
        RcLookahead = ProfileSettings.get('RcLookahead')
        if RcLookahead is not None:
            Parts.extend(['-rc-lookahead', str(int(RcLookahead))])
        BFrames = ProfileSettings.get('BFrames')
        if BFrames is not None:
            Parts.extend(['-bf', str(int(BFrames))])
        BRefMode = ProfileSettings.get('BRefMode')
        if BRefMode:
            Parts.extend(['-b_ref_mode', str(BRefMode)])
        WeightedPred = ProfileSettings.get('WeightedPred')
        if WeightedPred is not None:
            Parts.extend(['-weighted_pred', str(int(WeightedPred))])
        Gop = ProfileSettings.get('Gop')
        if Gop is not None and Gop != '' and Gop != 'None':
            Parts.extend(['-g', str(int(Gop))])

    # directive: transcode-flow-canonical | # see transcode.ST5
    def _EmitNvencVbrRateArgs(self, Parts: List[str], ProfileSettings: Dict[str, Any]) -> None:
        TargetKbps = ProfileSettings.get('TargetKbps')
        Multiplier = ProfileSettings.get('MaxBitrateMultiplier')
        if TargetKbps is None or int(TargetKbps) <= 0:
            raise ValueError(f"NVENC VBR profile missing ProfileThresholds.TargetKbps (got {TargetKbps}).")
        if not Multiplier or float(Multiplier) <= 0:
            raise ValueError(f"NVENC VBR profile missing ProfileThresholds.MaxBitrateMultiplier (got {Multiplier}).")
        Calc = int(TargetKbps)
        MaxRate = int(round(Calc * float(Multiplier)))
        Parts.extend([
            '-b:v', f'{Calc}k',
            '-maxrate:v', f'{MaxRate}k',
            '-bufsize:v', f'{MaxRate}k',
        ])

    # directive: transcode-flow-canonical | # see transcode.ST5
    def _EmitQsvArgs(self, Parts: List[str], ProfileSettings: Dict[str, Any]) -> None:
        Preset = ProfileSettings.get('Preset')
        if Preset is not None and Preset != '' and Preset != 'None':
            Parts.extend(['-preset', str(Preset)])
        RateControlMode = (ProfileSettings.get('RateControlMode') or 'vbr').lower()
        if RateControlMode == 'vbr':
            self._EmitQsvVbrRateArgs(Parts, ProfileSettings)
        elif RateControlMode == 'icq':
            Parts.extend(['-rc', 'icq'])
            IcqQ = ProfileSettings.get('IcqQ')
            if IcqQ is None:
                raise ValueError("QSV ICQ profile missing ProfileThresholds.IcqQ.")
            Parts.extend(['-global_quality', str(int(IcqQ))])
        else:
            raise ValueError(f"av1_qsv RateControlMode={RateControlMode!r} not implemented.")
        LowPower = ProfileSettings.get('LowPower')
        if LowPower is not None:
            Parts.extend(['-low_power', str(int(LowPower))])
        for Key, Flag in (
            ('QsvExtBrc', '-extbrc'),
            ('QsvBStrategy', '-b_strategy'),
            ('QsvAdaptiveI', '-adaptive_i'),
            ('QsvAdaptiveB', '-adaptive_b'),
            ('BFrames', '-bf'),
            ('QsvTileCols', '-tile_cols'),
            ('QsvTileRows', '-tile_rows'),
        ):
            Value = ProfileSettings.get(Key)
            if Value is not None:
                Parts.extend([Flag, str(int(Value))])
        QsvLookaheadDepth = ProfileSettings.get('QsvLookaheadDepth')
        if QsvLookaheadDepth is not None:
            Parts.extend(['-look_ahead', '1', '-look_ahead_depth', str(int(QsvLookaheadDepth))])
        Gop = ProfileSettings.get('Gop')
        if Gop is not None and Gop != '' and Gop != 'None':
            Parts.extend(['-g', str(int(Gop))])

    # directive: transcode-flow-canonical | # see transcode.ST5
    def _EmitQsvVbrRateArgs(self, Parts: List[str], ProfileSettings: Dict[str, Any]) -> None:
        TargetKbps = ProfileSettings.get('TargetKbps')
        Multiplier = ProfileSettings.get('MaxBitrateMultiplier')
        if TargetKbps is None or int(TargetKbps) <= 0:
            raise ValueError(f"QSV VBR profile missing ProfileThresholds.TargetKbps (got {TargetKbps}).")
        if not Multiplier or float(Multiplier) <= 0:
            raise ValueError(f"QSV VBR profile missing ProfileThresholds.MaxBitrateMultiplier (got {Multiplier}).")
        Calc = int(TargetKbps)
        MaxRate = int(round(Calc * float(Multiplier)))
        Parts.extend([
            '-b:v', f'{Calc}k',
            '-maxrate:v', f'{MaxRate}k',
            '-bufsize:v', f'{MaxRate}k',
        ])
