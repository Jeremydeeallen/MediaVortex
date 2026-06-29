from typing import Any, Dict

from Features.TranscodeJob.Emit.EncoderArgsStrategies.IEncoderArgsStrategy import IEncoderArgsStrategy


class NvencEncoderArgsStrategy(IEncoderArgsStrategy):
    """Emit av1_nvenc-specific args. Reads SpatialAq/TemporalAq/WeightedPred/AqStrength from ProfileSettings (COALESCEs to historical defaults)."""

    def AddCodecParameters(self, CommandParts: list, CodecParameters: list, ProfileSettings: Dict[str, Any]) -> None:
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
        else:
            CommandParts.extend(['-b:v', '0'])
            Quality = ProfileSettings.get('Quality')
            if Quality is not None and Quality != '' and Quality != 'None':
                CommandParts.extend(['-cq', str(Quality)])

        # SpatialAq/TemporalAq COALESCE to historical literal default (1). Surfaced as Profile columns 2026-06-29.
        SpatialAq = ProfileSettings.get('SpatialAq', 1) if ProfileSettings.get('SpatialAq') is not None else 1
        TemporalAq = ProfileSettings.get('TemporalAq', 1) if ProfileSettings.get('TemporalAq') is not None else 1
        CommandParts.extend(['-spatial-aq', str(int(SpatialAq)), '-temporal-aq', str(int(TemporalAq))])

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

        WeightedPred = ProfileSettings.get('WeightedPred')
        if WeightedPred is not None:
            CommandParts.extend(['-weighted_pred', str(int(WeightedPred))])

        Gop = ProfileSettings.get('Gop')
        if Gop is not None and Gop != '' and Gop != 'None':
            CommandParts.extend(['-g', str(int(Gop))])
