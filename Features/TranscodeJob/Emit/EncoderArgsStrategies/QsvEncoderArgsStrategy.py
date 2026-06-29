from typing import Any, Dict

from Features.TranscodeJob.Emit.EncoderArgsStrategies.IEncoderArgsStrategy import IEncoderArgsStrategy


class QsvEncoderArgsStrategy(IEncoderArgsStrategy):
    """Emit av1_qsv args for Intel Arc QSV. Reads Lowpower + QSV-specific knobs from ProfileSettings."""

    def AddCodecParameters(self, CommandParts: list, CodecParameters: list, ProfileSettings: Dict[str, Any]) -> None:
        Preset = ProfileSettings.get('Preset')
        if Preset is not None and Preset != '' and Preset != 'None':
            CommandParts.extend(['-preset', str(Preset)])

        RateControlMode = (ProfileSettings.get('RateControlMode') or 'vbr').lower()
        if RateControlMode == 'vbr':
            SrcKbps = ProfileSettings.get('SourceVideoBitrateKbps')
            Pct = ProfileSettings.get('SourceBitratePercent')
            MinKbps = ProfileSettings.get('MinBitrateKbps')
            MaxKbps = ProfileSettings.get('MaxBitrateKbps')
            Multiplier = ProfileSettings.get('MaxBitrateMultiplier')
            if not SrcKbps or float(SrcKbps) <= 0:
                raise ValueError(f"VBR profile cannot encode: source VideoBitrateKbps missing or zero (SrcKbps={SrcKbps}).")
            if not Pct or float(Pct) <= 0:
                raise ValueError(f"VBR profile missing SourceBitratePercent on ProfileThresholds (got {Pct}).")
            if not Multiplier or float(Multiplier) <= 0:
                raise ValueError(f"VBR profile missing MaxBitrateMultiplier on ProfileThresholds (got {Multiplier}).")
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
        elif RateControlMode == 'icq':
            CommandParts.extend(['-rc', 'icq'])
            Quality = ProfileSettings.get('Quality')
            if Quality is not None and Quality != '' and Quality != 'None':
                CommandParts.extend(['-global_quality', str(int(Quality))])
        else:
            raise ValueError(f"av1_qsv RateControlMode={RateControlMode!r} not implemented.")

        LowPower = ProfileSettings.get('LowPower')
        if LowPower is not None:
            CommandParts.extend(['-low_power', str(int(LowPower))])

        QsvExtBrc = ProfileSettings.get('QsvExtBrc')
        if QsvExtBrc is not None:
            CommandParts.extend(['-extbrc', str(int(QsvExtBrc))])

        QsvLookaheadDepth = ProfileSettings.get('QsvLookaheadDepth')
        if QsvLookaheadDepth is not None:
            CommandParts.extend(['-look_ahead', '1', '-look_ahead_depth', str(int(QsvLookaheadDepth))])

        QsvBStrategy = ProfileSettings.get('QsvBStrategy')
        if QsvBStrategy is not None:
            CommandParts.extend(['-b_strategy', str(int(QsvBStrategy))])

        QsvAdaptiveI = ProfileSettings.get('QsvAdaptiveI')
        if QsvAdaptiveI is not None:
            CommandParts.extend(['-adaptive_i', str(int(QsvAdaptiveI))])

        QsvAdaptiveB = ProfileSettings.get('QsvAdaptiveB')
        if QsvAdaptiveB is not None:
            CommandParts.extend(['-adaptive_b', str(int(QsvAdaptiveB))])

        BFrames = ProfileSettings.get('BFrames')
        if BFrames is not None:
            CommandParts.extend(['-bf', str(int(BFrames))])

        QsvTileCols = ProfileSettings.get('QsvTileCols')
        if QsvTileCols is not None:
            CommandParts.extend(['-tile_cols', str(int(QsvTileCols))])

        QsvTileRows = ProfileSettings.get('QsvTileRows')
        if QsvTileRows is not None:
            CommandParts.extend(['-tile_rows', str(int(QsvTileRows))])

        Gop = ProfileSettings.get('Gop')
        if Gop is not None and Gop != '' and Gop != 'None':
            CommandParts.extend(['-g', str(int(Gop))])
